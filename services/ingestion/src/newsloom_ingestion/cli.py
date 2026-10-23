"""Run ingestion explicitly; production never substitutes an accepting scanner."""

import argparse
import asyncio
import json
import math
import os
import time
from pathlib import Path
from typing import Never
from uuid import UUID, uuid4

import aiohttp
import httpx
import psycopg
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import AzureError
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from newsloom_core.feeds import load_feed_catalogue
from pydantic import ValidationError

from newsloom_ingestion.evaluation import (
    ReviewCase,
    compare,
    load_review,
    parse_review,
    private_path,
    review_entries,
)
from newsloom_ingestion.job import process_items, run, select_sources
from newsloom_ingestion.models import IngestionFailure, Limits, source_counts
from newsloom_ingestion.repository import Repository
from newsloom_ingestion.retrieval import PublicClient
from newsloom_ingestion.scanner import DecisionScanner, calibrate, calibration_id, load_cases
from newsloom_ingestion.telemetry import Telemetry, configure_logging, event


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise IngestionFailure("invalid_arguments")


async def runtime(args: argparse.Namespace, correlation: str) -> None:
    if args.command == "evaluate":
        await evaluate(args)
        return
    if args.command == "evaluate-job":
        await evaluate_job(args, correlation)
        return
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
    threshold = float(threshold_text) if threshold_text and args.command == "run" else None
    if args.command == "run" and (threshold is None or not math.isfinite(threshold)):
        raise IngestionFailure("scanner_threshold_required")
    if args.command == "run" and threshold is not None:
        expected = calibration_id(
            env["MODEL_ENDPOINT"],
            env["SCREENING_DEPLOYMENT"],
            env["SCREENING_MODEL"],
            env["SCREENING_VERSION"],
            threshold,
        )
        if env.get("SCANNER_CALIBRATION_ID") != expected:
            raise IngestionFailure("scanner_calibration_mismatch")
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
                    "calibration_id": calibration_id(
                        env["MODEL_ENDPOINT"],
                        env["SCREENING_DEPLOYMENT"],
                        env["SCREENING_MODEL"],
                        env["SCREENING_VERSION"],
                        float(result["threshold"]),
                    ),
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


async def evaluate(args: argparse.Namespace) -> None:
    if args.review_manifest is None or args.report is None or args.baseline_threshold is None:
        raise IngestionFailure("evaluation_arguments_required")
    report_path = private_path(args.report)
    manifest = private_path(args.review_manifest)
    if report_path == manifest or report_path.exists():
        raise IngestionFailure("evaluation_report_must_be_new")
    cases = load_review(manifest)
    async with AzureCliCredential(process_timeout=15) as credential:
        report = await comparison(args, credential, cases)
    with report_path.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    report_path.chmod(0o600)
    if not report["passed"]:
        raise IngestionFailure("screening_evaluation_failed")


async def comparison(
    args: argparse.Namespace,
    credential: AsyncTokenCredential,
    cases: tuple[ReviewCase, ...],
) -> dict[str, object]:
    report: dict[str, object]
    started = time.monotonic()
    env = os.environ
    try:
        if (
            args.baseline_threshold is None
            or not math.isfinite(args.baseline_threshold)
            or not 0 <= args.baseline_threshold <= 1
        ):
            raise IngestionFailure("invalid_baseline_threshold")
        sources = load_feed_catalogue(args.catalogue)
        async with httpx.AsyncClient() as client:
            scanner = DecisionScanner(
                client, credential, env["MODEL_ENDPOINT"], env["SCREENING_DEPLOYMENT"], None
            )
            deadline = started + Limits().job_seconds - 20
            # Establish inference access before retrieving private review content.
            await scanner.score(load_cases()[0].entry.model_dump_json(), deadline)
            review = await review_entries(cases, sources, deadline)
            report = await compare(
                scanner,
                review,
                args.baseline_threshold,
                env["SCREENING_MODEL"],
                env["SCREENING_VERSION"],
                deadline,
            )
    except (IngestionFailure, ValidationError, AzureError, httpx.HTTPError, TimeoutError) as error:
        report = {
            "passed": False,
            "error": str(error) if isinstance(error, IngestionFailure) else type(error).__name__,
        }
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return report


async def evaluate_job(args: argparse.Namespace, correlation: str) -> None:
    if not args.review_manifest_json or len(args.review_manifest_json.encode()) > 64 * 1024:
        raise IngestionFailure("evaluation_identity_manifest_required")
    cases = parse_review(args.review_manifest_json.encode())
    if any(case.entry is not None for case in cases):
        raise IngestionFailure("job_evaluation_requires_identities_only")
    async with ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"]) as credential:
        report = await comparison(args, credential, cases)
    observations = report.pop("observations", [])
    if not isinstance(observations, list):
        raise IngestionFailure("invalid_evaluation_report")
    for observation in observations:
        print(
            json.dumps(
                {
                    "event": "screening_comparison_case",
                    "correlation_id": correlation,
                    "case": observation,
                },
                allow_nan=False,
            ),
            flush=True,
        )
    print(
        json.dumps(
            {
                "event": "screening_comparison_summary",
                "correlation_id": correlation,
                "report": report,
            },
            allow_nan=False,
        ),
        flush=True,
    )
    if not report["passed"]:
        raise IngestionFailure("screening_evaluation_failed")


def main() -> None:
    configure_logging()
    correlation = uuid4().hex
    try:
        correlation = UUID(os.environ.get("PLATFORM_PROBE_RUN_ID", correlation)).hex
        parser = Parser(description=__doc__)
        parser.add_argument(
            "command",
            nargs="?",
            choices=["run", "fetch", "calibrate", "evaluate", "evaluate-job"],
            default="run",
        )
        parser.add_argument("--catalogue", type=Path, default=Path("config/feeds.json"))
        parser.add_argument("--source", action="append", default=[])
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--review-manifest", type=Path)
        parser.add_argument("--report", type=Path)
        parser.add_argument("--baseline-threshold", type=float)
        parser.add_argument("--review-manifest-json")
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
