from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_briefing.cli import verify_access
from newsloom_briefing.generation import PROMPT_REVISION, synthesize
from newsloom_briefing.repository import Repository, RevisionRefused
from newsloom_core.briefing import Briefing
from newsloom_enrichment.repository import Repository as EnrichmentRepository
from newsloom_mcp.briefing import read_briefing
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from test_briefing import Scripted
from test_enrichment_database import METADATA, enriched, seed, vector
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration


async def test_real_snapshot_roles_once_only_publication_and_recovery(
    platform_database: RuntimeConfig,
) -> None:
    cutoff = datetime(2026, 11, 2, 5, tzinfo=UTC)
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        await seed(platform_database, count=227)
        async with (
            await database.connect(
                platform_database, credential, "newsloom", "postgres"
            ) as connection,
            await database.connect(
                platform_database, credential, "newsloom", "postgres"
            ) as concurrent,
        ):
            await connection.execute(
                "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='newsloom_briefing') "
                "THEN CREATE ROLE newsloom_briefing LOGIN; END IF; END $$"
            )
            await connection.execute(database.migration_sql("005_briefing.sql"))
            enrichment = EnrichmentRepository(connection)
            for _ in range(227):
                claim = await enrichment.claim("seed")
                assert claim is not None
                await enrichment.complete(claim, enriched(), vector(), METADATA, "seed")
            await connection.execute(
                "UPDATE news SET title=%s,summary=%s,published_at=%s",
                (
                    "Authored event",
                    "Authored evidence of a published event.",
                    cutoff - timedelta(days=7),
                ),
            )
            ids = await (await connection.execute("SELECT id FROM news ORDER BY id")).fetchall()
            excluded = ids[-1][0]
            await connection.execute(
                "UPDATE news SET published_at=%s WHERE id=%s", (cutoff, excluded)
            )
            await connection.execute(
                "UPDATE news SET published_at=%s WHERE id=%s",
                (cutoff - timedelta(days=7, microseconds=1), ids[-2][0]),
            )
            await connection.execute("SET SESSION AUTHORIZATION newsloom_briefing")
            writer = Repository(connection)
            await verify_access(connection, "authored-access-probe")
            assert await writer.claim(cutoff, PROMPT_REVISION, "authored", "1")
            await concurrent.execute("SET SESSION AUTHORIZATION newsloom_briefing")
            assert not await Repository(concurrent).claim(cutoff, PROMPT_REVISION, "authored", "1")
            await concurrent.execute("RESET SESSION AUTHORIZATION")
            snapshot = writer.snapshot(cutoff - timedelta(days=7), cutoff)
            first = await anext(snapshot)
            await concurrent.execute(
                "UPDATE news SET published_at=%s WHERE id=%s",
                (cutoff - timedelta(days=1), excluded),
            )
            items = [first, *[item async for item in snapshot]]
            assert len(items) == 225 and all(item.id != excluded for item in items)
            await writer.evidence(cutoff, items)
            artifact = await synthesize(Scripted(items), items, cutoff, float("inf"))
            await writer.intent(cutoff, 1, "summary", "authored")
            await writer.usage(cutoff, 1, "completed", 50, 20, 1.0, Decimal("0.00009"))
            await writer.publish(artifact)
            assert not await writer.claim(cutoff, PROMPT_REVISION, "authored", "1")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await connection.execute("DELETE FROM news")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await connection.execute("CREATE TABLE public.briefing_forbidden(value int)")
            await concurrent.execute("SET SESSION AUTHORIZATION newsloom_mcp")
            read = await read_briefing(concurrent, cutoff)
            assert read.briefing == artifact and read.refresh.state == "ready"
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await concurrent.execute("UPDATE briefing_current SET payload='{}'::jsonb")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await concurrent.execute("SELECT * FROM briefing_calls")
            await concurrent.execute("RESET SESSION AUTHORIZATION")
            tomorrow = cutoff + timedelta(days=1)
            assert await writer.claim(tomorrow, PROMPT_REVISION, "authored", "1")
            await writer.intent(tomorrow, 1, "notes", "authored")
            await writer.fail(tomorrow, "authored_failure")
            assert not await writer.claim(tomorrow, PROMPT_REVISION, "authored", "1")
            await concurrent.execute("SET SESSION AUTHORIZATION newsloom_mcp")
            failed = await read_briefing(concurrent, tomorrow)
            assert failed.briefing == artifact and failed.refresh.stale
            assert failed.refresh.state == "failed"
            assert Briefing.model_validate_json(artifact.model_dump_json()) == artifact
            lost_slot = tomorrow + timedelta(days=1)
            assert await writer.claim(lost_slot, PROMPT_REVISION, "authored", "1")
            await writer.intent(lost_slot, 1, "notes", "authored")
            await connection.close()
            await concurrent.execute("RESET SESSION AUTHORIZATION")
            await concurrent.execute("SET SESSION AUTHORIZATION newsloom_briefing")
            recovered = Repository(concurrent)
            assert not await recovered.claim(lost_slot, PROMPT_REVISION, "authored", "1")
            lost = await (
                await concurrent.execute(
                    "SELECT status,error_category FROM briefing_runs WHERE cutoff=%s",
                    (lost_slot,),
                )
            ).fetchone()
            assert lost == ("failed", "worker_lost")
            unknown = await (
                await concurrent.execute(
                    "SELECT status,input_tokens,output_tokens FROM briefing_calls WHERE cutoff=%s",
                    (lost_slot,),
                )
            ).fetchone()
            assert unknown == ("unknown", None, None)


async def test_controlled_retry_archives_failure_without_resetting_calls_or_allowing_unknown_usage(
    platform_database: RuntimeConfig,
) -> None:
    cutoff = datetime(2026, 11, 3, 5, tzinfo=UTC)
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            await connection.execute(
                "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='newsloom_briefing') "
                "THEN CREATE ROLE newsloom_briefing LOGIN; END IF; END $$"
            )
            await connection.execute(database.migration_sql("005_briefing.sql"))
            await connection.execute(database.migration_sql("006_briefing_retry.sql"))
            await connection.execute("SET SESSION AUTHORIZATION newsloom_briefing")
            writer = Repository(connection)
            assert await writer.claim(cutoff, PROMPT_REVISION, "authored", "1")
            await writer.intent(cutoff, 1, "notes", "authored")
            await writer.usage(cutoff, 1, "completed", 50, 20, 1.0, Decimal("0.00009"))
            await writer.fail(cutoff, "briefing_foreign_citation")
            assert not await writer.claim(cutoff, PROMPT_REVISION, "authored", "1")
            assert await writer.retry_claim(cutoff, PROMPT_REVISION, "authored", "1") == 1
            assert await writer.retry_claim(cutoff, PROMPT_REVISION, "authored", "1") is None
            history = await (
                await connection.execute(
                    "SELECT failed_run->>'status',failed_run->>'error_category',last_call_ordinal "
                    "FROM briefing_attempts WHERE cutoff=%s",
                    (cutoff,),
                )
            ).fetchone()
            assert history == ("failed", "briefing_foreign_citation", 1)
            prior = await (
                await connection.execute(
                    "SELECT input_tokens,output_tokens,estimated_cost_usd "
                    "FROM briefing_calls WHERE cutoff=%s AND ordinal=1",
                    (cutoff,),
                )
            ).fetchone()
            assert prior == (50, 20, Decimal("0.00009"))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await connection.execute("DELETE FROM briefing_attempts")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await connection.execute("UPDATE briefing_attempts SET last_call_ordinal=0")
            await writer.intent(cutoff, 2, "notes", "authored")
            await writer.fail(cutoff, "briefing_foreign_citation")
            assert await writer.retry_claim(cutoff, PROMPT_REVISION, "authored", "1") is None
            unknown = await (
                await connection.execute(
                    "SELECT status FROM briefing_calls WHERE cutoff=%s AND ordinal=2",
                    (cutoff,),
                )
            ).fetchone()
            assert unknown == ("unknown",)
            assert await (
                await connection.execute("SELECT count(*) FROM briefing_attempts")
            ).fetchone() == (1,)
            earlier = cutoff - timedelta(days=1)
            assert await writer.claim(earlier, PROMPT_REVISION, "authored", "1")
            await writer.publish(
                Briefing(
                    version=uuid4(),
                    window_start=earlier - timedelta(days=7),
                    window_end=earlier,
                    generated_at=datetime.now(UTC),
                    coverage="empty",
                    evidence_count=0,
                    tldr=None,
                    sections=(),
                    citations=(),
                )
            )
            assert await writer.retry_claim(earlier, PROMPT_REVISION, "authored", "1") is None
            assert not await writer.claim(earlier, PROMPT_REVISION, "authored", "1")


def empty_briefing(cutoff: datetime) -> Briefing:
    return Briefing(
        version=uuid4(),
        window_start=cutoff - timedelta(days=7),
        window_end=cutoff,
        generated_at=datetime.now(UTC),
        coverage="empty",
        evidence_count=0,
        tldr=None,
        sections=(),
        citations=(),
    )


async def test_revision_preserves_success_accounting_and_publishes_only_against_its_base(
    platform_database: RuntimeConfig,
) -> None:
    cutoff = datetime(2026, 11, 1, 5, tzinfo=UTC)
    reason = "editorial-policy-upgrade"
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        async with (
            await database.connect(
                platform_database, credential, "newsloom", "postgres"
            ) as connection,
            await database.connect(platform_database, credential, "newsloom", "postgres") as other,
        ):
            await connection.execute(
                "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='newsloom_briefing') "
                "THEN CREATE ROLE newsloom_briefing LOGIN; END IF; END $$"
            )
            for name in ("005_briefing", "006_briefing_retry", "007_briefing_revisions"):
                await connection.execute(database.migration_sql(f"{name}.sql"))
            await connection.execute("SET SESSION AUTHORIZATION newsloom_briefing")
            writer = Repository(connection)
            assert await writer.claim(cutoff, PROMPT_REVISION, "authored", "1")
            await writer.intent(cutoff, 1, "summary", "authored")
            await writer.usage(cutoff, 1, "completed", 50, 20, 1.0, Decimal("0.00009"))
            original = empty_briefing(cutoff)
            await writer.publish(original)
            assert not await writer.claim(cutoff, PROMPT_REVISION, "authored", "1")
            assert await writer.retry_claim(cutoff, PROMPT_REVISION, "authored", "1") is None
            with pytest.raises(RevisionRefused, match="stale_version"):
                await writer.revise_claim(
                    cutoff, uuid4(), uuid4(), reason, PROMPT_REVISION, "authored", "1"
                )
            await other.execute("SET SESSION AUTHORIZATION newsloom_briefing")
            with pytest.raises(RevisionRefused, match="busy"):
                await Repository(other).revise_claim(
                    cutoff, uuid4(), original.version, reason, PROMPT_REVISION, "authored", "1"
                )
            await other.execute("RESET SESSION AUTHORIZATION")
            request = uuid4()
            assert (
                await writer.revise_claim(
                    cutoff, request, original.version, reason, PROMPT_REVISION, "authored", "1"
                )
                == 1
            )
            audit = await (
                await connection.execute(
                    "SELECT base_version,last_call_ordinal,prior_run->>'status',"
                    "prior_payload->>'version' FROM briefing_revisions WHERE request_id=%s",
                    (request,),
                )
            ).fetchone()
            assert audit == (original.version, 1, "ready", str(original.version))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await connection.execute("UPDATE briefing_revisions SET last_call_ordinal=0")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await connection.execute("DELETE FROM briefing_revisions")
            await other.execute("SET SESSION AUTHORIZATION newsloom_mcp")
            assert (await read_briefing(other, cutoff)).briefing == original
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await other.execute("SELECT * FROM briefing_revisions")
            await other.execute("RESET SESSION AUTHORIZATION")
            await writer.intent(cutoff, 2, "summary", "authored")
            await writer.usage(cutoff, 2, "completed", 60, 30, 1.0, Decimal("0.0001"))
            with pytest.raises(RevisionRefused, match="base_changed"):
                await writer.publish(empty_briefing(cutoff), uuid4())
            await writer.fail(cutoff, "briefing_foreign_citation")
            current = await (
                await connection.execute("SELECT payload->>'version' FROM briefing_current")
            ).fetchone()
            assert current == (str(original.version),)
            with pytest.raises(RevisionRefused, match="request_exists"):
                await writer.revise_claim(
                    cutoff, request, original.version, reason, PROMPT_REVISION, "authored", "1"
                )
            second = uuid4()
            assert (
                await writer.revise_claim(
                    cutoff, second, original.version, reason, PROMPT_REVISION, "authored", "1"
                )
                == 2
            )
            replacement = empty_briefing(cutoff)
            await writer.publish(replacement, original.version)
            await other.execute("SET SESSION AUTHORIZATION newsloom_mcp")
            read = await read_briefing(other, cutoff)
            assert read.briefing == replacement and read.refresh.state == "ready"
            await other.execute("RESET SESSION AUTHORIZATION")
            calls = await (
                await connection.execute(
                    "SELECT ordinal,input_tokens FROM briefing_calls WHERE cutoff=%s "
                    "ORDER BY ordinal",
                    (cutoff,),
                )
            ).fetchall()
            assert calls == [(1, 50), (2, 60)]
            await writer.intent(cutoff, 3, "summary", "authored")
            third = uuid4()
            await connection.execute(
                "UPDATE briefing_runs SET status='failed',finished_at=clock_timestamp(),"
                "error_category='briefing_foreign_citation' WHERE cutoff=%s",
                (cutoff,),
            )
            with pytest.raises(RevisionRefused, match="unknown_usage"):
                await writer.revise_claim(
                    cutoff, third, replacement.version, reason, PROMPT_REVISION, "authored", "1"
                )


async def test_revision_supersedes_known_failed_slot_while_older_report_stays_published(
    platform_database: RuntimeConfig,
) -> None:
    earlier = datetime(2026, 11, 1, 5, tzinfo=UTC)
    today = earlier + timedelta(days=1)
    reason = "editorial-policy-upgrade"
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            await connection.execute(
                "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='newsloom_briefing') "
                "THEN CREATE ROLE newsloom_briefing LOGIN; END IF; END $$"
            )
            for name in ("005_briefing", "006_briefing_retry", "007_briefing_revisions"):
                await connection.execute(database.migration_sql(f"{name}.sql"))
            await connection.execute("SET SESSION AUTHORIZATION newsloom_briefing")
            writer = Repository(connection)
            assert await writer.claim(earlier, PROMPT_REVISION, "authored", "1")
            published = empty_briefing(earlier)
            await writer.publish(published)
            assert await writer.claim(today, PROMPT_REVISION, "authored", "1")
            await writer.intent(today, 1, "notes", "authored")
            await writer.usage(today, 1, "completed", 40, 10, 1.0, Decimal("0.00005"))
            await writer.fail(today, "briefing_unsupported_fact")
            assert await writer.retry_claim(today, PROMPT_REVISION, "authored", "1") is None
            request = uuid4()
            assert (
                await writer.revise_claim(
                    today, request, published.version, reason, PROMPT_REVISION, "authored", "1"
                )
                == 1
            )
            audit = await (
                await connection.execute(
                    "SELECT prior_run->>'status',prior_run->>'error_category',"
                    "prior_payload->>'version' FROM briefing_revisions WHERE request_id=%s",
                    (request,),
                )
            ).fetchone()
            assert audit == ("failed", "briefing_unsupported_fact", str(published.version))
            replacement = empty_briefing(today)
            await writer.publish(replacement, published.version)
            current = await (
                await connection.execute("SELECT cutoff,payload->>'version' FROM briefing_current")
            ).fetchone()
            assert current == (today, str(replacement.version))
