"""Short fenced queue transactions; migrations own schema and privileges."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from newsloom_core.entries import Entry
from psycopg import AsyncConnection
from psycopg.errors import InsufficientPrivilege

from newsloom_enrichment.models import (
    DEFAULT_LIMITS,
    Claim,
    Enrichment,
    EnrichmentFailure,
    Limits,
    Vector,
)


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
        self, connection: AsyncConnection[tuple[object, ...]], limits: Limits = DEFAULT_LIMITS
    ) -> None:
        self.connection = connection
        self.limits = limits

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
                "taxonomy_revision,enrichment_run_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,"
                "%s,%s,%s,%s,%s,%s,%s)",
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
                ),
            )
            cursor = await self.connection.execute(
                "UPDATE ingestion_queue SET status='completed',completed_at=clock_timestamp(),"
                "updated_at=clock_timestamp(),lease_token=NULL,lease_until=NULL,last_error=NULL "
                "WHERE id=%s AND status='processing' AND lease_token=%s "
                "AND lease_until>clock_timestamp()",
                (claim.id, claim.token),
            )
            if cursor.rowcount != 1:
                raise EnrichmentFailure("enrichment_lease_lost")

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
