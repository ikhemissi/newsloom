from datetime import UTC, datetime, timedelta

import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_enrichment.repository import Repository
from newsloom_enrichment.triage import Rating
from newsloom_mcp.radar import CardInput, RadarRepository, entry_cards
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from test_enrichment_database import METADATA, vector
from test_enrichment_graph import announcement, mention, repository, result
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration
assert repository is not None
READER, OTHER = "a" * 64, "b" * 64


def rated(*tiers: str) -> tuple[Rating, ...]:
    return tuple(
        Rating(index=i, tier=tier, reason="Matters.", capability="agent tools")  # type: ignore[arg-type]
        for i, tier in enumerate(tiers)
    )


async def test_radar_ranks_personalises_and_isolates_readers(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    items = [
        (result(announcement(mention("Azure AI Foundry", "Microsoft"))), rated("act_now")),
        (result(announcement(mention("Gadget", "Other"))), rated("act_now")),
        (result(announcement(mention("Widget", "Acme"))), ()),
    ]
    for value, ratings in items:
        claim = await repository.claim("radar")
        assert claim is not None
        await repository.complete(claim, value, vector(), METADATA, "radar", {}, ratings)
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        await admin.execute("UPDATE news SET published_at=clock_timestamp()-interval '1 day'")
        await admin.execute("SET ROLE newsloom_mcp")
        store = RadarRepository(admin)
        now = datetime.now(UTC)
        radar = await store.radar(READER, 7, now)
        act = [c.statement for e in radar.tiers["act_now"] for c in entry_cards(e)]
        assert len(act) == 2
        untriaged = [c for e in radar.tiers["worth_knowing"] for c in entry_cards(e)]
        assert [c.tier for c in untriaged] == ["worth_knowing"] and untriaged[0].reason is None

        microsoft = next(e for e in await store.search("Microsoft") if e.kind == "vendor")
        assert [e.name for e in await store.set_stack(READER, (microsoft.id,))] == ["Microsoft"]
        personal = await store.radar(READER, 7, now)
        stacked = [c for e in personal.tiers["act_now"] for c in entry_cards(e)]
        assert [c.products[0].name for c in stacked] == ["Microsoft Foundry"]
        assert stacked[0].in_stack
        assert (
            len(
                [
                    c
                    for e in (await store.radar(OTHER, 7, now)).tiers["act_now"]
                    for c in entry_cards(e)
                ]
            )
            == 2
        )

        card = stacked[0]
        assert await store.set_card(READER, card.id, CardInput(state="snoozed"))
        snoozed = await store.radar(READER, 7, now)
        assert [c.id for c in snoozed.hidden] == [card.id] and not snoozed.tiers["act_now"]
        assert not (await store.radar(OTHER, 7, now)).hidden
        assert (await store.radar(READER, 7, now + timedelta(days=8))).hidden == ()
        assert await store.set_card(READER, card.id, CardInput(state=None))
        assert not await store.set_card(READER, microsoft.id, CardInput(state="done"))

        foundry = next(e for e in await store.search("foundry") if e.kind == "product")
        detail = await store.product(foundry.id)
        assert detail is not None and detail.vendor == "Microsoft"
        assert "azure ai foundry" in detail.aliases and len(detail.timeline) == 1
        assert await store.product(microsoft.id) is None
        assert await store.set_stack(READER, (microsoft.id, card.id)) == await store.stack(READER)
        assert [e.name for e in await store.stack(READER)] == ["Microsoft"]
