import argparse
import asyncio
import json
from pathlib import Path
from typing import NoReturn

from agent_evaluation.inputs import FIXTURE_SHA256, load_pilot, source_digest
from agent_evaluation.policy import EvaluationFailure


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.exit(2, '{"outcome":"failure","category":"invalid_evaluation_arguments"}\n')


def main() -> int:
    parser = Parser(description="Synthetic-only evaluation pilot.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "validate", help="Validate frozen fixtures and provenance; no Azure access."
    )
    execute = commands.add_parser("score", help="Run only an explicitly approved private manifest.")
    execute.add_argument("--manifest", type=Path, required=True)
    execute.add_argument("--approved-sha256", required=True)
    execute.add_argument("--output", type=Path, required=True)
    publication = commands.add_parser(
        "publish",
        help="Publish existing scores; an existing publication record permits reads only.",
    )
    publication.add_argument("--directory", type=Path, required=True)
    publication.add_argument("--approved-sha256", required=True)
    publication.add_argument(
        "--continue-unsubmitted",
        action="store_true",
        help="Allow never-attempted metadata operations after owned read-only reconciliation.",
    )
    retention = commands.add_parser(
        "cleanup", help="Verify exact owned historical assets; deletion requires --delete."
    )
    retention.add_argument("--directory", type=Path, required=True)
    retention.add_argument("--manifest", type=Path, required=True)
    retention.add_argument("--approved-sha256", required=True)
    retention.add_argument("--delete", action="store_true")
    args = parser.parse_args()
    if args.command == "validate":
        try:
            load_pilot()
            digest = source_digest()
        except EvaluationFailure, OSError, ValueError:
            print(json.dumps({"outcome": "failure", "category": "evaluation_validation_error"}))
            return 1
        print(
            json.dumps(
                {
                    "outcome": "validated",
                    "cases": 2,
                    "fixture_sha256": FIXTURE_SHA256,
                    "source_sha256": digest,
                    "model_calls": 0,
                },
                sort_keys=True,
            )
        )
        return 0

    import httpx2
    from azure.core.exceptions import AzureError
    from openai import OpenAIError
    from pydantic import ValidationError

    from agent_evaluation.runner import score

    try:
        if args.command == "cleanup":
            from agent_evaluation.cleanup import cleanup

            receipt = asyncio.run(
                cleanup(
                    args.directory,
                    args.manifest,
                    args.approved_sha256,
                    delete=args.delete,
                )
            )
            print(
                json.dumps(
                    {key: receipt[key] for key in ("outcome", "assets", "model_calls")},
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "publish":
            from agent_evaluation.publication import publish

            receipt = asyncio.run(
                publish(
                    args.directory,
                    args.approved_sha256,
                    continue_unsubmitted=args.continue_unsubmitted,
                )
            )
            print(
                json.dumps(
                    {
                        "outcome": receipt["outcome"],
                        "cases": receipt["cases"],
                        "ui_verified": False,
                        "model_calls": 0,
                    },
                    sort_keys=True,
                )
            )
            return 0
        result = asyncio.run(score(args.manifest, args.approved_sha256, args.output))
    except EvaluationFailure as error:
        print(json.dumps({"outcome": "failure", "category": str(error)}))
        return 1
    except (
        AzureError,
        httpx2.HTTPError,
        OpenAIError,
        ValidationError,
        OSError,
        ValueError,
        RuntimeError,
        TimeoutError,
    ):
        print(json.dumps({"outcome": "failure", "category": "evaluation_execution_error"}))
        return 1
    except KeyboardInterrupt, asyncio.CancelledError:
        print(json.dumps({"outcome": "failure", "category": "evaluation_cancelled"}))
        return 130
    print(
        json.dumps(
            {
                "outcome": "scored",
                "cases": len(result.cases),
                "source_sha256": result.source_sha256,
                "budget": result.budget.model_dump(mode="json"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
