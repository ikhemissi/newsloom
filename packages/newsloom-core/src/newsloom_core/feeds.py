"""Validate the feed catalogue without retrieving any remote content."""

import argparse
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator


class FeedSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    id: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    title: Annotated[str, Field(min_length=1)]
    url: HttpUrl
    kind: Literal["rss", "atom"]
    include_categories: Annotated[tuple[str, ...], Field(min_length=1)] | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("Feed configuration requires HTTPS URLs")
        if value.username is not None or value.password is not None:
            raise ValueError("Feed URLs must not contain credentials")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Feed titles must not be blank")
        return value

    @field_validator("include_categories")
    @classmethod
    def validate_categories(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is not None and any(not term.strip() for term in value):
            raise ValueError("Category filters must not contain blank terms")
        return value


_CATALOGUE = TypeAdapter(
    Annotated[list[FeedSource], Field(min_length=1)],
    config=ConfigDict(hide_input_in_errors=True),
)


def load_feed_catalogue(path: Path) -> tuple[FeedSource, ...]:
    sources = _CATALOGUE.validate_json(path.read_bytes())
    ids = [source.id for source in sources]
    urls = [source.url for source in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("Feed IDs must be unique")
    if len(urls) != len(set(urls)):
        raise ValueError("Feed URLs must be unique")
    return tuple(sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", type=Path, help="Path to a feed catalogue JSON file")
    args = parser.parse_args()
    sources = load_feed_catalogue(args.catalogue)
    print(f"Validated {len(sources)} feed sources (configuration only; no network requests).")
