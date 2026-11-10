"""Consistent pg_dump export streamed to immutable blob storage with a manifest."""

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime
from typing import Protocol

import psycopg

CHUNK = 4 * 1024 * 1024
SCHEMAS = ("public", "newsloom_admin")


class Failure(Exception):
    """Content-free failure category."""


class Container(Protocol):
    async def upload(self, name: str, data: AsyncIterator[bytes] | bytes) -> None: ...


async def table_counts(
    connection: psycopg.AsyncConnection[tuple[object, ...]],
) -> dict[str, int]:
    rows = await (
        await connection.execute(
            "SELECT schemaname, tablename FROM pg_tables WHERE schemaname = ANY(%s) "
            "ORDER BY schemaname, tablename",
            (list(SCHEMAS),),
        )
    ).fetchall()
    counts: dict[str, int] = {}
    for schema, table in rows:
        query = psycopg.sql.SQL("SELECT count(*) FROM {}.{}").format(
            psycopg.sql.Identifier(str(schema)), psycopg.sql.Identifier(str(table))
        )
        row = await (await connection.execute(query)).fetchone()
        if row is None or not isinstance(row[0], int):
            raise Failure("backup_count_failed")
        counts[f"{schema}.{table}"] = row[0]
    return counts


async def export(
    connection: psycopg.AsyncConnection[tuple[object, ...]],
    dump: Sequence[str],
    dump_env: Mapping[str, str],
    container: Container,
    now: datetime,
) -> dict[str, object]:
    """Dump the database in the snapshot used for the row counts, then write the manifest."""
    name = f"postgres/{now:%Y/%m/%d}/newsloom-{now:%Y%m%dT%H%M%SZ}"
    digest = hashlib.sha256()
    size = 0
    async with connection.transaction():
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        row = await (await connection.execute("SELECT pg_export_snapshot()")).fetchone()
        if row is None:
            raise Failure("backup_snapshot_failed")
        counts = await table_counts(connection)
        version = await (await connection.execute("SHOW server_version")).fetchone()
        process = await asyncio.create_subprocess_exec(
            *dump,
            f"--snapshot={row[0]}",
            env=dict(dump_env),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert process.stdout is not None
        stdout = process.stdout

        async def chunks() -> AsyncIterator[bytes]:
            nonlocal size
            while chunk := await stdout.read(CHUNK):
                digest.update(chunk)
                size += len(chunk)
                yield chunk
            # Raising before the iterator ends prevents the upload from committing.
            if await process.wait() != 0 or size == 0:
                raise Failure("backup_dump_failed")

        try:
            await container.upload(f"{name}.dump", chunks())
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    manifest = {
        "created_at": now.isoformat(),
        "dump": f"{name}.dump",
        "format": "pg_dump custom",
        "server_version": str(version[0]) if version else "",
        "bytes": size,
        "sha256": digest.hexdigest(),
        "tables": counts,
    }
    await container.upload(f"{name}.json", json.dumps(manifest, indent=2).encode())
    return manifest
