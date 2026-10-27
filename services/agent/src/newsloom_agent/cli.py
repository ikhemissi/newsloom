"""Agent operator commands with content-free startup and failure reporting."""

import argparse
import asyncio
from importlib import import_module
from typing import Never

from newsloom_core.diagnostics import configure_logging, event
from pydantic import ValidationError

from newsloom_agent.models import AgentFailure


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise AgentFailure("invalid_arguments")


async def serve() -> None:
    import uvicorn

    from newsloom_agent.runtime import application, environment_config

    async with application(environment_config()) as app:
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="0.0.0.0",
                port=8000,
                workers=1,
                log_config=None,
                access_log=False,
                proxy_headers=False,
                server_header=False,
                timeout_keep_alive=5,
                timeout_graceful_shutdown=120,
                h11_max_incomplete_event_size=16 * 1024,
            )
        )
        await server.serve()


def main() -> None:
    configure_logging()
    try:
        parser = Parser(description=__doc__)
        parser.add_argument(
            "command", choices=["check-runtime", "serve", "verify-delegation", "verify-streaming"]
        )
        args = parser.parse_args()
        if args.command == "serve":
            asyncio.run(serve())
            return
        if args.command in ("verify-delegation", "verify-streaming"):
            from newsloom_agent.client import verify_delegation

            streaming = args.command == "verify-streaming"
            counts = asyncio.run(verify_delegation(streaming=streaming))
            event(
                "agent_streaming_acceptance" if streaming else "agent_delegation_acceptance",
                "",
                outcome="success",
                counts=counts,
            )
            return
        modules = (
            "newsloom_agent.runtime",
            "agent_framework.a2a",
            "agent_framework_openai",
            "a2a.client",
            "a2a.server.routes",
            "azure.identity.aio",
            "mcp.client.streamable_http",
            "newsloom_agent.telemetry",
        )
        for module in modules:
            import_module(module)
        event("agent_runtime_check", "", outcome="success", counts={"modules": len(modules)})
    except (
        AgentFailure,
        ImportError,
        OSError,
        ValueError,
        KeyError,
        ValidationError,
        TimeoutError,
    ) as error:
        category = str(error) if isinstance(error, AgentFailure) else type(error).__name__
        event("agent_runtime_check", "", outcome="failure", category=category)
        raise SystemExit(1) from None
