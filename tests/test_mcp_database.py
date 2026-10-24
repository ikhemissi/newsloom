from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.categories import Category
from newsloom_enrichment.repository import Repository as EnrichmentRepository
from newsloom_mcp.models import DetailInput, McpFailure, RecentInput, SearchInput
from newsloom_mcp.repository import Repository
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from test_enrichment_database import METADATA, enriched, seed, vector
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration


@pytest.fixture
async def repository(platform_database: RuntimeConfig) -> AsyncIterator[Repository]:
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        await seed(platform_database, count=12)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as admin:
            writer = EnrichmentRepository(admin)
            for index in range(12):
                claim = await writer.claim("seed")
                assert claim is not None
                await writer.complete(claim, enriched(), vector(), METADATA, "seed")
                values = [0.0] * 1536
                values[0] = 1.0 if index < 6 else 0.1
                values[1] = 0.0 if index < 6 else 1.0
                await admin.execute(
                    "UPDATE news SET source=%s,category=%s,tags=%s,published_at=%s,"
                    "embedding=%s::vector WHERE id=%s",
                    (
                        claim.entry.source,
                        "models" if index < 6 else "governance",
                        ["ai", "gateway", "news"] if index >= 6 else ["ai", "model", "news"],
                        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
                        "[" + ",".join(map(str, values)) + "]",
                        claim.id,
                    ),
                )
            await admin.execute("SET SESSION AUTHORIZATION newsloom_mcp")
            yield Repository(admin, "embedding-test", "1")


async def test_recent_detail_and_sources_are_only_public_fields(repository: Repository) -> None:
    async with repository.connection.transaction():
        await repository.connection.execute("SET TRANSACTION READ ONLY")
        recent = await repository.recent(RecentInput(limit=2))
        assert (
            len(recent.items) == 2 and recent.items[0].published_at > recent.items[1].published_at
        )
        assert set(recent.items[0].model_dump()) == {
            "id",
            "title",
            "summary",
            "source",
            "category",
            "tags",
            "published_at",
            "url",
        }
        detail = await repository.detail(DetailInput(id=recent.items[0].id))
        assert detail.found and detail.item is not None and detail.item.author == ""
        absent = await repository.detail(DetailInput(id=UUID(int=0)))
        assert not absent.found and absent.item is None
        discovery = await repository.sources()
        assert len(discovery.sources) == 1
        assert {c.label for c in discovery.categories} == {"Models", "Governance"}
        boundary = await repository.recent(RecentInput(since=recent.items[0].published_at))
        assert len(boundary.items) == 1


async def test_selective_filters_rank_within_all_matches_not_global_top_k(
    repository: Repository,
) -> None:
    embedding = (1.0,) + (0.0,) * 1535
    async with repository.connection.transaction():
        await repository.connection.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        global_results = await repository.search(SearchInput(limit=5, query="agents"), embedding)
        assert all(item.category.value == "models" for item in global_results.items)
        filtered = await repository.search(
            SearchInput(
                query="agents",
                category=Category.GOVERNANCE,
                tags=("AI", "gateway"),
                limit=5,
            ),
            embedding,
        )
        assert len(filtered.items) == 5 and all(
            item.category.value == "governance" and item.similarity is not None
            for item in filtered.items
        )
        assert set(i.id for i in filtered.items).isdisjoint(i.id for i in global_results.items)


async def test_metadata_dates_tags_unknown_source_and_stable_ties(repository: Repository) -> None:
    args = SearchInput.model_validate(
        {
            "from": "2026-01-07T00:00:00Z",
            "to": "2026-01-09T00:00:00Z",
            "tags": ["gateway", "ai"],
            "limit": 50,
        }
    )
    result = await repository.search(args, None)
    assert len(result.items) == 2 and all(item.similarity is None for item in result.items)
    assert result.items[0].published_at == datetime(2026, 1, 8, tzinfo=UTC)
    assert len((await repository.search(SearchInput(source="unmatched"), None)).items) == 0
    assert len((await repository.search(SearchInput(tags=("ai", "absent")), None)).items) == 0
    first = await repository.search(SearchInput(query="test", limit=5), (1.0,) + (0.0,) * 1535)
    again = await repository.search(SearchInput(query="test", limit=5), (1.0,) + (0.0,) * 1535)
    assert [item.id for item in first.items] == sorted(item.id for item in again.items)


async def test_model_mismatch_cannot_silently_filter_eligible_rows(repository: Repository) -> None:
    repository.version = "incompatible"
    with pytest.raises(McpFailure, match="embedding_model_mismatch"):
        await repository.search(SearchInput(query="test"), (1.0,) + (0.0,) * 1535)
    assert len((await repository.search(SearchInput(), None)).items) == 10


async def test_reader_grants_do_not_expose_private_data_or_writes(repository: Repository) -> None:
    for statement in (
        "SELECT * FROM news",
        "SELECT id FROM ingestion_queue LIMIT 0",
        "SELECT id FROM quarantine LIMIT 0",
        "SELECT id FROM feed_sources LIMIT 0",
        "UPDATE news SET summary='override' WHERE false",
        "DELETE FROM news WHERE false",
        "INSERT INTO news DEFAULT VALUES",
        "CREATE TABLE public.unowned(id int)",
        "SET ROLE newsloom_enrichment",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with repository.connection.transaction():
                await repository.connection.execute(statement)
