"""Bounded ingestion values and content-free failure categories."""

from dataclasses import dataclass
from typing import Literal

from newsloom_core.entries import Candidate as Candidate
from newsloom_core.entries import Entry as Entry


class IngestionFailure(Exception):
    """Only a predetermined category, never a publisher response."""


@dataclass(frozen=True)
class Limits:
    concurrency: int = 4
    body_bytes: int = 8 * 1024 * 1024
    robots_bytes: int = 256 * 1024
    connect_seconds: float = 5
    request_seconds: float = 30
    feed_seconds: float = 60
    job_seconds: float = 900
    redirects: int = 3
    retries: int = 2
    entries: int = 1000
    text_bytes: int = 32 * 1024

    def __post_init__(self) -> None:
        if any(value <= 0 for value in vars(self).values()):
            raise IngestionFailure("invalid_limits")


DEFAULT_LIMITS = Limits()

SOURCE_COUNTERS = (
    "found",
    "filtered",
    "duplicates",
    "staged",
    "feeds_ok",
    "malformed_rejected",
    "accepted",
    "security_rejected",
    "deferred",
    "feed_item",
    "article_metadata",
    "article_body",
    "recovery_attempted",
    "recovery_failed",
    "recovery_deferred",
)


def source_counts() -> dict[str, int]:
    return dict.fromkeys(SOURCE_COUNTERS, 0)


@dataclass(frozen=True)
class ParsedFeed:
    candidates: tuple[Candidate, ...]
    malformed: tuple[str, ...]
    found: int


@dataclass(frozen=True)
class Decision:
    disposition: Literal["accepted", "rejected", "deferred"]
    reason: str
    score: float | None = None
    threshold: float | None = None


@dataclass(frozen=True)
class Document:
    status: int
    url: str
    body: bytes
    headers: dict[str, str]
