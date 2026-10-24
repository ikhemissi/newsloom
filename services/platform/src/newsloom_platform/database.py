"""Managed-identity PostgreSQL connections and serialized migrations."""

import hashlib
import json
import re
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
            for version in ("001_vector", "002_ingestion", "003_enrichment", "004_mcp_read"):
                sql = migration_sql(f"{version}.sql")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                async with application.transaction():
                    if not await is_applied(application, version, checksum):
                        await application.execute(sql)
                        await record(application, version, checksum)
                        applied += 1
        await admin.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK,))
    return applied


async def ingestion_status(
    config: RuntimeConfig, credential: AsyncTokenCredential
) -> dict[str, int]:
    queries = {
        "sources": "SELECT count(*) FROM feed_sources",
        "found": "SELECT coalesce(sum((counts->>'found')::int), 0) FROM feed_sources",
        "failed_sources": "SELECT count(*) FROM feed_sources "
        "WHERE outcome NOT IN ('fetched','empty','not_modified')",
        "fetched_sources": "SELECT count(*) FROM feed_sources WHERE outcome='fetched'",
        "not_modified_sources": "SELECT count(*) FROM feed_sources WHERE outcome='not_modified'",
        "pending": "SELECT count(*) FROM ingestion_queue WHERE status='pending'",
        "screened_pending": "SELECT count(*) FROM ingestion_queue WHERE score<=threshold "
        "AND model='Microsoft-Decision-1' AND model_version='1' AND status='pending'",
        "rejected": "SELECT count(*) FROM quarantine WHERE disposition='rejected'",
        "deferred": "SELECT count(*) FROM quarantine WHERE disposition='deferred'",
        "resolved": "SELECT count(*) FROM quarantine WHERE disposition='resolved'",
        "duplicate_urls": "WITH active AS (SELECT canonical_url FROM ingestion_queue UNION ALL "
        "SELECT canonical_url FROM quarantine WHERE disposition<>'resolved') "
        "SELECT count(*) FROM (SELECT canonical_url FROM active "
        "GROUP BY canonical_url HAVING count(*)>1) duplicates",
        "duplicate_guids": "WITH active AS (SELECT source,guid FROM ingestion_queue UNION ALL "
        "SELECT source,guid FROM quarantine WHERE disposition<>'resolved') "
        "SELECT count(*) FROM (SELECT source,guid FROM active WHERE guid IS NOT NULL "
        "GROUP BY source,guid HAVING count(*)>1) duplicates",
    }
    result: dict[str, int] = {}
    async with (
        await connect(
            config, credential, config.postgres_database, config.postgres_admin_name
        ) as connection,
        connection.transaction(),
    ):
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        await connection.execute("SET LOCAL statement_timeout='15s'")
        for key, sql in queries.items():
            row = await (await connection.execute(sql)).fetchone()
            if row is None or not isinstance(row[0], int):
                raise PlatformFailure("invalid_ingestion_readback")
            result[key] = row[0]
    return result


async def enrichment_status(
    config: RuntimeConfig, credential: AsyncTokenCredential
) -> dict[str, int]:
    queries = {
        **{
            state: f"SELECT count(*) FROM ingestion_queue WHERE status='{state}'"
            for state in ("pending", "processing", "completed", "failed", "dead_letter")
        },
        "news": "SELECT count(*) FROM news",
        "invalid_vectors": "SELECT count(*) FROM news "
        "WHERE vector_dims(embedding)<>1536 OR vector_norm(embedding)<=0",
        "completion_mismatches": "SELECT count(*) FROM news n JOIN ingestion_queue q ON q.id=n.id "
        "WHERE q.status<>'completed' OR q.source IS DISTINCT FROM n.source "
        "OR q.guid IS DISTINCT FROM n.guid OR q.canonical_url IS DISTINCT FROM n.canonical_url",
        "completed_without_news": "SELECT count(*) FROM ingestion_queue q "
        "LEFT JOIN news n ON n.id=q.id WHERE q.status='completed' AND n.id IS NULL",
        "duplicate_urls": "SELECT count(*) FROM (SELECT canonical_url FROM news "
        "GROUP BY canonical_url HAVING count(*)>1) duplicates",
        "duplicate_guids": "SELECT count(*) FROM (SELECT source,guid FROM news "
        "WHERE guid IS NOT NULL GROUP BY source,guid HAVING count(*)>1) duplicates",
        "rejected": "SELECT count(*) FROM quarantine WHERE disposition='rejected'",
        "published_rejections": "SELECT count(*) FROM news n JOIN quarantine q "
        "ON q.canonical_url=n.canonical_url OR (q.source=n.source AND q.guid=n.guid) "
        "WHERE q.disposition='rejected'",
    }
    result: dict[str, int] = {}
    async with (
        await connect(
            config, credential, config.postgres_database, config.postgres_admin_name
        ) as connection,
        connection.transaction(),
    ):
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        await connection.execute("SET LOCAL statement_timeout='15s'")
        for key, sql in queries.items():
            row = await (await connection.execute(sql)).fetchone()
            if row is None or not isinstance(row[0], int):
                raise PlatformFailure("invalid_enrichment_readback")
            result[key] = row[0]
    return result


async def ingestion_sources(
    config: RuntimeConfig, credential: AsyncTokenCredential
) -> list[tuple[str, str, str, dict[str, int]]]:
    keys = (
        "found",
        "filtered",
        "duplicates",
        "staged",
        "malformed_rejected",
        "accepted",
        "security_rejected",
        "deferred",
        "feed_item",
        "article_metadata",
        "article_body",
        "recovery_attempted",
        "recovery_failed",
        "recovery_deferred",
    )
    result: list[tuple[str, str, str, dict[str, int]]] = []
    async with (
        await connect(
            config, credential, config.postgres_database, config.postgres_admin_name
        ) as connection,
        connection.transaction(),
    ):
        await connection.execute("SET TRANSACTION READ ONLY")
        await connection.execute("SET LOCAL statement_timeout='15s'")
        rows = await (
            await connection.execute(
                "SELECT id,coalesce(outcome,'not_checked'),coalesce(last_run,''),counts "
                "FROM feed_sources ORDER BY id"
            )
        ).fetchall()
        for source, outcome, correlation, counts in rows:
            if (
                not isinstance(source, str)
                or not re.fullmatch(r"[a-z0-9-]+", source)
                or not isinstance(outcome, str)
                or not re.fullmatch(r"[A-Za-z0-9_]+", outcome)
                or not isinstance(correlation, str)
                or (correlation and not re.fullmatch(r"[A-Za-z0-9_-]+", correlation))
                or not isinstance(counts, dict)
            ):
                raise PlatformFailure("invalid_source_readback")
            safe_counts: dict[str, int] = {}
            for key in keys:
                value = counts.get(key, 0)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise PlatformFailure("invalid_source_readback")
                safe_counts[key] = value
            result.append((source, outcome, correlation, safe_counts))
    return result
