import asyncio
import json
import logging
import socket
import time
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
import pytest
import uvicorn
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    CancelTaskRequest,
    GetTaskRequest,
    ListTasksRequest,
    Message,
    Part,
    Role,
    SendMessageRequest,
    TaskState,
)
from agent_framework.a2a import A2AExecutor
from newsloom_agent.app import MAX_BODY_BYTES, create_app
from newsloom_agent.auth import Authorization, current_authorization
from newsloom_agent.delegation import DelegatedRead
from newsloom_agent.models import AgentFailure, RecentNews
from newsloom_agent.serving import MAX_TASKS, MAX_TEXT_BYTES, TaskRegistry
from newsloom_core.diagnostics import SafeHandler
from starlette.types import ASGIApp
from test_agent_auth import EndpointState, signed
from test_agent_auth import authority as authority
from test_agent_delegation import DelegationCase
from test_agent_delegation import delegated as delegated
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import endpoint as endpoint


@dataclass(repr=False)
class Reader:
    calls: list[Authorization] = field(default_factory=list)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    failure: Exception | None = None

    async def recent(self, authorization: Authorization) -> DelegatedRead:
        assert authorization is current_authorization()
        self.calls.append(authorization)
        try:
            await self.release.wait()
            assert authorization is current_authorization()
            if self.failure is not None:
                raise self.failure
            return DelegatedRead(RecentNews(items=()), user_preserved=True)
        finally:
            self.closed.set()


@dataclass(repr=False)
class Serving:
    http: httpx.AsyncClient
    authority: EndpointState
    reader: Reader
    registry: TaskRegistry

    async def rpc(self, method: str, params: Mapping[str, object]) -> httpx.Response:
        return await self.http.post(
            "/a2a", json={"jsonrpc": "2.0", "id": "local", "method": method, "params": dict(params)}
        )

    async def invoke(self, **message: object) -> httpx.Response:
        return await self.rpc("SendMessage", invocation(**message))


def invocation(**changes: object) -> dict[str, object]:
    return {
        "message": {
            "messageId": str(uuid4()),
            "role": "ROLE_USER",
            "parts": [{"text": "recent-news"}],
            **changes,
        }
    }


async def until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(5):
        while not predicate():  # noqa: ASYNC110 - SDK startup exposes no readiness event.
            await asyncio.sleep(0.001)


@pytest.fixture
async def serving(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> AsyncIterator[Serving]:
    _, state = authority
    reader = Reader()
    reader.release.set()
    registry = TaskRegistry()
    app = create_app(reader, state.verifier, public_url="https://agent.test/a2a", registry=registry)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="https://agent.test",
        headers={
            "Authorization": "Bearer " + signed(state),
            "A2A-Version": "1.0",
            "Content-Type": "application/json",
        },
    ) as http:
        yield Serving(http, state, reader, registry)
    assert all(record.producer is None for record in registry.records.values())
    await registry.close()


@asynccontextmanager
async def loopback(app_factory: Callable[[str], ASGIApp]) -> AsyncIterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.setblocking(False)
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(
            uvicorn.Config(
                app_factory(url),
                log_config=None,
                access_log=False,
                proxy_headers=False,
                lifespan="on",
            )
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            await until(lambda: server.started or task.done())
            if task.done():
                await task
                pytest.fail("agent_server_stopped")
            yield url
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 5)


async def test_real_http_official_a2a_client_to_actual_delegated_sdk_adapters(
    delegated: DelegationCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging.getLogger(), "handlers", [SafeHandler()])
    contexts: list[dict[str, object]] = []
    execute = A2AExecutor.execute

    async def capture_context(
        executor: A2AExecutor, context: RequestContext, queue: EventQueue
    ) -> None:
        assert context.call_context is not None
        contexts.append(dict(context.call_context.state))
        await execute(executor, context, queue)

    monkeypatch.setattr(A2AExecutor, "execute", capture_context)
    authorization = await delegated.authorization()
    registry = TaskRegistry()
    async with (
        loopback(
            lambda base: create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=f"{base}/a2a",
                registry=registry,
            )
        ) as base,
        httpx.AsyncClient(timeout=5, trust_env=False) as http,
    ):
        card = await A2ACardResolver(http, base).get_agent_card()
        assert not card.capabilities.streaming
        assert not card.capabilities.push_notifications
        assert [skill.id for skill in card.skills] == ["recent-news"]
        assert card.security_schemes[
            "entra"
        ].oauth2_security_scheme.flows.authorization_code.pkce_required
        scope = f"api://{delegated.config.agent_client_id}/news.agent"
        assert set(
            card.security_schemes["entra"].oauth2_security_scheme.flows.authorization_code.scopes
        ) == {scope}
        assert list(card.security_requirements[0].schemes["entra"].list) == [scope]
        assert not delegated.forms
        http.headers["Authorization"] = "Bearer " + authorization.caller.assertion
        client = ClientFactory(
            ClientConfig(
                streaming=False, httpx_client=http, supported_protocol_bindings=["JSONRPC"]
            )
        ).create(card)
        try:
            replies = [
                reply
                async for reply in client.send_message(
                    SendMessageRequest(
                        metadata={
                            "agent_framework": {
                                "client_kwargs": {
                                    "endpoint": "https://untrusted.invalid/NEWSLOOM_METADATA_CANARY"
                                }
                            }
                        },
                        message=Message(
                            message_id=str(uuid4()),
                            role=Role.ROLE_USER,
                            parts=[Part(text="recent-news")],
                        ),
                    )
                )
            ]
            task = await client.get_task(GetTaskRequest(id=replies[-1].task.id, history_length=10))
            assert task.status.state == TaskState.TASK_STATE_COMPLETED
            result = json.loads(task.history[-1].parts[0].text)
            assert result["outcome"] == "news"
            assert result["user_preserved"] is True
            assert len(result["news"]["items"]) == 1
            assert len(delegated.forms) == 1
            assert delegated.mcp_methods == [
                "initialize",
                "notifications/initialized",
                "tools/call",
            ]
            assert all(transport.closed for transport in delegated.identity_transports)
            assert all(http.is_closed for http in delegated.http_clients)
        finally:
            await client.close()
    assert contexts[0]["headers"] == {"a2a-version": "1.0"}
    assert authorization.caller.assertion not in json.dumps(contexts)
    assert str(authorization.caller.object_id) not in json.dumps(contexts)
    output = capsys.readouterr().out
    assert "CANARY" not in output
    assert authorization.caller.assertion not in output


async def test_static_discovery_and_missing_auth_never_invoke_reader(serving: Serving) -> None:
    serving.http.headers.pop("Authorization")
    for path in ("/health/live", "/.well-known/agent-card.json"):
        assert (await serving.http.get(path)).status_code == 200
    assert (await serving.invoke()).status_code == 401
    for method in ("GetTask", "CancelTask", "SubscribeToTask", "ListTasks"):
        assert (await serving.rpc(method, {"id": str(uuid4())})).status_code == 401
    assert not serving.reader.calls


async def test_empty_is_a_real_completed_empty_read_not_a_failure(serving: Serving) -> None:
    response = (await serving.invoke()).json()["result"]["task"]
    assert response["status"]["state"] == "TASK_STATE_COMPLETED"
    output = json.loads(response["history"][-1]["parts"][0]["text"])
    assert output == {"outcome": "empty", "news": {"items": []}, "user_preserved": True}
    assert len(serving.reader.calls) == 1


@pytest.mark.parametrize("method", ["GetTask", "CancelTask"])
async def test_foreign_and_unknown_task_ids_are_indistinguishable(
    serving: Serving, method: str
) -> None:
    task = (await serving.invoke()).json()["result"]["task"]
    serving.http.headers["Authorization"] = "Bearer " + signed(serving.authority)
    foreign = (await serving.rpc(method, {"id": task["id"]})).json()["error"]
    unknown = (await serving.rpc(method, {"id": str(uuid4())})).json()["error"]
    assert foreign == unknown
    assert len(serving.reader.calls) == 1


async def test_context_ownership_and_continuation_do_not_replay_work(serving: Serving) -> None:
    task = (await serving.invoke()).json()["result"]["task"]
    assert "result" in (await serving.invoke(contextId=task["contextId"])).json()
    assert "error" in (await serving.invoke(taskId=task["id"])).json()
    assert len(serving.reader.calls) == 2
    serving.http.headers["Authorization"] = "Bearer " + signed(serving.authority)
    for message in (
        {"contextId": task["contextId"]},
        {"taskId": task["id"]},
        {"contextId": str(uuid4())},
        {"taskId": str(uuid4())},
    ):
        assert "error" in (await serving.invoke(**message)).json()
    assert len(serving.reader.calls) == 2


@pytest.mark.parametrize(
    "method",
    [
        "SubscribeToTask",
        "SendStreamingMessage",
        "GetExtendedAgentCard",
        "CreateTaskPushNotificationConfig",
        "GetTaskPushNotificationConfig",
        "ListTaskPushNotificationConfigs",
        "DeleteTaskPushNotificationConfig",
        "message/send",
        "UnknownMethod",
    ],
)
async def test_unimplemented_methods_are_explicit_and_have_no_provider_activity(
    serving: Serving, method: str
) -> None:
    assert "error" in (await serving.rpc(method, invocation())).json()
    assert not serving.reader.calls
    assert not serving.registry.records


@pytest.mark.parametrize(
    "message",
    [
        {"parts": [{"url": "https://untrusted.invalid/news"}]},
        {"parts": [{"raw": "dW50cnVzdGVk"}]},
        {"parts": [{"data": {"operation": "query_database"}}]},
        {"parts": [{"text": "research something"}]},
        {"parts": [{"text": "recent-news", "filename": "notes.txt"}]},
        {"parts": [{"text": "recent-news"}], "extensions": ["https://untrusted.invalid"]},
        {"parts": [{"text": "recent-news"}], "referenceTaskIds": ["foreign"]},
        {"parts": [{"text": "recent-news"}, {"text": "instructions"}]},
        {"role": "ROLE_AGENT"},
        {"messageId": ""},
    ],
)
async def test_unsupported_work_and_attachments_stop_before_admission(
    serving: Serving, message: dict[str, object]
) -> None:
    assert "error" in (await serving.invoke(**message)).json()
    assert not serving.reader.calls
    assert not serving.registry.records


@pytest.mark.parametrize("size", [MAX_TEXT_BYTES - 1, MAX_TEXT_BYTES, MAX_TEXT_BYTES + 1])
@pytest.mark.parametrize("multibyte", [False, True])
async def test_exact_utf8_input_text_boundary(serving: Serving, size: int, multibyte: bool) -> None:
    padding = size - len("recent-news")
    text = "recent-news" + (
        "\u2003" * (padding // 3) + " " * (padding % 3) if multibyte else " " * padding
    )
    assert len(text.encode("utf-8")) == size
    result = (await serving.invoke(parts=[{"text": text}])).json()
    assert ("result" in result) is (size <= MAX_TEXT_BYTES)
    assert len(serving.reader.calls) == int(size <= MAX_TEXT_BYTES)


@pytest.mark.parametrize("size", [MAX_BODY_BYTES - 1, MAX_BODY_BYTES, MAX_BODY_BYTES + 1])
@pytest.mark.parametrize("chunked", [False, True])
async def test_exact_body_byte_boundary(serving: Serving, size: int, chunked: bool) -> None:
    raw = json.dumps(
        {"jsonrpc": "2.0", "id": "local", "method": "SendMessage", "params": invocation()}
    ).encode()
    body = raw + b" " * (size - len(raw))

    async def chunks() -> AsyncIterator[bytes]:
        for index in range(0, len(body), 4096):
            yield body[index : index + 4096]

    response = await serving.http.post("/a2a", content=chunks() if chunked else body)
    assert response.status_code == (200 if size <= MAX_BODY_BYTES else 413)
    assert len(serving.reader.calls) == int(size <= MAX_BODY_BYTES)


async def test_four_active_requests_then_explicit_overload_and_release(serving: Serving) -> None:
    serving.reader.release.clear()
    requests = [asyncio.create_task(serving.invoke()) for _ in range(4)]
    try:
        await until(lambda: len(serving.reader.calls) == 4)
        assert (await serving.invoke()).status_code == 429
        assert len(serving.reader.calls) == 4
        assert (await serving.http.get("/health/live")).status_code == 200
        assert (await serving.http.get("/.well-known/agent-card.json")).status_code == 200
    finally:
        serving.reader.release.set()
        responses = await asyncio.gather(*requests)
    assert all("result" in response.json() for response in responses)
    assert "result" in (await serving.invoke()).json()


async def test_exact_task_capacity_and_ttl_do_not_evict_active_or_replay(
    serving: Serving,
) -> None:
    now = 1000.0
    serving.registry.clock = lambda: now
    for _ in range(MAX_TASKS):
        assert "result" in (await serving.invoke()).json()
    assert len(serving.registry.records) == MAX_TASKS
    assert "error" in (await serving.invoke()).json()
    assert len(serving.reader.calls) == MAX_TASKS
    task_id = next(iter(serving.registry.records))
    now = 1299.999
    assert "result" in (await serving.rpc("GetTask", {"id": task_id})).json()
    now = 1300.0
    assert "error" in (await serving.rpc("GetTask", {"id": task_id})).json()
    assert "result" in (await serving.invoke()).json()
    assert len(serving.registry.records) == 1


async def test_idle_expiry_removes_state_without_retaining_request_authorization(
    serving: Serving, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("newsloom_agent.serving.TASK_RETENTION_SECONDS", 0.04)
    observed: list[bool] = []

    def clock() -> float:
        try:
            current_authorization()
        except AgentFailure:
            observed.append(False)
        else:
            observed.append(True)
        return time.monotonic()

    serving.registry.clock = clock
    assert "result" in (await serving.invoke()).json()
    await asyncio.sleep(0.08)
    assert not serving.registry.records
    assert False in observed


async def test_task_limit_cannot_evict_an_active_task(serving: Serving) -> None:
    for _ in range(MAX_TASKS - 1):
        assert "result" in (await serving.invoke()).json()
    serving.reader.release.clear()
    sending = asyncio.create_task(serving.invoke())
    try:
        await until(lambda: len(serving.reader.calls) == MAX_TASKS)
        active = next(
            record for record in serving.registry.records.values() if record.producer is not None
        )
        assert "error" in (await serving.invoke()).json()
        assert active.task.id in serving.registry.records
        assert len(serving.registry.records) == MAX_TASKS
    finally:
        serving.reader.release.set()
        await sending


async def test_two_interleaved_users_have_separate_listing_and_contexts(serving: Serving) -> None:
    serving.reader.release.clear()
    tokens = [signed(serving.authority), signed(serving.authority)]

    async def invoke(token: str) -> httpx.Response:
        return await serving.http.post(
            "/a2a",
            headers={"Authorization": "Bearer " + token},
            json={"jsonrpc": "2.0", "id": "local", "method": "SendMessage", "params": invocation()},
        )

    requests = [asyncio.create_task(invoke(token)) for token in tokens]
    try:
        await until(lambda: len(serving.reader.calls) == 2)
        ids = []
        for token in tokens:
            serving.http.headers["Authorization"] = "Bearer " + token
            result = (await serving.rpc("ListTasks", {})).json()["result"]
            assert result["totalSize"] == 1
            ids.append(result["tasks"][0]["id"])
        assert ids[0] != ids[1]
        assert "error" in (await serving.rpc("GetTask", {"id": ids[0]})).json()
        assert "error" in (await serving.rpc("CancelTask", {"id": ids[0]})).json()
    finally:
        serving.reader.release.set()
        responses = await asyncio.gather(*requests)
    assert all("result" in response.json() for response in responses)
    assert serving.reader.calls[0].caller.object_id != serving.reader.calls[1].caller.object_id


async def test_task_listing_pages_are_owned_bounded_and_metadata_only(serving: Serving) -> None:
    tasks = [(await serving.invoke()).json()["result"]["task"] for _ in range(3)]
    page = (await serving.rpc("ListTasks", {"pageSize": 2})).json()["result"]
    assert page["totalSize"] == 3
    assert [task["id"] for task in page["tasks"]] == [tasks[2]["id"], tasks[1]["id"]]
    assert all(not task.get("history") for task in page["tasks"])
    assert all(not task["status"].get("message") for task in page["tasks"])
    following = (
        await serving.rpc("ListTasks", {"pageSize": 2, "pageToken": page["nextPageToken"]})
    ).json()["result"]
    assert [task["id"] for task in following["tasks"]] == [tasks[0]["id"]]
    assert not following.get("nextPageToken")
    own_context = (await serving.rpc("ListTasks", {"contextId": tasks[0]["contextId"]})).json()[
        "result"
    ]
    assert own_context["totalSize"] == 1
    for params in (
        {"pageSize": 0},
        {"pageSize": 65},
        {"historyLength": 1},
        {"includeArtifacts": True},
    ):
        assert "error" in (await serving.rpc("ListTasks", params)).json()
    serving.http.headers["Authorization"] = "Bearer " + signed(serving.authority)
    assert not (await serving.rpc("ListTasks", {})).json()["result"].get("tasks")
    assert "error" in (await serving.rpc("ListTasks", {"pageToken": tasks[0]["id"]})).json()
    assert "error" in (await serving.rpc("ListTasks", {"contextId": tasks[0]["contextId"]})).json()
    assert len(serving.reader.calls) == 3


@pytest.mark.parametrize("seconds", [-0.001, 0.0, 0.2])
async def test_deadline_admission_boundary(
    serving: Serving, monkeypatch: pytest.MonkeyPatch, seconds: float
) -> None:
    monkeypatch.setattr("newsloom_agent.app.REQUEST_SECONDS", seconds)
    response = await serving.invoke()
    assert response.status_code == (200 if seconds > 0 else 503)
    assert len(serving.reader.calls) == int(seconds > 0)


async def test_restart_returns_not_found_without_replay(serving: Serving) -> None:
    task = (await serving.invoke()).json()["result"]["task"]
    restarted = create_app(
        serving.reader, serving.authority.verifier, public_url="https://agent.test/a2a"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(restarted),
        base_url="https://agent.test",
        headers=dict(serving.http.headers),
    ) as http:
        response = await http.post(
            "/a2a",
            json={"jsonrpc": "2.0", "id": 1, "method": "GetTask", "params": {"id": task["id"]}},
        )
        assert "error" in response.json()
    assert len(serving.reader.calls) == 1


async def test_cancel_waits_for_provider_cleanup_and_is_not_completed(serving: Serving) -> None:
    serving.reader.release.clear()
    sending = asyncio.create_task(serving.invoke())
    try:
        await until(lambda: len(serving.reader.calls) == 1)
        task_id = next(iter(serving.registry.records))
        current = (await serving.rpc("GetTask", {"id": task_id})).json()
        assert current["result"]["status"]["state"] == "TASK_STATE_WORKING"
        canceled = (await serving.rpc("CancelTask", {"id": task_id})).json()
        assert serving.reader.closed.is_set()
        assert canceled["result"]["status"]["state"] == "TASK_STATE_CANCELED"
        assert (await sending).json()["result"]["task"]["status"]["state"] == "TASK_STATE_CANCELED"
        assert "error" in (await serving.rpc("CancelTask", {"id": task_id})).json()
    finally:
        sending.cancel()
        await asyncio.gather(sending, return_exceptions=True)


@pytest.mark.parametrize("stage", ["exchange", "mcp"])
async def test_real_http_official_client_lists_reads_and_cancels_actual_sdk_work(
    delegated: DelegationCase, stage: str
) -> None:
    authorization = await delegated.authorization()
    release = delegated.exchange_release if stage == "exchange" else delegated.mcp_release
    entered = delegated.exchange_entered if stage == "exchange" else delegated.mcp_entered
    release.clear()
    registry = TaskRegistry()
    async with (
        loopback(
            lambda base: create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=f"{base}/a2a",
                registry=registry,
            )
        ) as base,
        httpx.AsyncClient(
            headers={"Authorization": "Bearer " + authorization.caller.assertion},
            timeout=5,
            trust_env=False,
        ) as http,
    ):
        card = await A2ACardResolver(http, base).get_agent_card()
        client = ClientFactory(
            ClientConfig(
                streaming=False, httpx_client=http, supported_protocol_bindings=["JSONRPC"]
            )
        ).create(card)

        async def invoke() -> None:
            replies = [
                reply
                async for reply in client.send_message(
                    SendMessageRequest(
                        message=Message(
                            message_id=str(uuid4()),
                            role=Role.ROLE_USER,
                            parts=[Part(text="recent-news")],
                        )
                    )
                )
            ]
            assert replies[-1].task.status.state == TaskState.TASK_STATE_CANCELED

        sending = asyncio.create_task(invoke())
        try:
            await asyncio.wait_for(entered.wait(), 3)
            listing = await client.list_tasks(ListTasksRequest())
            assert listing.total_size == 1
            task_id = listing.tasks[0].id
            current = await client.get_task(GetTaskRequest(id=task_id))
            assert current.status.state == TaskState.TASK_STATE_WORKING
            canceled = await client.cancel_task(CancelTaskRequest(id=task_id))
            assert canceled.status.state == TaskState.TASK_STATE_CANCELED
            await asyncio.wait_for(sending, 3)
            assert all(transport.closed for transport in delegated.identity_transports)
            assert all(http.is_closed for http in delegated.http_clients)
            assert all(record.producer is None for record in registry.records.values())
        finally:
            sending.cancel()
            await asyncio.gather(sending, return_exceptions=True)
            await client.close()


async def test_real_http_disconnect_stops_request_work(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    _, state = authority
    reader, registry = Reader(), TaskRegistry()
    async with (
        loopback(
            lambda base: create_app(
                reader, state.verifier, public_url=f"{base}/a2a", registry=registry
            )
        ) as base,
        httpx.AsyncClient(
            base_url=base,
            headers={"Authorization": "Bearer " + signed(state), "A2A-Version": "1.0"},
            trust_env=False,
        ) as http,
    ):
        sending = asyncio.create_task(
            http.post(
                "/a2a",
                json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": invocation()},
            )
        )
        await until(lambda: len(reader.calls) == 1)
        sending.cancel()
        await asyncio.gather(sending, return_exceptions=True)
        await asyncio.wait_for(reader.closed.wait(), 2)
        await until(lambda: all(record.producer is None for record in registry.records.values()))
        assert [record.task.status.state for record in registry.records.values()] == [
            TaskState.TASK_STATE_CANCELED
        ]
        assert (await http.get("/health/live")).status_code == 200


async def test_original_deadline_includes_body_auth_and_provider_cleanup(
    serving: Serving,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("newsloom_agent.app.REQUEST_SECONDS", 0.05)
    serving.reader.release.clear()
    started = time.monotonic()
    response = await serving.invoke()
    assert response.status_code == 504
    assert time.monotonic() - started < 0.5
    assert serving.reader.closed.is_set()
    authorization = serving.reader.calls[0]
    assert started <= authorization.deadline <= started + 0.06
    assert all(
        record.task.status.state != TaskState.TASK_STATE_COMPLETED
        for record in serving.registry.records.values()
    )


async def test_authorization_expiry_stops_already_admitted_work(serving: Serving) -> None:
    expires = int(time.time()) + 2
    serving.http.headers["Authorization"] = "Bearer " + signed(serving.authority, {"exp": expires})
    serving.reader.release.clear()
    started = time.monotonic()
    response = await serving.invoke()
    assert response.status_code == 504
    assert time.monotonic() - started < 2.2
    assert serving.reader.closed.is_set()
    assert len(serving.reader.calls) == 1
    assert time.time() >= expires - 0.05
    assert all(
        record.task.status.state != TaskState.TASK_STATE_COMPLETED
        for record in serving.registry.records.values()
    )


async def test_slow_request_body_spends_budget_before_provider_admission(
    serving: Serving, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("newsloom_agent.app.REQUEST_SECONDS", 0.04)

    async def slow() -> AsyncIterator[bytes]:
        yield b'{"jsonrpc":'
        await asyncio.sleep(0.08)
        yield b'"2.0"}'

    response = await serving.http.post("/a2a", content=slow())
    assert response.status_code == 504
    assert not serving.reader.calls
    assert not serving.registry.records


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"Content-Type": "text/plain"}, 415),
        ({"A2A-Version": "0.3"}, 200),
        ({"A2A-Version": "NEWSLOOM_VERSION_CANARY"}, 200),
        ({"A2A-Extensions": "https://untrusted.invalid/NEWSLOOM_EXTENSION_CANARY"}, 200),
        ({"Host": "untrusted.invalid"}, 400),
        ({"Origin": "https://untrusted.invalid"}, 403),
    ],
)
async def test_protocol_host_and_origin_controls_refuse_before_work(
    serving: Serving, headers: Mapping[str, str], status: int
) -> None:
    response = await serving.http.post(
        "/a2a",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": invocation()},
    )
    assert response.status_code == status
    if status == 200:
        assert "error" in response.json()
    assert "CANARY" not in response.text
    assert not serving.reader.calls
    assert not serving.registry.records


@pytest.mark.parametrize(
    "configuration",
    [
        {"returnImmediately": True},
        {"taskPushNotificationConfig": {}},
        {"acceptedOutputModes": ["application/octet-stream"]},
        {"historyLength": -1},
        {"historyLength": 11},
    ],
)
async def test_unsupported_configuration_is_rejected_before_any_work(
    serving: Serving, configuration: Mapping[str, object]
) -> None:
    result = await serving.rpc(
        "SendMessage", {**invocation(), "configuration": dict(configuration)}
    )
    assert "error" in result.json()
    assert not serving.reader.calls
    assert not serving.registry.records


@pytest.mark.parametrize("length", [0, 1, 10])
async def test_configured_history_length_and_terminal_output_are_preserved(
    serving: Serving, length: int
) -> None:
    result = (
        await serving.rpc(
            "SendMessage", {**invocation(), "configuration": {"historyLength": length}}
        )
    ).json()["result"]["task"]
    assert len(result.get("history", [])) == min(length, 2)
    assert json.loads(result["status"]["message"]["parts"][0]["text"])["outcome"] == "empty"


async def test_invalid_protocol_inputs_never_echo_content_or_start_delegation(
    serving: Serving, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logging.getLogger(), "handlers", [SafeHandler()])
    payloads: tuple[object, ...] = (
        [],
        {"jsonrpc": "NEWSLOOM_PROTOCOL_CANARY", "id": 1, "method": "SendMessage", "params": {}},
        {"jsonrpc": "2.0", "id": True, "method": "SendMessage", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {"message": {"role": "NEWSLOOM_ROLE_CANARY"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {"NEWSLOOM_FIELD_CANARY": "NEWSLOOM_VALUE_CANARY"},
        },
    )
    for payload in payloads:
        response = await serving.http.post("/a2a", json=payload)
        assert "error" in response.json()
        assert "CANARY" not in response.text
    for raw in (b"{NEWSLOOM_JSON_CANARY", b"\xff"):
        response = await serving.http.post("/a2a", content=raw)
        assert "error" in response.json()
        assert "CANARY" not in response.text
    assert not serving.reader.calls
    assert not serving.registry.records
    assert "CANARY" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "failure", [AgentFailure("exchange_denied"), RuntimeError("NEWSLOOM_ERROR_CANARY")]
)
async def test_executor_failure_is_sanitized_without_empty_success(
    serving: Serving,
    failure: Exception,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging.getLogger(), "handlers", [SafeHandler()])
    serving.reader.failure = failure
    result = (await serving.invoke()).json()["result"]["task"]
    assert result["status"]["state"] == "TASK_STATE_FAILED"
    category = "exchange_denied" if isinstance(failure, AgentFailure) else "agent_execution_failed"
    assert result["status"]["message"]["parts"][0]["text"] == category
    assert "NEWSLOOM_ERROR_CANARY" not in json.dumps(result)
    assert "CANARY" not in capsys.readouterr().out
    assert len(serving.reader.calls) == 1
