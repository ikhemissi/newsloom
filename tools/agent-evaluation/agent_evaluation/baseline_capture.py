import hashlib
import json
from typing import Literal

from pydantic import Field, JsonValue, StrictBool, StrictInt, StrictStr

from agent_evaluation.baseline_budget import BaselineBudget, BaselineRun
from agent_evaluation.baseline_inputs import CaseId, CaseReceipt, load_fixture, parse_document
from agent_evaluation.baseline_ipc import PrivateCaptureProcess
from agent_evaluation.baseline_scoring import EvidenceSnapshot, TransientAnswer
from agent_evaluation.inputs import ROOT, StrictModel
from agent_evaluation.policy import EvaluationFailure

CAPTURE_ENVIRONMENT = (
    "AGENT_TENANT_ID",
    "AGENT_API_CLIENT_ID",
    "MCP_API_CLIENT_ID",
    "MCP_RESOURCE_URL",
    "AGENT_PUBLIC_CLIENT_ID",
    "AGENT_RESOURCE_URL",
    "MCP_TENANT_ID",
    "MCP_PUBLIC_CLIENT_ID",
)


class WireReceipt(StrictModel):
    outcome: Literal["supported", "limited", "no_match"]
    items: StrictInt = Field(ge=0, le=10)
    user_preserved: StrictBool
    validated: StrictBool
    tool_calls: StrictInt = Field(ge=1, le=8)
    generation_calls: StrictInt = Field(ge=0, le=4)
    usage_observed_calls: StrictInt = Field(ge=0, le=4)
    input_tokens: StrictInt = Field(ge=0, le=262144)
    output_tokens: StrictInt = Field(ge=0, le=4096)


class CaptureReply(StrictModel):
    answer: StrictStr | None = Field(repr=False)
    evidence: tuple[EvidenceSnapshot, ...] = Field(max_length=10, repr=False)
    http_status: Literal[200, 401, 403]
    receipt: WireReceipt | None
    elapsed_ms: StrictInt = Field(ge=0, le=120000)


class CaptureSession:
    def __init__(
        self, budget: BaselineBudget, run: BaselineRun, environment: dict[str, str]
    ) -> None:
        progress = run.load_scoring_progress()
        if (
            progress.state != "calibrated"
            or budget.agents
            or progress.approval_sha256 != run.canonical_sha256
            or progress.frozen_sha256 != budget.approval.frozen_sha256
            or set(CAPTURE_ENVIRONMENT) - environment.keys()
        ):
            raise EvaluationFailure("baseline_capture_calibration_required")
        self.budget, self.run = budget, run
        self.environment = {key: environment[key] for key in CAPTURE_ENVIRONMENT}
        self.worker = PrivateCaptureProcess(
            (str(ROOT / ".venv/bin/python"), "-m", "scripts.agent_quality_worker"),
            source_sha256=budget.frozen.provenance.capture_source_sha256,
            deadline=budget.deadline,
            initial_sent=budget.byte_counts["ipc_sent"],
            initial_received=budget.byte_counts["ipc_received"],
            account_wire=budget.account_capture_wire,
        )
        self.opened = False

    async def open(self) -> None:
        self.budget.guard()
        if self.opened:
            raise EvaluationFailure("baseline_capture_already_open")
        self.opened = True
        await self.worker.__aenter__()
        succeeded = False
        try:
            actor = self.budget.frozen.bindings.actor_sha256
            result = await self.worker.exchange(
                "preflight",
                {
                    "action": "open",
                    "protocol": "baseline-v1",
                    "limit_profile": self.budget.approval.limit_profile,
                    "execution_approved": True,
                    "approval_sha256": self.run.canonical_sha256,
                    "frozen_sha256": self.budget.approval.frozen_sha256,
                    "actor_sha256": actor,
                    "environment": dict(self.environment),
                },
                request_sha256=self.budget.approval.frozen_sha256,
                evidence_sha256=actor,
                admit=self.budget.admit_capture,
            )
            if result != {"actor_sha256": actor}:
                raise EvaluationFailure("baseline_capture_user_mismatch")
            succeeded = True
        finally:
            if not succeeded:
                await self.worker.close()

    async def capture(self, case_id: CaseId) -> tuple[CaseReceipt, TransientAnswer | None]:
        if not self.opened or self.worker.closed:
            raise EvaluationFailure("baseline_capture_not_open")
        frozen = self.budget.frozen
        template = next(row for row in load_fixture().cases if row.case_id == case_id)
        oracle = next(row for row in frozen.oracles.cases if row.case_id == case_id)
        selected = next(
            (row for row in frozen.bindings.filters if row.alias == template.filter_alias), None
        )
        aliases = template.item_aliases if selected is None else selected.pool_aliases
        items: list[JsonValue] = [
            row.model_dump(mode="json")
            for alias in aliases
            for row in frozen.bindings.items
            if row.alias == alias
        ]
        await self.budget.admit_agent(case_id)
        payload: dict[str, JsonValue] = {
            "action": "capture",
            "request": frozen.request_document(case_id),
            "items": items,
            "pool_sha256": None if selected is None else selected.pool_sha256,
            "expected_status": oracle.expected_http_status,
            "wrong_audience": template.kind == "wrong_audience",
        }
        data = await self.worker.exchange(
            case_id,
            payload,
            request_sha256=self.budget.agents[case_id].request_sha256,
            evidence_sha256=self.budget.agents[case_id].evidence_sha256,
            admit=self.budget.admit_capture,
        )
        captured = parse_document(CaptureReply, json.dumps(data).encode())
        denied = oracle.expected_http_status != 200
        if (
            captured.http_status != oracle.expected_http_status
            or denied != (captured.receipt is None)
            or denied != (captured.answer is None)
            or (denied and captured.evidence)
        ):
            raise EvaluationFailure("baseline_capture_outcome_mismatch")
        wire = captured.receipt
        receipt = CaseReceipt(
            case_id=case_id,
            modality="live_a2a",
            outcome="denied" if wire is None else wire.outcome,
            request_sha256=self.budget.agents[case_id].request_sha256,
            evidence_sha256=self.budget.agents[case_id].evidence_sha256,
            answer_sha256=(
                None
                if captured.answer is None
                else hashlib.sha256(captured.answer.encode()).hexdigest()
            ),
            http_status=captured.http_status,
            tool_calls=0 if wire is None else wire.tool_calls,
            evidence_items=0 if wire is None else wire.items,
            validated=False if wire is None else wire.validated,
            generation_calls=0 if wire is None else wire.generation_calls,
            usage_observed_calls=0 if wire is None else wire.usage_observed_calls,
            input_tokens=0 if wire is None else wire.input_tokens,
            output_tokens=0 if wire is None else wire.output_tokens,
            elapsed_ms=captured.elapsed_ms,
            user_preserved=False if wire is None else wire.user_preserved,
            no_model_work_verified=False,
        )
        await self.budget.observe_agent(receipt)
        answer = (
            None
            if captured.answer is None
            else TransientAnswer(
                case_id=case_id,
                answer=captured.answer,
                evidence=captured.evidence,
                receipt=receipt,
            )
        )
        if answer is not None:
            answer.verify_frozen(self.budget)
        return receipt, answer

    async def close(self, *, graceful: bool) -> None:
        try:
            if graceful and self.opened and not self.worker.closed:
                actor = self.budget.frozen.bindings.actor_sha256
                result = await self.worker.exchange(
                    "preflight",
                    {"action": "close"},
                    request_sha256=self.budget.approval.frozen_sha256,
                    evidence_sha256=actor,
                    admit=self.budget.admit_capture,
                )
                if result != {"closed": True}:
                    raise EvaluationFailure("baseline_capture_cleanup_failed")
        finally:
            await self.worker.close()
