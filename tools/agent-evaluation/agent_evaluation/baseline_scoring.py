import hashlib
import json
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue, StrictStr, model_validator

from agent_evaluation.baseline_budget import BaselineBudget, BaselineRun
from agent_evaluation.baseline_inputs import (
    CASE_IDS,
    SEMANTIC_CASES,
    Alias,
    BaselineResult,
    CaseId,
    CaseReceipt,
    ControlMeasurement,
    MetricScore,
    ScoringProgress,
    load_fixture,
)
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.inputs import StrictModel
from agent_evaluation.judge import Completion
from agent_evaluation.metric import measure
from agent_evaluation.policy import EvaluationFailure

SNAPSHOT_FIELDS = {
    "id",
    "title",
    "summary",
    "source",
    "category",
    "tags",
    "published_at",
    "url",
    "author",
    "date_origin",
    "publisher_categories",
}


class EvidenceSnapshot(StrictModel):
    alias: Alias
    item: dict[str, JsonValue] = Field(repr=False)

    @model_validator(mode="after")
    def public_snapshot(self) -> Self:
        if set(self.item) != SNAPSHOT_FIELDS:
            raise ValueError("invalid_baseline_evidence_fields")
        encoded = json.dumps(self.item, allow_nan=False).encode()
        if len(encoded) > 64 * 1024:
            raise ValueError("baseline_evidence_limit")
        for field in (
            "id",
            "title",
            "summary",
            "source",
            "category",
            "published_at",
            "url",
            "author",
        ):
            if not isinstance(self.item[field], str):
                raise ValueError("invalid_baseline_evidence_field")
        for field in ("tags", "publisher_categories"):
            value = self.item[field]
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError("invalid_baseline_evidence_field")
        if self.item["date_origin"] not in ("published", "updated", "retrieved"):
            raise ValueError("invalid_baseline_evidence_field")
        return self


class TransientAnswer(StrictModel):
    case_id: CaseId
    answer: StrictStr = Field(min_length=1, max_length=16384, repr=False)
    evidence: Annotated[tuple[EvidenceSnapshot, ...], Field(max_length=10, repr=False)]
    receipt: CaseReceipt

    def verify_frozen(self, budget: BaselineBudget) -> None:
        row = budget.agents.get(self.case_id)
        bindings = {item.alias: item for item in budget.frozen.bindings.items}
        oracle = next(case for case in budget.frozen.oracles.cases if case.case_id == self.case_id)
        if (
            row is None
            or row.receipt is None
            or row.receipt != self.receipt
            or self.receipt.case_id != self.case_id
            or self.receipt.outcome == "denied"
            or self.receipt.answer_sha256 != hashlib.sha256(self.answer.encode()).hexdigest()
            or len(self.answer.encode()) > 16384
            or len({item.alias for item in self.evidence}) != len(self.evidence)
            or {item.alias for item in self.evidence} != set(oracle.required_aliases)
        ):
            raise EvaluationFailure("baseline_transient_answer_mismatch")
        for snapshot in self.evidence:
            binding = bindings.get(snapshot.alias)
            item_id = snapshot.item["id"]
            if (
                binding is None
                or not binding.present
                or not isinstance(item_id, str)
                or str(binding.item_id) != item_id
                or document_digest(snapshot.item) != binding.fingerprint
            ):
                raise EvaluationFailure("baseline_transient_evidence_mismatch")
            UUID(item_id)

    def judge_evidence(self) -> str:
        return json.dumps(
            [snapshot.item for snapshot in self.evidence],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


class BaselineCompletion(Completion):
    async def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        value = await super().complete(prompt, schema)
        if not self.budget.receipt().usage_complete:
            self.budget.halted = True
            await self.budget.checkpoint()
            raise EvaluationFailure("baseline_judge_usage_incomplete")
        return value


class BaselineScorer:
    def __init__(
        self, budget: BaselineBudget, run: BaselineRun, completion: BaselineCompletion
    ) -> None:
        if completion.budget is not budget.judge or run.canonical_sha256 != document_digest(
            budget.approval.model_dump(mode="json")
        ):
            raise EvaluationFailure("baseline_scorer_binding_mismatch")
        run.claim_scoring()
        self.budget, self.run, self.completion = budget, run, completion
        self.fixture = load_fixture()
        self.progress = ScoringProgress(
            protocol="baseline-v1",
            approval_sha256=run.canonical_sha256,
            frozen_sha256=budget.approval.frozen_sha256,
            state="new",
            pending_control=None,
            pending_case=None,
            controls=(),
            scores=(),
        )
        self.attempted_cases: set[CaseId] = set()

    async def save(self) -> None:
        try:
            await self.run.scoring_checkpoint(self.progress)
        except OSError, EvaluationFailure:
            await self.budget.halt()
            raise EvaluationFailure("baseline_scoring_checkpoint_failed") from None

    async def measured(self, *, question: str, evidence: str, answer: str) -> tuple[float, int]:
        before = len(self.budget.judge.attempts)
        score, _reason = await measure(
            self.completion, question=question, evidence=evidence, answer=answer
        )
        after = self.budget.judge.receipt()
        if after.attempts <= before or not after.usage_complete or self.budget.judge.halted:
            raise EvaluationFailure("baseline_judge_usage_incomplete")
        self.budget.guard()
        return score, after.attempts - before

    async def calibrate(self) -> ScoringProgress:
        if self.progress.state != "new":
            raise EvaluationFailure("baseline_calibration_already_attempted")
        self.budget.guard()
        self.progress = self.progress.model_copy(update={"state": "calibrating"})
        for control in self.fixture.controls:
            self.progress = self.progress.model_copy(update={"pending_control": control.control_id})
            await self.save()
            passed = False
            try:
                score, attempts = await self.measured(
                    question=self.fixture.control_question,
                    evidence=self.fixture.control_evidence,
                    answer=control.answer,
                )
                passed = (
                    score >= self.fixture.thresholds.supported_min
                    if control.label == "supported"
                    else score <= self.fixture.thresholds.unsupported_max
                )
                row = ControlMeasurement(
                    control_id=control.control_id,
                    label=control.label,
                    score=score,
                    passed=passed,
                    judge_attempts=attempts,
                )
                self.progress = self.progress.model_copy(
                    update={
                        "controls": (*self.progress.controls, row),
                    }
                )
            finally:
                if not passed:
                    self.progress = self.progress.model_copy(update={"state": "failed"})
                    await self.budget.halt()
                await self.save()
            if not passed:
                raise EvaluationFailure("baseline_calibration_failed")
        self.progress = self.progress.model_copy(
            update={
                "state": "calibrated",
                "pending_control": None,
            }
        )
        await self.save()
        return self.progress

    async def score(self, captured: TransientAnswer) -> MetricScore:
        if self.progress.state not in ("calibrated", "scoring"):
            raise EvaluationFailure("baseline_calibration_required")
        if captured.case_id not in SEMANTIC_CASES or captured.case_id in self.attempted_cases:
            raise EvaluationFailure("baseline_case_scoring_not_admitted")
        captured.verify_frozen(self.budget)
        self.budget.guard()
        self.attempted_cases.add(captured.case_id)
        self.progress = self.progress.model_copy(
            update={
                "state": "scoring",
                "pending_case": captured.case_id,
            }
        )
        await self.save()
        succeeded = False
        try:
            request = self.budget.frozen.request_document(captured.case_id)
            question = request["question"]
            if not isinstance(question, str):
                raise EvaluationFailure("baseline_question_invalid")
            score, _attempts = await self.measured(
                question=question, evidence=captured.judge_evidence(), answer=captured.answer
            )
            result = MetricScore(case_id=captured.case_id, metric_id="faithfulness", score=score)
            self.progress = self.progress.model_copy(
                update={
                    "scores": (*self.progress.scores, result),
                    "pending_case": None,
                }
            )
            succeeded = True
            return result
        finally:
            if not succeeded:
                self.progress = self.progress.model_copy(update={"state": "failed"})
                await self.budget.halt()
            await self.save()

    def semantic_gate_passed(self) -> bool:
        rows = [value for value in self.progress.scores if value.metric_id == "faithfulness"]
        if {value.case_id for value in rows} != set(SEMANTIC_CASES):
            return False
        values = [Decimal(repr(value.score)) for value in rows]
        return all(
            value >= Decimal(str(self.fixture.thresholds.case_min)) for value in values
        ) and sum(values) / len(values) >= Decimal(str(self.fixture.thresholds.macro_min))

    async def record_contracts(self, case_id: CaseId, scores: tuple[MetricScore, ...]) -> None:
        if self.progress.state not in ("calibrated", "scoring"):
            raise EvaluationFailure("baseline_calibration_required")
        row = self.budget.agents.get(case_id)
        expected = (
            {"citation_validity", "contract_adherence"}
            if case_id in SEMANTIC_CASES
            else {"contract_adherence"}
        )
        if (
            row is None
            or row.receipt is None
            or any(value.case_id != case_id for value in scores)
            or {value.metric_id for value in scores} != expected
            or len(scores) != len(expected)
            or {(value.case_id, value.metric_id) for value in scores}
            & {(value.case_id, value.metric_id) for value in self.progress.scores}
        ):
            raise EvaluationFailure("baseline_contract_score_mismatch")
        self.progress = self.progress.model_copy(
            update={
                "state": "scoring",
                "scores": (*self.progress.scores, *scores),
            }
        )
        await self.save()

    async def finish(self) -> BaselineResult:
        if self.progress.state != "scoring":
            raise EvaluationFailure("baseline_scoring_incomplete")
        cases = []
        for case_id in CASE_IDS:
            row = self.budget.agents.get(case_id)
            if row is None or row.receipt is None:
                raise EvaluationFailure("baseline_scoring_incomplete")
            cases.append(row.receipt)
        result = BaselineResult(
            protocol="baseline-v1",
            provenance=self.budget.frozen.provenance,
            frozen_sha256=self.budget.approval.frozen_sha256,
            cases=tuple(cases),
            scores=self.progress.scores,
        )
        await self.run.save_results(result)
        self.progress = self.progress.model_copy(update={"state": "completed"})
        await self.save()
        return result
