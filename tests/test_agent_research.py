import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from newsloom_agent.auth import Authorization, Caller
from newsloom_agent.delegation import ResearchToolResult
from newsloom_agent.models import AgentFailure, NewsMetadata
from newsloom_agent.research import (
    EvidenceState,
    ResearchConnection,
    ResearchController,
    ResearchProgress,
    ResearchResult,
    render_answer,
    safe_citation,
)
from newsloom_agent.research_generation import FINAL_TOKENS, PLANNING_TOKENS, ResearchStats
from newsloom_agent.research_models import (
    MAX_ANSWER_BYTES,
    DetailArguments,
    DetailCall,
    ItemResult,
    NewsDetail,
    NewsResults,
    PlanningScope,
    RecentArguments,
    RecentCall,
    ResearchAnswer,
    ResearchClaim,
    ResearchFilters,
    ResearchPlan,
    ResearchRequest,
    SearchArguments,
    SearchCall,
    SearchResults,
    SourcesArguments,
    SourcesCall,
    SourcesResult,
    ToolCall,
)
from newsloom_core.categories import Category
from pydantic import ValidationError


def authorization() -> Authorization:
    return Authorization(
        Caller(
            uuid4(), uuid4(), uuid4(), "authored-subject", int(time.time()) + 600, "test-assertion"
        ),
        time.monotonic() + 30,
    )


def detail(name: str = "Alder", item_id: UUID | None = None) -> NewsDetail:
    return NewsDetail(
        id=item_id or uuid4(),
        title=f"Project {name} announcement",
        summary=f"Project {name} reports a batch limit of 8 items, up from 4.",
        source="authored-source",
        category=Category.GOVERNANCE,
        tags=("agents", "mcp"),
        published_at=datetime(2026, 10, 27, 10, tzinfo=UTC),
        url=f"https://example.test/{name}",
        author="Authored author",
        date_origin="published",
        publisher_categories=(),
    )


def metadata(item: NewsDetail) -> NewsMetadata:
    return NewsMetadata.model_validate(item.model_dump(include=set(NewsMetadata.model_fields)))


def answer(
    items: tuple[NewsDetail, ...], *, coverage: str = "discovery", missing: tuple[UUID, ...] = ()
) -> ResearchAnswer:
    return ResearchAnswer.model_validate(
        {
            "outcome": "limited" if missing else "supported",
            "claims": [
                {
                    "text": f"Project {item.title.split()[1]} reports a doubled batch limit.",
                    "evidence_ids": [str(item.id)],
                }
                for item in items
            ],
            "limitations": ["One selected record is missing."] if missing else [],
            "missing_item_ids": [str(value) for value in missing],
            "coverage": coverage,
        }
    )


def plan(*calls: ToolCall) -> ResearchPlan:
    return ResearchPlan(action="tools" if calls else "synthesize", calls=calls)


@dataclass(repr=False)
class ScriptedConnection:
    authorization: Authorization
    results: list[ResearchToolResult | AgentFailure]
    calls: list[ToolCall] = field(default_factory=list)

    async def call(self, call: ToolCall) -> ResearchToolResult:
        self.calls.append(call)
        if not self.results:
            pytest.fail("unexpected tool call")
        result = self.results.pop(0)
        if isinstance(result, AgentFailure):
            raise result
        return result


@dataclass(repr=False)
class ScriptedReader:
    results: list[ResearchToolResult | AgentFailure]
    connections: list[ScriptedConnection] = field(default_factory=list)
    closed: int = 0

    @asynccontextmanager
    async def research(
        self, authorization: Authorization, selected_ids: tuple[UUID, ...] | None = None
    ) -> AsyncIterator[ResearchConnection]:
        connection = ScriptedConnection(authorization, self.results)
        self.connections.append(connection)
        try:
            yield connection
        finally:
            self.closed += 1


@dataclass(repr=False)
class ScriptedModel:
    plans: list[ResearchPlan]
    answer: ResearchAnswer | None
    contexts: list[str] = field(default_factory=list)
    final_calls: int = 0
    scopes: list[PlanningScope] = field(default_factory=list)

    async def plan(
        self,
        context: str,
        authorization: Authorization,
        stats: ResearchStats,
        *,
        scope: PlanningScope,
    ) -> ResearchPlan:
        self.scopes.append(scope)
        self.contexts.append(context)
        stats.admit(final=False)
        stats.usage(100, 30, PLANNING_TOKENS)
        if not self.plans:
            pytest.fail("unexpected planning call")
        return self.plans.pop(0)

    async def synthesize(
        self, context: str, authorization: Authorization, stats: ResearchStats
    ) -> ResearchAnswer:
        self.contexts.append(context)
        self.final_calls += 1
        stats.admit(final=True)
        stats.usage(100, 50, FINAL_TOKENS)
        if self.answer is None:
            pytest.fail("unexpected synthesis")
        return self.answer


async def test_selected_multi_item_bootstrap_preferences_and_supported_comparison() -> None:
    first, second = detail(), detail("Birch")
    reader = ScriptedReader(
        [ItemResult(found=True, item=first), ItemResult(found=True, item=second)]
    )
    model = ScriptedModel([plan()], answer((first, second), coverage="complete"))
    request = ResearchRequest.model_validate(
        {
            "operation": "research",
            "question": "Compare the reported batch limits.",
            "item_ids": [str(first.id), str(second.id)],
            "preferences": {"audience": "Engineers", "language": "English", "detail": "detailed"},
        }
    )
    stats = ResearchStats()
    updates = [
        update
        async for update in ResearchController(reader, model).run(request, authorization(), stats)
    ]
    assert all(isinstance(update, ResearchProgress) for update in updates[:-1])
    result = updates[-1]
    assert isinstance(result, ResearchResult)
    assert first.url in result.text and second.url in result.text
    assert "doubled batch limit" in result.text
    assert "full articles and web search were not accessed" in result.text
    assert stats.tool_calls == 2 and stats.calls == 2 and reader.closed == 1
    assert all(isinstance(call, DetailCall) for call in reader.connections[0].calls)
    context = json.loads(model.contexts[0])
    assert context["request"]["preferences"]["audience"] == "Engineers"
    assert len(context["detail_evidence"]) == 2 and context["coverage"] == "complete"
    assert "test-assertion" not in "".join(model.contexts)


async def test_discovery_uses_sources_search_and_only_discovered_details() -> None:
    item = detail()
    reader = ScriptedReader(
        [
            SourcesResult(sources=(), categories=()),
            SearchResults.model_validate(
                {"items": [{**metadata(item).model_dump(), "similarity": 0.8}]}
            ),
            ItemResult(found=True, item=item),
        ]
    )
    model = ScriptedModel(
        [
            plan(
                SourcesCall(tool="list_sources", arguments=SourcesArguments()),
                SearchCall(tool="search_news", arguments=SearchArguments(query="batch limit")),
            ),
            plan(DetailCall(tool="get_news_item", arguments=DetailArguments(id=item.id))),
            plan(),
        ],
        answer((item,)),
    )
    stats = ResearchStats()
    request = ResearchRequest(operation="research", question="What batch limits changed?")
    updates = [
        update
        async for update in ResearchController(reader, model).run(request, authorization(), stats)
    ]
    assert isinstance(updates[-1], ResearchResult)
    assert stats.planning_calls == 3 and stats.final_calls == 1 and stats.tool_calls == 3
    assert [call.tool for call in reader.connections[0].calls] == [
        "list_sources",
        "search_news",
        "get_news_item",
    ]
    initial, discovered, inspected = model.scopes
    assert initial.detail_ids == () and not initial.can_synthesize
    assert "get_news_item" not in initial.tools
    assert discovered.detail_ids == (item.id,) and not discovered.can_synthesize
    assert "list_sources" not in discovered.tools
    assert inspected.can_synthesize and inspected.detail_ids == ()
    assert [scope.remaining_tool_calls for scope in model.scopes] == [8, 6, 5]


async def test_no_match_after_healthy_retrieval_never_calls_final_model() -> None:
    reader = ScriptedReader([NewsResults(items=())])
    model = ScriptedModel(
        [plan(RecentCall(tool="get_recent_news", arguments=RecentArguments())), plan()], None
    )
    updates = [
        update
        async for update in ResearchController(reader, model).run(
            ResearchRequest(operation="research", question="Any matching news?"),
            authorization(),
            ResearchStats(),
        )
    ]
    result = updates[-1]
    assert isinstance(result, ResearchResult) and result.answer.outcome == "no_match"
    assert model.final_calls == 0 and reader.closed == 1


async def test_missing_selected_records_are_explicit_without_replacement_discovery() -> None:
    item, missing = detail(), uuid4()
    reader = ScriptedReader([ItemResult(found=True, item=item), ItemResult(found=False, item=None)])
    model = ScriptedModel([plan()], answer((item,), coverage="partial", missing=(missing,)))
    request = ResearchRequest(
        operation="research", question="Compare them", item_ids=(item.id, missing)
    )
    updates = [
        update
        async for update in ResearchController(reader, model).run(
            request, authorization(), ResearchStats()
        )
    ]
    result = updates[-1]
    assert isinstance(result, ResearchResult)
    assert str(missing) in result.text and "partial" in result.text
    assert len(reader.connections[0].calls) == 2
    assert all(isinstance(call, DetailCall) for call in reader.connections[0].calls)


async def test_all_selected_missing_needs_no_model_calls() -> None:
    missing = uuid4()
    reader = ScriptedReader([ItemResult(found=False, item=None)])
    model = ScriptedModel([], None)
    request = ResearchRequest(operation="research", question="Explain it", item_ids=(missing,))
    stats = ResearchStats()
    updates = [
        update
        async for update in ResearchController(reader, model).run(request, authorization(), stats)
    ]
    result = updates[-1]
    assert isinstance(result, ResearchResult) and result.answer.coverage == "none"
    assert not model.contexts and stats.calls == 0 and stats.tool_calls == 1


async def test_absent_article_detail_is_an_explicit_limitation_not_an_invented_claim() -> None:
    item = detail()
    reader = ScriptedReader([ItemResult(found=True, item=item)])
    limited = ResearchAnswer(
        outcome="limited",
        claims=(),
        limitations=("The stored summary does not describe the requested experiment design.",),
        missing_item_ids=(),
        coverage="complete",
    )
    model = ScriptedModel([plan()], limited)
    request = ResearchRequest(
        operation="research",
        question="Explain the full article's experiment design",
        item_ids=(item.id,),
    )
    updates = [
        update
        async for update in ResearchController(reader, model).run(
            request, authorization(), ResearchStats()
        )
    ]
    result = updates[-1]
    assert isinstance(result, ResearchResult) and result.answer.outcome == "limited"
    assert "does not describe" in result.text and not result.answer.claims
    assert "full articles and web search were not accessed" in result.text


async def test_request_local_language_and_focus_reach_the_model_without_persistence() -> None:
    item = detail()
    reader = ScriptedReader([ItemResult(found=True, item=item)])
    french = ResearchAnswer(
        outcome="supported",
        claims=(
            ResearchClaim(
                text="La limite annoncee passe de 4 a 8 elements.", evidence_ids=(item.id,)
            ),
        ),
        limitations=(),
        missing_item_ids=(),
        coverage="complete",
    )
    model = ScriptedModel([plan()], french)
    request = ResearchRequest.model_validate(
        {
            "operation": "research",
            "question": "Explain the reported change.",
            "item_ids": [str(item.id)],
            "preferences": {
                "language": "French",
                "focus": "Batch capacity",
                "audience": "Operators",
            },
        }
    )
    updates = [
        update
        async for update in ResearchController(reader, model).run(
            request, authorization(), ResearchStats()
        )
    ]
    assert isinstance(updates[-1], ResearchResult) and "4 a 8" in updates[-1].text
    for context in model.contexts:
        preferences = json.loads(context)["request"]["preferences"]
        assert preferences["language"] == "French" and preferences["focus"] == "Batch capacity"


def filters() -> dict[str, object]:
    return {
        "source": "authored-source",
        "category": "governance",
        "tags": ["agents", "mcp"],
        "from": "2026-10-27T09:00:00Z",
        "to": "2026-10-27T11:00:00Z",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"source": None},
        {"source": "another-source"},
        {"category": None},
        {"category": "models"},
        {"tags": ["agents"]},
        {"from": None},
        {"from": "2026-10-27T08:00:00Z"},
        {"to": None},
        {"to": "2026-10-27T12:00:00Z"},
    ],
)
def test_model_cannot_drop_or_broaden_immutable_caller_filters(changes: dict[str, object]) -> None:
    request = ResearchRequest.model_validate(
        {"operation": "research", "question": "Filtered research", "filters": filters()}
    )
    state = EvidenceState(request)
    call = SearchCall(
        tool="search_news", arguments=SearchArguments.model_validate({**filters(), **changes})
    )
    with pytest.raises(AgentFailure, match="research_filter_relaxation"):
        state.authorize(call)
    assert not state.history
    with pytest.raises(AgentFailure, match="research_filter_relaxation"):
        state.authorize(RecentCall(tool="get_recent_news", arguments=RecentArguments()))


def test_valid_narrower_search_and_server_filter_violation() -> None:
    request = ResearchRequest.model_validate(
        {"operation": "research", "question": "Filtered research", "filters": filters()}
    )
    state = EvidenceState(request)
    call = SearchCall(tool="search_news", arguments=SearchArguments.model_validate(filters()))
    state.authorize(call)
    item = detail()
    state.add(item, call.arguments)
    for changed in (
        item.model_copy(update={"source": "another-source"}),
        item.model_copy(update={"tags": ("agents",)}),
        item.model_copy(update={"published_at": datetime(2026, 10, 27, 11, tzinfo=UTC)}),
    ):
        with pytest.raises(AgentFailure, match="research_filter_violation"):
            state.add(changed, call.arguments)
    newer = SearchCall(
        tool="search_news",
        arguments=SearchArguments.model_validate(
            {**filters(), "from": "2026-10-27T10:00:00Z", "to": "2026-10-27T10:30:00Z"}
        ),
    )
    state.authorize(newer)
    state.add(item, newer.arguments)


def test_evidence_deduplication_conflicts_and_exact_unique_record_limit() -> None:
    state = EvidenceState(ResearchRequest(operation="research", question="Compare"))
    items = [detail(str(index)) for index in range(10)]
    for item in items:
        state.add(item, ResearchFilters())
        state.add(metadata(item), ResearchFilters())
    assert len(state.metadata) == len(state.details) == 10
    with pytest.raises(AgentFailure, match="research_evidence_limit"):
        state.add(detail("eleventh"), ResearchFilters())
    assert len(state.metadata) == 10
    for changes in (
        {"summary": "Changed summary"},
        {"url": "https://example.test/replacement"},
        {"author": "Another author"},
    ):
        with pytest.raises(AgentFailure, match="research_inconsistent_evidence"):
            state.add(items[0].model_copy(update=changes), ResearchFilters())


def test_eighth_tool_and_repeated_equivalent_call_admission() -> None:
    state = EvidenceState(ResearchRequest(operation="research", question="Compare"))
    for index in range(8):
        state.authorize(SearchCall(tool="search_news", arguments=SearchArguments(query=str(index))))
    assert len(state.history) == 8
    with pytest.raises(AgentFailure, match="research_tool_limit"):
        state.authorize(SourcesCall(tool="list_sources", arguments=SourcesArguments()))
    state = EvidenceState(ResearchRequest(operation="research", question="Compare"))
    call = SearchCall(tool="search_news", arguments=SearchArguments(query="same"))
    state.authorize(call)
    with pytest.raises(AgentFailure, match="research_repeated_tool"):
        state.authorize(call)


async def test_tool_failure_is_not_model_recollection_or_partial_success() -> None:
    item = detail()
    reader = ScriptedReader([ItemResult(found=True, item=item), AgentFailure("mcp_unavailable")])
    model = ScriptedModel([], None)
    request = ResearchRequest(operation="research", question="Compare", item_ids=(item.id, uuid4()))
    seen = []
    with pytest.raises(AgentFailure, match="mcp_unavailable"):
        async for update in ResearchController(reader, model).run(
            request, authorization(), ResearchStats()
        ):
            seen.append(update)
    assert all(isinstance(update, ResearchProgress) for update in seen)
    assert not model.contexts and reader.closed == 1


async def test_over_budget_planning_batch_executes_no_additional_tools() -> None:
    items = tuple(detail(str(index)) for index in range(5))
    reader = ScriptedReader([ItemResult(found=True, item=item) for item in items])
    model = ScriptedModel(
        [
            plan(
                *(
                    DetailCall(tool="get_news_item", arguments=DetailArguments(id=item.id))
                    for item in items[:4]
                )
            )
        ],
        None,
    )
    request = ResearchRequest(
        operation="research", question="Compare", item_ids=tuple(item.id for item in items)
    )
    with pytest.raises(AgentFailure, match="research_tool_limit"):
        _ = [
            update
            async for update in ResearchController(reader, model).run(
                request, authorization(), ResearchStats()
            )
        ]
    assert len(reader.connections[0].calls) == 5 and model.final_calls == 0


async def test_model_cannot_claim_absence_without_any_news_retrieval() -> None:
    reader, model = ScriptedReader([]), ScriptedModel([plan()], None)
    with pytest.raises(AgentFailure, match="research_no_retrieval"):
        _ = [
            update
            async for update in ResearchController(reader, model).run(
                ResearchRequest(operation="research", question="Any news?"),
                authorization(),
                ResearchStats(),
            )
        ]
    assert not reader.connections[0].calls and reader.closed == 1


@pytest.mark.parametrize("dependent", [False, True])
async def test_whole_plan_rejects_unknown_detail_before_dispatch(dependent: bool) -> None:
    item = detail()
    reader = ScriptedReader(
        [NewsResults(items=(metadata(item),)), ItemResult(found=True, item=item)]
    )
    model = ScriptedModel(
        [
            plan(
                RecentCall(tool="get_recent_news", arguments=RecentArguments()),
                DetailCall(
                    tool="get_news_item",
                    arguments=DetailArguments(id=item.id if dependent else uuid4()),
                ),
            ),
            plan(),
        ],
        answer((item,)),
    )
    with pytest.raises(AgentFailure, match="research_unknown_item"):
        _ = [
            update
            async for update in ResearchController(reader, model).run(
                ResearchRequest(operation="research", question="Discover and explain"),
                authorization(),
                ResearchStats(),
            )
        ]
    assert not reader.connections[0].calls and reader.closed == 1
    assert model.final_calls == 0


async def test_metadata_only_synthesis_is_rejected_before_another_planning_turn() -> None:
    item = detail()
    reader = ScriptedReader([NewsResults(items=(metadata(item),))])
    model = ScriptedModel(
        [
            plan(RecentCall(tool="get_recent_news", arguments=RecentArguments())),
            plan(),
        ],
        None,
    )
    stats = ResearchStats()
    with pytest.raises(AgentFailure, match="research_missing_detail"):
        _ = [
            update
            async for update in ResearchController(reader, model).run(
                ResearchRequest(operation="research", question="Explain matching news"),
                authorization(),
                stats,
            )
        ]
    assert stats.planning_calls == 2 and model.final_calls == 0
    assert len(reader.connections[0].calls) == 1 and reader.closed == 1


async def test_whole_plan_duplicate_is_rejected_before_dispatch() -> None:
    call = RecentCall(tool="get_recent_news", arguments=RecentArguments())
    reader = ScriptedReader([NewsResults(items=())])
    model = ScriptedModel([plan(call, call)], None)
    with pytest.raises(AgentFailure, match="research_repeated_tool"):
        _ = [
            update
            async for update in ResearchController(reader, model).run(
                ResearchRequest(operation="research", question="Any news?"),
                authorization(),
                ResearchStats(),
            )
        ]
    assert not reader.connections[0].calls and reader.closed == 1


async def test_whole_plan_filter_relaxation_does_not_execute_earlier_legal_call() -> None:
    request = ResearchRequest.model_validate(
        {"operation": "research", "question": "Filtered research", "filters": filters()}
    )
    reader = ScriptedReader([SourcesResult(sources=(), categories=())])
    model = ScriptedModel(
        [
            plan(
                SourcesCall(tool="list_sources", arguments=SourcesArguments()),
                SearchCall(tool="search_news", arguments=SearchArguments(query="change")),
            )
        ],
        None,
    )
    with pytest.raises(AgentFailure, match="research_filter_relaxation"):
        _ = [
            update
            async for update in ResearchController(reader, model).run(
                request, authorization(), ResearchStats()
            )
        ]
    assert not reader.connections[0].calls and reader.closed == 1
    assert model.scopes[0].tools == ("list_sources", "search_news")


async def test_source_listing_alone_cannot_authorize_no_match() -> None:
    reader = ScriptedReader([SourcesResult(sources=(), categories=())])
    model = ScriptedModel(
        [plan(SourcesCall(tool="list_sources", arguments=SourcesArguments())), plan()], None
    )
    with pytest.raises(AgentFailure, match="research_no_retrieval"):
        _ = [
            update
            async for update in ResearchController(reader, model).run(
                ResearchRequest(operation="research", question="Any news?"),
                authorization(),
                ResearchStats(),
            )
        ]
    assert model.scopes[1].can_synthesize is False
    assert reader.closed == 1 and model.final_calls == 0


def test_planning_scope_is_frozen_request_local_and_does_not_mutate_evidence() -> None:
    first, second = detail(), detail("Birch")
    state = EvidenceState(ResearchRequest(operation="research", question="Compare"))
    state.add(metadata(first), ResearchFilters())
    scope = state.planning_scope()
    state.add(metadata(second), ResearchFilters())
    assert scope.detail_ids == (first.id,) and state.planning_scope().detail_ids == (
        first.id,
        second.id,
    )
    with pytest.raises(ValidationError, match="frozen"):
        scope.__setattr__("can_synthesize", True)
    with pytest.raises(AgentFailure, match="research_unknown_item"):
        scope.validate_plan(
            plan(DetailCall(tool="get_news_item", arguments=DetailArguments(id=second.id)))
        )
    other = EvidenceState(ResearchRequest(operation="research", question="Another caller"))
    assert not other.planning_scope().detail_ids
    assert not state.history and not state.signatures
    assert str(first.id) not in repr(scope)


@pytest.mark.parametrize("has_details", [False, True])
def test_exhausted_tool_budget_never_widens_scope_or_allows_metadata_only_synthesis(
    has_details: bool,
) -> None:
    state = EvidenceState(ResearchRequest(operation="research", question="Compare"))
    item = detail()
    state.add(item if has_details else metadata(item), ResearchFilters())
    for index in range(8):
        state.authorize(SearchCall(tool="search_news", arguments=SearchArguments(query=str(index))))
    scope = state.planning_scope()
    assert not scope.tools and scope.remaining_tool_calls == 0
    assert scope.can_synthesize is has_details
    if has_details:
        scope.validate_plan(plan())
    else:
        with pytest.raises(AgentFailure, match="research_missing_detail"):
            scope.validate_plan(plan())
    with pytest.raises(AgentFailure, match="research_tool_limit"):
        scope.validate_plan(plan(SourcesCall(tool="list_sources", arguments=SourcesArguments())))


async def test_invalid_final_citations_emit_only_safe_progress() -> None:
    item = detail()
    reader = ScriptedReader([ItemResult(found=True, item=item)])
    model = ScriptedModel([plan()], answer((detail("Unseen"),), coverage="complete"))
    request = ResearchRequest(operation="research", question="Explain", item_ids=(item.id,))
    seen = []
    with pytest.raises(AgentFailure, match="research_citation_unknown"):
        async for update in ResearchController(reader, model).run(
            request, authorization(), ResearchStats()
        ):
            seen.append(update)
    assert seen and all(isinstance(update, ResearchProgress) for update in seen)
    assert reader.closed == 1


async def test_closing_during_validation_awaits_session_cleanup() -> None:
    item = detail()
    reader = ScriptedReader([ItemResult(found=True, item=item)])
    model = ScriptedModel([plan()], answer((item,), coverage="complete"))
    request = ResearchRequest(operation="research", question="Explain", item_ids=(item.id,))
    stream = ResearchController(reader, model).run(request, authorization(), ResearchStats())
    try:
        async for update in stream:
            assert isinstance(update, ResearchProgress)
            if update.phase == "validating":
                break
    finally:
        await stream.aclose()
    assert reader.closed == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/news",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "//example.test/news",
        "https://",
        "https://user:password@example.test/news",
        "https://user@example.test/news",
        "https://example.test/\nnews",
        "https://example.test/%0anews",
        "https://example.test/\u202enews",
        "https://example.test/news other",
        "https://example.test:invalid/news",
        "https://example.test/<script>",
    ],
)
def test_unsafe_stored_citation_urls_are_never_rendered(url: str) -> None:
    with pytest.raises(AgentFailure, match="research_citation_url_invalid"):
        safe_citation(url)


def test_safe_url_is_preserved_exactly_not_fetched_or_canonicalized() -> None:
    url = "https://Example.test:443/a%20b?q=one%20two#section"
    assert safe_citation(url) == url


def state_with_item() -> tuple[EvidenceState, NewsDetail]:
    item = detail()
    state = EvidenceState(
        ResearchRequest(operation="research", question="Explain the announcement")
    )
    state.add(item, ResearchFilters())
    return state, item


def test_unknown_or_metadata_only_citations_and_replacement_urls_fail() -> None:
    state, item = state_with_item()
    unknown = detail("Unknown")
    with pytest.raises(AgentFailure, match="research_citation_unknown"):
        render_answer(answer((unknown,)), state, state.details)
    with pytest.raises(AgentFailure, match="research_citation_unknown"):
        render_answer(answer((item,)), state, {})
    for text in (
        "Read https://untrusted.invalid",
        "[replacement](https://untrusted.invalid)",
        "www.untrusted.invalid",
    ):
        replaced = answer((item,)).model_copy(
            update={"claims": (ResearchClaim(text=text, evidence_ids=(item.id,)),)}
        )
        with pytest.raises(AgentFailure, match="research_model_url_refused"):
            render_answer(replaced, state, state.details)


def test_selection_coverage_and_missing_ids_must_match_actual_reads() -> None:
    item, missing = detail(), uuid4()
    state = EvidenceState(
        ResearchRequest(operation="research", question="Compare", item_ids=(item.id, missing))
    )
    state.add(item, ResearchFilters())
    state.missing.add(missing)
    valid = answer((item,), coverage="partial", missing=(missing,))
    assert str(missing) in render_answer(valid, state, state.details)
    for changes in ({"missing_item_ids": ()}, {"coverage": "complete"}):
        with pytest.raises(AgentFailure, match="research_coverage_invalid"):
            render_answer(valid.model_copy(update=changes), state, state.details)


@pytest.mark.parametrize("multibyte", [False, True])
@pytest.mark.parametrize("excess", [0, 1])
def test_exact_rendered_answer_byte_boundary(multibyte: bool, excess: int) -> None:
    state, item = state_with_item()
    baseline = answer((item,)).model_copy(
        update={"claims": (ResearchClaim(text="x", evidence_ids=(item.id,)),)}
    )
    overhead = len(render_answer(baseline, state, state.details).encode()) - 1
    available = MAX_ANSWER_BYTES - overhead + excess
    text = "\u00e9" * (available // 2) + "x" * (available % 2) if multibyte else "x" * available
    candidate = baseline.model_copy(
        update={"claims": (ResearchClaim(text=text, evidence_ids=(item.id,)),)}
    )
    if excess:
        with pytest.raises(AgentFailure, match="research_answer_limit"):
            render_answer(candidate, state, state.details)
    else:
        assert len(render_answer(candidate, state, state.details).encode()) == MAX_ANSWER_BYTES
