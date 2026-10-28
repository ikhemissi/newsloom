import asyncio
import io
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
import httpx2
import pytest
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import GetTaskRequest, Message, Part, Role, SendMessageRequest, TaskState
from google.protobuf.json_format import Parse
from google.protobuf.struct_pb2 import Value
from newsloom_agent import cli
from newsloom_agent import client as acceptance
from newsloom_agent.app import create_app
from newsloom_agent.client import ClientSettings
from newsloom_agent.research import ResearchController
from newsloom_agent.research_models import ResearchReceipt, ResearchRequest
from newsloom_agent.serving import TaskRegistry
from test_agent_delegation import BodyStream, DelegationCase
from test_agent_delegation import delegated as delegated
from test_agent_research_generation import StructuredModel, completion
from test_agent_serving import loopback
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Endpoint
from test_mcp_http import endpoint as endpoint


@dataclass(repr=False)
class ResearchWire(StructuredModel):
    search: bool = False
    second_discovery: bool = False
    claim_text: str | None = None
    unknown_citation: bool = False
    pause_final: bool = False
    final_entered: asyncio.Event = field(default_factory=asyncio.Event)
    final_release: asyncio.Event = field(default_factory=asyncio.Event)
    plan_override: dict[str, object] | None = None

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://owned.services.ai.azure.com/openai/v1/chat/completions"
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer " + self.credential.token.token
        self.requests.append(request)
        self.entered.set()
        await self.release.wait()
        if self.status != 200:
            body = BodyStream(b'{"error":{"message":"RESEARCH_PROVIDER_ERROR_CANARY"}}')
            self.bodies.append(body)
            return httpx2.Response(
                self.status, headers={"Content-Type": "application/json"}, stream=body
            )
        payload = json.loads(request.content)
        context = json.loads(payload["messages"][1]["content"])
        kind = payload["response_format"]["json_schema"]["name"]
        details = context["detail_evidence"]
        result: dict[str, object]
        if kind == "research_plan":
            history = context["completed_calls"]
            if self.plan_override is not None:
                result = self.plan_override
            elif context["request"]["item_ids"] is not None:
                result = {"action": "synthesize", "calls": []}
            elif not history:
                tool = "search_news" if self.search else "get_recent_news"
                result = {
                    "action": "tools",
                    "calls": [
                        {
                            "tool": tool,
                            "arguments": {"query": "authored query"}
                            if self.search
                            else {"limit": 5},
                        }
                    ],
                }
            elif self.second_discovery and len(history) == 1:
                result = {
                    "action": "tools",
                    "calls": [
                        {
                            "tool": "search_news",
                            "arguments": {"query": "authored second discovery", "limit": 5},
                        }
                    ],
                }
            elif context["metadata"] and not details:
                result = {
                    "action": "tools",
                    "calls": [
                        {"tool": "get_news_item", "arguments": {"id": item["id"]}}
                        for item in context["metadata"][:5]
                    ],
                }
            else:
                result = {"action": "synthesize", "calls": []}
        else:
            assert kind == "research_answer"
            self.final_entered.set()
            if self.pause_final:
                await self.final_release.wait()
            result = {
                "outcome": "limited" if context["missing_item_ids"] else "supported",
                "claims": [
                    {
                        "text": self.claim_text if self.claim_text is not None else item["summary"],
                        "evidence_ids": [str(uuid4()) if self.unknown_citation else item["id"]],
                    }
                    for item in details
                ],
                "limitations": ["One selected record is missing."]
                if context["missing_item_ids"]
                else [],
                "missing_item_ids": context["missing_item_ids"],
                "coverage": context["coverage"],
            }
        body = BodyStream(json.dumps(completion(json.dumps(result))).encode() + b" " * self.padding)
        self.bodies.append(body)
        return httpx2.Response(200, headers={"Content-Type": "application/json"}, stream=body)


@pytest.fixture
def research_wire() -> ResearchWire:
    wire = ResearchWire()
    wire.release.set()
    return wire


def request(item: str | None = None) -> ResearchRequest:
    return ResearchRequest.model_validate(
        {
            "operation": "research",
            "question": "AUTHORED_RESEARCH_QUESTION_CANARY",
            **({"item_ids": [item]} if item else {}),
        }
    )


def message(request: ResearchRequest) -> Message:
    return Message(
        message_id=str(uuid4()),
        role=Role.ROLE_USER,
        parts=[
            Part(
                data=Parse(request.model_dump_json(by_alias=True), Value()),
                media_type="application/json",
            )
        ],
    )


@pytest.mark.parametrize("selected", [False, True])
async def test_real_loopback_official_client_progress_validated_artifacts_and_readback(
    delegated: DelegationCase,
    endpoint: Endpoint,
    research_wire: ResearchWire,
    selected: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authorization, registry = await delegated.authorization(), TaskRegistry()
    controller = ResearchController(delegated.adapter, research_wire.generator())
    async with (
        loopback(
            lambda base: create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=base + "/a2a",
                registry=registry,
                research=controller,
            )
        ) as base,
        httpx.AsyncClient(
            base_url=base,
            trust_env=False,
            headers={
                "Authorization": "Bearer " + authorization.caller.assertion,
                "A2A-Version": "1.0",
            },
        ) as http,
    ):
        async with httpx.AsyncClient(trust_env=False) as public:
            card = await A2ACardResolver(public, base).get_agent_card()
        assert [skill.id for skill in card.skills] == ["recent-news", "research"]
        assert list(card.default_input_modes) == ["text/plain", "application/json"]
        assert card.capabilities.streaming
        client = ClientFactory(
            ClientConfig(streaming=True, httpx_client=http, supported_protocol_bindings=["JSONRPC"])
        ).create(card)
        try:
            received = [
                event
                async for event in client.send_message(
                    SendMessageRequest(
                        message=message(request(str(endpoint[1].item.id) if selected else None))
                    )
                )
            ]
            artifacts = [event for event in received if event.HasField("artifact_update")]
            progress = [
                event
                for event in received
                if event.HasField("status_update")
                and event.status_update.status.state == TaskState.TASK_STATE_WORKING
                and event.status_update.status.message.parts
            ]
            assert artifacts and progress
            assert received.index(progress[0]) < received.index(artifacts[0])
            for event in progress:
                value = json.loads(event.status_update.status.message.parts[0].text)
                assert set(value) == {"phase", "tool_calls", "evidence_items"}
                assert "CANARY" not in json.dumps(value)
            text = "".join(event.artifact_update.artifact.parts[0].text for event in artifacts)
            task = await client.get_task(GetTaskRequest(id=received[-1].task.id, history_length=2))
            assert task.status.state == TaskState.TASK_STATE_COMPLETED
            assert task.artifacts[0].parts[0].text == text and endpoint[1].item.url in text
            receipt = ResearchReceipt.model_validate_json(task.status.message.parts[0].text)
            assert receipt.validated and receipt.user_preserved
            assert receipt.generation_calls == (2 if selected else 4)
            assert receipt.tool_calls == (1 if selected else 2)
        finally:
            await client.close()
    assert len(delegated.forms) == 1 and len(delegated.http_clients) == 1
    assert all(body.closed for body in research_wire.bodies)
    assert all(client.is_closed for client in delegated.http_clients)
    assert "CANARY" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "parts",
    [
        [{"data": {"operation": "research", "question": "x"}}],
        [{"data": {"operation": "research", "question": "x", "extra": True}}],
        [{"data": {"operation": "research", "question": " "}}],
        [{"data": {"operation": "research", "question": "x", "item_ids": []}}],
        [{"data": {"operation": "research", "question": "x", "preferences": {"memory": True}}}],
        [{"data": {"operation": "research", "question": "x", "filters": {"from": "2026-10-27"}}}],
        [{"data": {"operation": "research", "question": "x" * 8193}}],
        [{"data": ["research"]}],
        [{"data": True}],
        [{"data": {"operation": "research", "question": "x"}}, {"text": "extra"}],
    ],
)
async def test_disabled_or_malformed_requests_do_zero_model_and_mcp_work(
    delegated: DelegationCase, research_wire: ResearchWire, parts: list[dict[str, object]]
) -> None:
    authorization, registry = await delegated.authorization(), TaskRegistry()
    disabled = len(parts) == 1 and parts[0] == {"data": {"operation": "research", "question": "x"}}
    controller = (
        None if disabled else ResearchController(delegated.adapter, research_wire.generator())
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url="https://agent.test/a2a",
                registry=registry,
                research=controller,
            )
        ),
        base_url="https://agent.test",
        headers={"Authorization": "Bearer " + authorization.caller.assertion, "A2A-Version": "1.0"},
    ) as http:
        response = await http.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "SendMessage",
                "params": {
                    "message": {"messageId": str(uuid4()), "role": "ROLE_USER", "parts": parts}
                },
            },
        )
        assert "error" in response.json()
    assert not registry.records and not research_wire.requests and not delegated.forms


async def test_invalid_citation_fails_without_exposing_draft_artifacts(
    delegated: DelegationCase, endpoint: Endpoint, research_wire: ResearchWire
) -> None:
    research_wire.unknown_citation = True
    authorization, registry = await delegated.authorization(), TaskRegistry()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url="https://agent.test/a2a",
                registry=registry,
                research=ResearchController(delegated.adapter, research_wire.generator()),
            )
        ),
        base_url="https://agent.test",
        headers={"Authorization": "Bearer " + authorization.caller.assertion, "A2A-Version": "1.0"},
    ) as http:
        result = await http.post(
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
                                "data": request(str(endpoint[1].item.id)).model_dump(
                                    mode="json", by_alias=True
                                )
                            }
                        ],
                    }
                },
            },
        )
        task = result.json()["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_FAILED"
        assert not task.get("artifacts")
        assert task["status"]["message"]["parts"][0]["text"] == "research_citation_unknown"
    await registry.close()
    assert all(client.is_closed for client in delegated.http_clients)


async def test_recent_news_is_unchanged_with_research_enabled(
    delegated: DelegationCase, endpoint: Endpoint, research_wire: ResearchWire
) -> None:
    authorization, registry = await delegated.authorization(), TaskRegistry()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url="https://agent.test/a2a",
                registry=registry,
                research=ResearchController(delegated.adapter, research_wire.generator()),
            )
        ),
        base_url="https://agent.test",
        headers={"Authorization": "Bearer " + authorization.caller.assertion, "A2A-Version": "1.0"},
    ) as http:
        response = await http.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid4()),
                        "role": "ROLE_USER",
                        "parts": [{"text": "recent-news"}],
                    }
                },
            },
        )
        task = response.json()["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"
        readback = await http.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "GetTask",
                "params": {"id": task["id"], "historyLength": 2},
            },
        )
        result = json.loads(readback.json()["result"]["history"][-1]["parts"][0]["text"])
        assert result["news"]["items"][0]["id"] == str(endpoint[1].item.id)
    await registry.close()
    assert not research_wire.requests and len(delegated.forms) == 1


@pytest.mark.parametrize(
    "body",
    [
        b'{"operation":"research","question":"CLI_QUESTION_CANARY"}',
        b'{"operation":"research","question":"CLI_QUESTION_CANARY","extra":true}',
        b"CLI_INVALID_JSON_CANARY",
        b"CLI_SIZE_CANARY" + b"x" * 65536,
    ],
)
def test_cli_validates_bounded_stdin_and_reports_only_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], body: bytes
) -> None:
    received: list[ResearchRequest] = []

    async def verify(request: ResearchRequest) -> dict[str, int]:
        received.append(request)
        return {"validated": 1, "generation_calls": 2}

    monkeypatch.setattr("newsloom_agent.client.verify_research", verify)
    monkeypatch.setattr("sys.argv", ["newsloom-agent", "verify-research"])
    with io.TextIOWrapper(io.BytesIO(body), encoding="utf-8") as stdin:
        monkeypatch.setattr("sys.stdin", stdin)
        if body.endswith(b'"CLI_QUESTION_CANARY"}'):
            cli.main()
            assert len(received) == 1
        else:
            with pytest.raises(SystemExit, match="1"):
                cli.main()
            assert not received
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err


async def test_foreign_read_list_cancel_and_context_do_not_replay_research(
    delegated: DelegationCase, endpoint: Endpoint, research_wire: ResearchWire
) -> None:
    owner, foreign = await delegated.authorization(), await delegated.authorization()
    registry = TaskRegistry()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url="https://agent.test/a2a",
                registry=registry,
                research=ResearchController(delegated.adapter, research_wire.generator()),
            )
        ),
        base_url="https://agent.test",
        headers={"Authorization": "Bearer " + owner.caller.assertion, "A2A-Version": "1.0"},
    ) as http:
        params = {
            "message": {
                "messageId": str(uuid4()),
                "role": "ROLE_USER",
                "parts": [
                    {
                        "data": request(str(endpoint[1].item.id)).model_dump(
                            mode="json", by_alias=True
                        )
                    }
                ],
            }
        }
        task = (
            await http.post(
                "/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": params}
            )
        ).json()["result"]["task"]
        http.headers["Authorization"] = "Bearer " + foreign.caller.assertion
        for method in ("GetTask", "CancelTask"):
            response = await http.post(
                "/a2a",
                json={"jsonrpc": "2.0", "id": 2, "method": method, "params": {"id": task["id"]}},
            )
            assert "error" in response.json()
        listing = (
            await http.post(
                "/a2a", json={"jsonrpc": "2.0", "id": 3, "method": "ListTasks", "params": {}}
            )
        ).json()["result"]
        assert listing.get("totalSize", 0) == 0
        params["message"]["contextId"] = task["contextId"]
        assert (
            "error"
            in (
                await http.post(
                    "/a2a",
                    json={"jsonrpc": "2.0", "id": 4, "method": "SendMessage", "params": params},
                )
            ).json()
        )
    await registry.close()
    assert len(delegated.forms) == 1 and len(research_wire.requests) == 2


async def test_explicit_research_acceptance_client_uses_native_sdk_and_safe_counts(
    delegated: DelegationCase,
    endpoint: Endpoint,
    research_wire: ResearchWire,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = await delegated.authorization()
    settings = ClientSettings(
        tenant=delegated.config.tenant,
        agent_client_id=delegated.config.agent_client_id,
        mcp_audience=delegated.config.mcp_audience,
        mcp_url=delegated.config.mcp_url,
        public_client_id=authorization.caller.client_id,
        resource_url="https://agent.test/a2a",
    )
    original = httpx.AsyncClient
    registry = TaskRegistry()
    async with original(
        transport=httpx.ASGITransport(
            create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=settings.resource_url,
                registry=registry,
                research=ResearchController(delegated.adapter, research_wire.generator()),
            )
        )
    ) as app:

        async def route(request: httpx.Request) -> httpx.Response:
            response = await app.request(
                request.method, str(request.url), headers=request.headers, content=request.content
            )
            return httpx.Response(
                response.status_code, content=response.content, headers=response.headers
            )

        class LocalClient(httpx.AsyncClient):
            def __init__(
                self,
                *,
                trust_env: bool,
                follow_redirects: bool,
                timeout: float,
                headers: Mapping[str, str],
                event_hooks: Mapping[str, list[Callable[[httpx.Request], Awaitable[None]]]],
            ) -> None:
                super().__init__(
                    trust_env=trust_env,
                    follow_redirects=follow_redirects,
                    timeout=timeout,
                    headers=headers,
                    event_hooks=event_hooks,
                    transport=httpx.MockTransport(route),
                )

        async with original(transport=httpx.MockTransport(route)) as public:
            monkeypatch.setattr("httpx.AsyncClient", LocalClient)
            result = await acceptance.invoke_research(
                settings, authorization.caller.assertion, public, request(str(endpoint[1].item.id))
            )
        assert result.counts["validated"] == result.counts["user_preserved"] == 1
        assert result.counts["generation_calls"] == result.counts["usage_observed_calls"] == 2
        assert result.counts["progress_events"] > 0 and result.counts["task_reads"] == 1
        assert endpoint[1].item.url in result.text
        assert "CANARY" not in json.dumps(result.counts)
    await registry.close()
