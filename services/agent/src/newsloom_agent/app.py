"""Truthful discovery and guarded, request-owned A2A JSON-RPC."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from a2a.server.request_handlers.response_helpers import build_error_response
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.routes.jsonrpc_dispatcher import JsonRpcDispatcher
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    AuthorizationCodeOAuthFlow,
    OAuth2SecurityScheme,
    OAuthFlows,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)
from a2a.utils.errors import InvalidParamsError, InvalidRequestError
from agent_framework.observability import disable_instrumentation
from google.protobuf.json_format import ParseDict, ParseError
from newsloom_core.diagnostics import event
from starlette.applications import Starlette
from starlette.datastructures import URL, Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from newsloom_agent.auth import AgentAuthentication, AgentVerifier, request_authorization
from newsloom_agent.generation import NewsGenerator
from newsloom_agent.models import AgentFailure
from newsloom_agent.serving import AgentHandler, PrivateContextBuilder, RecentReader, TaskRegistry
from newsloom_agent.telemetry import AgentObserver

MAX_BODY_BYTES = 64 * 1024
MAX_ACTIVE_REQUESTS = 4
REQUEST_SECONDS = 120
PUBLIC_PATHS = {"/.well-known/agent-card.json", "/health/live"}


def agent_card(
    public_url: str, tenant: UUID, audience: UUID, *, streaming: bool = False
) -> AgentCard:
    scope = f"api://{audience}/news.agent"
    authority = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    return AgentCard(
        name="Newsloom recent-news access",
        description=(
            "One delegated stored-news read and one bounded streamed briefing. No full research."
            if streaming
            else "One delegated stored-news read. No generation, streaming or full research."
        ),
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(url=public_url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(streaming=streaming, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        security_schemes={
            "entra": SecurityScheme(
                oauth2_security_scheme=OAuth2SecurityScheme(
                    flows=OAuthFlows(
                        authorization_code=AuthorizationCodeOAuthFlow(
                            authorization_url=f"{authority}/authorize",
                            token_url=f"{authority}/token",
                            scopes={scope: "Invoke the recent-news access demonstrator"},
                            pkce_required=True,
                        )
                    )
                )
            )
        },
        security_requirements=[SecurityRequirement(schemes={"entra": StringList(list=[scope])})],
        skills=[
            AgentSkill(
                id="recent-news",
                name="Read recent stored news",
                description=(
                    "Send recent-news for one get_recent_news(limit=1) result. "
                    + (
                        "A nonempty result gets one bounded streamed briefing. "
                        "No independent retrieval."
                        if streaming
                        else "An empty result is explicit; no generated answer "
                        "or independent retrieval."
                    )
                ),
                tags=["stored-news", "delegated-access"],
                examples=["recent-news"],
            )
        ],
    )


class Ingress:
    def __init__(
        self,
        app: ASGIApp,
        allowed_origins: tuple[str, ...],
        observer: AgentObserver | None = None,
    ) -> None:
        self.app, self.allowed_origins = app, allowed_origins
        self.observer = observer
        self.active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started, status, cancelled, completed = time.monotonic(), 500, False, False

        async def observed_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.http(scope, receive, observed_send)
            completed = True
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            if self.observer is not None:
                path = scope["path"]
                surface = (
                    "a2a"
                    if path == "/a2a"
                    else "metadata"
                    if path == "/.well-known/agent-card.json"
                    else "health"
                    if path == "/health/live"
                    else "other"
                )
                outcome = (
                    "cancelled"
                    if cancelled or scope.get("newsloom.agent.disconnected") is True
                    else "failure"
                    if not completed
                    else "unauthorized"
                    if status == 401
                    else "forbidden"
                    if status == 403
                    else "overloaded"
                    if status == 429
                    else "success"
                    if 200 <= status < 300
                    else "failure"
                )
                self.observer.http(surface, outcome, time.monotonic() - started)

    async def http(self, scope: Scope, receive: Receive, send: Send) -> None:
        origins = Headers(scope=scope).getlist("origin")
        if origins and (len(origins) != 1 or origins[0] not in self.allowed_origins):
            await JSONResponse({"error": "origin_denied"}, status_code=403)(scope, receive, send)
            return
        if scope["method"] == "GET" and scope["path"] in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        if self.active >= MAX_ACTIVE_REQUESTS:
            event("agent_http", "", outcome="overloaded", category="request_capacity")
            await JSONResponse({"error": "request_capacity"}, status_code=429)(scope, receive, send)
            return
        self.active += 1
        deadline = time.monotonic() + REQUEST_SECONDS
        scope["newsloom.agent.deadline"] = deadline
        started = False

        async def track(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            async with asyncio.timeout_at(deadline):
                await self.app(scope, receive, track)
        except TimeoutError:
            event("agent_http", "", outcome="failure", category="request_timeout")
            if started:
                raise
            await JSONResponse({"error": "request_timeout"}, status_code=504)(scope, receive, send)
        finally:
            self.active -= 1


class RpcBoundary:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/a2a":
            await self.app(scope, receive, send)
            return
        authorization = request_authorization(scope)
        headers = Headers(scope=scope)
        if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            await JSONResponse({"error": "json_content_type_required"}, status_code=415)(
                scope, receive, send
            )
            return
        body = bytearray()
        async with asyncio.timeout_at(authorization.deadline):
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    scope["newsloom.agent.disconnected"] = True
                    event("agent_http", "", outcome="cancelled", category="disconnected")
                    return
                if message["type"] != "http.request":
                    raise RuntimeError("invalid_http_receive_event")
                if len(body) + len(message.get("body", b"")) > MAX_BODY_BYTES:
                    await JSONResponse({"error": "request_body_limit"}, status_code=413)(
                        scope, receive, send
                    )
                    return
                body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            request_id: str | int | None = None
            try:
                payload: object = json.loads(body)
                if not isinstance(payload, dict):
                    raise InvalidRequestError(message="invalid_request")
                raw_id = payload.get("id")
                if isinstance(raw_id, bool) or not isinstance(raw_id, str | int):
                    raise InvalidRequestError(message="invalid_request_id")
                if isinstance(raw_id, str) and len(raw_id) > 128:
                    raise InvalidRequestError(message="invalid_request_id")
                request_id = raw_id
                if (
                    payload.get("jsonrpc") != "2.0"
                    or not isinstance(payload.get("method"), str)
                    or not isinstance(payload.get("params"), dict)
                    or set(payload) - {"jsonrpc", "id", "method", "params"}
                    or Headers(scope=scope).getlist("a2a-version") != ["1.0"]
                    or headers.getlist("a2a-extensions")
                ):
                    raise InvalidRequestError(message="invalid_request")
                model = JsonRpcDispatcher.METHOD_TO_MODEL.get(payload["method"])
                if model is not None:
                    ParseDict(
                        payload["params"],
                        model(),
                        ignore_unknown_fields=False,
                        max_recursion_depth=16,
                    )
            except (InvalidRequestError, InvalidParamsError) as error:
                await JSONResponse(build_error_response(request_id, error))(scope, receive, send)
                return
            except ValueError, ParseError, RecursionError, TypeError:
                await JSONResponse(
                    build_error_response(request_id, InvalidParamsError(message="invalid_params"))
                )(scope, receive, send)
                return

            consumed = False
            disconnected = False
            disconnect = asyncio.Event()

            async def replay() -> Message:
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                await disconnect.wait()
                return {"type": "http.disconnect"}

            async def watch() -> None:
                nonlocal disconnected
                while True:
                    incoming = await receive()
                    if incoming["type"] == "http.disconnect":
                        disconnected = True
                        scope["newsloom.agent.disconnected"] = True
                        disconnect.set()
                        worker.cancel()
                        return

            async def dispatch() -> None:
                await self.app(scope, replay, send)

            worker = asyncio.create_task(dispatch())
            watcher = asyncio.create_task(watch())
            try:
                await worker
            except asyncio.CancelledError:
                if not disconnected:
                    raise
                event("agent_http", "", outcome="cancelled", category="disconnected")
            finally:
                worker.cancel()
                watcher.cancel()
                await asyncio.gather(worker, watcher, return_exceptions=True)


def create_app(
    reader: RecentReader,
    verifier: AgentVerifier,
    *,
    public_url: str,
    registry: TaskRegistry | None = None,
    allowed_origins: tuple[str, ...] = (),
    generator: NewsGenerator | None = None,
    observer: AgentObserver | None = None,
) -> ASGIApp:
    disable_instrumentation()
    url = URL(public_url)
    host = url.hostname
    if (
        not host
        or url.path != "/a2a"
        or url.username
        or url.password
        or url.query
        or url.fragment
        or (
            url.scheme != "https"
            and not (url.scheme == "http" and host in ("localhost", "127.0.0.1"))
        )
        or (url.scheme == "https" and url.port not in (None, 443))
    ):
        raise AgentFailure("invalid_public_url")
    registry = registry if registry is not None else TaskRegistry()
    card = agent_card(
        public_url, verifier.tenant, UUID(verifier.audience), streaming=generator is not None
    )

    async def live(request: Request) -> JSONResponse:
        return JSONResponse({"status": "live"})

    @asynccontextmanager
    async def lifespan(application: Starlette) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await registry.close()

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/health/live", live, methods=["GET"]),
            *create_agent_card_routes(card),
            *create_jsonrpc_routes(
                AgentHandler(reader, registry, generator, observer),
                "/a2a",
                context_builder=PrivateContextBuilder(),
                enable_v0_3_compat=False,
            ),
        ],
    )
    return TrustedHostMiddleware(
        Ingress(AgentAuthentication(RpcBoundary(app), verifier), allowed_origins, observer),
        allowed_hosts=[host, "localhost", "127.0.0.1"],
    )
