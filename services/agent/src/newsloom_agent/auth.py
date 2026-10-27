"""Agent-only delegated authorization; verified identities remain request-private."""

import asyncio
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

import httpx
from newsloom_core.auth import Claims, EntraTokenVerifier, TrustedKeysFailure
from newsloom_core.diagnostics import event
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from newsloom_agent.models import AgentFailure


class UserClaims(Claims):
    oid: UUID
    idtyp: Literal["user"] | None = None
    nonce: None = None


@dataclass(frozen=True, repr=False)
class Caller:
    tenant: UUID
    object_id: UUID
    client_id: UUID
    subject: str
    expires_at: int
    assertion: str


@dataclass(frozen=True, repr=False)
class Authorization:
    caller: Caller
    deadline: float
    producers: set[asyncio.Task[object]] = field(default_factory=set, compare=False)


_authorization: ContextVar[Authorization | None] = ContextVar("agent_authorization", default=None)


def current_authorization() -> Authorization:
    authorization = _authorization.get()
    if authorization is None:
        raise AgentFailure("missing_authorization")
    return authorization


class AgentVerifier(EntraTokenVerifier[UserClaims]):
    def __init__(self, client: httpx.AsyncClient, tenant: UUID, audience: UUID) -> None:
        super().__init__(client, tenant, audience, UserClaims)

    async def authenticate(self, token: str, deadline: float) -> Caller:
        if time.monotonic() >= deadline:
            raise AgentFailure("authorization_timeout")
        try:
            async with asyncio.timeout_at(deadline):
                claims = await self.verify_claims(token)
        except TrustedKeysFailure as error:
            event("agent_auth", "", outcome="unavailable", category=str(error))
            raise AgentFailure("trusted_keys_unavailable") from None
        except TimeoutError:
            raise AgentFailure("authorization_timeout") from None
        if claims is None:
            raise AgentFailure("invalid_authorization")
        if "news.agent" not in claims.scp.split():
            raise AgentFailure("insufficient_scope")
        if time.monotonic() >= deadline:
            raise AgentFailure("authorization_timeout")
        return Caller(
            tenant=claims.tid,
            object_id=claims.oid,
            client_id=claims.azp,
            subject=claims.sub,
            expires_at=claims.exp,
            assertion=token,
        )


def request_authorization(scope: Scope) -> Authorization:
    authorization = scope.get("newsloom.agent.authorization")
    if not isinstance(authorization, Authorization):
        raise AgentFailure("missing_authorization")
    return authorization


class AgentAuthentication:
    def __init__(self, app: ASGIApp, verifier: AgentVerifier) -> None:
        self.app, self.verifier = app, verifier

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            raise AgentFailure("unsupported_transport")
        if scope["method"] == "GET" and scope["path"] in (
            "/.well-known/agent-card.json",
            "/health/live",
        ):
            await self.app(scope, receive, send)
            return
        deadline = time.monotonic() + 120
        original = scope.get("newsloom.agent.deadline")
        if isinstance(original, float):
            deadline = min(deadline, original)
        try:
            values = Headers(scope=scope).getlist("authorization")
            if len(values) != 1:
                raise AgentFailure("missing_authorization")
            scheme, separator, token = values[0].partition(" ")
            if scheme.lower() != "bearer" or not separator or not token or " " in token:
                raise AgentFailure("invalid_authorization")
            caller = await self.verifier.authenticate(token, deadline)
            expires_at = min(caller.expires_at, time.time() + 120)
            deadline = min(deadline, time.monotonic() + expires_at - time.time())
            if deadline <= time.monotonic():
                raise AgentFailure("invalid_authorization")
        except AgentFailure as error:
            category = str(error)
            status = (
                503
                if category in ("trusted_keys_unavailable", "authorization_timeout")
                else 403
                if category == "insufficient_scope"
                else 401
            )
            event("agent_auth", "", outcome="denied", category=category)
            response = JSONResponse(
                {"error": category},
                status_code=status,
                headers={"WWW-Authenticate": "Bearer"} if status == 401 else {},
            )
            await response(scope, receive, send)
            return
        authorization = Authorization(caller, deadline)
        scope["newsloom.agent.authorization"] = authorization
        context = _authorization.set(authorization)
        try:
            await self.app(scope, receive, send)
        finally:
            try:
                producers = tuple(authorization.producers)
                for producer in producers:
                    producer.cancel()
                if producers:
                    async with asyncio.timeout_at(authorization.deadline):
                        results = await asyncio.gather(*producers, return_exceptions=True)
                    if any(
                        isinstance(result, BaseException)
                        and not isinstance(result, asyncio.CancelledError)
                        for result in results
                    ):
                        raise AgentFailure("request_cleanup_failed")
            finally:
                authorization.producers.clear()
                _authorization.reset(context)
