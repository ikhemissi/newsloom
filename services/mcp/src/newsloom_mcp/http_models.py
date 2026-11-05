"""Versioned HTTP contracts and untrusted, position-only browse cursors."""

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from newsloom_core.briefing import BriefingRead
from pydantic import ConfigDict, Field, field_validator
from starlette.datastructures import QueryParams

from newsloom_mcp.models import (
    Contract,
    Limit,
    NewsDetail,
    NewsItem,
    RankedItem,
    SearchInput,
    SourcesResult,
    timestamp_input,
    utc_timestamp,
)


class ApiFailure(Exception):
    def __init__(self, status: int, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("invalid_api_error_code")
        self.status, self.code = status, code
        super().__init__(code)


ERROR_CODES = frozenset(
    {
        "invalid_input",
        "unauthorized",
        "insufficient_scope",
        "forbidden",
        "unavailable",
        "not_found",
        "method_denied",
        "request_limit",
        "unsupported_media_type",
        "overloaded",
        "deadline",
        "origin_denied",
        "host_denied",
        "preflight_denied",
        "response_limit",
        "invalid_response",
    }
)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def json_input(raw: bytes) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate_json_field")
            value[key] = item
        return value

    return json.loads(raw, object_pairs_hook=unique)


def normalized(args: SearchInput) -> dict[str, object]:
    result = args.model_dump(mode="json", by_alias=True, exclude_none=True)
    result["tags"] = sorted(args.tags)
    return result


class SemanticInput(SearchInput):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        validate_by_name=False,
        validate_by_alias=True,
    )
    query: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]
    limit: Limit = 20


class Position(Contract):
    published_at: datetime
    id: UUID

    @field_validator("published_at", mode="before")
    @classmethod
    def timestamp(cls, value: object) -> object:
        return timestamp_input(value)

    @field_validator("published_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return utc_timestamp(value)


class Cursor(Position):
    version: Literal[1]
    fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("invalid_cursor_version")
        return value


def fingerprint(args: SearchInput) -> str:
    return digest({"version": 1, "route": "news", "arguments": normalized(args)})


def encode_cursor(item: NewsItem, args: SearchInput) -> str:
    value = Cursor(
        version=1, published_at=item.published_at, id=item.id, fingerprint=fingerprint(args)
    )
    return base64.urlsafe_b64encode(value.model_dump_json().encode()).decode().rstrip("=")


def decode_cursor(value: str, args: SearchInput) -> Cursor:
    if not 1 <= len(value) <= 2048 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ApiFailure(400, "invalid_input")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        cursor = Cursor.model_validate(json_input(raw))
    except ValueError, binascii.Error, OverflowError:
        raise ApiFailure(400, "invalid_input") from None
    if cursor.fingerprint != fingerprint(args):
        raise ApiFailure(400, "invalid_input")
    return cursor


def browse_input(params: QueryParams) -> tuple[SearchInput, Cursor | None]:
    fields: dict[str, object] = {"limit": 20}
    allowed = {"source", "category", "tags", "from", "to", "limit", "cursor"}
    for key in params:
        values = params.getlist(key)
        if key not in allowed or (key != "tags" and len(values) != 1):
            raise ApiFailure(400, "invalid_input")
        if key == "tags":
            fields[key] = values
        elif key == "limit":
            if not re.fullmatch(r"[0-9]{1,2}", values[0]):
                raise ApiFailure(400, "invalid_input")
            fields[key] = int(values[0])
        elif key != "cursor":
            fields[key] = values[0]
    args = SearchInput.model_validate(fields)
    cursor = decode_cursor(params["cursor"], args) if "cursor" in params else None
    return args, cursor


ResultScope = Literal["page", "bounded", "item", "catalogue", "briefing"]


class Meta(Contract):
    read_at: datetime
    cache_age_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    result_scope: ResultScope


class Page(Contract):
    items: tuple[NewsItem, ...]
    next_cursor: str | None
    meta: Meta


class SemanticResult(Contract):
    items: tuple[RankedItem, ...]
    next_cursor: None = None
    meta: Meta


class DetailResult(Contract):
    item: NewsDetail
    meta: Meta


class CatalogueResult(SourcesResult):
    meta: Meta


class BriefingResult(BriefingRead):
    meta: Meta
