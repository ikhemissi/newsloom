"""Managed-identity PostgreSQL connections and serialized migrations."""

import hashlib
import json
from importlib.resources import files

from azure.core.credentials_async import AsyncTokenCredential
from psycopg import AsyncConnection

from newsloom_platform.config import (
    RUNTIME_WORKLOADS,
    PlatformFailure,
    RuntimeConfig,
    database_role,
)

ADVISORY_LOCK = 736981071
LEDGER_SQL = """
CREATE SCHEMA IF NOT EXISTS newsloom_admin;
REVOKE ALL ON SCHEMA newsloom_admin FROM PUBLIC;
CREATE TABLE IF NOT EXISTS newsloom_admin.schema_migrations (
    version text PRIMARY KEY,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
"""


async def connect(
    config: RuntimeConfig, credential: AsyncTokenCredential, database: str, user: str
) -> AsyncConnection[tuple[object, ...]]:
    token = await credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
    return await AsyncConnection.connect(
        host=config.postgres_host,
        dbname=database,
        user=user,
        password=token.token,
        sslmode="verify-full",
        sslrootcert="/etc/ssl/certs/ca-certificates.crt",
        connect_timeout=15,
        application_name="newsloom-platform",
        autocommit=True,
    )


def migration_sql(name: str) -> str:
    return files("newsloom_platform").joinpath("migrations", name).read_text()


async def is_applied(
    connection: AsyncConnection[tuple[object, ...]], version: str, checksum: str
) -> bool:
    await connection.execute(LEDGER_SQL)
    cursor = await connection.execute(
        "SELECT checksum FROM newsloom_admin.schema_migrations WHERE version = %s", (version,)
    )
    row = await cursor.fetchone()
    if row is None:
        return False
    if row[0] != checksum:
        raise PlatformFailure("migration_checksum_mismatch")
    return True


async def record(
    connection: AsyncConnection[tuple[object, ...]], version: str, checksum: str
) -> None:
    await connection.execute(
        "INSERT INTO newsloom_admin.schema_migrations(version, checksum) VALUES (%s, %s)",
        (version, checksum),
    )


async def verify_principals(
    connection: AsyncConnection[tuple[object, ...]], config: RuntimeConfig, *, create: bool
) -> None:
    cursor = await connection.execute("SELECT * FROM pg_catalog.pgaadauth_list_principals(false)")
    mappings = {str(row[0]): row for row in await cursor.fetchall()}
    cursor = await connection.execute(
        "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, "
        "pg_has_role(rolname, 'azure_pg_admin', 'member') FROM pg_roles "
        "WHERE rolname = ANY(%s)",
        ([database_role(w) for w in RUNTIME_WORKLOADS],),
    )
    roles = {str(row[0]): row for row in await cursor.fetchall()}
    for workload in RUNTIME_WORKLOADS:
        role = database_role(workload)
        expected = str(config.identities[workload].principal_id)
        if role in roles:
            mapped = mappings.get(role)
            if (
                mapped is None
                or len(mapped) != 6
                or mapped[1] != "service"
                or str(mapped[2]).lower() != expected
                or mapped[5] != 0
                or any(roles[role][1:])
            ):
                raise PlatformFailure("principal_mapping_mismatch")
        elif create:
            await connection.execute(migration_sql("001_principals.sql"), (role, expected))
        else:
            raise PlatformFailure("principal_mapping_missing")


async def migrate(config: RuntimeConfig, credential: AsyncTokenCredential) -> int:
    principal_sql = migration_sql("001_principals.sql")
    mapping = {w: str(config.identities[w].principal_id) for w in RUNTIME_WORKLOADS}
    checksum = hashlib.sha256(
        principal_sql.encode() + json.dumps(mapping, sort_keys=True).encode()
    ).hexdigest()
    applied = 0
    # Entra role functions exist in postgres; the session lock spans both database phases.
    async with await connect(config, credential, "postgres", config.postgres_admin_name) as admin:
        await admin.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK,))
        async with admin.transaction():
            already = await is_applied(admin, "001_workload_principals", checksum)
            await verify_principals(admin, config, create=not already)
            if not already:
                await record(admin, "001_workload_principals", checksum)
                applied += 1
        async with await connect(
            config, credential, config.postgres_database, config.postgres_admin_name
        ) as application:
            sql = migration_sql("001_vector.sql")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            async with application.transaction():
                if not await is_applied(application, "001_vector", checksum):
                    await application.execute(sql)
                    await record(application, "001_vector", checksum)
                    applied += 1
        await admin.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK,))
    return applied
