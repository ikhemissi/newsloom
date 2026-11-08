"""Strict generation values, bounded processing and content-free failures."""

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from newsloom_core.categories import Category
from newsloom_core.entries import Entry
from newsloom_core.model_transport import ModelFailure
from newsloom_core.model_transport import (
    ServiceSafetyBlock as ServiceSafetyBlock,
)
from newsloom_core.model_transport import (
    Vector as Vector,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

EnrichmentFailure = ModelFailure


@dataclass(frozen=True)
class Limits:
    job_seconds: float = 900
    shutdown_seconds: float = 20
    item_seconds: float = 240
    lease_seconds: int = 300
    request_seconds: float = 30
    transport_attempts: int = 3
    queue_attempts: int = 5
    max_items: int = 25
    tokens_per_minute: int = 90_000

    def __post_init__(self) -> None:
        if (
            any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in vars(self).values())
            or self.lease_seconds <= self.item_seconds
            or self.item_seconds + self.shutdown_seconds >= self.job_seconds
            or self.max_items > 25
            or self.queue_attempts > 5
        ):
            raise EnrichmentFailure("invalid_enrichment_limits")


DEFAULT_LIMITS = Limits()


def one_sentence(value: str) -> str:
    value = " ".join(value.split())
    masked = re.sub(r"\b(?:[A-Z]\.){2,}", "INITIALISM", value)
    masked = re.sub(r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|Inc|Ltd|vs)\.", "ABBR", masked)
    boundaries = re.findall(r"""[.!?]+["')\]]*(?=\s+[A-Z"'(]|\Z)""", masked)
    if len(boundaries) != 1 or not re.search(r"""[.!?]["')\]]*\Z""", value):
        raise ValueError("invalid_summary_sentence")
    return value


class ArticleKind(StrEnum):
    ANNOUNCEMENT = "announcement"
    ROUNDUP = "roundup"
    SECURITY = "security"
    RETIREMENT = "retirement"
    REGULATION = "regulation"
    CASE_STUDY = "case_study"
    OPINION = "opinion"
    TUTORIAL = "tutorial"
    OTHER = "other"


class ChangeType(StrEnum):
    LAUNCH = "launch"
    UPDATE = "update"
    AVAILABILITY = "availability"
    PRICING = "pricing"
    DEPRECATION = "deprecation"
    RETIREMENT = "retirement"
    SECURITY = "security"
    POLICY = "policy"
    OTHER = "other"


class Status(StrEnum):
    ANNOUNCED = "announced"
    PREVIEW = "preview"
    GA = "ga"
    UPDATED = "updated"
    DEPRECATED = "deprecated"
    RETIRED = "retired"
    NONE = "none"


DATE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
MAX_STATEMENT_WORDS = 40
MAX_ANNOUNCEMENTS = 30


class Mention(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    product: Annotated[str, Field(min_length=1, max_length=120)]
    vendor: Annotated[str, Field(min_length=1, max_length=80)]


class Announcement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    statement: Annotated[str, Field(min_length=1, max_length=400)]
    change_type: ChangeType
    status: Status
    effective_date: Annotated[str, Field(pattern=DATE)] | None
    deadline: Annotated[str, Field(pattern=DATE)] | None
    products: Annotated[tuple[Mention, ...], Field(min_length=1, max_length=5)]


class Enrichment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        json_schema_serialization_defaults_required=True,
    )

    summary_sentences: Annotated[tuple[str, ...], Field(min_length=2, max_length=3)]
    category: Category
    tags: Annotated[tuple[str, ...], Field(min_length=3, max_length=5)]
    article_kind: ArticleKind = ArticleKind.OTHER
    announcements: Annotated[tuple[Announcement, ...], Field(max_length=MAX_ANNOUNCEMENTS)] = ()

    @field_validator("summary_sentences")
    @classmethod
    def sentences(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(one_sentence(sentence) for sentence in value)
        if len(" ".join(result).split()) > 100:
            raise ValueError("summary_word_limit")
        return result

    @field_validator("tags")
    @classmethod
    def normalized_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        result = tuple(" ".join(tag.split()).casefold() for tag in value)
        if len(set(result)) != len(result) or any(
            not re.fullmatch(r"[a-z0-9][a-z0-9 +#.-]{0,47}", tag) for tag in result
        ):
            raise ValueError("invalid_enrichment_tags")
        return result

    @property
    def summary(self) -> str:
        return " ".join(self.summary_sentences)


def strict_schema() -> dict[str, object]:
    """Structured-output schema: every field required and no `default` keywords."""

    def clean(node: object) -> object:
        if isinstance(node, dict):
            return {key: clean(value) for key, value in node.items() if key != "default"}
        if isinstance(node, list):
            return [clean(value) for value in node]
        return node

    result = clean(Enrichment.model_json_schema(mode="serialization"))
    assert isinstance(result, dict)
    return result


def normalized(value: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z+#.]+", " ", value.casefold()).split())


def grounded(
    announcements: tuple[Announcement, ...], entry: Entry
) -> tuple[tuple[Announcement, ...], dict[str, int]]:
    """Keep only announcements supported by the entry; one bad element never drops the item."""
    haystack = f" {normalized(entry.title + ' ' + entry.text)} "
    published = entry.published_at.date()
    kept: list[Announcement] = []
    dropped = dict.fromkeys(("unnamed_product", "invalid_date", "long_statement"), 0)
    for item in announcements:
        if len(item.statement.split()) > MAX_STATEMENT_WORDS:
            dropped["long_statement"] += 1
            continue
        if any(f" {normalized(m.product)} " not in haystack for m in item.products):
            dropped["unnamed_product"] += 1
            continue
        try:
            dates = [date.fromisoformat(v) for v in (item.effective_date, item.deadline) if v]
        except ValueError:
            dropped["invalid_date"] += 1
            continue
        if any(abs(value - published) > timedelta(days=730) for value in dates):
            dropped["invalid_date"] += 1
            continue
        kept.append(item)
    return tuple(kept), dropped


@dataclass(frozen=True)
class Claim:
    id: UUID
    token: UUID
    entry: Entry
    attempts: int
    lease_until: datetime
