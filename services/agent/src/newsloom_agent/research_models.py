"""Application-owned research contracts, independent of the MCP server package."""

import re
from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from newsloom_core.categories import Category
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from newsloom_agent.models import AgentFailure, NewsMetadata

MAX_QUESTION_BYTES = 8 * 1024
MAX_LANGUAGE_BYTES = 64
MAX_AUDIENCE_BYTES = 256
MAX_FOCUS_BYTES = 1024
MAX_SELECTED_ITEMS = 5
MAX_TOOL_CALLS = 8
MAX_EVIDENCE_ITEMS = 10
MAX_ANSWER_BYTES = 16 * 1024

SourceId = Annotated[str, Field(strict=True, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)]
ResearchLimit = Annotated[int, Field(strict=True, ge=1, le=5)]
EvidenceIds = Annotated[tuple[UUID, ...], Field(max_length=MAX_EVIDENCE_ITEMS)]


def bounded_text(value: str, maximum: int) -> str:
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("invalid_utf8") from None
    if not value.strip() or size > maximum:
        raise ValueError("invalid_text_size")
    return value


def timestamp_input(value: object) -> object:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        raise ValueError("timestamp_required")
    return value


def utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_required")
    return value.astimezone(UTC)


def distinct_ids(value: tuple[UUID, ...]) -> tuple[UUID, ...]:
    if len(set(value)) != len(value):
        raise ValueError("duplicate_item_ids")
    return value


class ResearchContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class PresentationPreferences(ResearchContract):
    language: str | None = Field(default=None, strict=True, repr=False)
    audience: str | None = Field(default=None, strict=True, repr=False)
    detail: Literal["brief", "detailed"] = "brief"
    focus: str | None = Field(default=None, strict=True, repr=False)

    @field_validator("language")
    @classmethod
    def bounded_language(cls, value: str | None) -> str | None:
        return bounded_text(value, MAX_LANGUAGE_BYTES) if value is not None else None

    @field_validator("audience")
    @classmethod
    def bounded_audience(cls, value: str | None) -> str | None:
        return bounded_text(value, MAX_AUDIENCE_BYTES) if value is not None else None

    @field_validator("focus")
    @classmethod
    def bounded_focus(cls, value: str | None) -> str | None:
        return bounded_text(value, MAX_FOCUS_BYTES) if value is not None else None


class ResearchFilters(ResearchContract):
    source: SourceId | None = None
    category: Category | None = None
    tags: Annotated[tuple[str, ...], Field(max_length=10, repr=False)] = ()
    from_: datetime | None = Field(default=None, alias="from", repr=False)
    to: datetime | None = Field(default=None, repr=False)

    @field_validator("from_", "to", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: object) -> object:
        return timestamp_input(value)

    @field_validator("from_", "to")
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        return utc_timestamp(value) if value is not None else None

    @field_validator("tags")
    @classmethod
    def normalized_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        tags = tuple(" ".join(tag.split()).casefold() for tag in value)
        if any(not re.fullmatch(r"[a-z0-9][a-z0-9 +#.-]{0,47}", tag) for tag in tags):
            raise ValueError("invalid_tag_filter")
        return tuple(dict.fromkeys(tags))

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.from_ is not None and self.to is not None and self.from_ >= self.to:
            raise ValueError("invalid_date_interval")
        return self


class ResearchRequest(ResearchContract):
    operation: Literal["research"]
    question: str = Field(strict=True, repr=False)
    item_ids: (
        Annotated[tuple[UUID, ...], Field(min_length=1, max_length=MAX_SELECTED_ITEMS)] | None
    ) = Field(default=None, repr=False)
    filters: ResearchFilters = Field(default_factory=ResearchFilters, repr=False)
    preferences: PresentationPreferences = Field(
        default_factory=PresentationPreferences, repr=False
    )

    @field_validator("question")
    @classmethod
    def bounded_question(cls, value: str) -> str:
        return bounded_text(value, MAX_QUESTION_BYTES)

    @field_validator("item_ids")
    @classmethod
    def distinct_selection(cls, value: tuple[UUID, ...] | None) -> tuple[UUID, ...] | None:
        return distinct_ids(value) if value is not None else None


class RecentArguments(ResearchContract):
    limit: ResearchLimit = 5
    since: datetime | None = Field(default=None, repr=False)

    @field_validator("since", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: object) -> object:
        return timestamp_input(value)

    @field_validator("since")
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        return utc_timestamp(value) if value is not None else None


class DetailArguments(ResearchContract):
    id: UUID = Field(repr=False)


class SourcesArguments(ResearchContract):
    pass


class SearchArguments(ResearchFilters):
    query: str | None = Field(default=None, strict=True, min_length=1, max_length=2048, repr=False)
    limit: ResearchLimit = 5

    @field_validator("query")
    @classmethod
    def meaningful_query(cls, value: str | None) -> str | None:
        return bounded_text(value, 8192).strip() if value is not None else None


class RecentCall(ResearchContract):
    tool: Literal["get_recent_news"]
    arguments: RecentArguments


class DetailCall(ResearchContract):
    tool: Literal["get_news_item"]
    arguments: DetailArguments


class SourcesCall(ResearchContract):
    tool: Literal["list_sources"]
    arguments: SourcesArguments


class SearchCall(ResearchContract):
    tool: Literal["search_news"]
    arguments: SearchArguments


ToolCall = Annotated[
    RecentCall | DetailCall | SourcesCall | SearchCall, Field(discriminator="tool")
]
ToolName = Literal["get_recent_news", "get_news_item", "list_sources", "search_news"]


class ResearchPlan(ResearchContract):
    action: Literal["tools", "synthesize"]
    calls: Annotated[tuple[ToolCall, ...], Field(max_length=MAX_TOOL_CALLS, repr=False)] = ()

    @model_validator(mode="after")
    def action_matches_calls(self) -> Self:
        if (self.action == "tools") != bool(self.calls):
            raise ValueError("invalid_plan_action")
        return self


class PlanningScope(ResearchContract):
    tools: tuple[ToolName, ...]
    detail_ids: EvidenceIds = Field(repr=False)
    can_synthesize: bool
    remaining_tool_calls: Annotated[int, Field(strict=True, ge=0, le=MAX_TOOL_CALLS)]

    def validate_plan(self, plan: ResearchPlan) -> None:
        if plan.action == "synthesize":
            if not self.can_synthesize:
                raise AgentFailure("research_missing_detail")
            return
        if len(plan.calls) > self.remaining_tool_calls:
            raise AgentFailure("research_tool_limit")
        for call in plan.calls:
            if isinstance(call, DetailCall) and call.arguments.id not in self.detail_ids:
                raise AgentFailure("research_unknown_item")
            if call.tool not in self.tools:
                raise AgentFailure("research_tool_invalid")


class NewsDetail(NewsMetadata):
    author: str = Field(repr=False)
    date_origin: Literal["published", "updated", "retrieved"]
    publisher_categories: tuple[str, ...] = Field(repr=False)


class RankedMetadata(NewsMetadata):
    similarity: Annotated[float, Field(strict=True, allow_inf_nan=False)] | None = None


class NewsResults(ResearchContract):
    items: Annotated[tuple[NewsMetadata, ...], Field(max_length=5, repr=False)]


class SearchResults(ResearchContract):
    items: Annotated[tuple[RankedMetadata, ...], Field(max_length=5, repr=False)]


class ItemResult(ResearchContract):
    found: bool = Field(strict=True)
    item: NewsDetail | None = Field(repr=False)

    @model_validator(mode="after")
    def matches_presence(self) -> Self:
        if self.found != (self.item is not None):
            raise ValueError("invalid_item_presence")
        return self


class CategoryInfo(ResearchContract):
    id: Category
    label: str = Field(repr=False)


class SourceInfo(ResearchContract):
    id: SourceId
    categories: tuple[Category, ...]


class SourcesResult(ResearchContract):
    sources: tuple[SourceInfo, ...] = Field(repr=False)
    categories: tuple[CategoryInfo, ...] = Field(repr=False)


class ResearchClaim(ResearchContract):
    text: str = Field(strict=True, repr=False)
    evidence_ids: Annotated[
        tuple[UUID, ...], Field(min_length=1, max_length=MAX_EVIDENCE_ITEMS)
    ] = Field(repr=False)

    @field_validator("text")
    @classmethod
    def bounded_claim(cls, value: str) -> str:
        return bounded_text(value, MAX_ANSWER_BYTES)

    @field_validator("evidence_ids")
    @classmethod
    def distinct_support(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return distinct_ids(value)


class ResearchAnswer(ResearchContract):
    outcome: Literal["supported", "limited", "no_match"]
    claims: tuple[ResearchClaim, ...] = Field(repr=False)
    limitations: tuple[str, ...] = Field(repr=False)
    missing_item_ids: Annotated[tuple[UUID, ...], Field(max_length=MAX_SELECTED_ITEMS)] = Field(
        repr=False
    )
    coverage: Literal["complete", "partial", "none", "discovery"]

    @field_validator("limitations")
    @classmethod
    def bounded_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for limitation in value:
            bounded_text(limitation, MAX_ANSWER_BYTES)
        return value

    @field_validator("missing_item_ids")
    @classmethod
    def distinct_missing(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return distinct_ids(value)

    @model_validator(mode="after")
    def meaningful_outcome(self) -> Self:
        if self.outcome == "supported" and (not self.claims or self.missing_item_ids):
            raise ValueError("invalid_supported_answer")
        if self.outcome == "no_match" and self.claims:
            raise ValueError("invalid_no_match_answer")
        if self.outcome != "supported" and not self.limitations:
            raise ValueError("missing_evidence_limitations")
        return self


class SynthesisScope(ResearchContract):
    coverage: Literal["complete", "partial", "none", "discovery"]
    missing_item_ids: Annotated[tuple[UUID, ...], Field(max_length=MAX_SELECTED_ITEMS)] = Field(
        repr=False
    )

    @field_validator("missing_item_ids")
    @classmethod
    def distinct_missing(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return distinct_ids(value)

    def validate_answer(self, answer: ResearchAnswer) -> None:
        if answer.coverage != self.coverage or set(answer.missing_item_ids) != set(
            self.missing_item_ids
        ):
            raise AgentFailure("research_coverage_invalid")


class ResearchReceipt(ResearchContract):
    outcome: Literal["supported", "limited", "no_match"]
    items: Annotated[int, Field(strict=True, ge=0, le=MAX_EVIDENCE_ITEMS)]
    user_preserved: bool = Field(strict=True)
    validated: bool = Field(strict=True)
    tool_calls: Annotated[int, Field(strict=True, ge=1, le=MAX_TOOL_CALLS)]
    generation_calls: Annotated[int, Field(strict=True, ge=0, le=4)]
    usage_observed_calls: Annotated[int, Field(strict=True, ge=0, le=4)]
    input_tokens: Annotated[int, Field(strict=True, ge=0, le=262144)]
    output_tokens: Annotated[int, Field(strict=True, ge=0, le=4096)]

    @model_validator(mode="after")
    def verified_completion(self) -> Self:
        if (
            not self.user_preserved
            or not self.validated
            or self.usage_observed_calls != self.generation_calls
            or (not self.generation_calls and (self.input_tokens or self.output_tokens))
        ):
            raise ValueError("invalid_research_receipt")
        return self
