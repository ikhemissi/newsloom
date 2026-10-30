"""Fixed, content-free record verification; also executable in the retained image."""

import asyncio
import base64
import hashlib
import json
import logging
import os
import sys
import time
import zlib
from datetime import UTC, datetime

from psycopg import AsyncConnection, IsolationLevel

MAX_ROWS = 4096
MAX_BYTES = 512 * 1024
PREFIX = "NEWSLOOM_EVALUATION_RECORDS "
SCHEMA = "news-metadata-v1"
METADATA = (
    "id,title,summary,source,category,tags,published_at,"
    "canonical_url,author,date_origin,publisher_categories"
)


def encoded(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cutoff(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != UTC.utcoffset(None):
        raise ValueError("record_cutoff_not_utc")
    return parsed


async def collect(
    connection: AsyncConnection[tuple[object, ...]],
    cutoffs: tuple[str, str] | None,
    expected_user: str,
) -> dict[str, object]:
    start = time.monotonic()
    boundaries = tuple(cutoff(value) for value in cutoffs) if cutoffs else ()
    if (
        (boundaries and boundaries[0] >= boundaries[1])
        or (not boundaries and expected_user != "newsloom_mcp")
        or not connection.autocommit
    ):
        raise ValueError("record_verification_boundary")
    await connection.set_read_only(True)
    await connection.set_isolation_level(IsolationLevel.REPEATABLE_READ)
    async with asyncio.timeout(570), connection.transaction():
        await connection.execute("SET LOCAL statement_timeout = '60s'")
        await connection.execute("SET LOCAL transaction_timeout = '540s'")
        await connection.execute("SET LOCAL idle_in_transaction_session_timeout = '60s'")
        await connection.execute("SET LOCAL TIME ZONE 'UTC'")
        settings = await (
            await connection.execute(
                "SELECT current_user, current_setting('transaction_read_only'), "
                "current_setting('transaction_isolation'), "
                "current_setting('statement_timeout'), current_setting('transaction_timeout')"
            )
        ).fetchone()
        if settings != (expected_user, "on", "repeatable read", "1min", "9min"):
            raise ValueError("record_read_only_not_enforced")
        # LIMIT is checked before accepting evidence, never treated as a complete sample.
        query = (
            "SELECT id::text,md5(row_to_json(n)::text),"
            "encode(sha256(convert_to(row_to_json(n)::text,'UTF8')),'hex'),published_at,"
            "encode(sha256(convert_to(canonical_url,'UTF8')),'hex')"
            + (",created_at<=%s,created_at<=%s" if boundaries else "")
            + " FROM "
            f"(SELECT {METADATA} FROM public.news) AS n "
            + (
                "JOIN (SELECT id AS stored_id,created_at FROM public.news) AS stored "
                "ON stored.stored_id=n.id "
                if boundaries
                else ""
            )
            + "ORDER BY id LIMIT 4097"
        )
        cursor = await connection.execute(query, boundaries or None)
        records = await cursor.fetchall()
        if not 0 < len(records) <= MAX_ROWS:
            raise ValueError("record_row_limit")
        if len({row[0] for row in records}) != len(records):
            raise ValueError("record_duplicate_identity")
        reconstructions = []
        for index, boundary in enumerate(cutoffs or ()):
            subset = [row for row in records if row[5 + index] is True]
            if not subset:
                raise ValueError("record_historical_subset_empty")
            if any(not isinstance(row[3], datetime) for row in subset):
                raise ValueError("record_publication_time_missing")
            recent = sorted(
                subset,
                key=lambda row: (
                    -datetime.fromisoformat(str(row[3])).timestamp(),
                    str(row[0]),
                ),
            )[0]
            reconstructions.append(
                {
                    "cutoff_utc": boundary,
                    "news_count": len(subset),
                    "news_metadata_fingerprint": hashlib.sha256(
                        encoded([[row[0], row[1]] for row in subset])
                    ).hexdigest(),
                    "recent_id_sha256": sha(str(recent[0])),
                    "recent_url_sha256": recent[4],
                }
            )
        evidence: dict[str, object] = {
            "schema": SCHEMA,
            "outcome": "success",
            "verified_utc": datetime.now(UTC).isoformat(),
            "news_count": len(records),
            "rows": sorted([[sha(str(row[0])), row[2]] for row in records]),
            "historical_membership": [
                0 if row[5] is True else 1 if row[6] is True else 2
                for row in sorted(records, key=lambda row: sha(str(row[0])))
            ]
            if boundaries
            else [],
            "reconstructions": reconstructions,
            "read_only": True,
            "identity_sha256": sha(expected_user),
            "statement_timeout_ms": 60000,
            "transaction_timeout_ms": 540000,
            "elapsed_ms": int((time.monotonic() - start) * 1000),
            "writes_performed": 0,
            "model_calls": 0,
        }
        if len(encoded(evidence)) > MAX_BYTES:
            raise ValueError("record_evidence_limit")
        return evidence


def lines(value: dict[str, object]) -> list[str]:
    raw = encoded(value)
    if len(raw) > MAX_BYTES:
        raise ValueError("record_evidence_limit")
    payload = base64.b64encode(zlib.compress(raw)).decode()
    chunks = [payload[index : index + 4096] for index in range(0, len(payload), 4096)]
    result = [
        PREFIX
        + encoded(
            {
                "index": index,
                "total": len(chunks),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "payload": chunk,
            }
        ).decode()
        for index, chunk in enumerate(chunks)
    ]
    if len("\n".join(result).encode()) > MAX_BYTES:
        raise ValueError("record_wire_limit")
    return result


async def main() -> None:
    from azure.identity.aio import ManagedIdentityCredential

    from newsloom_platform.config import RuntimeConfig
    from newsloom_platform.database import connect

    logging.disable(logging.CRITICAL)
    if len(sys.argv) != 3:
        raise ValueError("record_cutoffs_required")
    config = RuntimeConfig.from_environment(os.environ)
    identity = config.identities["migrations"]
    if os.environ.get("AZURE_CLIENT_ID") != str(identity.client_id):
        raise ValueError("record_migration_identity_mismatch")
    async with (
        asyncio.timeout(570),
        ManagedIdentityCredential(client_id=str(identity.client_id)) as credential,
        await connect(
            config, credential, config.postgres_database, config.postgres_admin_name
        ) as connection,
    ):
        value = await collect(connection, (sys.argv[1], sys.argv[2]), config.postgres_admin_name)
    for line in lines(value):
        print(line, flush=True)


if __name__ == "__main__":
    from azure.core.exceptions import AzureError
    from psycopg import Error

    from newsloom_platform.config import PlatformFailure

    try:
        asyncio.run(main())
    except (AzureError, Error, PlatformFailure, ValueError, KeyError, TimeoutError) as error:
        print(PREFIX + encoded({"outcome": "failure", "category": type(error).__name__}).decode())
        raise SystemExit(1) from None
