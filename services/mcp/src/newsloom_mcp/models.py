"""Public MCP contracts, strict inputs and bounded safe failures."""

import re
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from newsloom_core.categories import Category
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Limit = Annotated[int, Field(strict=True, ge=1, le=50)]
SourceId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)]


class McpFailure(Exception):
    def __init__(self, category: str) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", category):
            raise ValueError("invalid_mcp_error_category")
        super().__init__(category)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_required")
    return value.astimezone(UTC)


def timestamp_input(value: object) -> object:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        raise ValueError("timestamp_required")
    return value


class RecentInput(Contract):
    limit: Limit = 10
    since: datetime | None = None

    @field_validator("since", mode="before")
    @classmethod
    def timestamp_since(cls, value: object) -> object:
        return timestamp_input(value)

    @field_validator("since")
    @classmethod
    def aware_since(cls, value: datetime | None) -> datetime | None:
        return utc_timestamp(value) if value is not None else None


class DetailInput(Contract):
    id: UUID


class SearchInput(Contract):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, populate_by_name=True
    )
    query: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    source: SourceId | None = None
    category: Category | None = None
    tags: Annotated[tuple[str, ...], Field(max_length=10)] = ()
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    limit: Limit = 10

    @field_validator("from_", "to", mode="before")
    @classmethod
    def timestamp_bounds(cls, value: object) -> object:
        return timestamp_input(value)

    @field_validator("query")
    @classmethod
    def meaningful_query(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("blank_query")
        return value.strip() if value is not None else None

    @field_validator("tags")
    @classmethod
    def normalized_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        tags = tuple(" ".join(tag.split()).casefold() for tag in value)
        if any(not re.fullmatch(r"[a-z0-9][a-z0-9 +#.-]{0,47}", tag) for tag in tags):
            raise ValueError("invalid_tag_filter")
        return tuple(dict.fromkeys(tags))

    @field_validator("from_", "to")
    @classmethod
    def aware_date(cls, value: datetime | None) -> datetime | None:
        return utc_timestamp(value) if value is not None else None

    @model_validator(mode="after")
    def ordered_dates(self) -> SearchInput:
        if self.from_ is not None and self.to is not None and self.from_ >= self.to:
            raise ValueError("invalid_date_interval")
        return self


class NewsItem(Contract):
    id: UUID
    title: str
    summary: str
    source: SourceId
    category: Category
    tags: tuple[str, ...]
    published_at: datetime
    url: str

    @field_validator("published_at")
    @classmethod
    def publication_utc(cls, value: datetime) -> datetime:
        return utc_timestamp(value)


class NewsDetail(NewsItem):
    author: str
    date_origin: Literal["published", "updated", "retrieved"]
    publisher_categories: tuple[str, ...]


class RankedItem(NewsItem):
    similarity: Annotated[float, Field(allow_inf_nan=False)] | None = None


class NewsResults(Contract):
    items: tuple[NewsItem, ...]


class SearchResults(Contract):
    items: tuple[RankedItem, ...]


class ItemResult(Contract):
    found: bool
    item: NewsDetail | None

    @model_validator(mode="after")
    def matches_presence(self) -> ItemResult:
        if self.found != (self.item is not None):
            raise ValueError("invalid_item_presence")
        return self


class CategoryInfo(Contract):
    id: Category
    label: str


class SourceInfo(Contract):
    id: SourceId
    categories: tuple[Category, ...]


class SourcesResult(Contract):
    sources: tuple[SourceInfo, ...]
    categories: tuple[CategoryInfo, ...]
