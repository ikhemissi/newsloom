"""Short serialized PostgreSQL transactions; schema is owned by migrations."""

import asyncio
from typing import Protocol
from uuid import UUID

from newsloom_core.feeds import FeedSource
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from newsloom_ingestion.models import Candidate, Decision, Entry, IngestionFailure, source_counts

RUN_LOCK = 736981072


class IngestionRepository(Protocol):
    async def stage(
        self,
        entry: Entry,
        correlation: str,
        acquisition: str = "feed_item",
        feed_text: str | None = None,
    ) -> bool: ...

    async def decide(
        self, identifier: UUID, entry: Entry, decision: Decision, correlation: str
    ) -> None: ...


class Repository:
    def __init__(
        self, connection: AsyncConnection[tuple[object, ...]], model: str, version: str
    ) -> None:
        self.connection = connection
        self.model = model
        self.version = version
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        row = await (
            await self.connection.execute("SELECT pg_try_advisory_lock(%s)", (RUN_LOCK,))
        ).fetchone()
        if row != (True,):
            raise IngestionFailure("ingestion_already_running")

    async def release(self) -> None:
        await self.connection.execute("SELECT pg_advisory_unlock(%s)", (RUN_LOCK,))

    async def source(self, source: FeedSource, correlation: str | None = None) -> dict[str, str]:
        async with self.lock, self.connection.transaction():
            await self.connection.execute(
                "INSERT INTO feed_sources(id, configuration) VALUES (%s, %s) "
                "ON CONFLICT(id) DO UPDATE SET configuration = EXCLUDED.configuration",
                (source.id, Jsonb(source.model_dump(mode="json"))),
            )
            row = await (
                await self.connection.execute(
                    "SELECT etag, last_modified FROM feed_sources WHERE id = %s", (source.id,)
                )
            ).fetchone()
            if correlation is not None:
                await self.connection.execute(
                    "UPDATE feed_sources SET last_run=%s,counts=%s,outcome='processing' "
                    "WHERE id=%s",
                    (correlation, Jsonb(source_counts()), source.id),
                )
        if row is None:
            raise IngestionFailure("source_state_missing")
        return {
            name: str(value)
            for name, value in zip(("If-None-Match", "If-Modified-Since"), row, strict=True)
            if value is not None
        }

    async def known(self, entry: Candidate) -> bool:
        async with self.lock:
            return await self._known(entry)

    async def _known(self, entry: Candidate) -> bool:
        row = await (
            await self.connection.execute(
                "SELECT 1 FROM ingestion_queue WHERE canonical_url = %s "
                "OR (source = %s AND guid = %s) UNION ALL "
                "SELECT 1 FROM quarantine WHERE canonical_url = %s "
                "OR (source = %s AND guid = %s) LIMIT 1",
                (entry.url, entry.source, entry.guid, entry.url, entry.source, entry.guid),
            )
        ).fetchone()
        return row is not None

    async def stage(
        self,
        entry: Entry,
        correlation: str,
        acquisition: str = "feed_item",
        feed_text: str | None = None,
    ) -> bool:
        async with self.lock, self.connection.transaction():
            if await self._known(entry):
                return False
            await self.connection.execute(
                "INSERT INTO quarantine(source, guid, canonical_url, entry, disposition, reason, "
                "model, model_version, correlation_id, acquisition, feed_text) "
                "VALUES (%s,%s,%s,%s,'deferred','awaiting_screening',%s,%s,%s,%s,%s)",
                (
                    entry.source,
                    entry.guid,
                    entry.url,
                    Jsonb(entry.model_dump(mode="json")),
                    self.model,
                    self.version,
                    correlation,
                    acquisition,
                    feed_text,
                ),
            )
        return True

    async def finish_source(
        self,
        source: str,
        correlation: str,
        outcome: str,
        counts: dict[str, int],
        headers: dict[str, str] | None = None,
    ) -> None:
        async with self.lock, self.connection.transaction():
            await self.connection.execute(
                "UPDATE feed_sources SET checked_at=clock_timestamp(), last_run=%s, outcome=%s, "
                "counts=%s WHERE id=%s",
                (correlation, outcome, Jsonb(counts), source),
            )
            if headers is not None:
                await self.connection.execute(
                    "UPDATE feed_sources SET etag=%s, last_modified=%s WHERE id=%s",
                    (headers.get("etag"), headers.get("last-modified"), source),
                )

    async def deferred(self, sources: list[str]) -> tuple[UUID, Entry] | None:
        row = await (
            await self.connection.execute(
                "SELECT id, entry FROM quarantine WHERE disposition='deferred' "
                "AND source=ANY(%s) AND retry_after <= clock_timestamp() "
                "ORDER BY attempts, created_at LIMIT 1",
                (sources,),
            )
        ).fetchone()
        if row is None:
            return None
        if not isinstance(row[0], UUID):
            raise IngestionFailure("invalid_entry_identifier")
        return row[0], Entry.model_validate(row[1])

    async def decide(
        self, identifier: UUID, entry: Entry, decision: Decision, correlation: str
    ) -> None:
        async with self.lock, self.connection.transaction():
            row = await (
                await self.connection.execute(
                    "SELECT disposition,acquisition,feed_text FROM quarantine "
                    "WHERE id=%s FOR UPDATE",
                    (identifier,),
                )
            ).fetchone()
            if row is None or row[0] != "deferred":
                raise IngestionFailure("screening_state_changed")
            if decision.disposition == "accepted":
                cursor = await self.connection.execute(
                    "INSERT INTO ingestion_queue(source,guid,canonical_url,entry,score,threshold,"
                    "model,model_version,correlation_id,acquisition,feed_text,acquired_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "CASE WHEN %s::text IS NULL THEN NULL ELSE clock_timestamp() END) RETURNING id",
                    (
                        entry.source,
                        entry.guid,
                        entry.url,
                        Jsonb(entry.model_dump(mode="json")),
                        decision.score,
                        decision.threshold,
                        self.model,
                        self.version,
                        correlation,
                        row[1],
                        row[2],
                        row[1],
                    ),
                )
                accepted = await cursor.fetchone()
                if accepted is None:
                    raise IngestionFailure("accepted_row_missing")
                await self.connection.execute(
                    "UPDATE quarantine SET disposition='resolved', reason='accepted', "
                    "entry='{}', feed_text=NULL, resolved_queue_id=%s, "
                    "updated_at=clock_timestamp(), "
                    "score=%s,threshold=%s,attempts=attempts+1 WHERE id=%s",
                    (accepted[0], decision.score, decision.threshold, identifier),
                )
            else:
                await self.connection.execute(
                    "UPDATE quarantine SET disposition=%s,reason=%s,score=%s,threshold=%s,"
                    "attempts=attempts+1,updated_at=clock_timestamp(),correlation_id=%s,"
                    "retry_after=clock_timestamp()+interval '30 minutes' WHERE id=%s",
                    (
                        decision.disposition,
                        decision.reason,
                        decision.score,
                        decision.threshold,
                        correlation,
                        identifier,
                    ),
                )
            key = (
                "security_rejected" if decision.disposition == "rejected" else decision.disposition
            )
            cursor = await self.connection.execute(
                "UPDATE feed_sources SET counts=jsonb_set(counts,ARRAY[%s],"
                "to_jsonb(coalesce((counts->>%s)::int,0)+1)) WHERE id=%s AND last_run=%s",
                (key, key, entry.source, correlation),
            )
            if cursor.rowcount != 1:
                raise IngestionFailure("source_run_changed")

    async def retain_feed_text(self) -> int:
        """Drop article text kept longer than 90 days; feed text and published news stay."""
        async with self.lock:
            cursor = await self.connection.execute(
                "UPDATE ingestion_queue SET entry=jsonb_set(entry,'{text}',to_jsonb(feed_text)),"
                "feed_text=NULL,updated_at=clock_timestamp() WHERE id IN (SELECT id FROM "
                "ingestion_queue WHERE status='completed' AND feed_text IS NOT NULL "
                "AND acquired_at < clock_timestamp() - interval '90 days' LIMIT 500)"
            )
            return max(cursor.rowcount, 0)

    async def backfill_candidates(self, limit: int) -> list[tuple[UUID, Entry]]:
        async with self.lock:
            rows = await (
                await self.connection.execute(
                    "SELECT id, entry FROM ingestion_queue WHERE status='completed' "
                    "AND acquisition IS NULL AND (entry->>'published_at')::timestamptz >= "
                    "clock_timestamp() - interval '14 days' ORDER BY created_at, id LIMIT %s",
                    (limit,),
                )
            ).fetchall()
        result: list[tuple[UUID, Entry]] = []
        for identifier, entry in rows:
            if not isinstance(identifier, UUID):
                raise IngestionFailure("invalid_entry_identifier")
            result.append((identifier, Entry.model_validate(entry)))
        return result

    async def record_backfill(
        self, identifier: UUID, acquisition: str, entry: Entry | None, feed_text: str | None
    ) -> bool:
        async with self.lock:
            if entry is None:
                cursor = await self.connection.execute(
                    "UPDATE ingestion_queue SET acquisition=%s WHERE id=%s "
                    "AND status='completed' AND acquisition IS NULL",
                    (acquisition, identifier),
                )
            else:
                cursor = await self.connection.execute(
                    "UPDATE ingestion_queue SET entry=%s,feed_text=%s,acquisition=%s,"
                    "acquired_at=clock_timestamp(),updated_at=clock_timestamp() "
                    "WHERE id=%s AND status='completed' AND acquisition IS NULL",
                    (Jsonb(entry.model_dump(mode="json")), feed_text, acquisition, identifier),
                )
            return cursor.rowcount == 1

    async def counts(self) -> dict[str, int]:
        row = await (
            await self.connection.execute(
                "SELECT (SELECT count(*) FROM ingestion_queue WHERE status='pending'), "
                "(SELECT count(*) FROM quarantine WHERE disposition='rejected'), "
                "(SELECT count(*) FROM quarantine WHERE disposition='deferred')"
            )
        ).fetchone()
        if row is None or any(not isinstance(value, int) for value in row):
            raise IngestionFailure("invalid_database_counts")
        result: dict[str, int] = {}
        for name, value in zip(("pending", "rejected", "deferred"), row, strict=True):
            if not isinstance(value, int):
                raise IngestionFailure("invalid_database_counts")
            result[name] = value
        return result

    async def source_statistics(self, source: str, correlation: str) -> dict[str, int]:
        row = await (
            await self.connection.execute(
                "SELECT counts FROM feed_sources WHERE id=%s AND last_run=%s",
                (source, correlation),
            )
        ).fetchone()
        if row is None or not isinstance(row[0], dict):
            raise IngestionFailure("source_run_changed")
        expected = source_counts()
        result: dict[str, int] = {}
        for key in expected:
            value = row[0].get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise IngestionFailure("invalid_source_counts")
            result[key] = value
        return result
