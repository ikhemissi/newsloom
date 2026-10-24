"""Exact-named temporary evaluation objects; never production news fixture writes."""

import re
from uuid import UUID

from azure.core.credentials_async import AsyncTokenCredential
from newsloom_core.retrieval_fixtures import corpus_uuid, fixture_revision, load_fixtures
from psycopg import sql

from newsloom_platform import database
from newsloom_platform.config import PlatformFailure, RuntimeConfig


def evaluation_schema(run_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise PlatformFailure("invalid_evaluation_run_id")
    return "mcp_eval_" + UUID(hex=run_id).hex


async def prepare(config: RuntimeConfig, credential: AsyncTokenCredential, run_id: str) -> int:
    schema = evaluation_schema(run_id)
    fixtures = load_fixtures()
    async with (
        await database.connect(
            config, credential, config.postgres_database, config.postgres_admin_name
        ) as connection,
        connection.transaction(),
    ):
        exists = await (
            await connection.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,))
        ).fetchone()
        if exists is not None:
            raise PlatformFailure("evaluation_schema_already_exists")
        await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        await connection.execute(
            sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema))
        )
        await connection.execute(
            sql.SQL(
                "CREATE TABLE {}.manifest(run_id text PRIMARY KEY,revision text NOT NULL)"
            ).format(sql.Identifier(schema))
        )
        await connection.execute(
            sql.SQL("INSERT INTO {}.manifest VALUES (%s,%s)").format(sql.Identifier(schema)),
            (run_id, fixture_revision()),
        )
        await connection.execute(
            sql.SQL(
                "CREATE TABLE {}.news_fixture("
                "id uuid PRIMARY KEY,title text,summary text,source text,"
                "category text,tags text[],published_at timestamptz,canonical_url text,"
                "embedding_model text,embedding_version text)"
            ).format(sql.Identifier(schema))
        )
        for item in fixtures.corpus:
            await connection.execute(
                sql.SQL(
                    "INSERT INTO {}.news_fixture VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                ).format(sql.Identifier(schema)),
                (
                    corpus_uuid(item.id),
                    item.title,
                    item.summary,
                    item.source,
                    item.category.value,
                    list(item.tags),
                    item.published_at,
                    "https://example.com/" + item.id,
                    "text-embedding-3-large",
                    "1",
                ),
            )
        await connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO newsloom_mcp").format(sql.Identifier(schema))
        )
        await connection.execute(
            sql.SQL("GRANT SELECT ON {}.news_fixture,{}.manifest TO newsloom_mcp").format(
                sql.Identifier(schema), sql.Identifier(schema)
            )
        )
    return len(fixtures.corpus)


async def cleanup(config: RuntimeConfig, credential: AsyncTokenCredential, run_id: str) -> None:
    schema = evaluation_schema(run_id)
    async with (
        await database.connect(
            config, credential, config.postgres_database, config.postgres_admin_name
        ) as connection,
        connection.transaction(),
    ):
        exists = await (
            await connection.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,))
        ).fetchone()
        if exists is None:
            raise PlatformFailure("evaluation_schema_missing")
        marker = await (
            await connection.execute(
                sql.SQL("SELECT run_id FROM {}.manifest").format(sql.Identifier(schema))
            )
        ).fetchone()
        if marker != (run_id,):
            raise PlatformFailure("evaluation_schema_ownership_mismatch")
        await connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        if (
            await (
                await connection.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,))
            ).fetchone()
            is not None
        ):
            raise PlatformFailure("evaluation_cleanup_not_proven")
