"""Bounded ingestion values and content-free failure categories."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    source: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    guid: Annotated[str, Field(max_length=2048)] | None
    url: Annotated[str, Field(min_length=1, max_length=4096)]
    title: Annotated[str, Field(max_length=2048)]
    text: str
    published_at: datetime
    date_origin: Literal["published", "updated", "retrieved"]
    author: Annotated[str, Field(max_length=2048)]
    categories: tuple[str, ...]

    def entry(self) -> Entry:
        return Entry.model_validate(self.model_dump())


class Entry(Candidate):
    title: Annotated[str, Field(min_length=1, max_length=2048)]


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
