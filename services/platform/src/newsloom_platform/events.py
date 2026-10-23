"""Allowlisted diagnostics; dependency messages are never rendered."""

import json
import logging


def event(
    name: str,
    outcome: str,
    correlation_id: str,
    *,
    checks: int = 0,
    category: str = "",
    workload: str = "",
    counts: dict[str, int] | None = None,
    source: str = "",
    source_run: str = "",
) -> None:
    print(
        json.dumps(
            {
                "event": name,
                "outcome": outcome,
                "correlation_id": correlation_id,
                "checks": checks,
                "category": category,
                "workload": workload,
                **({"counts": counts} if counts is not None else {}),
                **({"source": source} if source else {}),
                **({"source_run": source_run} if source_run else {}),
            }
        ),
        flush=True,
    )


class SafeDependencyHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        event("dependency", "warning", "", category=f"level_{record.levelno}")


def configure_logging() -> None:
    logging.basicConfig(level=logging.WARNING, handlers=[SafeDependencyHandler()], force=True)
    for name in ["azure", "httpx", "httpcore"]:
        logging.getLogger(name).setLevel(logging.WARNING)
