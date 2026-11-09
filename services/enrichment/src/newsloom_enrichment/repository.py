"""Short fenced queue transactions; migrations own schema and privileges."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from newsloom_core.entries import Entry
from psycopg import AsyncConnection
from psycopg.errors import InsufficientPrivilege

from newsloom_enrichment.entities import Curated, GraphWriter, load_curated
from newsloom_enrichment.models import (
    DEFAULT_LIMITS,
    Announcement,
    Claim,
    Enrichment,
    EnrichmentFailure,
    Limits,
    Vector,
)
from newsloom_enrichment.triage import Rating


@dataclass
class Untriaged:
    news_id: UUID
    title: str
    summary: str
    article_kind: str
    ids: list[UUID]
    announcements: list[Announcement]


@dataclass(frozen=True)
class ModelMetadata:
    generation_model: str
    generation_version: str
    embedding_model: str
    embedding_version: str
    prompt_revision: str
    taxonomy_revision: str


class EnrichmentRepository(Protocol):
    async def claim(self, correlation: str) -> Claim | None: ...
    async def complete(
        self,
        claim: Claim,
        result: Enrichment,
        vector: Vector,
        metadata: ModelMetadata,
        correlation: str,
        mentions: dict[str, Vector] | None = None,
        ratings: tuple[Rating, ...] = (),
    ) -> None: ...
    async def fail(
        self,
        claim: Claim,
        reason: str,
        retry_after: float,
        correlation: str,
    ) -> None: ...
    async def counts(self) -> dict[str, int]: ...


class Repository:
    def __init__(
        self,
        connection: AsyncConnection[tuple[object, ...]],
        limits: Limits = DEFAULT_LIMITS,
        curated: Curated | None = None,
    ) -> None:
        self.connection = connection
        self.limits = limits
        self.curated = curated or load_curated()
        self.graph = dict.fromkeys(("announcements", "curated", "exact", "similar", "new"), 0)

    async def verify_access(self) -> int:
        row = await (
            await self.connection.execute(
                "SELECT has_table_privilege(current_user,'ingestion_queue','SELECT'),"
                "has_table_privilege(current_user,'news','SELECT'),"
                "has_table_privilege(current_user,'news','INSERT'),"
                "has_column_privilege(current_user,'ingestion_queue','status','UPDATE'),"
                "has_column_privilege(current_user,'ingestion_queue','entry','UPDATE'),"
                "pg_has_role(current_user,'azure_pg_admin','member')"
            )
        ).fetchone()
        if row != (True, True, True, True, False, False):
            raise EnrichmentFailure("enrichment_grant_mismatch")
        await self.connection.execute("SELECT id FROM ingestion_queue LIMIT 0")
        await self.connection.execute("SELECT id FROM news LIMIT 0")
        statements = (
            "SELECT id FROM quarantine LIMIT 0",
            "INSERT INTO ingestion_queue DEFAULT VALUES",
            "UPDATE ingestion_queue SET entry='{}' WHERE false",
            "DELETE FROM news WHERE false",
            "CREATE TABLE public.enrichment_privilege_probe(id integer)",
        )
        for statement in statements:
            try:
                async with self.connection.transaction():
                    await self.connection.execute(statement)
                    raise EnrichmentFailure("enrichment_denial_not_proven")
            except InsufficientPrivilege:
                pass
        return 3 + len(statements)

    async def claim(self, correlation: str) -> Claim | None:
        async with self.connection.transaction():
            await self.connection.execute(
                "WITH expired AS (SELECT id FROM ingestion_queue "
                "WHERE (status='processing' AND lease_until<=clock_timestamp()) "
                "OR (status IN ('pending','failed') AND attempts>=%s) "
                "FOR UPDATE SKIP LOCKED LIMIT %s) "
                "UPDATE ingestion_queue q SET "
                "status=CASE WHEN attempts>=%s THEN 'dead_letter' ELSE 'failed' END,"
                "lease_token=NULL,lease_until=NULL,retry_after=clock_timestamp(),"
                "last_error='lease_expired',updated_at=clock_timestamp() "
                "FROM expired e WHERE q.id=e.id",
                (self.limits.queue_attempts, self.limits.max_items, self.limits.queue_attempts),
            )
            row = await (
                await self.connection.execute(
                    "WITH eligible AS (SELECT id FROM ingestion_queue "
                    "WHERE status IN ('pending','failed') AND retry_after<=clock_timestamp() "
                    "AND attempts<%s ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1) "
                    "UPDATE ingestion_queue q SET status='processing',attempts=attempts+1,"
                    "lease_token=gen_random_uuid(),"
                    "lease_until=clock_timestamp()+%s*interval '1 second',"
                    "started_at=clock_timestamp(),updated_at=clock_timestamp(),"
                    "last_error=NULL,enrichment_run_id=%s FROM eligible e WHERE q.id=e.id "
                    "RETURNING q.id,q.lease_token,q.entry,q.attempts,q.lease_until",
                    (self.limits.queue_attempts, self.limits.lease_seconds, correlation),
                )
            ).fetchone()
            if row is None:
                return None
            if (
                not isinstance(row[0], UUID)
                or not isinstance(row[1], UUID)
                or not isinstance(row[3], int)
                or not isinstance(row[4], datetime)
            ):
                raise EnrichmentFailure("invalid_queue_claim")
            return Claim(row[0], row[1], Entry.model_validate(row[2]), row[3], row[4])

    async def complete(
        self,
        claim: Claim,
        result: Enrichment,
        vector: Vector,
        metadata: ModelMetadata,
        correlation: str,
        mentions: dict[str, Vector] | None = None,
        ratings: tuple[Rating, ...] = (),
    ) -> None:
        async with self.connection.transaction():
            owned = await (
                await self.connection.execute(
                    "SELECT 1 FROM ingestion_queue WHERE id=%s AND status='processing' "
                    "AND lease_token=%s AND lease_until>clock_timestamp() FOR UPDATE",
                    (claim.id, claim.token),
                )
            ).fetchone()
            if owned != (1,):
                raise EnrichmentFailure("enrichment_lease_lost")
            item = claim.entry
            await self.connection.execute(
                "INSERT INTO news(id,source,guid,canonical_url,title,published_at,date_origin,"
                "author,publisher_categories,summary,category,tags,embedding,generation_model,"
                "generation_version,embedding_model,embedding_version,prompt_revision,"
                "taxonomy_revision,enrichment_run_id,article_kind) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,"
                "%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    claim.id,
                    item.source,
                    item.guid,
                    item.url,
                    item.title,
                    item.published_at,
                    item.date_origin,
                    item.author,
                    list(item.categories),
                    result.summary,
                    result.category.value,
                    list(result.tags),
                    "[" + ",".join(str(value) for value in vector.values) + "]",
                    metadata.generation_model,
                    metadata.generation_version,
                    metadata.embedding_model,
                    metadata.embedding_version,
                    metadata.prompt_revision,
                    metadata.taxonomy_revision,
                    correlation,
                    result.article_kind.value,
                ),
            )
            await self.write_graph(claim.id, result, mentions or {}, ratings)
            cursor = await self.connection.execute(
                "UPDATE ingestion_queue SET status='completed',completed_at=clock_timestamp(),"
                "updated_at=clock_timestamp(),lease_token=NULL,lease_until=NULL,last_error=NULL "
                "WHERE id=%s AND status='processing' AND lease_token=%s "
                "AND lease_until>clock_timestamp()",
                (claim.id, claim.token),
            )
            if cursor.rowcount != 1:
                raise EnrichmentFailure("enrichment_lease_lost")

    async def write_graph(
        self,
        news_id: UUID,
        result: Enrichment,
        mentions: dict[str, Vector],
        ratings: tuple[Rating, ...] = (),
    ) -> None:
        if not result.announcements:
            return
        writer = GraphWriter(self.connection, self.curated)
        await writer.write(news_id, result.announcements, mentions, ratings)
        self.graph["announcements"] += len(result.announcements)
        for key, value in writer.counts.items():
            self.graph[key] += value

    async def backfill_candidates(self, limit: int) -> list[tuple[UUID, Entry]]:
        """Published news from the last 30 days that predates announcement extraction."""
        rows = await (
            await self.connection.execute(
                "SELECT n.id,q.entry FROM news n JOIN ingestion_queue q ON q.id=n.id "
                "WHERE n.article_kind IS NULL AND n.published_at>=clock_timestamp()-interval "
                "'30 days' ORDER BY n.published_at DESC,n.id LIMIT %s",
                (limit,),
            )
        ).fetchall()
        result: list[tuple[UUID, Entry]] = []
        for identifier, entry in rows:
            if not isinstance(identifier, UUID):
                raise EnrichmentFailure("invalid_news_identifier")
            result.append((identifier, Entry.model_validate(entry)))
        return result

    async def store_backfill(
        self, news_id: UUID, result: Enrichment, mentions: dict[str, Vector]
    ) -> bool:
        async with self.connection.transaction():
            row = await (
                await self.connection.execute(
                    "SELECT 1 FROM news WHERE id=%s AND article_kind IS NULL FOR UPDATE",
                    (news_id,),
                )
            ).fetchone()
            if row is None:
                return False
            await self.connection.execute(
                "UPDATE news SET article_kind=%s WHERE id=%s",
                (result.article_kind.value, news_id),
            )
            await self.write_graph(news_id, result, mentions)
        return True

    async def untriaged(self, limit: int) -> list[Untriaged]:
        """News items whose stored announcements have not been triaged yet."""
        rows = await (
            await self.connection.execute(
                "SELECT n.id,n.title,n.summary,coalesce(n.article_kind,'other'),a.id,a.ordinal,"
                "a.statement,a.change_type,a.status,a.effective_date,a.deadline,"
                "coalesce(array_agg(e.canonical_name ORDER BY e.canonical_name) "
                "FILTER (WHERE e.id IS NOT NULL),'{}'),"
                "coalesce(array_agg(v.canonical_name ORDER BY e.canonical_name) "
                "FILTER (WHERE e.id IS NOT NULL),'{}') "
                "FROM news n JOIN announcements a ON a.news_id=n.id "
                "LEFT JOIN announcement_entities ae ON ae.announcement_id=a.id "
                "LEFT JOIN entities e ON e.id=ae.entity_id "
                "LEFT JOIN entities v ON v.id=e.vendor_id "
                "WHERE n.id IN (SELECT DISTINCT news_id FROM announcements WHERE tier IS NULL "
                "LIMIT %s) GROUP BY n.id,a.id ORDER BY n.id,a.ordinal",
                (limit,),
            )
        ).fetchall()
        items: dict[UUID, Untriaged] = {}
        for row in rows:
            news_id, title, summary, kind, announcement_id = row[:5]
            products = [
                {"product": str(name)[:120], "vendor": str(vendor)[:80]}
                for name, vendor in zip(row[11], row[12], strict=True)  # type: ignore[call-overload]
            ][:5]
            if (
                not isinstance(news_id, UUID)
                or not isinstance(announcement_id, UUID)
                or not products
            ):
                continue
            item = items.setdefault(
                news_id, Untriaged(news_id, str(title), str(summary), str(kind), [], [])
            )
            item.ids.append(announcement_id)
            item.announcements.append(
                Announcement.model_validate(
                    {
                        "statement": row[6],
                        "change_type": row[7],
                        "status": row[8],
                        "effective_date": row[9].isoformat() if row[9] else None,  # type: ignore[attr-defined]
                        "deadline": row[10].isoformat() if row[10] else None,  # type: ignore[attr-defined]
                        "products": products,
                    }
                )
            )
        return list(items.values())

    async def store_triage(self, ids: list[UUID], ratings: tuple[Rating, ...]) -> int:
        stored = 0
        async with self.connection.transaction():
            for rating in ratings:
                cursor = await self.connection.execute(
                    "UPDATE announcements SET tier=%s,reason=%s,capability=%s,"
                    "triaged_at=clock_timestamp() WHERE id=%s AND tier IS NULL",
                    (rating.tier, rating.reason, rating.capability, ids[rating.index]),
                )
                stored += cursor.rowcount
        return stored

    async def fail(
        self,
        claim: Claim,
        reason: str,
        retry_after: float,
        correlation: str,
    ) -> None:
        delay = max(min(1800, 30 * 2 ** (claim.attempts - 1)), retry_after)
        cursor = await self.connection.execute(
            "UPDATE ingestion_queue SET status=CASE WHEN attempts>=%s THEN 'dead_letter' "
            "ELSE 'failed' END,last_error=%s,retry_after=clock_timestamp()+%s*interval '1 second',"
            "lease_token=NULL,lease_until=NULL,updated_at=clock_timestamp(),enrichment_run_id=%s "
            "WHERE id=%s AND status='processing' AND lease_token=%s "
            "AND lease_until>clock_timestamp()",
            (self.limits.queue_attempts, reason, delay, correlation, claim.id, claim.token),
        )
        if cursor.rowcount != 1:
            raise EnrichmentFailure("enrichment_lease_lost")

    async def counts(self) -> dict[str, int]:
        states = dict.fromkeys(("pending", "processing", "completed", "failed", "dead_letter"), 0)
        rows = await (
            await self.connection.execute(
                "SELECT status,count(*) FROM ingestion_queue GROUP BY status"
            )
        ).fetchall()
        for status, count in rows:
            if not isinstance(status, str) or status not in states or not isinstance(count, int):
                raise EnrichmentFailure("invalid_queue_counts")
            states[status] = count
        row = await (await self.connection.execute("SELECT count(*) FROM news")).fetchone()
        if row is None or not isinstance(row[0], int):
            raise EnrichmentFailure("invalid_news_counts")
        return {**states, "news": row[0]}
