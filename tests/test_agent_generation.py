import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
import httpx2
import jwt
import pytest
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import (
    CancelTaskRequest,
    GetTaskRequest,
    Message,
    Part,
    Role,
    SendMessageRequest,
    TaskState,
)
from a2a.utils.errors import A2AError
from agent_framework.observability import OBSERVABILITY_SETTINGS, enable_instrumentation
from azure.core.credentials import AccessToken
from mcp.types import CallToolResult
from newsloom_agent.app import create_app
from newsloom_agent.generation import (
    MAX_GENERATED_TOKENS,
    MAX_NEWS_BYTES,
    MAX_OUTPUT_BYTES,
    MODEL_SCOPE,
    FoundryGenerator,
    GenerationConfig,
    GenerationStats,
)
from newsloom_agent.models import AgentFailure, RecentNews
from newsloom_agent.serving import TaskRegistry
from opentelemetry import trace
from starlette.types import Message as ASGIMessage
from starlette.types import Receive, Scope, Send
from test_agent_delegation import DelegationCase, Workload
from test_agent_delegation import delegated as delegated
from test_agent_serving import loopback, until
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import endpoint as endpoint


def update(
    text: str | None = None,
    *,
    finish: str | None = None,
    usage: int | None = None,
    delta: dict[str, object] | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "id": "NEWSLOOM_MODEL_ID_CANARY",
        "created": 1,
        "model": "existing-chat",
        "object": "chat.completion.chunk",
        "choices": [
            {
                "index": 0,
                "delta": delta if delta is not None else {"content": text},
                "finish_reason": finish,
            }
        ]
        if usage is None
        else [],
    }
    if usage is not None:
        payload["usage"] = {
            "prompt_tokens": 25,
            "completion_tokens": usage,
            "total_tokens": 25 + usage,
        }
    return b"data: " + json.dumps(payload).encode() + b"\n\n"


@dataclass(repr=False)
class ModelStream(httpx2.AsyncByteStream):
    wire: list[bytes]
    release: asyncio.Event
    paused: asyncio.Event = field(default_factory=asyncio.Event)
    closed: bool = False
    consumed: int = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, chunk in enumerate(self.wire):
            if index == 1:
                self.paused.set()
                await self.release.wait()
            self.consumed += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@dataclass(repr=False)
class Model:
    wire: list[bytes] = field(
        default_factory=lambda: [
            update("NEWSLOOM_COMPLETION_CANARY "),
            update("second"),
            update(finish="stop"),
            update(usage=4),
            b"data: [DONE]\n\n",
        ]
    )
    requests: list[httpx2.Request] = field(default_factory=list)
    streams: list[ModelStream] = field(default_factory=list)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    workload: Workload = field(default_factory=Workload)
    status: int = 200

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        self.entered.set()
        assert str(request.url) == "https://owned.services.ai.azure.com/openai/v1/chat/completions"
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer " + self.workload.token.token
        if self.status == 307:
            return httpx2.Response(307, headers={"Location": "https://untrusted.invalid"})
        if self.status != 200:
            return httpx2.Response(
                self.status, json={"error": {"message": "NEWSLOOM_MODEL_ERROR_CANARY"}}
            )
        stream = ModelStream(self.wire, self.release)
        self.streams.append(stream)
        return httpx2.Response(200, headers={"Content-Type": "text/event-stream"}, stream=stream)

    def generator(self) -> FoundryGenerator:
        return FoundryGenerator(
            GenerationConfig(
                endpoint="https://owned.services.ai.azure.com", deployment="existing-chat"
            ),
            self.workload,
            transport=httpx2.MockTransport(self.handle),
        )


@pytest.fixture
def model() -> Model:
    value = Model()
    value.release.set()
    return value


def news(title: str = "NEWSLOOM_NEWS_CANARY") -> RecentNews:
    return RecentNews.model_validate(
        {
            "items": [
                {
                    "id": str(uuid4()),
                    "title": title,
                    "summary": "NEWSLOOM_SUMMARY_CANARY",
                    "source": "local",
                    "category": "developer-tools",
                    "tags": ["NEWSLOOM_TAG_CANARY"],
                    "published_at": "2026-10-27T00:00:00Z",
                    "url": "https://untrusted.invalid/NEWSLOOM_URL_CANARY",
                }
            ]
        }
    )


async def test_official_chat_connector_uses_one_fixed_mi_call_and_wire_token_bound(
    delegated: DelegationCase,
    model: Model,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "NEWSLOOM_ENV_KEY_CANARY")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.invalid")
    monkeypatch.setenv("HTTPS_PROXY", "https://untrusted.invalid")
    enable_instrumentation(force=True, enable_sensitive_data=True)
    provider = trace.get_tracer_provider()
    generator = model.generator()
    assert not OBSERVABILITY_SETTINGS.ENABLED
    stats = GenerationStats()
    authorization = await delegated.authorization()
    result = [part async for part in generator.stream(news(), authorization, stats)]
    assert trace.get_tracer_provider() is provider
    assert result == ["NEWSLOOM_COMPLETION_CANARY ", "second"]
    assert stats == GenerationStats(1, 2, 25, 4, True)
    assert model.workload.scopes == [(MODEL_SCOPE,)]
    assert len(model.requests) == 1
    payload = json.loads(model.requests[0].content)
    assert payload["model"] == "existing-chat"
    assert payload["max_completion_tokens"] == MAX_GENERATED_TOKENS
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["store"] is False
    assert payload.get("tools", []) == []
    assert "tool_choice" not in payload
    assert [message["role"] for message in payload["messages"]] == ["developer", "user"]
    assert "NEWSLOOM_NEWS_CANARY" not in payload["messages"][0]["content"]
    assert "NEWSLOOM_NEWS_CANARY" in payload["messages"][1]["content"]
    assert authorization.caller.assertion not in model.requests[0].content.decode()
    assert "NEWSLOOM_ENV_KEY_CANARY" not in str(model.requests[0].headers)
    assert all(stream.closed for stream in model.streams)


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, "model_denied"),
        (403, "model_denied"),
        (429, "model_throttled"),
        (500, "model_unavailable"),
        (307, "model_redirect_refused"),
    ],
)
async def test_denial_quota_errors_redirects_never_retry_or_fall_back(
    delegated: DelegationCase,
    model: Model,
    status: int,
    category: str,
) -> None:
    model.status = status
    authorization = await delegated.authorization()
    with pytest.raises(AgentFailure, match=f"^{category}$"):
        _ = [
            part
            async for part in model.generator().stream(news(), authorization, GenerationStats())
        ]
    assert len(model.requests) == 1


@pytest.mark.parametrize("kind", ["unfinished", "usage", "refused", "tools", "length", "quota"])
async def test_partial_or_unsupported_responses_are_never_completed(
    delegated: DelegationCase,
    model: Model,
    kind: str,
) -> None:
    model.wire = {
        "unfinished": [update("partial"), b"data: [DONE]\n\n"],
        "usage": [update("partial"), update(finish="stop"), b"data: [DONE]\n\n"],
        "refused": [update(delta={"refusal": "NEWSLOOM_REFUSAL_CANARY"})],
        "tools": [
            update(
                delta={
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call",
                            "type": "function",
                            "function": {"name": "untrusted", "arguments": "{}"},
                        }
                    ]
                }
            )
        ],
        "length": [update("partial"), update(finish="length")],
        "quota": [update("partial"), update(finish="stop"), update(usage=513)],
    }[kind]
    with pytest.raises(AgentFailure):
        _ = [
            part
            async for part in model.generator().stream(
                news(), await delegated.authorization(), GenerationStats()
            )
        ]
    assert len(model.requests) == 1
    assert all(stream.closed for stream in model.streams)


@pytest.mark.parametrize("excess", [0, 1])
async def test_exact_output_byte_and_token_limits(
    delegated: DelegationCase,
    model: Model,
    excess: int,
) -> None:
    model.wire = [
        update("x" * (MAX_OUTPUT_BYTES + excess)),
        update(finish="stop"),
        update(usage=512),
        b"data: [DONE]\n\n",
    ]
    authorization, stats = await delegated.authorization(), GenerationStats()
    if excess:
        with pytest.raises(AgentFailure, match="model_output_limit"):
            _ = [part async for part in model.generator().stream(news(), authorization, stats)]
    else:
        parts = [part async for part in model.generator().stream(news(), authorization, stats)]
        assert sum(len(part) for part in parts) == MAX_OUTPUT_BYTES
        assert stats.output_tokens == 512
    assert all(stream.closed for stream in model.streams)


async def test_news_bytes_and_model_identity_fail_before_any_generation(
    delegated: DelegationCase,
    model: Model,
) -> None:
    for data in (RecentNews(items=()), news("x" * MAX_NEWS_BYTES)):
        with pytest.raises(AgentFailure):
            _ = [
                part
                async for part in model.generator().stream(
                    data, await delegated.authorization(), GenerationStats()
                )
            ]
    model.workload.token = AccessToken("NEWSLOOM_EXPIRED_MODEL_TOKEN", int(time.time()) - 1)
    with pytest.raises(AgentFailure, match="model_token_lifetime"):
        _ = [
            part
            async for part in model.generator().stream(
                news(), await delegated.authorization(), GenerationStats()
            )
        ]
    assert model.requests == []


@pytest.mark.parametrize("excess", [0, 1])
async def test_exact_news_json_byte_limit(
    delegated: DelegationCase,
    model: Model,
    excess: int,
) -> None:
    overhead = len(news("").model_dump_json().encode())
    item = news("x" * (MAX_NEWS_BYTES - overhead + excess))
    assert len(item.model_dump_json().encode()) == MAX_NEWS_BYTES + excess
    authorization = await delegated.authorization()
    if excess:
        with pytest.raises(AgentFailure, match="model_input_limit"):
            _ = [
                text
                async for text in model.generator().stream(item, authorization, GenerationStats())
            ]
        assert not model.requests and not model.workload.scopes
    else:
        assert [
            text async for text in model.generator().stream(item, authorization, GenerationStats())
        ]
        assert len(model.requests) == 1


@pytest.mark.parametrize("cancel", [False, True])
async def test_original_deadline_and_cancellation_close_actual_model_stream(
    delegated: DelegationCase,
    model: Model,
    cancel: bool,
) -> None:
    model.release.clear()
    authorization = await delegated.authorization(seconds=2 if cancel else 0.1)

    async def invoke() -> None:
        _ = [
            part
            async for part in model.generator().stream(news(), authorization, GenerationStats())
        ]

    task = asyncio.create_task(invoke())
    try:
        async with asyncio.timeout(1):
            await model.entered.wait()
            await model.streams[0].paused.wait()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else AgentFailure):
            await task
        assert all(stream.closed for stream in model.streams)
        assert len(model.requests) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_actual_http_obo_mcp_framework_chat_and_a2a_stream_before_model_finishes(
    delegated: DelegationCase,
    model: Model,
) -> None:
    model.release.clear()
    authorization, registry = await delegated.authorization(), TaskRegistry()
    async with (
        loopback(
            lambda base: create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=f"{base}/a2a",
                registry=registry,
                generator=model.generator(),
            )
        ) as base,
        httpx.AsyncClient(
            headers={"Authorization": "Bearer " + authorization.caller.assertion},
            trust_env=False,
            timeout=5,
        ) as http,
    ):
        card = await A2ACardResolver(http, base).get_agent_card()
        assert card.capabilities.streaming
        client = ClientFactory(
            ClientConfig(streaming=True, httpx_client=http, supported_protocol_bindings=["JSONRPC"])
        ).create(card)
        artifacts: list[str] = []
        terminal = TaskState.TASK_STATE_UNSPECIFIED
        try:
            async with asyncio.timeout(5):
                async for reply in client.send_message(
                    SendMessageRequest(
                        message=Message(
                            message_id=str(uuid4()),
                            role=Role.ROLE_USER,
                            parts=[Part(text="recent-news")],
                        )
                    )
                ):
                    if reply.HasField("artifact_update"):
                        artifacts.append(reply.artifact_update.artifact.parts[0].text)
                        if len(artifacts) == 1:
                            assert not model.release.is_set()
                            assert len(model.requests) == 1
                            assert (
                                registry.records[reply.artifact_update.task_id].producer is not None
                            )
                            model.release.set()
                    if reply.HasField("task"):
                        terminal = reply.task.status.state
            assert terminal == TaskState.TASK_STATE_COMPLETED
            assert artifacts == ["NEWSLOOM_COMPLETION_CANARY ", "second"]
            record = next(iter(registry.records.values()))
            task = await client.get_task(GetTaskRequest(id=record.task.id, history_length=2))
            assert task.artifacts[0].parts[0].text == "".join(artifacts)
            assert json.loads(task.status.message.parts[0].text) == {
                "outcome": "news",
                "items": 1,
                "user_preserved": True,
                "generated": True,
                "generation_calls": 1,
                "output_tokens": 4,
            }
            assert len(delegated.forms) == 1
            assert all(stream.closed for stream in model.streams)
            assert all(transport.closed for transport in delegated.identity_transports)
            assert all(client.is_closed for client in delegated.http_clients)
        finally:
            model.release.set()
            await client.close()


@pytest.mark.parametrize("capacity", [2, 8])
async def test_stream_channel_backpressure_stops_model_reads_at_the_exact_capacity(
    delegated: DelegationCase,
    model: Model,
    capacity: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("newsloom_agent.serving.MAX_STREAM_EVENTS", capacity)
    model.wire = [
        *(update(str(index)) for index in range(40)),
        update(finish="stop"),
        update(usage=512),
        b"data: [DONE]\n\n",
    ]
    authorization, registry = await delegated.authorization(), TaskRegistry()
    app = create_app(
        delegated.adapter,
        delegated.agent_verifier,
        public_url="https://agent.test/a2a",
        registry=registry,
        generator=model.generator(),
    )
    release, blocked = asyncio.Event(), asyncio.Event()

    async def slow_consumer(scope: Scope, receive: Receive, send: Send) -> None:
        async def hold(message: ASGIMessage) -> None:
            if (
                message["type"] == "http.response.body"
                and message.get("body")
                and not blocked.is_set()
            ):
                blocked.set()
                await release.wait()
            await send(message)

        await app(scope, receive, hold)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(slow_consumer),
        base_url="https://agent.test",
        headers={"Authorization": "Bearer " + authorization.caller.assertion, "A2A-Version": "1.0"},
    ) as http:
        sending = asyncio.create_task(
            http.post(
                "/a2a",
                json={
                    "jsonrpc": "2.0",
                    "id": "local",
                    "method": "SendStreamingMessage",
                    "params": {
                        "message": {
                            "messageId": str(uuid4()),
                            "role": "ROLE_USER",
                            "parts": [{"text": "recent-news"}],
                        }
                    },
                },
            )
        )
        try:
            await asyncio.wait_for(blocked.wait(), 3)
            await until(lambda: bool(model.streams) and model.streams[0].consumed >= capacity - 1)
            assert model.streams[0].consumed == capacity - 1
            assert not sending.done()
            release.set()
            assert (await asyncio.wait_for(sending, 3)).status_code == 200
            assert (
                next(iter(registry.records.values())).task.status.state
                == TaskState.TASK_STATE_COMPLETED
            )
            assert all(stream.closed for stream in model.streams)
        finally:
            release.set()
            sending.cancel()
            await asyncio.gather(sending, return_exceptions=True)
            await registry.close()


@pytest.mark.parametrize(
    "mode",
    [
        "empty",
        "exchange",
        "mcp",
        "throttled",
        "partial",
        "malformed",
        "cancel",
        "disconnect",
        "deadline",
        "expiry",
        "unsupported",
    ],
)
async def test_real_http_terminal_states_and_request_owned_cleanup(
    delegated: DelegationCase,
    model: Model,
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if mode == "empty":
        delegated.mcp_result = CallToolResult(
            content=[], structured_content={"items": []}
        ).model_dump(mode="json", by_alias=True, exclude_none=True)
    if mode == "exchange":
        delegated.exchange_status, delegated.exchange_payload = 400, {"error": "invalid_grant"}
    if mode == "mcp":
        delegated.mcp_status = 403
    if mode == "throttled":
        model.status = 429
    if mode == "partial":
        model.wire = [update("partial"), b"data: [DONE]\n\n"]
    if mode == "malformed":
        model.wire = [b'data: {"choices":"NEWSLOOM_MALFORMED_CANARY"}\n\n']
    if mode in ("cancel", "disconnect", "deadline", "expiry"):
        model.release.clear()
    if mode == "deadline":
        monkeypatch.setattr("newsloom_agent.app.REQUEST_SECONDS", 1.0)
    authorization, registry = await delegated.authorization(), TaskRegistry()
    bearer = authorization.caller.assertion
    if mode == "expiry":
        claims = jwt.decode(bearer, options={"verify_signature": False})
        claims["exp"] = int(time.time()) + 2
        token = jwt.encode(
            claims, delegated.key, algorithm="RS256", headers={"kid": "local-test-key"}
        )
        delegated.issued[token] = delegated.issued[bearer]
        bearer = token
    async with (
        loopback(
            lambda base: create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=f"{base}/a2a",
                registry=registry,
                generator=model.generator(),
            )
        ) as base,
        httpx.AsyncClient(
            headers={"Authorization": "Bearer " + bearer},
            trust_env=False,
            timeout=5,
        ) as http,
    ):
        client = ClientFactory(
            ClientConfig(streaming=True, httpx_client=http, supported_protocol_bindings=["JSONRPC"])
        ).create(await A2ACardResolver(http, base).get_agent_card())
        first_artifact = asyncio.Event()

        async def consume() -> None:
            async for reply in client.send_message(
                SendMessageRequest(
                    message=Message(
                        message_id=str(uuid4()),
                        role=Role.ROLE_USER,
                        parts=[
                            Part(text="unsupported" if mode == "unsupported" else "recent-news")
                        ],
                    )
                )
            ):
                if reply.HasField("artifact_update"):
                    first_artifact.set()

        task = asyncio.create_task(consume())
        try:
            if mode in ("cancel", "disconnect", "deadline", "expiry"):
                await asyncio.wait_for(first_artifact.wait(), 3)
                record = next(iter(registry.records.values()))
                if mode == "cancel":
                    result = await client.cancel_task(CancelTaskRequest(id=record.task.id))
                    assert result.status.state == TaskState.TASK_STATE_CANCELED
                if mode == "disconnect":
                    task.cancel()
                if mode in ("deadline", "expiry"):
                    with pytest.raises(A2AError):
                        await task
                elif mode == "disconnect":
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    await task
            elif mode == "unsupported":
                with pytest.raises(A2AError):
                    await task
                assert not registry.records and not model.requests and not delegated.forms
                return
            else:
                await task
            await until(
                lambda: all(record.producer is None for record in registry.records.values())
            )
            record = next(iter(registry.records.values()))
            expected = (
                TaskState.TASK_STATE_COMPLETED
                if mode == "empty"
                else TaskState.TASK_STATE_CANCELED
                if mode in ("cancel", "disconnect")
                else TaskState.TASK_STATE_FAILED
            )
            if mode == "expiry":
                with pytest.raises(A2AError):
                    await client.get_task(GetTaskRequest(id=record.task.id))
                renewed = await delegated.authorization(user=authorization.caller.object_id)
                http.headers["Authorization"] = "Bearer " + renewed.caller.assertion
            result = await client.get_task(GetTaskRequest(id=record.task.id))
            assert result.status.state == expected
            if mode == "empty":
                assert json.loads(result.status.message.parts[0].text)["outcome"] == "empty"
                assert json.loads(result.status.message.parts[0].text)["generation_calls"] == 0
            if mode in ("partial", "cancel", "disconnect", "deadline", "expiry"):
                assert result.artifacts and result.artifacts[0].parts[0].text
                assert result.status.state != TaskState.TASK_STATE_COMPLETED
            assert len(model.requests) == (0 if mode in ("empty", "exchange", "mcp") else 1)
            assert all(stream.closed for stream in model.streams)
            assert all(transport.closed for transport in delegated.identity_transports)
            assert all(http.is_closed for http in delegated.http_clients)
            assert "CANARY" not in capsys.readouterr().out
        finally:
            model.release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await client.close()
