"""Strict generation values, bounded processing and content-free failures."""

import math
import re
from dataclasses import dataclass
from datetime import datetime
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


class Enrichment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    summary_sentences: Annotated[tuple[str, ...], Field(min_length=2, max_length=3)]
    category: Category
    tags: Annotated[tuple[str, ...], Field(min_length=3, max_length=5)]

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


@dataclass(frozen=True)
class Claim:
    id: UUID
    token: UUID
    entry: Entry
    attempts: int
    lease_until: datetime
