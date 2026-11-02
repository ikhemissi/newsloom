from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from azure.identity.aio import ManagedIdentityCredential
from newsloom_mcp.http_models import browse_input, decode_cursor, encode_cursor
from newsloom_mcp.models import DetailInput, SearchInput
from newsloom_mcp.repository import Repository
from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig
from starlette.datastructures import QueryParams
from test_mcp_database import repository as repository
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration


async def test_tied_keysets_exact_page_multiples_filters_and_public_projection(
    repository: Repository,
) -> None:
    # Fixture setup uses admin authority; every browse below uses the MCP role.
    await repository.connection.execute("RESET SESSION AUTHORIZATION")
    await repository.connection.execute(
        "UPDATE news SET published_at=%s",
        (datetime(2026, 1, 1, tzinfo=UTC),),
    )
    await repository.connection.execute("SET SESSION AUTHORIZATION newsloom_mcp")
    args = SearchInput(limit=3)
    observed: list[UUID] = []
    after = None
    for _ in range(4):
        rows = await repository.browse(args, after)
        assert len(rows.items) in (3, 4)
        page = rows.items[: args.limit]
        observed.extend(item.id for item in page)
        after = (
            decode_cursor(encode_cursor(page[-1], args), args)
            if len(rows.items) > args.limit
            else None
        )
    assert after is None and len(observed) == len(set(observed)) == 12
    assert observed == sorted(observed)
    args, _ = browse_input(
        QueryParams(
            "category=governance&tags=AI&tags=Gateway&source=synthetic-00"
            "&from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z&limit=2"
        )
    )
    # Use the actual represented source rather than inventing a fixture label.
    sources = await repository.sources()
    args = args.model_copy(update={"source": sources.sources[0].id})
    filtered = await repository.browse(args, None)
    assert len(filtered.items) == 3
    assert all(item.category.value == "governance" for item in filtered.items)
    assert not (await repository.browse(SearchInput(source="missing"), None)).items
    boundary = args.model_copy(
        update={"to": datetime(2026, 1, 1, tzinfo=UTC), "from_": datetime(2025, 12, 31, tzinfo=UTC)}
    )
    assert not (await repository.browse(boundary, None)).items
    absent = await repository.detail(DetailInput(id=UUID(int=0)))
    assert absent.item is None


async def test_live_keysets_do_not_claim_snapshot_after_updates(
    repository: Repository,
    platform_database: RuntimeConfig,
) -> None:
    args = SearchInput(limit=3)
    first = await repository.browse(args, None)
    anchor = decode_cursor(encode_cursor(first.items[2], args), args)
    tail = await repository.browse(args, anchor)
    changed = tail.items[0].id
    async with (
        ManagedIdentityCredential() as credential,
        await database.connect(platform_database, credential, "newsloom", "postgres") as admin,
    ):
        await admin.execute(
            "UPDATE news SET published_at=%s WHERE id=%s",
            (anchor.published_at + timedelta(days=1), changed),
        )
        await admin.execute(
            "CREATE TEMP TABLE saved_news AS SELECT * FROM news WHERE id=%s",
            (tail.items[1].id,),
        )
        await admin.execute("DELETE FROM news WHERE id=%s", (tail.items[1].id,))
        await admin.execute(
            "UPDATE saved_news SET published_at=%s",
            (anchor.published_at + timedelta(days=2),),
        )
        await admin.execute("INSERT INTO news SELECT * FROM saved_news")
    next_page = await repository.browse(args, anchor)
    assert changed not in {item.id for item in next_page.items}
    assert tail.items[1].id not in {item.id for item in next_page.items}
    assert changed in {item.id for item in (await repository.browse(args, None)).items}
    assert tail.items[1].id in {item.id for item in (await repository.browse(args, None)).items}
