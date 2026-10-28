import asyncio
from dataclasses import replace

import httpx2
import pytest
from chat_fakes import scripted_chat
from openai import AsyncOpenAI, InternalServerError, RateLimitError
from pydantic import BaseModel, ValidationError
from test_budget import PRICES, Clock

from agent_evaluation.budget import MODEL_SNAPSHOT, Budget, Limits
from agent_evaluation.judge import Completion, JudgeTransport, chat_endpoint
from agent_evaluation.metric import measure
from agent_evaluation.policy import EvaluationFailure

ENDPOINT = "https://evaluation-test.openai.azure.com"


class Text(BaseModel):
    value: str


async def test_real_metric_uses_one_shared_budget_across_both_cases() -> None:
    clock = Clock()
    budget = Budget(PRICES, clock=clock, sleep=clock.sleep)
    requests: list[httpx2.Request] = []
    unsupported = False

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return scripted_chat(request, unsupported=unsupported, snapshot=MODEL_SNAPSHOT)

    transport = JudgeTransport(ENDPOINT, "test-deployment", budget, httpx2.MockTransport(respond))
    async with AsyncOpenAI(
        base_url=ENDPOINT + "/openai/v1",
        api_key="synthetic",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=transport, follow_redirects=False),
    ) as client:
        completion = Completion(client, "test-deployment", budget)
        first, _ = await measure(
            completion, question="Synthetic?", evidence="Tuesday.", answer="Tuesday."
        )
        unsupported = True
        second, _ = await measure(
            completion, question="Synthetic?", evidence="Tuesday.", answer="Monday."
        )
    assert first == 1
    assert second == 0
    assert len(requests) == 8
    assert clock.waits == [70] * 7
    receipt = budget.receipt()
    assert receipt.attempts == receipt.usage_observed == 8
    assert receipt.usage_unknown == 0
    assert receipt.usage_complete


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://evaluation-test.openai.azure.com",
        "https://evaluation-test.openai.azure.com/foreign",
        "https://evaluation-test.openai.azure.com?foreign=1",
        "https://evaluation-test.openai.azure.com#foreign",
        "https://user@evaluation-test.openai.azure.com",
        "https://evaluation-test.openai.azure.com.evil.example",
        "https://example.com",
    ],
)
def test_fixed_endpoint_validation(endpoint: str) -> None:
    with pytest.raises(EvaluationFailure, match="invalid_fixed_judge_endpoint"):
        chat_endpoint(endpoint)


async def test_native_rate_limit_is_not_retried_or_refunded() -> None:
    calls = 0
    budget = Budget(PRICES)

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(429, json={"error": {"message": "synthetic limit"}})

    async with AsyncOpenAI(
        base_url=ENDPOINT + "/openai/v1",
        api_key="synthetic",
        max_retries=0,
        http_client=httpx2.AsyncClient(
            transport=JudgeTransport(
                ENDPOINT, "test-deployment", budget, httpx2.MockTransport(respond)
            )
        ),
    ) as client:
        with pytest.raises(RateLimitError):
            await Completion(client, "test-deployment", budget).complete("Synthetic", Text)
    assert calls == 1
    assert budget.receipt().usage_unknown == 1


async def test_native_redirect_is_rejected_before_following() -> None:
    calls = 0
    budget = Budget(PRICES)

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(307, headers={"location": "https://foreign.example"})

    async with AsyncOpenAI(
        base_url=ENDPOINT + "/openai/v1",
        api_key="synthetic",
        max_retries=0,
        http_client=httpx2.AsyncClient(
            follow_redirects=True,
            transport=JudgeTransport(
                ENDPOINT, "test-deployment", budget, httpx2.MockTransport(respond)
            ),
        ),
    ) as client:
        with pytest.raises(EvaluationFailure, match="judge_redirect_rejected"):
            await Completion(client, "test-deployment", budget).complete("Synthetic", Text)
    assert calls == 1
    assert budget.receipt().usage_unknown == 1


async def test_library_extra_call_cannot_bypass_shared_admission() -> None:
    calls = 0
    budget = Budget(PRICES, replace(Limits(), attempts=1, spacing_s=0))

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return scripted_chat(request, snapshot=MODEL_SNAPSHOT)

    async with AsyncOpenAI(
        base_url=ENDPOINT + "/openai/v1",
        api_key="synthetic",
        max_retries=0,
        http_client=httpx2.AsyncClient(
            transport=JudgeTransport(
                ENDPOINT, "test-deployment", budget, httpx2.MockTransport(respond)
            )
        ),
    ) as client:
        with pytest.raises(EvaluationFailure, match="judge_attempt_limit"):
            await measure(
                Completion(client, "test-deployment", budget),
                question="Synthetic?",
                evidence="Tuesday.",
                answer="Tuesday.",
            )
    assert calls == 1
    assert budget.receipt().attempts == 1


async def test_cancellation_keeps_inflight_reservation() -> None:
    budget = Budget(PRICES)
    entered = asyncio.Event()

    async def respond(request: httpx2.Request) -> httpx2.Response:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async with AsyncOpenAI(
        base_url=ENDPOINT + "/openai/v1",
        api_key="synthetic",
        max_retries=0,
        http_client=httpx2.AsyncClient(
            transport=JudgeTransport(
                ENDPOINT, "test-deployment", budget, httpx2.MockTransport(respond)
            )
        ),
    ) as client:
        task = asyncio.create_task(
            Completion(client, "test-deployment", budget).complete("Synthetic", Text)
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert budget.receipt().attempts == budget.receipt().usage_unknown == 1
    assert budget.exposure() > 0
    assert budget.receipt().admission_halted


@pytest.mark.parametrize("malformed", [False, True])
async def test_failed_call_stops_queued_sibling_before_another_dispatch(malformed: bool) -> None:
    budget = Budget(PRICES)
    calls = 0

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if not malformed:
            return httpx2.Response(500, json={"error": {"message": "synthetic failure"}})
        return httpx2.Response(
            200,
            json={
                "id": "test",
                "created": 1,
                "object": "chat.completion",
                "model": MODEL_SNAPSHOT,
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"value":{}}'},
                    }
                ],
            },
        )

    async with AsyncOpenAI(
        base_url=ENDPOINT + "/openai/v1",
        api_key="synthetic",
        max_retries=0,
        http_client=httpx2.AsyncClient(
            transport=JudgeTransport(
                ENDPOINT, "test-deployment", budget, httpx2.MockTransport(respond)
            )
        ),
    ) as client:
        completion = Completion(client, "test-deployment", budget)
        with pytest.raises(ValidationError if malformed else InternalServerError):
            await asyncio.gather(
                completion.complete("Synthetic", Text),
                completion.complete("Synthetic", Text),
            )
    assert calls == 1
    assert budget.receipt().admission_halted
