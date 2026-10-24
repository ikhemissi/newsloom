import json
import time

import httpx
import pytest
from newsloom_enrichment.models import EnrichmentFailure, ServiceSafetyBlock
from newsloom_enrichment.providers import (
    FoundryEmbedding,
    FoundryLlm,
    ModelClient,
    prompt,
    revisions,
)
from test_enrichment_contracts import result
from test_enrichment_database import enriched
from test_ingestion_database import entry
from test_ingestion_scanner import Credential


def chat(content: object = None) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {"content": json.dumps(result()) if content is None else content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


async def test_production_generation_payload_is_isolated_and_strict() -> None:
    item = entry().model_copy(
        update={"title": "NEWSLOOM_CONTENT_CANARY", "text": "NEWSLOOM_CREDENTIAL_CANARY"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        value = json.loads(request.content)
        assert request.url.path == "/openai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer synthetic-test-token"
        assert value["messages"][0] == {"role": "developer", "content": prompt()}
        assert "CANARY" not in value["messages"][0]["content"]
        assert value["messages"][1] == {"role": "user", "content": item.model_dump_json()}
        assert len(value["messages"]) == 2 and "tools" not in value
        assert value["response_format"]["json_schema"]["strict"] is True
        assert value["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        return httpx.Response(200, json=chat())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = ModelClient(client, Credential(), "https://example.com")
        provider = FoundryLlm(transport, "generation")
        generated = await provider.generate(item, time.monotonic() + 60)
        assert generated.summary == "Nova released an SDK. It supports asynchronous requests."
        assert transport.observations.generation_calls == 1
        assert transport.observations.input_tokens == 10
        assert transport.observations.output_tokens == 20
    assert len(revisions()[0]) == len(revisions()[1]) == 64


async def test_embedding_uses_validated_summary_not_raw_article() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        value = json.loads(request.content)
        assert request.url.path == "/openai/v1/embeddings"
        assert value["dimensions"] == 1536 and value["model"] == "embedding"
        fields = json.loads(value["input"])
        assert fields["summary"] == enriched().summary and "text" not in fields
        return httpx.Response(
            200, json={"data": [{"embedding": [0.1] * 1536}], "usage": {"prompt_tokens": 12}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = ModelClient(client, Credential(), "https://example.com")
        vector = await FoundryEmbedding(transport, "embedding").embed(
            entry(), enriched(), time.monotonic() + 60
        )
        assert len(vector.values) == 1536 and transport.observations.input_tokens == 12


@pytest.mark.parametrize(
    "bad",
    [
        {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
        {
            "choices": [{"message": {"content": json.dumps(result())}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
        {
            "choices": [
                {
                    "message": {"content": None, "refusal": "NEWSLOOM_CONTENT_CANARY"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
        chat("NEWSLOOM_CONTENT_CANARY"),
        chat(json.dumps({**result(), "extra": "canary"})),
        {**chat(), "usage": {"prompt_tokens": True, "completion_tokens": 1}},
        {**chat(), "usage": {"prompt_tokens": 1}},
    ],
)
async def test_generation_failures_are_safe_and_never_repaired(
    bad: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=bad))
    ) as client:
        transport = ModelClient(client, Credential(), "https://example.com")
        with pytest.raises(EnrichmentFailure) as caught:
            await FoundryLlm(transport, "generation").generate(entry(), time.monotonic() + 60)
        assert "CANARY" not in str(caught.value)
        assert transport.observations.generation_calls == 1
    assert "CANARY" not in capsys.readouterr().out


@pytest.mark.parametrize("values", [[0.0] * 1536, [0.1] * 1535, [True] + [0.1] * 1535])
async def test_invalid_embeddings_cannot_publish(values: list[object]) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"data": [{"embedding": values}], "usage": {"prompt_tokens": 1}}
            )
        )
    ) as client:
        with pytest.raises(EnrichmentFailure, match=r"^invalid_embedding$"):
            await FoundryEmbedding(
                ModelClient(client, Credential(), "https://example.com"), "embedding"
            ).embed(entry(), enriched(), time.monotonic() + 60)


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_nonretryable_status_does_not_log_provider_errors(status: int) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                status, json={"message": "NEWSLOOM_CREDENTIAL_CANARY NEWSLOOM_COMPLETION_CANARY"}
            )
        )
    ) as client:
        transport = ModelClient(client, Credential(), "https://example.com")
        with pytest.raises(EnrichmentFailure, match=f"^generation_http_{status}$"):
            await FoundryLlm(transport, "generation").generate(entry(), time.monotonic() + 60)
        assert transport.observations.generation_calls == 1


async def test_retry_budget_and_long_retry_after_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    calls = []

    async def sleep(seconds: float) -> None:
        clock[0] += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(clock[0])
        return httpx.Response(429, headers={"Retry-After": "2"})

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr("newsloom_core.model_transport.asyncio.sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FoundryLlm(
            ModelClient(client, Credential(), "https://example.com"), "generation"
        )
        with pytest.raises(EnrichmentFailure, match=r"^generation_http_429$") as failure:
            await provider.generate(entry(), 160)
        assert calls == [100.0, 102.0, 104.0] and failure.value.retry_after == 2
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(429, headers={"Retry-After": "3600"})
        )
    ) as client:
        provider = FoundryLlm(
            ModelClient(client, Credential(), "https://example.com"), "generation"
        )
        with pytest.raises(EnrichmentFailure) as failure:
            await provider.generate(entry(), 160)
        assert failure.value.retry_after == 3600


async def test_invalid_retry_header_and_bounded_response() -> None:
    for response, reason in [
        (httpx.Response(429, headers={"Retry-After": "invalid"}), "generation_invalid_retry_after"),
        (httpx.Response(200, content=b"x" * (256 * 1024 + 1)), "generation_response_limit"),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, response=response: response)
        ) as client:
            with pytest.raises(EnrichmentFailure, match=f"^{reason}$"):
                await FoundryLlm(
                    ModelClient(client, Credential(), "https://example.com"), "generation"
                ).generate(entry(), time.monotonic() + 60)


def safety_body(
    *,
    code: str = "content_filter",
    policy: str = "ResponsibleAIPolicyViolation",
    detected: object = True,
    filtered: object = True,
) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": "NEWSLOOM_COMPLETION_CANARY",
            "innererror": {
                "code": policy,
                "content_filter_result": {
                    "jailbreak": {"detected": detected, "filtered": filtered}
                },
            },
        }
    }


async def test_only_confirmed_generation_jailbreak_blocks_get_typed_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(400, json=safety_body()))
    ) as client:
        transport = ModelClient(client, Credential(), "https://example.com")
        with pytest.raises(ServiceSafetyBlock, match="generation_jailbreak_filtered"):
            await FoundryLlm(transport, "generation").generate(entry(), time.monotonic() + 60)
        assert transport.observations.generation_calls == 1
    assert "CANARY" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "change",
    [
        {"code": "bad_request"},
        {"policy": "unknown"},
        {"detected": False},
        {"filtered": False},
        {"detected": "true"},
        {"filtered": 1},
    ],
)
async def test_unconfirmed_policy_errors_remain_http_failures(change: dict[str, object]) -> None:
    body = safety_body()
    if "code" in change:
        body = safety_body(code="bad_request")
    if "policy" in change:
        body = safety_body(policy="unknown")
    if "detected" in change:
        body = safety_body(detected=change["detected"])
    if "filtered" in change:
        body = safety_body(filtered=change["filtered"])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(400, json=body))
    ) as client:
        with pytest.raises(EnrichmentFailure, match="generation_http_400") as caught:
            await FoundryLlm(
                ModelClient(client, Credential(), "https://example.com"), "generation"
            ).generate(entry(), time.monotonic() + 60)
        assert not isinstance(caught.value, ServiceSafetyBlock)


@pytest.mark.parametrize("status", [200, 401, 403])
async def test_policy_shaped_body_with_wrong_status_cannot_bypass_validation(status: int) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=safety_body()))
    ) as client:
        with pytest.raises(EnrichmentFailure) as caught:
            await FoundryLlm(
                ModelClient(client, Credential(), "https://example.com"), "generation"
            ).generate(entry(), time.monotonic() + 60)
        assert not isinstance(caught.value, ServiceSafetyBlock)


async def test_embedding_error_and_malformed_400_are_not_generation_safety_blocks() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(400, json=safety_body()))
    ) as client:
        with pytest.raises(EnrichmentFailure, match="embedding_http_400") as caught:
            await FoundryEmbedding(
                ModelClient(client, Credential(), "https://example.com"), "embedding"
            ).embed(entry(), enriched(), time.monotonic() + 60)
        assert not isinstance(caught.value, ServiceSafetyBlock)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(400, content=b"invalid JSON"))
    ) as client:
        with pytest.raises(EnrichmentFailure, match="generation_invalid_json"):
            await FoundryLlm(
                ModelClient(client, Credential(), "https://example.com"), "generation"
            ).generate(entry(), time.monotonic() + 60)
