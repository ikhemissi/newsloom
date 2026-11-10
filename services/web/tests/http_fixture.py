"""Loopback-only real HTTP API contracts with authored data and no cloud credentials."""

import asyncio
import json
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID, uuid4

import httpx
import uvicorn
from newsloom_core.categories import Category
from newsloom_core.model_transport import Vector
from newsloom_mcp.app import Services, create_app
from newsloom_mcp.auth import Claims, EntraVerifier
from newsloom_mcp.http_models import Position
from newsloom_mcp.models import (
    CategoryInfo,
    DetailInput,
    ItemResult,
    NewsDetail,
    NewsItem,
    NewsResults,
    RankedItem,
    RecentInput,
    SearchInput,
    SearchResults,
    SourceInfo,
    SourcesResult,
)
from newsloom_mcp.radar import (
    Card,
    CardInput,
    Product,
    ProductDetail,
    Radar,
    StackEntry,
    rank,
)
from newsloom_mcp.repository import NewsRepository

ITEM = NewsItem(
    id=uuid4(),
    title="Authored SDK result",
    summary="Authored summary.",
    source="fixture-source",
    category=Category.AGENTS_APPLICATIONS,
    tags=("ai",),
    published_at=datetime(2026, 11, 1, 8, tzinfo=UTC),
    url="https://publisher.test/article",
)
CLIENT = uuid4()


class Reader:
    async def recent(self, args: RecentInput) -> NewsResults:
        return NewsResults(items=(ITEM,))

    async def browse(self, args: SearchInput, after: Position | None) -> NewsResults:
        return NewsResults(items=() if after else tuple(await self.eligible(args)))

    async def eligible(self, args: SearchInput) -> list[NewsItem]:
        if (
            (args.source is not None and args.source != ITEM.source)
            or (args.category is not None and args.category != ITEM.category)
            or (args.from_ is not None and ITEM.published_at < args.from_)
            or (args.to is not None and ITEM.published_at >= args.to)
        ):
            return []
        return [ITEM]

    async def search(self, args: SearchInput, vector: tuple[float, ...] | None) -> SearchResults:
        items = [] if args.query == "empty" else await self.eligible(args)
        return SearchResults(
            items=tuple(RankedItem(**item.model_dump(), similarity=0.9) for item in items)
        )

    async def detail(self, args: DetailInput) -> ItemResult:
        item = (
            NewsDetail(
                **ITEM.model_dump(),
                author="Authored",
                date_origin="published",
                publisher_categories=("Authored",),
            )
            if args.id == ITEM.id
            else None
        )
        return ItemResult(found=item is not None, item=item)

    async def sources(self) -> SourcesResult:
        return SourcesResult(
            sources=(SourceInfo(id=ITEM.source, categories=(ITEM.category,)),),
            categories=(CategoryInfo(id=ITEM.category, label="Agents and applications"),),
        )


def product(name: str, vendor: str) -> Product:
    return Product(id=uuid4(), name=name, vendor=vendor, vendor_id=uuid4())


def card(statement: str, **change: object) -> Card:
    values: dict[str, object] = {
        "id": uuid4(),
        "news_id": uuid4(),
        "title": "Authored radar item",
        "url": "https://publisher.test/radar",
        "source": "fixture-source",
        "published_at": datetime(2026, 11, 7, 10, 0, 0, 123456, tzinfo=UTC),
        "article_kind": "announcement",
        "statement": statement,
        "status": "ga",
        "effective_date": date(2026, 11, 2),
        "deadline": None,
        "products": (product("Widget", "Acme"),),
        "tier": "worth_knowing",
        "reason": "Authored reason.",
        "capability": "agent tools",
    }
    return Card.model_validate({**values, **change})


# Edge cases the browser must accept: a multi-vendor card, a real group, five
# products, untriaged fields, deadlines and a snoozed card.
CARDS = [
    card("Security fix.", tier="act_now", article_kind="security", deadline=date(2026, 11, 30)),
    card(
        "Router fix.",
        capability="model routing",
        products=(product("Proxy", "LiteLLM"), product("Bedrock", "AWS")),
    ),
    card("Tool A.", products=(product("Gateway", "AWS"),)),
    card("Tool B.", products=tuple(product(f"Tool {n}", f"Vendor {n}") for n in range(5))),
    card("Untriaged.", reason=None, capability=None, effective_date=None),
    card("Later.", tier="later", capability="other"),
    card("Snoozed.", state="snoozed"),
]
FOLLOWED = StackEntry(id=uuid4(), name="Acme", kind="vendor", vendor=None)


class Radars:
    def __init__(self) -> None:
        self.followed: tuple[StackEntry, ...] = ()

    async def radar(self, reader: str, window: Literal[7, 30], now: datetime) -> Radar:
        return rank(CARDS, window, bool(self.followed), datetime(2026, 11, 8, tzinfo=UTC))

    async def set_card(self, reader: str, announcement: UUID, value: CardInput) -> bool:
        return announcement == CARDS[0].id

    async def stack(self, reader: str) -> tuple[StackEntry, ...]:
        return self.followed

    async def set_stack(self, reader: str, ids: tuple[UUID, ...]) -> tuple[StackEntry, ...]:
        self.followed = (FOLLOWED,) if FOLLOWED.id in ids else ()
        return self.followed

    async def search(self, query: str) -> tuple[StackEntry, ...]:
        return (FOLLOWED,)

    async def product(self, identifier: UUID) -> ProductDetail | None:
        return (
            ProductDetail(
                id=identifier,
                name="Widget",
                vendor="Acme",
                aliases=("acme widget",),
                related=(),
                timeline=tuple(CARDS[:2]),
            )
            if identifier == CARDS[0].products[0].id
            else None
        )


class Embeddings:
    async def embed(self, query: str, deadline: float) -> Vector:
        if query == "delay":
            await asyncio.sleep(5)
        return Vector(values=(0.1,) * 1536)


class AuthoredVerifier(EntraVerifier):
    async def verify_claims(self, token: str) -> Claims | None:
        if token != "fixture-news-token":
            return None
        return Claims(
            iss=self.issuer,
            aud=self.audience,
            tid=self.tenant,
            sub="authored-subject",
            azp=CLIENT,
            exp=int(time.time()) + 600,
            nbf=0,
            ver="2.0",
            scp="news.read",
            oid=UUID(int=9),
        )


async def serve(listener: socket.socket) -> None:
    @asynccontextmanager
    async def repositories() -> AsyncIterator[NewsRepository]:
        yield Reader()

    async def ready() -> bool:
        return True

    store = Radars()

    @asynccontextmanager
    async def radar() -> AsyncIterator[Radars]:
        yield store

    async with httpx.AsyncClient() as client:
        port = listener.getsockname()[1]
        app = create_app(
            Services(repositories, Embeddings(), ready, radar=radar),
            AuthoredVerifier(client, uuid4(), uuid4()),
            f"http://127.0.0.1:{port}/mcp",
            [f"127.0.0.1:{port}"],
            [],
            news_api_enabled=True,
        )
        await uvicorn.Server(
            uvicorn.Config(
                app,
                log_config=None,
                log_level="critical",
                access_log=False,
            )
        ).serve(sockets=[listener])


if __name__ == "__main__":
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        print(json.dumps({"port": listener.getsockname()[1]}), flush=True)
        asyncio.run(serve(listener))
