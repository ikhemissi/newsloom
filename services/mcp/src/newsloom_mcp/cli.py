"""Run the authenticated service; no environment or user data appears in failures."""

import argparse
import asyncio
from typing import Never
from uuid import UUID

import httpx
import psycopg
import uvicorn
from azure.core.exceptions import AzureError
from newsloom_core.diagnostics import configure_logging, event
from newsloom_core.model_transport import ModelFailure
from pydantic import ValidationError

from newsloom_mcp.models import McpFailure
from newsloom_mcp.runtime import Config, application, resources


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise McpFailure("invalid_arguments")


async def runtime(args: argparse.Namespace) -> None:
    if args.command != "verify-access" and (
        args.generation_deployment or args.screening_deployment
    ):
        raise McpFailure("verification_options_require_verifier")
    if args.command == "verify-access":
        from newsloom_mcp.verification import verify_access

        if args.generation_deployment is None or args.screening_deployment is None:
            raise McpFailure("verification_deployments_required")
        counts = await verify_access(
            Config.environment(),
            args.generation_deployment,
            args.screening_deployment,
            args.evaluation_run_id,
        )
        event("mcp_access_verification", "", outcome="success", counts=counts)
        return
    if args.command == "evaluate":
        import time

        from newsloom_mcp.evaluation import evaluate

        if args.evaluation_run_id is None:
            raise McpFailure("evaluation_run_id_required")
        run_id = UUID(args.evaluation_run_id).hex
        async with resources(Config.environment(), instrument=False) as (services, _):
            report = await evaluate(
                services.repositories, services.embeddings, run_id, time.monotonic() + 900
            )
        if report["passed"] != 1:
            raise McpFailure("retrieval_evaluation_failed")
        return
    async with application(Config.environment()) as app:
        await uvicorn.Server(
            uvicorn.Config(
                app,
                host="0.0.0.0",
                port=8000,
                access_log=False,
                log_config=None,
                proxy_headers=False,
            )
        ).serve()


def main() -> None:
    configure_logging()
    try:
        parser = Parser(description=__doc__)
        parser.add_argument(
            "command", nargs="?", choices=["serve", "evaluate", "verify-access"], default="serve"
        )
        parser.add_argument("--evaluation-run-id")
        parser.add_argument("--generation-deployment")
        parser.add_argument("--screening-deployment")
        asyncio.run(runtime(parser.parse_args()))
    except (
        McpFailure,
        ModelFailure,
        ValidationError,
        KeyError,
        ValueError,
        TimeoutError,
        AzureError,
        psycopg.Error,
        httpx.HTTPError,
        OSError,
        ImportError,
    ) as error:
        category = (
            str(error) if isinstance(error, (McpFailure, ModelFailure)) else type(error).__name__
        )
        event("mcp_service", "", outcome="failure", category=category)
        raise SystemExit(1) from None
