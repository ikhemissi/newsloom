"""Application-owned evidence, constraints, budgets and validated research delivery."""

import asyncio
import json
import re
import unicodedata
from collections.abc import AsyncGenerator, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol
from urllib.parse import unquote, urlsplit
from uuid import UUID

import httpx2

from newsloom_agent.auth import Authorization
from newsloom_agent.delegation import ResearchToolResult, remaining
from newsloom_agent.models import AgentFailure, NewsMetadata
from newsloom_agent.research_generation import MAX_PLANNING_CALLS, ResearchModel, ResearchStats
from newsloom_agent.research_models import (
    MAX_ANSWER_BYTES,
    MAX_EVIDENCE_ITEMS,
    MAX_TOOL_CALLS,
    DetailArguments,
    DetailCall,
    ItemResult,
    NewsDetail,
    NewsResults,
    PlanningScope,
    RecentCall,
    ResearchAnswer,
    ResearchFilters,
    ResearchPlan,
    ResearchRequest,
    SearchCall,
    SearchResults,
    SourcesCall,
    SourcesResult,
    ToolCall,
    ToolName,
)


class ResearchConnection(Protocol):
    @property
    def authorization(self) -> Authorization: ...

    async def call(self, call: ToolCall) -> ResearchToolResult: ...


class ResearchReader(Protocol):
    def research(
        self, authorization: Authorization, selected_ids: tuple[UUID, ...] | None = None
    ) -> AbstractAsyncContextManager[ResearchConnection]: ...


@dataclass(frozen=True)
class ResearchProgress:
    phase: Literal["retrieving", "planning", "synthesizing", "validating"]
    tool_calls: int
    evidence_items: int


@dataclass(frozen=True, repr=False)
class ResearchResult:
    answer: ResearchAnswer
    text: str


def eligible(item: NewsMetadata, filters: ResearchFilters) -> bool:
    return (
        (filters.source is None or item.source == filters.source)
        and (filters.category is None or item.category == filters.category)
        and all(tag in item.tags for tag in filters.tags)
        and (filters.from_ is None or item.published_at >= filters.from_)
        and (filters.to is None or item.published_at < filters.to)
    )


@dataclass(repr=False)
class EvidenceState:
    request: ResearchRequest
    metadata: dict[UUID, NewsMetadata] = field(default_factory=dict)
    details: dict[UUID, NewsDetail] = field(default_factory=dict)
    missing: set[UUID] = field(default_factory=set)
    sources: SourcesResult | None = None
    history: list[ToolCall] = field(default_factory=list)
    signatures: set[str] = field(default_factory=set)
    retrievals: int = 0

    @property
    def missing_ids(self) -> tuple[UUID, ...]:
        return tuple(item for item in self.request.item_ids or () if item in self.missing)

    @property
    def coverage(self) -> Literal["complete", "partial", "none", "discovery"]:
        if self.request.item_ids is None:
            return "discovery"
        if not self.missing:
            return "complete"
        return "none" if len(self.missing) == len(self.request.item_ids) else "partial"

    def authorize(self, call: ToolCall) -> None:
        if not isinstance(call, DetailCall | RecentCall | SearchCall | SourcesCall):
            raise AgentFailure("research_tool_invalid")
        if len(self.history) >= MAX_TOOL_CALLS:
            raise AgentFailure("research_tool_limit")
        signature = call.model_dump_json(by_alias=True)
        if signature in self.signatures:
            raise AgentFailure("research_repeated_tool")
        if self.request.item_ids is not None and not isinstance(call, DetailCall):
            raise AgentFailure("research_selection_boundary")
        if isinstance(call, DetailCall):
            allowed = self.request.item_ids or tuple(self.metadata)
            if call.arguments.id not in allowed:
                raise AgentFailure("research_unknown_item")
        elif isinstance(call, RecentCall):
            filters = self.request.filters
            if (
                filters.source is not None
                or filters.category is not None
                or filters.tags
                or filters.to is not None
                or (
                    filters.from_ is not None
                    and (call.arguments.since is None or call.arguments.since < filters.from_)
                )
            ):
                raise AgentFailure("research_filter_relaxation")
        elif isinstance(call, SearchCall):
            caller, planned = self.request.filters, call.arguments
            if (
                (caller.source is not None and planned.source != caller.source)
                or (caller.category is not None and planned.category != caller.category)
                or not set(caller.tags).issubset(planned.tags)
                or (
                    caller.from_ is not None
                    and (planned.from_ is None or planned.from_ < caller.from_)
                )
                or (caller.to is not None and (planned.to is None or planned.to > caller.to))
            ):
                raise AgentFailure("research_filter_relaxation")
        self.signatures.add(signature)
        self.history.append(call)

    def planning_scope(self) -> PlanningScope:
        available = MAX_TOOL_CALLS - len(self.history)
        detail_ids = tuple(
            item_id
            for item_id in self.request.item_ids or tuple(self.metadata)
            if item_id not in self.details and item_id not in self.missing
        )
        tools: list[ToolName] = []
        if available:
            if self.request.item_ids is None:
                if self.sources is None:
                    tools.append("list_sources")
                filters = self.request.filters
                if (
                    filters.source is None
                    and filters.category is None
                    and not filters.tags
                    and filters.to is None
                ):
                    tools.append("get_recent_news")
                tools.append("search_news")
            if detail_ids:
                tools.append("get_news_item")
        return PlanningScope(
            tools=tuple(tools),
            detail_ids=detail_ids,
            can_synthesize=bool(self.details) or bool(self.retrievals and not self.metadata),
            remaining_tool_calls=available,
        )

    def validate_plan(self, plan: ResearchPlan, scope: PlanningScope) -> None:
        if plan.action == "synthesize" and not self.retrievals:
            raise AgentFailure("research_no_retrieval")
        scope.validate_plan(plan)
        for call in plan.calls:
            self.authorize(call)

    def add(self, item: NewsMetadata, filters: ResearchFilters) -> None:
        if not eligible(item, filters) or not eligible(item, self.request.filters):
            raise AgentFailure("research_filter_violation")
        metadata = NewsMetadata.model_validate(
            item.model_dump(include=set(NewsMetadata.model_fields))
        )
        if item.id in self.missing:
            raise AgentFailure("research_inconsistent_evidence")
        previous = self.metadata.get(item.id)
        if previous is not None and previous != metadata:
            raise AgentFailure("research_inconsistent_evidence")
        if previous is None and len(self.metadata) >= MAX_EVIDENCE_ITEMS:
            raise AgentFailure("research_evidence_limit")
        self.metadata[item.id] = metadata
        if isinstance(item, NewsDetail):
            if item.id in self.details and self.details[item.id] != item:
                raise AgentFailure("research_inconsistent_evidence")
            self.details[item.id] = item

    def accept(self, call: ToolCall, result: ResearchToolResult) -> None:
        if isinstance(call, SourcesCall) and isinstance(result, SourcesResult):
            self.sources = result
            return
        self.retrievals += 1
        if isinstance(call, DetailCall) and isinstance(result, ItemResult):
            if result.item is None:
                if call.arguments.id in self.metadata:
                    raise AgentFailure("research_inconsistent_evidence")
                self.missing.add(call.arguments.id)
            elif result.item.id != call.arguments.id:
                raise AgentFailure("mcp_response_item_mismatch")
            else:
                self.add(result.item, self.request.filters)
        elif isinstance(call, RecentCall) and isinstance(result, NewsResults):
            if len(result.items) > call.arguments.limit:
                raise AgentFailure("mcp_response_item_limit")
            for item in result.items:
                if call.arguments.since is not None and item.published_at < call.arguments.since:
                    raise AgentFailure("research_filter_violation")
                self.add(item, self.request.filters)
        elif isinstance(call, SearchCall) and isinstance(result, SearchResults):
            if len(result.items) > call.arguments.limit:
                raise AgentFailure("mcp_response_item_limit")
            for item in result.items:
                self.add(item, call.arguments)
        else:
            raise AgentFailure("mcp_response_invalid")

    def context(self, stats: ResearchStats) -> str:
        return json.dumps(
            {
                "request": self.request.model_dump(mode="json", by_alias=True),
                "metadata": [item.model_dump(mode="json") for item in self.metadata.values()],
                "detail_evidence": [item.model_dump(mode="json") for item in self.details.values()],
                "sources": self.sources.model_dump(mode="json")
                if self.sources is not None
                else None,
                "completed_calls": [
                    call.model_dump(mode="json", by_alias=True) for call in self.history
                ],
                "missing_item_ids": [str(item) for item in self.missing_ids],
                "coverage": self.coverage,
                "remaining_tool_calls": MAX_TOOL_CALLS - len(self.history),
                "remaining_planning_calls": MAX_PLANNING_CALLS - stats.planning_calls,
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )


def safe_citation(value: str) -> str:
    try:
        decoded = unquote(value, errors="strict")
        if (
            any(char.isspace() for char in value)
            or any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in decoded)
            or any(char in value for char in '\\<>"')
        ):
            raise AgentFailure("research_citation_url_invalid")
        parsed, url = urlsplit(value), httpx2.URL(value)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.netloc
            or not url.host
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise AgentFailure("research_citation_url_invalid")
        _ = parsed.port
    except ValueError, UnicodeError, httpx2.InvalidURL:
        raise AgentFailure("research_citation_url_invalid") from None
    return value


def plain_statement(value: str) -> None:
    if re.search(r"(?i)\b[a-z][a-z0-9+.-]*://|\bwww\.|\]\s*\(", value):
        raise AgentFailure("research_model_url_refused")
    if any(unicodedata.category(char) in {"Cf", "Cs"} for char in value):
        raise AgentFailure("research_answer_invalid")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise AgentFailure("research_answer_invalid")


def render_answer(
    answer: ResearchAnswer,
    state: EvidenceState,
    evidence: Mapping[UUID, NewsDetail],
) -> str:
    if set(answer.missing_item_ids) != set(state.missing_ids) or answer.coverage != state.coverage:
        raise AgentFailure("research_coverage_invalid")
    references: dict[UUID, int] = {}
    lines: list[str] = []
    for claim in answer.claims:
        plain_statement(claim.text)
        markers = []
        for item_id in claim.evidence_ids:
            if item_id not in evidence:
                raise AgentFailure("research_citation_unknown")
            if state.request.item_ids is not None and item_id not in state.request.item_ids:
                raise AgentFailure("research_selection_boundary")
            safe_citation(evidence[item_id].url)
            number = references.setdefault(item_id, len(references) + 1)
            markers.append(f"[{number}]")
        lines.append(claim.text + " " + " ".join(markers))
    for limitation in answer.limitations:
        plain_statement(limitation)
        lines.append("Limitation: " + limitation)
    if state.request.item_ids is not None:
        lines.append("Selection retrieval coverage: " + answer.coverage + ".")
    if state.missing_ids:
        lines.append("Missing selected items: " + ", ".join(map(str, state.missing_ids)) + ".")
    lines.append(
        "Evidence is limited to stored summaries and metadata; "
        "full articles and web search were not accessed."
    )
    for item_id, number in references.items():
        lines.append(f"[{number}] {evidence[item_id].url}")
    text = "\n\n".join(lines)
    if len(text.encode()) > MAX_ANSWER_BYTES:
        raise AgentFailure("research_answer_limit")
    return text


class ResearchController:
    def __init__(self, reader: ResearchReader, model: ResearchModel) -> None:
        self.reader, self.model = reader, model

    async def run(
        self, request: ResearchRequest, authorization: Authorization, stats: ResearchStats
    ) -> AsyncGenerator[ResearchProgress | ResearchResult]:
        state = EvidenceState(request)

        def progress(
            phase: Literal["retrieving", "planning", "synthesizing", "validating"],
        ) -> ResearchProgress:
            return ResearchProgress(phase, len(state.history), len(state.details))

        remaining(authorization)
        yield progress("retrieving")
        try:
            async with (
                asyncio.timeout_at(authorization.deadline),
                self.reader.research(authorization, request.item_ids) as connection,
            ):
                delegated = connection.authorization

                async def invoke(call: ToolCall) -> None:
                    remaining(delegated)
                    state.authorize(call)
                    stats.tool_calls = len(state.history)
                    result = await connection.call(call)
                    remaining(delegated)
                    state.accept(call, result)

                for item_id in request.item_ids or ():
                    await invoke(
                        DetailCall(tool="get_news_item", arguments=DetailArguments(id=item_id))
                    )
                if not request.item_ids or state.metadata:
                    for _ in range(MAX_PLANNING_CALLS):
                        planned = replace(
                            state,
                            metadata=dict(state.metadata),
                            details=dict(state.details),
                            missing=set(state.missing),
                            history=list(state.history),
                            signatures=set(state.signatures),
                        )
                        scope = planned.planning_scope()
                        yield progress("planning")
                        plan = await self.model.plan(
                            state.context(stats), delegated, stats, scope=scope
                        )
                        remaining(delegated)
                        planned.validate_plan(plan, scope)
                        if plan.action == "synthesize":
                            break
                        for call in plan.calls:
                            yield progress("retrieving")
                            await invoke(call)
                if not state.retrievals:
                    raise AgentFailure("research_no_retrieval")
                if not state.metadata:
                    answer = ResearchAnswer(
                        outcome="no_match",
                        claims=(),
                        limitations=("No matching stored news is available for this request.",),
                        missing_item_ids=state.missing_ids,
                        coverage=state.coverage,
                    )
                else:
                    if not state.details:
                        raise AgentFailure("research_missing_detail")
                    yield progress("synthesizing")
                    answer = await self.model.synthesize(state.context(stats), delegated, stats)
                remaining(delegated)
                yield progress("validating")
                await asyncio.sleep(0)
                text = render_answer(answer, state, state.details)
                remaining(delegated)
                await asyncio.sleep(0)
                yield ResearchResult(answer, text)
        except TimeoutError:
            raise AgentFailure("request_timeout") from None
