"""Run ingestion explicitly; production never substitutes an accepting scanner."""

import argparse
import asyncio
import math
import os
import time
from pathlib import Path
from typing import Never
from uuid import UUID, uuid4

import aiohttp
import httpx
import psycopg
from azure.core.exceptions import AzureError
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.feeds import load_feed_catalogue
from pydantic import ValidationError

from newsloom_ingestion.job import process_items, run, select_sources
from newsloom_ingestion.models import IngestionFailure, Limits, source_counts
from newsloom_ingestion.repository import Repository
from newsloom_ingestion.retrieval import PublicClient
from newsloom_ingestion.scanner import DecisionScanner, calibrate
from newsloom_ingestion.telemetry import Telemetry, configure_logging, event


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise IngestionFailure("invalid_arguments")


async def runtime(args: argparse.Namespace, correlation: str) -> None:
    sources = select_sources(load_feed_catalogue(args.catalogue), args.source)
    limits = Limits()
    if args.command == "fetch":
        if len(sources) != 2 or {source.kind for source in sources} != {"rss", "atom"}:
            raise IngestionFailure("local_smoke_requires_one_rss_one_atom")
        for source in sources:
            feed_client = PublicClient(limits)
            deadline = time.monotonic() + limits.feed_seconds
            document = await feed_client.fetch(str(source.url), {}, deadline)
            if document.status != 200:
                raise IngestionFailure(f"feed_http_{document.status}")
            counts = source_counts()
            await process_items(source, document, feed_client, counts, deadline, correlation)
            event(
                "fetch",
                correlation,
                source=source.id,
                outcome="partial" if counts["recovery_deferred"] else "success",
                counts=counts,
            )
        return
    env = os.environ
    client_id = env["AZURE_CLIENT_ID"]
    threshold_text = env.get("SCANNER_THRESHOLD", "")
    threshold = float(threshold_text) if threshold_text else None
    if args.command == "run" and (threshold is None or not math.isfinite(threshold)):
        raise IngestionFailure("scanner_threshold_required")
    async with (
        ManagedIdentityCredential(client_id=client_id) as credential,
        httpx.AsyncClient() as client,
    ):
        scanner = DecisionScanner(
            client, credential, env["MODEL_ENDPOINT"], env["SCREENING_DEPLOYMENT"], threshold
        )
        if args.command == "calibrate":
            result = await calibrate(scanner, time.monotonic() + limits.job_seconds - 20)
            event(
                "calibration",
                correlation,
                outcome="success",
                counts={
                    **result,
                    "model": env["SCREENING_MODEL"],
                    "model_version": env["SCREENING_VERSION"],
                },
            )
            return
        token = await credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        async with await psycopg.AsyncConnection.connect(
            host=env["POSTGRES_HOST"],
            dbname=env["POSTGRES_DATABASE"],
            user="newsloom_ingestion",
            password=token.token,
            sslmode="verify-full",
            sslrootcert="/etc/ssl/certs/ca-certificates.crt",
            connect_timeout=15,
            options="-c statement_timeout=15000 -c idle_in_transaction_session_timeout=30000",
            application_name="newsloom-ingestion",
            autocommit=True,
        ) as connection:
            repository = Repository(connection, env["SCREENING_MODEL"], env["SCREENING_VERSION"])
            telemetry = Telemetry(env["APPLICATIONINSIGHTS_CONNECTION_STRING"], client_id)
            start = time.monotonic()
            try:
                counts = await run(sources, repository, scanner, correlation, force=args.force)
                telemetry.record(correlation, counts, time.monotonic() - start)
            finally:
                await asyncio.to_thread(telemetry.close)


def main() -> None:
    configure_logging()
    correlation = uuid4().hex
    try:
        correlation = UUID(os.environ.get("PLATFORM_PROBE_RUN_ID", correlation)).hex
        parser = Parser(description=__doc__)
        parser.add_argument(
            "command", nargs="?", choices=["run", "fetch", "calibrate"], default="run"
        )
        parser.add_argument("--catalogue", type=Path, default=Path("config/feeds.json"))
        parser.add_argument("--source", action="append", default=[])
        parser.add_argument("--force", action="store_true")
        asyncio.run(runtime(parser.parse_args(), correlation))
    except (
        IngestionFailure,
        ValidationError,
        KeyError,
        ValueError,
        TimeoutError,
        AzureError,
        psycopg.Error,
        httpx.HTTPError,
        aiohttp.ClientError,
        OSError,
    ) as error:
        category = str(error) if isinstance(error, IngestionFailure) else type(error).__name__
        event("ingestion", correlation, outcome="failure", category=category)
        raise SystemExit(1) from None
