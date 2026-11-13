"""Scheduled operations entry point; logs only counts and outcomes."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Never
from uuid import uuid4

import httpx
import psycopg
from azure.core.exceptions import AzureError
from azure.identity.aio import ManagedIdentityCredential
from azure.storage.blob.aio import ContainerClient
from newsloom_core.diagnostics import configure_logging, event

from newsloom_operations import azure, backup

DATABASE_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
MANAGEMENT_SCOPE = "https://management.azure.com/.default"
ROLE = "newsloom_operations"
CA = "/etc/ssl/certs/ca-certificates.crt"
COMMANDS = (
    "backup",
    "stop-database",
    "start-database",
    "restore-tags",
    "restore-state-access",
    "nightly",
    "wake",
)


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise backup.Failure("operations_invalid_arguments")


class Blobs:
    def __init__(self, client: ContainerClient) -> None:
        self.client = client

    async def upload(self, name: str, data: AsyncIterator[bytes] | bytes) -> None:
        await self.client.upload_blob(name, data, overwrite=False)


async def run_backup(credential: ManagedIdentityCredential, correlation: str) -> None:
    env = os.environ
    token = (await credential.get_token(DATABASE_SCOPE)).token
    dump_env = {
        "PATH": env.get("PATH", "/usr/bin:/bin"),
        "PGHOST": env["POSTGRES_HOST"],
        "PGDATABASE": env["POSTGRES_DATABASE"],
        "PGUSER": ROLE,
        "PGPASSWORD": token,
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": CA,
        "PGAPPNAME": "newsloom-operations",
        "PGCONNECT_TIMEOUT": "15",
    }
    dump = ["pg_dump", "--format=custom", "--no-password"]
    dump += [f"--schema={schema}" for schema in backup.SCHEMAS] + ["--extension=vector"]
    async with (
        await psycopg.AsyncConnection.connect(
            host=env["POSTGRES_HOST"],
            dbname=env["POSTGRES_DATABASE"],
            user=ROLE,
            password=token,
            sslmode="verify-full",
            sslrootcert=CA,
            connect_timeout=15,
            application_name="newsloom-operations",
        ) as connection,
        ContainerClient(
            env["BACKUP_ACCOUNT_URL"], env["BACKUP_CONTAINER"], credential=credential
        ) as client,
    ):
        manifest = await backup.export(connection, dump, dump_env, Blobs(client), datetime.now(UTC))
    tables = manifest["tables"]
    assert isinstance(tables, dict)
    event(
        "database_backup",
        correlation,
        outcome="completed",
        counts={
            "bytes": int(str(manifest["bytes"])),
            "tables": len(tables),
            "rows": sum(int(v) for v in tables.values()),
        },
    )


async def run(command: str, correlation: str) -> None:
    env = os.environ
    failures: list[str] = []
    async with (
        ManagedIdentityCredential(client_id=env["AZURE_CLIENT_ID"]) as credential,
        httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False) as http,
    ):

        async def token() -> str:
            access = await credential.get_token(MANAGEMENT_SCOPE)
            return str(access.token)

        manager = azure.Manager(http, token)

        async def step(name: str) -> None:
            try:
                if name == "backup":
                    await run_backup(credential, correlation)
                elif name in ("stop-database", "start-database"):
                    target = "Stopped" if name == "stop-database" else "Ready"
                    sent = await manager.power(env["POSTGRES_SERVER_ID"], target)
                    event(
                        "database_power",
                        correlation,
                        outcome=target.lower(),
                        counts={"changed": int(sent)},
                    )
                elif name == "restore-tags":
                    groups = [env["AZURE_RESOURCE_GROUP_ID"]]
                    if env.get("AZURE_STATE_RESOURCE_GROUP_ID"):
                        groups.append(env["AZURE_STATE_RESOURCE_GROUP_ID"])
                    # The tags the tenant's policies require: GOVERNANCE_TAGS, a JSON object the
                    # infrastructure sets from the azd environment. None: nothing to restore.
                    tags = json.loads(env.get("GOVERNANCE_TAGS") or "{}")
                    for group in groups:
                        counts = await manager.restore_tags(group, tags)
                        event("governance_tags", correlation, outcome="checked", counts=counts)
                        if counts["failed"]:
                            raise azure.Failure("governance_tags_partially_failed")
                else:
                    changed = await manager.restore_public_access(env["AZURE_STATE_STORAGE_ID"])
                    event(
                        "state_storage_access",
                        correlation,
                        outcome="enabled",
                        counts={"changed": int(changed)},
                    )
            except (
                backup.Failure,
                azure.Failure,
                AzureError,
                httpx.HTTPError,
                psycopg.Error,
                OSError,
                KeyError,
            ) as error:
                category = (
                    str(error)
                    if isinstance(error, backup.Failure | azure.Failure)
                    else f"{name.replace('-', '_')}_{type(error).__name__}"
                )
                event("operations_step", correlation, outcome="failed", category=category)
                failures.append(name)

        steps = {
            "nightly": ("backup", "stop-database"),
            "wake": ("start-database", "restore-tags")
            + (("restore-state-access",) if env.get("AZURE_STATE_STORAGE_ID") else ()),
        }.get(command, (command,))
        for name in steps:
            await step(name)
    if failures:
        raise backup.Failure("operations_failed")


def main() -> None:
    configure_logging()
    correlation = uuid4().hex
    try:
        parser = Parser(prog="newsloom-operations")
        parser.add_argument("command", choices=COMMANDS)
        command = parser.parse_args().command
        asyncio.run(run(command, correlation))
    except backup.Failure as error:
        event("operations", correlation, outcome="failed", category=str(error))
        sys.exit(1)
    event("operations", correlation, outcome="completed", category=command)
