import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_mcp.feedback import FeedbackInput, FeedbackRepository, ReviewQuery, reader_hash
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from psycopg.types.json import Jsonb
from test_briefing_database import empty_briefing
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration

SNAPSHOT = {"question": "Q", "answer": {"outcome": "supported"}, "citations": [], "filters": {}}


async def test_feedback_is_insert_only_and_latest_vote_wins(
    platform_database: RuntimeConfig,
) -> None:
    cutoff = datetime(2026, 11, 1, 5, tzinfo=UTC)
    published = empty_briefing(cutoff)
    first = reader_hash(UUID(int=1), UUID(int=2))
    second = reader_hash(UUID(int=1), UUID(int=3))
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            await connection.execute(
                "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='newsloom_briefing') "
                "THEN CREATE ROLE newsloom_briefing LOGIN; END IF; END $$"
            )
            for name in (
                "005_briefing",
                "006_briefing_retry",
                "007_briefing_revisions",
                "008_briefing_history",
            ):
                await connection.execute(database.migration_sql(f"{name}.sql"))
            await connection.execute(
                "INSERT INTO briefing_history(version,cutoff,payload) VALUES (%s,%s,%s)",
                (published.version, cutoff, Jsonb(json.loads(published.model_dump_json()))),
            )
            await connection.execute("SET SESSION AUTHORIZATION newsloom_mcp")
            store = FeedbackRepository(connection)

            def vote(rating: str, comment: str | None = None, ref: str = "") -> FeedbackInput:
                return FeedbackInput.model_validate(
                    {
                        "target_type": "briefing",
                        "target_ref": ref or str(published.version),
                        "rating": rating,
                        "comment": comment,
                    }
                )

            assert await store.record(first, vote("down", "dull"))
            assert await store.record(first, vote("up"))
            assert await store.record(second, vote("down"))
            assert not await store.record(first, vote("down", ref=str(UUID(int=99))))
            research = FeedbackInput.model_validate(
                {
                    "target_type": "research",
                    "target_ref": "task-1",
                    "rating": "down",
                    "snapshot": SNAPSHOT,
                }
            )
            assert await store.record(first, research)
            mine = await store.mine(first, "briefing", str(published.version))
            assert mine is not None and mine.rating == "up"
            downs = await store.review(ReviewQuery(rating="down"))
            assert sorted(item.target_ref for item in downs) == sorted(
                [str(published.version), "task-1"]
            )
            assert all(item.created_at > datetime.now(UTC) - timedelta(minutes=5) for item in downs)
            research_rows = await store.review(ReviewQuery(target_type="research"))
            assert research_rows[0].snapshot == SNAPSHOT
            for statement in ("UPDATE feedback SET rating=1", "DELETE FROM feedback"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    await connection.execute(statement)
            with pytest.raises(psycopg.errors.CheckViolation):
                await connection.execute(
                    "INSERT INTO feedback(reader_hash,target_type,target_ref,rating) "
                    "VALUES (%s,'research','task-2',-1)",
                    (first,),
                )
