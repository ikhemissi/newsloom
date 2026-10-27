"""Secretless request-local OBO and exactly one fixed, read-only MCP operation."""

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from uuid import UUID

import httpx
from azure.core.credentials import AccessToken
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import AzureError, ClientAuthenticationError
from azure.identity import AzureAuthorityHosts
from azure.identity.aio import OnBehalfOfCredential
from httpx2 import URL, AsyncByteStream, AsyncClient, InvalidURL, Limits, Request, Response
from httpx2 import HTTPError as McpHttpError
from httpx2 import HTTPStatusError as McpHttpStatusError
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult
from newsloom_core.auth import EntraTokenVerifier, TrustedKeysFailure
from newsloom_core.diagnostics import event
from pydantic import BaseModel, ConfigDict, model_validator

from newsloom_agent.auth import Authorization, UserClaims
from newsloom_agent.models import AgentFailure, RecentNews

ASSERTION_SCOPE = "api://AzureADTokenExchange/.default"
ASSERTION_MARGIN_SECONDS = 30
MAX_RESPONSE_BYTES = 128 * 1024


class DelegationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    tenant: UUID
    agent_client_id: UUID
    mcp_audience: UUID
    mcp_url: str

    @model_validator(mode="after")
    def trusted_resource(self) -> DelegationConfig:
        try:
            url = URL(self.mcp_url)
        except InvalidURL:
            raise ValueError("invalid_mcp_resource_url") from None
        if (
            url.scheme != "https"
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
            or url.port not in (None, 443)
            or url.path != "/mcp"
        ):
            raise ValueError("invalid_mcp_resource_url")
        if self.agent_client_id == self.mcp_audience:
            raise ValueError("separate_audiences_required")
        return self

    @property
    def scope(self) -> str:
        return f"api://{self.mcp_audience}/.default"


@dataclass(frozen=True, repr=False)
class DelegatedRead:
    news: RecentNews
    user_preserved: bool


def remaining(authorization: Authorization) -> float:
    if time.time() >= authorization.caller.expires_at:
        raise AgentFailure("authorization_expired")
    seconds = authorization.deadline - time.monotonic()
    if seconds <= 0:
        raise AgentFailure("request_timeout")
    return seconds


def assertion_value(assertion: AccessToken, required_until: float) -> str:
    if (
        not isinstance(assertion.token, str)
        or not assertion.token
        or assertion.expires_on < required_until
    ):
        raise AgentFailure("assertion_lifetime")
    return assertion.token


def leaf_errors(error: BaseException) -> Iterator[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            yield from leaf_errors(child)
    else:
        yield error


class BoundedResponse(AsyncByteStream):
    def __init__(self, source: AsyncByteStream, *, category: str = "mcp_response_limit") -> None:
        self.source, self.category = source, category

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = 0
        async for chunk in self.source:
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise AgentFailure(self.category)
            yield chunk

    async def aclose(self) -> None:
        await self.source.aclose()


class RecentNewsSession(ClientSession):
    """Validate the fixed DTO, never a server-selected schema or remote reference."""

    news: RecentNews | None = None

    async def validate_tool_result(self, name: str, result: CallToolResult) -> None:
        if name != "get_recent_news" or result.structured_content is None:
            raise AgentFailure("mcp_response_invalid")
        self.news = RecentNews.model_validate(result.structured_content)


class DelegatedMcp:
    def __init__(
        self,
        config: DelegationConfig,
        workload: AsyncTokenCredential,
        trusted_keys: httpx.AsyncClient,
    ) -> None:
        self.config, self.workload = config, workload
        self.verifier = EntraTokenVerifier(
            trusted_keys, config.tenant, config.mcp_audience, UserClaims
        )

    async def recent(self, authorization: Authorization) -> DelegatedRead:
        if authorization.caller.tenant != self.config.tenant:
            raise AgentFailure("invalid_authorization")
        remaining(authorization)
        try:
            async with asyncio.timeout_at(authorization.deadline):
                token = await self._exchange(authorization)
                claims = await self._validate_token(token, authorization)
                expires_at = min(
                    claims.exp, token.expires_on, time.time() + remaining(authorization)
                )
                deadline = min(
                    authorization.deadline,
                    time.monotonic() + expires_at - time.time(),
                )
                delegated = Authorization(authorization.caller, deadline)
                remaining(delegated)
                async with asyncio.timeout_at(deadline):
                    news = await self._read(token.token, delegated)
                event(
                    "agent_delegated_read",
                    "",
                    outcome="success",
                    counts={"items": len(news.items), "user_preserved": 1},
                )
                return DelegatedRead(news, user_preserved=True)
        except TimeoutError:
            raise AgentFailure("request_timeout") from None

    async def _exchange(self, authorization: Authorization) -> AccessToken:
        try:
            assertion = await self.workload.get_token(ASSERTION_SCOPE)
        except AzureError:
            raise AgentFailure("assertion_unavailable") from None
        assertion_value(
            assertion, time.time() + remaining(authorization) + ASSERTION_MARGIN_SECONDS
        )

        def client_assertion() -> str:
            remaining(authorization)
            return assertion_value(assertion, time.time() + ASSERTION_MARGIN_SECONDS)

        try:
            async with OnBehalfOfCredential(
                tenant_id=str(self.config.tenant),
                client_id=str(self.config.agent_client_id),
                user_assertion=authorization.caller.assertion,
                client_assertion_func=client_assertion,
                authority=AzureAuthorityHosts.AZURE_PUBLIC_CLOUD,
                logging_enable=False,
                enable_support_logging=False,
            ) as credential:
                token = await credential.get_token(self.config.scope)
        except ClientAuthenticationError:
            raise AgentFailure("exchange_denied") from None
        except AzureError:
            raise AgentFailure("exchange_unavailable") from None
        except ValueError, KeyError, TypeError:
            raise AgentFailure("exchange_response_invalid") from None
        if not isinstance(token.token, str) or not token.token or token.expires_on <= time.time():
            raise AgentFailure("exchange_response_invalid")
        return token

    async def _validate_token(self, token: AccessToken, authorization: Authorization) -> UserClaims:
        try:
            claims = await self.verifier.verify_claims(token.token)
        except TrustedKeysFailure:
            raise AgentFailure("downstream_keys_unavailable") from None
        if claims is None:
            raise AgentFailure("downstream_token_invalid")
        if (
            claims.tid != authorization.caller.tenant
            or claims.oid != authorization.caller.object_id
        ):
            raise AgentFailure("user_preservation_failed")
        if claims.azp != self.config.agent_client_id or set(claims.scp.split()) != {"news.read"}:
            raise AgentFailure("downstream_permission_invalid")
        return claims

    async def _read(self, token: str, authorization: Authorization) -> RecentNews:
        async def guard(request: Request) -> None:
            remaining(authorization)
            if request.url != URL(self.config.mcp_url) or request.method not in (
                "GET",
                "POST",
                "DELETE",
            ):
                raise AgentFailure("mcp_endpoint_mismatch")
            if request.headers.get("Authorization") != f"Bearer {token}":
                raise AgentFailure("mcp_authorization_mismatch")

        async def bound(response: Response) -> None:
            if response.status_code in (401, 403):
                raise AgentFailure("mcp_access_denied")
            if response.status_code >= 400:
                raise AgentFailure("mcp_unavailable")
            if 300 <= response.status_code < 400:
                raise AgentFailure("mcp_redirect_refused")
            if response.is_stream_consumed:
                if len(response.content) > MAX_RESPONSE_BYTES:
                    raise AgentFailure("mcp_response_limit")
            else:
                if not isinstance(response.stream, AsyncByteStream):
                    raise AgentFailure("mcp_response_invalid")
                response.stream = BoundedResponse(response.stream)

        try:
            async with (
                AsyncClient(
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=remaining(authorization),
                    trust_env=False,
                    follow_redirects=False,
                    limits=Limits(max_connections=2, max_keepalive_connections=0),
                    event_hooks={"request": [guard], "response": [bound]},
                ) as client,
                streamable_http_client(
                    self.config.mcp_url,
                    http_client=client,
                    terminate_on_close=False,
                    max_sse_event_size=MAX_RESPONSE_BYTES,
                ) as (read, write),
                RecentNewsSession(
                    read, write, read_timeout_seconds=remaining(authorization)
                ) as session,
            ):
                await session.initialize()
                result = await session.call_tool(
                    "get_recent_news",
                    {"limit": 1},
                    read_timeout_seconds=remaining(authorization),
                )
                if not isinstance(result, CallToolResult) or result.is_error:
                    raise AgentFailure("mcp_tool_failure")
                if session.news is None:
                    raise AgentFailure("mcp_response_invalid")
                remaining(authorization)
                return session.news
        except* McpHttpStatusError as errors:
            if any(
                error.response.status_code in (401, 403)
                for error in leaf_errors(errors)
                if isinstance(error, McpHttpStatusError)
            ):
                raise AgentFailure("mcp_access_denied") from None
            raise AgentFailure("mcp_unavailable") from None
        except* McpHttpError, MCPError:
            raise AgentFailure("mcp_unavailable") from None
        except* ValueError, RuntimeError:
            raise AgentFailure("mcp_response_invalid") from None
        except* TimeoutError:
            raise AgentFailure("request_timeout") from None
        except* AgentFailure as errors:
            categories = {str(error) for error in leaf_errors(errors)}
            category = categories.pop() if len(categories) == 1 else "mcp_request_failed"
            raise AgentFailure(category) from None
