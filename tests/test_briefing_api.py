from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, tzinfo
from unittest.mock import AsyncMock

import httpx
import psycopg
import pytest
from newsloom_core.briefing import BriefingRead, cutoff_at
from newsloom_mcp.briefing import read_briefing
from newsloom_mcp.http_api import NewsApi
from newsloom_mcp.repository import NewsRepository
from newsloom_mcp.services import Services
from starlette.types import Receive, Scope, Send
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Endpoint
from test_mcp_http import endpoint as endpoint


async def test_expired_running_refresh_is_honestly_failed_without_writing() -> None:
    connection = AsyncMock(spec=psycopg.AsyncConnection)
    artifact = AsyncMock()
    artifact.fetchone.return_value = None
    status = AsyncMock()
    status.fetchone.return_value = ("running", datetime.now(UTC) - timedelta(hours=2))
    connection.execute.side_effect = [artifact, status]
    result = await read_briefing(connection, cutoff_at(datetime.now(UTC)))
    assert result.briefing is None and result.refresh.state == "failed"
    assert result.refresh.stale
    assert all(call.args[0].startswith("SELECT") for call in connection.execute.call_args_list)


async def test_briefing_read_authorization_cache_and_no_other_work(
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, reader, embeddings, token, verifier, _ = endpoint
    calls = []
    initial = cutoff_at(datetime.now(UTC))
    clock = [initial + timedelta(hours=23, minutes=59)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Clock:
            return cls.fromtimestamp(clock[0].timestamp(), tz)

    monkeypatch.setattr("newsloom_mcp.http_api.datetime", Clock)

    async def briefing(cutoff: datetime) -> BriefingRead:
        calls.append(cutoff)
        return BriefingRead.model_validate(
            {
                "briefing": None,
                "refresh": {"expected_cutoff": cutoff, "state": "pending", "stale": True},
            }
        )

    async def ready() -> bool:
        return True

    @asynccontextmanager
    async def repositories() -> AsyncIterator[NewsRepository]:
        raise AssertionError("briefing_must_not_query_news_or_embed")
        yield reader

    async def unused(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("briefing_not_handled")

    services = Services(repositories, embeddings, ready, briefing=briefing)
    app = NewsApi(
        unused,
        services,
        verifier,
        __import__("asyncio").Semaphore(4),
        True,
        ("newsloom.test",),
        ("https://vscode.dev",),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="https://newsloom.test",
    ) as client:
        assert (await client.get("/api/v1/briefing")).status_code == 401
        client.headers["Authorization"] = "Bearer " + token
        first = await client.get("/api/v1/briefing")
        assert first.status_code == 200 and first.json()["meta"]["result_scope"] == "briefing"
        assert first.headers["cache-control"] == "no-store"
        assert first.json()["refresh"]["stale"] is True
        assert (await client.get("/api/v1/briefing")).status_code == 200
        assert calls == [initial]
        clock[0] = initial + timedelta(days=1)
        assert (await client.get("/api/v1/briefing")).status_code == 200
        assert calls == [initial, initial + timedelta(days=1)]
        assert not reader.calls and not embeddings.calls
        assert (await client.get("/api/v1/briefing?generate=true")).status_code == 400
        assert (await client.post("/api/v1/briefing")).status_code == 405

        def forbidden(*args: object) -> None:
            raise AssertionError("unauthorized_cache_access")

        monkeypatch.setattr("newsloom_mcp.response_cache.ResponseCache.get", forbidden)
        client.headers["Authorization"] = "Bearer invalid"
        assert (await client.get("/api/v1/briefing")).status_code == 401
