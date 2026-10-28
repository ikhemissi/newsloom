import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from newsloom_agent.models import RecentNews
from newsloom_agent.research_models import (
    MAX_QUESTION_BYTES,
    ItemResult,
    NewsResults,
    PresentationPreferences,
    ResearchAnswer,
    ResearchFilters,
    ResearchPlan,
    ResearchRequest,
    SearchArguments,
    SearchResults,
    SourcesResult,
)
from pydantic import ValidationError


def metadata() -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "title": "Authored contract fixture",
        "summary": "Only this authored summary is available.",
        "source": "test-source",
        "category": "research-evaluations",
        "tags": ["agents"],
        "published_at": "2026-10-27T10:00:00Z",
        "url": "https://example.test/authored",
    }


@pytest.mark.parametrize("count", [1, 5])
def test_selected_request_contract(count: int) -> None:
    ids = [str(uuid4()) for _ in range(count)]
    request = ResearchRequest.model_validate(
        {
            "operation": "research",
            "question": "Compare the selected items.",
            "item_ids": ids,
            "preferences": {"audience": "Researcher", "detail": "detailed", "language": "English"},
        }
    )
    assert request.item_ids is not None and len(request.item_ids) == count
    assert request.preferences.detail == "detailed"
    assert ResearchRequest.model_validate_json(request.model_dump_json()) == request
    assert "Compare the selected" not in repr(request)
    assert ids[0] not in repr(request)


@pytest.mark.parametrize(
    "changes",
    [
        {"item_ids": []},
        {"item_ids": [str(uuid4()) for _ in range(6)]},
        {"item_ids": ["not-a-uuid"]},
        {"item_ids": [str(uuid4())] * 2},
        {"question": ""},
        {"question": " \n\t"},
        {"question": False},
        {"question": "\ud800"},
        {"question": "x" * (MAX_QUESTION_BYTES + 1)},
        {"question": "\u00e9" * (MAX_QUESTION_BYTES // 2 + 1)},
        {"endpoint": "https://example.test"},
        {"operation": "recent-news"},
        {"filters": {"query": "not a hard filter"}},
        {"preferences": {"memory": True}},
        {"preferences": {"detail": "unlimited"}},
    ],
)
def test_request_rejects_malformed_or_oversized_input(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResearchRequest.model_validate(
            {"operation": "research", "question": "Authored question", **changes}
        )


def test_question_exact_utf8_boundaries() -> None:
    for question in ("x" * MAX_QUESTION_BYTES, "\u00e9" * (MAX_QUESTION_BYTES // 2)):
        request = ResearchRequest(operation="research", question=question)
        assert len(request.question.encode()) == MAX_QUESTION_BYTES
        assert request.item_ids is None


@pytest.mark.parametrize(("field", "limit"), [("language", 64), ("audience", 256), ("focus", 1024)])
def test_preference_byte_boundaries(field: str, limit: int) -> None:
    for text in ("x" * limit, "\u00e9" * (limit // 2)):
        assert PresentationPreferences.model_validate({field: text}).model_dump()[field] == text
        with pytest.raises(ValidationError):
            PresentationPreferences.model_validate({field: text + "x"})
    for invalid in ("", "  ", 42, "\ud800"):
        with pytest.raises(ValidationError):
            PresentationPreferences.model_validate({field: invalid})


def test_filter_normalization_and_roundtrip() -> None:
    filters = ResearchFilters.model_validate(
        {
            "source": "test-source",
            "tags": [" Agents ", "AGENTS", "  model   serving  ", "c++"],
            "from": "2026-10-27T11:00:00+01:00",
            "to": "2026-10-28T10:00:00Z",
        }
    )
    assert filters.tags == ("agents", "model serving", "c++")
    assert filters.from_ == datetime(2026, 10, 27, 10, tzinfo=UTC)
    assert ResearchFilters.model_validate_json(filters.model_dump_json(by_alias=True)) == filters


@pytest.mark.parametrize(
    "filters",
    [
        {"from": "2026-10-27"},
        {"to": "2026-10-27T10:00:00"},
        {"from": 1793095200},
        {"to": True},
        {"from": "this week"},
        {"from": "2026-10-28T00:00:00Z", "to": "2026-10-27T00:00:00Z"},
        {"from": "2026-10-27T00:00:00Z", "to": "2026-10-27T00:00:00Z"},
        {"source": "https://example.test"},
        {"category": "unknown"},
        {"tags": [""]},
        {"tags": ["a" * 49]},
        {"tags": ["a"] * 11},
        {"tags": ["hostile\ninstruction!"]},
        {"url": "https://example.test"},
    ],
)
def test_invalid_filters(filters: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResearchFilters.model_validate(filters)


@pytest.mark.parametrize("limit", [0, 6, True, 1.0, "1"])
def test_search_limit_is_strict_and_research_specific(limit: object) -> None:
    with pytest.raises(ValidationError):
        SearchArguments.model_validate({"limit": limit})


def test_fixed_tool_plan_shapes() -> None:
    calls = [
        {"tool": "list_sources", "arguments": {}},
        {"tool": "get_recent_news", "arguments": {"limit": 5}},
        {"tool": "search_news", "arguments": {"query": "agents", "tags": ["Agents"]}},
        {"tool": "get_news_item", "arguments": {"id": str(uuid4())}},
    ]
    plan = ResearchPlan.model_validate({"action": "tools", "calls": calls})
    assert len(plan.calls) == 4
    assert ResearchPlan.model_validate_json(plan.model_dump_json(by_alias=True)) == plan
    assert ResearchPlan(action="synthesize").calls == ()


@pytest.mark.parametrize(
    "plan",
    [
        {"action": "tools", "calls": []},
        {"action": "synthesize", "calls": [{"tool": "list_sources", "arguments": {}}]},
        {"action": "tools", "calls": [{"tool": "web_search", "arguments": {}}]},
        {"action": "tools", "calls": [{"tool": "list_sources", "arguments": {"endpoint": "x"}}]},
        {"action": "tools", "calls": [{"tool": "list_sources", "arguments": {}}] * 9},
        {"action": "synthesize", "reasoning": "not an allowed field"},
    ],
)
def test_plan_closed_shapes(plan: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResearchPlan.model_validate(plan)


def test_public_metadata_detail_and_not_found_shapes() -> None:
    item = metadata()
    result = NewsResults.model_validate({"items": [item]})
    assert result.items[0].title == item["title"]
    ranked = SearchResults.model_validate({"items": [{**item, "similarity": 0.8}]})
    assert ranked.items[0].similarity == 0.8
    detail = {
        **item,
        "author": "Authored author",
        "date_origin": "published",
        "publisher_categories": ["AI"],
    }
    found = ItemResult.model_validate({"found": True, "item": detail})
    assert found.item is not None and found.item.author == "Authored author"
    assert ItemResult(found=False, item=None).item is None
    sources = SourcesResult.model_validate(
        {
            "sources": [{"id": "test-source", "categories": ["research-evaluations"]}],
            "categories": [{"id": "research-evaluations", "label": "Research"}],
        }
    )
    assert sources.sources[0].id == "test-source"
    assert "Authored author" not in repr(found)
    with pytest.raises(ValidationError):
        ItemResult.model_validate({"found": True, "item": item})
    with pytest.raises(ValidationError):
        ItemResult.model_validate({"found": False, "item": detail})
    with pytest.raises(ValidationError):
        ItemResult.model_validate({"found": "false", "item": None})
    with pytest.raises(ValidationError):
        NewsResults.model_validate({"items": [{**item, "full_text": "not available"}]})
    with pytest.raises(ValidationError):
        SearchResults.model_validate({"items": [{**item, "similarity": float("nan")}]})
    with pytest.raises(ValidationError):
        NewsResults.model_validate({"items": [item] * 6})


def test_recent_news_contract_is_not_widened() -> None:
    item = metadata()
    assert len(RecentNews.model_validate({"items": [item]}).items) == 1
    with pytest.raises(ValidationError):
        RecentNews.model_validate({"items": [item, item]})


def test_closed_final_answer_contract() -> None:
    evidence = str(uuid4())
    answer: dict[str, object] = {
        "outcome": "supported",
        "claims": [{"text": "Authored supported statement.", "evidence_ids": [evidence]}],
        "limitations": [],
        "missing_item_ids": [],
        "coverage": "discovery",
    }
    parsed = ResearchAnswer.model_validate(answer)
    assert ResearchAnswer.model_validate_json(json.dumps(answer)) == parsed
    assert "Authored supported" not in repr(parsed)
    variants: tuple[dict[str, object], ...] = (
        {"url": "https://example.test/invented"},
        {"claims": [{"text": "Unsupported", "evidence_ids": []}]},
        {"claims": [{"text": "Duplicate", "evidence_ids": [evidence, evidence]}]},
        {"claims": []},
        {"outcome": "no_match"},
        {"missing_item_ids": [evidence]},
    )
    for changes in variants:
        with pytest.raises(ValidationError):
            ResearchAnswer.model_validate({**answer, **changes})
    assert (
        ResearchAnswer.model_validate(
            {
                "outcome": "no_match",
                "claims": [],
                "limitations": ["No matching stored evidence."],
                "missing_item_ids": [],
                "coverage": "discovery",
            }
        ).outcome
        == "no_match"
    )
