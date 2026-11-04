import asyncio
import hashlib
import math
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, Literal, Self

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from agent_evaluation.baseline_inputs import (
    BaselineResult,
    CaseId,
    CaseReceipt,
    FrozenBaseline,
    ScoringProgress,
)
from agent_evaluation.baseline_ipc import CaptureAdmission
from agent_evaluation.baseline_provenance import Digest, document_digest
from agent_evaluation.budget import (
    Attempt,
    Budget,
    BudgetReceipt,
    Limits,
    Prices,
)
from agent_evaluation.inputs import ROOT, StrictModel, json_document
from agent_evaluation.policy import EvaluationFailure

if TYPE_CHECKING:
    from agent_evaluation.baseline_publication import (
        BaselinePublicationReceipt,
        BaselinePublicationState,
    )

Money = Annotated[StrictStr, Field(pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,24})?$", max_length=64)]
Operation = Literal[
    "evidence",
    "metadata_before",
    "metadata_after",
    "auth_http",
    "sign_ins",
    "task_reads",
    "publication_reads",
    "publication_creates",
]
OP_LIMITS: Final[dict[Operation, int]] = {
    "evidence": 160,
    "metadata_before": 60,
    "metadata_after": 60,
    "auth_http": 40,
    "sign_ins": 4,
    "task_reads": 12,
    "publication_reads": 180,
    "publication_creates": 6,
}
LimitProfile = Literal[
    "baseline-12x8-v1",
    "baseline-12x8-v2",
    "baseline-12x8-v3",
    "baseline-12x8-v4",
    "baseline-12x8-v5",
    "baseline-12x8-v6",
]


def operation_limits(profile: LimitProfile) -> dict[Operation, int]:
    return {
        **OP_LIMITS,
        **(
            {
                "metadata_before": 180
                if profile in ("baseline-12x8-v5", "baseline-12x8-v6")
                else 120,
                "sign_ins": {
                    "baseline-12x8-v2": 6,
                    "baseline-12x8-v3": 7,
                    "baseline-12x8-v4": 9,
                    "baseline-12x8-v5": 9,
                    "baseline-12x8-v6": 9,
                }[profile],
            }
            if profile != "baseline-12x8-v1"
            else {}
        ),
    }


ByteSurface = Literal["evidence", "ipc_sent", "ipc_received"]
BYTE_LIMITS: Final[dict[ByteSurface, int]] = {
    "evidence": 10 * 1024 * 1024,
    "ipc_sent": 8 * 1024 * 1024,
    "ipc_received": 8 * 1024 * 1024,
}


class OperationCounts(StrictModel):
    evidence: StrictInt = Field(ge=0, le=160)
    metadata_before: StrictInt = Field(ge=0, le=180)
    metadata_after: StrictInt = Field(ge=0, le=60)
    auth_http: StrictInt = Field(ge=0, le=40)
    sign_ins: StrictInt = Field(ge=0, le=9)
    task_reads: StrictInt = Field(ge=0, le=12)
    publication_reads: StrictInt = Field(ge=0, le=180)
    publication_creates: StrictInt = Field(ge=0, le=6)

    @classmethod
    def empty(cls) -> OperationCounts:
        return cls.model_validate({name: 0 for name in OP_LIMITS})


class BaselineApproval(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    protocol: Literal["baseline-v1"]
    limit_profile: LimitProfile
    execution_approved: StrictBool
    frozen_sha256: Digest
    readiness_receipt_sha256: Digest
    approved_at: datetime
    expires_at: datetime
    prices_verified_at: datetime
    input_per_million_usd: Money
    output_per_million_usd: Money
    embedding_input_per_million_usd: Money
    embedding_token_bound: StrictInt = Field(ge=8192, le=8192)
    maximum_usd: Literal["10", "100"]
    preparation_counts: OperationCounts
    preparation_evidence_bytes: StrictInt = Field(ge=0, le=10 * 1024 * 1024)
    preparation_ipc_sent_bytes: StrictInt = Field(ge=0, le=8 * 1024 * 1024)
    preparation_ipc_received_bytes: StrictInt = Field(ge=0, le=8 * 1024 * 1024)
    preparation_model_calls: StrictInt = Field(ge=0, le=0)
    prior_usage_sha256: Digest | None = Field(default=None, exclude_if=lambda value: value is None)
    prior_model_exposure_usd: Money = Field(default="0", exclude_if=lambda value: value == "0")

    @model_validator(mode="after")
    def profile_counts(self) -> Self:
        if Decimal(self.prior_model_exposure_usd) > Decimal(self.maximum_usd) or (
            Decimal(self.prior_model_exposure_usd) > 0 and self.prior_usage_sha256 is None
        ):
            raise ValueError("baseline_prior_exposure_invalid")
        if self.maximum_usd != ("100" if self.limit_profile == "baseline-12x8-v6" else "10"):
            raise ValueError("baseline_profile_cost_limit")
        if any(
            getattr(self.preparation_counts, name) > limit
            for name, limit in operation_limits(self.limit_profile).items()
        ):
            raise ValueError("baseline_preparation_profile_limit")
        return self

    @field_validator("approved_at", "expires_at", "prices_verified_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.utcoffset() != UTC.utcoffset(None):
            raise ValueError("baseline_utc_required")
        return value

    def validate_execution(self, now: datetime, frozen: FrozenBaseline) -> Prices:
        frozen.provenance.verify_current(frozen.bindings.accepted_runtime)
        if (
            not self.execution_approved
            or now.utcoffset() != UTC.utcoffset(None)
            or not self.approved_at <= now < self.expires_at
            or not timedelta(0) < self.expires_at - self.approved_at <= timedelta(hours=3)
            or not timedelta(0) <= now - self.prices_verified_at <= timedelta(days=1)
            or self.frozen_sha256 != document_digest(frozen.model_dump(mode="json", by_alias=True))
            or Decimal(self.embedding_input_per_million_usd) <= 0
            or any(
                getattr(self.preparation_counts, name) != 0
                for name in (
                    "metadata_after",
                    "task_reads",
                    "publication_reads",
                    "publication_creates",
                )
            )
        ):
            raise EvaluationFailure("stale_or_unapproved_baseline")
        return Prices(Decimal(self.input_per_million_usd), Decimal(self.output_per_million_usd))


class AgentExposure(StrictModel):
    case_id: CaseId
    request_sha256: Digest
    evidence_sha256: Digest
    reserved_chat_usd: Money
    reserved_embedding_usd: Money
    observed_chat_usd: Money | None
    embedding_unused_verified: StrictBool
    receipt: CaseReceipt | None


class BaselineBudgetReceipt(StrictModel):
    protocol: Literal["baseline-v1"]
    limit_profile: LimitProfile = "baseline-12x8-v1"
    approval_sha256: Digest
    frozen_sha256: Digest
    original_expires_at: datetime
    halted: StrictBool
    counts: OperationCounts
    evidence_response_bytes: StrictInt = Field(ge=0, le=10 * 1024 * 1024)
    ipc_sent_bytes: StrictInt = Field(ge=0, le=8 * 1024 * 1024)
    ipc_received_bytes: StrictInt = Field(ge=0, le=8 * 1024 * 1024)
    agents: tuple[AgentExposure, ...]
    judge: BudgetReceipt
    embedding_dispatches_reserved: StrictInt = Field(ge=0, le=768)
    operator_embedding_usd_reserved: Money
    combined_exposure_usd: Money
    prior_model_exposure_usd: Money = Field(default="0", exclude_if=lambda value: value == "0")

    @model_validator(mode="after")
    def bounded_judge_metadata(self) -> Self:
        if any(
            getattr(self.counts, name) > limit
            for name, limit in operation_limits(self.limit_profile).items()
        ):
            raise ValueError("baseline_checkpoint_profile_limit")
        try:
            amounts = tuple(
                Decimal(value)
                for value in (
                    self.judge.estimated_observed_usd,
                    self.judge.estimated_reserved_unknown_usd,
                    self.judge.estimated_total_exposure_usd,
                )
            )
        except InvalidOperation:
            raise ValueError("invalid_baseline_judge_amount") from None
        if (
            any(not value.is_finite() or value < 0 for value in amounts)
            or amounts[0] + amounts[1] != amounts[2]
            or not math.isfinite(self.judge.remaining_s)
            or not 0 <= self.judge.remaining_s <= 10800
            or not 0 <= self.judge.attempts <= 80
            or not 0 <= self.judge.usage_observed <= 80
            or not 0 <= self.judge.usage_unknown <= 80
            or self.judge.usage_observed + self.judge.usage_unknown != self.judge.attempts
            or self.judge.usage_complete != (self.judge.usage_unknown == 0)
            or not 0 <= self.judge.input_tokens_observed <= 80 * 400000
            or not 0 <= self.judge.output_tokens_observed <= 80 * 1024
            or Decimal(self.combined_exposure_usd)
            > (100 if self.limit_profile == "baseline-12x8-v6" else 10)
            or Decimal(self.combined_exposure_usd) < amounts[2]
            or Decimal(self.combined_exposure_usd) < Decimal(self.prior_model_exposure_usd)
            or not 0 <= self.judge.request_bytes <= 5 * 1024 * 1024
            or not 0
            <= self.judge.response_bytes_observed
            <= self.judge.response_bytes_exposure
            <= 5 * 1024 * 1024
        ):
            raise ValueError("invalid_baseline_judge_metadata")
        return self


class CombinedJudgeBudget(Budget):
    def __init__(
        self,
        prices: Prices,
        limits: Limits,
        *,
        external: Callable[[], Decimal],
        guard: Callable[[], None],
        admission: asyncio.Lock,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
        persist: Callable[[BudgetReceipt], Awaitable[None]],
        ready: Callable[[], Awaitable[None]],
    ) -> None:
        self.external, self.guard, self.admission = external, guard, admission
        super().__init__(prices, limits, clock=clock, sleep=sleep, persist=persist, ready=ready)

    def exposure(self) -> Decimal:
        return super().exposure() + self.external()

    async def admit(self, request_bytes: int) -> Attempt:
        async with self.admission:
            self.guard()
            return await super().admit(request_bytes)


class BaselineBudget:
    def __init__(
        self,
        approval: BaselineApproval,
        frozen: FrozenBaseline,
        *,
        persist: Callable[[BaselineBudgetReceipt], Awaitable[None]],
        ready: Callable[[], Awaitable[None]],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        prices = approval.validate_execution(now(), frozen)
        self.approval, self.frozen, self.persist = approval, frozen, persist
        self.now, self.clock = now, clock
        self.deadline = clock() + (approval.expires_at - now()).total_seconds()
        self.counts = {name: getattr(approval.preparation_counts, name) for name in OP_LIMITS}
        self.byte_counts: dict[ByteSurface, int] = {
            "evidence": approval.preparation_evidence_bytes,
            "ipc_sent": approval.preparation_ipc_sent_bytes,
            "ipc_received": approval.preparation_ipc_received_bytes,
        }
        self.agents: dict[CaseId, AgentExposure] = {}
        self.embedding_dispatches = 0
        self.operator_embedding_usd = Decimal(0)
        self.halted = False
        self.started = False
        self.admission = asyncio.Lock()
        self.prices = prices
        self.embedding_attempt_usd = (
            Decimal(approval.embedding_input_per_million_usd)
            * approval.embedding_token_bound
            / Decimal(1_000_000)
        )
        self.judge = CombinedJudgeBudget(
            prices,
            Limits(
                attempts=80,
                spacing_s=70,
                output_tokens=1024,
                request_bytes=64 * 1024,
                response_bytes=64 * 1024,
                total_request_bytes=5 * 1024 * 1024,
                total_response_bytes=5 * 1024 * 1024,
                deadline_s=self.deadline - clock(),
                usd=Decimal(approval.maximum_usd),
            ),
            external=self.external_exposure,
            guard=self.guard,
            admission=self.admission,
            clock=clock,
            sleep=sleep,
            persist=self.judge_checkpoint,
            ready=self.guarded_ready(ready),
        )
        self.judge.deadline = self.deadline

    def external_exposure(self) -> Decimal:
        return (
            Decimal(self.approval.prior_model_exposure_usd)
            + self.operator_embedding_usd
            + sum(
                (
                    Decimal(
                        row.reserved_chat_usd
                        if row.observed_chat_usd is None
                        else row.observed_chat_usd
                    )
                    + (
                        Decimal(0)
                        if row.embedding_unused_verified
                        else Decimal(row.reserved_embedding_usd)
                    )
                    for row in self.agents.values()
                ),
                Decimal(0),
            )
        )

    def guard(self, *, read_only_recovery: bool = False) -> None:
        self.approval.validate_execution(self.now(), self.frozen)
        if not self.started or ((self.halted or self.judge.halted) and not read_only_recovery):
            raise EvaluationFailure("baseline_admission_halted")
        if self.clock() >= self.deadline:
            raise EvaluationFailure("baseline_execution_deadline")

    async def start(self) -> None:
        if self.started:
            raise EvaluationFailure("baseline_execution_already_started")
        self.started = True
        await self.checkpoint()

    async def checkpoint(self) -> None:
        try:
            await self.persist(self.receipt())
        except OSError, EvaluationFailure:
            self.halted = self.judge.halted = True
            raise EvaluationFailure("baseline_checkpoint_failed") from None

    async def judge_checkpoint(self, receipt: BudgetReceipt) -> None:
        await self.checkpoint()

    def guarded_ready(self, ready: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        async def verify() -> None:
            self.guard()
            await ready()
            self.guard()

        return verify

    async def admit_agent(self, case_id: CaseId) -> None:
        async with self.admission:
            self.guard()
            if case_id in self.agents or len(self.agents) >= 12:
                raise EvaluationFailure("baseline_agent_slot_consumed")
            if case_id not in {case.case_id for case in self.frozen.oracles.cases}:
                raise EvaluationFailure("baseline_foreign_case")
            reserved_chat = self.prices.cost(262144, 4096)
            reserved_embedding = self.embedding_attempt_usd * 24
            self.check_extra_cost(reserved_chat + reserved_embedding, embedding_dispatches=24)
            self.agents[case_id] = AgentExposure(
                case_id=case_id,
                request_sha256=document_digest(self.frozen.request_document(case_id)),
                evidence_sha256=self.frozen.evidence_digest(case_id),
                reserved_chat_usd=format(reserved_chat, "f"),
                reserved_embedding_usd=format(reserved_embedding, "f"),
                observed_chat_usd=None,
                embedding_unused_verified=False,
                receipt=None,
            )
            self.embedding_dispatches += 24
            await self.checkpoint()
            self.guard()

    async def observe_agent(self, receipt: CaseReceipt) -> None:
        async with self.admission:
            self.guard()
            row = self.agents.get(receipt.case_id)
            if (
                row is None
                or row.receipt is not None
                or row.request_sha256 != receipt.request_sha256
                or row.evidence_sha256 != receipt.evidence_sha256
            ):
                raise EvaluationFailure("baseline_agent_receipt_mismatch")
            unknown_denial = receipt.outcome == "denied" and not receipt.no_model_work_verified
            observed = (
                None
                if unknown_denial
                else format(self.prices.cost(receipt.input_tokens, receipt.output_tokens), "f")
            )
            self.agents[receipt.case_id] = row.model_copy(
                update={
                    "observed_chat_usd": observed,
                    "embedding_unused_verified": receipt.outcome == "denied" and not unknown_denial,
                    "receipt": receipt,
                }
            )
            await self.checkpoint()

    def check_extra_cost(self, value: Decimal, *, embedding_dispatches: int = 0) -> None:
        if (
            not value.is_finite()
            or value < 0
            or self.embedding_dispatches + embedding_dispatches > 768
            or self.judge.exposure() + value > Decimal(self.approval.maximum_usd)
        ):
            raise EvaluationFailure("baseline_combined_reservation_limit")

    async def admit(
        self, operation: Operation, *, semantic_query: bool = False, recovery: bool = False
    ) -> None:
        async with self.admission:
            if operation not in OP_LIMITS:
                raise EvaluationFailure("baseline_operation_invalid")
            self.guard(read_only_recovery=recovery and operation == "publication_reads")
            if self.counts[operation] >= operation_limits(self.approval.limit_profile)[operation]:
                raise EvaluationFailure("baseline_operation_limit")
            if semantic_query and operation != "evidence":
                raise EvaluationFailure("baseline_invalid_embedding_reservation")
            if semantic_query:
                value = self.embedding_attempt_usd * 3
                self.check_extra_cost(value, embedding_dispatches=3)
                self.operator_embedding_usd += value
                self.embedding_dispatches += 3
            self.counts[operation] += 1
            await self.checkpoint()
            self.guard(read_only_recovery=recovery and operation == "publication_reads")

    async def admit_capture(self, event: CaptureAdmission) -> None:
        if event.operation == "evidence_bytes":
            async with self.admission:
                self.guard()
                self.consume("evidence", event.amount)
                await self.checkpoint()
                self.guard()
        elif event.operation == "semantic_evidence":
            await self.admit("evidence", semantic_query=True)
        else:
            await self.admit(event.operation)

    async def account_capture_wire(
        self, surface: Literal["ipc_sent", "ipc_received"], size: int
    ) -> None:
        async with self.admission:
            self.guard()
            self.consume(surface, size)
            await self.checkpoint()
            self.guard()

    def consume(self, surface: ByteSurface, size: int) -> None:
        if (
            surface not in BYTE_LIMITS
            or type(size) is not int
            or size < 0
            or self.byte_counts[surface] + size > BYTE_LIMITS[surface]
        ):
            self.halted = self.judge.halted = True
            raise EvaluationFailure("baseline_cumulative_byte_limit")
        self.byte_counts[surface] += size

    async def halt(self) -> None:
        self.halted = self.judge.halted = True
        await self.checkpoint()

    def receipt(self) -> BaselineBudgetReceipt:
        return BaselineBudgetReceipt(
            protocol="baseline-v1",
            limit_profile=self.approval.limit_profile,
            approval_sha256=document_digest(self.approval.model_dump(mode="json")),
            frozen_sha256=self.approval.frozen_sha256,
            original_expires_at=self.approval.expires_at,
            halted=self.halted or self.judge.halted,
            counts=OperationCounts.model_validate(self.counts),
            evidence_response_bytes=self.byte_counts["evidence"],
            ipc_sent_bytes=self.byte_counts["ipc_sent"],
            ipc_received_bytes=self.byte_counts["ipc_received"],
            agents=tuple(self.agents.values()),
            judge=self.judge.receipt(),
            embedding_dispatches_reserved=self.embedding_dispatches,
            operator_embedding_usd_reserved=format(self.operator_embedding_usd, "f"),
            combined_exposure_usd=format(self.judge.exposure(), "f"),
            prior_model_exposure_usd=self.approval.prior_model_exposure_usd,
        )


class BaselineRun:
    def __init__(
        self,
        path: Path,
        approval_bytes: bytes,
        approved_sha256: str,
        frozen: FrozenBaseline,
        *,
        registry: Path | None = None,
    ) -> None:
        from agent_evaluation.runner import Journal

        self.approval = self.parse_approval(approval_bytes, approved_sha256)
        self.approval.validate_execution(datetime.now(UTC), frozen)
        self.frozen = frozen
        self.canonical_sha256 = document_digest(self.approval.model_dump(mode="json"))
        self._journal = Journal(
            path,
            self.canonical_sha256,
            registry=ROOT / ".azure/agent-quality-baseline" if registry is None else registry,
        )
        self._journal.write("approval.json", self.approval.model_dump(mode="json"))

    @staticmethod
    def parse_approval(data: bytes, approved_sha256: str) -> BaselineApproval:
        if len(data) > 16 * 1024 or hashlib.sha256(data).hexdigest() != approved_sha256:
            raise EvaluationFailure("baseline_approval_fingerprint_mismatch")
        json_document(data)
        try:
            return BaselineApproval.model_validate_json(data)
        except ValueError:
            raise EvaluationFailure("invalid_baseline_approval") from None

    async def checkpoint(self, receipt: BaselineBudgetReceipt) -> None:
        receipt = self.validated_metadata(receipt)
        if (
            receipt.approval_sha256 != self.canonical_sha256
            or receipt.limit_profile != self.approval.limit_profile
            or receipt.prior_model_exposure_usd != self.approval.prior_model_exposure_usd
            or receipt.frozen_sha256 != self.approval.frozen_sha256
            or receipt.original_expires_at != self.approval.expires_at
        ):
            raise EvaluationFailure("baseline_checkpoint_binding_mismatch")
        await self._journal.persist("budget.json", receipt.model_dump(mode="json"))

    def claim_scoring(self) -> None:
        from agent_evaluation.runner import sync_directory

        try:
            descriptor = os.open(
                self._journal.path / "scoring.claim",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
        except FileExistsError:
            raise EvaluationFailure("baseline_scoring_already_claimed") from None
        with os.fdopen(descriptor, "w") as stream:
            stream.write(self.canonical_sha256)
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(self._journal.path)

    async def scoring_checkpoint(self, progress: ScoringProgress) -> None:
        progress = self.validated_metadata(progress)
        if (
            progress.approval_sha256 != self.canonical_sha256
            or progress.frozen_sha256 != self.approval.frozen_sha256
        ):
            raise EvaluationFailure("baseline_checkpoint_binding_mismatch")
        await self._journal.persist("partial-results.json", progress.model_dump(mode="json"))

    async def save_results(self, result: BaselineResult) -> None:
        result = self.validated_metadata(result)
        result.verify_frozen(self.frozen)
        if result.frozen_sha256 != self.approval.frozen_sha256:
            raise EvaluationFailure("baseline_checkpoint_binding_mismatch")
        await self._journal.persist("results.json", result.model_dump(mode="json"))

    def load_results(self) -> BaselineResult:
        from agent_evaluation.runner import read_file

        data = read_file(self._journal.path / "results.json", 256 * 1024)
        json_document(data)
        try:
            result = BaselineResult.model_validate_json(data)
        except ValueError:
            raise EvaluationFailure("invalid_baseline_results") from None
        result.verify_frozen(self.frozen)
        if result.frozen_sha256 != self.approval.frozen_sha256:
            raise EvaluationFailure("baseline_checkpoint_binding_mismatch")
        return result

    def load_scoring_progress(self) -> ScoringProgress:
        from agent_evaluation.runner import read_file

        data = read_file(self._journal.path / "partial-results.json", 256 * 1024)
        json_document(data)
        try:
            result = ScoringProgress.model_validate_json(data)
        except ValueError:
            raise EvaluationFailure("invalid_baseline_scoring_progress") from None
        if (
            result.approval_sha256 != self.canonical_sha256
            or result.frozen_sha256 != self.approval.frozen_sha256
        ):
            raise EvaluationFailure("baseline_checkpoint_binding_mismatch")
        return result

    def load_publication_state(self) -> BaselinePublicationState | None:
        from agent_evaluation.baseline_publication import BaselinePublicationState
        from agent_evaluation.runner import read_file

        path = self._journal.path / "publication-state.json"
        if path.is_symlink():
            raise EvaluationFailure("baseline_publication_state_mismatch")
        if not path.exists():
            return None
        data = read_file(path, 256 * 1024)
        json_document(data)
        try:
            state = BaselinePublicationState.model_validate_json(data)
        except ValueError:
            raise EvaluationFailure("invalid_baseline_publication_state") from None
        self.verify_publication_binding(
            state.approval_sha256, state.frozen_sha256, state.results_sha256
        )
        return state

    def verify_publication_binding(self, approval: str, frozen: str, results: str) -> None:
        if (
            approval != self.canonical_sha256
            or frozen != self.approval.frozen_sha256
            or results != document_digest(self.load_results().model_dump(mode="json"))
        ):
            raise EvaluationFailure("baseline_checkpoint_binding_mismatch")

    async def publication_checkpoint(self, state: BaselinePublicationState) -> None:
        state = self.validated_metadata(state)
        self.verify_publication_binding(
            state.approval_sha256, state.frozen_sha256, state.results_sha256
        )
        await self._journal.persist("publication-state.json", state.model_dump(mode="json"))

    async def publication_receipt(self, receipt: BaselinePublicationReceipt) -> None:
        receipt = self.validated_metadata(receipt)
        if receipt.approval_sha256 != self.canonical_sha256:
            raise EvaluationFailure("baseline_checkpoint_binding_mismatch")
        await self._journal.persist("publication.json", receipt.model_dump(mode="json"))

    @staticmethod
    def validated_metadata[Model: StrictModel](value: Model) -> Model:
        try:
            return type(value).model_validate_json(value.model_dump_json(warnings=False))
        except ValueError:
            raise EvaluationFailure("invalid_baseline_persisted_metadata") from None

    @classmethod
    def read_budget(
        cls,
        path: Path,
        approval_bytes: bytes,
        approved_sha256: str,
        *,
        registry: Path | None = None,
    ) -> BaselineBudgetReceipt:
        from agent_evaluation.runner import Journal, read_file

        approval = cls.parse_approval(approval_bytes, approved_sha256)
        canonical = document_digest(approval.model_dump(mode="json"))
        journal = Journal.reopen(
            path,
            canonical,
            registry=ROOT / ".azure/agent-quality-baseline" if registry is None else registry,
        )
        data = read_file(journal.path / "budget.json", 256 * 1024)
        json_document(data)
        try:
            result = BaselineBudgetReceipt.model_validate_json(data)
        except ValueError:
            raise EvaluationFailure("invalid_baseline_checkpoint") from None
        if (
            result.approval_sha256 != canonical
            or result.limit_profile != approval.limit_profile
            or result.prior_model_exposure_usd != approval.prior_model_exposure_usd
            or result.frozen_sha256 != approval.frozen_sha256
            or result.original_expires_at != approval.expires_at
        ):
            raise EvaluationFailure("baseline_checkpoint_binding_mismatch")
        return result
