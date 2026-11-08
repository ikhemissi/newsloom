"""Fixed read-only projections; filters precede exact vector ranking."""

from typing import Protocol

from newsloom_core.categories import load_categories
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

from newsloom_mcp.http_models import Position
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
    async def browse(self, args: SearchInput, after: Position | None) -> NewsResults: ...
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

    async def browse(self, args: SearchInput, after: Position | None) -> NewsResults:
        where, values = predicates(args)
        continuation = sql.SQL("")
        if after is not None:
            continuation = sql.SQL(" AND (published_at<%s OR (published_at=%s AND id>%s))")
            values.extend((after.published_at, after.published_at, after.id))
        async with self.connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                sql.SQL("SELECT {} FROM public.news WHERE ({})").format(PROJECTION, where)
                + continuation
                + sql.SQL(" ORDER BY published_at DESC,id ASC LIMIT %s"),
                [*values, args.limit + 1],
            )
            return NewsResults(
                items=tuple(NewsItem.model_validate(row) for row in await cursor.fetchall())
            )

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
                    "SELECT {},author,date_origin,publisher_categories,article_kind "
                    "FROM public.news WHERE id=%s"
                ).format(PROJECTION),
                (args.id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return ItemResult(found=False, item=None)
            await cursor.execute(
                "SELECT a.statement,a.change_type,a.status,a.effective_date,a.deadline,"
                "coalesce(array_agg(e.canonical_name ORDER BY e.canonical_name) "
                "FILTER (WHERE e.id IS NOT NULL),'{}') AS products "
                "FROM public.announcements a "
                "LEFT JOIN public.announcement_entities ae ON ae.announcement_id=a.id "
                "LEFT JOIN public.entities e ON e.id=ae.entity_id "
                "WHERE a.news_id=%s GROUP BY a.id ORDER BY a.ordinal",
                (args.id,),
            )
            announcements = tuple(await cursor.fetchall())
            return ItemResult(
                found=True, item=NewsDetail.model_validate({**row, "announcements": announcements})
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
                # Items naming a known product or matching the query words rank first.
                await cursor.execute(
                    eligible
                    + sql.SQL(
                        ", query AS (SELECT btrim(regexp_replace(lower(%s),"
                        "'[^0-9a-z+#.]+',' ','g')) AS words, "
                        "websearch_to_tsquery('simple',%s) AS terms), "
                        "named AS (SELECT DISTINCT a.news_id FROM public.announcements a "
                        "JOIN public.announcement_entities ae ON ae.announcement_id=a.id "
                        "JOIN public.entity_aliases al ON al.entity_id=ae.entity_id, query q "
                        "WHERE length(al.alias)>=3 AND length(q.words)>=3 AND ("
                        "(' '||al.alias||' ') LIKE ('%% '||q.words||' %%') "
                        "OR (' '||q.words||' ') LIKE ('%% '||al.alias||' %%')) "
                        "UNION SELECT a.news_id FROM public.announcements a, query q "
                        "WHERE a.search_text @@ q.terms) "
                        "SELECT {},1-(embedding <=> %s::vector) AS similarity "
                        "FROM eligible, query q ORDER BY "
                        "(id IN (SELECT news_id FROM named) OR "
                        "to_tsvector('simple',title||' '||summary) @@ q.terms) DESC,"
                        "embedding <=> %s::vector,id ASC LIMIT %s"
                    ).format(PROJECTION),
                    [
                        *relation_values,
                        *values,
                        args.query,
                        args.query,
                        vector_text,
                        vector_text,
                        args.limit,
                    ],
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
