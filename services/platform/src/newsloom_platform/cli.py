"""Explicit operational commands with content-free failure reporting."""

import argparse
import asyncio
import logging
import os
import subprocess
from typing import Never
from uuid import UUID, uuid4

import httpx
import psycopg
from azure.core.exceptions import AzureError
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.phase1_contracts import AcceptanceFailure, TestConfig
from pydantic import ValidationError

from newsloom_platform.config import PlatformFailure, RuntimeConfig
from newsloom_platform.database import (
    enrichment_status,
    ingestion_sources,
    ingestion_status,
    migrate,
)
from newsloom_platform.events import configure_logging, event


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise PlatformFailure("invalid_arguments")


async def runtime(command: str, workload: str, correlation: str) -> None:
    config = RuntimeConfig.from_environment(os.environ)
    identity = config.identities[workload]
    async with (
        asyncio.timeout(600),
        ManagedIdentityCredential(client_id=str(identity.client_id)) as credential,
    ):
        if command == "migrate":
            applied = await migrate(config, credential)
            event("migrations", "success", correlation, checks=applied)
        elif command in ("phase1-prepare", "phase1-cleanup"):
            from newsloom_platform import phase1_database

            acceptance = TestConfig.from_encoded(os.environ["PHASE1_CONFIG_BASE64"], correlation)
            if command == "phase1-prepare":
                prepared = await phase1_database.prepare(config, credential, acceptance)
                event("phase1_database", "prepared", correlation, checks=prepared)
            else:
                await phase1_database.cleanup(acceptance, credential, admin_config=config)
                event("phase1_database", "removed", correlation, checks=1)
        elif command in ("mcp-eval-prepare", "mcp-eval-cleanup"):
            from newsloom_platform.mcp_evaluation import cleanup, prepare

            if command == "mcp-eval-prepare":
                count = await prepare(config, credential, correlation)
                event("mcp_evaluation_schema", "prepared", correlation, checks=count)
            else:
                await cleanup(config, credential, correlation)
                event("mcp_evaluation_schema", "removed", correlation, checks=1)
        elif command == "enrichment-status":
            counts = await enrichment_status(config, credential)
            event("enrichment_readback", "success", correlation, counts=counts)
        elif command == "ingestion-status":
            counts = await ingestion_status(config, credential)
            event("ingestion_readback", "success", correlation, counts=counts)
            for source, outcome, source_run, source_counts in await ingestion_sources(
                config, credential
            ):
                event(
                    "ingestion_source_readback",
                    outcome,
                    correlation,
                    source=source,
                    source_run=source_run,
                    counts=source_counts,
                )
        else:
            from newsloom_platform.probe import probe

            checks = await probe(config, credential, workload, correlation)
            event("platform_probe", "success", correlation, checks=checks, workload=workload)


def main() -> None:
    configure_logging()
    correlation = uuid4().hex
    try:
        correlation = UUID(os.environ.get("PLATFORM_PROBE_RUN_ID", correlation)).hex
        parser = Parser(description=__doc__)
        parser.add_argument(
            "command",
            choices=[
                "migrate",
                "probe",
                "build",
                "execute",
                "verify",
                "ingestion-status",
                "build-ingestion",
                "execute-ingestion",
                "calibrate-ingestion",
                "read-ingestion",
                "enrichment-status",
                "build-enrichment",
                "execute-enrichment",
                "evaluate-enrichment",
                "read-enrichment",
                "verify-enrichment",
                "build-mcp",
                "verify-mcp",
                "prepare-mcp-evaluation",
                "cleanup-mcp-evaluation",
                "mcp-eval-prepare",
                "mcp-eval-cleanup",
                "prepare-mcp-identity",
                "prepare-agent-identity",
                "prepare-agent-layer",
                "prepare-agent-evaluation-layer",
                "build-agent",
                "verify-agent",
                "evaluate-mcp",
                "build-phase1",
                "prepare-phase1-layer",
                "configure-phase1-github",
                "prepare-phase1-acceptance",
                "cleanup-phase1-acceptance",
                "phase1-prepare",
                "phase1-cleanup",
            ],
        )
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument(
            "workload", nargs="?", choices=["ingestion", "enrichment", "mcp", "migrations"]
        )
        args = parser.parse_args()
        if args.force and args.command != "execute-ingestion":
            raise PlatformFailure("force_requires_ingestion_execution")
        if not 1 <= args.limit <= 25 or (args.limit != 25 and args.command != "execute-enrichment"):
            raise PlatformFailure("invalid_enrichment_limit")
        if args.command != "probe" and args.workload is not None:
            raise PlatformFailure("unexpected_workload_argument")
        if args.command in [
            "migrate",
            "probe",
            "ingestion-status",
            "enrichment-status",
            "mcp-eval-prepare",
            "mcp-eval-cleanup",
            "phase1-prepare",
            "phase1-cleanup",
        ]:
            workload = args.workload if args.command == "probe" else "migrations"
            if workload is None:
                raise PlatformFailure("workload_required")
            asyncio.run(runtime(args.command, workload, correlation))
        else:
            from newsloom_platform.control import control

            if args.force:
                control(args.command, correlation, force=True)
            elif args.command == "execute-enrichment":
                control(args.command, correlation, limit=args.limit)
            else:
                control(args.command, correlation)
    except (
        PlatformFailure,
        AcceptanceFailure,
        ValidationError,
        KeyError,
        ValueError,
        TimeoutError,
        AzureError,
        psycopg.Error,
        httpx.HTTPError,
        subprocess.SubprocessError,
        OSError,
    ) as error:
        category = (
            str(error)
            if isinstance(error, (PlatformFailure, AcceptanceFailure))
            else type(error).__name__
        )
        event("platform", "failure", correlation, category=category)
        raise SystemExit(1) from None
    finally:
        logging.shutdown()
