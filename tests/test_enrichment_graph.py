from collections.abc import AsyncIterator

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.categories import Category
from newsloom_enrichment.entities import load_curated
from newsloom_enrichment.models import (
    Announcement,
    ArticleKind,
    Enrichment,
    EnrichmentFailure,
    Vector,
)
from newsloom_enrichment.repository import Repository
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from psycopg.errors import InsufficientPrivilege
from test_enrichment_database import METADATA, seed, vector
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration


def mention(product: str, vendor: str) -> dict[str, str]:
    return {"product": product, "vendor": vendor}


def announcement(*products: dict[str, str], status: str = "ga") -> Announcement:
    return Announcement.model_validate(
        {
            "statement": "A product changed.",
            "change_type": "launch",
            "status": status,
            "effective_date": None,
            "deadline": None,
            "products": list(products),
        }
    )


def result(*items: Announcement) -> Enrichment:
    return Enrichment(
        summary_sentences=("A vendor shipped changes.", "They are available now."),
        category=Category.DEVELOPER_TOOLS,
        tags=("release", "platform", "update"),
        article_kind=ArticleKind.ROUNDUP,
        announcements=items,
    )


def unit(index: int) -> Vector:
    values = [0.0] * 1536
    values[index] = 1.0
    return Vector(values=tuple(values))


@pytest.fixture
async def repository(platform_database: RuntimeConfig) -> AsyncIterator[Repository]:
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        await seed(platform_database, count=6)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            await connection.execute("SET ROLE newsloom_enrichment")
            yield Repository(connection)


async def complete(repository: Repository, value: Enrichment, mentions: dict[str, Vector]) -> None:
    claim = await repository.claim("graph")
    assert claim is not None
    await repository.complete(claim, value, vector(), METADATA, "graph", mentions)


async def rows(repository: Repository, sql: str) -> list[tuple[object, ...]]:
    return await (await repository.connection.execute(sql)).fetchall()


async def test_curated_aliases_relations_and_article_kind(repository: Repository) -> None:
    await complete(
        repository,
        result(
            announcement(mention("Azure AI Foundry", "Microsoft Foundry")),
            announcement(mention("Azure AI Agent Service", "Microsoft")),
        ),
        {},
    )
    entities = await rows(
        repository,
        "SELECT e.canonical_name, v.canonical_name, ae.method FROM announcement_entities ae "
        "JOIN entities e ON e.id=ae.entity_id JOIN entities v ON v.id=e.vendor_id "
        "JOIN announcements a ON a.id=ae.announcement_id ORDER BY a.ordinal",
    )
    assert entities == [
        ("Microsoft Foundry", "Microsoft", "curated"),
        ("Foundry Agent Service", "Microsoft", "curated"),
    ]
    relations = await rows(
        repository,
        "SELECT s.canonical_name, r.relation, t.canonical_name FROM entity_relations r "
        "JOIN entities s ON s.id=r.source_id JOIN entities t ON t.id=r.target_id",
    )
    assert relations == [("Foundry Agent Service", "part_of", "Microsoft Foundry")]
    assert await rows(repository, "SELECT DISTINCT article_kind FROM news") == [("roundup",)]
    assert repository.graph["announcements"] == 2 and repository.graph["curated"] == 2


async def test_exact_prefix_similar_and_vendor_separation(repository: Repository) -> None:
    await complete(
        repository,
        result(announcement(mention("Widget Pro 2", "Acme"))),
        {"Acme: Widget Pro 2": unit(0)},
    )
    await complete(
        repository,
        result(
            announcement(mention("Acme Widget Pro 2", "Acme Corp.")),
            announcement(mention("Widget Pro 2", "Other Vendor")),
        ),
        {"Acme Corp.: Acme Widget Pro 2": unit(0), "Other Vendor: Widget Pro 2": unit(0)},
    )
    # Same embedding, same version numbers: similar. Different version: a new product.
    await complete(
        repository,
        result(
            announcement(mention("Widget Professional 2", "Acme")),
            announcement(mention("Widget Pro 3", "Acme")),
        ),
        {"Acme: Widget Professional 2": unit(0), "Acme: Widget Pro 3": unit(0)},
    )
    links = await rows(
        repository,
        "SELECT v.canonical_name, e.canonical_name, ae.method FROM announcement_entities ae "
        "JOIN entities e ON e.id=ae.entity_id JOIN entities v ON v.id=e.vendor_id "
        "JOIN announcements a ON a.id=ae.announcement_id ORDER BY a.created_at, a.ordinal",
    )
    assert links == [
        ("Acme", "Widget Pro 2", "new"),
        ("Acme Corp.", "Acme Widget Pro 2", "new"),
        ("Other Vendor", "Widget Pro 2", "new"),
        ("Acme", "Widget Pro 2", "similar"),
        ("Acme", "Widget Pro 3", "new"),
    ]


async def test_graph_is_append_only_for_enrichment_and_read_only_for_mcp(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    await complete(repository, result(announcement(mention("Widget", "Acme"))), {})
    for statement in (
        "UPDATE announcements SET statement='changed'",
        "DELETE FROM entity_aliases",
        "UPDATE news SET summary='changed'",
    ):
        with pytest.raises(InsufficientPrivilege):
            async with repository.connection.transaction():
                await repository.connection.execute(statement)
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        await admin.execute("SET ROLE newsloom_mcp")
        counted = await (await admin.execute("SELECT count(*) FROM announcements")).fetchone()
        assert counted == (1,)
        with pytest.raises(InsufficientPrivilege):
            await admin.execute("INSERT INTO entities(kind,canonical_name) VALUES ('vendor','x')")


async def test_invalid_graph_rolls_back_the_whole_item(repository: Repository) -> None:
    bad = announcement(mention("Widget", "Acme")).model_copy(update={"statement": " "})
    with pytest.raises(psycopg.errors.CheckViolation):
        await complete(repository, result(bad), {})
    assert await rows(repository, "SELECT count(*) FROM news") == [(0,)]
    assert await rows(repository, "SELECT count(*) FROM entities") == [(0,)]


def test_curated_catalogue_is_consistent() -> None:
    curated = load_curated()
    assert curated.vendor("Amazon Web Services") == ("AWS", True)
    assert curated.vendor("Acme") == ("Acme", False)
    assert curated.products[("AWS", "agentcore")] == "Amazon Bedrock AgentCore"
    assert "foundry" in curated.keys("Microsoft", "Microsoft Foundry")


async def test_known_vendor_prefix_matches_the_same_product(repository: Repository) -> None:
    await complete(repository, result(announcement(mention("Widget X", "Microsoft"))), {})
    await complete(repository, result(announcement(mention("Microsoft Widget X", "Azure"))), {})
    links = await rows(
        repository,
        "SELECT e.canonical_name, ae.method FROM announcement_entities ae "
        "JOIN entities e ON e.id=ae.entity_id JOIN announcements a ON a.id=ae.announcement_id "
        "ORDER BY a.created_at",
    )
    assert links == [("Widget X", "new"), ("Widget X", "exact")]


async def test_backfill_adds_announcements_once_without_changing_summaries(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    from newsloom_core.entries import Entry
    from newsloom_enrichment.job import backfill
    from test_enrichment_job import Embeddings

    for _ in range(2):
        await complete(repository, result(), {})
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        await admin.execute(
            "UPDATE news SET article_kind=NULL, published_at=clock_timestamp() - interval '1 day'"
        )
    summaries = await rows(repository, "SELECT id, summary FROM news ORDER BY id")

    class Llm:
        calls = 0

        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            Llm.calls += 1
            return result(announcement(mention("Widget", "Acme"))).model_copy(
                update={"summary_sentences": ("Different summary.", "Not stored.")}
            )

    counts = await backfill(repository, Llm(), Embeddings(), "backfill")
    assert counts["candidates"] == counts["stored"] == 2 and Llm.calls == 2
    assert await rows(repository, "SELECT id, summary FROM news ORDER BY id") == summaries
    assert await rows(repository, "SELECT DISTINCT article_kind FROM news") == [("roundup",)]
    assert await rows(repository, "SELECT count(*) FROM announcements") == [(2,)]
    again = await backfill(repository, Llm(), Embeddings(), "backfill")
    assert again["candidates"] == 0 and Llm.calls == 2


async def test_triage_is_stored_with_announcements_and_backfilled_once(
    repository: Repository, platform_database: RuntimeConfig
) -> None:
    from newsloom_enrichment.job import triage_backfill
    from newsloom_enrichment.triage import Rating

    def rated(count: int) -> tuple[Rating, ...]:
        return tuple(
            Rating(index=i, tier="act_now", reason="Breaks deployments.", capability="security")
            for i in range(count)
        )

    claim = await repository.claim("graph")
    assert claim is not None
    value = result(announcement(mention("Widget", "Acme")), announcement(mention("Gadget", "Acme")))
    await repository.complete(claim, value, vector(), METADATA, "graph", {}, rated(1))
    await complete(repository, result(announcement(mention("Widget", "Acme"))), {})
    stored = await rows(
        repository,
        "SELECT tier, capability, triaged_at IS NOT NULL FROM announcements "
        "ORDER BY created_at, ordinal",
    )
    assert stored == [("act_now", "security", True), (None, None, False), (None, None, False)]

    class Triage:
        calls = 0

        async def rate(self, title, summary, kind, announcements, deadline):  # type: ignore[no-untyped-def]
            Triage.calls += 1
            assert [m.product for item in announcements for m in item.products]
            return rated(len(announcements))

    counts = await triage_backfill(repository, Triage(), "triage")
    assert counts == {"items": 2, "announcements": 2, "failed": 0, "deferred": 0}
    assert await rows(repository, "SELECT count(*) FROM announcements WHERE tier IS NULL") == [(0,)]
    again = await triage_backfill(repository, Triage(), "triage")
    assert again["items"] == 0 and Triage.calls == 2
    with pytest.raises(InsufficientPrivilege):
        async with repository.connection.transaction():
            await repository.connection.execute("UPDATE announcements SET status='ga'")
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        await admin.execute("SET ROLE newsloom_mcp")
        announcement_id = (
            await (await admin.execute("SELECT id FROM announcements LIMIT 1")).fetchone()
        )[0]  # type: ignore[index]
        reader = "a" * 64
        await admin.execute(
            "INSERT INTO reader_card_state(reader,announcement_id,state,snoozed_until) "
            "VALUES (%s,%s,'snoozed',clock_timestamp())",
            (reader, announcement_id),
        )
        await admin.execute("DELETE FROM reader_card_state WHERE reader=%s", (reader,))
        with pytest.raises(InsufficientPrivilege):
            await admin.execute("UPDATE announcements SET tier='later'")


async def test_triage_failure_never_blocks_publication(repository: Repository) -> None:
    from newsloom_core.entries import Entry
    from newsloom_enrichment.job import run
    from test_enrichment_job import Embeddings

    class Llm:
        async def generate(self, item: Entry, deadline: float) -> Enrichment:
            return result(announcement(mention("Widget", "Acme")))

    class Failing:
        async def rate(self, *args: object) -> tuple[()]:
            raise EnrichmentFailure("invalid_triage")

    counts = await run(repository, Llm(), Embeddings(), METADATA, "run", limit=1, triage=Failing())
    assert counts["enriched_run"] == 1 and counts["triage_failed"] == 1
    assert await rows(repository, "SELECT tier FROM announcements") == [(None,)]
