"""Strict generation values, bounded processing and content-free failures."""

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from newsloom_core.categories import Category
from newsloom_core.entries import Entry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EnrichmentFailure(Exception):
    def __init__(self, category: str, *, retry_after: float = 0) -> None:
        if (
            not re.fullmatch(r"[a-z0-9_]+", category)
            or not math.isfinite(retry_after)
            or not 0 <= retry_after <= 2147483647
        ):
            raise ValueError("invalid_enrichment_failure")
        super().__init__(category)
        self.retry_after = retry_after


class ServiceSafetyBlock(EnrichmentFailure):
    """Only a validated generation-service jailbreak-filter response."""

    def __init__(self) -> None:
        super().__init__("generation_jailbreak_filtered")


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


Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class Vector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    values: Annotated[tuple[Number, ...], Field(min_length=1536, max_length=1536)]

    @model_validator(mode="after")
    def nonzero(self) -> Vector:
        if not any(value != 0 for value in self.values):
            raise ValueError("zero_embedding")
        return self


@dataclass(frozen=True)
class Claim:
    id: UUID
    token: UUID
    entry: Entry
    attempts: int
    lease_until: datetime
