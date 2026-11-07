import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from newsloom_mcp.app import Services, create_app
from newsloom_mcp.auth import EntraVerifier
from newsloom_mcp.feedback import FeedbackInput, ReviewItem, ReviewQuery, Vote, reader_hash
from newsloom_mcp.repository import NewsRepository
from test_mcp_auth import jwks
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Embeddings, Reader

VERSION = str(UUID(int=7))
SNAPSHOT = {
    "question": "What changed in agent gateways?",
    "answer": {"outcome": "supported", "claims": [{"text": "A gateway changed."}]},
    "citations": [{"number": 1, "url": "https://example.test/a"}],
    "filters": {"sources": ["example"]},
}


class Store:
    def __init__(self) -> None:
        self.rows: list[tuple[str, FeedbackInput]] = []
        self.known = {VERSION}

    async def record(self, reader: str, entry: FeedbackInput) -> bool:
        if entry.target_type == "briefing" and entry.target_ref not in self.known:
            return False
        self.rows.append((reader, entry))
        return True

    async def mine(self, reader: str, target_type: str, target_ref: str) -> Vote | None:
        for row_reader, entry in reversed(self.rows):
            if (row_reader, entry.target_type, entry.target_ref) == (
                reader,
                target_type,
                target_ref,
            ):
                return Vote(rating=entry.rating, comment=entry.comment)
        return None

    async def review(self, query: ReviewQuery) -> list[ReviewItem]:
        return [
            ReviewItem(
                created_at=datetime.now(UTC),
                target_type=entry.target_type,
                target_ref=entry.target_ref,
                rating=entry.rating,
                comment=entry.comment,
                snapshot=entry.snapshot.model_dump(mode="json") if entry.snapshot else None,
            )
            for _, entry in self.rows
            if query.rating in (None, entry.rating)
        ]


Client = tuple[httpx.AsyncClient, Store, dict[str, object], rsa.RSAPrivateKey]


@pytest.fixture
async def api(signing_key: rsa.RSAPrivateKey) -> AsyncIterator[Client]:
    store = Store()
    tenant, audience, oid = uuid4(), uuid4(), uuid4()
    reviewer = UUID(int=42)

    async def ready() -> bool:
        return True

    @asynccontextmanager
    async def repository() -> AsyncIterator[NewsRepository]:
        yield Reader()

    @asynccontextmanager
    async def feedback() -> AsyncIterator[Store]:
        yield store

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=jwks(signing_key)))
    ) as trusted_keys:
        verifier = EntraVerifier(trusted_keys, tenant, audience)
        claims: dict[str, object] = {
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
        }
        app = create_app(
            Services(
                repository,
                Embeddings(),
                ready,
                feedback=feedback,
                feedback_reviewers=frozenset({reviewer}),
            ),
            verifier,
            "https://newsloom.test/mcp",
            ["newsloom.test"],
            ["https://vscode.dev"],
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
                yield client, store, claims, signing_key
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)


def bearer(api: Client, **changes: object) -> dict[str, str]:
    _, _, claims, key = api
    token = jwt.encode(
        {**claims, **changes}, key, algorithm="RS256", headers={"kid": "local-test-key"}
    )
    return {"Authorization": "Bearer " + token}


async def test_vote_is_recorded_pseudonymously_and_latest_wins(api: Client) -> None:
    client, store, claims, _ = api
    body = {
        "target_type": "briefing",
        "target_ref": VERSION,
        "rating": "down",
        "comment": "COMMENT_CANARY too generic",
    }
    response = await client.post("/api/v1/feedback", json=body, headers=bearer(api))
    assert response.status_code == 201 and response.headers["Cache-Control"] == "no-store"
    expected = reader_hash(UUID(str(claims["tid"])), UUID(str(claims["oid"])))
    assert store.rows[0][0] == expected and str(claims["oid"]) not in expected
    await client.post(
        "/api/v1/feedback", json={**body, "rating": "up", "comment": None}, headers=bearer(api)
    )
    mine = await client.get(
        "/api/v1/feedback/mine",
        params={"target_type": "briefing", "target_ref": VERSION},
        headers=bearer(api),
    )
    assert mine.json() == {"vote": {"rating": "up", "comment": None}}


async def test_research_vote_requires_bounded_snapshot(api: Client) -> None:
    client, store, _, _ = api
    base = {"target_type": "research", "target_ref": "task-1", "rating": "down"}
    assert (
        await client.post("/api/v1/feedback", json=base, headers=bearer(api))
    ).status_code == 400
    ok = await client.post(
        "/api/v1/feedback", json={**base, "snapshot": SNAPSHOT}, headers=bearer(api)
    )
    assert ok.status_code == 201 and store.rows[-1][1].snapshot is not None
    huge = {**SNAPSHOT, "question": "x" * 8000, "answer": {"text": "y" * 45000}}
    assert (
        await client.post("/api/v1/feedback", json={**base, "snapshot": huge}, headers=bearer(api))
    ).status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"target_type": "briefing", "target_ref": str(uuid4()), "rating": "down"},
        {"target_type": "briefing", "target_ref": "not-a-uuid", "rating": "down"},
        {"target_type": "briefing", "target_ref": VERSION, "rating": "meh"},
        {"target_type": "briefing", "target_ref": VERSION, "rating": "up", "comment": "x" * 1001},
        {"target_type": "briefing", "target_ref": VERSION, "rating": "up", "extra": 1},
    ],
)
async def test_invalid_or_unknown_targets_store_nothing(
    api: Client, body: dict[str, object]
) -> None:
    client, store, _, _ = api
    response = await client.post("/api/v1/feedback", json=body, headers=bearer(api))
    assert response.status_code == 400 and not store.rows


@pytest.mark.parametrize("changes", [{"scp": "news.agent"}, {"oid": None}, {"scp": ""}])
async def test_read_scope_and_object_id_are_required(
    api: Client, changes: dict[str, object]
) -> None:
    client, store, _, _ = api
    body = {"target_type": "briefing", "target_ref": VERSION, "rating": "up"}
    claims = {k: v for k, v in changes.items() if v is not None}
    headers = bearer(api, **claims)
    if changes.get("oid", "") is None:
        _, _, base, key = api
        token = jwt.encode(
            {k: v for k, v in base.items() if k != "oid"},
            key,
            algorithm="RS256",
            headers={"kid": "local-test-key"},
        )
        headers = {"Authorization": "Bearer " + token}
    response = await client.post("/api/v1/feedback", json=body, headers=headers)
    assert response.status_code == 403 and not store.rows
    assert 'scope="news.read"' in response.headers["WWW-Authenticate"]


async def test_review_and_export_require_allowlisted_reviewer(api: Client) -> None:
    client, _, _, _ = api
    body = {"target_type": "briefing", "target_ref": VERSION, "rating": "down", "comment": "bad"}
    await client.post("/api/v1/feedback", json=body, headers=bearer(api))
    for path in ("/api/v1/feedback/review", "/api/v1/feedback/export"):
        assert (await client.get(path, headers=bearer(api))).status_code == 403
    reviewer = bearer(api, oid=str(UUID(int=42)))
    listed = await client.get("/api/v1/feedback/review?rating=down", headers=reviewer)
    assert listed.status_code == 200 and listed.json()["items"][0]["comment"] == "bad"
    exported = await client.get("/api/v1/feedback/export", headers=reviewer)
    assert exported.headers["content-type"].startswith("application/x-ndjson")
    assert exported.text.count("\n") == 1 and "reader" not in exported.text


async def test_feedback_text_is_never_logged(api: Client, caplog: pytest.LogCaptureFixture) -> None:
    client, _, _, _ = api
    caplog.set_level(logging.DEBUG)
    body = {
        "target_type": "research",
        "target_ref": "task-9",
        "rating": "down",
        "comment": "COMMENT_CANARY",
        "snapshot": SNAPSHOT,
    }
    assert (
        await client.post("/api/v1/feedback", json=body, headers=bearer(api))
    ).status_code == 201
    assert "COMMENT_CANARY" not in caplog.text and "agent gateways" not in caplog.text


def test_every_api_route_is_a_valid_telemetry_category() -> None:
    from newsloom_mcp.http_api import FEEDBACK_ROUTES, SCOPES
    from newsloom_mcp.telemetry import API_ROUTES

    routes = {name for name, _ in FEEDBACK_ROUTES.values()} | set(SCOPES)
    assert routes <= API_ROUTES


async def test_anonymous_feedback_is_401_with_production_telemetry_checks(
    signing_key: rsa.RSAPrivateKey,
) -> None:
    from newsloom_mcp.telemetry import Telemetry

    recorded: list[str] = []

    def observe(route: str, outcome: str, cache: str, elapsed: float) -> None:
        # Run the production validation without exporting anything.
        Telemetry.record_api(_Recorder(recorded), route, outcome, cache, elapsed)  # type: ignore[arg-type]

    async def ready() -> bool:
        return True

    @asynccontextmanager
    async def repository() -> AsyncIterator[NewsRepository]:
        yield Reader()

    @asynccontextmanager
    async def feedback() -> AsyncIterator[Store]:
        yield Store()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=jwks(signing_key)))
    ) as trusted_keys:
        app = create_app(
            Services(repository, Embeddings(), ready, observe_api=observe, feedback=feedback),
            EntraVerifier(trusted_keys, uuid4(), uuid4()),
            "https://newsloom.test/mcp",
            ["newsloom.test"],
            ["https://vscode.dev"],
            news_api_enabled=True,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://newsloom.test"
        ) as client:
            for method, path in (
                ("POST", "/api/v1/feedback"),
                ("GET", "/api/v1/feedback/mine"),
                ("GET", "/api/v1/feedback/review"),
                ("GET", "/api/v1/feedback/export"),
            ):
                assert (await client.request(method, path)).status_code == 401
    assert recorded == ["feedback", "feedback_mine", "feedback_review", "feedback_export"]


class _Recorder:
    def __init__(self, recorded: list[str]) -> None:
        self.recorded = recorded
        self.api_calls = self
        self.api_latency = self

    def add(self, value: int, attributes: dict[str, str]) -> None:
        self.recorded.append(attributes["route"])

    def record(self, value: float, attributes: dict[str, str]) -> None:
        return None
