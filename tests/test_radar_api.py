import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from newsloom_mcp.app import Services, create_app
from newsloom_mcp.auth import EntraVerifier
from newsloom_mcp.feedback import reader_hash
from newsloom_mcp.radar import CardInput, ProductDetail, Radar, StackEntry, rank
from newsloom_mcp.repository import NewsRepository
from test_feedback_api import _Recorder
from test_mcp_auth import jwks
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Embeddings, Reader

KNOWN = UUID(int=11)


class Store:
    def __init__(self) -> None:
        self.stacks: dict[str, tuple[UUID, ...]] = {}
        self.cards: dict[tuple[str, UUID], str | None] = {}
        self.windows: list[int] = []

    async def radar(self, reader: str, window: Literal[7, 30], now: datetime) -> Radar:
        self.windows.append(window)
        return rank([], window, reader in self.stacks, now)

    async def set_card(self, reader: str, announcement: UUID, value: CardInput) -> bool:
        if announcement != KNOWN:
            return False
        self.cards[(reader, announcement)] = value.state
        return True

    async def stack(self, reader: str) -> tuple[StackEntry, ...]:
        return tuple(
            StackEntry(id=entity, name=f"Entity {entity.int}", kind="vendor", vendor=None)
            for entity in self.stacks.get(reader, ())
        )

    async def set_stack(self, reader: str, ids: tuple[UUID, ...]) -> tuple[StackEntry, ...]:
        self.stacks[reader] = ids
        return await self.stack(reader)

    async def search(self, query: str) -> tuple[StackEntry, ...]:
        return (StackEntry(id=KNOWN, name=query, kind="product", vendor="Acme"),)

    async def product(self, identifier: UUID) -> ProductDetail | None:
        if identifier != KNOWN:
            return None
        return ProductDetail(
            id=KNOWN, name="Widget", vendor="Acme", aliases=("widget",), related=(), timeline=()
        )


Client = tuple[httpx.AsyncClient, Store, dict[str, object], rsa.RSAPrivateKey]


@pytest.fixture
async def api(signing_key: rsa.RSAPrivateKey) -> AsyncIterator[Client]:
    store = Store()
    tenant, audience = uuid4(), uuid4()

    async def ready() -> bool:
        return True

    @asynccontextmanager
    async def repository() -> AsyncIterator[NewsRepository]:
        yield Reader()

    @asynccontextmanager
    async def radar() -> AsyncIterator[Store]:
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
            "oid": str(uuid4()),
            "azp": str(uuid4()),
            "exp": int(time.time()) + 600,
            "nbf": int(time.time()) - 1,
            "ver": "2.0",
            "scp": "news.read",
        }
        app = create_app(
            Services(repository, Embeddings(), ready, radar=radar),
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
                yield client, store, claims, signing_key
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)


def bearer(api: Client, drop: str = "") -> dict[str, str]:
    _, _, claims, key = api
    token = jwt.encode(
        {k: v for k, v in claims.items() if k != drop},
        key,
        algorithm="RS256",
        headers={"kid": "local-test-key"},
    )
    return {"Authorization": "Bearer " + token}


async def test_reader_state_is_pseudonymous_and_isolated(api: Client) -> None:
    client, store, claims, _ = api
    entity = str(UUID(int=5))
    saved = await client.put("/api/v1/me/stack", json={"ids": [entity]}, headers=bearer(api))
    assert saved.status_code == 200 and saved.json()["items"][0]["id"] == entity
    reader = reader_hash(UUID(str(claims["tid"])), UUID(str(claims["oid"])))
    assert list(store.stacks) == [reader] and str(claims["oid"]) not in reader
    listed = await client.get("/api/v1/me/stack", headers=bearer(api))
    assert listed.json()["items"][0]["id"] == entity
    assert listed.headers["Cache-Control"] == "no-store"
    done = await client.put(
        f"/api/v1/me/cards/{KNOWN}", json={"state": "done"}, headers=bearer(api)
    )
    assert done.status_code == 200 and done.json() == {"state": "done"}
    assert store.cards == {(reader, KNOWN): "done"}
    unknown = await client.put(
        f"/api/v1/me/cards/{uuid4()}", json={"state": "snoozed"}, headers=bearer(api)
    )
    assert unknown.status_code == 404
    radar = await client.get("/api/v1/radar?window=30", headers=bearer(api))
    assert radar.status_code == 200 and set(radar.json()["tiers"]) == {
        "act_now",
        "worth_knowing",
        "later",
    }
    assert store.windows == [30]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/radar?window=14", None),
        ("GET", "/api/v1/radar?other=1", None),
        ("PUT", "/api/v1/me/stack", {"ids": [str(uuid4()) for _ in range(51)]}),
        ("PUT", "/api/v1/me/stack", {"ids": ["not-a-uuid"]}),
        ("PUT", f"/api/v1/me/cards/{KNOWN}", {"state": "hidden"}),
        ("PUT", "/api/v1/me/cards/not-a-uuid", {"state": "done"}),
        ("GET", "/api/v1/products?query=a", None),
        ("GET", "/api/v1/products/not-a-uuid", None),
    ],
)
async def test_invalid_input_is_rejected(api: Client, method: str, path: str, body: object) -> None:
    client, store, _, _ = api
    response = await client.request(method, path, json=body, headers=bearer(api))
    assert response.status_code == 400 and not store.stacks and not store.cards


async def test_methods_media_types_and_object_id(api: Client) -> None:
    client, _, _, _ = api
    assert (
        await client.post("/api/v1/me/stack", json={"ids": []}, headers=bearer(api))
    ).status_code == 405
    raw = await client.put(
        "/api/v1/me/stack",
        content=b'{"ids":[]}',
        headers={**bearer(api), "Content-Type": "text/plain"},
    )
    assert raw.status_code == 415
    for path in ("/api/v1/radar", "/api/v1/me/stack"):
        assert (await client.get(path, headers=bearer(api, drop="oid"))).status_code == 403
    catalogue = await client.get("/api/v1/products?query=wid", headers=bearer(api, drop="oid"))
    assert catalogue.status_code == 200 and catalogue.json()["items"][0]["vendor"] == "Acme"
    product = await client.get(f"/api/v1/products/{KNOWN}", headers=bearer(api))
    assert product.json()["aliases"] == ["widget"]
    assert (await client.get(f"/api/v1/products/{uuid4()}", headers=bearer(api))).status_code == 404


async def test_browser_preflight_allows_the_write_methods(api: Client) -> None:
    client, _, _, _ = api
    for path, method in (
        ("/api/v1/me/stack", "PUT"),
        (f"/api/v1/me/cards/{KNOWN}", "PUT"),
        ("/api/v1/radar", "GET"),
    ):
        response = await client.options(
            path,
            headers={
                "Origin": "https://web.test",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 204, path
        assert response.headers["Access-Control-Allow-Origin"] == "https://web.test"


def test_every_radar_route_is_a_valid_telemetry_category() -> None:
    from newsloom_mcp.http_api import RADAR_ROUTES
    from newsloom_mcp.telemetry import API_ROUTES

    assert RADAR_ROUTES <= API_ROUTES


async def test_anonymous_radar_is_401_through_production_telemetry(
    signing_key: rsa.RSAPrivateKey,
) -> None:
    from newsloom_mcp.telemetry import Telemetry

    recorded: list[str] = []

    def observe(route: str, outcome: str, cache: str, elapsed: float) -> None:
        Telemetry.record_api(_Recorder(recorded), route, outcome, cache, elapsed)  # type: ignore[arg-type]

    async def ready() -> bool:
        return True

    @asynccontextmanager
    async def repository() -> AsyncIterator[NewsRepository]:
        yield Reader()

    @asynccontextmanager
    async def radar() -> AsyncIterator[Store]:
        yield Store()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=jwks(signing_key)))
    ) as trusted_keys:
        app = create_app(
            Services(repository, Embeddings(), ready, observe_api=observe, radar=radar),
            EntraVerifier(trusted_keys, uuid4(), uuid4()),
            "https://newsloom.test/mcp",
            ["newsloom.test"],
            ["https://web.test"],
            news_api_enabled=True,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://newsloom.test"
        ) as client:
            calls = (
                ("GET", "/api/v1/radar"),
                ("GET", "/api/v1/me/stack"),
                ("PUT", "/api/v1/me/stack"),
                ("PUT", f"/api/v1/me/cards/{KNOWN}"),
                ("GET", "/api/v1/products"),
                ("GET", f"/api/v1/products/{KNOWN}"),
            )
            for method, path in calls:
                assert (await client.request(method, path)).status_code == 401
    assert recorded == ["radar", "stack", "stack_update", "card_state", "products", "product"]


def test_rank_matches_the_browser_rules() -> None:
    from datetime import date

    from newsloom_mcp.radar import Card, Product

    def card(name: str, **change: object) -> Card:
        values: dict[str, object] = {
            "id": uuid4(),
            "news_id": uuid4(),
            "title": name,
            "url": "https://publisher.test/" + name,
            "source": "fixture",
            "published_at": datetime(2026, 11, 7, tzinfo=UTC),
            "article_kind": "announcement",
            "statement": name,
            "status": "ga",
            "effective_date": None,
            "deadline": None,
            "products": [
                Product(
                    id=uuid4(),
                    name=name,
                    vendor=str(change.pop("vendor", "Acme")),
                    vendor_id=uuid4(),
                )
            ],
            "tier": "worth_knowing",
            "reason": None,
            "capability": None,
        }
        return Card.model_validate({**values, **change})

    now = datetime(2026, 11, 8, tzinfo=UTC)
    cards = [
        card("a", tier="act_now"),
        card("b", tier="act_now", in_stack=True),
        card("c", tier="act_now", article_kind="security"),
        card("d", capability="browser automation"),
        card("e", capability="browser automation", vendor="Other"),
        card("f", deadline=date(2026, 12, 1)),
        card("g", tier="later", deadline=date(2026, 11, 20)),
        card("h", state="done"),
    ]
    result = rank(cards, 7, True, now)

    def names(tier: Literal["act_now", "worth_knowing", "later"]) -> list[str]:
        return [
            c.statement
            for e in result.tiers[tier]
            for c in (e.cards if e.kind == "group" else (e.card,))
        ]

    assert names("act_now") == ["b", "c"]
    assert names("worth_knowing") == ["f", "a", "d", "e"]
    assert [e.kind for e in result.tiers["worth_knowing"]] == ["card", "card", "group"]
    assert [c.statement for c in result.deadlines] == ["f"]
    assert [c.statement for c in result.hidden] == ["h"]
    unpersonalised = rank(cards, 7, False, now)
    # Without a stack every act-now item stays; stack membership still sorts first.
    assert [e.card.statement for e in unpersonalised.tiers["act_now"] if e.kind == "card"] == [
        "b",
        "a",
        "c",
    ]


def test_one_multi_vendor_card_is_never_a_group() -> None:
    from newsloom_mcp.radar import Card, Product

    lone = Card.model_validate(
        {
            "id": uuid4(),
            "news_id": uuid4(),
            "title": "t",
            "url": "https://publisher.test/t",
            "source": "s",
            "published_at": datetime(2026, 11, 7, tzinfo=UTC),
            "article_kind": "announcement",
            "statement": "LiteLLM fixed Bedrock routing.",
            "status": "updated",
            "effective_date": None,
            "deadline": None,
            "products": [
                Product(id=uuid4(), name="Proxy", vendor="LiteLLM", vendor_id=uuid4()),
                Product(id=uuid4(), name="Bedrock", vendor="AWS", vendor_id=uuid4()),
            ],
            "tier": "worth_knowing",
            "reason": None,
            "capability": "model routing",
        }
    )
    entries = rank([lone], 7, False, datetime(2026, 11, 8, tzinfo=UTC)).tiers["worth_knowing"]
    assert [entry.kind for entry in entries] == ["card"]
