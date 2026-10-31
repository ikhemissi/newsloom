"""Explicit browser PKCE acceptance client; credentials and results stay in memory."""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID, uuid4

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    GetTaskRequest,
    Message,
    Part,
    Role,
    SendMessageRequest,
    TaskState,
    TaskStatus,
)
from a2a.utils.errors import A2AError
from google.protobuf.json_format import Parse
from google.protobuf.struct_pb2 import Value
from pydantic import field_validator, model_validator

from newsloom_agent.auth import AgentVerifier
from newsloom_agent.delegation import DelegationConfig
from newsloom_agent.generation import MAX_GENERATED_TOKENS, MAX_OUTPUT_BYTES
from newsloom_agent.models import AgentFailure, RecentNews
from newsloom_agent.research_models import MAX_ANSWER_BYTES, ResearchReceipt, ResearchRequest
from newsloom_agent.runtime import Config

CALLBACK = "http://127.0.0.1:8400/callback"
SIGN_IN_SECONDS = 180
MAX_SIGN_IN_BYTES = 32 * 1024
RESEARCH_CLIENT_FAILURES = {
    "agent_research_acceptance_unavailable",
    "agent_research_acceptance_response_invalid",
    "agent_research_not_completed",
    "agent_research_remote_failed",
    "agent_research_event_limit",
    "agent_research_artifact_invalid",
    "agent_research_answer_limit",
    "agent_research_progress_invalid",
    "agent_research_readback_invalid",
    "agent_client_transport_boundary",
}


class ClientSettings(DelegationConfig):
    public_client_id: UUID
    resource_url: str

    @field_validator("resource_url")
    @classmethod
    def trusted_interface(cls, value: str) -> str:
        return Config.https_interface(value)

    @model_validator(mode="after")
    def separate_public_client(self) -> ClientSettings:
        if self.public_client_id in (self.agent_client_id, self.mcp_audience):
            raise ValueError("separate_public_client_required")
        return self

    @property
    def invoke_scope(self) -> str:
        return f"api://{self.agent_client_id}/news.agent"

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> ClientSettings:
        return cls.model_validate(
            {
                "tenant": env["AGENT_TENANT_ID"],
                "agent_client_id": env["AGENT_API_CLIENT_ID"],
                "mcp_audience": env["MCP_API_CLIENT_ID"],
                "mcp_url": env["MCP_RESOURCE_URL"],
                "public_client_id": env["AGENT_PUBLIC_CLIENT_ID"],
                "resource_url": env["AGENT_RESOURCE_URL"],
            }
        )


@dataclass(frozen=True, repr=False)
class ProofKey:
    verifier: str
    state: str

    @classmethod
    def create(cls) -> ProofKey:
        return cls(secrets.token_urlsafe(48), secrets.token_urlsafe(32))

    @property
    def challenge(self) -> str:
        return (
            base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

    def authorization_url(self, settings: ClientSettings) -> str:
        query = urlencode(
            {
                "client_id": str(settings.public_client_id),
                "response_type": "code",
                "redirect_uri": CALLBACK,
                "response_mode": "query",
                "scope": settings.invoke_scope,
                "code_challenge": self.challenge,
                "code_challenge_method": "S256",
                "state": self.state,
                "prompt": "select_account",
            }
        )
        return f"https://login.microsoftonline.com/{settings.tenant}/oauth2/v2.0/authorize?{query}"


def callback_code(header: bytes, state: str) -> str:
    try:
        lines = header.decode("ascii").split("\r\n")
        method, target, version = lines[0].split(" ")
        headers = [line.split(":", 1) for line in lines[1:] if line]
        hosts = [value.strip() for key, value in headers if key.lower() == "host"]
        url = urlsplit(target)
        query = parse_qs(url.query, strict_parsing=True, max_num_fields=10)
        if (
            method != "GET"
            or version != "HTTP/1.1"
            or url.scheme
            or url.netloc
            or url.path != "/callback"
            or url.fragment
            or hosts != ["127.0.0.1:8400"]
            or query.get("state") != [state]
            or "error" in query
            or len(query.get("code", [])) != 1
            or not query["code"][0]
        ):
            raise AgentFailure("browser_callback_invalid")
        return query["code"][0]
    except ValueError, UnicodeError:
        raise AgentFailure("browser_callback_invalid") from None


async def authorization_code(settings: ClientSettings, proof: ProofKey, deadline: float) -> str:
    loop = asyncio.get_running_loop()
    result: asyncio.Future[str] = loop.create_future()
    callbacks: set[asyncio.Task[None]] = set()

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout_at(deadline):
                try:
                    header = await reader.readuntil(b"\r\n\r\n")
                    code = callback_code(header, proof.state)
                except asyncio.LimitOverrunError, asyncio.IncompleteReadError, AgentFailure:
                    if not result.done():
                        result.set_exception(AgentFailure("browser_callback_invalid"))
                    response = (
                        b"HTTP/1.1 400 Bad Request\r\n"
                        b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                else:
                    if not result.done():
                        result.set_result(code)
                    response = (
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                        b"Content-Length: 34\r\nConnection: close\r\n\r\n"
                        b"Sign-in received. Close this tab.\n"
                    )
                writer.write(response)
                await writer.drain()
        except ConnectionError, OSError, TimeoutError:
            if not result.done():
                result.set_exception(AgentFailure("browser_callback_unavailable"))
        finally:
            writer.close()
            try:
                async with asyncio.timeout_at(deadline):
                    await writer.wait_closed()
            except ConnectionError, OSError, TimeoutError:
                if not result.done():
                    result.set_exception(AgentFailure("browser_callback_unavailable"))

    def connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(receive(reader, writer))
        callbacks.add(task)
        task.add_done_callback(callbacks.discard)

    try:
        server = await asyncio.start_server(
            connected, "127.0.0.1", 8400, limit=16 * 1024, backlog=4
        )
    except OSError:
        raise AgentFailure("browser_callback_port_unavailable") from None
    try:
        async with server, asyncio.timeout_at(deadline):
            opened = await asyncio.to_thread(webbrowser.open, proof.authorization_url(settings))
            if not opened:
                raise AgentFailure("browser_unavailable")
            return await result
    finally:
        server.close()
        await server.wait_closed()
        for task in tuple(callbacks):
            task.cancel()
        await asyncio.gather(*callbacks, return_exceptions=True)
        if result.done() and not result.cancelled():
            result.exception()
        else:
            result.cancel()


async def sign_in(
    settings: ClientSettings,
    http: httpx.AsyncClient,
    get_code: Callable[[ClientSettings, ProofKey, float], Awaitable[str]] = authorization_code,
) -> str:
    deadline = time.monotonic() + SIGN_IN_SECONDS
    proof = ProofKey.create()
    try:
        async with asyncio.timeout_at(deadline):
            code = await get_code(settings, proof, deadline)
            async with http.stream(
                "POST",
                f"https://login.microsoftonline.com/{settings.tenant}/oauth2/v2.0/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": str(settings.public_client_id),
                    "redirect_uri": CALLBACK,
                    "scope": settings.invoke_scope,
                    "code": code,
                    "code_verifier": proof.verifier,
                },
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise AgentFailure("browser_token_denied")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_SIGN_IN_BYTES:
                        raise AgentFailure("browser_token_response_limit")
            payload: object = json.loads(body)
            if not isinstance(payload, dict):
                raise AgentFailure("browser_token_response_invalid")
            token: object = payload.get("access_token")
            if (
                not isinstance(token, str)
                or not 1 <= len(token) <= 16 * 1024
                or payload.get("token_type") != "Bearer"
                or "refresh_token" in payload
            ):
                raise AgentFailure("browser_token_response_invalid")
            caller = await AgentVerifier(
                http, settings.tenant, settings.agent_client_id
            ).authenticate(token, deadline)
            if caller.client_id != settings.public_client_id:
                raise AgentFailure("browser_client_mismatch")
            return token
    except httpx.HTTPError, TimeoutError:
        raise AgentFailure("browser_sign_in_unavailable") from None
    except ValueError:
        raise AgentFailure("browser_token_response_invalid") from None


def validate_card(
    card: AgentCard, settings: ClientSettings, *, streaming: bool, research: bool = False
) -> None:
    skills = [skill.id for skill in card.skills]
    has_research = skills == ["recent-news", "research"]
    if (
        len(card.supported_interfaces) != 1
        or card.supported_interfaces[0].url != settings.resource_url
        or card.supported_interfaces[0].protocol_binding != "JSONRPC"
        or card.supported_interfaces[0].protocol_version != "1.0"
        or card.capabilities.streaming != streaming
        or card.capabilities.push_notifications
        or (skills != ["recent-news"] and not has_research)
        or (research and not has_research)
        or list(card.default_input_modes)
        != (["text/plain", "application/json"] if has_research else ["text/plain"])
        or card.default_output_modes != ["text/plain"]
        or set(card.security_schemes) != {"entra"}
        or set(
            card.security_schemes["entra"].oauth2_security_scheme.flows.authorization_code.scopes
        )
        != {settings.invoke_scope}
        or not card.security_schemes[
            "entra"
        ].oauth2_security_scheme.flows.authorization_code.pkce_required
        or len(card.security_requirements) != 1
        or set(card.security_requirements[0].schemes) != {"entra"}
        or list(card.security_requirements[0].schemes["entra"].list) != [settings.invoke_scope]
    ):
        raise AgentFailure("agent_card_contract_mismatch")


async def invoke(
    settings: ClientSettings, token: str, http: httpx.AsyncClient, *, streaming: bool = False
) -> dict[str, int]:
    origin = settings.resource_url.removesuffix("/a2a")
    try:
        if http.headers.get("authorization"):
            raise AgentFailure("client_public_transport_required")
        card = await A2ACardResolver(http, origin).get_agent_card()
        validate_card(card, settings, streaming=streaming)
        params = {
            "jsonrpc": "2.0",
            "id": "acceptance",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": str(uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"text": "recent-news"}],
                }
            },
        }
        for bearer in (None, "invalid-authorization"):
            headers = {"A2A-Version": "1.0"}
            if bearer is not None:
                headers["Authorization"] = f"Bearer {bearer}"
            denied = await http.post(settings.resource_url, json=params, headers=headers)
            if denied.status_code != 401:
                raise AgentFailure("agent_auth_denial_not_observed")
        cross_resource = await http.post(
            settings.mcp_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": "acceptance", "method": "tools/list"},
        )
        if cross_resource.status_code not in (401, 403):
            raise AgentFailure("agent_to_mcp_audience_denial_not_observed")

        async def guard(request: httpx.Request) -> None:
            if (
                str(request.url) != settings.resource_url
                or request.method != "POST"
                or request.headers.get("authorization") != f"Bearer {token}"
            ):
                raise AgentFailure("agent_client_transport_boundary")

        async with httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            timeout=120,
            headers={"Authorization": f"Bearer {token}"},
            event_hooks={"request": [guard]},
        ) as authorized:
            client = ClientFactory(
                ClientConfig(
                    streaming=streaming,
                    httpx_client=authorized,
                    supported_protocol_bindings=["JSONRPC"],
                )
            ).create(card)
            try:
                async with asyncio.timeout(120):
                    responses = [
                        response
                        async for response in client.send_message(
                            SendMessageRequest(
                                message=Message(
                                    message_id=str(uuid4()),
                                    role=Role.ROLE_USER,
                                    parts=[Part(text="recent-news")],
                                )
                            )
                        )
                    ]
                    if not responses:
                        raise AgentFailure("agent_response_missing")
                    streamed = [
                        response.artifact_update.artifact.parts[0].text
                        for response in responses
                        if response.HasField("artifact_update")
                        and len(response.artifact_update.artifact.parts) == 1
                    ]
                    task = await client.get_task(
                        GetTaskRequest(id=responses[-1].task.id, history_length=2)
                    )
                    if (
                        task.status.state != TaskState.TASK_STATE_COMPLETED
                        or not task.history
                        or len(task.history[-1].parts) != 1
                    ):
                        raise AgentFailure("agent_delegation_not_completed")
                    payload: object = json.loads(task.history[-1].parts[0].text)
                    if streaming:
                        if (
                            not isinstance(payload, dict)
                            or set(payload)
                            != {
                                "outcome",
                                "items",
                                "user_preserved",
                                "generated",
                                "generation_calls",
                                "output_tokens",
                            }
                            or payload.get("outcome") != "news"
                            or payload.get("items") != 1
                            or payload.get("user_preserved") is not True
                            or payload.get("generated") is not True
                            or payload.get("generation_calls") != 1
                            or not isinstance(payload.get("output_tokens"), int)
                            or not 0 <= payload["output_tokens"] <= MAX_GENERATED_TOKENS
                            or not streamed
                            or not 0 < len("".join(streamed).encode()) <= MAX_OUTPUT_BYTES
                            or len(task.artifacts) != 1
                            or len(task.artifacts[0].parts) != 1
                            or task.artifacts[0].parts[0].text != "".join(streamed)
                        ):
                            raise AgentFailure("agent_streaming_receipt_invalid")
                        return {
                            "items": 1,
                            "user_preserved": 1,
                            "agent_auth_denials": 2,
                            "cross_audience_denials": 1,
                            "task_reads": 1,
                            "artifact_events": len(streamed),
                            "generation_calls": 1,
                            "output_tokens": payload["output_tokens"],
                        }
                    if (
                        not isinstance(payload, dict)
                        or set(payload) != {"outcome", "news", "user_preserved"}
                        or payload.get("outcome") != "news"
                        or payload.get("user_preserved") is not True
                    ):
                        raise AgentFailure("agent_delegation_receipt_invalid")
                    news = RecentNews.model_validate(payload["news"])
                    if len(news.items) != 1:
                        raise AgentFailure("agent_news_missing")
                    return {
                        "items": 1,
                        "user_preserved": 1,
                        "agent_auth_denials": 2,
                        "cross_audience_denials": 1,
                        "task_reads": 1,
                    }
            finally:
                await client.close()
    except A2AError, httpx.HTTPError, TimeoutError:
        raise AgentFailure("agent_acceptance_unavailable") from None
    except ValueError:
        raise AgentFailure("agent_acceptance_response_invalid") from None


async def verify_delegation(*, streaming: bool = False) -> dict[str, int]:
    settings = ClientSettings.from_environment(os.environ)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10) as http:
        token = await sign_in(settings, http)
        return await invoke(settings, token, http, streaming=streaming)


@dataclass(frozen=True, repr=False)
class ResearchInvocation:
    text: str
    counts: dict[str, int]
    receipt: ResearchReceipt | None = None


def research_message(request: ResearchRequest) -> SendMessageRequest:
    return SendMessageRequest(
        message=Message(
            message_id=str(uuid4()),
            role=Role.ROLE_USER,
            parts=[
                Part(
                    data=Parse(request.model_dump_json(by_alias=True), Value()),
                    media_type="application/json",
                )
            ],
        )
    )


def raise_research_failure(status: TaskStatus) -> None:
    if status.state != TaskState.TASK_STATE_FAILED:
        return
    from newsloom_agent.telemetry import CATEGORIES

    if len(status.message.parts) == 1:
        part = status.message.parts[0]
        if part.WhichOneof("content") == "text" and part.text and part.text in CATEGORIES:
            raise AgentFailure(part.text)
    raise AgentFailure("agent_research_remote_failed")


async def invoke_research(
    settings: ClientSettings,
    token: str,
    http: httpx.AsyncClient,
    request: ResearchRequest,
    *,
    request_hook: Callable[[httpx.Request], Awaitable[None]] | None = None,
    response_hook: Callable[[httpx.Response], Awaitable[None]] | None = None,
) -> ResearchInvocation:
    try:
        if http.headers.get("authorization"):
            raise AgentFailure("client_public_transport_required")
        card = await A2ACardResolver(
            http, settings.resource_url.removesuffix("/a2a")
        ).get_agent_card()
        validate_card(card, settings, streaming=True, research=True)

        async def guard(outgoing: httpx.Request) -> None:
            if (
                str(outgoing.url) != settings.resource_url
                or outgoing.method != "POST"
                or outgoing.headers.get_list("authorization") != [f"Bearer {token}"]
            ):
                raise AgentFailure("agent_client_transport_boundary")
            if request_hook is not None:
                await request_hook(outgoing)

        async with (
            asyncio.timeout(120),
            httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=120,
                headers={"Authorization": f"Bearer {token}"},
                event_hooks={
                    "request": [guard],
                    "response": [] if response_hook is None else [response_hook],
                },
            ) as authorized,
        ):
            client = ClientFactory(
                ClientConfig(
                    streaming=True,
                    httpx_client=authorized,
                    supported_protocol_bindings=["JSONRPC"],
                )
            ).create(card)
            try:
                chunks: list[str] = []
                task_id = ""
                progress_events = events = size = 0
                async for response in client.send_message(research_message(request)):
                    events += 1
                    if events > 64:
                        raise AgentFailure("agent_research_event_limit")
                    if response.HasField("task"):
                        raise_research_failure(response.task.status)
                        task_id = response.task.id
                    if response.HasField("artifact_update"):
                        artifact = response.artifact_update.artifact
                        if (
                            not progress_events
                            or len(artifact.parts) != 1
                            or artifact.parts[0].WhichOneof("content") != "text"
                        ):
                            raise AgentFailure("agent_research_artifact_invalid")
                        text = artifact.parts[0].text
                        size += len(text.encode())
                        if size > MAX_ANSWER_BYTES:
                            raise AgentFailure("agent_research_answer_limit")
                        chunks.append(text)
                    if response.HasField("status_update"):
                        status = response.status_update.status
                        raise_research_failure(status)
                        if status.state == TaskState.TASK_STATE_WORKING and status.message.parts:
                            if chunks or len(status.message.parts) != 1:
                                raise AgentFailure("agent_research_progress_invalid")
                            part = status.message.parts[0]
                            if part.WhichOneof("content") != "text":
                                raise AgentFailure("agent_research_progress_invalid")
                            progress: object = json.loads(part.text)
                            if (
                                not isinstance(progress, dict)
                                or set(progress) != {"phase", "tool_calls", "evidence_items"}
                                or progress.get("phase")
                                not in {"retrieving", "planning", "synthesizing", "validating"}
                                or type(progress.get("tool_calls")) is not int
                                or type(progress.get("evidence_items")) is not int
                                or not 0 <= progress["tool_calls"] <= 8
                                or not 0 <= progress["evidence_items"] <= 10
                            ):
                                raise AgentFailure("agent_research_progress_invalid")
                            progress_events += 1
                if not task_id or not chunks or not size:
                    raise AgentFailure("agent_research_not_completed")
                task = await client.get_task(GetTaskRequest(id=task_id, history_length=2))
                raise_research_failure(task.status)
                if (
                    task.status.state != TaskState.TASK_STATE_COMPLETED
                    or len(task.status.message.parts) != 1
                    or len(task.artifacts) != 1
                    or len(task.artifacts[0].parts) != 1
                    or task.artifacts[0].parts[0].text != "".join(chunks)
                ):
                    raise AgentFailure("agent_research_readback_invalid")
                receipt = ResearchReceipt.model_validate_json(task.status.message.parts[0].text)
                return ResearchInvocation(
                    "".join(chunks),
                    {
                        "items": receipt.items,
                        "user_preserved": 1,
                        "validated": 1,
                        "progress_events": progress_events,
                        "artifact_events": len(chunks),
                        "generation_calls": receipt.generation_calls,
                        "usage_observed_calls": receipt.usage_observed_calls,
                        "input_tokens": receipt.input_tokens,
                        "output_tokens": receipt.output_tokens,
                        "tool_calls": receipt.tool_calls,
                        "task_reads": 1,
                    },
                    receipt,
                )
            finally:
                await client.close()
    except A2AError, httpx.HTTPError, TimeoutError:
        raise AgentFailure("agent_research_acceptance_unavailable") from None
    except ValueError:
        raise AgentFailure("agent_research_acceptance_response_invalid") from None


async def verify_research(request: ResearchRequest) -> dict[str, int]:
    settings = ClientSettings.from_environment(os.environ)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10) as http:
        token = await sign_in(settings, http)
        return (await invoke_research(settings, token, http, request)).counts
