import argparse
import asyncio
import json
import os
import signal
from typing import Never

from azure.identity.aio import ManagedIdentityCredential
from newsloom_core.diagnostics import configure_logging
from newsloom_core.phase1_contracts import AcceptanceFailure, TestConfig
from newsloom_platform.phase1_database import cleanup

from phase1_acceptance.run import ERRORS, execute, safe_category
from phase1_acceptance.telemetry import publish
from phase1_acceptance.worker import work


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise AcceptanceFailure("invalid_acceptance_arguments")


async def runtime(args: argparse.Namespace) -> None:
    config = TestConfig.from_encoded(os.environ["PHASE1_CONFIG_BASE64"], args.run_id, args.scenario)
    task = asyncio.current_task()
    if task is None:
        raise AcceptanceFailure("acceptance_runtime_task_missing")
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    async with ManagedIdentityCredential(client_id=str(config.client_id)) as credential:
        if args.command == "worker":
            await work(config, credential, pause=args.pause_after_claim)
        elif args.command == "cleanup":
            await cleanup(config, credential)
            print(
                json.dumps(
                    {
                        "event": "phase1_cleanup",
                        "run_id": config.run_id,
                        "absent": 1,
                    }
                ),
                flush=True,
            )
        else:
            report = await execute(config, credential)
            await asyncio.to_thread(
                publish,
                report,
                os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
                str(config.client_id),
            )
            print(report.model_dump_json(), flush=True)
            if report.outcome != "success":
                raise SystemExit(1)


def main() -> None:
    configure_logging()
    try:
        parser = Parser()
        parser.add_argument("command", choices=["run", "cleanup", "worker"])
        parser.add_argument("--run-id", required=True)
        parser.add_argument(
            "--scenario",
            choices=[
                "acceptance",
                "failure-after-ingestion",
                "cancel-after-claim",
            ],
            default="acceptance",
        )
        parser.add_argument("--pause-after-claim", action="store_true")
        args = parser.parse_args()
        if args.pause_after_claim and args.command != "worker":
            raise AcceptanceFailure("pause_requires_acceptance_child")
        asyncio.run(runtime(args))
    except (*ERRORS, KeyError, ImportError) as error:
        print(
            json.dumps(
                {
                    "event": "phase1_error",
                    "category": safe_category(error),
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
    except asyncio.CancelledError:
        print(json.dumps({"event": "phase1_error", "category": "acceptance_cancelled"}), flush=True)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
