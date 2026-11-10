"""Nightly read snapshot and the read-only stores that serve it while the database sleeps."""

import asyncio
import gzip
import io
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from datetime import datetime, timedelta
from typing import Literal, TypeVar
from uuid import UUID

import httpx
import psycopg
from newsloom_core.briefing import BriefingRead, cutoff_at
from newsloom_core.categories import load_categories
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from newsloom_mcp.briefing import read_briefing
from newsloom_mcp.feedback import FeedbackInput, ReviewItem, ReviewQuery, Vote
from newsloom_mcp.http_models import Position
from newsloom_mcp.models import (
    CategoryInfo,
    DetailInput,
    ItemResult,
    McpFailure,
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
    CARD_COLUMNS,
    CARD_JOINS,
    Card,
    CardInput,
    ProductDetail,
    Radar,
    RadarRepository,
    StackEntry,
    card,
    rank,
)
from newsloom_mcp.repository import PROJECTION

CARD_DAYS = 30
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
BLOB_VERSION = "2023-11-03"
STORAGE_SCOPE = "https://storage.azure.com/.default"
UNREACHABLE = (psycopg.OperationalError, TimeoutError, OSError)
T = TypeVar("T")


class ReadOnly(McpFailure):
    def __init__(self) -> None:
        super().__init__("read_only")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class CardState(Contract):
    state: Literal["done", "snoozed"]
    until: datetime | None


class Snapshot(Contract):
    version: Literal[1] = 1
    as_of: datetime
    items: tuple[NewsDetail, ...]
    cards: tuple[Card, ...]
    products: tuple[ProductDetail, ...]
    stack_entries: tuple[StackEntry, ...]
    stacks: dict[str, tuple[UUID, ...]]
    states: dict[str, dict[UUID, CardState]]
    briefing: BriefingRead | None

    def encode(self) -> bytes:
        return gzip.compress(self.model_dump_json().encode(), mtime=0)

    @classmethod
    def decode(cls, data: bytes) -> Snapshot:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise McpFailure("snapshot_too_large")
        return cls.model_validate_json(raw)


async def build(connection: AsyncConnection[tuple[object, ...]], now: datetime) -> Snapshot:
    """Read everything the read-only stores need; call inside a read-only transaction."""
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            sql.SQL(
                "SELECT {},author,date_origin,publisher_categories,article_kind FROM public.news"
            ).format(PROJECTION)
        )
        rows = await cursor.fetchall()
        await cursor.execute(
            "SELECT a.news_id,a.statement,a.change_type,a.status,a.effective_date,a.deadline,"
            "coalesce(array_agg(e.canonical_name ORDER BY e.canonical_name) "
            "FILTER (WHERE e.id IS NOT NULL),'{}') AS products "
            "FROM public.announcements a "
            "LEFT JOIN public.announcement_entities ae ON ae.announcement_id=a.id "
            "LEFT JOIN public.entities e ON e.id=ae.entity_id "
            "GROUP BY a.id ORDER BY a.news_id,a.ordinal"
        )
        announcements: dict[UUID, list[dict[str, object]]] = defaultdict(list)
        for row in await cursor.fetchall():
            news_id = row.pop("news_id")
            announcements[news_id].append(row)
    items = tuple(
        NewsDetail.model_validate({**row, "announcements": announcements.get(row["id"], [])})
        for row in rows
    )
    cards = tuple(
        card(row)
        for row in await (
            await connection.execute(
                "SELECT "
                + CARD_COLUMNS
                + CARD_JOINS
                + " WHERE n.published_at>=%s GROUP BY a.id,n.id"
                " ORDER BY n.published_at DESC,a.ordinal LIMIT 3000",
                (now - timedelta(days=CARD_DAYS),),
            )
        ).fetchall()
    )
    radar = RadarRepository(connection)
    products = []
    for identifier in sorted({p.id for c in cards for p in c.products}):
        detail = await radar.product(identifier)
        if detail is not None:
            products.append(detail)
    stacks: dict[str, list[UUID]] = defaultdict(list)
    for reader, entity in await (
        await connection.execute("SELECT reader,entity_id FROM public.reader_stack")
    ).fetchall():
        assert isinstance(reader, str) and isinstance(entity, UUID)
        stacks[reader].append(entity)
    followed = sorted({entity for ids in stacks.values() for entity in ids})
    entries: tuple[StackEntry, ...] = ()
    if followed:
        rows_ = await (
            await connection.execute(
                "SELECT e.id,e.canonical_name,e.kind,v.canonical_name FROM public.entities e "
                "LEFT JOIN public.entities v ON v.id=e.vendor_id WHERE e.id=ANY(%s)",
                (followed,),
            )
        ).fetchall()
        entries = tuple(
            StackEntry.model_validate(dict(zip(("id", "name", "kind", "vendor"), row, strict=True)))
            for row in rows_
        )
    states: dict[str, dict[UUID, CardState]] = defaultdict(dict)
    for reader, announcement, state, until in await (
        await connection.execute(
            "SELECT reader,announcement_id,state,snoozed_until FROM public.reader_card_state"
        )
    ).fetchall():
        assert isinstance(reader, str) and isinstance(announcement, UUID)
        states[reader][announcement] = CardState.model_validate({"state": state, "until": until})
    exists = await (
        await connection.execute("SELECT to_regclass('public.briefing_current') IS NOT NULL")
    ).fetchone()
    published = bool(exists and exists[0])
    return Snapshot(
        as_of=now,
        items=items,
        cards=cards,
        products=tuple(products),
        stack_entries=entries,
        stacks={reader: tuple(ids) for reader, ids in stacks.items()},
        states=dict(states),
        briefing=await read_briefing(connection, cutoff_at(now)) if published else None,
    )


def newest_first(item: NewsItem) -> tuple[float, int]:
    return (-item.published_at.timestamp(), item.id.int)


class SnapshotNews:
    """`NewsRepository` over a snapshot: same filters and continuation, no ranking."""

    def __init__(self, snapshot: Snapshot) -> None:
        self.items = sorted(snapshot.items, key=newest_first)
        self.by_id = {item.id: item for item in snapshot.items}

    def matching(self, args: SearchInput) -> list[NewsDetail]:
        return [
            item
            for item in self.items
            if (args.source is None or item.source == args.source)
            and (args.category is None or item.category == args.category)
            and (args.from_ is None or item.published_at >= args.from_)
            and (args.to is None or item.published_at < args.to)
            and set(args.tags) <= set(item.tags)
        ]

    @staticmethod
    def summary(item: NewsItem) -> NewsItem:
        return NewsItem.model_validate(item.model_dump(include=set(NewsItem.model_fields)))

    async def browse(self, args: SearchInput, after: Position | None) -> NewsResults:
        selected = self.matching(args)
        if after is not None:
            selected = [
                item
                for item in selected
                if item.published_at < after.published_at
                or (item.published_at == after.published_at and item.id.int > after.id.int)
            ]
        return NewsResults(items=tuple(self.summary(i) for i in selected[: args.limit + 1]))

    async def recent(self, args: RecentInput) -> NewsResults:
        selected = [i for i in self.items if args.since is None or i.published_at >= args.since]
        return NewsResults(items=tuple(self.summary(i) for i in selected[: args.limit]))

    async def detail(self, args: DetailInput) -> ItemResult:
        item = self.by_id.get(args.id)
        return ItemResult(found=item is not None, item=item)

    async def sources(self) -> SourcesResult:
        categories: dict[str, set[str]] = defaultdict(set)
        for item in self.items:
            categories[item.source].add(item.category)
        sources = tuple(
            SourceInfo.model_validate({"id": source, "categories": sorted(values)})
            for source, values in sorted(categories.items())
        )
        represented = {category for source in sources for category in source.categories}
        return SourcesResult(
            sources=sources,
            categories=tuple(
                CategoryInfo(id=item.id, label=item.label)
                for item in load_categories()
                if item.id in represented
            ),
        )

    async def search(self, args: SearchInput, vector: tuple[float, ...] | None) -> SearchResults:
        if vector is not None or args.query is not None:
            raise ReadOnly()
        return SearchResults(
            items=tuple(
                RankedItem.model_validate({**self.summary(item).model_dump(), "similarity": None})
                for item in self.matching(args)[: args.limit]
            )
        )


class SnapshotRadar:
    """`RadarStore` over a snapshot: personalised reads, no writes."""

    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self.products = {product.id: product for product in snapshot.products}
        self.entries = {entry.id: entry for entry in snapshot.stack_entries}

    async def radar(self, reader: str, window: Literal[7, 30], now: datetime) -> Radar:
        followed = set(self.snapshot.stacks.get(reader, ()))
        states = self.snapshot.states.get(reader, {})
        since = now - timedelta(days=window)
        cards = []
        for item in self.snapshot.cards:
            if item.published_at < since:
                continue
            saved = states.get(item.id)
            active = saved is not None and (
                saved.state == "done" or (saved.until is not None and saved.until > now)
            )
            cards.append(
                item.model_copy(
                    update={
                        "state": saved.state if active and saved else None,
                        "in_stack": any(
                            p.id in followed or p.vendor_id in followed for p in item.products
                        ),
                    }
                )
            )
        return rank(cards, window, bool(followed), now)

    async def set_card(self, reader: str, announcement: UUID, value: CardInput) -> bool:
        raise ReadOnly()

    async def stack(self, reader: str) -> tuple[StackEntry, ...]:
        chosen = [
            self.entries[i] for i in self.snapshot.stacks.get(reader, ()) if i in self.entries
        ]
        return tuple(sorted(chosen, key=lambda entry: (entry.kind == "product", entry.name)))

    async def set_stack(self, reader: str, ids: tuple[UUID, ...]) -> tuple[StackEntry, ...]:
        raise ReadOnly()

    async def search(self, query: str) -> tuple[StackEntry, ...]:
        raise ReadOnly()

    async def product(self, identifier: UUID) -> ProductDetail | None:
        return self.products.get(identifier)


class SnapshotFeedback:
    async def record(self, reader: str, entry: FeedbackInput) -> bool:
        raise ReadOnly()

    async def mine(self, reader: str, target_type: str, target_ref: str) -> Vote | None:
        raise ReadOnly()

    async def review(self, query: ReviewQuery) -> list[ReviewItem]:
        raise ReadOnly()


def snapshot_briefing(snapshot: Snapshot) -> BriefingRead:
    if snapshot.briefing is None:
        raise ReadOnly()
    return snapshot.briefing


class SnapshotBlob:
    """One overwritten blob read and written with the workload's Entra token."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        token: Callable[[], Awaitable[str]],
        url: str,
    ) -> None:
        self.client, self.token, self.url = client, token, url

    async def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.token()}", "x-ms-version": BLOB_VERSION}

    async def put(self, data: bytes) -> None:
        headers = await self.headers()
        headers |= {"x-ms-blob-type": "BlockBlob", "Content-Type": "application/gzip"}
        response = await self.client.put(self.url, content=data, headers=headers, timeout=120)
        if response.status_code != 201:
            raise McpFailure("snapshot_upload_failed")

    async def get(self, etag: str | None) -> tuple[bytes, str] | None:
        """Returns the blob and its ETag, or None when it is unchanged."""
        headers = await self.headers()
        if etag:
            headers["If-None-Match"] = etag
        async with self.client.stream("GET", self.url, headers=headers, timeout=60) as response:
            if response.status_code == 304:
                return None
            if response.status_code != 200:
                raise McpFailure("snapshot_unavailable")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_SNAPSHOT_BYTES:
                    raise McpFailure("snapshot_too_large")
            return bytes(body), response.headers.get("etag", "")


class Fallback:
    """Remembers that the database is unreachable and serves the latest snapshot meanwhile."""

    REMEMBER = 300.0
    RECHECK = 600.0

    def __init__(
        self, blob: SnapshotBlob | None, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.blob, self.clock = blob, clock
        self.down_until = 0.0
        self.current: Snapshot | None = None
        self.etag: str | None = None
        self.checked = -self.RECHECK
        self.lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.blob is not None

    def offline(self) -> bool:
        return self.enabled and self.clock() < self.down_until

    def failed(self) -> None:
        self.down_until = self.clock() + self.REMEMBER

    def as_of(self) -> datetime | None:
        return self.current.as_of if self.offline() and self.current else None

    async def snapshot(self) -> Snapshot:
        async with self.lock:
            if self.blob is not None and (
                self.current is None or self.clock() - self.checked >= self.RECHECK
            ):
                try:
                    fetched = await self.blob.get(self.etag if self.current else None)
                    if fetched is not None:
                        self.current, self.etag = Snapshot.decode(fetched[0]), fetched[1]
                    self.checked = self.clock()
                except McpFailure, httpx.HTTPError, ValueError, OSError, EOFError:
                    if self.current is None:
                        raise McpFailure("snapshot_unavailable") from None
            if self.current is None:
                raise McpFailure("snapshot_unavailable")
            return self.current

    async def loaded(self) -> bool:
        try:
            await self.snapshot()
        except McpFailure:
            return False
        return True

    @asynccontextmanager
    async def database(
        self, connect: Callable[[], AbstractAsyncContextManager[T]]
    ) -> AsyncIterator[T | None]:
        """Yields a connection, or None when the snapshot must serve instead."""
        if self.offline():
            yield None
            return
        stack = AsyncExitStack()
        try:
            current = await stack.enter_async_context(connect())
        except UNREACHABLE:
            await stack.aclose()
            if not self.enabled:
                raise
            self.failed()
            yield None
            return
        async with stack:
            yield current
