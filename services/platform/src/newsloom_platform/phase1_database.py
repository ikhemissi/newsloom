"""Explicit acceptance-only database lifecycle; never part of production migration startup."""

import asyncio
import hashlib
import time
from importlib.resources import files
from typing import Literal

import psycopg
from azure.core.credentials_async import AsyncTokenCredential
from newsloom_core.phase1_contracts import (
    ROLE,
    AcceptanceFailure,
    Manifest,
    TestConfig,
    prepared_manifest,
)
from psycopg import sql
from psycopg.types.json import Jsonb

from newsloom_platform import database
from newsloom_platform.config import RuntimeConfig

VERSIONS = ("002_ingestion", "003_enrichment", "004_mcp_read")


def bootstrap_sql() -> str:
    return (
        files("newsloom_platform")
        .joinpath("acceptance_migrations", "001_test_database.sql")
        .read_text()
    )


def schema_revision() -> str:
    values = [bootstrap_sql(), *(database.migration_sql(name + ".sql") for name in VERSIONS)]
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


async def connect(
    config: TestConfig,
    credential: AsyncTokenCredential,
    *,
    maintenance: bool = False,
) -> psycopg.AsyncConnection[tuple[object, ...]]:
    token = await credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
    current = await psycopg.AsyncConnection.connect(
        host=config.postgres_host,
        dbname="postgres" if maintenance else config.database,
        user=ROLE,
        password=token.token,
        sslmode="verify-full",
        sslrootcert="/etc/ssl/certs/ca-certificates.crt",
        connect_timeout=15,
        autocommit=True,
        application_name="newsloom-phase1",
        options="-c statement_timeout=15000 -c idle_in_transaction_session_timeout=30000",
    )
    verified = False
    try:
        row = await (await current.execute("SELECT current_database(),current_user")).fetchone()
        if row != ("postgres" if maintenance else config.database, ROLE):
            raise AcceptanceFailure("acceptance_connection_identity_mismatch")
        if not maintenance:
            await verify_manifest(current, config)
        verified = True
    finally:
        if not verified:
            await current.close()
    return current


async def verify_role(
    connection: psycopg.AsyncConnection[tuple[object, ...]],
    config: TestConfig,
) -> None:
    row = await (
        await connection.execute(
            "SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,"
            "pg_has_role(rolname,'azure_pg_admin','member'),"
            "pg_has_role(rolname,'newsloom_ingestion','member'),"
            "pg_has_role(rolname,'newsloom_enrichment','member'),"
            "pg_has_role(rolname,'newsloom_mcp','member'),"
            "has_database_privilege(rolname,'newsloom','CONNECT') "
            "FROM pg_roles WHERE rolname=%s",
            (ROLE,),
        )
    ).fetchone()
    if row != (False,) * 9:
        raise AcceptanceFailure("acceptance_role_not_isolated")
    mappings = await (
        await connection.execute("SELECT * FROM pg_catalog.pgaadauth_list_principals(false)")
    ).fetchall()
    matched = [item for item in mappings if str(item[0]) == ROLE]
    if (
        len(matched) != 1
        or len(matched[0]) != 6
        or matched[0][1] != "service"
        or str(matched[0][2]).lower() != str(config.principal_id)
        or matched[0][5] != 0
    ):
        raise AcceptanceFailure("acceptance_principal_mapping_mismatch")


async def verify_manifest(
    connection: psycopg.AsyncConnection[tuple[object, ...]],
    config: TestConfig,
    *,
    expected_owner: str = ROLE,
) -> Manifest:
    row = await (
        await connection.execute(
            "SELECT current_database(),pg_get_userbyid(datdba) FROM pg_database "
            "WHERE datname=current_database()"
        )
    ).fetchone()
    if row != (config.database, expected_owner):
        raise AcceptanceFailure("acceptance_database_ownership_mismatch")
    row = await (
        await connection.execute("SELECT payload FROM newsloom_acceptance_admin.manifest")
    ).fetchone()
    if row is None:
        raise AcceptanceFailure("acceptance_manifest_missing")
    manifest = Manifest.model_validate(row[0])
    expected = prepared_manifest(config, schema_revision())
    if manifest.model_dump(exclude={"prepared_at"}) != expected.model_dump(exclude={"prepared_at"}):
        raise AcceptanceFailure("acceptance_manifest_mismatch")
    ledger = await (
        await connection.execute(
            "SELECT version,checksum FROM newsloom_acceptance_admin.schema_migrations "
            "ORDER BY version"
        )
    ).fetchall()
    expected_ledger = [("001_test_database", hashlib.sha256(bootstrap_sql().encode()).hexdigest())]
    expected_ledger.extend(
        (version, hashlib.sha256(database.migration_sql(version + ".sql").encode()).hexdigest())
        for version in VERSIONS
    )
    if ledger != expected_ledger:
        raise AcceptanceFailure("acceptance_schema_revision_mismatch")
    return manifest


async def prepare(
    admin_config: RuntimeConfig,
    credential: AsyncTokenCredential,
    config: TestConfig,
) -> Literal[0, 1]:
    if config.postgres_host != admin_config.postgres_host:
        raise AcceptanceFailure("acceptance_server_mismatch")
    expected = prepared_manifest(config, schema_revision())
    created, complete = False, False
    async with await database.connect(
        admin_config,
        credential,
        "postgres",
        admin_config.postgres_admin_name,
    ) as admin:
        await admin.execute(
            "SELECT pg_advisory_lock(hashtextextended(%s,0))",
            ("phase1/" + config.run_id,),
        )
        try:
            roles = await (
                await admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,))
            ).fetchone()
            if roles is None:
                await admin.execute(
                    database.migration_sql("001_principals.sql"),
                    (ROLE, str(config.principal_id)),
                )
            await verify_role(admin, config)
            exists = await (
                await admin.execute(
                    "SELECT 1 FROM pg_database WHERE datname=%s", (config.database,)
                )
            ).fetchone()
            if exists is not None:
                async with await database.connect(
                    admin_config,
                    credential,
                    config.database,
                    admin_config.postgres_admin_name,
                ) as current:
                    await verify_manifest(current, config)
                    state = await (
                        await current.execute(
                            "SELECT started FROM newsloom_acceptance_admin.manifest"
                        )
                    ).fetchone()
                    if state != (False,):
                        raise AcceptanceFailure("acceptance_run_already_started")
                complete = True
                return 0
            await admin.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(config.database),
                )
            )
            created = True
            await admin.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(config.database),
                )
            )
            await admin.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {},{}").format(
                    sql.Identifier(config.database),
                    sql.Identifier(ROLE),
                    sql.Identifier(admin_config.postgres_admin_name),
                )
            )
            await admin.execute(
                sql.SQL("GRANT CONNECT ON DATABASE postgres TO {}").format(
                    sql.Identifier(ROLE),
                )
            )
            async with (
                await database.connect(
                    admin_config,
                    credential,
                    config.database,
                    admin_config.postgres_admin_name,
                ) as current,
                current.transaction(),
            ):
                await current.execute(bootstrap_sql())
                await current.execute(
                    "INSERT INTO newsloom_acceptance_admin.schema_migrations VALUES (%s,%s)",
                    ("001_test_database", hashlib.sha256(bootstrap_sql().encode()).hexdigest()),
                )
                for version in VERSIONS:
                    content = database.migration_sql(version + ".sql")
                    await current.execute(content)
                    await current.execute(
                        "INSERT INTO newsloom_acceptance_admin.schema_migrations VALUES (%s,%s)",
                        (version, hashlib.sha256(content.encode()).hexdigest()),
                    )
                await current.execute(
                    "INSERT INTO newsloom_acceptance_admin.manifest(payload) VALUES (%s)",
                    (Jsonb(expected.model_dump(mode="json")),),
                )
                await current.execute(
                    sql.SQL(
                        "GRANT USAGE ON SCHEMA public,newsloom_acceptance_admin TO {}; "
                        "GRANT SELECT,INSERT,UPDATE,DELETE ON public.feed_sources,"
                        "public.ingestion_queue,public.quarantine,public.news TO {}; "
                        "GRANT SELECT ON newsloom_acceptance_admin.manifest,"
                        "newsloom_acceptance_admin.schema_migrations TO {}; "
                        "GRANT UPDATE(started) ON newsloom_acceptance_admin.manifest TO {}"
                    ).format(*(sql.Identifier(ROLE) for _ in range(4)))
                )
            await admin.execute(
                sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                    sql.Identifier(config.database),
                    sql.Identifier(ROLE),
                )
            )
            async with await database.connect(
                admin_config,
                credential,
                config.database,
                admin_config.postgres_admin_name,
            ) as current:
                await verify_manifest(current, config)
            complete = True
            return 1
        finally:
            try:
                if created and not complete:
                    await admin.execute(
                        sql.SQL("DROP DATABASE {}").format(
                            sql.Identifier(config.database),
                        )
                    )
            finally:
                await admin.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s,0))",
                    ("phase1/" + config.run_id,),
                )


async def cleanup(
    config: TestConfig,
    credential: AsyncTokenCredential,
    *,
    admin_config: RuntimeConfig | None = None,
) -> None:
    async def open_connection(maintenance: bool) -> psycopg.AsyncConnection[tuple[object, ...]]:
        if admin_config is None:
            return await connect(config, credential, maintenance=maintenance)
        if config.postgres_host != admin_config.postgres_host:
            raise AcceptanceFailure("acceptance_server_mismatch")
        return await database.connect(
            admin_config,
            credential,
            "postgres" if maintenance else config.database,
            admin_config.postgres_admin_name,
        )

    async with await open_connection(True) as admin:
        await admin.execute(
            "SELECT pg_advisory_lock(hashtextextended(%s,0))",
            ("phase1/" + config.run_id,),
        )
        try:
            owner = await (
                await admin.execute(
                    "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s",
                    (config.database,),
                )
            ).fetchone()
            if owner is not None:
                if owner != (ROLE,):
                    raise AcceptanceFailure("acceptance_cleanup_owner_mismatch")
                async with await open_connection(False) as current:
                    await verify_manifest(current, config)
                deadline = time.monotonic() + 30
                while True:
                    sessions = await (
                        await admin.execute(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname=%s",
                            (config.database,),
                        )
                    ).fetchone()
                    if sessions == (0,):
                        break
                    if time.monotonic() >= deadline:
                        raise AcceptanceFailure("acceptance_cleanup_connections_still_open")
                    await asyncio.sleep(1)
                await admin.execute(
                    sql.SQL("DROP DATABASE {}").format(
                        sql.Identifier(config.database),
                    )
                )
            if (
                await (
                    await admin.execute(
                        "SELECT 1 FROM pg_database WHERE datname=%s", (config.database,)
                    )
                ).fetchone()
                is not None
            ):
                raise AcceptanceFailure("acceptance_cleanup_not_verified")
        finally:
            await admin.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s,0))",
                ("phase1/" + config.run_id,),
            )
