"""The snapshot stores answer like the database stores on the same data."""

import gzip
from datetime import UTC, datetime, timedelta

import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_enrichment.repository import Repository
from newsloom_mcp.feedback import FeedbackInput
from newsloom_mcp.http_models import Position
from newsloom_mcp.models import DetailInput, RecentInput, SearchInput
from newsloom_mcp.radar import CardInput, RadarRepository
from newsloom_mcp.repository import Repository as NewsRepository
from newsloom_mcp.snapshot import (
    ReadOnly,
    Snapshot,
    SnapshotFeedback,
    SnapshotNews,
    SnapshotRadar,
    build,
)
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from test_enrichment_database import METADATA, vector
from test_enrichment_graph import announcement, mention, repository, result
from test_platform_database import platform_database as platform_database
from test_radar_database import OTHER, READER, rated

pytestmark = pytest.mark.integration
assert repository is not None


async def test_snapshot_stores_match_the_database(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    items = [
        (result(announcement(mention("Azure AI Foundry", "Microsoft"))), rated("act_now")),
        (result(announcement(mention("Gadget", "Other"))), rated("act_now")),
        (result(announcement(mention("Widget", "Acme"))), ()),
    ]
    for value, ratings in items:
        claim = await repository.claim("snapshot")
        assert claim is not None
        await repository.complete(claim, value, vector(), METADATA, "snapshot", {}, ratings)
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        # Equal timestamps exercise the id tie-break of the continuation.
        await admin.execute("UPDATE news SET published_at=clock_timestamp()-interval '1 day'")
        await admin.execute("SET ROLE newsloom_mcp")
        live = RadarRepository(admin)
        microsoft = next(e for e in await live.search("Microsoft") if e.kind == "vendor")
        await live.set_stack(READER, (microsoft.id,))
        now = datetime.now(UTC)
        first = (await live.radar(READER, 7, now)).tiers["act_now"][0]
        assert first.kind == "card"
        await live.set_card(READER, first.card.id, CardInput(state="snoozed"))

        async with admin.transaction():
            await admin.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot = await build(admin, now)
        encoded = snapshot.encode()
        assert b"embedding" not in gzip.decompress(encoded)
        restored = Snapshot.decode(encoded)
        assert restored == snapshot

        radar = SnapshotRadar(restored)
        for reader in (READER, OTHER):
            for when in (now, now + timedelta(days=8)):
                assert await radar.radar(reader, 7, when) == await live.radar(reader, 7, when)
            assert await radar.stack(reader) == await live.stack(reader)
        foundry = next(e for e in await live.search("foundry") if e.kind == "product")
        assert await radar.product(foundry.id) == await live.product(foundry.id)

        news = SnapshotNews(restored)
        stored = NewsRepository(admin, "m", "v")
        page = SearchInput(limit=1)
        assert await news.browse(page, None) == await stored.browse(page, None)
        top = (await stored.browse(page, None)).items[0]
        after = Position(published_at=top.published_at, id=top.id)
        assert await news.browse(page, after) == await stored.browse(page, after)
        assert await news.recent(RecentInput(limit=5)) == await stored.recent(RecentInput(limit=5))
        assert await news.detail(DetailInput(id=top.id)) == await stored.detail(
            DetailInput(id=top.id)
        )
        assert await news.sources() == await stored.sources()
        assert await news.search(SearchInput(), None) == await stored.search(SearchInput(), None)

        with pytest.raises(ReadOnly):
            await news.search(SearchInput(query="foundry"), (0.0,))
        with pytest.raises(ReadOnly):
            await radar.set_card(READER, first.card.id, CardInput(state="done"))
        with pytest.raises(ReadOnly):
            await radar.set_stack(READER, ())
        with pytest.raises(ReadOnly):
            await radar.search("foundry")
        with pytest.raises(ReadOnly):
            await SnapshotFeedback().record(
                READER,
                FeedbackInput.model_validate(
                    {"target_type": "briefing", "target_ref": str(top.id), "rating": "up"}
                ),
            )
