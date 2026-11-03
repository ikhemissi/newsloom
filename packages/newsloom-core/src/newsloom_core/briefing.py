"""Shared validated publication contract; never contains prompts or raw evidence."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Count = Annotated[int, Field(strict=True, ge=0)]
Reference = Annotated[int, Field(strict=True, gt=0)]
Text = Annotated[str, Field(strict=True, min_length=1, max_length=16000)]


def cutoff_at(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("briefing_timezone_required")
    now = now.astimezone(UTC)
    cutoff = now.replace(hour=5, minute=0, second=0, microsecond=0)
    return cutoff if now >= cutoff else cutoff - timedelta(days=1)


class BriefingContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Paragraph(BriefingContract):
    text: Text = Field(repr=False)
    references: Annotated[tuple[Reference, ...], Field(min_length=1, max_length=100)]

    @field_validator("references")
    @classmethod
    def distinct(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(values)) != len(values):
            raise ValueError("duplicate_briefing_reference")
        return values


class Section(BriefingContract):
    heading: Annotated[str, Field(strict=True, min_length=1, max_length=160)]
    paragraphs: Annotated[tuple[Paragraph, ...], Field(min_length=1, max_length=30)]


class Citation(BriefingContract):
    number: Reference
    url: Annotated[str, Field(strict=True, max_length=4096)] = Field(repr=False)
    title: Annotated[str, Field(strict=True, min_length=1, max_length=1000)] = Field(repr=False)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.port not in (None, 443)
            or any(ord(char) <= 32 for char in value)
        ):
            raise ValueError("invalid_briefing_url")
        return value


class Briefing(BriefingContract):
    version: UUID
    window_start: datetime
    window_end: datetime
    generated_at: datetime
    coverage: Literal["full", "limited", "empty", "no_material_changes"]
    editorial_policy: Literal["architect-v1"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    evidence_count: Count
    tldr: Paragraph | None = Field(repr=False)
    sections: Annotated[tuple[Section, ...], Field(max_length=16)] = Field(repr=False)
    citations: Annotated[tuple[Citation, ...], Field(max_length=100)] = Field(repr=False)

    @field_validator("window_start", "window_end", "generated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("briefing_timezone_required")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            self.window_end != cutoff_at(self.window_end)
            or self.window_start != self.window_end - timedelta(days=7)
            or self.generated_at < self.window_end
        ):
            raise ValueError("invalid_briefing_window")
        if self.coverage == "empty":
            if self.evidence_count or self.tldr is not None or self.sections or self.citations:
                raise ValueError("invalid_empty_briefing")
            return self
        if self.coverage == "no_material_changes":
            if (
                self.editorial_policy != "architect-v1"
                or not self.evidence_count
                or self.tldr is not None
                or self.sections
                or self.citations
            ):
                raise ValueError("invalid_no_material_briefing")
            return self
        if not self.evidence_count or self.tldr is None or not self.sections or not self.citations:
            raise ValueError("incomplete_briefing")
        if "\n" in self.tldr.text or not 1 <= len(self.tldr.text.split()) <= 120:
            raise ValueError("invalid_briefing_tldr")
        if [c.number for c in self.citations] != list(range(1, len(self.citations) + 1)):
            raise ValueError("invalid_briefing_citations")
        references = {r for s in self.sections for p in s.paragraphs for r in p.references}
        if references != {c.number for c in self.citations} or not set(
            self.tldr.references
        ).issubset(references):
            raise ValueError("invalid_briefing_references")
        words = sum(len(p.text.split()) for s in self.sections for p in s.paragraphs)
        if self.editorial_policy == "architect-v1":
            invalid_length = not words or words + len(self.tldr.text.split()) > 1000
        else:
            invalid_length = not 1 <= words <= 1100 or (self.coverage == "full" and words < 900)
        if invalid_length:
            raise ValueError("invalid_briefing_length")
        return self


class Refresh(BriefingContract):
    expected_cutoff: datetime
    state: Literal["pending", "running", "ready", "failed"]
    stale: bool = Field(strict=True)

    @field_validator("expected_cutoff")
    @classmethod
    def cutoff(cls, value: datetime) -> datetime:
        if value != cutoff_at(value):
            raise ValueError("invalid_briefing_cutoff")
        return value.astimezone(UTC)


class BriefingRead(BriefingContract):
    briefing: Briefing | None
    refresh: Refresh

    @model_validator(mode="after")
    def coherent(self) -> Self:
        end = self.briefing.window_end if self.briefing else None
        if end is not None and end > self.refresh.expected_cutoff:
            raise ValueError("future_briefing_version")
        if self.refresh.stale != (end is None or end < self.refresh.expected_cutoff):
            raise ValueError("invalid_briefing_staleness")
        if self.refresh.state == "ready" and self.refresh.stale:
            raise ValueError("missing_ready_briefing")
        return self
