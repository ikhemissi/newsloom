"""Architect radar: per-reader ranking of triaged announcements, stack and card state.

Reader data is keyed by the pseudonymous feedback reader hash and never logged.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, Protocol
from uuid import UUID

from psycopg import AsyncConnection
from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["act_now", "worth_knowing", "later"]
TIERS: tuple[Tier, ...] = ("act_now", "worth_knowing", "later")
URGENT_KINDS = frozenset({"security", "regulation"})
MAX_STACK = 50
LATER_SHOWN = 150
SNOOZE = timedelta(days=7)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Product(Contract):
    id: UUID
    name: str
    vendor: str
    vendor_id: UUID


class Card(Contract):
    id: UUID
    news_id: UUID
    title: str
    url: str
    source: str
    published_at: datetime
    article_kind: str
    statement: str
    status: str
    effective_date: date | None
    deadline: date | None
    products: tuple[Product, ...]
    tier: Tier
    reason: str | None
    capability: str | None
    in_stack: bool = False
    state: Literal["done", "snoozed"] | None = None


class CardEntry(Contract):
    kind: Literal["card"] = "card"
    card: Card


class GroupEntry(Contract):
    kind: Literal["group"] = "group"
    capability: str
    cards: tuple[Card, ...]


Entry = CardEntry | GroupEntry


class Radar(Contract):
    window: Literal[7, 30]
    tiers: dict[Tier, tuple[Entry, ...]]
    deadlines: tuple[Card, ...]
    hidden: tuple[Card, ...]


class StackEntry(Contract):
    id: UUID
    name: str
    kind: Literal["vendor", "product"]
    vendor: str | None


class Related(Contract):
    id: UUID
    name: str
    relation: Literal["part_of", "replaces"]


class ProductDetail(Contract):
    id: UUID
    name: str
    vendor: str
    aliases: tuple[str, ...]
    related: tuple[Related, ...]
    timeline: tuple[Card, ...]


class StackInput(Contract):
    ids: Annotated[tuple[UUID, ...], Field(max_length=MAX_STACK)]


class CardInput(Contract):
    state: Literal["done", "snoozed"] | None


class SearchQuery(Contract):
    query: Annotated[str, Field(min_length=2, max_length=100)]


def rank(cards: list[Card], window: Literal[7, 30], has_stack: bool, now: datetime) -> Radar:
    """Personalise model tiers by the reader's stack, hide done/snoozed cards and group
    the same capability across vendors."""
    visible: list[Card] = []
    hidden: list[Card] = []
    for card in cards:
        urgent = not has_stack or card.in_stack or card.article_kind in URGENT_KINDS
        if card.tier == "act_now" and not urgent:
            card = card.model_copy(update={"tier": "worth_knowing"})
        (hidden if card.state else visible).append(card)

    def order(card: Card) -> tuple[bool, date, float]:
        return (not card.in_stack, card.deadline or date.max, -card.published_at.timestamp())

    tiers: dict[Tier, tuple[Entry, ...]] = {}
    for tier in TIERS:
        selected = sorted((card for card in visible if card.tier == tier), key=order)
        if tier == "later":
            selected = selected[:LATER_SHOWN]
        tiers[tier] = group(selected)
    today = now.date()
    return Radar(
        window=window,
        tiers=tiers,
        hidden=tuple(hidden),
        deadlines=tuple(
            sorted(
                (
                    card
                    for card in visible
                    if card.tier != "later"
                    and card.deadline is not None
                    and today <= card.deadline <= today + timedelta(days=90)
                ),
                key=lambda card: card.deadline or date.max,
            )
        ),
    )


def group(cards: list[Card]) -> tuple[Entry, ...]:
    by_capability: dict[str, list[Card]] = defaultdict(list)
    for card in cards:
        if card.capability and card.capability != "other":
            by_capability[card.capability].append(card)
    entries: list[Entry] = []
    grouped: set[str] = set()
    for card in cards:
        members = by_capability.get(card.capability or "", [])
        vendors = {product.vendor for member in members for product in member.products}
        if card.capability and len(vendors) >= 2:
            if card.capability not in grouped:
                grouped.add(card.capability)
                entries.append(GroupEntry(capability=card.capability, cards=tuple(members)))
        else:
            entries.append(CardEntry(card=card))
    return tuple(entries)


def entry_cards(entry: Entry) -> tuple[Card, ...]:
    return entry.cards if isinstance(entry, GroupEntry) else (entry.card,)


class RadarStore(Protocol):
    async def radar(self, reader: str, window: Literal[7, 30], now: datetime) -> Radar: ...
    async def set_card(self, reader: str, announcement: UUID, value: CardInput) -> bool: ...
    async def stack(self, reader: str) -> tuple[StackEntry, ...]: ...
    async def set_stack(self, reader: str, ids: tuple[UUID, ...]) -> tuple[StackEntry, ...]: ...
    async def search(self, query: str) -> tuple[StackEntry, ...]: ...
    async def product(self, identifier: UUID) -> ProductDetail | None: ...


CARD_COLUMNS = (
    "a.id,n.id,n.title,n.canonical_url,n.source,n.published_at,"
    "coalesce(n.article_kind,'other'),a.statement,a.status,a.effective_date,a.deadline,"
    "coalesce(a.tier,'worth_knowing'),a.reason,a.capability,"
    "coalesce(json_agg(json_build_object('id',e.id,'name',e.canonical_name,"
    "'vendor',v.canonical_name,'vendor_id',v.id) ORDER BY e.canonical_name) "
    "FILTER (WHERE e.id IS NOT NULL),'[]')"
)
CARD_JOINS = (
    " FROM public.announcements a JOIN public.news n ON n.id=a.news_id"
    " LEFT JOIN public.announcement_entities ae ON ae.announcement_id=a.id"
    " LEFT JOIN public.entities e ON e.id=ae.entity_id"
    " LEFT JOIN public.entities v ON v.id=e.vendor_id"
)
FIELDS = (
    "id",
    "news_id",
    "title",
    "url",
    "source",
    "published_at",
    "article_kind",
    "statement",
    "status",
    "effective_date",
    "deadline",
    "tier",
    "reason",
    "capability",
    "products",
)


def card(row: tuple[object, ...], **extra: object) -> Card:
    return Card.model_validate({**dict(zip(FIELDS, row[: len(FIELDS)], strict=True)), **extra})


class RadarRepository:
    def __init__(self, connection: AsyncConnection[tuple[object, ...]]) -> None:
        self.connection = connection

    async def radar(self, reader: str, window: Literal[7, 30], now: datetime) -> Radar:
        rows = await (
            await self.connection.execute(
                "SELECT "
                + CARD_COLUMNS
                + ",s.state,s.snoozed_until,EXISTS (SELECT 1 FROM public.announcement_entities x "
                "JOIN public.entities xe ON xe.id=x.entity_id JOIN public.reader_stack r "
                "ON r.reader=%s AND r.entity_id IN (xe.id,xe.vendor_id) "
                "WHERE x.announcement_id=a.id)"
                + CARD_JOINS
                + " LEFT JOIN public.reader_card_state s ON s.reader=%s AND s.announcement_id=a.id"
                " WHERE n.published_at>=%s GROUP BY a.id,n.id,s.state,s.snoozed_until"
                " ORDER BY n.published_at DESC,a.ordinal LIMIT 3000",
                (reader, reader, now - timedelta(days=window)),
            )
        ).fetchall()
        stacked = await (
            await self.connection.execute(
                "SELECT EXISTS (SELECT 1 FROM public.reader_stack WHERE reader=%s)", (reader,)
            )
        ).fetchone()
        cards = []
        for row in rows:
            state, until, in_stack = row[len(FIELDS)], row[len(FIELDS) + 1], row[len(FIELDS) + 2]
            active = state == "done" or (
                state == "snoozed" and isinstance(until, datetime) and until > now
            )
            cards.append(card(row, state=state if active else None, in_stack=in_stack))
        return rank(cards, window, bool(stacked and stacked[0]), now)

    async def set_card(self, reader: str, announcement: UUID, value: CardInput) -> bool:
        known = await (
            await self.connection.execute(
                "SELECT 1 FROM public.announcements WHERE id=%s", (announcement,)
            )
        ).fetchone()
        if known is None:
            return False
        if value.state is None:
            await self.connection.execute(
                "DELETE FROM public.reader_card_state WHERE reader=%s AND announcement_id=%s",
                (reader, announcement),
            )
            return True
        await self.connection.execute(
            "INSERT INTO public.reader_card_state(reader,announcement_id,state,snoozed_until) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (reader,announcement_id) DO UPDATE SET "
            "state=excluded.state,snoozed_until=excluded.snoozed_until,"
            "updated_at=clock_timestamp()",
            (
                reader,
                announcement,
                value.state,
                datetime.now(UTC) + SNOOZE if value.state == "snoozed" else None,
            ),
        )
        return True

    async def entries(self, where: str, values: tuple[object, ...]) -> tuple[StackEntry, ...]:
        rows = await (
            await self.connection.execute(
                "SELECT e.id,e.canonical_name,e.kind,v.canonical_name FROM public.entities e "
                "LEFT JOIN public.entities v ON v.id=e.vendor_id WHERE "
                + where
                + " ORDER BY e.kind='product',e.canonical_name LIMIT 50",
                values,
            )
        ).fetchall()
        return tuple(
            StackEntry.model_validate(dict(zip(("id", "name", "kind", "vendor"), row, strict=True)))
            for row in rows
        )

    async def stack(self, reader: str) -> tuple[StackEntry, ...]:
        return await self.entries(
            "e.id IN (SELECT entity_id FROM public.reader_stack WHERE reader=%s)", (reader,)
        )

    async def set_stack(self, reader: str, ids: tuple[UUID, ...]) -> tuple[StackEntry, ...]:
        await self.connection.execute("DELETE FROM public.reader_stack WHERE reader=%s", (reader,))
        if ids:
            await self.connection.execute(
                "INSERT INTO public.reader_stack(reader,entity_id) "
                "SELECT %s,id FROM public.entities WHERE id=ANY(%s) ON CONFLICT DO NOTHING",
                (reader, list(ids)),
            )
        return await self.stack(reader)

    async def search(self, query: str) -> tuple[StackEntry, ...]:
        words = " ".join(
            "".join(c if c.isalnum() or c in "+#." else " " for c in query.casefold()).split()
        )
        found = await self.entries(
            "(e.canonical_name ILIKE %s OR e.id IN (SELECT entity_id FROM public.entity_aliases "
            "WHERE alias LIKE %s))",
            ("%" + query.replace("%", "").replace("_", "") + "%", "%" + words + "%"),
        )
        return found[:10]

    async def product(self, identifier: UUID) -> ProductDetail | None:
        row = await (
            await self.connection.execute(
                "SELECT e.canonical_name,v.canonical_name FROM public.entities e "
                "JOIN public.entities v ON v.id=e.vendor_id WHERE e.id=%s AND e.kind='product'",
                (identifier,),
            )
        ).fetchone()
        if row is None:
            return None
        aliases = await (
            await self.connection.execute(
                "SELECT alias FROM public.entity_aliases WHERE entity_id=%s ORDER BY alias",
                (identifier,),
            )
        ).fetchall()
        related = await (
            await self.connection.execute(
                "SELECT t.id,t.canonical_name,r.relation FROM public.entity_relations r "
                "JOIN public.entities t ON t.id=r.target_id WHERE r.source_id=%s "
                "ORDER BY t.canonical_name",
                (identifier,),
            )
        ).fetchall()
        timeline = await (
            await self.connection.execute(
                "SELECT "
                + CARD_COLUMNS
                + CARD_JOINS
                + " WHERE a.id IN (SELECT announcement_id FROM public.announcement_entities "
                "WHERE entity_id=%s) GROUP BY a.id,n.id ORDER BY n.published_at DESC LIMIT 100",
                (identifier,),
            )
        ).fetchall()
        name = str(row[0])
        return ProductDetail(
            id=identifier,
            name=name,
            vendor=str(row[1]),
            aliases=tuple(str(alias[0]) for alias in aliases if str(alias[0]) != name.casefold()),
            related=tuple(
                Related.model_validate(dict(zip(("id", "name", "relation"), item, strict=True)))
                for item in related
            ),
            timeline=tuple(card(item) for item in timeline),
        )
