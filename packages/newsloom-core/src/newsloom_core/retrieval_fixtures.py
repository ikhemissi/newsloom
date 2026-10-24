"""Authored frozen retrieval inputs shared by the evaluator and administrative staging."""

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from newsloom_core.categories import Category

FIXTURES = Path("config/mcp-evaluation.json")


def corpus_uuid(identifier: str) -> UUID:
    return uuid5(NAMESPACE_URL, "newsloom/retrieval-evaluation/" + identifier)


class CorpusItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    id: Annotated[str, Field(pattern=r"^d[0-9]{2}$")]
    source: Annotated[str, Field(pattern=r"^synthetic-[ab]$")]
    category: Category
    title: Annotated[str, Field(min_length=1, max_length=2048)]
    summary: Annotated[str, Field(min_length=1, max_length=2048)]
    tags: Annotated[tuple[str, ...], Field(min_length=3, max_length=5)]
    published_at: datetime


class QueryCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    id: Annotated[str, Field(pattern=r"^[uf][0-9]{2}$")]
    group: Literal["filtered", "unfiltered"]
    query: Annotated[str, Field(min_length=1, max_length=2048)]
    filters: dict[str, object]
    relevant: Annotated[tuple[str, ...], Field(min_length=1, max_length=5)]


class RetrievalFixtures(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    corpus: Annotated[tuple[CorpusItem, ...], Field(min_length=11, max_length=64)]
    queries: Annotated[tuple[QueryCase, ...], Field(min_length=20, max_length=20)]
    development: Annotated[tuple[dict[str, object], ...], Field(min_length=1)]

    @model_validator(mode="after")
    def frozen_groups(self) -> RetrievalFixtures:
        ids = {item.id for item in self.corpus}
        if (
            len(ids) != len(self.corpus)
            or len({q.id for q in self.queries}) != 20
            or {item.category for item in self.corpus} != set(Category)
            or sum(q.group == "filtered" for q in self.queries) != 10
            or sum(q.group == "unfiltered" for q in self.queries) != 10
            or any(
                (q.group == "filtered") != bool(q.filters)
                or len(set(q.relevant)) != len(q.relevant)
                or not set(q.relevant) <= ids
                for q in self.queries
            )
            or any(item.published_at.tzinfo is None for item in self.corpus)
        ):
            raise ValueError("invalid_frozen_retrieval_set")
        return self


def load_fixtures() -> RetrievalFixtures:
    return RetrievalFixtures.model_validate_json(FIXTURES.read_bytes())


def fixture_revision() -> str:
    return sha256(FIXTURES.read_bytes()).hexdigest()
