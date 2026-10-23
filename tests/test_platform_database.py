"""Real PostgreSQL SQL tests; local stand-ins do not claim Entra authentication."""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import psycopg
import pytest
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import ManagedIdentityCredential
from newsloom_platform import database
from newsloom_platform.config import (
    RUNTIME_WORKLOADS,
    PlatformFailure,
    RuntimeConfig,
    database_role,
)
from psycopg.conninfo import conninfo_to_dict

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("NEWSLOOM_TEST_POSTGRES_DSN"),
        reason="Explicit local PostgreSQL 18/pgvector instance required.",
    ),
]


@pytest.fixture
async def platform_database(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[RuntimeConfig]:
    dsn = os.environ.get("NEWSLOOM_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Explicit local PostgreSQL 18/pgvector instance required.")
    parameters = conninfo_to_dict(dsn)
    if parameters.get("host") not in ["127.0.0.1", "localhost", "::1"]:
        raise ValueError("Integration tests require an explicitly local disposable database.")
    if parameters.get("user") != "postgres" or parameters.get("dbname") != "postgres":
        raise ValueError("Integration tests require the disposable postgres maintenance database.")
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as connection:
        row = await (await connection.execute("SHOW server_version_num")).fetchone()
        assert row is not None and 180000 <= int(row[0]) < 190000
        await connection.execute("DROP DATABASE IF EXISTS newsloom WITH (FORCE)")
        await connection.execute("DROP SCHEMA IF EXISTS newsloom_admin CASCADE")
        await connection.execute("CREATE DATABASE newsloom")
        for workload in RUNTIME_WORKLOADS:
            await connection.execute(
                psycopg.sql.SQL("DROP ROLE IF EXISTS {}").format(
                    psycopg.sql.Identifier(database_role(workload))
                )
            )
        await connection.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'azure_pg_admin') THEN
                    CREATE ROLE azure_pg_admin NOLOGIN;
                END IF;
            END $$;
            DROP TABLE IF EXISTS public.test_principals;
            CREATE TABLE public.test_principals (
                rolename name PRIMARY KEY, principal_type text, object_id text,
                tenant_id text, is_mfa integer, is_admin integer
            );
            CREATE OR REPLACE FUNCTION pg_catalog.pgaadauth_list_principals(boolean)
            RETURNS TABLE (
                rolename name, principal_type text, object_id text,
                tenant_id text, is_mfa integer, is_admin integer
            ) LANGUAGE sql AS 'SELECT * FROM public.test_principals';
            CREATE OR REPLACE FUNCTION pg_catalog.pgaadauth_create_principal_with_oid(
                role_name text, object_id text, object_type text,
                is_admin boolean, is_mfa boolean
            ) RETURNS text LANGUAGE plpgsql AS $$
            BEGIN
                EXECUTE format('CREATE ROLE %I LOGIN', role_name);
                INSERT INTO public.test_principals VALUES
                    (role_name, object_type, object_id, '', is_mfa::integer, is_admin::integer);
                RETURN 'created';
            END $$;
        """)

    async def local_connect(
        config: RuntimeConfig, credential: AsyncTokenCredential, name: str, user: str
    ) -> psycopg.AsyncConnection[tuple[object, ...]]:
        return await psycopg.AsyncConnection.connect(dsn, dbname=name, autocommit=True)

    monkeypatch.setattr(database, "connect", local_connect)
    yield RuntimeConfig.model_validate(
        {
            "identities": {
                w: {"id": f"/test/{w}", "client_id": uuid4(), "principal_id": uuid4()}
                for w in (*RUNTIME_WORKLOADS, "migrations")
            },
            "postgres_host": "localhost",
            "postgres_database": "newsloom",
            "postgres_admin_name": "postgres",
            "model_endpoint": "https://test.services.ai.azure.com",
            "enrichment_deployment": "enrichment",
            "embeddings_deployment": "embeddings",
            "screening_deployment": "screening",
            "registry_endpoint": "test.azurecr.io",
            "model_account_id": "/test/account",
            "applicationinsights_connection_string": "unused-local-routing",
        }
    )


async def test_migration_replay_and_vector_contract(platform_database: RuntimeConfig) -> None:
    async with ManagedIdentityCredential() as credential:
        assert await database.migrate(platform_database, credential) == 3
        assert await database.migrate(platform_database, credential) == 0
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            row = await (
                await connection.execute(
                    "SELECT vector_dims(array_fill(0.0::real, ARRAY[1536])::vector)"
                )
            ).fetchone()
            assert row == (1536,)
            rows = await (
                await connection.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_type = 'BASE TABLE' "
                    "AND table_schema NOT IN ('pg_catalog', 'information_schema')"
                )
            ).fetchall()
            assert set(rows) == {
                ("newsloom_admin", "schema_migrations"),
                ("public", "feed_sources"),
                ("public", "ingestion_queue"),
                ("public", "quarantine"),
            }


async def test_concurrent_migrations_serialize(platform_database: RuntimeConfig) -> None:
    async with ManagedIdentityCredential() as credential:
        outcomes = await asyncio.gather(
            database.migrate(platform_database, credential),
            database.migrate(platform_database, credential),
        )
    assert sorted(outcomes) == [0, 3]


async def test_failed_sql_phase_rolls_back(
    platform_database: RuntimeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = database.record

    async def fail_vector(
        connection: psycopg.AsyncConnection[tuple[object, ...]], version: str, checksum: str
    ) -> None:
        if version == "001_vector":
            raise psycopg.errors.SyntaxError("synthetic rollback canary")
        await original(connection, version, checksum)

    monkeypatch.setattr(database, "record", fail_vector)
    async with ManagedIdentityCredential() as credential:
        with pytest.raises(psycopg.errors.SyntaxError):
            await database.migrate(platform_database, credential)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            row = await (
                await connection.execute(
                    "SELECT count(*) FROM pg_extension WHERE extname = 'vector'"
                )
            ).fetchone()
            assert row == (0,)
        monkeypatch.setattr(database, "record", original)
        assert await database.migrate(platform_database, credential) == 2


async def test_ingestion_migration_rolls_back_atomically_and_replays(
    platform_database: RuntimeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = database.migration_sql

    def interrupted(name: str) -> str:
        sql = original(name)
        return sql + "\nSELECT 1 / 0;" if name == "002_ingestion.sql" else sql

    monkeypatch.setattr(database, "migration_sql", interrupted)
    async with ManagedIdentityCredential() as credential:
        with pytest.raises(psycopg.errors.DivisionByZero):
            await database.migrate(platform_database, credential)
        async with await database.connect(
            platform_database, credential, "newsloom", "postgres"
        ) as connection:
            assert (
                await (
                    await connection.execute(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                    )
                ).fetchall()
                == []
            )
            assert await (
                await connection.execute(
                    "SELECT count(*) FROM newsloom_admin.schema_migrations "
                    "WHERE version='002_ingestion'"
                )
            ).fetchone() == (0,)
        monkeypatch.setattr(database, "migration_sql", original)
        assert await database.migrate(platform_database, credential) == 1
        assert await database.migrate(platform_database, credential) == 0


async def test_mismatched_principal_fails_without_remapping(
    platform_database: RuntimeConfig,
) -> None:
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)
        async with await database.connect(
            platform_database, credential, "postgres", "postgres"
        ) as connection:
            await connection.execute(
                "UPDATE public.test_principals SET object_id = %s WHERE rolename = %s",
                (str(uuid4()), "newsloom_mcp"),
            )
        with pytest.raises(PlatformFailure, match="principal_mapping_mismatch"):
            await database.migrate(platform_database, credential)
