import asyncio
import time
from uuid import uuid4

import pytest
from mcp.types import CallToolResult, TextContent
from newsloom_agent.delegation import (
    MAX_RESEARCH_RESPONSE_BYTES,
    McpResponseBudget,
)
from newsloom_agent.models import AgentFailure
from newsloom_agent.research_models import (
    DetailArguments,
    DetailCall,
    ItemResult,
    NewsResults,
    RecentArguments,
    RecentCall,
    SearchArguments,
    SearchCall,
    SearchResults,
    SourcesArguments,
    SourcesCall,
    SourcesResult,
)
from test_agent_delegation import DelegationCase
from test_agent_delegation import delegated as delegated
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Endpoint
from test_mcp_http import endpoint as endpoint


async def test_four_actual_sdk_tools_reuse_one_validated_user_session(
    delegated: DelegationCase, endpoint: Endpoint, capsys: pytest.CaptureFixture[str]
) -> None:
    authorization = await delegated.authorization()
    async with delegated.adapter.research(authorization) as connection:
        sources = await connection.call(
            SourcesCall(tool="list_sources", arguments=SourcesArguments())
        )
        assert isinstance(sources, SourcesResult)
        recent = await connection.call(
            RecentCall(tool="get_recent_news", arguments=RecentArguments(limit=5))
        )
        assert isinstance(recent, NewsResults)
        detail = await connection.call(
            DetailCall(tool="get_news_item", arguments=DetailArguments(id=recent.items[0].id))
        )
        assert isinstance(detail, ItemResult) and detail.found
        search = await connection.call(
            SearchCall(tool="search_news", arguments=SearchArguments(query="authored query"))
        )
        assert isinstance(search, SearchResults) and search.items[0].similarity == 0.8
        assert connection.calls == 4 and connection.response_budget.received > 0
        assert connection.authorization.deadline <= authorization.deadline
    assert connection.closed
    assert len(delegated.forms) == len(delegated.http_clients) == 1
    assert delegated.mcp_methods.count("initialize") == 1
    assert delegated.mcp_methods.count("tools/call") == 4
    assert set(delegated.mcp_authorizations) == {
        "Bearer " + delegated.issued[authorization.caller.assertion]
    }
    assert endpoint[2].calls == ["authored query"]
    assert len(endpoint[1].calls) == 4
    with pytest.raises(AgentFailure, match="mcp_session_closed"):
        await connection.call(SourcesCall(tool="list_sources", arguments=SourcesArguments()))
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err


async def test_selected_or_discovered_ids_are_the_only_admitted_detail_reads(
    delegated: DelegationCase, endpoint: Endpoint
) -> None:
    authorization = await delegated.authorization()
    selected = endpoint[1].item.id
    async with delegated.adapter.research(authorization, (selected,)) as connection:
        with pytest.raises(AgentFailure, match="research_unknown_item"):
            await connection.call(
                DetailCall(tool="get_news_item", arguments=DetailArguments(id=uuid4()))
            )
        with pytest.raises(AgentFailure, match="research_selection_boundary"):
            await connection.call(RecentCall(tool="get_recent_news", arguments=RecentArguments()))
        found = await connection.call(
            DetailCall(tool="get_news_item", arguments=DetailArguments(id=selected))
        )
        assert isinstance(found, ItemResult) and found.found
        assert connection.calls == 1
    async with delegated.adapter.research(await delegated.authorization()) as discovery:
        with pytest.raises(AgentFailure, match="research_unknown_item"):
            await discovery.call(
                DetailCall(tool="get_news_item", arguments=DetailArguments(id=selected))
            )
        results = await discovery.call(SearchCall(tool="search_news", arguments=SearchArguments()))
        assert isinstance(results, SearchResults) and results.items[0].id == selected
        assert isinstance(
            await discovery.call(
                DetailCall(tool="get_news_item", arguments=DetailArguments(id=selected))
            ),
            ItemResult,
        )


async def test_explicit_not_found_is_not_a_failed_or_replaced_selection(
    delegated: DelegationCase,
) -> None:
    selected = uuid4()
    delegated.mcp_result = CallToolResult(
        content=[], structured_content={"found": False, "item": None}
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    async with delegated.adapter.research(await delegated.authorization(), (selected,)) as session:
        result = await session.call(
            DetailCall(tool="get_news_item", arguments=DetailArguments(id=selected))
        )
        assert isinstance(result, ItemResult) and not result.found and result.item is None
        assert session.calls == 1
    assert delegated.mcp_methods.count("tools/call") == 1


@pytest.mark.parametrize(
    ("structured", "is_error", "category"),
    [
        (None, False, "mcp_response_invalid"),
        ({}, False, "mcp_response_invalid"),
        ({"sources": [], "categories": [], "endpoint": "x"}, False, "mcp_response_invalid"),
        ({"sources": [], "categories": []}, True, "mcp_tool_failure"),
    ],
)
async def test_invalid_or_failed_result_never_becomes_an_empty_success(
    delegated: DelegationCase,
    structured: dict[str, object] | None,
    is_error: bool,
    category: str,
) -> None:
    delegated.mcp_result = CallToolResult(
        content=[TextContent(type="text", text="RESEARCH_RESULT_ERROR_CANARY")],
        structured_content=structured,
        is_error=is_error,
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    with pytest.raises(AgentFailure, match=f"^{category}$"):
        async with delegated.adapter.research(await delegated.authorization()) as connection:
            await connection.call(SourcesCall(tool="list_sources", arguments=SourcesArguments()))
    assert delegated.mcp_methods.count("tools/call") == 1


@pytest.mark.parametrize(
    ("changes", "category"),
    [
        ({"oid": str(uuid4())}, "user_preservation_failed"),
        ({"tid": str(uuid4())}, "downstream_token_invalid"),
        ({"aud": str(uuid4())}, "downstream_token_invalid"),
        ({"azp": str(uuid4())}, "downstream_permission_invalid"),
        ({"scp": "news.agent"}, "downstream_permission_invalid"),
        ({"scp": "news.read extra.read"}, "downstream_permission_invalid"),
        ({"exp": 1}, "downstream_token_invalid"),
        ({"idtyp": "app"}, "downstream_token_invalid"),
    ],
)
async def test_wrong_user_permission_or_expired_downstream_stops_before_mcp(
    delegated: DelegationCase, changes: dict[str, object], category: str
) -> None:
    authorization = await delegated.authorization(downstream=changes)
    with pytest.raises(AgentFailure, match=f"^{category}$"):
        async with delegated.adapter.research(authorization):
            pytest.fail("invalid identity entered a research session")
    assert not delegated.http_clients and not delegated.mcp_methods


async def test_overlapping_research_requests_never_share_sessions_or_discovery(
    delegated: DelegationCase, endpoint: Endpoint
) -> None:
    first, second = await asyncio.gather(delegated.authorization(), delegated.authorization())
    async with (
        delegated.adapter.research(first) as one,
        delegated.adapter.research(second) as two,
    ):
        await one.call(RecentCall(tool="get_recent_news", arguments=RecentArguments()))
        assert endpoint[1].item.id in one.known_ids and not two.known_ids
        assert one.session is not two.session
        with pytest.raises(AgentFailure, match="research_unknown_item"):
            await two.call(
                DetailCall(tool="get_news_item", arguments=DetailArguments(id=endpoint[1].item.id))
            )
        await two.call(SourcesCall(tool="list_sources", arguments=SourcesArguments()))
    assert len(delegated.forms) == len(delegated.http_clients) == 2
    assert set(delegated.mcp_authorizations) == {
        "Bearer " + delegated.issued[value.caller.assertion] for value in (first, second)
    }


@pytest.mark.parametrize("stage", ["exchange", "mcp", "between_calls"])
async def test_cancellation_closes_one_request_owned_session_and_credential(
    delegated: DelegationCase, stage: str
) -> None:
    authorization = await delegated.authorization()
    entered, release = asyncio.Event(), asyncio.Event()
    if stage != "between_calls":
        entered = delegated.exchange_entered if stage == "exchange" else delegated.mcp_entered
        release = delegated.exchange_release if stage == "exchange" else delegated.mcp_release
        release.clear()

    async def work() -> None:
        async with delegated.adapter.research(authorization) as connection:
            await connection.call(SourcesCall(tool="list_sources", arguments=SourcesArguments()))
            entered.set()
            await release.wait()

    task = asyncio.create_task(work())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert all(client.is_closed for client in delegated.http_clients)
        assert all(transport.closed for transport in delegated.identity_transports)
        assert not delegated.workload.closed
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("stage", ["exchange", "mcp", "between_calls"])
async def test_all_research_stages_keep_the_original_deadline(
    delegated: DelegationCase, stage: str
) -> None:
    authorization = await delegated.authorization(seconds=0.1)
    release = asyncio.Event()
    if stage == "exchange":
        delegated.exchange_release.clear()
    if stage == "mcp":
        delegated.mcp_release.clear()
    started = time.monotonic()
    try:
        with pytest.raises(AgentFailure, match="request_timeout"):
            async with delegated.adapter.research(authorization) as connection:
                await connection.call(
                    SourcesCall(tool="list_sources", arguments=SourcesArguments())
                )
                await release.wait()
        assert time.monotonic() - started < 1
        assert all(client.is_closed for client in delegated.http_clients)
        assert all(transport.closed for transport in delegated.identity_transports)
    finally:
        delegated.exchange_release.set()
        delegated.mcp_release.set()
        release.set()


async def test_exchanged_token_expiry_bounds_the_entire_multi_call_session(
    delegated: DelegationCase,
) -> None:
    authorization = await delegated.authorization()
    delegated.exchange_payload = {
        "access_token": delegated.issued[authorization.caller.assertion],
        "expires_in": 2,
    }
    started = time.monotonic()
    with pytest.raises(AgentFailure, match="request_timeout"):
        async with delegated.adapter.research(authorization) as connection:
            assert connection.authorization.deadline < authorization.deadline
            await connection.call(SourcesCall(tool="list_sources", arguments=SourcesArguments()))
            await asyncio.sleep(3)
    assert time.monotonic() - started < 2.5
    assert all(client.is_closed for client in delegated.http_clients)


async def test_repeated_calls_and_ninth_operation_are_refused_before_execution(
    delegated: DelegationCase,
) -> None:
    async with delegated.adapter.research(await delegated.authorization()) as connection:
        await connection.call(SourcesCall(tool="list_sources", arguments=SourcesArguments()))
        with pytest.raises(AgentFailure, match="research_repeated_tool"):
            await connection.call(SourcesCall(tool="list_sources", arguments=SourcesArguments()))
        for index in range(7):
            await connection.call(
                SearchCall(tool="search_news", arguments=SearchArguments(query=f"authored {index}"))
            )
        assert connection.calls == 8
        with pytest.raises(AgentFailure, match="research_tool_limit"):
            await connection.call(
                SearchCall(tool="search_news", arguments=SearchArguments(query="ninth"))
            )
    assert delegated.mcp_methods.count("tools/call") == 8


def test_aggregate_response_byte_boundary_does_not_reset_per_operation() -> None:
    budget = McpResponseBudget()
    budget.consume(MAX_RESEARCH_RESPONSE_BYTES // 2)
    budget.consume(MAX_RESEARCH_RESPONSE_BYTES // 2)
    assert budget.received == MAX_RESEARCH_RESPONSE_BYTES
    with pytest.raises(AgentFailure, match="mcp_aggregate_response_limit"):
        budget.consume(1)
    with pytest.raises(AgentFailure, match="mcp_aggregate_response_limit"):
        budget.consume(-1)


async def test_real_transport_response_accounting_is_aggregate_across_calls(
    delegated: DelegationCase,
) -> None:
    delegated.response_padding = 96 * 1024
    with pytest.raises(AgentFailure, match="mcp_aggregate_response_limit"):
        async with delegated.adapter.research(await delegated.authorization()) as connection:
            for index in range(8):
                await connection.call(
                    SearchCall(
                        tool="search_news", arguments=SearchArguments(query=f"authored {index}")
                    )
                )
    assert 1 <= delegated.mcp_methods.count("tools/call") < 8
    assert all(client.is_closed for client in delegated.http_clients)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_research_http_denials_close_without_a_fallback(
    delegated: DelegationCase, status: int
) -> None:
    delegated.mcp_status = status
    category = "mcp_access_denied" if status in (401, 403) else "mcp_unavailable"
    with pytest.raises(AgentFailure, match=category):
        async with delegated.adapter.research(await delegated.authorization()):
            pytest.fail("denied initialization entered a session")
    assert delegated.mcp_methods == ["initialize"]
    assert all(client.is_closed for client in delegated.http_clients)


async def test_another_records_detail_cannot_replace_the_selected_id(
    delegated: DelegationCase, endpoint: Endpoint
) -> None:
    selected = uuid4()
    with pytest.raises(AgentFailure, match="mcp_response_item_mismatch"):
        async with delegated.adapter.research(
            await delegated.authorization(), (selected,)
        ) as connection:
            await connection.call(
                DetailCall(tool="get_news_item", arguments=DetailArguments(id=selected))
            )
    assert endpoint[1].item.id != selected
