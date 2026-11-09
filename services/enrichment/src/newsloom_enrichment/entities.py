"""Conservative vendor/product resolution into the relational product graph."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from psycopg import AsyncConnection
from pydantic import BaseModel, ConfigDict, Field

from newsloom_enrichment.models import Announcement, EnrichmentFailure, Vector, normalized
from newsloom_enrichment.triage import Rating

SIMILARITY = 0.92
# Serializes graph writers (scheduled enrichment and backfill) inside their transactions.
GRAPH_LOCK = 5_381_207_114
Method = Literal["curated", "exact", "similar", "new"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VendorConfig(Strict):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    aliases: tuple[str, ...]


class ProductConfig(Strict):
    vendor: str
    name: Annotated[str, Field(min_length=1, max_length=120)]
    aliases: tuple[str, ...]


class RelationConfig(Strict):
    source: tuple[str, str]
    relation: Literal["part_of", "replaces"]
    target: tuple[str, str]


class EntityConfig(Strict):
    vendors: tuple[VendorConfig, ...]
    products: tuple[ProductConfig, ...]
    relations: tuple[RelationConfig, ...]


@dataclass(frozen=True)
class Curated:
    vendors: dict[str, str]
    products: dict[tuple[str, str], str]
    relations: tuple[RelationConfig, ...]
    prefixes: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def vendor(self, name: str) -> tuple[str, bool]:
        key = normalized(name)
        canonical = self.vendors.get(key)
        return (canonical, True) if canonical else (" ".join(name.split()), False)

    def keys(self, vendor: str, product: str) -> tuple[str, ...]:
        """Normalised lookup keys: the name, then the name without a leading vendor alias."""
        key = normalized(product)
        result = [key]
        for prefix in self.prefixes.get(vendor, ()):
            if key.startswith(prefix + " ") and len(key) > len(prefix) + 1:
                result.append(key[len(prefix) + 1 :])
        return tuple(dict.fromkeys(result))


def load_curated(path: Path = Path("config/entities.json")) -> Curated:
    config = EntityConfig.model_validate_json(path.read_bytes())
    vendors: dict[str, str] = {}
    prefixes: dict[str, list[str]] = {}
    for vendor in config.vendors:
        for alias in (vendor.name, *vendor.aliases):
            key = normalized(alias)
            if not key or vendors.setdefault(key, vendor.name) != vendor.name:
                raise EnrichmentFailure("invalid_entity_catalogue")
            prefixes.setdefault(vendor.name, []).append(key)
    products: dict[tuple[str, str], str] = {}
    for product in config.products:
        if product.vendor not in prefixes:
            raise EnrichmentFailure("invalid_entity_catalogue")
        for alias in (product.name, *product.aliases):
            pair = (product.vendor, normalized(alias))
            if products.setdefault(pair, product.name) != product.name:
                raise EnrichmentFailure("invalid_entity_catalogue")
    for relation in config.relations:
        for owner, name in (relation.source, relation.target):
            if products.get((owner, normalized(name))) != name:
                raise EnrichmentFailure("invalid_entity_catalogue")
    return Curated(
        vendors,
        products,
        config.relations,
        {name: tuple(sorted(keys, key=len, reverse=True)) for name, keys in prefixes.items()},
    )


def numbers(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[0-9]+(?:\.[0-9]+)*", value))


def mention_text(vendor: str, product: str) -> str:
    return f"{vendor}: {product}"


class GraphWriter:
    """Writes announcements and entities inside the caller's transaction."""

    def __init__(self, connection: AsyncConnection[tuple[object, ...]], curated: Curated) -> None:
        self.connection, self.curated = connection, curated
        self.counts = dict.fromkeys(("curated", "exact", "similar", "new"), 0)

    async def write(
        self,
        news_id: UUID,
        announcements: tuple[Announcement, ...],
        vectors: dict[str, Vector],
        ratings: tuple[Rating, ...] = (),
    ) -> None:
        await self.connection.execute("SELECT pg_advisory_xact_lock(%s)", (GRAPH_LOCK,))
        rated = {rating.index: rating for rating in ratings}
        for ordinal, item in enumerate(announcements):
            rating = rated.get(ordinal)
            row = await (
                await self.connection.execute(
                    "INSERT INTO announcements(news_id,ordinal,statement,change_type,status,"
                    "effective_date,deadline,tier,reason,capability,triaged_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "CASE WHEN %s::text IS NULL THEN NULL ELSE clock_timestamp() END) RETURNING id",
                    (
                        news_id,
                        ordinal,
                        " ".join(item.statement.split()),
                        item.change_type.value,
                        item.status.value,
                        item.effective_date,
                        item.deadline,
                        rating and rating.tier,
                        rating and rating.reason,
                        rating and rating.capability,
                        rating and rating.tier,
                    ),
                )
            ).fetchone()
            if row is None or not isinstance(row[0], UUID):
                raise EnrichmentFailure("announcement_insert_failed")
            linked: set[UUID] = set()
            for mention in item.products:
                vendor_id, vendor = await self.vendor(mention.vendor)
                entity, method = await self.product(
                    vendor_id,
                    vendor,
                    mention.product,
                    vectors.get(mention_text(vendor, mention.product)),
                )
                if entity in linked:
                    continue
                linked.add(entity)
                self.counts[method] += 1
                await self.connection.execute(
                    "INSERT INTO announcement_entities(announcement_id,entity_id,method) "
                    "VALUES (%s,%s,%s)",
                    (row[0], entity, method),
                )

    async def alias(self, vendor_id: UUID | None, key: str) -> UUID | None:
        row = await (
            await self.connection.execute(
                "SELECT entity_id FROM entity_aliases WHERE vendor_id IS NOT DISTINCT FROM %s "
                "AND alias=%s",
                (vendor_id, key),
            )
        ).fetchone()
        return row[0] if row is not None and isinstance(row[0], UUID) else None

    async def add_alias(self, vendor_id: UUID | None, key: str, entity: UUID, method: str) -> None:
        if key:
            await self.connection.execute(
                "INSERT INTO entity_aliases(alias,vendor_id,entity_id,method) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (key, vendor_id, entity, method),
            )

    async def create(
        self, kind: str, vendor_id: UUID | None, name: str, vector: Vector | None
    ) -> UUID:
        row = await (
            await self.connection.execute(
                "INSERT INTO entities(kind,vendor_id,canonical_name,embedding) "
                "VALUES (%s,%s,%s,%s::vector) RETURNING id",
                (
                    kind,
                    vendor_id,
                    name[:120],
                    None if vector is None else "[" + ",".join(map(str, vector.values)) + "]",
                ),
            )
        ).fetchone()
        if row is None or not isinstance(row[0], UUID):
            raise EnrichmentFailure("entity_insert_failed")
        return row[0]

    async def vendor(self, name: str) -> tuple[UUID, str]:
        canonical, _ = self.curated.vendor(name)
        for key in (normalized(canonical), normalized(name)):
            found = await self.alias(None, key)
            if found is not None:
                return found, canonical
        entity = await self.create("vendor", None, canonical, None)
        await self.add_alias(None, normalized(canonical), entity, "canonical")
        await self.add_alias(None, normalized(name), entity, "exact")
        return entity, canonical

    async def product(
        self, vendor_id: UUID, vendor: str, name: str, vector: Vector | None
    ) -> tuple[UUID, Method]:
        keys = self.curated.keys(vendor, name)
        curated = next(
            (
                self.curated.products[(vendor, key)]
                for key in keys
                if (vendor, key) in self.curated.products
            ),
            None,
        )
        if curated is not None:
            canonical_key = normalized(curated)
            entity = await self.alias(vendor_id, canonical_key)
            if entity is None:
                entity = await self.create("product", vendor_id, curated, vector)
                await self.add_alias(vendor_id, canonical_key, entity, "curated")
                await self.relations(vendor, curated, entity, vendor_id)
            for key in keys:
                await self.add_alias(vendor_id, key, entity, "curated")
            return entity, "curated"
        for key in keys:
            entity = await self.alias(vendor_id, key)
            if entity is not None:
                for other in keys:
                    await self.add_alias(vendor_id, other, entity, "exact")
                return entity, "exact"
        if vector is not None:
            row = await (
                await self.connection.execute(
                    "SELECT id,canonical_name,1-(embedding<=>%s::vector) FROM entities "
                    "WHERE kind='product' AND vendor_id=%s AND embedding IS NOT NULL "
                    "ORDER BY embedding<=>%s::vector LIMIT 1",
                    (
                        "[" + ",".join(map(str, vector.values)) + "]",
                        vendor_id,
                        "[" + ",".join(map(str, vector.values)) + "]",
                    ),
                )
            ).fetchone()
            # Similar names must also carry the same version numbers (GPT-6.1 vs GPT-6.2).
            if (
                row is not None
                and isinstance(row[0], UUID)
                and isinstance(row[2], float)
                and row[2] >= SIMILARITY
                and numbers(str(row[1])) == numbers(name)
            ):
                for key in keys:
                    await self.add_alias(vendor_id, key, row[0], "similar")
                return row[0], "similar"
        entity = await self.create("product", vendor_id, " ".join(name.split()), vector)
        for key in keys:
            await self.add_alias(vendor_id, key, entity, "canonical")
        return entity, "new"

    async def relations(self, vendor: str, name: str, entity: UUID, vendor_id: UUID) -> None:
        for relation in self.curated.relations:
            if relation.source != (vendor, name):
                continue
            target_vendor_id, target_vendor = await self.vendor(relation.target[0])
            target, _ = await self.product(
                target_vendor_id, target_vendor, relation.target[1], None
            )
            await self.connection.execute(
                "INSERT INTO entity_relations(source_id,target_id,relation) VALUES (%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (entity, target, relation.relation),
            )


def mention_texts(curated: Curated, announcements: tuple[Announcement, ...]) -> list[str]:
    texts: dict[str, None] = {}
    for item in announcements:
        for mention in item.products:
            texts[mention_text(curated.vendor(mention.vendor)[0], mention.product)] = None
    return list(texts)
