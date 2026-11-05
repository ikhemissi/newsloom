import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from test_baseline_inputs import frozen_data, result_data
from test_budget import Clock
from test_runner import CLOCK_MARGIN

from agent_evaluation.baseline_budget import (
    BYTE_LIMITS,
    OP_LIMITS,
    BaselineApproval,
    BaselineBudget,
    BaselineBudgetReceipt,
    BaselineRun,
    Operation,
    OperationCounts,
    operation_limits,
)
from agent_evaluation.baseline_inputs import CaseReceipt, FrozenBaseline, parse_document
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.budget import Usage
from agent_evaluation.policy import EvaluationFailure


def frozen() -> FrozenBaseline:
    return parse_document(FrozenBaseline, json.dumps(frozen_data()).encode())


def approval(value: FrozenBaseline, now: datetime | None = None) -> BaselineApproval:
    start = datetime.now(UTC) if now is None else now
    return BaselineApproval(
        schema_version=1,
        protocol="baseline-v1",
        limit_profile="baseline-12x8-v1",
        execution_approved=True,
        frozen_sha256=document_digest(value.model_dump(mode="json", by_alias=True)),
        readiness_receipt_sha256="1" * 64,
        approved_at=start - timedelta(seconds=1),
        expires_at=start + timedelta(seconds=10799),
        prices_verified_at=start - CLOCK_MARGIN,
        input_per_million_usd="0.825",
        output_per_million_usd="4.95",
        embedding_input_per_million_usd="0.022",
        embedding_token_bound=8192,
        maximum_usd="10",
        preparation_counts=OperationCounts.empty(),
        preparation_evidence_bytes=0,
        preparation_ipc_sent_bytes=0,
        preparation_ipc_received_bytes=0,
        preparation_model_calls=0,
    )


async def ready() -> None:
    return None


@pytest.mark.parametrize(
    "profile,reads,sign_ins",
    [
        ("baseline-12x8-v1", 60, 4),
        ("baseline-12x8-v2", 120, 6),
        ("baseline-12x8-v3", 120, 7),
        ("baseline-12x8-v4", 120, 9),
        ("baseline-12x8-v5", 180, 9),
        ("baseline-12x8-v6", 180, 9),
    ],
)
async def test_versioned_limits_preserve_prior_counts_and_exact_boundaries(
    profile: str,
    reads: int,
    sign_ins: int,
) -> None:
    value = frozen()
    data = approval(value).model_dump(mode="json")
    data["limit_profile"] = profile
    data["maximum_usd"] = "100" if profile == "baseline-12x8-v6" else "10"
    counts = data["preparation_counts"]
    assert isinstance(counts, dict)
    counts.update(metadata_before=47, auth_http=2, sign_ins=1)
    approved = BaselineApproval.model_validate_json(json.dumps(data))
    budget = BaselineBudget(approved, value, persist=Recorder(), ready=ready)
    await budget.start()
    assert budget.counts["metadata_before"] == 47
    assert budget.counts["auth_http"] == 2 and budget.counts["sign_ins"] == 1
    boundaries: tuple[tuple[Operation, int], ...] = (
        ("metadata_before", reads),
        ("sign_ins", sign_ins),
    )
    for operation, maximum in boundaries:
        while budget.counts[operation] < maximum:
            await budget.admit(operation)
        with pytest.raises(EvaluationFailure, match="baseline_operation_limit"):
            await budget.admit(operation)
    receipt = budget.receipt()
    assert receipt.limit_profile == profile
    BaselineBudgetReceipt.model_validate_json(receipt.model_dump_json())
    unchanged: tuple[Operation, ...] = (
        "metadata_after",
        "auth_http",
        "evidence",
        "publication_reads",
    )
    for operation in unchanged:
        assert OP_LIMITS[operation] == operation_limits(approved.limit_profile)[operation]


def test_v1_cannot_inherit_v2_preparation_or_checkpoint_limits() -> None:
    data = approval(frozen()).model_dump(mode="json")
    counts = data["preparation_counts"]
    assert isinstance(counts, dict)
    counts["metadata_before"] = 61
    with pytest.raises(ValueError, match="baseline_preparation_profile_limit"):
        BaselineApproval.model_validate_json(json.dumps(data))
    data["limit_profile"] = "baseline-12x8-v2"
    BaselineApproval.model_validate_json(json.dumps(data))


async def test_usd100_is_explicit_v6_only_and_never_extends_other_limits() -> None:
    value = frozen()
    data = approval(value).model_dump(mode="json")
    data["maximum_usd"] = "100"
    with pytest.raises(ValueError, match="baseline_profile_cost_limit"):
        BaselineApproval.model_validate_json(json.dumps(data))
    data["limit_profile"] = "baseline-12x8-v6"
    approved = BaselineApproval.model_validate_json(json.dumps(data))
    budget = BaselineBudget(approved, value, persist=Recorder(), ready=ready)
    await budget.start()
    budget.check_extra_cost(Decimal("100"))
    with pytest.raises(EvaluationFailure, match="baseline_combined_reservation_limit"):
        budget.check_extra_cost(Decimal("100.0000001"))
    assert budget.judge.limits.attempts == 80
    assert budget.receipt().original_expires_at == approved.expires_at


class Recorder:
    def __init__(self) -> None:
        self.states: list[BaselineBudgetReceipt] = []

    async def __call__(self, value: BaselineBudgetReceipt) -> None:
        self.states.append(value)


def case_receipt(
    value: FrozenBaseline, case: str = "b01", *, denial_proven: bool = False
) -> CaseReceipt:
    data = result_data()
    cases = data["cases"]
    assert isinstance(cases, list)
    row = next(item for item in cases if item["case_id"] == case)
    result = CaseReceipt.model_validate_json(json.dumps(row))
    return result.model_copy(
        update={
            "request_sha256": document_digest(value.request_document(result.case_id)),
            "evidence_sha256": value.evidence_digest(result.case_id),
            "no_model_work_verified": denial_proven,
        }
    )


async def test_agent_intent_is_persisted_before_dispatch_and_never_replayed() -> None:
    value = frozen()
    record = Recorder()
    budget = BaselineBudget(approval(value), value, persist=record, ready=ready)
    await budget.start()
    await budget.admit_agent("b01")
    row = record.states[-1].agents[0]
    assert row.receipt is None and row.observed_chat_usd is None
    assert Decimal(row.reserved_chat_usd) > 0 and Decimal(row.reserved_embedding_usd) > 0
    assert budget.receipt().embedding_dispatches_reserved == 24
    with pytest.raises(EvaluationFailure, match="baseline_agent_slot_consumed"):
        await budget.admit_agent("b01")
    assert len(budget.receipt().agents) == 1
    before = Decimal(budget.receipt().combined_exposure_usd)
    await budget.observe_agent(case_receipt(value))
    after = budget.receipt()
    assert Decimal(after.combined_exposure_usd) < before
    assert Decimal(after.agents[0].reserved_embedding_usd) > 0
    assert not after.agents[0].embedding_unused_verified
    with pytest.raises(EvaluationFailure, match="baseline_agent_receipt_mismatch"):
        await budget.observe_agent(case_receipt(value))


@pytest.mark.parametrize("proven", [False, True])
async def test_denial_does_not_make_unknown_model_exposure_free(proven: bool) -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    await budget.admit_agent("b11")
    before = Decimal(budget.receipt().combined_exposure_usd)
    await budget.observe_agent(case_receipt(value, "b11", denial_proven=proven))
    after = Decimal(budget.receipt().combined_exposure_usd)
    assert after == (Decimal(0) if proven else before)


async def test_combined_judge_and_agent_exposure_share_the_same_ceiling() -> None:
    value = frozen()
    record = Recorder()
    budget = BaselineBudget(approval(value), value, persist=record, ready=ready)
    await budget.start()
    budget.operator_embedding_usd = Decimal("9.7")
    with pytest.raises(EvaluationFailure, match="judge_cost_reservation_limit"):
        await budget.judge.admit(100)
    assert budget.judge.receipt().attempts == 0
    budget.operator_embedding_usd = Decimal(0)
    budget.check_extra_cost(Decimal("10"))
    with pytest.raises(EvaluationFailure, match="baseline_combined_reservation_limit"):
        budget.check_extra_cost(Decimal("10.00000000000000000001"))
    await budget.admit_agent("b01")
    await budget.judge.admit(100)
    state = record.states[-1]
    assert state.judge.usage_unknown == 1
    assert Decimal(state.combined_exposure_usd) > Decimal(state.judge.estimated_total_exposure_usd)
    assert state.original_expires_at == budget.approval.expires_at


@pytest.mark.parametrize("operation", tuple(OP_LIMITS))
async def test_operation_limit_is_exact_and_one_over_never_dispatches(operation: str) -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    counts = budget.approval.preparation_counts.model_dump()
    assert operation in OP_LIMITS
    for key in budget.counts:
        if key == operation:
            budget.counts[key] = OP_LIMITS[key] - 1
            await budget.admit(key)
            assert budget.counts[key] == OP_LIMITS[key]
            with pytest.raises(EvaluationFailure, match="baseline_operation_limit"):
                await budget.admit(key)
    assert counts == OperationCounts.empty().model_dump()


@pytest.mark.parametrize("surface", tuple(BYTE_LIMITS))
async def test_byte_surface_exact_boundary_and_halt(surface: str) -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    for key in budget.byte_counts:
        if key == surface:
            budget.consume(key, BYTE_LIMITS[key])
            with pytest.raises(EvaluationFailure, match="baseline_cumulative_byte_limit"):
                budget.consume(key, 1)
    assert budget.halted and budget.judge.halted


async def test_query_embedding_reserves_all_three_transport_attempts() -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    await budget.admit("evidence", semantic_query=True)
    state = budget.receipt()
    assert state.embedding_dispatches_reserved == 3
    assert Decimal(state.operator_embedding_usd_reserved) == budget.embedding_attempt_usd * 3
    assert Decimal(state.combined_exposure_usd) == Decimal(state.operator_embedding_usd_reserved)


async def test_original_deadline_and_failure_state_cannot_be_reset() -> None:
    value = frozen()
    clock = Clock()
    start = datetime.now(UTC)
    budget = BaselineBudget(
        approval(value, start),
        value,
        persist=Recorder(),
        ready=ready,
        clock=clock,
        sleep=clock.sleep,
        now=lambda: start + timedelta(seconds=clock.now),
    )
    await budget.start()
    await budget.admit_agent("b01")
    await budget.halt()
    with pytest.raises(EvaluationFailure, match="baseline_admission_halted"):
        await budget.admit_agent("b02")
    await budget.admit("publication_reads", recovery=True)
    assert budget.receipt().counts.publication_reads == 1
    clock.now = 10800
    with pytest.raises(EvaluationFailure, match="stale_or_unapproved_baseline"):
        await budget.admit("publication_reads", recovery=True)
    assert budget.receipt().agents[0].observed_chat_usd is None
    assert budget.deadline == 10799


async def test_judge_failure_halts_new_agent_work() -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    budget.judge.halted = True
    with pytest.raises(EvaluationFailure, match="baseline_admission_halted"):
        await budget.admit_agent("b01")


async def test_approval_is_once_only_even_when_json_whitespace_changes(tmp_path: Path) -> None:
    value = frozen()
    approved = approval(value)
    data = approved.model_dump_json().encode()
    registry = tmp_path / "registry"
    run = BaselineRun(
        tmp_path / "run", data, hashlib.sha256(data).hexdigest(), value, registry=registry
    )
    budget = BaselineBudget(approved, value, persist=run.checkpoint, ready=ready)
    await budget.start()
    await budget.admit_agent("b01")
    alternate = json.dumps(approved.model_dump(mode="json"), indent=2).encode()
    with pytest.raises(FileExistsError):
        BaselineRun(
            tmp_path / "replayed",
            alternate,
            hashlib.sha256(alternate).hexdigest(),
            value,
            registry=registry,
        )
    recovered = BaselineRun.read_budget(
        tmp_path / "run", data, hashlib.sha256(data).hexdigest(), registry=registry
    )
    assert recovered.agents[0].observed_chat_usd is None
    assert recovered.original_expires_at == approved.expires_at
    assert not (tmp_path / "replayed").exists()
    encoded = recovered.model_dump_json()
    assert all(f'"{name}":' not in encoded for name in ("answer", "summary", "question", "reason"))


async def test_checkpoint_failure_never_admits_work() -> None:
    value = frozen()

    async def fail(receipt: BaselineBudgetReceipt) -> None:
        raise OSError("PRIVATE_ERROR_CANARY")

    budget = BaselineBudget(approval(value), value, persist=fail, ready=ready)
    with pytest.raises(EvaluationFailure, match="baseline_checkpoint_failed") as caught:
        await budget.start()
    assert "CANARY" not in str(caught.value)
    assert budget.halted and budget.judge.halted


async def test_observed_judge_usage_does_not_release_unobserved_embeddings() -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    await budget.admit_agent("b01")
    row = await budget.judge.admit(100)
    external = budget.external_exposure()
    budget.judge.observe(row, Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    assert budget.external_exposure() == external
    assert budget.judge.exposure() > external


async def test_preparation_read_auth_and_byte_counts_are_not_reset() -> None:
    value = frozen()
    approved = approval(value)
    previous = approved.preparation_counts.model_copy(
        update={
            "evidence": 20,
            "auth_http": 9,
            "sign_ins": 2,
            "metadata_before": 41,
        }
    )
    approved = approved.model_copy(
        update={
            "preparation_counts": previous,
            "preparation_evidence_bytes": 1000,
            "preparation_ipc_sent_bytes": 2000,
            "preparation_ipc_received_bytes": 3000,
        }
    )
    budget = BaselineBudget(approved, value, persist=Recorder(), ready=ready)
    await budget.start()
    state = budget.receipt()
    assert state.counts == previous
    assert state.evidence_response_bytes == 1000
    assert state.ipc_sent_bytes == 2000 and state.ipc_received_bytes == 3000
    await budget.admit("evidence")
    assert budget.receipt().counts.evidence == 21


@pytest.mark.parametrize("change", ["unapproved", "expired", "prices", "frozen"])
def test_fresh_explicit_source_bound_approval_is_required(change: str) -> None:
    value = frozen()
    now = datetime.now(UTC)
    approved = approval(value, now)
    if change == "unapproved":
        approved = approved.model_copy(update={"execution_approved": False})
    elif change == "expired":
        approved = approved.model_copy(update={"expires_at": now - timedelta(seconds=1)})
    elif change == "prices":
        approved = approved.model_copy(update={"prices_verified_at": now - timedelta(days=2)})
    else:
        approved = approved.model_copy(update={"frozen_sha256": "0" * 64})
    with pytest.raises(EvaluationFailure, match="stale_or_unapproved_baseline"):
        approved.validate_execution(now, value)


async def test_eightieth_judge_attempt_is_the_last_admitted_slot() -> None:
    value = frozen()
    approved = approval(value).model_copy(
        update={
            "input_per_million_usd": "0.000001",
            "output_per_million_usd": "0.000001",
        }
    )
    budget = BaselineBudget(approved, value, persist=Recorder(), ready=ready)
    await budget.start()
    for _ in range(80):
        await budget.judge.admit(100)
    with pytest.raises(EvaluationFailure, match="judge_attempt_limit"):
        await budget.judge.admit(100)
    state = budget.receipt()
    assert state.judge.attempts == state.judge.usage_unknown == 80
    assert state.judge.response_bytes_exposure == 5 * 1024 * 1024
