"""Web research: Web IQ client, planning budgets, separate web citations."""

import hashlib
import json
from uuid import UUID

import httpx
import pytest
from azure.core.credentials import AccessToken
from newsloom_agent import research_generation as generation
from newsloom_agent.models import AgentFailure
from newsloom_agent.research import EvidenceState, ResearchController, ResearchResult
from newsloom_agent.research_generation import ResearchStats
from newsloom_agent.research_models import (
    DetailArguments,
    DetailCall,
    ItemResult,
    PlanningScope,
    ResearchAnswer,
    ResearchRequest,
    SearchArguments,
    SearchCall,
    SearchResults,
    SynthesisScope,
    WebSearchArguments,
    WebSearchCall,
)
from newsloom_agent.web import ENDPOINT, Found, WebIq, WebUnavailable, parse
from test_agent_research import ScriptedModel, ScriptedReader, authorization, detail, metadata, plan

# Captured from the stored-news-only agent before web research existed.
GOLDEN = {
    "instructions": "7cc9a38fb3881452fd391abea90574e0c84e68885d9782a0d2e87c56628238bc",
    "planning": [
        "570fd429b0de78baff61048eb0cc1ccd0fea3bb87546ac972f7f22b1e6725aea",
        "b0430d90f32ece356b563ba849c8bc439f7560911889ef41aa599d7223858fd8",
        "a99b57c2c66df170b8967693b3cb0d43ab0b8591ca73e5f3081685ee05185297",
    ],
    "synthesis": [
        "aee7c5335a6c749fdedd8b1841bf92fdea5c1ab90ad630fdcfa512ad769d40c4",
        "340ae94120243c1067050d152245b541b01adce6078eb251a7f803236530f038",
    ],
}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def test_without_web_the_model_sees_exactly_the_stored_news_contract() -> None:
    # Updated deliberately on 2026-11-15 (no invented from/to dates); schemas stay pinned.
    assert hashlib.sha256(generation.INSTRUCTIONS.encode()).hexdigest() == GOLDEN["instructions"]
    scopes = [
        PlanningScope(
            tools=("list_sources", "get_recent_news", "search_news"),
            detail_ids=(),
            can_synthesize=False,
            remaining_tool_calls=8,
        ),
        PlanningScope(
            tools=("search_news", "get_news_item"),
            detail_ids=(UUID(int=1),),
            can_synthesize=True,
            remaining_tool_calls=5,
        ),
        PlanningScope(tools=(), detail_ids=(), can_synthesize=True, remaining_tool_calls=0),
    ]
    assert [digest(generation.planning_schema(s)) for s in scopes] == GOLDEN["planning"]
    synthesis = [
        SynthesisScope(coverage="discovery", missing_item_ids=()),
        SynthesisScope(coverage="partial", missing_item_ids=(UUID(int=2),)),
    ]
    assert [digest(generation.synthesis_schema(s)) for s in synthesis] == GOLDEN["synthesis"]
    context = json.loads(
        EvidenceState(ResearchRequest(operation="research", question="Q")).context(ResearchStats())
    )
    assert not {"web_results", "web_searches_remaining", "web_unavailable"} & set(context)


def test_with_web_the_schemas_offer_only_the_supplied_results() -> None:
    schema = generation.synthesis_schema(
        SynthesisScope(coverage="discovery", missing_item_ids=(), web_ids=("W1", "W2"))
    )
    definitions = schema["$defs"]  # type: ignore[index]
    stored = definitions["StoredClaim"]["properties"]
    web = definitions["WebClaim"]["properties"]
    assert stored["evidence_ids"]["minItems"] == 1 and web["web_ids"]["minItems"] == 1
    assert web["web_ids"]["items"]["enum"] == ["W1", "W2"]
    assert schema["properties"]["claims"]["items"] == {  # type: ignore[index]
        "anyOf": [{"$ref": "#/$defs/StoredClaim"}, {"$ref": "#/$defs/WebClaim"}]
    }
    plan_schema = generation.planning_schema(
        PlanningScope(
            tools=("search_news", "search_web"),
            detail_ids=(),
            can_synthesize=False,
            remaining_tool_calls=8,
        )
    )
    assert "WebSearchCall" in plan_schema["$defs"]  # type: ignore[index]
    assert "Public web results" in generation.WEB_INSTRUCTIONS
    assert generation.NO_WEB not in generation.WEB_INSTRUCTIONS


def web_row(n: int, **change: object) -> dict[str, object]:
    return {
        "title": f"Result {n}",
        "url": f"https://web.test/{n}",
        "content": f"Snippet {n} " * 200,
        "lastUpdatedAt": "2026-11-14T10:00:00Z",
        "isAdult": False,
        **change,
    }


def test_results_are_filtered_bounded_and_truncated() -> None:
    rows = [
        web_row(1, isAdult=True),
        web_row(2, url="http://web.test/2"),
        web_row(3, url="https://user:pw@web.test/3"),
        web_row(4, title=" "),
        *(web_row(n) for n in range(5, 12)),
    ]
    found = parse({"webResults": rows})
    assert [item.url for item in found] == [f"https://web.test/{n}" for n in range(5, 10)]
    assert all(len(item.snippet) <= 1000 and item.updated for item in found)
    invalid: object
    for invalid in ({}, {"webResults": "x"}, []):
        with pytest.raises(WebUnavailable):
            parse(invalid)


class Credential:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    async def get_token(self, *scopes: str, **_: object) -> AccessToken:
        self.scopes.extend(scopes)
        return AccessToken("web-token", 2**31)


async def test_web_iq_uses_the_managed_identity_and_reports_failures() -> None:
    credential = Credential()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"webResults": [web_row(1)]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        found = await WebIq(client, credential).search("agentcore pricing")  # type: ignore[arg-type]
    assert [item.title for item in found] == ["Result 1"]
    assert str(seen[0].url) == ENDPOINT and seen[0].headers["Authorization"] == "Bearer web-token"
    assert json.loads(seen[0].content) == {"query": "agentcore pricing"}
    assert credential.scopes == ["https://api.microsoft.ai/.default"]
    assert "x-apikey" not in seen[0].headers
    for response in (httpx.Response(401), httpx.Response(200, content=b"x" * (1024 * 1024 + 1))):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, r=response: r)
        ) as client:
            with pytest.raises(WebUnavailable):
                await WebIq(client, credential).search("q")  # type: ignore[arg-type]


class FakeWeb:
    def __init__(self, *results: tuple[Found, ...] | WebUnavailable) -> None:
        self.results, self.queries = list(results), list[str]()

    async def search(self, query: str) -> tuple[Found, ...]:
        self.queries.append(query)
        result = self.results.pop(0)
        if isinstance(result, WebUnavailable):
            raise result
        return result


def found(n: int) -> Found:
    return Found(f"Result {n}", f"https://web.test/{n}", f"Snippet {n}", None)


def web_answer(item_id: UUID, *, web: tuple[str, ...] = ("W1",)) -> ResearchAnswer:
    return ResearchAnswer.model_validate(
        {
            "outcome": "supported",
            "claims": [
                {"text": "Stored news reports the launch.", "evidence_ids": [str(item_id)]},
                {
                    "text": "The product page lists the new limits.",
                    "evidence_ids": [],
                    "web_ids": list(web),
                },
            ],
            "limitations": [],
            "missing_item_ids": [],
            "coverage": "discovery",
        }
    )


SEARCH = SearchCall(tool="search_news", arguments=SearchArguments(query="launch"))
WEB = WebSearchCall(tool="search_web", arguments=WebSearchArguments(query="product limits"))


async def run(model: ScriptedModel, reader: ScriptedReader, web: FakeWeb) -> ResearchResult:
    updates = [
        update
        async for update in ResearchController(reader, model, web).run(
            ResearchRequest(operation="research", question="What changed?"),
            authorization(),
            ResearchStats(),
        )
    ]
    result = updates[-1]
    assert isinstance(result, ResearchResult)
    return result


async def test_web_claims_are_rendered_separately_with_web_citations() -> None:
    item = detail()
    reader = ScriptedReader(
        [
            SearchResults.model_validate(
                {"items": [{**metadata(item).model_dump(), "similarity": 0.9}]}
            ),
            ItemResult(found=True, item=item),
        ]
    )
    model = ScriptedModel(
        [
            plan(SEARCH, WEB),
            plan(DetailCall(tool="get_news_item", arguments=DetailArguments(id=item.id))),
            plan(),
        ],
        web_answer(item.id),
    )
    web = FakeWeb((found(1), found(2)))
    result = await run(model, reader, web)
    lines = result.text.split("\n\n")
    assert lines[0].endswith("[1]") and lines[1] == "From the web:"
    assert lines[2] == "The product page lists the new limits. [W1]"
    assert "web search results; full articles were not accessed." in result.text
    assert lines[-2:] == [f"[1] {item.url}", "[W1] https://web.test/1"]
    assert web.queries == ["product limits"]
    context = json.loads(model.contexts[1])
    assert [r["id"] for r in context["web_results"]] == ["W1", "W2"]
    assert context["web_searches_remaining"] == 1


async def test_an_unreachable_web_leaves_a_stored_news_answer_with_a_limitation() -> None:
    item = detail()
    reader = ScriptedReader(
        [
            SearchResults.model_validate(
                {"items": [{**metadata(item).model_dump(), "similarity": 0.9}]}
            ),
            ItemResult(found=True, item=item),
        ]
    )
    stored_only = ResearchAnswer.model_validate(
        {
            "outcome": "supported",
            "claims": [{"text": "Stored news reports the launch.", "evidence_ids": [str(item.id)]}],
            "limitations": [],
            "missing_item_ids": [],
            "coverage": "discovery",
        }
    )
    model = ScriptedModel(
        [
            plan(SEARCH, WEB),
            plan(DetailCall(tool="get_news_item", arguments=DetailArguments(id=item.id))),
            plan(),
        ],
        stored_only,
    )
    result = await run(model, reader, FakeWeb(WebUnavailable("web_status_401")))
    assert "Limitation: The web could not be reached for this request." in result.text
    assert "full articles and web search were not accessed." in result.text
    assert "[W" not in result.text


def test_web_is_offered_only_in_discovery_mode_within_budget() -> None:
    discovery = EvidenceState(ResearchRequest(operation="research", question="Q"), web_enabled=True)
    assert "search_web" in discovery.planning_scope().tools
    discovery.authorize(WEB)
    discovery.web_searches = 1
    discovery.authorize(
        WebSearchCall(tool="search_web", arguments=WebSearchArguments(query="other"))
    )
    discovery.web_searches = 2
    assert "search_web" not in discovery.planning_scope().tools
    with pytest.raises(AgentFailure, match="research_web_not_offered"):
        discovery.authorize(
            WebSearchCall(tool="search_web", arguments=WebSearchArguments(query="third"))
        )
    selected = EvidenceState(
        ResearchRequest(operation="research", question="Q", item_ids=(UUID(int=7),)),
        web_enabled=True,
    )
    assert "search_web" not in selected.planning_scope().tools
    with pytest.raises(AgentFailure):
        selected.authorize(WEB)
    disabled = EvidenceState(ResearchRequest(operation="research", question="Q"))
    assert "search_web" not in disabled.planning_scope().tools
    with pytest.raises(AgentFailure, match="research_web_not_offered"):
        disabled.authorize(WEB)


def test_web_results_share_the_evidence_budget_and_unknown_web_ids_fail() -> None:
    state = EvidenceState(ResearchRequest(operation="research", question="Q"), web_enabled=True)
    state.accept_web(tuple(found(n) for n in range(1, 6)))
    state.accept_web(tuple(found(n) for n in range(6, 12)))
    assert len(state.web) == 10 and "search_web" not in state.planning_scope().tools
    scope = SynthesisScope(coverage="discovery", missing_item_ids=(), web_ids=("W1",))
    with pytest.raises(AgentFailure, match="research_web_citation_unknown"):
        scope.validate_answer(web_answer(UUID(int=3), web=("W2",)))
    with pytest.raises(ValueError):
        ResearchAnswer.model_validate(
            {
                "outcome": "supported",
                "claims": [{"text": "Unsupported.", "evidence_ids": []}],
                "limitations": [],
                "missing_item_ids": [],
                "coverage": "discovery",
            }
        )


async def test_a_web_only_follow_up_can_be_answered() -> None:
    answer = ResearchAnswer.model_validate(
        {
            "outcome": "supported",
            "claims": [
                {"text": "The limit was raised again.", "evidence_ids": [], "web_ids": ["W1"]}
            ],
            "limitations": [],
            "missing_item_ids": [],
            "coverage": "discovery",
        }
    )
    model = ScriptedModel([plan(WEB), plan()], answer)
    result = await run(model, ScriptedReader([]), FakeWeb((found(1),)))
    assert result.text.startswith("From the web:\n\nThe limit was raised again. [W1]")


async def test_without_any_retrieval_synthesis_is_still_refused() -> None:
    model = ScriptedModel([plan(WEB), plan()], None)
    with pytest.raises(AgentFailure, match="research_no_retrieval"):
        await run(model, ScriptedReader([]), FakeWeb(WebUnavailable("web_status_401")))
