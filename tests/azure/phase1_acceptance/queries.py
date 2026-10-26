import math
from datetime import timedelta
from uuid import UUID

import psycopg
from newsloom_core.phase1_contracts import AcceptanceFailure, FixtureCase, TestConfig, load_fixtures
from newsloom_mcp.embedding import QueryEmbedding
from newsloom_mcp.models import DetailInput, RecentInput, SearchInput
from newsloom_mcp.repository import Repository


async def verify(
    connection: psycopg.AsyncConnection[tuple[object, ...]],
    config: TestConfig,
    embedding: QueryEmbedding,
    deadline: float,
) -> None:
    expected: dict[str, FixtureCase] = {
        case.id: case for case in load_fixtures().cases if not case.hostile
    }
    async with connection.transaction():
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        stored = await (
            await connection.execute(
                "SELECT id,guid,title,summary,source,category,tags,published_at,canonical_url,"
                "author,date_origin,publisher_categories,vector_dims(embedding) "
                "FROM public.news ORDER BY published_at DESC,id"
            )
        ).fetchall()
        if (
            len(stored) != 2
            or {row[1] for row in stored} != set(expected)
            or any(row[12] != 1536 for row in stored)
        ):
            raise AcceptanceFailure("acceptance_stored_news_mismatch")
        repository = Repository(connection, config.embedding_model, config.embedding_version)
        recent = await repository.recent(RecentInput())
        if [item.id for item in recent.items] != [row[0] for row in stored]:
            raise AcceptanceFailure("acceptance_recent_mismatch")
        for row, item in zip(stored, recent.items, strict=True):
            if (
                not isinstance(row[0], UUID)
                or not isinstance(row[1], str)
                or not isinstance(row[6], list)
                or not isinstance(row[11], list)
            ):
                raise AcceptanceFailure("acceptance_invalid_stored_projection")
            case = expected[row[1]]
            detail = await repository.detail(DetailInput(id=item.id))
            if not detail.found or detail.item is None:
                raise AcceptanceFailure("acceptance_detail_missing")
            full = detail.item
            if (
                (
                    full.title,
                    full.summary,
                    full.source,
                    full.category,
                    full.tags,
                    full.published_at,
                    full.url,
                    full.author,
                    full.date_origin,
                    full.publisher_categories,
                )
                != (*row[2:6], tuple(row[6]), *row[7:11], tuple(row[11]))
                or full.title != case.title
                or full.url != case.url
                or full.author != case.author
            ):
                raise AcceptanceFailure("acceptance_detail_mismatch")
        discovery = await repository.sources()
        if {
            (source.id, category.value)
            for source in discovery.sources
            for category in source.categories
        } != {(str(row[4]), str(row[5])) for row in stored}:
            raise AcceptanceFailure("acceptance_discovery_mismatch")
        first = recent.items[-1]
        args = SearchInput(
            source=first.source,
            category=first.category,
            tags=first.tags[:2],
            from_=first.published_at,
            to=first.published_at + timedelta(days=2),
            limit=5,
        )
        metadata = await repository.search(args, None)
        if [item.id for item in metadata.items] != [first.id] or metadata.items[
            0
        ].similarity is not None:
            raise AcceptanceFailure("acceptance_metadata_mismatch")
    # Inference does not hold a database snapshot or idle transaction.
    vector = await embedding.embed(
        "multilingual open model release inference measurements", deadline
    )
    async with connection.transaction():
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        semantic = await repository.search(args, vector.values)
        literal = "[" + ",".join(map(str, vector.values)) + "]"
        exact = await (
            await connection.execute(
                "SELECT id,1-(embedding<=>%s::vector) AS similarity FROM public.news "
                "WHERE source=%s AND category=%s AND tags @> %s::text[] "
                "AND published_at>=%s AND published_at<%s ORDER BY similarity DESC,id LIMIT 5",
                (
                    literal,
                    args.source,
                    args.category.value if args.category else "",
                    list(args.tags),
                    args.from_,
                    args.to,
                ),
            )
        ).fetchall()
        if (
            len(semantic.items) != 1
            or [item.id for item in semantic.items] != [row[0] for row in exact]
            or semantic.items[0].similarity is None
            or not isinstance(exact[0][1], float)
            or not math.isclose(semantic.items[0].similarity, exact[0][1], abs_tol=1e-6)
        ):
            raise AcceptanceFailure("acceptance_semantic_mismatch")
