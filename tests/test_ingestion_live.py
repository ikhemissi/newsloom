"""Explicit opt-in two-publisher smoke; fixture verdicts are not model acceptance."""

import os
from pathlib import Path

import pytest
from newsloom_core.feeds import load_feed_catalogue
from newsloom_ingestion.job import run, select_sources
from newsloom_ingestion.models import Decision, Entry
from newsloom_ingestion.repository import Repository
from test_ingestion_database import repository as repository
from test_platform_database import platform_database as platform_database

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("NEWSLOOM_LIVE_INGESTION") != "1",
        reason="Live publishers are excluded from normal local checks and CI",
    ),
]


async def test_one_live_rss_one_live_atom_persist(repository: Repository) -> None:
    class FixtureScanner:
        async def scan(self, entry: Entry, deadline: float) -> Decision:
            return Decision("accepted", "screened", 0.1, 0.5)

    sources = select_sources(
        load_feed_catalogue(Path("config/feeds.json")),
        [
            "microsoft-foundry-devblog",
            "vertex-ai-release-notes",
        ],
    )
    assert len(sources) == 2 and {source.kind for source in sources} == {"rss", "atom"}
    await repository.release()
    try:
        counts = await run(sources, repository, FixtureScanner(), "local-live-fixture")
        assert counts["feeds_ok"] == 2 and counts["feeds_failed"] == 0
        assert counts["found"] > 0 and counts["pending"] > 0
        assert counts["pending"] == counts["found"] - counts["filtered"]
        assert counts["duplicates"] == 0
        for source in sources:
            row = await (
                await repository.connection.execute(
                    "SELECT outcome,(counts->>'found')::int, "
                    "(SELECT count(*) FROM ingestion_queue WHERE source=feed_sources.id) "
                    "FROM feed_sources WHERE id=%s",
                    (source.id,),
                )
            ).fetchone()
            assert (
                row is not None
                and row[0] == "fetched"
                and isinstance(row[1], int)
                and row[1] > 0
                and row[1] == row[2]
            )
        repeated = await run(sources, repository, FixtureScanner(), "local-live-forced", force=True)
        assert repeated["staged"] == repeated["accepted_run"] == 0
        assert repeated["duplicates"] == repeated["found"]
        assert repeated["pending"] == counts["pending"]
    finally:
        await repository.acquire()
