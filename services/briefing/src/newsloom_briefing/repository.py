"""Serialized publication and metadata-only operation accounting."""

import hashlib
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from newsloom_core.briefing import Briefing, BriefingContract
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field

LOCK_ID = 736981085


class Evidence(BriefingContract):
    id: UUID
    title: Annotated[str, Field(min_length=1, max_length=1000)] = Field(repr=False)
    summary: Annotated[str, Field(min_length=1, max_length=16000)] = Field(repr=False)
    source: str
    category: str
    published_at: datetime
    url: str = Field(repr=False)


class Repository:
    def __init__(self, connection: AsyncConnection[tuple[object, ...]]) -> None:
        self.connection = connection

    async def claim(self, cutoff: datetime, prompt_revision: str, model: str, version: str) -> bool:
        lock = await self.connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,))
        row = await lock.fetchone()
        if row is None or row[0] is not True:
            return False
        # Owning the session lock proves that an earlier running slot has no live owner.
        await self.connection.execute(
            "UPDATE public.briefing_runs SET status='failed',finished_at=clock_timestamp(),"
            "error_category='worker_lost' WHERE status='running'"
        )
        await self.connection.execute(
            "UPDATE public.briefing_calls SET status='unknown' WHERE status='pending'"
        )
        current = await self.connection.execute(
            "INSERT INTO public.briefing_runs"
            "(cutoff,status,started_at,prompt_revision,model,model_version) "
            "VALUES (%s,'running',clock_timestamp(),%s,%s,%s) "
            "ON CONFLICT (cutoff) DO NOTHING RETURNING cutoff",
            (cutoff, prompt_revision, model, version),
        )
        return await current.fetchone() is not None

    async def snapshot(self, start: datetime, end: datetime) -> AsyncGenerator[Evidence]:
        async with self.connection.transaction():
            await self.connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            async with self.connection.cursor(
                name="briefing_snapshot", row_factory=dict_row
            ) as cursor:
                await cursor.execute(
                    "SELECT id,title,summary,source,category,published_at,canonical_url AS url "
                    "FROM public.news WHERE published_at>=%s AND published_at<%s "
                    "ORDER BY published_at DESC,id ASC",
                    (start, end),
                )
                async for row in cursor:
                    yield Evidence.model_validate(row)

    async def evidence(self, cutoff: datetime, items: list[Evidence]) -> None:
        digest = hashlib.sha256()
        for item in items:
            digest.update(item.model_dump_json().encode() + b"\n")
        await self.connection.execute(
            "UPDATE public.briefing_runs SET evidence_count=%s,evidence_sha256=%s WHERE cutoff=%s",
            (len(items), digest.hexdigest(), cutoff),
        )

    async def intent(self, cutoff: datetime, ordinal: int, stage: str, price_basis: str) -> None:
        await self.connection.execute(
            "INSERT INTO public.briefing_calls(cutoff,ordinal,stage,status,price_basis) "
            "VALUES (%s,%s,%s,'pending',%s)",
            (cutoff, ordinal, stage, price_basis),
        )

    async def usage(
        self,
        cutoff: datetime,
        ordinal: int,
        state: Literal["completed", "unknown"],
        input_tokens: int | None,
        output_tokens: int | None,
        elapsed: float,
        cost: Decimal | None,
    ) -> None:
        await self.connection.execute(
            "UPDATE public.briefing_calls SET status=%s,input_tokens=%s,output_tokens=%s,"
            "elapsed_seconds=%s,estimated_cost_usd=%s WHERE cutoff=%s AND ordinal=%s",
            (state, input_tokens, output_tokens, elapsed, cost, cutoff, ordinal),
        )

    async def publish(self, artifact: Briefing) -> None:
        validated = Briefing.model_validate_json(artifact.model_dump_json())
        async with self.connection.transaction():
            await self.connection.execute(
                "INSERT INTO public.briefing_current(singleton,cutoff,payload) VALUES(true,%s,%s)"
                " ON CONFLICT(singleton) DO UPDATE "
                "SET cutoff=excluded.cutoff,payload=excluded.payload",
                (validated.window_end, Jsonb(json.loads(validated.model_dump_json()))),
            )
            await self.connection.execute(
                "UPDATE public.briefing_runs SET status='ready',finished_at=clock_timestamp() "
                "WHERE cutoff=%s AND status='running'",
                (validated.window_end,),
            )

    async def fail(self, cutoff: datetime, category: str) -> None:
        async with self.connection.transaction():
            await self.connection.execute(
                "UPDATE public.briefing_calls SET status='unknown' "
                "WHERE cutoff=%s AND status='pending'",
                (cutoff,),
            )
            await self.connection.execute(
                "UPDATE public.briefing_runs SET status='failed',finished_at=clock_timestamp(),"
                "error_category=%s WHERE cutoff=%s AND status='running'",
                (category, cutoff),
            )
