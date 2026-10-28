import json

import httpx2
import pytest
from azure.identity.aio import get_bearer_token_provider
from chat_fakes import scripted_chat
from fakes import TOKEN, Credential
from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from agent_evaluation.metric import Judge, measure
from agent_evaluation.policy import EvaluationFailure


class Completion:
    def __init__(self, client: AsyncOpenAI) -> None:
        self.client = client

    async def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        result = await self.client.chat.completions.parse(
            model="test-deployment",
            messages=[{"role": "user", "content": prompt}],
            response_format=schema,
            max_completion_tokens=1024,
        )
        parsed = result.choices[0].message.parsed
        if parsed is None:
            raise EvaluationFailure("missing_structured_judge_response")
        return parsed


class TextResponse(BaseModel):
    value: str


@pytest.mark.parametrize("unsupported", [False, True])
async def test_real_metric_and_entra_chat_wire(
    unsupported: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert request.url == "https://evaluation-test.openai.azure.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        payload = json.loads(request.content)
        assert payload["model"] == "test-deployment"
        assert payload["max_completion_tokens"] == 1024
        assert payload["response_format"]["type"] == "json_schema"
        return scripted_chat(request, unsupported=unsupported)

    async with (
        Credential() as credential,
        AsyncOpenAI(
            base_url="https://evaluation-test.openai.azure.com/openai/v1",
            api_key=get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            ),
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(respond), trust_env=False, follow_redirects=False
            ),
        ) as client,
    ):
        score, reason = await measure(
            Completion(client),
            question="When is the synthetic launch?",
            evidence="The synthetic launch is Tuesday.",
            answer="Monday." if unsupported else "Tuesday.",
        )
    assert credential.closed
    assert credential.scopes == [("https://cognitiveservices.azure.com/.default",)]
    assert score == (0.0 if unsupported else 1.0)
    assert reason == ("Unsupported synthetic claim." if unsupported else "Supported.")
    assert len(requests) == 4
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
    assert "synthetic launch" not in captured.out + captured.err


async def test_real_chat_sdk_does_not_retry_rate_limit() -> None:
    calls = 0

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(429, json={"error": {"message": "synthetic rate limit"}})

    async with (
        Credential() as credential,
        AsyncOpenAI(
            base_url="https://evaluation-test.openai.azure.com/openai/v1",
            api_key=get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            ),
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond)),
        ) as client,
    ):
        with pytest.raises(RateLimitError):
            await Completion(client).complete("Synthetic question", TextResponse)
    assert calls == 1


async def test_judge_rejects_nonstructured_and_synchronous_calls() -> None:
    class Forbidden:
        async def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
            raise AssertionError("unexpected_dispatch")

    judge = Judge(Forbidden())
    with pytest.raises(EvaluationFailure, match="synchronous_judge_forbidden"):
        judge.generate("Synthetic")
    with pytest.raises(EvaluationFailure, match="judge_schema_required"):
        await judge.a_generate("Synthetic")


async def test_invalid_real_schema_response_is_not_a_quality_score() -> None:
    class Invalid:
        async def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
            return schema.model_validate_json('{"foreign":true}')

    with pytest.raises(ValidationError):
        await measure(Invalid(), question="Synthetic?", evidence="Synthetic.", answer="Synthetic.")
