"""Safe operational failures at the agent boundary."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from newsloom_core.categories import Category
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentFailure(Exception):
    """An application-owned category, never an upstream error payload."""

    def __init__(self, category: str) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", category):
            raise ValueError("invalid_agent_error_category")
        super().__init__(category)


class NewsMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    id: UUID
    title: str = Field(repr=False)
    summary: str = Field(repr=False)
    source: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)]
    category: Category
    tags: tuple[str, ...] = Field(repr=False)
    published_at: datetime
    url: str = Field(repr=False)

    @field_validator("published_at")
    @classmethod
    def aware_publication(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone_required")
        return value


class RecentNews(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    items: Annotated[tuple[NewsMetadata, ...], Field(max_length=1, repr=False)]
