from collections.abc import AsyncIterator
from datetime import timedelta

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.categories import Category
from newsloom_core.entries import Entry
from newsloom_enrichment.models import Enrichment, EnrichmentFailure, Vector
from newsloom_enrichment.repository import ModelMetadata, Repository
from newsloom_ingestion.models import Decision
from newsloom_ingestion.repository import Repository as IngestionRepository
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from test_ingestion_database import entry
from test_ingestion_feeds import source
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration
METADATA = ModelMetadata("gpt-test", "1", "embedding-test", "1", "a" * 64, "b" * 64)


def enriched() -> Enrichment:
    return Enrichment(
        summary_sentences=("A developer released Nova.", "It adds asynchronous requests."),
        category=Category.DEVELOPER_TOOLS,
        tags=("sdk", "async", "software"),
    )


def vector() -> Vector:
    return Vector(values=(0.1,) * 1536)


async def seed(config: RuntimeConfig, count: int = 1, offset: int = 0) -> list[Entry]:
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(config, credential, "newsloom", "postgres") as connection,
    ):
        await connection.execute("SET ROLE newsloom_ingestion")
        repo = IngestionRepository(connection, "Microsoft-Decision-1", "1")
        await repo.source(source(), "fixture")
        entries = [
            entry().model_copy(
                update={"guid": f"entry-{index}", "url": f"https://example.com/entry-{index}"}
            )
            for index in range(offset, offset + count)
        ]
        for item in entries:
            assert await repo.stage(item, "fixture")
            pending = await repo.deferred([item.source])
            assert pending is not None
            await repo.decide(
                pending[0], item, Decision("accepted", "screened", 0.1, 0.5), "fixture"
            )
        return entries


@pytest.fixture
async def repository(platform_database: RuntimeConfig) -> AsyncIterator[Repository]:
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        await seed(platform_database)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            await connection.execute("SET ROLE newsloom_enrichment")
            yield Repository(connection)


async def test_migration_preserves_existing_ingestion_and_replays(
    platform_database: RuntimeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = database.record

    async def stop_before_enrichment(
        connection: psycopg.AsyncConnection[tuple[object, ...]], version: str, checksum: str
    ) -> None:
        if version == "003_enrichment":
            raise RuntimeError("synthetic migration interruption")
        await original(connection, version, checksum)

    monkeypatch.setattr(database, "record", stop_before_enrichment)
    async with ManagedIdentityCredential() as credential:
        with pytest.raises(RuntimeError):
            await database.migrate(platform_database, credential)
        entries = await seed(platform_database)
        monkeypatch.setattr(database, "record", original)
        assert await database.migrate(platform_database, credential) == 2
        assert await database.migrate(platform_database, credential) == 0
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            row = await (
                await connection.execute("SELECT entry,status,attempts FROM ingestion_queue")
            ).fetchone()
            assert row == (entries[0].model_dump(mode="json"), "pending", 0)
            assert await (
                await connection.execute("SELECT disposition FROM quarantine")
            ).fetchone() == ("resolved",)


async def test_complete_atomically_preserves_identity_and_pending_depth(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    claim = await repository.claim("run")
    assert claim is not None
    assert repository.connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
    await repository.complete(claim, enriched(), vector(), METADATA, "run")
    counts = await repository.counts()
    assert counts == {
        "pending": 0,
        "processing": 0,
        "completed": 1,
        "failed": 0,
        "dead_letter": 0,
        "news": 1,
    }
    assert await repository.claim("replay") is None
    with pytest.raises(EnrichmentFailure, match="lease_lost"):
        await repository.complete(claim, enriched(), vector(), METADATA, "stale")
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as connection,
    ):
        await connection.execute("SET ROLE newsloom_ingestion")
        ingestion = IngestionRepository(connection, "Microsoft-Decision-1", "1")
        assert await ingestion.known(claim.entry)
        assert (await ingestion.counts())["pending"] == 0
        assert not await ingestion.stage(claim.entry, "repeat")
        status = await database.ingestion_status(platform_database, credential)
        assert status["pending"] == status["screened_pending"] == 0
        status = await database.enrichment_status(platform_database, credential)
        assert status["completed"] == status["news"] == 1
        definition = await (
            await connection.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='news'::regclass AND conname='news_category_check'"
            )
        ).fetchone()
        assert definition is not None and isinstance(definition[0], str)
        assert all(f"'{category.value}'" in definition[0] for category in Category)
        assert await (
            await connection.execute(
                "SELECT count(*) FROM pg_indexes WHERE tablename='news' "
                "AND indexdef LIKE '%hnsw%vector_cosine_ops%'"
            )
        ).fetchone() == (1,)
        assert all(
            status[key] == 0
            for key in (
                "completion_mismatches",
                "completed_without_news",
                "invalid_vectors",
                "published_rejections",
                "duplicate_urls",
                "duplicate_guids",
            )
        )


async def test_concurrent_claims_are_disjoint(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    await seed(platform_database, count=1, offset=1)
    first = await repository.claim("first")
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as connection,
    ):
        await connection.execute("SET ROLE newsloom_enrichment")
        other = Repository(connection)
        second = await other.claim("second")
        assert first is not None and second is not None and first.id != second.id
        assert await other.claim("third") is None


async def test_expired_claim_is_recovered_and_both_stale_paths_fail(repository: Repository) -> None:
    first = await repository.claim("first")
    assert first is not None
    await repository.connection.execute(
        "UPDATE ingestion_queue SET lease_until=clock_timestamp()-interval '1 second'"
    )
    recovered = await repository.claim("recovered")
    assert recovered is not None and recovered.id == first.id
    assert recovered.token != first.token and recovered.attempts == 2
    with pytest.raises(EnrichmentFailure, match="lease_lost"):
        await repository.complete(first, enriched(), vector(), METADATA, "stale")
    with pytest.raises(EnrichmentFailure, match="lease_lost"):
        await repository.fail(first, "model_http_429", 0, "stale")
    await repository.complete(recovered, enriched(), vector(), METADATA, "recovered")
    assert (await repository.counts())["news"] == 1


async def test_retry_after_is_preserved_and_exhaustion_terminates(repository: Repository) -> None:
    claim = await repository.claim("first")
    assert claim is not None
    await repository.fail(claim, "model_http_429", 3600, "first")
    row = await (
        await repository.connection.execute(
            "SELECT status,last_error,retry_after-clock_timestamp() FROM ingestion_queue"
        )
    ).fetchone()
    assert row is not None and row[:2] == ("failed", "model_http_429")
    assert isinstance(row[2], timedelta) and row[2] > timedelta(minutes=59)
    assert await repository.claim("too-soon") is None
    await repository.connection.execute(
        "UPDATE ingestion_queue SET retry_after=clock_timestamp(),attempts=4"
    )
    last = await repository.claim("last")
    assert last is not None and last.attempts == 5
    await repository.fail(last, "invalid_generation", 0, "last")
    assert await repository.claim("exhausted") is None
    assert (await repository.counts())["dead_letter"] == 1


async def test_expired_last_attempt_does_not_become_orphaned(repository: Repository) -> None:
    assert await repository.claim("run") is not None
    await repository.connection.execute(
        "UPDATE ingestion_queue SET attempts=5,lease_until=clock_timestamp()-interval '1 second'"
    )
    assert await repository.claim("recover") is None
    assert (await repository.counts())["dead_letter"] == 1


async def test_completion_rolls_back_as_one_transaction(repository: Repository) -> None:
    claim = await repository.claim("run")
    assert claim is not None
    with pytest.raises(RuntimeError):
        async with repository.connection.transaction():
            await repository.complete(claim, enriched(), vector(), METADATA, "run")
            raise RuntimeError("synthetic interruption")
    counts = await repository.counts()
    assert counts["news"] == counts["completed"] == 0 and counts["processing"] == 1


async def test_expiry_during_insert_rolls_back_news(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        await admin.execute("""
            CREATE FUNCTION expire_test_claim() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                UPDATE ingestion_queue SET lease_until=clock_timestamp()-interval '1 second'
                WHERE id=NEW.id;
                RETURN NEW;
            END $$;
            CREATE TRIGGER expire_claim AFTER INSERT ON news
            FOR EACH ROW EXECUTE FUNCTION expire_test_claim();
        """)
    claim = await repository.claim("run")
    assert claim is not None
    with pytest.raises(EnrichmentFailure, match="lease_lost"):
        await repository.complete(claim, enriched(), vector(), METADATA, "run")
    counts = await repository.counts()
    assert counts["news"] == counts["completed"] == 0 and counts["processing"] == 1


async def test_runtime_grants_exclude_unowned_operations(repository: Repository) -> None:
    assert await repository.verify_access() == 8
    for query in (
        "SELECT * FROM quarantine",
        "INSERT INTO ingestion_queue DEFAULT VALUES",
        "UPDATE ingestion_queue SET entry='{}' WHERE false",
        "DELETE FROM news",
        "CREATE TABLE public.unowned(id int)",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with repository.connection.transaction():
                await repository.connection.execute(query)


async def test_news_vector_constraints_and_state_readbacks(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    claim = await repository.claim("run")
    assert claim is not None
    await repository.complete(claim, enriched(), vector(), METADATA, "run")
    await seed(platform_database, count=4, offset=1)
    for status in ("processing", "failed", "dead_letter"):
        claim = await repository.claim(status)
        assert claim is not None
        if status != "processing":
            if status == "dead_letter":
                await repository.connection.execute(
                    "UPDATE ingestion_queue SET attempts=5 WHERE id=%s", (claim.id,)
                )
            await repository.fail(claim, "synthetic_failure", 0, status)
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        for values in ([0.0] * 1536, [0.1] * 1535):
            with pytest.raises(psycopg.Error):
                async with admin.transaction():
                    await admin.execute(
                        "UPDATE news SET embedding=%s::vector",
                        ("[" + ",".join(map(str, values)) + "]",),
                    )
        counts = await database.enrichment_status(platform_database, credential)
        assert all(
            counts[key] == 1
            for key in ("pending", "processing", "failed", "dead_letter", "completed", "news")
        )
        assert (await database.ingestion_status(platform_database, credential))["pending"] == 1
