import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, StrictInt

from agent_evaluation.policy import EvaluationFailure, verify_privacy

CONTEXT_TOKEN_BOUND = 400_000
MODEL_SNAPSHOT: Final = "gpt-5.4-mini-2026-03-17"
MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Limits:
    attempts: int = 12
    spacing_s: float = 70
    output_tokens: int = 1024
    request_bytes: int = 64 * 1024
    response_bytes: int = 64 * 1024
    total_request_bytes: int = 512 * 1024
    total_response_bytes: int = 512 * 1024
    deadline_s: float = 1800
    usd: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        integers = (
            self.attempts,
            self.output_tokens,
            self.request_bytes,
            self.response_bytes,
            self.total_request_bytes,
            self.total_response_bytes,
        )
        if (
            any(type(value) is not int or value <= 0 for value in integers)
            or type(self.spacing_s) not in (int, float)
            or not math.isfinite(self.spacing_s)
            or self.spacing_s < 0
            or type(self.deadline_s) not in (int, float)
            or not math.isfinite(self.deadline_s)
            or self.deadline_s <= 0
            or not self.usd.is_finite()
            or self.usd <= 0
        ):
            raise EvaluationFailure("invalid_evaluation_limits")


@dataclass(frozen=True)
class Prices:
    input_per_million: Decimal
    output_per_million: Decimal

    def __post_init__(self) -> None:
        if any(
            not value.is_finite() or value <= 0
            for value in (self.input_per_million, self.output_per_million)
        ):
            raise EvaluationFailure("invalid_evaluation_prices")

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            self.input_per_million * input_tokens + self.output_per_million * output_tokens
        ) / MILLION


class Usage(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    prompt_tokens: StrictInt
    completion_tokens: StrictInt
    total_tokens: StrictInt


@dataclass
class Attempt:
    request_bytes: int
    reservation_usd: Decimal
    response_bytes: int = 0
    response_complete: bool = False
    observed_usd: Decimal | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class BudgetReceipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    attempts: int
    usage_observed: int
    usage_unknown: int
    usage_complete: bool
    admission_halted: bool
    request_bytes: int
    response_bytes_observed: int
    response_bytes_exposure: int
    input_tokens_observed: int
    output_tokens_observed: int
    estimated_observed_usd: str
    estimated_reserved_unknown_usd: str
    estimated_total_exposure_usd: str
    remaining_s: float


class Budget:
    def __init__(
        self,
        prices: Prices,
        limits: Limits | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        persist: Callable[[BudgetReceipt], Awaitable[None]] | None = None,
        ready: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        verify_privacy()
        self.prices = prices
        self.limits = limits if limits is not None else Limits()
        self.clock = clock
        self.sleep = sleep
        self.persist = persist
        self.ready = ready
        self.deadline = clock() + self.limits.deadline_s
        self.last_dispatch: float | None = None
        self.attempts: list[Attempt] = []
        self.lock = asyncio.Lock()
        # Parsing must finish before a queued sibling can dispatch after a failure.
        self.operation_lock = asyncio.Lock()
        self.checkpoint_lock = asyncio.Lock()
        self.halted = False

    def remaining(self) -> float:
        value = self.deadline - self.clock()
        if value <= 0:
            raise EvaluationFailure("evaluation_deadline")
        return value

    def exposure(self) -> Decimal:
        return sum(
            (
                row.reservation_usd if row.observed_usd is None else row.observed_usd
                for row in self.attempts
            ),
            Decimal(0),
        )

    def response_exposure(self) -> int:
        return sum(
            row.response_bytes
            if row.response_complete
            else max(row.response_bytes, self.limits.response_bytes)
            for row in self.attempts
        )

    async def pace(self) -> None:
        if self.last_dispatch is not None:
            wait = self.last_dispatch + self.limits.spacing_s - self.clock()
            if wait > 0:
                if wait >= self.remaining():
                    raise EvaluationFailure("evaluation_deadline")
                await self.sleep(wait)
        self.remaining()

    async def checkpoint(self) -> None:
        if self.persist is not None:
            async with self.checkpoint_lock:
                await self.persist(self.receipt())

    async def admit(self, request_bytes: int) -> Attempt:
        verify_privacy()
        self.remaining()
        if self.halted:
            raise EvaluationFailure("judge_admission_halted")
        if type(request_bytes) is not int or not 0 < request_bytes <= self.limits.request_bytes:
            raise EvaluationFailure("judge_request_byte_limit")
        if len(self.attempts) >= self.limits.attempts:
            raise EvaluationFailure("judge_attempt_limit")
        if sum(row.request_bytes for row in self.attempts) + request_bytes > (
            self.limits.total_request_bytes
        ):
            raise EvaluationFailure("judge_total_request_byte_limit")
        if self.response_exposure() + self.limits.response_bytes > (
            self.limits.total_response_bytes
        ):
            raise EvaluationFailure("judge_total_response_byte_limit")
        reservation = self.prices.cost(CONTEXT_TOKEN_BOUND, self.limits.output_tokens)
        if self.exposure() + reservation > self.limits.usd:
            raise EvaluationFailure("judge_cost_reservation_limit")
        row = Attempt(request_bytes=request_bytes, reservation_usd=reservation)
        self.attempts.append(row)
        await self.checkpoint()
        self.remaining()
        self.last_dispatch = self.clock()
        return row

    def consume(self, row: Attempt, size: int) -> None:
        if type(size) is not int or size < 0:
            raise EvaluationFailure("invalid_judge_response_size")
        row.response_bytes += size
        if row.response_bytes > self.limits.response_bytes:
            raise EvaluationFailure("judge_response_byte_limit")

    def observe(self, row: Attempt, usage: Usage) -> None:
        if (
            row.observed_usd is not None
            or not 1 <= usage.prompt_tokens <= CONTEXT_TOKEN_BOUND
            or not 1 <= usage.completion_tokens <= self.limits.output_tokens
            or usage.total_tokens != usage.prompt_tokens + usage.completion_tokens
        ):
            raise EvaluationFailure("invalid_judge_usage")
        row.input_tokens = usage.prompt_tokens
        row.output_tokens = usage.completion_tokens
        row.observed_usd = self.prices.cost(usage.prompt_tokens, usage.completion_tokens)

    def receipt(self) -> BudgetReceipt:
        observed = sum(
            (row.observed_usd for row in self.attempts if row.observed_usd is not None),
            Decimal(0),
        )
        unknown = sum(
            (row.reservation_usd for row in self.attempts if row.observed_usd is None),
            Decimal(0),
        )
        count = sum(row.observed_usd is not None for row in self.attempts)
        return BudgetReceipt(
            attempts=len(self.attempts),
            usage_observed=count,
            usage_unknown=len(self.attempts) - count,
            usage_complete=count == len(self.attempts),
            admission_halted=self.halted,
            request_bytes=sum(row.request_bytes for row in self.attempts),
            response_bytes_observed=sum(row.response_bytes for row in self.attempts),
            response_bytes_exposure=self.response_exposure(),
            input_tokens_observed=sum(row.input_tokens or 0 for row in self.attempts),
            output_tokens_observed=sum(row.output_tokens or 0 for row in self.attempts),
            estimated_observed_usd=str(observed),
            estimated_reserved_unknown_usd=str(unknown),
            estimated_total_exposure_usd=str(observed + unknown),
            remaining_s=max(0.0, self.deadline - self.clock()),
        )
