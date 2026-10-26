import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from azure.core.credentials import AccessToken
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.phase1_contracts import ROLE, AcceptanceFailure, TestConfig
from newsloom_platform import database, phase1_database
from newsloom_platform.config import RuntimeConfig
from psycopg import sql
from test_phase1_contracts import phase_config as phase_config
from test_platform_database import platform_database as platform_database

pytestmark = pytest.mark.integration


@pytest.fixture
async def isolated(
    platform_database: RuntimeConfig,
    phase_config: TestConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[RuntimeConfig, TestConfig]]:
    async def forbidden_token(
        self: ManagedIdentityCredential,
        *scopes: str,
        **kwargs: object,
    ) -> AccessToken:
        raise AssertionError("local_acceptance_test_requested_cloud_token")

    monkeypatch.setattr(ManagedIdentityCredential, "get_token", forbidden_token)
    async with ManagedIdentityCredential() as credential:
        await database.migrate(platform_database, credential)

        async def local_connect(
            config: TestConfig,
            credential: AsyncTokenCredential,
            *,
            maintenance: bool = False,
        ) -> psycopg.AsyncConnection[tuple[object, ...]]:
            current = await database.connect(
                platform_database,
                credential,
                "postgres" if maintenance else config.database,
                "postgres",
            )
            await current.execute(
                sql.SQL("SET SESSION AUTHORIZATION {}").format(sql.Identifier(ROLE))
            )
            verified = False
            try:
                if not maintenance:
                    await phase1_database.verify_manifest(current, config)
                verified = True
            finally:
                if not verified:
                    await current.close()
            return current

        monkeypatch.setattr(phase1_database, "connect", local_connect)
        try:
            yield platform_database, phase_config
        finally:
            async with await database.connect(
                platform_database,
                credential,
                "postgres",
                "postgres",
            ) as admin:
                exists = await (
                    await admin.execute(
                        "SELECT 1 FROM pg_database WHERE datname=%s", (phase_config.database,)
                    )
                ).fetchone()
                if exists:
                    await admin.execute(
                        sql.SQL("DROP DATABASE {}").format(sql.Identifier(phase_config.database))
                    )
                if await (
                    await admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,))
                ).fetchone():
                    await admin.execute(
                        sql.SQL("REVOKE CONNECT ON DATABASE postgres FROM {}").format(
                            sql.Identifier(ROLE)
                        )
                    )
                    await admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(ROLE)))


async def test_isolated_prepare_replay_and_owner_cleanup_preserve_production(
    isolated: tuple[RuntimeConfig, TestConfig],
) -> None:
    admin_config, config = isolated
    async with ManagedIdentityCredential() as credential:
        async with await database.connect(admin_config, credential, "newsloom", "postgres") as prod:
            before = await (
                await prod.execute(
                    "SELECT version,checksum FROM newsloom_admin.schema_migrations ORDER BY version"
                )
            ).fetchall()
        assert await phase1_database.prepare(admin_config, credential, config) == 1
        assert await phase1_database.prepare(admin_config, credential, config) == 0
        async with await phase1_database.connect(config, credential) as current:
            manifest = await phase1_database.verify_manifest(current, config)
            assert manifest.run_id == config.run_id
            assert await (await current.execute("SELECT count(*) FROM news")).fetchone() == (0,)
            assert await (
                await current.execute(
                    "SELECT vector_dims(array_fill(0.1::real,ARRAY[1536])::vector)"
                )
            ).fetchone() == (1536,)
            for other in (
                "azure_pg_admin",
                "newsloom_ingestion",
                "newsloom_enrichment",
                "newsloom_mcp",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    async with current.transaction():
                        await current.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(other)))
        with pytest.raises(psycopg.OperationalError):
            async with await psycopg.AsyncConnection.connect(
                os.environ["NEWSLOOM_TEST_POSTGRES_DSN"],
                dbname="newsloom",
                user=ROLE,
            ):
                raise AssertionError("production_database_connected")
        async with await database.connect(admin_config, credential, "newsloom", "postgres") as prod:
            after = await (
                await prod.execute(
                    "SELECT version,checksum FROM newsloom_admin.schema_migrations ORDER BY version"
                )
            ).fetchall()
            assert before == after
            assert await (await prod.execute("SELECT count(*) FROM news")).fetchone() == (0,)
        await phase1_database.cleanup(config, credential)
        await phase1_database.cleanup(config, credential)
        async with await database.connect(
            admin_config, credential, "postgres", "postgres"
        ) as admin:
            assert (
                await (
                    await admin.execute(
                        "SELECT 1 FROM pg_database WHERE datname=%s", (config.database,)
                    )
                ).fetchone()
                is None
            )


async def test_cleanup_refuses_manifest_drift_and_foreign_ownership(
    isolated: tuple[RuntimeConfig, TestConfig],
) -> None:
    admin_config, config = isolated
    async with ManagedIdentityCredential() as credential:
        await phase1_database.prepare(admin_config, credential, config)
        altered = config.model_copy(update={"image_revision": "c" * 64})
        with pytest.raises(AcceptanceFailure, match="manifest_mismatch"):
            await phase1_database.cleanup(altered, credential)
        async with await database.connect(
            admin_config, credential, "postgres", "postgres"
        ) as admin:
            await admin.execute(
                sql.SQL("ALTER DATABASE {} OWNER TO postgres").format(
                    sql.Identifier(config.database)
                )
            )
        with pytest.raises(AcceptanceFailure, match="cleanup_owner_mismatch"):
            await phase1_database.cleanup(config, credential)


async def test_schema_ledger_drift_and_started_run_are_not_reprepared(
    isolated: tuple[RuntimeConfig, TestConfig],
) -> None:
    admin_config, config = isolated
    async with ManagedIdentityCredential() as credential:
        await phase1_database.prepare(admin_config, credential, config)
        async with await phase1_database.connect(config, credential) as current:
            await current.execute("UPDATE newsloom_acceptance_admin.manifest SET started=true")
        with pytest.raises(AcceptanceFailure, match="already_started"):
            await phase1_database.prepare(admin_config, credential, config)
        async with await database.connect(
            admin_config, credential, config.database, "postgres"
        ) as admin:
            await admin.execute(
                "UPDATE newsloom_acceptance_admin.schema_migrations SET checksum=%s", ("d" * 64,)
            )
        with pytest.raises(AcceptanceFailure, match="schema_revision_mismatch"):
            await phase1_database.cleanup(config, credential)


async def test_failed_application_setup_removes_only_its_created_database(
    isolated: tuple[RuntimeConfig, TestConfig],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_config, config = isolated
    original = phase1_database.bootstrap_sql
    monkeypatch.setattr(
        phase1_database, "bootstrap_sql", lambda: original() + "\nSELECT phase1_missing_function();"
    )
    async with ManagedIdentityCredential() as credential:
        with pytest.raises(psycopg.errors.UndefinedFunction):
            await phase1_database.prepare(admin_config, credential, config)
        async with await database.connect(
            admin_config, credential, "postgres", "postgres"
        ) as admin:
            assert (
                await (
                    await admin.execute(
                        "SELECT 1 FROM pg_database WHERE datname=%s", (config.database,)
                    )
                ).fetchone()
                is None
            )
            assert await (
                await admin.execute("SELECT 1 FROM pg_database WHERE datname='newsloom'")
            ).fetchone() == (1,)
