import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from newsloom_core.categories import Category
from newsloom_core.model_transport import Vector
from newsloom_mcp.app import Services, create_app
from newsloom_mcp.auth import EntraVerifier
from newsloom_mcp.models import (
    DetailInput,
    ItemResult,
    NewsDetail,
    NewsItem,
    NewsResults,
    RankedItem,
    RecentInput,
    SearchInput,
    SearchResults,
    SourcesResult,
)
from newsloom_mcp.repository import NewsRepository
from test_mcp_auth import jwks
from test_mcp_auth import signing_key as signing_key


class Reader:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.observations: list[tuple[str, str, float]] = []
        self.http_observations: list[tuple[str, str, float]] = []
        self.item = NewsItem(
            id=uuid4(),
            title="NEWSLOOM_CONTENT_CANARY",
            summary="NEWSLOOM_COMPLETION_CANARY",
            source="synthetic",
            category=Category.GOVERNANCE,
            tags=("ai", "gateway", "news"),
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            url="https://example.com/news",
        )

    async def recent(self, args: RecentInput) -> NewsResults:
        self.calls.append(args)
        return NewsResults(items=(self.item,))

    def observe(self, tool: str, outcome: str, elapsed: float) -> None:
        self.observations.append((tool, outcome, elapsed))

    def observe_http(self, surface: str, outcome: str, elapsed: float) -> None:
        self.http_observations.append((surface, outcome, elapsed))

    async def detail(self, args: DetailInput) -> ItemResult:
        self.calls.append(args)
        return ItemResult(
            found=True,
            item=NewsDetail(
                **self.item.model_dump(),
                author="",
                date_origin="published",
                publisher_categories=(),
            ),
        )

    async def sources(self) -> SourcesResult:
        self.calls.append("sources")
        return SourcesResult(sources=(), categories=())

    async def search(self, args: SearchInput, vector: tuple[float, ...] | None) -> SearchResults:
        self.calls.append(args)
        return SearchResults(
            items=(
                RankedItem(
                    **self.item.model_dump(),
                    similarity=0.8 if vector else None,
                ),
            )
        )


class Embeddings:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, query: str, deadline: float) -> Vector:
        self.calls.append(query)
        return Vector(values=(0.1,) * 1536)


Endpoint = tuple[httpx.AsyncClient, Reader, Embeddings, str, EntraVerifier, rsa.RSAPrivateKey]


@pytest.fixture
async def endpoint(
    signing_key: rsa.RSAPrivateKey,
) -> AsyncIterator[Endpoint]:
    reader, embeddings = Reader(), Embeddings()
    tenant, audience = uuid4(), uuid4()

    async def ready() -> bool:
        return True

    @asynccontextmanager
    async def repository() -> AsyncIterator[NewsRepository]:
        yield reader

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=jwks(signing_key)))
    ) as trusted_keys:
        verifier = EntraVerifier(trusted_keys, tenant, audience)
        claims = {
            "iss": verifier.issuer,
            "aud": str(audience),
            "tid": str(tenant),
            "sub": "synthetic-subject",
            "azp": str(uuid4()),
            "exp": int(time.time()) + 600,
            "nbf": int(time.time()) - 1,
            "ver": "2.0",
            "scp": "news.read",
        }
        token = jwt.encode(
            claims, signing_key, algorithm="RS256", headers={"kid": "local-test-key"}
        )
        app = create_app(
            Services(repository, embeddings, ready, reader.observe, reader.observe_http),
            verifier,
            "https://newsloom.test/mcp",
            ["newsloom.test"],
            ["https://vscode.dev"],
        )
        started, stop = asyncio.Event(), asyncio.Event()

        async def lifespan() -> None:
            async with app.router.lifespan_context(app):
                started.set()
                await stop.wait()

        task = asyncio.create_task(lifespan())
        await asyncio.wait_for(started.wait(), 5)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app),
                base_url="https://newsloom.test",
                headers={"Accept": "application/json, text/event-stream"},
            ) as client:
                yield client, reader, embeddings, token, verifier, signing_key
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)


def request(method: str, params: dict[str, object] | None = None) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


async def test_authenticated_http_tools_have_exact_aliases_and_structured_outputs(
    endpoint: Endpoint,
) -> None:
    client, reader, embeddings, token, _verifier, _key = endpoint
    client.headers["Authorization"] = "Bearer " + token
    response = await client.post(
        "/mcp",
        json=request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "synthetic", "version": "1"},
            },
        ),
    )
    assert response.status_code == 200
    response = await client.post("/mcp", json=request("tools/list"))
    tools = response.json()["result"]["tools"]
    assert {item["name"] for item in tools} == {
        "get_recent_news",
        "get_news_item",
        "list_sources",
        "search_news",
    }
    schema = next(item["inputSchema"] for item in tools if item["name"] == "search_news")
    assert "from" in schema["properties"] and "from_" not in schema["properties"]
    for name, arguments in [
        ("get_recent_news", {}),
        ("get_news_item", {"id": str(reader.item.id)}),
        ("list_sources", {}),
        ("search_news", {"from": "2026-01-01T00:00:00Z", "tags": ["AI"]}),
        ("search_news", {"query": "NEWSLOOM_QUERY_CANARY", "category": "governance"}),
    ]:
        response = await client.post(
            "/mcp", json=request("tools/call", {"name": name, "arguments": arguments})
        )
        value = response.json()["result"]
        assert response.status_code == 200 and not value.get("isError", False)
        assert "structuredContent" in value
    assert len(embeddings.calls) == 1
    assert any(isinstance(args, SearchInput) and args.from_ is not None for args in reader.calls)


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "forged",
        "expired",
        "future",
        "issuer",
        "tenant",
        "audience",
        "scope",
        "app-only",
        "id-token",
    ],
)
async def test_actual_http_auth_rejects_before_any_data_or_model_use(
    endpoint: Endpoint,
    kind: str,
) -> None:
    client, reader, embeddings, token, _verifier, key = endpoint
    claims = jwt.decode(token, options={"verify_signature": False})
    if kind == "expired":
        claims["exp"] = 1
    if kind == "future":
        claims["nbf"] = int(time.time()) + 600
    if kind == "issuer":
        claims["iss"] = "https://issuer.invalid"
    if kind == "tenant":
        claims["tid"] = str(uuid4())
    if kind == "audience":
        claims["aud"] = str(uuid4())
    if kind == "scope":
        claims["scp"] = "other.read"
    if kind == "app-only":
        del claims["scp"]
        claims["roles"] = ["news.read"]
    if kind == "id-token":
        claims["aud"] = str(uuid4())
        claims["nonce"] = "NEWSLOOM_ID_TOKEN_CANARY"
        del claims["scp"]
    if kind == "forged":
        token = token[:-8] + "forged00"
    elif kind != "missing":
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "local-test-key"})
    if kind != "missing":
        client.headers["Authorization"] = "Bearer " + token
    for method in ("initialize", "tools/list", "tools/call"):
        response = await client.post(
            "/mcp",
            json=request(
                method, {"name": "search_news", "arguments": {"query": "NEWSLOOM_QUERY_CANARY"}}
            ),
        )
        assert response.status_code == (403 if kind in ("scope", "app-only") else 401)
    assert reader.calls == embeddings.calls == []


async def test_metadata_host_origin_invalid_inputs_and_privacy(
    endpoint: Endpoint,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client, reader, embeddings, token, verifier, _key = endpoint
    metadata = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert metadata.status_code == 200
    assert metadata.json()["resource"] == "https://newsloom.test/mcp"
    assert metadata.json()["scopes_supported"] == [verifier.scope]
    challenge = await client.post("/mcp", json=request("tools/list"))
    assert "resource_metadata" in challenge.headers["www-authenticate"]
    client.headers["Authorization"] = "Bearer " + token
    response = await client.post(
        "/mcp", json=request("tools/list"), headers={"Origin": "https://evil.invalid"}
    )
    assert response.status_code == 403
    response = await client.post(
        "/mcp", json=request("tools/list"), headers={"Host": "evil.invalid"}
    )
    assert response.status_code == 421
    for arguments in ({"limit": True}, {"query": " "}, {"from": "2026-01-01"}, {"extra": "CANARY"}):
        response = await client.post(
            "/mcp", json=request("tools/call", {"name": "search_news", "arguments": arguments})
        )
        assert response.json()["result"]["isError"]
    assert reader.calls == embeddings.calls == []
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err


async def test_body_limit_and_health_are_explicit(endpoint: Endpoint) -> None:
    client, reader, embeddings, token, _verifier, _key = endpoint
    assert (await client.get("/health/live")).status_code == 200
    assert (await client.get("/health/ready")).status_code == 200
    client.headers["Authorization"] = "Bearer " + token
    response = await client.post(
        "/mcp", content=b"x" * (64 * 1024 + 1), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert not reader.calls and not embeddings.calls

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(65):
            yield b"x" * 1024

    response = await client.post(
        "/mcp", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert not reader.calls and not embeddings.calls


async def test_overload_and_cancellation_release_bounded_work(
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, reader, _embeddings, token, _verifier, _key = endpoint
    client.headers["Authorization"] = "Bearer " + token
    active = 0
    admitted = asyncio.Event()
    cancelled = []

    async def blocked(args: RecentInput) -> NewsResults:
        nonlocal active
        active += 1
        if active == 4:
            admitted.set()
        try:
            await asyncio.Future[None]()
        except asyncio.CancelledError:
            cancelled.append(1)
            raise
        return NewsResults(items=())

    monkeypatch.setattr(reader, "recent", blocked)
    tasks = [
        asyncio.create_task(
            client.post(
                "/mcp",
                json=request(
                    "tools/call",
                    {
                        "name": "get_recent_news",
                        "arguments": {},
                    },
                ),
            )
        )
        for _ in range(4)
    ]
    await asyncio.wait_for(admitted.wait(), 5)
    response = await client.post(
        "/mcp",
        json=request(
            "tools/call",
            {
                "name": "get_recent_news",
                "arguments": {},
            },
        ),
    )
    assert response.json()["result"]["isError"]
    assert response.json()["result"]["content"][0]["text"] == "mcp_overloaded"
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert len(cancelled) == 4
    assert (await client.get("/health/ready")).status_code == 200
    assert sum(outcome == "cancelled" for _, outcome, _ in reader.observations) == 4
    assert sum(outcome == "cancelled" for _, outcome, _ in reader.http_observations) == 4
