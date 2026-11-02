import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from newsloom_core.categories import Category
from newsloom_mcp.http_models import (
    ApiFailure,
    SemanticInput,
    browse_input,
    decode_cursor,
    encode_cursor,
    normalized,
)
from newsloom_mcp.models import NewsItem, SearchInput
from pydantic import ValidationError
from starlette.datastructures import QueryParams


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=51",
        "limit=true",
        "limit=1.5",
        "limit=20&limit=20",
        "query=x",
        "unknown=x",
        "category=unknown",
        "cursor=",
        "from=2026-01-01",
        "from=2026-02-01T00:00:00Z&to=2026-01-01T00:00:00Z",
    ],
)
def test_invalid_browse_input(query: str) -> None:
    with pytest.raises((ApiFailure, ValidationError)):
        browse_input(QueryParams(query))


def test_normalized_aliases_tags_and_exact_limit_bounds() -> None:
    for limit in (1, 50):
        args, after = browse_input(
            QueryParams(
                f"limit={limit}&tags=AI&tags=ai&tags=Gateway&from=2026-01-01T09:00:00%2B09:00"
            )
        )
        assert args.limit == limit and after is None
        assert normalized(args)["tags"] == ["ai", "gateway"]
        assert args.from_ == datetime(2026, 1, 1, tzinfo=UTC)
    args, _ = browse_input(QueryParams())
    assert args.limit == 20 and args.from_ is None
    for value in (
        {"query": ""},
        {"query": " "},
        {"query": "a" * 2049},
        {"query": "x", "limit": True},
        {"query": "x", "cursor": "x"},
        {"query": "x", "from_": "2026-01-01T00:00:00Z"},
    ):
        with pytest.raises(ValidationError):
            SemanticInput.model_validate(value)


def test_cursor_is_bound_to_normalized_filters_not_process_or_identity() -> None:
    args = SearchInput(tags=("ai", "gateway"), limit=20)
    item = NewsItem(
        id=uuid4(),
        title="authored",
        summary="authored",
        source="fixture",
        category=Category.MODELS,
        tags=(),
        published_at=datetime.now(UTC),
        url="https://example.test",
    )
    cursor = encode_cursor(item, args)
    assert decode_cursor(cursor, SearchInput(tags=("Gateway", "AI"), limit=20)).id == item.id
    assert decode_cursor(cursor, args).published_at == item.published_at
    for changed in (SearchInput(limit=10), SearchInput(tags=("ai",), limit=20)):
        with pytest.raises(ApiFailure):
            decode_cursor(cursor, changed)
    for bad in (
        "?",
        "a" * 2049,
        base64.urlsafe_b64encode(json.dumps({"version": 999}).encode()).decode().rstrip("="),
    ):
        with pytest.raises(ApiFailure):
            decode_cursor(bad, args)


def test_runtime_enablement_is_strict_and_default_is_explicit() -> None:
    from newsloom_mcp.runtime import parse_api_enabled

    assert parse_api_enabled("true") and not parse_api_enabled("false")
    for bad in ("", "1", "yes", "TRUE"):
        with pytest.raises(ValueError, match="invalid_news_api_enabled"):
            parse_api_enabled(bad)
