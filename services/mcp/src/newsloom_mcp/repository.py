"""Fixed read-only projections; filters precede exact vector ranking."""

from typing import Protocol

from newsloom_core.categories import load_categories
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

from newsloom_mcp.models import (
    CategoryInfo,
    DetailInput,
    ItemResult,
    McpFailure,
    NewsDetail,
    NewsItem,
    NewsResults,
    RankedItem,
    RecentInput,
    SearchInput,
    SearchResults,
    SourceInfo,
    SourcesResult,
)

PUBLIC_FIELDS = (
    "id",
    "title",
    "summary",
    "source",
    "category",
    "tags",
    "published_at",
    "canonical_url",
)
PROJECTION = sql.SQL(",").join(
    sql.SQL("{} AS {}").format(
        sql.Identifier(field), sql.Identifier("url" if field == "canonical_url" else field)
    )
    for field in PUBLIC_FIELDS
)


class NewsRepository(Protocol):
    async def recent(self, args: RecentInput) -> NewsResults: ...
    async def detail(self, args: DetailInput) -> ItemResult: ...
    async def sources(self) -> SourcesResult: ...
    async def search(
        self, args: SearchInput, vector: tuple[float, ...] | None
    ) -> SearchResults: ...


def predicates(args: SearchInput) -> tuple[sql.Composed, list[object]]:
    clauses: list[sql.SQL] = []
    values: list[object] = []
    for clause, value in [
        ("source=%s", args.source),
        ("category=%s", args.category.value if args.category else None),
        ("published_at>=%s", args.from_),
        ("published_at<%s", args.to),
        ("tags @> %s::text[]", list(args.tags) if args.tags else None),
    ]:
        if value is not None:
            clauses.append(sql.SQL(clause))
            values.append(value)
    return sql.SQL(" AND ").join(clauses or [sql.SQL("true")]), values


class Repository:
    def __init__(
        self, connection: AsyncConnection[tuple[object, ...]], model: str, version: str
    ) -> None:
        self.connection, self.model, self.version = connection, model, version

    async def recent(self, args: RecentInput) -> NewsResults:
        async with self.connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                sql.SQL(
                    "SELECT {} FROM public.news "
                    "WHERE (%s::timestamptz IS NULL OR published_at>=%s) "
                    "ORDER BY published_at DESC,id ASC LIMIT %s"
                ).format(PROJECTION),
                (args.since, args.since, args.limit),
            )
            return NewsResults(
                items=tuple(NewsItem.model_validate(row) for row in await cursor.fetchall())
            )

    async def detail(self, args: DetailInput) -> ItemResult:
        async with self.connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                sql.SQL(
                    "SELECT {},author,date_origin,publisher_categories FROM public.news WHERE id=%s"
                ).format(PROJECTION),
                (args.id,),
            )
            row = await cursor.fetchone()
            return ItemResult(
                found=row is not None, item=NewsDetail.model_validate(row) if row else None
            )

    async def sources(self) -> SourcesResult:
        async with self.connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                "SELECT source,array_agg(DISTINCT category ORDER BY category) AS categories "
                "FROM public.news GROUP BY source ORDER BY source"
            )
            sources = tuple(
                SourceInfo.model_validate({"id": row["source"], "categories": row["categories"]})
                for row in await cursor.fetchall()
            )
        represented = {category for source in sources for category in source.categories}
        return SourcesResult(
            sources=sources,
            categories=tuple(
                CategoryInfo(id=item.id, label=item.label)
                for item in load_categories()
                if item.id in represented
            ),
        )

    async def search(self, args: SearchInput, vector: tuple[float, ...] | None) -> SearchResults:
        return await self.rank(args, vector, sql.SQL("public.news"), [])

    async def rank(
        self,
        args: SearchInput,
        vector: tuple[float, ...] | None,
        relation: sql.Composable,
        relation_values: list[object],
    ) -> SearchResults:
        where, values = predicates(args)
        fields = sql.SQL(",").join(
            sql.Identifier(field)
            for field in (*PUBLIC_FIELDS, "embedding", "embedding_model", "embedding_version")
        )
        eligible = sql.SQL("WITH eligible AS MATERIALIZED (SELECT {} FROM {} WHERE {}) ").format(
            fields, relation, where
        )
        # Compatibility and ranking share the caller's read-only repeatable-read snapshot.
        async with self.connection.cursor(row_factory=dict_row) as cursor:
            if vector is not None:
                await cursor.execute(
                    eligible
                    + sql.SQL(
                        "SELECT count(*) AS mismatches FROM eligible "
                        "WHERE embedding_model<>%s OR embedding_version<>%s"
                    ),
                    [*relation_values, *values, self.model, self.version],
                )
                row = await cursor.fetchone()
                if row is None or row["mismatches"] != 0:
                    raise McpFailure("embedding_model_mismatch")
                vector_text = "[" + ",".join(str(value) for value in vector) + "]"
                await cursor.execute(
                    eligible
                    + sql.SQL(
                        "SELECT {},1-(embedding <=> %s::vector) AS similarity "
                        "FROM eligible ORDER BY embedding <=> %s::vector,id ASC LIMIT %s"
                    ).format(PROJECTION),
                    [*relation_values, *values, vector_text, vector_text, args.limit],
                )
            else:
                await cursor.execute(
                    eligible
                    + sql.SQL(
                        "SELECT {},NULL::double precision AS similarity FROM eligible "
                        "ORDER BY published_at DESC,id ASC LIMIT %s"
                    ).format(PROJECTION),
                    [*relation_values, *values, args.limit],
                )
            return SearchResults(
                items=tuple(RankedItem.model_validate(row) for row in await cursor.fetchall())
            )
