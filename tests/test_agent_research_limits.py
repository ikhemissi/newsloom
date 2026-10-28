import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from a2a.types import TaskState
from newsloom_agent.app import create_app
from newsloom_agent.generation import GenerationStats
from newsloom_agent.research import ResearchController
from newsloom_agent.research_generation import ResearchStats
from newsloom_agent.serving import TaskRegistry
from newsloom_mcp.models import (
    DetailInput,
    ItemResult,
    NewsDetail,
    NewsResults,
    RankedItem,
    RecentInput,
    SearchInput,
    SearchResults,
)
from test_agent_delegation import DelegationCase
from test_agent_delegation import delegated as delegated
from test_agent_privacy import Captured
from test_agent_privacy import captured as captured
from test_agent_research_serving import ResearchWire
from test_agent_research_serving import research_wire as research_wire
from test_agent_serving import loopback, until
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Endpoint
from test_mcp_http import endpoint as endpoint


async def test_four_near_limit_research_requests_with_one_final_stage_disconnect(
    delegated: DelegationCase,
    endpoint: Endpoint,
    research_wire: ResearchWire,
    captured: Captured,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = tuple(
        endpoint[1].item.model_copy(
            update={
                "id": uuid4(),
                "title": "Authored bounded evidence " + "t" * 256,
                "summary": "The stored release adds bounded retries. " + "x" * 2600,
                "url": f"https://example.com/authored-{index}",
            }
        )
        for index in range(10)
    )

    async def recent(args: RecentInput) -> NewsResults:
        assert args.limit == 5
        return NewsResults(items=items[:5])

    async def search(args: SearchInput, vector: tuple[float, ...] | None) -> SearchResults:
        assert args.limit == 5 and vector is not None
        return SearchResults(
            items=tuple(RankedItem(**item.model_dump(), similarity=0.8) for item in items[5:])
        )

    async def detail(args: DetailInput) -> ItemResult:
        item = next(item for item in items if item.id == args.id)
        return ItemResult(
            found=True,
            item=NewsDetail(
                **item.model_dump(),
                author="Authored author",
                date_origin="published",
                publisher_categories=(),
            ),
        )

    monkeypatch.setattr(endpoint[1], "recent", recent)
    monkeypatch.setattr(endpoint[1], "search", search)
    monkeypatch.setattr(endpoint[1], "detail", detail)
    research_wire.second_discovery = True
    research_wire.claim_text = "The stored release adds bounded retries."
    research_wire.padding = 124 * 1024
    research_wire.pause_final = True
    observations: list[ResearchStats] = []
    execute = captured.telemetry.execution

    def observe(outcome: str, category: str, elapsed: float, stats: GenerationStats) -> None:
        assert isinstance(stats, ResearchStats)
        observations.append(stats)
        execute(outcome, category, elapsed, stats)

    monkeypatch.setattr(captured.telemetry, "execution", observe)
    authorization, registry = await delegated.authorization(), TaskRegistry()
    async with (
        loopback(
            lambda base: create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=base + "/a2a",
                registry=registry,
                observer=captured.telemetry,
                research=ResearchController(delegated.adapter, research_wire.generator()),
            )
        ) as base,
        httpx.AsyncClient(
            base_url=base,
            trust_env=False,
            timeout=10,
            headers={
                "Authorization": "Bearer " + authorization.caller.assertion,
                "A2A-Version": "1.0",
            },
        ) as http,
    ):

        async def invoke() -> httpx.Response:
            return await http.post(
                "/a2a",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": str(uuid4()),
                            "role": "ROLE_USER",
                            "parts": [
                                {
                                    "data": {
                                        "operation": "research",
                                        "question": "q" * 8192,
                                        "preferences": {
                                            "language": "l" * 64,
                                            "audience": "a" * 256,
                                            "focus": "f" * 1024,
                                            "detail": "detailed",
                                        },
                                    }
                                }
                            ],
                        }
                    },
                },
            )

        sending = [asyncio.create_task(invoke()) for _ in range(4)]
        try:
            await until(
                lambda: len(research_wire.requests) == 16 or all(task.done() for task in sending)
            )
            assert len(research_wire.requests) == 16
            assert len(registry.records) == 4
            assert all(record.producer is not None for record in registry.records.values())
            sending[0].cancel()
            await asyncio.gather(sending[0], return_exceptions=True)
            await until(
                lambda: sum(record.producer is None for record in registry.records.values()) == 1
            )
            research_wire.final_release.set()
            replies = await asyncio.gather(*sending[1:])
            assert all(
                reply.json()["result"]["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
                for reply in replies
            )
        finally:
            research_wire.final_release.set()
            for task in sending:
                task.cancel()
            await asyncio.gather(*sending, return_exceptions=True)
        await until(lambda: all(record.producer is None for record in registry.records.values()))
        records = tuple(registry.records.values())
    async with httpx.AsyncClient(trust_env=False, timeout=1) as probe:
        with pytest.raises(httpx.ConnectError):
            await probe.get(base + "/health/live")
    assert (
        sum(record.task.status.state == TaskState.TASK_STATE_COMPLETED for record in records) == 3
    )
    assert sum(record.task.status.state == TaskState.TASK_STATE_CANCELED for record in records) == 1
    maximum_input = max(len(request.content) for request in research_wire.requests)
    assert 60 * 1024 <= maximum_input <= 64 * 1024
    assert len(observations) == 4
    assert all(stats.calls == 4 and stats.tool_calls == 7 for stats in observations)
    assert all(stats.input_bytes <= 256 * 1024 for stats in observations)
    complete = [stats for stats in observations if stats.usage_observed]
    assert len(complete) == 3
    assert all(496 * 1024 <= stats.response_bytes <= 512 * 1024 for stats in complete)
    assert all(client.is_closed for client in delegated.http_clients)
    assert all(transport.closed for transport in delegated.identity_transports)
    assert all(body.closed for body in research_wire.bodies)
    print(
        json.dumps(
            {
                "concurrent_requests": 4,
                "completed": 3,
                "cancelled": 1,
                "max_model_input_bytes": maximum_input,
                "max_aggregate_model_response_bytes": max(
                    stats.response_bytes for stats in complete
                ),
            }
        )
    )
