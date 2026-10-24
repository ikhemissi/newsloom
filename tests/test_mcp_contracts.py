from datetime import UTC, datetime
from uuid import uuid4

import pytest
from newsloom_mcp.models import DetailInput, ItemResult, RecentInput, SearchInput
from pydantic import ValidationError


@pytest.mark.parametrize("value", [True, False, 0, 51, "10", 1.0])
def test_limits_are_not_guessed_or_clamped(value: object) -> None:
    for model in (RecentInput, SearchInput):
        with pytest.raises(ValidationError):
            model.model_validate({"limit": value})


def test_defaults_and_utc_filter_semantics() -> None:
    assert RecentInput().limit == SearchInput().limit == 10
    value = SearchInput.model_validate(
        {
            "query": "  agent permissions  ",
            "from": "2026-01-01T01:00:00+01:00",
            "to": "2026-01-02T00:00:00Z",
            "tags": [" AI ", "Gateway", "AI"],
        }
    )
    assert value.from_ == datetime(2026, 1, 1, tzinfo=UTC)
    assert value.tags == ("ai", "gateway") and value.query == "agent permissions"
    assert "from" in SearchInput.model_json_schema()["properties"]
    assert "from_" not in SearchInput.model_json_schema()["properties"]


@pytest.mark.parametrize(
    "value",
    [
        {"since": "2026-01-01"},
        {"since": "invalid"},
        {"since": 0},
        {"since": "0"},
    ],
)
def test_browsing_rejects_ambiguous_dates(value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RecentInput.model_validate(value)


@pytest.mark.parametrize(
    "value",
    [
        {"from": "2026-01-02T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        {"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        {"from": "2026-01-01"},
        {"query": " "},
        {"query": "x" * 2049},
        {"category": "Governance"},
        {"source": "bad' OR true"},
        {"tags": [""]},
        {"tags": ["tag"] * 11},
        {"tags": ["x" * 49]},
        {"extra": True},
    ],
)
def test_invalid_search_inputs_fail_explicitly(value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SearchInput.model_validate(value)


def test_detail_absence_and_malformed_identifier_are_distinct() -> None:
    assert DetailInput(id=uuid4()).id
    assert not ItemResult(found=False, item=None).found
    with pytest.raises(ValidationError):
        DetailInput.model_validate({"id": "invalid"})
    with pytest.raises(ValidationError):
        ItemResult(found=True, item=None)
