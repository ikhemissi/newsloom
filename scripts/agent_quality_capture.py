"""Root-environment capture primitives; no sign-in or network work on import."""

import asyncio
import hashlib
import json
import logging
import subprocess
import time
import webbrowser
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import httpx2
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.utils.errors import A2AError
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from newsloom_agent.auth import AgentVerifier, Caller, UserClaims
from newsloom_agent.client import (
    ClientSettings,
    ResearchInvocation,
    invoke_research,
    research_message,
    sign_in,
    validate_card,
)
from newsloom_agent.delegation import BoundedResponse, ResearchMcpSession, ResearchToolResult
from newsloom_agent.models import AgentFailure
from newsloom_agent.research_models import (
    DetailArguments,
    ItemResult,
    NewsDetail,
    RecentArguments,
    ResearchRequest,
    SearchArguments,
    SourcesArguments,
)
from newsloom_core.auth import EntraTokenVerifier
from pydantic import BaseModel, ValidationError

MCP_CALLBACK = "http://127.0.0.1:33418"
TOOLS: dict[str, type[BaseModel]] = {
    "get_news_item": DetailArguments,
    "get_recent_news": RecentArguments,
    "search_news": SearchArguments,
    "list_sources": SourcesArguments,
}


class WindowsDefaultBrowser(webbrowser.BaseBrowser):
    def __init__(self, executable: str) -> None:
        super().__init__(executable)

    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "login.microsoftonline.com"
            or any(char in url for char in ("\r", "\n", "\x00"))
        ):
            raise AgentFailure("baseline_browser_target")
        script = "Start-Process -FilePath '" + url.replace("'", "''") + "'\n"
        try:
            result = subprocess.run(
                [self.name, "-NoProfile", "-NonInteractive", "-Command", "-"],
                input=script.encode(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        except OSError, subprocess.TimeoutExpired:
            raise AgentFailure("baseline_browser_launch_failed") from None
        if result.returncode:
            raise AgentFailure("baseline_browser_launch_failed")
        return True


def configure_operator_browser() -> None:
    executable = Path("/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe")
    if executable.is_file():
        webbrowser.register(
            "baseline-windows", None, WindowsDefaultBrowser(str(executable)), preferred=True
        )


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True, repr=False)
class CaptureSettings:
    agent: ClientSettings
    mcp_public_client_id: UUID

    def __post_init__(self) -> None:
        if self.mcp_public_client_id in (
            self.agent.public_client_id,
            self.agent.agent_client_id,
            self.agent.mcp_audience,
        ):
            raise AgentFailure("baseline_capture_client_not_separate")

    @property
    def mcp_scope(self) -> str:
        return f"api://{self.agent.mcp_audience}/news.read"

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> CaptureSettings:
        agent = ClientSettings.from_environment(env)
        if UUID(env["MCP_TENANT_ID"]) != agent.tenant:
            raise AgentFailure("baseline_capture_tenant_mismatch")
        return cls(agent, UUID(env["MCP_PUBLIC_CLIENT_ID"]))


@dataclass
class CaptureLimits:
    operations: int = 0
    auth_requests: int = 0
    sign_ins: int = 0
    received: int = 0
    deadline: float = field(default_factory=lambda: time.monotonic() + 180)
    permit: Callable[[str, int], None] | None = field(default=None, repr=False)
    pending_tool: bool = field(default=False, repr=False)
    metadata_reads: int = 0
    limit_profile: Literal[
        "baseline-12x8-v1",
        "baseline-12x8-v2",
        "baseline-12x8-v3",
        "baseline-12x8-v4",
        "baseline-12x8-v5",
        "baseline-12x8-v6",
    ] = "baseline-12x8-v1"

    def authorize(self, operation: str, amount: int = 1) -> None:
        self.available()
        if self.permit is not None:
            self.permit(operation, amount)
        self.available()

    def available(self) -> None:
        if time.monotonic() >= self.deadline:
            raise AgentFailure("baseline_capture_deadline")

    def admit_tool(self, *, semantic_query: bool = False) -> None:
        self.available()
        if self.operations >= 160:
            raise AgentFailure("baseline_capture_operation_limit")
        self.authorize("semantic_evidence" if semantic_query else "evidence")
        self.operations += 1
        self.pending_tool = True

    def admit_metadata(self) -> None:
        maximum = (
            60
            if self.limit_profile == "baseline-12x8-v1"
            else 180
            if self.limit_profile in ("baseline-12x8-v5", "baseline-12x8-v6")
            else 120
        )
        if self.metadata_reads >= maximum:
            raise AgentFailure("baseline_capture_metadata_limit")
        self.authorize("metadata_before")
        self.metadata_reads += 1

    def admit_auth(self) -> None:
        self.available()
        if self.auth_requests >= 40:
            raise AgentFailure("baseline_capture_auth_limit")
        self.authorize("auth_http")
        self.auth_requests += 1

    def admit_sign_in(self) -> None:
        self.available()
        maximum = {
            "baseline-12x8-v1": 4,
            "baseline-12x8-v2": 6,
            "baseline-12x8-v3": 7,
            "baseline-12x8-v4": 9,
            "baseline-12x8-v5": 9,
            "baseline-12x8-v6": 9,
        }[self.limit_profile]
        if self.sign_ins >= maximum:
            raise AgentFailure("baseline_capture_sign_in_limit")
        self.authorize("sign_ins")
        self.sign_ins += 1

    def consume(self, size: int) -> None:
        if type(size) is not int or size < 0 or self.received + size > 10 * 1024 * 1024:
            raise AgentFailure("baseline_capture_response_limit")
        if size:
            self.authorize("evidence_bytes", size)
        self.received += size


@dataclass(repr=False)
class MemoryOAuth:
    settings: CaptureSettings
    tokens: OAuthToken | None = None

    @property
    def client_info(self) -> OAuthClientInformationFull:
        return OAuthClientInformationFull.model_validate(
            {
                "client_id": str(self.settings.mcp_public_client_id),
                "redirect_uris": [MCP_CALLBACK],
                "scope": self.settings.mcp_scope,
                "token_endpoint_auth_method": "none",
                "application_type": "native",
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
            }
        )

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        if (
            self.tokens is not None
            or tokens.token_type.lower() != "bearer"
            or tokens.refresh_token is not None
            or not 1 <= len(tokens.access_token) <= 16 * 1024
        ):
            raise AgentFailure("baseline_capture_token_not_admitted")
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        if (
            client_info.client_id != str(self.settings.mcp_public_client_id)
            or client_info.client_secret is not None
            or client_info.token_endpoint_auth_method != "none"
            or client_info.scope != self.settings.mcp_scope
            or tuple(map(str, client_info.redirect_uris or ()))
            != tuple(map(str, self.client_info.redirect_uris or ()))
        ):
            raise AgentFailure("baseline_capture_registration_forbidden")


class McpCallback:
    def __init__(self, settings: CaptureSettings, limits: CaptureLimits) -> None:
        self.settings, self.limits = settings, limits
        self.future: asyncio.Future[AuthorizationCodeResult] = (
            asyncio.get_running_loop().create_future()
        )
        self.tasks: set[asyncio.Task[None]] = set()
        self.server: asyncio.Server | None = None

    async def __aenter__(self) -> McpCallback:
        try:
            self.server = await asyncio.start_server(
                self.connected, "127.0.0.1", 33418, limit=16 * 1024, backlog=4
            )
        except OSError:
            raise AgentFailure("baseline_capture_callback_unavailable") from None
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if not self.future.done():
            self.future.cancel()
        elif not self.future.cancelled():
            self.future.exception()

    def connected(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(self.receive(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def receive(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout_at(self.limits.deadline):
                header = await reader.readuntil(b"\r\n\r\n")
                lines = header.decode("ascii").split("\r\n")
                method, target, version = lines[0].split(" ")
                headers = [line.split(":", 1) for line in lines[1:] if line]
                hosts = [value.strip() for key, value in headers if key.lower() == "host"]
                url = urlsplit(target)
                query = parse_qs(url.query, strict_parsing=True, max_num_fields=6)
                if (
                    method != "GET"
                    or version != "HTTP/1.1"
                    or url.scheme
                    or url.netloc
                    or url.path != "/"
                    or url.fragment
                    or hosts != ["127.0.0.1:33418"]
                    or set(query) - {"code", "state", "iss", "session_state"}
                    or len(query.get("code", [])) != 1
                    or len(query.get("state", [])) != 1
                    or len(query.get("iss", [])) > 1
                    or len(query.get("session_state", [])) > 1
                    or any(len(value) > 512 for value in query.get("session_state", []))
                    or self.future.done()
                ):
                    raise ValueError("invalid_callback")
                value = AuthorizationCodeResult(
                    code=query["code"][0],
                    state=query["state"][0],
                    iss=query.get("iss", [None])[0],
                )
                self.future.set_result(value)
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                    b"Content-Length: 34\r\nConnection: close\r\n\r\n"
                    b"Sign-in received. Close this tab.\n"
                )
                await writer.drain()
        except (
            ValueError,
            UnicodeError,
            asyncio.LimitOverrunError,
            asyncio.IncompleteReadError,
            ConnectionError,
            OSError,
            TimeoutError,
        ):
            if not self.future.done():
                self.future.set_exception(AgentFailure("baseline_capture_callback_invalid"))
            if not writer.is_closing():
                writer.write(
                    b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
        finally:
            writer.close()
            try:
                async with asyncio.timeout_at(self.limits.deadline):
                    await writer.wait_closed()
            except ConnectionError, OSError, TimeoutError:
                if not self.future.done():
                    self.future.set_exception(AgentFailure("baseline_capture_callback_unavailable"))

    async def redirect(self, url: str) -> None:
        self.limits.admit_sign_in()
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, strict_parsing=True, max_num_fields=16)
        if (
            parsed.scheme != "https"
            or parsed.fragment
            or parsed.netloc != "login.microsoftonline.com"
            or parsed.path != f"/{self.settings.agent.tenant}/oauth2/v2.0/authorize"
            or query.get("client_id") != [str(self.settings.mcp_public_client_id)]
            or query.get("redirect_uri") != [MCP_CALLBACK]
            or query.get("scope") != [self.settings.mcp_scope]
            or query.get("response_type") != ["code"]
            or query.get("code_challenge_method") != ["S256"]
            or len(query.get("state", [])) != 1
            or len(query.get("code_challenge", [])) != 1
        ):
            raise AgentFailure("baseline_capture_authorization_target")
        if not await asyncio.to_thread(webbrowser.open, url):
            raise AgentFailure("browser_unavailable")

    async def wait(self) -> AuthorizationCodeResult:
        async with asyncio.timeout_at(self.limits.deadline):
            return await self.future


async def verified_mcp_user(
    token: str,
    settings: CaptureSettings,
    caller: Caller,
    verifier: EntraTokenVerifier[UserClaims],
    deadline: float,
) -> UserClaims:
    async with asyncio.timeout_at(deadline):
        claims = await verifier.verify_claims(token)
    if (
        claims is None
        or claims.oid != caller.object_id
        or claims.tid != caller.tenant
        or claims.azp != settings.mcp_public_client_id
        or "news.read" not in claims.scp.split()
        or claims.exp <= time.time()
    ):
        raise AgentFailure("baseline_capture_user_mismatch")
    return claims


class EvidenceReader:
    def __init__(
        self,
        session: ResearchMcpSession,
        limits: CaptureLimits,
        *,
        caller: Caller,
        verify_user: Callable[[], Awaitable[None]],
        readiness: bool,
    ) -> None:
        self.session, self.limits, self.readiness = session, limits, readiness
        self.caller, self.verify_user = caller, verify_user
        self.denial: Callable[[httpx.AsyncClient, ResearchRequest, int], Awaitable[int]] | None = (
            None
        )

    async def call(self, name: str, arguments: dict[str, object]) -> ResearchToolResult:
        model = TOOLS.get(name)
        if model is None:
            raise AgentFailure("baseline_capture_tool_forbidden")
        try:
            value = model.model_validate(arguments)
        except ValidationError:
            raise AgentFailure("baseline_capture_arguments_invalid") from None
        if self.readiness and isinstance(value, SearchArguments) and value.query is not None:
            raise AgentFailure("baseline_capture_paid_preparation_forbidden")
        await self.verify_user()
        self.limits.admit_tool(
            semantic_query=isinstance(value, SearchArguments) and value.query is not None
        )
        self.session.result = None
        try:
            async with asyncio.timeout_at(min(self.limits.deadline, time.monotonic() + 90)):
                result = await self.session.call_tool(
                    name, value.model_dump(mode="json", by_alias=True)
                )
        except TimeoutError:
            raise AgentFailure("baseline_capture_deadline") from None
        if result.is_error or self.session.result is None:
            raise AgentFailure("baseline_capture_tool_failed")
        return self.session.result

    async def item(self, item_id: UUID) -> NewsDetail | None:
        value = await self.call("get_news_item", {"id": item_id})
        if not isinstance(value, ItemResult):
            raise AgentFailure("baseline_capture_item_invalid")
        return value.item


class PrivateDependencyLogs:
    def __init__(self) -> None:
        self.previous: dict[str, bool] = {}

    async def __aenter__(self) -> PrivateDependencyLogs:
        for name in tuple(logging.Logger.manager.loggerDict):
            if name == "mcp" or name.startswith(("mcp.", "httpx", "httpcore")):
                logger = logging.getLogger(name)
                self.previous[name] = logger.disabled
                logger.disabled = True
        return self

    async def __aexit__(self, *exc: object) -> None:
        for name, disabled in self.previous.items():
            logging.getLogger(name).disabled = disabled


@asynccontextmanager
async def evidence_session(
    settings: CaptureSettings,
    caller: Caller,
    limits: CaptureLimits,
    *,
    readiness: bool,
    transport: httpx2.AsyncBaseTransport | None = None,
    keys_transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[EvidenceReader]:
    store = MemoryOAuth(settings)
    base = settings.agent.mcp_url
    tenant = str(settings.agent.tenant)

    async def guard(request: httpx2.Request) -> None:
        limits.available()
        target = urlsplit(str(request.url))
        known_resource = str(request.url) == base and request.method in ("GET", "POST", "DELETE")
        known_metadata = (
            target.scheme == "https"
            and target.netloc == urlsplit(base).netloc
            and target.path
            in (
                "/.well-known/oauth-protected-resource",
                "/.well-known/oauth-protected-resource/mcp",
            )
            and not target.query
            and request.method == "GET"
        )
        known_entra = (
            target.scheme == "https"
            and target.netloc == "login.microsoftonline.com"
            and (
                (target.path == f"/{tenant}/oauth2/v2.0/token" and request.method == "POST")
                or (
                    target.path
                    in (
                        f"/.well-known/oauth-authorization-server/{tenant}/v2.0",
                        f"/.well-known/openid-configuration/{tenant}/v2.0",
                        f"/{tenant}/v2.0/.well-known/openid-configuration",
                        f"/{tenant}/v2.0/.well-known/oauth-authorization-server",
                    )
                    and request.method == "GET"
                )
            )
            and not target.query
        )
        if not (known_resource or known_metadata or known_entra):
            raise AgentFailure("baseline_capture_http_target")
        if known_resource:
            try:
                body: object = json.loads(request.content) if request.method == "POST" else {}
            except ValueError:
                raise AgentFailure("baseline_capture_http_request_invalid") from None
            if isinstance(body, dict) and body.get("method") == "tools/call":
                if not limits.pending_tool:
                    raise AgentFailure("baseline_capture_unadmitted_tool_dispatch")
                limits.pending_tool = False
            else:
                limits.admit_metadata()
        else:
            limits.admit_auth()

    async def bounded(response: httpx2.Response) -> None:
        received = 0

        def consume(size: int) -> None:
            nonlocal received
            received += size
            if received > 64 * 1024:
                raise AgentFailure("baseline_capture_response_limit")
            limits.consume(size)

        if response.is_stream_consumed:
            consume(len(response.content))
            return
        if not isinstance(response.stream, httpx2.AsyncByteStream):
            raise AgentFailure("baseline_capture_response_stream_invalid")
        response.stream = BoundedResponse(response.stream, consume=consume)

    async def guard_keys(request: httpx.Request) -> None:
        if (
            request.method != "GET"
            or str(request.url) != f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        ):
            raise AgentFailure("baseline_capture_keys_target")
        limits.admit_auth()

    async with (
        asyncio.timeout_at(limits.deadline),
        PrivateDependencyLogs(),
        McpCallback(settings, limits) as callback,
    ):
        provider = OAuthClientProvider(
            base,
            OAuthClientMetadata.model_validate(store.client_info.model_dump()),
            store,
            redirect_handler=callback.redirect,
            callback_handler=callback.wait,
        )
        async with (
            httpx2.AsyncClient(
                auth=provider,
                trust_env=False,
                follow_redirects=False,
                timeout=90,
                transport=transport,
                event_hooks={"request": [guard], "response": [bounded]},
            ) as http,
            httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=5,
                transport=keys_transport,
                event_hooks={"request": [guard_keys]},
            ) as keys,
            streamable_http_client(base, http_client=http, max_sse_event_size=64 * 1024) as streams,
            ResearchMcpSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            if store.tokens is None:
                raise AgentFailure("baseline_capture_token_missing")
            verifier = EntraTokenVerifier(
                keys, settings.agent.tenant, settings.agent.mcp_audience, UserClaims
            )
            await verified_mcp_user(
                store.tokens.access_token, settings, caller, verifier, limits.deadline
            )

            async def verify_user() -> None:
                if store.tokens is None:
                    raise AgentFailure("baseline_capture_token_missing")
                await verified_mcp_user(
                    store.tokens.access_token, settings, caller, verifier, limits.deadline
                )

            reader = EvidenceReader(
                session, limits, caller=caller, verify_user=verify_user, readiness=readiness
            )

            async def denial(
                public: httpx.AsyncClient, request: ResearchRequest, status: int
            ) -> int:
                await verify_user()
                if store.tokens is None:
                    raise AgentFailure("baseline_capture_token_missing")
                return await capture_denial(
                    settings,
                    public,
                    request,
                    expected_status=status,
                    wrong_audience_token=store.tokens.access_token,
                )

            reader.denial = denial
            yield reader


@dataclass(frozen=True, repr=False)
class TransientResearch:
    invocation: ResearchInvocation
    evidence: tuple[NewsDetail, ...]


class BoundedA2AResponse(httpx.AsyncByteStream):
    def __init__(self, source: httpx.AsyncByteStream) -> None:
        self.source = source

    async def __aiter__(self) -> AsyncIterator[bytes]:
        received = 0
        async for chunk in self.source:
            received += len(chunk)
            if received > 64 * 1024:
                raise AgentFailure("baseline_capture_response_limit")
            yield chunk

    async def aclose(self) -> None:
        await self.source.aclose()


class ResearchHttpAdmission:
    def __init__(self, limits: CaptureLimits) -> None:
        self.limits = limits
        self.sent = self.reads = 0

    async def request(self, request: httpx.Request) -> None:
        self.limits.available()
        try:
            data: object = json.loads(request.content)
        except ValueError:
            raise AgentFailure("baseline_capture_research_request_invalid") from None
        if not isinstance(data, dict):
            raise AgentFailure("baseline_capture_research_request_invalid")
        method = data.get("method")
        if method == "SendStreamingMessage" and not self.sent and not self.reads:
            self.sent = 1
        elif method == "GetTask" and self.sent == 1 and not self.reads:
            self.limits.authorize("task_reads")
            self.reads = 1
        else:
            raise AgentFailure("baseline_capture_research_dispatch_limit")

    async def response(self, response: httpx.Response) -> None:
        self.limits.available()
        if response.is_stream_consumed:
            if len(response.content) > 64 * 1024:
                raise AgentFailure("baseline_capture_response_limit")
        elif isinstance(response.stream, httpx.AsyncByteStream):
            response.stream = BoundedA2AResponse(response.stream)
        else:
            raise AgentFailure("baseline_capture_response_stream_invalid")


@asynccontextmanager
async def public_admission(
    settings: CaptureSettings, http: httpx.AsyncClient, limits: CaptureLimits
) -> AsyncIterator[None]:
    tenant = str(settings.agent.tenant)
    keys = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
    token = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    card = settings.agent.resource_url.removesuffix("/a2a") + "/.well-known/agent-card.json"

    async def guard(request: httpx.Request) -> None:
        target = str(request.url)
        if (request.method == "GET" and target == keys) or (
            request.method == "POST" and target == token
        ):
            limits.admit_auth()
        elif request.method == "GET" and target == card:
            limits.admit_metadata()
        else:
            raise AgentFailure("baseline_capture_public_http_target")

    bounded = ResearchHttpAdmission(limits).response
    http.event_hooks["request"].append(guard)
    http.event_hooks["response"].append(bounded)
    try:
        yield
    finally:
        http.event_hooks["request"].remove(guard)
        http.event_hooks["response"].remove(bounded)


class EvidenceSource(Protocol):
    @property
    def caller(self) -> Caller: ...

    @property
    def limits(self) -> CaptureLimits: ...

    async def item(self, item_id: UUID) -> NewsDetail | None: ...


async def capture_research(
    settings: CaptureSettings,
    token: str,
    public: httpx.AsyncClient,
    reader: EvidenceSource,
    request: ResearchRequest,
    expected: Mapping[UUID, str | None],
) -> TransientResearch:
    async with public_admission(settings, public, reader.limits):
        caller = await AgentVerifier(
            public, settings.agent.tenant, settings.agent.agent_client_id
        ).authenticate(token, min(reader.limits.deadline, time.monotonic() + 120))
    if (
        caller.client_id != settings.agent.public_client_id
        or caller.object_id != reader.caller.object_id
        or caller.tenant != reader.caller.tenant
    ):
        raise AgentFailure("baseline_capture_agent_client_mismatch")
    evidence: list[NewsDetail] = []
    for item_id, expected_hash in expected.items():
        item = await reader.item(item_id)
        actual = None if item is None else fingerprint(item.model_dump(mode="json"))
        if actual != expected_hash:
            raise AgentFailure("baseline_capture_evidence_drift")
        if item is not None:
            evidence.append(item)
    admission = ResearchHttpAdmission(reader.limits)
    async with public_admission(settings, public, reader.limits):
        result = await invoke_research(
            settings.agent,
            token,
            public,
            request,
            request_hook=admission.request,
            response_hook=admission.response,
        )
    if admission.sent != 1 or admission.reads != 1:
        raise AgentFailure("baseline_capture_research_dispatch_incomplete")
    if result.receipt is None:
        raise AgentFailure("baseline_capture_receipt_missing")
    for item_id, expected_hash in expected.items():
        item = await reader.item(item_id)
        if (None if item is None else fingerprint(item.model_dump(mode="json"))) != expected_hash:
            raise AgentFailure("baseline_capture_evidence_drift")
    return TransientResearch(result, tuple(evidence))


async def sign_in_agent(
    settings: CaptureSettings, public: httpx.AsyncClient, limits: CaptureLimits
) -> tuple[str, Caller]:
    limits.admit_sign_in()
    async with asyncio.timeout_at(limits.deadline), public_admission(settings, public, limits):
        token = await sign_in(settings.agent, public)
        caller = await AgentVerifier(
            public, settings.agent.tenant, settings.agent.agent_client_id
        ).authenticate(token, limits.deadline)
    return token, caller


async def capture_denial(
    settings: CaptureSettings,
    public: httpx.AsyncClient,
    request: ResearchRequest,
    *,
    expected_status: int,
    wrong_audience_token: str | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    if expected_status not in (401, 403):
        raise AgentFailure("baseline_capture_denial_status_invalid")
    card = await A2ACardResolver(
        public, settings.agent.resource_url.removesuffix("/a2a")
    ).get_agent_card()
    validate_card(card, settings.agent, streaming=True, research=True)
    headers = (
        {} if wrong_audience_token is None else {"Authorization": f"Bearer {wrong_audience_token}"}
    )
    sent = 0
    statuses: list[int] = []

    async def guard(request: httpx.Request) -> None:
        nonlocal sent
        if (
            request.method != "POST"
            or str(request.url) != settings.agent.resource_url
            or request.headers.get_list("authorization")
            != ([] if wrong_audience_token is None else [f"Bearer {wrong_audience_token}"])
            or sent != 0
        ):
            raise AgentFailure("baseline_capture_denial_dispatch")
        sent += 1

    async def response(value: httpx.Response) -> None:
        statuses.append(value.status_code)
        if value.is_stream_consumed:
            if len(value.content) > 64 * 1024:
                raise AgentFailure("baseline_capture_response_limit")
        elif isinstance(value.stream, httpx.AsyncByteStream):
            value.stream = BoundedA2AResponse(value.stream)
        else:
            raise AgentFailure("baseline_capture_response_stream_invalid")

    async with (
        PrivateDependencyLogs(),
        asyncio.timeout(120),
        httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            timeout=120,
            transport=transport,
            headers=headers,
            event_hooks={"request": [guard], "response": [response]},
        ) as http,
    ):
        client = ClientFactory(
            ClientConfig(streaming=True, httpx_client=http, supported_protocol_bindings=["JSONRPC"])
        ).create(card)
        try:
            async for _ in client.send_message(research_message(request)):
                raise AgentFailure("baseline_capture_denial_unexpected_success")
        except A2AError, httpx.HTTPError:
            if statuses == [expected_status] and sent == 1:
                return expected_status
            raise AgentFailure("baseline_capture_denial_unverified") from None
        finally:
            await client.close()
    raise AgentFailure("baseline_capture_denial_unverified")
