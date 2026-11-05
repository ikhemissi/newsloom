"""Reader feedback on briefings and research answers: validation, hashing and storage.

Feedback text is untrusted user content: it is stored, never logged.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Protocol
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_SNAPSHOT_BYTES = 48 * 1024  # answer (16 KiB) + question (8 KiB) + JSON overhead


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ResearchSnapshot(Contract):
    """What the browser showed: provenance is client-supplied, not verified."""

    question: Annotated[str, Field(min_length=1, max_length=8192)]
    answer: dict[str, object]
    citations: Annotated[list[dict[str, object]], Field(max_length=100)] = []
    filters: dict[str, object] = {}

    @model_validator(mode="after")
    def bounded(self) -> ResearchSnapshot:
        if len(self.model_dump_json().encode()) > MAX_SNAPSHOT_BYTES:
            raise ValueError("snapshot_too_large")
        return self


class FeedbackInput(Contract):
    target_type: Literal["briefing", "research"]
    target_ref: Annotated[str, Field(min_length=1, max_length=200)]
    rating: Literal["up", "down"]
    comment: Annotated[str | None, Field(max_length=1000)] = None
    snapshot: ResearchSnapshot | None = None

    @field_validator("comment")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def consistent(self) -> FeedbackInput:
        if self.target_type == "briefing":
            UUID(self.target_ref)
            if self.snapshot is not None:
                raise ValueError("briefing_feedback_has_no_snapshot")
        elif self.snapshot is None:
            raise ValueError("research_feedback_requires_snapshot")
        return self


class ReviewQuery(Contract):
    rating: Literal["up", "down"] | None = None
    target_type: Literal["briefing", "research"] | None = None
    days: Annotated[int, Field(ge=1, le=365)] = 30
    limit: Annotated[int, Field(ge=1, le=1000)] = 200


class Vote(Contract):
    rating: Literal["up", "down"]
    comment: str | None


class ReviewItem(Contract):
    created_at: datetime
    target_type: Literal["briefing", "research"]
    target_ref: str
    rating: Literal["up", "down"]
    comment: str | None
    snapshot: dict[str, object] | None


def reader_hash(tenant: UUID, object_id: UUID) -> str:
    """Pseudonymous reader key: stable per reader, not reversible without the object ID."""
    return hashlib.sha256(f"newsloom-feedback:v1:{tenant}:{object_id}".encode()).hexdigest()


def rating_value(rating: str) -> int:
    return 1 if rating == "up" else -1


def rating_name(value: object) -> Literal["up", "down"]:
    return "up" if value == 1 else "down"


class FeedbackStore(Protocol):
    async def record(self, reader: str, entry: FeedbackInput) -> bool: ...

    async def mine(self, reader: str, target_type: str, target_ref: str) -> Vote | None: ...

    async def review(self, query: ReviewQuery) -> list[ReviewItem]: ...


class FeedbackRepository:
    def __init__(self, connection: AsyncConnection[tuple[object, ...]]) -> None:
        self.connection = connection

    async def record(self, reader: str, entry: FeedbackInput) -> bool:
        """Insert one vote; False when the briefing version is not in the history."""
        if entry.target_type == "briefing":
            known = await (
                await self.connection.execute(
                    "SELECT 1 FROM public.briefing_history WHERE version=%s",
                    (UUID(entry.target_ref),),
                )
            ).fetchone()
            if known is None:
                return False
        snapshot = entry.snapshot.model_dump(mode="json") if entry.snapshot else None
        await self.connection.execute(
            "INSERT INTO public.feedback"
            "(reader_hash,target_type,target_ref,rating,comment,snapshot,snapshot_source) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                reader,
                entry.target_type,
                entry.target_ref,
                rating_value(entry.rating),
                entry.comment,
                Jsonb(snapshot) if snapshot is not None else None,
                "client" if snapshot is not None else None,
            ),
        )
        return True

    async def mine(self, reader: str, target_type: str, target_ref: str) -> Vote | None:
        row = await (
            await self.connection.execute(
                "SELECT rating,comment FROM public.feedback "
                "WHERE reader_hash=%s AND target_type=%s AND target_ref=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (reader, target_type, target_ref),
            )
        ).fetchone()
        if row is None:
            return None
        return Vote(rating=rating_name(row[0]), comment=row[1] if isinstance(row[1], str) else None)

    async def review(self, query: ReviewQuery) -> list[ReviewItem]:
        since = datetime.now(UTC) - timedelta(days=query.days)
        rows = await (
            await self.connection.execute(
                "SELECT created_at,target_type,target_ref,rating,comment,snapshot FROM ("
                " SELECT DISTINCT ON (target_type,target_ref,reader_hash) *"
                " FROM public.feedback WHERE created_at >= %s"
                " AND (%s::text IS NULL OR target_type = %s)"
                " ORDER BY target_type,target_ref,reader_hash,created_at DESC"
                ") latest WHERE (%s::smallint IS NULL OR rating = %s)"
                " ORDER BY created_at DESC LIMIT %s",
                (
                    since,
                    query.target_type,
                    query.target_type,
                    rating_value(query.rating) if query.rating else None,
                    rating_value(query.rating) if query.rating else None,
                    query.limit,
                ),
            )
        ).fetchall()
        return [
            ReviewItem.model_validate(
                {
                    "created_at": row[0],
                    "target_type": row[1],
                    "target_ref": row[2],
                    "rating": rating_name(row[3]),
                    "comment": row[4],
                    "snapshot": row[5],
                }
            )
            for row in rows
        ]


def export_lines(items: list[ReviewItem]) -> str:
    return "".join(
        json.dumps(item.model_dump(mode="json"), sort_keys=True) + "\n" for item in items
    )
