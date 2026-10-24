"""Real bounded enrichment; evaluation is explicit and never publishes fixtures."""

import argparse
import asyncio
import os
import time
from typing import Never
from uuid import UUID, uuid4

import httpx
import psycopg
from azure.core.exceptions import AzureError
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.categories import load_categories
from newsloom_core.diagnostics import configure_logging, event
from pydantic import ValidationError

from newsloom_enrichment.evaluation import evaluate
from newsloom_enrichment.job import run
from newsloom_enrichment.models import DEFAULT_LIMITS, EnrichmentFailure
from newsloom_enrichment.providers import FoundryEmbedding, FoundryLlm, ModelClient, revisions
from newsloom_enrichment.repository import ModelMetadata, Repository
from newsloom_enrichment.telemetry import Telemetry


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise EnrichmentFailure("invalid_arguments")


async def runtime(args: argparse.Namespace, correlation: str) -> None:
    if isinstance(args.limit, bool) or not 1 <= args.limit <= 25:
        raise EnrichmentFailure("invalid_item_limit")
    load_categories()
    env = os.environ
    for name in (
        "AZURE_CLIENT_ID",
        "MODEL_ENDPOINT",
        "ENRICHMENT_DEPLOYMENT",
        "EMBEDDINGS_DEPLOYMENT",
        "ENRICHMENT_MODEL",
        "ENRICHMENT_VERSION",
        "EMBEDDINGS_MODEL",
        "EMBEDDINGS_VERSION",
    ):
        if not env.get(name):
            raise EnrichmentFailure("enrichment_configuration_required")
    async with (
        ManagedIdentityCredential(client_id=env["AZURE_CLIENT_ID"]) as credential,
        httpx.AsyncClient() as client,
    ):
        transport = ModelClient(client, credential, env["MODEL_ENDPOINT"])
        llm = FoundryLlm(transport, env["ENRICHMENT_DEPLOYMENT"])
        embedding = FoundryEmbedding(transport, env["EMBEDDINGS_DEPLOYMENT"])
        started = time.monotonic()
        if args.command == "evaluate":
            report = await evaluate(
                llm, embedding, correlation, started + DEFAULT_LIMITS.job_seconds - 20
            )
            usage = transport.observations
            event(
                "enrichment_evaluation_usage",
                correlation,
                outcome="observed",
                counts={
                    "generation_calls": usage.generation_calls,
                    "embedding_calls": usage.embedding_calls,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "generation_seconds": usage.generation_seconds,
                    "embedding_seconds": usage.embedding_seconds,
                    "generation_model": env["ENRICHMENT_MODEL"],
                    "generation_version": env["ENRICHMENT_VERSION"],
                    "embedding_model": env["EMBEDDINGS_MODEL"],
                    "embedding_version": env["EMBEDDINGS_VERSION"],
                },
            )
            if report["passed"] != 1:
                raise EnrichmentFailure("enrichment_evaluation_failed")
            return
        prompt_revision, taxonomy_revision = revisions()
        metadata = ModelMetadata(
            env["ENRICHMENT_MODEL"],
            env["ENRICHMENT_VERSION"],
            env["EMBEDDINGS_MODEL"],
            env["EMBEDDINGS_VERSION"],
            prompt_revision,
            taxonomy_revision,
        )
        token = await credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        async with await psycopg.AsyncConnection.connect(
            host=env["POSTGRES_HOST"],
            dbname=env["POSTGRES_DATABASE"],
            user="newsloom_enrichment",
            password=token.token,
            sslmode="verify-full",
            sslrootcert="/etc/ssl/certs/ca-certificates.crt",
            connect_timeout=15,
            options="-c statement_timeout=15000 -c idle_in_transaction_session_timeout=30000",
            application_name="newsloom-enrichment",
            autocommit=True,
        ) as connection:
            repository = Repository(connection)
            if args.command == "verify-access":
                checks = await repository.verify_access()
                event(
                    "enrichment_access", correlation, outcome="success", counts={"checks": checks}
                )
                return
            telemetry = Telemetry(
                env["APPLICATIONINSIGHTS_CONNECTION_STRING"], env["AZURE_CLIENT_ID"]
            )
            try:
                counts = await run(
                    repository, llm, embedding, metadata, correlation, limit=args.limit
                )
                telemetry.record(
                    correlation, counts, time.monotonic() - started, transport.observations
                )
            finally:
                await asyncio.to_thread(telemetry.close)


def main() -> None:
    configure_logging()
    correlation = uuid4().hex
    try:
        correlation = UUID(os.environ.get("PLATFORM_PROBE_RUN_ID", correlation)).hex
        parser = Parser(description=__doc__)
        parser.add_argument(
            "command", nargs="?", choices=["run", "evaluate", "verify-access"], default="run"
        )
        parser.add_argument("--limit", type=int, default=25)
        asyncio.run(runtime(parser.parse_args(), correlation))
    except (
        EnrichmentFailure,
        ImportError,
        ValidationError,
        KeyError,
        ValueError,
        TimeoutError,
        AzureError,
        psycopg.Error,
        httpx.HTTPError,
        OSError,
    ) as error:
        category = str(error) if isinstance(error, EnrichmentFailure) else type(error).__name__
        event("enrichment", correlation, outcome="failure", category=category)
        raise SystemExit(1) from None
