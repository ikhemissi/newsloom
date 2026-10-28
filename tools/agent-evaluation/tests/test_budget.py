import asyncio
from dataclasses import replace
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agent_evaluation.budget import (
    CONTEXT_TOKEN_BOUND,
    Budget,
    BudgetReceipt,
    Limits,
    Prices,
    Usage,
)
from agent_evaluation.inputs import FIXTURE_SHA256, json_document, load_pilot, source_digest
from agent_evaluation.policy import EvaluationFailure

PRICES = Prices(Decimal("0.825"), Decimal("4.95"))


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


def test_frozen_two_case_inputs_and_source_digest() -> None:
    pilot = load_pilot()
    assert tuple(row.case_id for row in pilot.cases) == ("p01", "p02")
    assert len(FIXTURE_SHA256) == len(source_digest()) == 64


def test_json_duplicate_fields_are_not_last_value_wins() -> None:
    with pytest.raises(EvaluationFailure, match="duplicate_json_field"):
        json_document(b'{"score":0,"score":1}')


async def test_exact_cost_boundary_and_unknown_usage_remain_reserved() -> None:
    reservation = PRICES.cost(CONTEXT_TOKEN_BOUND, 1024)
    budget = Budget(PRICES, replace(Limits(), usd=reservation))
    await budget.admit(1)
    receipt = budget.receipt()
    assert receipt.usage_unknown == 1
    assert not receipt.usage_complete
    assert Decimal(receipt.estimated_reserved_unknown_usd) == reservation
    with pytest.raises(EvaluationFailure, match="judge_cost_reservation_limit"):
        await budget.admit(1)
    assert budget.receipt().attempts == 1


async def test_valid_observed_usage_releases_only_unused_reservation() -> None:
    reservation = PRICES.cost(CONTEXT_TOKEN_BOUND, 1024)
    observed = PRICES.cost(10, 5)
    budget = Budget(PRICES, replace(Limits(), usd=reservation + observed))
    first = await budget.admit(1)
    first.response_complete = True
    budget.observe(first, Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    await budget.admit(1)
    assert budget.exposure() == reservation + observed
    receipt = budget.receipt()
    assert receipt.usage_observed == receipt.usage_unknown == 1
    assert receipt.input_tokens_observed == 10
    with pytest.raises(EvaluationFailure, match="judge_cost_reservation_limit"):
        await budget.admit(1)


@pytest.mark.parametrize(
    ("limits", "category"),
    [
        (Limits(attempts=1), "judge_attempt_limit"),
        (Limits(total_request_bytes=1), "judge_total_request_byte_limit"),
        (Limits(total_response_bytes=65536), "judge_total_response_byte_limit"),
    ],
)
async def test_shared_exact_boundary_and_one_over(limits: Limits, category: str) -> None:
    budget = Budget(PRICES, limits)
    await budget.admit(1)
    with pytest.raises(EvaluationFailure, match=category):
        await budget.admit(1)
    assert budget.receipt().attempts == 1


async def test_per_request_and_response_byte_boundaries() -> None:
    budget = Budget(PRICES)
    with pytest.raises(EvaluationFailure, match="judge_request_byte_limit"):
        await budget.admit(65537)
    row = await budget.admit(65536)
    budget.consume(row, 65536)
    with pytest.raises(EvaluationFailure, match="judge_response_byte_limit"):
        budget.consume(row, 1)
    assert budget.receipt().response_bytes_observed == 65537
    assert budget.receipt().response_bytes_exposure == 65537


async def test_shared_spacing_and_deadline() -> None:
    clock = Clock()
    budget = Budget(PRICES, clock=clock, sleep=clock.sleep)
    await budget.pace()
    await budget.admit(1)
    await budget.pace()
    assert clock.waits == [70]
    clock.now = 1799
    budget.last_dispatch = 1799
    with pytest.raises(EvaluationFailure, match="evaluation_deadline"):
        await budget.pace()
    clock.now = 1800
    with pytest.raises(EvaluationFailure, match="evaluation_deadline"):
        await budget.admit(1)
    assert budget.receipt().attempts == 1


@pytest.mark.parametrize(
    "values",
    [
        b'{"prompt_tokens":true,"completion_tokens":1,"total_tokens":2}',
        b'{"prompt_tokens":1,"completion_tokens":false,"total_tokens":1}',
        b'{"prompt_tokens":1,"completion_tokens":1,"total_tokens":NaN}',
    ],
)
def test_usage_types_are_not_coerced(values: bytes) -> None:
    with pytest.raises(ValidationError):
        Usage.model_validate_json(values)


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "total"),
    [(0, 1, 1), (1, 0, 1), (400001, 1, 400002), (1, 1025, 1026), (1, 1, 3)],
)
async def test_invalid_usage_does_not_release_unknown_reservation(
    input_tokens: int, output_tokens: int, total: int
) -> None:
    budget = Budget(PRICES)
    row = await budget.admit(1)
    with pytest.raises(EvaluationFailure, match="invalid_judge_usage"):
        budget.observe(
            row,
            Usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=total,
            ),
        )
    assert budget.receipt().usage_unknown == 1


async def test_persistence_happens_before_dispatch_and_cancellation_does_not_refund() -> None:
    receipts: list[BudgetReceipt] = []

    async def persist(receipt: BudgetReceipt) -> None:
        receipts.append(receipt)
        raise asyncio.CancelledError

    budget = Budget(PRICES, persist=persist)
    with pytest.raises(asyncio.CancelledError):
        await budget.admit(1)
    assert receipts[0].usage_unknown == 1
    assert budget.receipt().attempts == budget.receipt().usage_unknown == 1


async def test_default_twelve_attempt_boundary_is_shared_across_calls() -> None:
    budget = Budget(PRICES)
    for _ in range(12):
        row = await budget.admit(1)
        row.response_complete = True
        budget.observe(row, Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2))
    with pytest.raises(EvaluationFailure, match="judge_attempt_limit"):
        await budget.admit(1)
    assert budget.receipt().attempts == 12


async def test_default_half_megabyte_cumulative_request_boundary() -> None:
    budget = Budget(PRICES)
    for _ in range(8):
        row = await budget.admit(65536)
        row.response_complete = True
        budget.observe(row, Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2))
    assert budget.receipt().request_bytes == 512 * 1024
    with pytest.raises(EvaluationFailure, match="judge_total_request_byte_limit"):
        await budget.admit(1)


async def test_default_half_megabyte_cumulative_response_boundary() -> None:
    budget = Budget(PRICES)
    for _ in range(8):
        row = await budget.admit(1)
        budget.consume(row, 65536)
        row.response_complete = True
        budget.observe(row, Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2))
    assert budget.receipt().response_bytes_exposure == 512 * 1024
    with pytest.raises(EvaluationFailure, match="judge_total_response_byte_limit"):
        await budget.admit(1)


async def test_concurrent_checkpoints_are_serialized() -> None:
    active = 0
    maximum = 0

    async def persist(receipt: BudgetReceipt) -> None:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1

    budget = Budget(PRICES, persist=persist)
    await asyncio.gather(*(budget.checkpoint() for _ in range(32)))
    assert maximum == 1
