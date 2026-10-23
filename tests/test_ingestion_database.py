from collections.abc import AsyncIterator

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_ingestion.job import ingest_source, run
from newsloom_ingestion.models import (
    DEFAULT_LIMITS,
    Decision,
    Document,
    Entry,
    IngestionFailure,
    Limits,
)
from newsloom_ingestion.parsing import parse
from newsloom_ingestion.repository import Repository
from newsloom_ingestion.retrieval import PublicClient
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from test_ingestion_feeds import NOW, rss, source
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration


@pytest.fixture
async def repository(platform_database: RuntimeConfig) -> AsyncIterator[Repository]:
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            await connection.execute("SET ROLE newsloom_ingestion")
            repo = Repository(connection, "Microsoft-Decision-1", "1")
            await repo.acquire()
            await repo.source(source())
            yield repo
            await repo.release()


def entry() -> Entry:
    return parse(source(), rss(), str(source().url), NOW)[0][0]


async def test_stage_accept_and_global_deduplication(repository: Repository) -> None:
    item = entry()
    assert await repository.stage(item, "first-run")
    assert not await repository.stage(item, "second-run")
    pending = await repository.deferred([item.source])
    assert pending is not None
    await repository.decide(
        pending[0], item, Decision("accepted", "screened", 0.1, 0.5), "first-run"
    )
    assert await repository.counts() == {"pending": 1, "rejected": 0, "deferred": 0}
    assert not await repository.stage(item.model_copy(update={"guid": "different"}), "third-run")
    assert not await repository.stage(
        item.model_copy(update={"url": "https://example.com/new-url"}), "fourth-run"
    )
    row = await (
        await repository.connection.execute(
            "SELECT disposition, entry, resolved_queue_id IS NOT NULL FROM quarantine"
        )
    ).fetchone()
    assert row == ("resolved", {}, True)


async def test_rejected_entries_are_retained_not_accepted(repository: Repository) -> None:
    item = entry()
    await repository.stage(item, "run")
    pending = await repository.deferred([item.source])
    assert pending is not None
    await repository.decide(
        pending[0], item, Decision("rejected", "prompt_injection", 0.9, 0.5), "run"
    )
    assert await repository.counts() == {"pending": 0, "rejected": 1, "deferred": 0}
    assert await repository.deferred([item.source]) is None
    assert not await repository.stage(item, "rerun")
    with pytest.raises(IngestionFailure, match="screening_state_changed"):
        await repository.decide(pending[0], item, Decision("accepted", "screened", 0.1, 0.5), "run")


async def test_deferred_retry_ignores_http_validator_and_recovers(repository: Repository) -> None:
    item = entry()
    await repository.stage(item, "first")
    pending = await repository.deferred([item.source])
    assert pending is not None
    await repository.decide(pending[0], item, Decision("deferred", "scanner_unavailable"), "first")
    assert await repository.deferred([item.source]) is None
    await repository.connection.execute("UPDATE quarantine SET retry_after=clock_timestamp()")
    retry = await repository.deferred([item.source])
    assert retry is not None
    await repository.decide(retry[0], item, Decision("accepted", "screened", 0.2, 0.5), "retry")
    assert await repository.counts() == {"pending": 1, "rejected": 0, "deferred": 0}


async def test_empty_failed_fetch_does_not_replace_validators(repository: Repository) -> None:
    await repository.finish_source(source().id, "run", "fetched", {"found": 1}, {"etag": "old"})
    assert await repository.source(source()) == {"If-None-Match": "old"}
    await repository.finish_source(source().id, "empty", "empty", {"found": 0})
    assert await repository.source(source()) == {"If-None-Match": "old"}
    await repository.finish_source(source().id, "failed", "failed", {"found": 1})
    assert await repository.source(source()) == {"If-None-Match": "old"}


async def test_accept_transaction_rolls_back_without_losing_deferred(
    repository: Repository,
) -> None:
    item = entry()
    await repository.stage(item, "run")
    pending = await repository.deferred([item.source])
    assert pending is not None
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        async with repository.connection.transaction():
            await repository.decide(
                pending[0], item, Decision("accepted", "screened", 0.1, 0.5), "run"
            )
            raise RuntimeError("synthetic interruption")
    assert await repository.counts() == {"pending": 0, "rejected": 0, "deferred": 1}


async def test_distinct_anchored_entries_persist_and_repeat_without_duplicates(
    repository: Repository,
) -> None:
    first = entry().model_copy(update={"guid": "one", "url": "https://example.com/releases#one"})
    second = first.model_copy(update={"guid": "two", "url": "https://example.com/releases#two"})
    for item in (first, second):
        assert await repository.stage(item, "first")
        pending = await repository.deferred([item.source])
        assert pending is not None
        await repository.decide(
            pending[0], item, Decision("accepted", "screened", 0.1, 0.5), "first"
        )
    for item in (first, second):
        assert not await repository.stage(item, "forced")
    assert (await repository.counts())["pending"] == 2


async def test_ingestion_role_cannot_create_or_delete_quarantine(repository: Repository) -> None:
    for sql in ("CREATE TABLE public.unowned(id int)", "DELETE FROM quarantine"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with repository.connection.transaction():
                await repository.connection.execute(sql)


@pytest.mark.parametrize(
    "score,threshold,status", [(1.1, 0.5, "pending"), (0.1, -0.1, "pending"), (0.1, 0.5, "done")]
)
async def test_sql_constraints_reject_invalid_accepted_rows(
    repository: Repository,
    score: float,
    threshold: float,
    status: str,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        async with repository.connection.transaction():
            await repository.connection.execute(
                "INSERT INTO ingestion_queue(source,canonical_url,entry,score,threshold,status,"
                "model,model_version,correlation_id) VALUES (%s,%s,'{}',%s,%s,%s,%s,%s,%s)",
                (
                    source().id,
                    "https://example.com/fixture",
                    score,
                    threshold,
                    status,
                    "Microsoft-Decision-1",
                    "1",
                    "fixture",
                ),
            )
    assert (await repository.counts())["pending"] == 0


async def test_overlapping_run_is_rejected_and_lock_recovers(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as other,
    ):
        second = Repository(other, "Microsoft-Decision-1", "1")
        with pytest.raises(IngestionFailure, match="already_running"):
            await second.acquire()
        await repository.release()
        await second.acquire()
        await second.release()
        await repository.acquire()


async def test_conditional_force_empty_and_304_pipeline(repository: Repository) -> None:
    class Client(PublicClient):
        def __init__(self) -> None:
            super().__init__()
            self.status = 200
            self.body = rss()
            self.headers: list[dict[str, str]] = []

        async def fetch(
            self, url: str, headers: dict[str, str], deadline: float, *, robots: bool = False
        ) -> Document:
            self.headers.append(headers)
            return Document(self.status, url, self.body, {"etag": "fixture-validator"})

    client = Client()
    first = await ingest_source(source(), client, repository, "first", False, DEFAULT_LIMITS)
    assert first["staged"] == 1
    client.status = 304
    assert (await ingest_source(source(), client, repository, "repeat", False, DEFAULT_LIMITS))[
        "feeds_ok"
    ] == 1
    assert client.headers[-1] == {"If-None-Match": "fixture-validator"}
    client.status = 200
    assert (await ingest_source(source(), client, repository, "forced", True, DEFAULT_LIMITS))[
        "duplicates"
    ] == 1
    assert client.headers[-1] == {}
    client.body = b"<rss><channel/></rss>"
    assert (await ingest_source(source(), client, repository, "empty", True, DEFAULT_LIMITS))[
        "found"
    ] == 0
    assert await repository.source(source()) == {"If-None-Match": "fixture-validator"}
    assert await repository.deferred(["other-feed"]) is None
    assert await repository.deferred([source().id]) is not None


async def test_fixture_job_writes_and_logs_only_counts(
    repository: Repository,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    platform_database: RuntimeConfig,
) -> None:
    from newsloom_ingestion import job

    await repository.release()

    class Client(PublicClient):
        async def fetch(
            self, url: str, headers: dict[str, str], deadline: float, *, robots: bool = False
        ) -> Document:
            return Document(200, url, rss("NEWSLOOM_CONTENT_CANARY"), {"etag": "fixture"})

    class Scanner:
        async def scan(self, item: Entry, deadline: float) -> Decision:
            assert "NEWSLOOM_CONTENT_CANARY" in item.text
            return Decision("accepted", "screened", 0.1, 0.5)

    monkeypatch.setattr(job, "PublicClient", Client)
    counts = await run((source(),), repository, Scanner(), "fixture")
    assert counts["pending"] == counts["accepted_run"] == counts["found"] == 1
    async with ManagedIdentityCredential() as credential:
        readback = await database.ingestion_status(platform_database, credential)
        source_rows = await database.ingestion_sources(platform_database, credential)
    assert readback["pending"] == readback["screened_pending"] == 1
    assert source_rows == [(source().id, "fetched", 1, 0, 0, 1)]
    assert readback["duplicate_urls"] == readback["duplicate_guids"] == 0
    assert "NEWSLOOM_CONTENT_CANARY" not in capsys.readouterr().out
    await repository.acquire()


async def test_feed_deadline_does_not_advance_validator(repository: Repository) -> None:
    import asyncio

    class Slow(PublicClient):
        async def fetch(
            self, url: str, headers: dict[str, str], deadline: float, *, robots: bool = False
        ) -> Document:
            await asyncio.sleep(0.1)
            return Document(200, url, rss(), {"etag": "not-committed"})

    counts = await ingest_source(
        source(), Slow(), repository, "deadline", False, Limits(feed_seconds=0.01)
    )
    assert counts["feeds_failed"] == 1
    assert await repository.source(source()) == {}


async def test_four_feed_concurrency_is_bounded(
    repository: Repository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from newsloom_ingestion import job

    active = 0
    maximum = 0

    class Client(PublicClient):
        async def fetch(
            self, url: str, headers: dict[str, str], deadline: float, *, robots: bool = False
        ) -> Document:
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            try:
                await asyncio.sleep(0.02)
                return Document(200, url, rss(), {})
            finally:
                active -= 1

    class Scanner:
        async def scan(self, item: Entry, deadline: float) -> Decision:
            return Decision("accepted", "screened", 0.1, 0.5)

    monkeypatch.setattr(job, "PublicClient", Client)
    sources = tuple(source().model_copy(update={"id": f"feed-{i}"}) for i in range(5))
    await repository.release()
    try:
        counts = await run(sources, repository, Scanner(), "bounded")
        assert counts["feeds_ok"] == 5 and maximum == 4 and active == 0
    finally:
        await repository.acquire()
