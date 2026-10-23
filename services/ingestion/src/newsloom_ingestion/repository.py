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
    async def stage(self, entry: Entry, correlation: str) -> bool: ...

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

    async def stage(self, entry: Entry, correlation: str) -> bool:
        async with self.lock, self.connection.transaction():
            if await self._known(entry):
                return False
            await self.connection.execute(
                "INSERT INTO quarantine(source, guid, canonical_url, entry, disposition, reason, "
                "model, model_version, correlation_id) "
                "VALUES (%s,%s,%s,%s,'deferred','awaiting_screening',%s,%s,%s)",
                (
                    entry.source,
                    entry.guid,
                    entry.url,
                    Jsonb(entry.model_dump(mode="json")),
                    self.model,
                    self.version,
                    correlation,
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
                    "SELECT disposition FROM quarantine WHERE id=%s FOR UPDATE", (identifier,)
                )
            ).fetchone()
            if row != ("deferred",):
                raise IngestionFailure("screening_state_changed")
            if decision.disposition == "accepted":
                cursor = await self.connection.execute(
                    "INSERT INTO ingestion_queue(source,guid,canonical_url,entry,score,threshold,"
                    "model,model_version,correlation_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
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
                    ),
                )
                accepted = await cursor.fetchone()
                if accepted is None:
                    raise IngestionFailure("accepted_row_missing")
                await self.connection.execute(
                    "UPDATE quarantine SET disposition='resolved', reason='accepted', "
                    "entry='{}', resolved_queue_id=%s, updated_at=clock_timestamp(), "
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

    async def counts(self) -> dict[str, int]:
        row = await (
            await self.connection.execute(
                "SELECT (SELECT count(*) FROM ingestion_queue), "
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
