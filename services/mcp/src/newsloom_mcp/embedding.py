"""Query-only embedding under the workload identity; no user credential forwarding."""

from typing import Protocol

from newsloom_core.model_transport import EmbeddingResponse, ModelClient, Usage, Vector
from pydantic import ValidationError

from newsloom_mcp.models import McpFailure


class QueryEmbedding(Protocol):
    async def embed(self, query: str, deadline: float) -> Vector: ...


class FoundryQueryEmbedding:
    def __init__(self, transport: ModelClient, deployment: str) -> None:
        if not deployment:
            raise McpFailure("embedding_deployment_required")
        self.transport, self.deployment = transport, deployment

    async def embed(self, query: str, deadline: float) -> Vector:
        if not query.strip() or len(query) > 2048:
            raise McpFailure("invalid_query")
        value = await self.transport.request(
            "embedding",
            "/openai/v1/embeddings",
            {
                "model": self.deployment,
                "input": query,
                "dimensions": 1536,
            },
            deadline,
        )
        try:
            response = EmbeddingResponse.model_validate(value)
            self.transport.record_usage(
                Usage(prompt_tokens=response.usage.prompt_tokens, completion_tokens=0)
            )
            return Vector.model_validate({"values": response.data[0].embedding})
        except ValidationError:
            raise McpFailure("invalid_query_embedding") from None
