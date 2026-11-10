"""Read-only overnight serving: fallback memory, snapshot reloads and HTTP behaviour."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import httpx
import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from newsloom_mcp.app import Services, create_app
from newsloom_mcp.auth import EntraVerifier
from newsloom_mcp.feedback import reader_hash
from newsloom_mcp.models import McpFailure, NewsDetail
from newsloom_mcp.radar import Card, Product, RadarStore
from newsloom_mcp.repository import NewsRepository
from newsloom_mcp.snapshot import (
    CardState,
    Fallback,
    Snapshot,
    SnapshotNews,
    SnapshotRadar,
)
from test_mcp_auth import jwks
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Embeddings

AS_OF = datetime(2026, 11, 10, 22, 45, tzinfo=UTC)
NEWS = UUID(int=1)


def snapshot(reader: str = "") -> Snapshot:
    product = Product(id=UUID(int=2), name="Widget", vendor="Acme", vendor_id=UUID(int=3))
    card = Card(
        id=UUID(int=4),
        news_id=NEWS,
        title="Widget ships",
        url="https://publisher.test/widget",
        source="fixture-source",
        published_at=datetime(2026, 11, 10, 9, tzinfo=UTC),
        article_kind="announcement",
        statement="Widget is generally available.",
        status="ga",
        effective_date=date(2026, 11, 10),
        deadline=None,
        products=(product,),
        tier="act_now",
        reason="Matters.",
        capability="agent tools",
    )
    item = NewsDetail.model_validate(
        {
            "id": NEWS,
            "title": "Widget ships",
            "summary": "Widget is generally available.",
            "source": "fixture-source",
            "category": "models",
            "tags": ["widget"],
            "published_at": card.published_at,
            "url": card.url,
            "author": "Fixture",
            "date_origin": "published",
            "publisher_categories": [],
        }
    )
    return Snapshot(
        as_of=AS_OF,
        items=(item,),
        cards=(card,),
        products=(),
        stack_entries=(),
        stacks={},
        states={reader: {card.id: CardState(state="done", until=None)}} if reader else {},
        briefing=None,
    )


class Blob:
    def __init__(self, value: Snapshot | None) -> None:
        self.value, self.etag, self.calls = value, "v1", 0

    async def get(self, etag: str | None) -> tuple[bytes, str] | None:
        self.calls += 1
        if self.value is None:
            raise McpFailure("snapshot_unavailable")
        return None if etag == self.etag else (self.value.encode(), self.etag)


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def unreachable() -> object:
    @asynccontextmanager
    async def connect() -> AsyncIterator[object]:
        raise psycopg.OperationalError("connection refused")
        yield

    return connect


async def test_fallback_remembers_failures_and_reloads_only_changed_snapshots() -> None:
    blob, clock = Blob(snapshot()), Clock()
    fallback = Fallback(blob, clock)  # type: ignore[arg-type]
    attempts = 0

    @asynccontextmanager
    async def connect() -> AsyncIterator[str]:
        nonlocal attempts
        attempts += 1
        raise psycopg.OperationalError("connection refused")
        yield "never"

    for _ in range(3):
        async with fallback.database(connect) as current:
            assert current is None
    assert attempts == 1 and fallback.offline()
    assert (await fallback.snapshot()).as_of == AS_OF and fallback.as_of() == AS_OF
    await fallback.snapshot()
    assert blob.calls == 1
    clock.now += Fallback.RECHECK
    await fallback.snapshot()
    assert blob.calls == 2  # unchanged ETag: kept in memory

    clock.now += Fallback.REMEMBER
    assert not fallback.offline() and fallback.as_of() is None

    @asynccontextmanager
    async def healthy() -> AsyncIterator[str]:
        yield "connection"

    async with fallback.database(healthy) as current:
        assert current == "connection"


async def test_without_a_snapshot_the_failure_is_explicit() -> None:
    fallback = Fallback(Blob(None), Clock())  # type: ignore[arg-type]
    fallback.failed()
    with pytest.raises(McpFailure, match="snapshot_unavailable"):
        await fallback.snapshot()
    assert not await fallback.loaded()


async def test_without_snapshot_configuration_connection_errors_propagate() -> None:
    fallback = Fallback(None)

    @asynccontextmanager
    async def connect() -> AsyncIterator[str]:
        raise psycopg.OperationalError("connection refused")
        yield "never"

    with pytest.raises(psycopg.OperationalError):
        async with fallback.database(connect):
            pass
    assert not fallback.offline()


@pytest.fixture
async def night(
    signing_key: rsa.RSAPrivateKey,
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str]]]:
    tenant, audience, oid = uuid4(), uuid4(), uuid4()
    data = snapshot(reader_hash(tenant, oid))

    async def ready() -> bool:
        return True

    @asynccontextmanager
    async def repository() -> AsyncIterator[NewsRepository]:
        yield SnapshotNews(data)

    @asynccontextmanager
    async def radar() -> AsyncIterator[RadarStore]:
        yield SnapshotRadar(data)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=jwks(signing_key)))
    ) as trusted_keys:
        verifier = EntraVerifier(trusted_keys, tenant, audience)
        token = jwt.encode(
            {
                "iss": verifier.issuer,
                "aud": str(audience),
                "tid": str(tenant),
                "sub": "synthetic-subject",
                "oid": str(oid),
                "azp": str(uuid4()),
                "exp": int(time.time()) + 600,
                "nbf": int(time.time()) - 1,
                "ver": "2.0",
                "scp": "news.read",
            },
            signing_key,
            algorithm="RS256",
            headers={"kid": "local-test-key"},
        )
        app = create_app(
            Services(repository, Embeddings(), ready, radar=radar, read_only=lambda: AS_OF),
            verifier,
            "https://newsloom.test/mcp",
            ["newsloom.test"],
            ["https://web.test"],
            news_api_enabled=True,
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
                transport=httpx.ASGITransport(app), base_url="https://newsloom.test"
            ) as client:
                yield client, {"Authorization": "Bearer " + token, "Origin": "https://web.test"}
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)


async def test_reads_are_served_and_marked_and_writes_are_read_only(
    night: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, headers = night
    response = await client.get("/api/v1/radar?window=7", headers=headers)
    assert response.status_code == 200
    assert response.headers["X-Newsloom-Read-Only"] == AS_OF.isoformat()
    assert response.headers["Access-Control-Expose-Headers"] == "X-Newsloom-Read-Only"
    assert [card["state"] for card in response.json()["hidden"]] == ["done"]

    detail = await client.get(f"/api/v1/news/{NEWS}", headers=headers)
    assert detail.status_code == 200 and detail.json()["item"]["title"] == "Widget ships"

    for method, path, body in (
        ("PUT", f"/api/v1/me/cards/{UUID(int=4)}", {"state": "done"}),
        ("PUT", "/api/v1/me/stack", {"ids": []}),
        ("POST", "/api/v1/search", {"query": "widget"}),
    ):
        blocked = await client.request(method, path, json=body, headers=headers)
        assert blocked.status_code == 503, path
        assert blocked.json()["error"]["code"] == "read_only"
        assert blocked.headers["X-Newsloom-Read-Only"] == AS_OF.isoformat()
