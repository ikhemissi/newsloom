"""Shared normalized publisher data; all fields remain untrusted."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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
