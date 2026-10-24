import time

import httpx
import pytest
from newsloom_core.model_transport import ModelClient, ModelFailure
from newsloom_mcp.embedding import FoundryQueryEmbedding
from newsloom_mcp.models import McpFailure
from test_ingestion_scanner import Credential


async def test_query_embedding_uses_only_query_and_workload_token() -> None:
    import json

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        value = json.loads(request.content)
        assert value == {"model": "embedding", "input": "agent access policies", "dimensions": 1536}
        assert request.url.path == "/openai/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer synthetic-test-token"
        calls.append(1)
        return httpx.Response(
            200, json={"data": [{"embedding": [0.1] * 1536}], "usage": {"prompt_tokens": 5}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = ModelClient(client, Credential(), "https://example.com")
        result = await FoundryQueryEmbedding(transport, "embedding").embed(
            "agent access policies", time.monotonic() + 60
        )
        assert len(result.values) == 1536
        assert transport.observations.input_tokens == 5
        assert transport.observations.generation_calls == 0
    assert len(calls) == 1


@pytest.mark.parametrize("bad", [[0.1] * 1535, [0.0] * 1536, [True] + [0.1] * 1535])
async def test_invalid_query_vectors_remain_failures(bad: list[object]) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"data": [{"embedding": bad}], "usage": {"prompt_tokens": 2}}
            )
        )
    ) as client:
        with pytest.raises(McpFailure, match="invalid_query_embedding"):
            await FoundryQueryEmbedding(
                ModelClient(client, Credential(), "https://example.com"), "embedding"
            ).embed("query", time.monotonic() + 60)


async def test_no_semantic_fallback_on_inference_error() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(403, text="NEWSLOOM_CREDENTIAL_CANARY")
        )
    ) as client:
        with pytest.raises(ModelFailure, match="embedding_http_403"):
            await FoundryQueryEmbedding(
                ModelClient(client, Credential(), "https://example.com"), "embedding"
            ).embed("query", time.monotonic() + 60)
