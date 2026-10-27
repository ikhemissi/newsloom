import asyncio
import socket
from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Literal, overload
from uuid import uuid4

import httpx
import pytest
import uvicorn
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    GetTaskRequest,
    Message,
    Part,
    Role,
    SendMessageRequest,
    TaskState,
)
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    Content,
    ResponseStream,
    ServiceSessionId,
    SupportsAgentRun,
)
from agent_framework.a2a import A2AExecutor
from newsloom_agent.cli import main
from starlette.applications import Starlette


class ProtocolProbe:
    """Deterministic test-only provider; no serving, identity or inference claim."""

    id = "protocol-probe"
    name: str | None = "Protocol probe"
    description: str | None = "Local SDK compatibility only."

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, object] | None = None,
        client_kwargs: Mapping[str, object] | None = None,
    ) -> Awaitable[AgentResponse[None]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, object] | None = None,
        client_kwargs: Mapping[str, object] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[None]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, object] | None = None,
        client_kwargs: Mapping[str, object] | None = None,
    ) -> Awaitable[AgentResponse[None]] | ResponseStream[AgentResponseUpdate, AgentResponse[None]]:
        if stream:
            return ResponseStream(self.updates(), finalizer=self.finalize)
        return self.response()

    async def updates(self) -> AsyncIterator[AgentResponseUpdate]:
        for text in ["local ", "protocol probe"]:
            yield AgentResponseUpdate(
                contents=[Content.from_text(text)],
                role="assistant",
                message_id="probe-message",
            )

    def finalize(self, updates: Sequence[AgentResponseUpdate]) -> AgentResponse[None]:
        return AgentResponse[None].from_updates(updates)

    async def response(self) -> AgentResponse[None]:
        return self.finalize([update async for update in self.updates()])

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(
        self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None
    ) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)


@asynccontextmanager
async def loopback_server(executor_streaming: bool) -> AsyncIterator[tuple[str, AgentCard]]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.setblocking(False)
        base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        card = AgentCard(
            name="Protocol probe",
            description="Local-only compatibility test, not the news agent.",
            version="0.1.0",
            supported_interfaces=[
                AgentInterface(
                    url=f"{base_url}/a2a", protocol_binding="JSONRPC", protocol_version="1.0"
                )
            ],
            capabilities=AgentCapabilities(streaming=True),
            default_input_modes=["text/plain"],
            default_output_modes=["text/plain"],
            skills=[
                AgentSkill(
                    id="probe",
                    name="Probe",
                    description="Local protocol test.",
                    tags=["compatibility"],
                )
            ],
        )
        probe: SupportsAgentRun = ProtocolProbe()
        handler = DefaultRequestHandler(
            agent_executor=A2AExecutor(probe, stream=executor_streaming),
            task_store=InMemoryTaskStore(),
            agent_card=card,
        )
        app = Starlette(
            routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/a2a")]
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                access_log=False,
                log_config=None,
                proxy_headers=False,
                lifespan="off",
            )
        )
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if serving.done():
                        await serving
                        pytest.fail("Loopback server stopped before readiness")
                    await asyncio.sleep(0.01)
            yield base_url, card
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 5)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("executor_streaming", [False, True])
async def test_pinned_framework_and_official_client_use_real_http(
    streaming: bool, executor_streaming: bool
) -> None:
    async with (
        loopback_server(executor_streaming) as (base_url, expected_card),
        httpx.AsyncClient(timeout=5, trust_env=False) as http,
    ):
        card = await A2ACardResolver(http, base_url).get_agent_card()
        assert card == expected_card
        client = ClientFactory(
            ClientConfig(
                streaming=streaming,
                httpx_client=http,
                supported_protocol_bindings=["JSONRPC"],
            )
        ).create(card)
        try:
            events = [
                event
                async for event in client.send_message(
                    SendMessageRequest(
                        message=Message(
                            message_id=uuid4().hex, role=Role.ROLE_USER, parts=[Part(text="probe")]
                        )
                    )
                )
            ]
            assert events
            task_id = events[0].task.id
            assert task_id
            task = await client.get_task(GetTaskRequest(id=task_id, history_length=10))
            assert task.status.state == TaskState.TASK_STATE_COMPLETED
            if executor_streaming:
                assert (
                    "".join(part.text for artifact in task.artifacts for part in artifact.parts)
                    == "local protocol probe"
                )
            else:
                assert not task.artifacts
                assert [
                    "".join(part.text for part in message.parts)
                    for message in task.history
                    if message.role == Role.ROLE_AGENT
                ] == ["local protocol probe"]
            if streaming:
                chunks = [
                    event.artifact_update for event in events if event.HasField("artifact_update")
                ]
                assert [
                    "".join(part.text for part in chunk.artifact.parts) for chunk in chunks
                ] == (["local ", "protocol probe"] if executor_streaming else [])
                if executor_streaming:
                    assert chunks[0].artifact.artifact_id == chunks[1].artifact.artifact_id
                    assert not chunks[0].append and chunks[1].append
                assert events[-1].status_update.status.state == TaskState.TASK_STATE_COMPLETED
            else:
                assert events[-1].task.status.state == TaskState.TASK_STATE_COMPLETED
        finally:
            await client.close()


def test_runtime_check_has_no_environment_or_network_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["newsloom-agent", "check-runtime"])
    main()


def test_cli_does_not_echo_invalid_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["newsloom-agent", "NEWSLOOM_CLI_SECRET_CANARY"])
    with pytest.raises(SystemExit, match="1"):
        main()
    captured = capsys.readouterr()
    assert "NEWSLOOM_CLI_SECRET_CANARY" not in captured.out + captured.err
