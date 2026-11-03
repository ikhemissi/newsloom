"""Scheduled workload entry point; no user credentials or article output."""

import argparse
import asyncio
import os
import time
from contextlib import aclosing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Never
from uuid import uuid4

import httpx
import psycopg
from azure.core.exceptions import AzureError
from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.briefing import Briefing, cutoff_at
from newsloom_core.diagnostics import configure_logging, event
from newsloom_core.model_transport import ModelClient, ModelFailure, TransportLimits
from pydantic import ValidationError

from newsloom_briefing.generation import PROMPT_REVISION, Failure, FoundryGenerator, synthesize
from newsloom_briefing.repository import Repository

MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise Failure("briefing_invalid_arguments")


async def execute(
    repository: Repository, generator: FoundryGenerator, model: str, version: str
) -> bool:
    cutoff = generator.cutoff
    if not await repository.claim(cutoff, PROMPT_REVISION, model, version):
        return False
    deadline = time.monotonic() + 3540
    try:
        async with asyncio.timeout_at(deadline):
            evidence = []
            size = 0
            async with aclosing(
                repository.snapshot(cutoff - timedelta(days=7), cutoff)
            ) as snapshot:
                async for item in snapshot:
                    size += len(item.model_dump_json().encode())
                    if size > MAX_SNAPSHOT_BYTES:
                        raise Failure("briefing_snapshot_limit")
                    evidence.append(item)
            await repository.evidence(cutoff, evidence)
            artifact = await synthesize(generator, evidence, cutoff, deadline)
            await repository.publish(artifact)
    except (
        Failure,
        ModelFailure,
        ValidationError,
        AzureError,
        httpx.HTTPError,
        psycopg.Error,
        TimeoutError,
        asyncio.CancelledError,
    ) as error:
        category = (
            str(error) if isinstance(error, Failure | ModelFailure) else "briefing_execution_failed"
        )
        await repository.fail(cutoff, category)
        raise
    return True


async def inspect(
    connection: psycopg.AsyncConnection[tuple[object, ...]], correlation: str
) -> None:
    async with connection.transaction():
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        row = await (
            await connection.execute("SELECT payload FROM public.briefing_current WHERE singleton")
        ).fetchone()
        if row is None:
            raise Failure("briefing_not_published")
        artifact = Briefing.model_validate(row[0])
        usage = await (
            await connection.execute(
                "SELECT count(*),coalesce(sum(input_tokens),0),coalesce(sum(output_tokens),0),"
                "coalesce(sum(estimated_cost_usd),0),"
                "count(*) FILTER(WHERE status<>'completed' OR input_tokens IS NULL "
                "OR output_tokens IS NULL) FROM public.briefing_calls WHERE cutoff=%s",
                (artifact.window_end,),
            )
        ).fetchone()
        assert usage is not None
        words = sum(len(p.text.split()) for s in artifact.sections for p in s.paragraphs)
        event(
            "briefing_inspection",
            correlation,
            outcome="validated",
            counts={
                "cutoff": artifact.window_end.isoformat(),
                "evidence_count": artifact.evidence_count,
                "summary_words": words,
                "tldr_words": len(artifact.tldr.text.split()) if artifact.tldr else 0,
                "citations": len(artifact.citations),
                "coverage": artifact.coverage,
                "physical_call_intents": int(str(usage[0])),
                "observed_input_tokens": int(str(usage[1])),
                "observed_output_tokens": int(str(usage[2])),
                "estimated_observed_model_cost_usd": float(str(usage[3])),
                "unknown_usage_operations": int(str(usage[4])),
                "semantic_quality_verified": False,
            },
        )


async def verify_access(
    connection: psycopg.AsyncConnection[tuple[object, ...]], correlation: str
) -> None:
    counts: dict[str, int] = {}
    for table in ("briefing_runs", "briefing_calls", "briefing_current"):
        row = await (
            await connection.execute(
                psycopg.sql.SQL("SELECT count(*) FROM public.{}").format(
                    psycopg.sql.Identifier(table)
                )
            )
        ).fetchone()
        if row is None or not isinstance(row[0], int):
            raise Failure("briefing_access_readback_failed")
        counts[table] = row[0]
    await connection.execute("SELECT id,title,summary FROM public.news LIMIT 0")
    try:
        async with connection.transaction():
            await connection.execute("UPDATE public.news SET title=title WHERE false")
    except psycopg.errors.InsufficientPrivilege:
        counts["news_write_denied"] = 1
    else:
        raise Failure("briefing_news_write_granted")
    event("briefing_access", correlation, outcome="verified", counts=counts)


async def runtime(correlation: str, command: str = "run") -> None:
    env = os.environ
    input_price = Decimal(env["BRIEFING_INPUT_PRICE_PER_MILLION"])
    output_price = Decimal(env["BRIEFING_OUTPUT_PRICE_PER_MILLION"])
    if not all(p.is_finite() and p >= 0 for p in (input_price, output_price)):
        raise Failure("briefing_invalid_price")
    if not env["BRIEFING_PRICE_BASIS"].strip():
        raise Failure("briefing_price_basis_required")
    cutoff = cutoff_at(datetime.now(UTC))
    async with (
        ManagedIdentityCredential(client_id=env["AZURE_CLIENT_ID"]) as credential,
        httpx.AsyncClient(follow_redirects=False, trust_env=False) as http,
    ):
        token = await credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        async with await psycopg.AsyncConnection.connect(
            host=env["POSTGRES_HOST"],
            dbname=env["POSTGRES_DATABASE"],
            user="newsloom_briefing",
            password=token.token,
            sslmode="verify-full",
            sslrootcert="/etc/ssl/certs/ca-certificates.crt",
            connect_timeout=15,
            options="-c statement_timeout=30000 -c idle_in_transaction_session_timeout=30000",
            application_name="newsloom-briefing",
            autocommit=True,
        ) as connection:
            if command == "verify-access":
                await verify_access(connection, correlation)
                return
            if command == "inspect":
                await inspect(connection, correlation)
                return
            repository = Repository(connection)
            transport = ModelClient(
                http,
                credential,
                env["MODEL_ENDPOINT"],
                TransportLimits(request_seconds=90, transport_attempts=1),
            )
            generator = FoundryGenerator(
                transport,
                repository,
                cutoff,
                env["BRIEFING_DEPLOYMENT"],
                input_price,
                output_price,
                env["BRIEFING_PRICE_BASIS"],
            )
            published = await execute(
                repository, generator, env["BRIEFING_MODEL"], env["BRIEFING_MODEL_VERSION"]
            )
            event(
                "briefing_run",
                correlation,
                outcome="published" if published else "already_claimed",
                counts={"generation_calls": generator.ordinal},
            )


def main() -> None:
    configure_logging()
    correlation = uuid4().hex
    try:
        parser = Parser(description=__doc__)
        parser.add_argument(
            "command", choices=["run", "inspect", "verify-access"], nargs="?", default="run"
        )
        arguments = parser.parse_args()
        asyncio.run(runtime(correlation, arguments.command))
    except (
        Failure,
        ModelFailure,
        ValidationError,
        AzureError,
        httpx.HTTPError,
        psycopg.Error,
        KeyError,
        ValueError,
        ArithmeticError,
        TimeoutError,
        OSError,
        ImportError,
    ) as error:
        category = str(error) if isinstance(error, Failure | ModelFailure) else "briefing_failed"
        event("briefing_run", correlation, outcome="failure", category=category)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
