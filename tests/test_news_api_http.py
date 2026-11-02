import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import jwt
import psycopg
import pytest
from newsloom_core.auth import TrustedKeysFailure
from newsloom_core.diagnostics import SafeHandler
from newsloom_core.model_transport import Vector
from newsloom_mcp.http_api import NewsApi
from newsloom_mcp.models import SearchInput, SearchResults
from newsloom_mcp.repository import NewsRepository
from newsloom_mcp.services import Services
from starlette.types import Message, Receive, Scope, Send
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Endpoint, request
from test_mcp_http import endpoint as endpoint

pytestmark = pytest.mark.parametrize("endpoint", [True], indirect=True)


def signed(endpoint: Endpoint, **changes: object) -> str:
    _, _, _, token, _, key = endpoint
    claims = jwt.decode(token, options={"verify_signature": False})
    claims.update(changes)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "local-test-key"})


async def test_routes_cache_hits_avoid_repository_embedding_and_preserve_mcp(
    endpoint: Endpoint,
) -> None:
    client, reader, embeddings, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    for path in ("/api/v1/news", "/api/v1/sources", f"/api/v1/news/{reader.item.id}"):
        first = await client.get(path)
        assert first.status_code == 200 and first.headers["Cache-Control"] == "no-store"
        calls = len(reader.calls)
        second = await client.get(path)
        assert second.status_code == 200 and len(reader.calls) == calls
        assert second.json()["meta"]["read_at"] == first.json()["meta"]["read_at"]
    first = await client.post("/api/v1/search", json={"query": "AUTHORED_QUERY_CANARY"})
    assert first.status_code == 200 and first.json()["next_cursor"] is None
    assert first.json()["meta"]["result_scope"] == "bounded"
    calls = len(reader.calls)
    second = await client.post("/api/v1/search", json={"query": "AUTHORED_QUERY_CANARY"})
    assert second.status_code == 200 and len(reader.calls) == calls
    assert len(embeddings.calls) == 1
    assert [row[2] for row in reader.api_observations] == ["miss", "hit"] * 4
    response = await client.post(
        "/mcp", json=request("tools/call", {"name": "get_recent_news", "arguments": {}})
    )
    assert response.status_code == 200 and response.json()["result"]["structuredContent"]["items"]


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"exp": 1}, 401),
        ({"nbf": 9999999999}, 401),
        ({"aud": "wrong"}, 401),
        ({"tid": str(uuid4())}, 401),
        ({"iss": "https://wrong.test"}, 401),
        ({"scp": ""}, 403),
        ({"scp": "news.agent"}, 403),
    ],
)
async def test_warm_cache_is_never_consulted_before_authorization(
    endpoint: Endpoint,
    changes: dict[str, object],
    status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, reader, _, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    assert (await client.get("/api/v1/news")).status_code == 200

    def forbidden(*args: object) -> None:
        raise AssertionError("cache_consulted_before_authorization")

    monkeypatch.setattr("newsloom_mcp.response_cache.ResponseCache.get", forbidden)
    client.headers["Authorization"] = "Bearer " + signed(endpoint, **changes)
    response = await client.get("/api/v1/news")
    assert response.status_code == status and len(reader.calls) == 1
    client.headers.pop("Authorization")
    assert (await client.get("/api/v1/news")).status_code == 401


async def test_caller_client_scope_partitions_and_token_renewal(endpoint: Endpoint) -> None:
    client, reader, _, token, _, _ = endpoint
    cases: list[tuple[dict[str, object], int]] = [
        ({}, 1),
        ({"exp": int(time.time()) + 1200}, 1),
        ({"sub": "other-subject"}, 2),
        ({"azp": str(uuid4())}, 3),
        ({"scp": "news.read extra.scope"}, 4),
    ]
    for changes, expected_calls in cases:
        client.headers["Authorization"] = "Bearer " + (
            signed(endpoint, **changes) if changes else token
        )
        assert (await client.get("/api/v1/news")).status_code == 200
        assert len(reader.calls) == expected_calls


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/news?limit=true",
        "/api/v1/news?limit=0",
        "/api/v1/news?limit=51",
        "/api/v1/news?limit=20&limit=20",
        "/api/v1/news?query=hidden",
        "/api/v1/news?cursor=bad",
        "/api/v1/news/not-a-uuid",
        "/api/v1/sources?x=y",
        "/api/v1/news?from=0001-01-01T00:00:00%2B09:00",
    ],
)
async def test_invalid_requests_use_safe_errors_and_zero_work(
    endpoint: Endpoint, path: str
) -> None:
    client, reader, embeddings, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    result = await client.get(path)
    assert result.status_code == 400
    assert set(result.json()["error"]) == {"code", "request_id"}
    assert not reader.calls and not embeddings.calls


async def test_invalid_json_duplicates_limits_methods_and_cors(endpoint: Endpoint) -> None:
    client, reader, _, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    for body, media, status in [
        (b'{"query":"a","query":"b"}', "application/json", 400),
        (b'{"query":""}', "application/json", 400),
        (b'{"query":"x","cursor":"x"}', "application/json", 400),
        (b"{", "application/json", 400),
        (b"{}", "text/plain", 415),
        (b"x" * (64 * 1024 + 1), "application/json", 413),
    ]:
        result = await client.post("/api/v1/search", content=body, headers={"Content-Type": media})
        assert result.status_code == status
    assert (await client.put("/api/v1/news")).status_code == 405
    assert (await client.get("/api/v1/unknown")).status_code == 404
    assert not reader.calls
    for path, method in (("/api/v1/news", "GET"), ("/api/v1/search", "POST")):
        response = await client.options(
            path,
            headers={
                "Origin": "https://vscode.dev",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Methods"] == method
        assert response.headers["Access-Control-Max-Age"] == "300"
    for headers in ({"Origin": "https://wrong.test"}, {"Host": "wrong.test"}):
        assert (await client.get("/api/v1/news", headers=headers)).status_code == 403
    denied = await client.get(
        "/api/v1/news", headers={"Origin": "https://vscode.dev", "Authorization": "Bearer invalid"}
    )
    assert (
        denied.status_code == 401
        and denied.headers["Access-Control-Allow-Origin"] == "https://vscode.dev"
    )


async def test_cancelled_and_failed_misses_never_cache_or_log_content(
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client, reader, embeddings, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    monkeypatch.setattr(logging.getLogger(), "handlers", [SafeHandler()])

    async def fail(args: SearchInput, vector: tuple[float, ...] | None) -> SearchResults:
        raise psycopg.OperationalError("PRIVATE_SQL_CANARY")

    with monkeypatch.context() as patch:
        patch.setattr(reader, "search", fail)
        for _ in range(2):
            response = await client.post("/api/v1/search", json={"query": "PRIVATE_QUERY_CANARY"})
            assert response.status_code == 503
    admitted = asyncio.Event()

    async def blocked(query: str, deadline: float) -> Vector:
        admitted.set()
        await asyncio.Future[None]()
        raise AssertionError("cancelled_model_returned")

    with monkeypatch.context() as patch:
        patch.setattr(embeddings, "embed", blocked)
        pending = asyncio.create_task(
            client.post("/api/v1/search", json={"query": "PRIVATE_QUERY_CANARY"})
        )
        await asyncio.wait_for(admitted.wait(), 2)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert (await client.get("/api/v1/news")).status_code == 200
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err
    assert token not in output.out + output.err


async def test_equivalent_cache_arguments_and_model_errors_remain_private(
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from newsloom_core.model_transport import ModelFailure

    client, reader, embeddings, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    monkeypatch.setattr(logging.getLogger(), "handlers", [SafeHandler()])
    for query, tags in (
        ("  PRIVATE_QUERY_CANARY  ", ["AI", "Gateway"]),
        ("PRIVATE_QUERY_CANARY", ["gateway", "ai"]),
    ):
        assert (
            await client.post("/api/v1/search", json={"query": query, "tags": tags})
        ).status_code == 200
    assert len(embeddings.calls) == 1
    assert reader.api_observations[-1][2] == "hit"

    async def fail(query: str, deadline: float) -> Vector:
        logging.getLogger("httpx").warning("PRIVATE_DEPENDENCY_CANARY")
        raise ModelFailure("model_throttled")

    monkeypatch.setattr(embeddings, "embed", fail)
    for _ in range(2):
        response = await client.post(
            "/api/v1/search", json={"query": "different PRIVATE_QUERY_CANARY"}
        )
        assert response.status_code == 503
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err


async def test_mixed_mcp_api_capacity_is_shared_and_released(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, embeddings, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    admitted = 0
    ready = asyncio.Event()

    async def blocked(query: str, deadline: float) -> Vector:
        nonlocal admitted
        admitted += 1
        if admitted == 4:
            ready.set()
        await asyncio.Future[None]()
        raise AssertionError("blocked_embedding_returned")

    monkeypatch.setattr(embeddings, "embed", blocked)
    tasks = [
        asyncio.create_task(client.post("/api/v1/search", json={"query": f"fixture {i}"}))
        for i in range(3)
    ]
    tasks.append(
        asyncio.create_task(
            client.post(
                "/mcp",
                json=request(
                    "tools/call",
                    {"name": "search_news", "arguments": {"query": "fixture MCP"}},
                ),
            )
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), 3)
        assert (await client.get("/api/v1/news")).status_code == 429
        assert admitted == 4
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert (await client.get("/api/v1/news")).status_code == 200


async def test_keys_unavailable_duplicate_auth_and_preflight_never_reach_cache(
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, reader, _, token, verifier, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token

    async def unavailable(value: str) -> None:
        raise TrustedKeysFailure("trusted_keys_unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(verifier, "verify_claims", unavailable)
        assert (await client.get("/api/v1/news")).status_code == 503
        assert (
            await client.options(
                "/api/v1/news",
                headers={
                    "Origin": "https://vscode.dev",
                    "Access-Control-Request-Method": "GET",
                },
            )
        ).status_code == 204
    client.headers.pop("Authorization")
    assert (
        await client.get(
            "/api/v1/news",
            headers=[
                ("Authorization", "Bearer " + token),
                ("Authorization", "Bearer " + token),
            ],
        )
    ).status_code == 401
    assert not reader.calls


async def test_deadline_and_oversized_results_never_become_cached_successes(
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, reader, _, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    original = asyncio.timeout

    async def blocked(*args: object) -> object:
        await asyncio.Future[None]()
        raise AssertionError("blocked_query_returned")

    with monkeypatch.context() as patch:
        patch.setattr(
            "newsloom_mcp.http_api.asyncio.timeout",
            lambda seconds: original(0.02 if seconds == 90 else seconds),
        )
        patch.setattr(reader, "browse", blocked)
        assert (await client.get("/api/v1/news")).status_code == 504
    reader.item = reader.item.model_copy(update={"summary": "x" * (1024 * 1024)})
    assert (await client.get("/api/v1/news")).status_code == 503
    reader.item = reader.item.model_copy(update={"summary": "authored"})
    assert (await client.get("/api/v1/news")).status_code == 200


async def test_real_disconnect_cancels_work_and_disabled_api_allocates_no_cache(
    endpoint: Endpoint,
) -> None:
    _, reader, embeddings, token, verifier, _ = endpoint

    @asynccontextmanager
    async def repositories() -> AsyncIterator[NewsRepository]:
        yield reader

    async def ready() -> bool:
        return True

    async def unused(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("api_request_reached_mcp")

    semaphore = asyncio.Semaphore(4)
    services = Services(repositories, embeddings, ready)
    app = NewsApi(unused, services, verifier, semaphore, True, ("newsloom.test",), ())
    disabled = NewsApi(unused, services, verifier, semaphore, False, ("newsloom.test",), ())
    assert disabled.cache is None
    messages: asyncio.Queue[Message] = asyncio.Queue()
    await messages.put({"type": "http.request", "body": b"", "more_body": False})
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/news",
        "raw_path": b"/api/v1/news",
        "query_string": b"",
        "scheme": "https",
        "headers": [(b"host", b"newsloom.test"), (b"authorization", ("Bearer " + token).encode())],
        "server": ("newsloom.test", 443),
    }
    await disabled(scope, messages.get, send)
    assert sent[0]["status"] == 404
    entered = asyncio.Event()
    original = reader.browse

    async def blocked(args: SearchInput, after: object) -> object:
        entered.set()
        await asyncio.Future[None]()
        raise AssertionError("blocked_read_returned")

    # Assigning through a scoped monkeypatch preserves the fixture's typed method.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(reader, "browse", blocked)
        task = asyncio.create_task(app(scope, messages.get, send))
        await asyncio.wait_for(entered.wait(), 2)
        await messages.put({"type": "http.disconnect"})
        with pytest.raises(asyncio.CancelledError):
            await task
    assert reader.browse == original
    assert semaphore._value == 4 and app.cache is not None and not app.cache.entries


async def test_forged_headers_and_no_scope_cannot_reuse_results(endpoint: Endpoint) -> None:
    client, reader, _, token, _, key = endpoint
    claims = jwt.decode(token, options={"verify_signature": False})
    for header in (
        {"kid": "unknown"},
        {"kid": "local-test-key", "jku": "https://attacker.test/keys"},
        {"kid": "local-test-key", "x5u": "https://attacker.test/key"},
    ):
        bad = jwt.encode(claims, key, algorithm="RS256", headers=header)
        assert (
            await client.get("/api/v1/news", headers={"Authorization": "Bearer " + bad})
        ).status_code == 401
    assert (
        await client.get(
            "/api/v1/news",
            headers={
                "Authorization": "Bearer "
                + jwt.encode(claims, "authored-not-a-real-secret-long-enough", algorithm="HS256"),
            },
        )
    ).status_code == 401
    client.headers["Authorization"] = "Bearer " + token
    assert (
        await client.get(
            "/api/v1/news",
            headers=[
                ("Origin", "https://vscode.dev"),
                ("Origin", "https://vscode.dev"),
            ],
        )
    ).status_code == 403
    assert not reader.calls


async def test_404_is_not_cached_and_empty_collections_are_cached(
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from newsloom_mcp.http_models import Position
    from newsloom_mcp.models import DetailInput, ItemResult, NewsResults

    client, reader, _, token, _, _ = endpoint
    client.headers["Authorization"] = "Bearer " + token
    calls = 0

    async def absent(args: DetailInput) -> ItemResult:
        nonlocal calls
        calls += 1
        return ItemResult(found=False, item=None)

    monkeypatch.setattr(reader, "detail", absent)
    missing = uuid4()
    for _ in range(2):
        assert (await client.get(f"/api/v1/news/{missing}")).status_code == 404
    assert calls == 2

    async def empty(args: SearchInput, after: Position | None) -> NewsResults:
        nonlocal calls
        calls += 1
        return NewsResults(items=())

    monkeypatch.setattr(reader, "browse", empty)
    for _ in range(2):
        response = await client.get("/api/v1/news")
        assert response.status_code == 200 and response.json()["items"] == []
    assert calls == 3
