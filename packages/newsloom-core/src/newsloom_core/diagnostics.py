"""Content-free structured events and dependency log suppression."""

import json
import logging
from collections.abc import Mapping


def event(
    name: str,
    correlation: str,
    *,
    source: str = "",
    outcome: str = "",
    category: str = "",
    counts: Mapping[str, int | float | str] | None = None,
) -> None:
    print(
        json.dumps(
            {
                "event": name,
                "correlation_id": correlation,
                "source": source,
                "outcome": outcome,
                "category": category,
                "counts": dict(counts or {}),
            }
        ),
        flush=True,
    )


class SafeHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        event("dependency", "", outcome="warning", category=f"level_{record.levelno}")


def configure_logging() -> None:
    logging.basicConfig(level=logging.WARNING, handlers=[SafeHandler()], force=True)
    for name in ("azure", "aiohttp", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
