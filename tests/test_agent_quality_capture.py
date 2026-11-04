import asyncio
import base64
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.shared.auth import AuthorizationCodeResult, OAuthToken
from newsloom_agent.app import create_app
from newsloom_agent.auth import Caller, UserClaims
from newsloom_agent.client import ClientSettings
from newsloom_agent.models import AgentFailure
from newsloom_agent.research import ResearchController
from newsloom_agent.research_models import NewsDetail, ResearchRequest
from newsloom_agent.serving import TaskRegistry
from newsloom_core.auth import EntraTokenVerifier
from test_agent_delegation import DelegationCase
from test_agent_delegation import delegated as delegated
from test_agent_research_serving import ResearchWire
from test_agent_research_serving import research_wire as research_wire
from test_mcp_auth import jwks
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Endpoint
from test_mcp_http import endpoint as endpoint

from scripts.agent_quality_capture import (
    MCP_CALLBACK,
    CaptureLimits,
    CaptureSettings,
    McpCallback,
    MemoryOAuth,
    ResearchHttpAdmission,
    WindowsDefaultBrowser,
    capture_denial,
    capture_research,
    evidence_session,
    fingerprint,
    public_admission,
    verified_mcp_user,
)


def settings() -> CaptureSettings:
    return CaptureSettings(
        ClientSettings(
            tenant=uuid4(),
            agent_client_id=uuid4(),
            mcp_audience=uuid4(),
            mcp_url="https://mcp.test/mcp",
            public_client_id=uuid4(),
            resource_url="https://agent.test/a2a",
        ),
        uuid4(),
    )


def caller(config: CaptureSettings) -> Caller:
    return Caller(
        config.agent.tenant,
        uuid4(),
        config.agent.public_client_id,
        "agent-subject",
        int(time.time()) + 600,
        "AGENT_CREDENTIAL_CANARY",
    )


def token(
    config: CaptureSettings,
    user: Caller,
    key: rsa.RSAPrivateKey,
    change: Mapping[str, object] | None = None,
) -> str:
    return jwt.encode(
        {
            "iss": f"https://login.microsoftonline.com/{config.agent.tenant}/v2.0",
            "aud": str(config.agent.mcp_audience),
            "tid": str(config.agent.tenant),
            "oid": str(user.object_id),
            "azp": str(config.mcp_public_client_id),
            "sub": "different-pairwise-mcp-subject",
            "exp": int(time.time()) + 600,
            "nbf": int(time.time()) - 5,
            "ver": "2.0",
            "scp": "news.read",
            "idtyp": "user",
            **(change or {}),
        },
        key,
        algorithm="RS256",
        headers={"kid": "local-test-key"},
    )


@pytest.mark.parametrize(
    "change",
    [None, {"oid": str(uuid4())}, {"azp": str(uuid4())}, {"scp": ""}, {"aud": "wrong"}, {"exp": 1}],
)
async def test_mcp_identity_requires_trusted_same_user_scope_and_existing_client(
    signing_key: rsa.RSAPrivateKey, change: Mapping[str, object] | None
) -> None:
    config = settings()
    user = caller(config)
    calls: list[str] = []

    def keys(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=jwks(signing_key))

    async with httpx.AsyncClient(transport=httpx.MockTransport(keys)) as http:
        verifier = EntraTokenVerifier(
            http, config.agent.tenant, config.agent.mcp_audience, UserClaims
        )
        value = token(config, user, signing_key, change)
        if change is None:
            claims = await verified_mcp_user(value, config, user, verifier, time.monotonic() + 10)
            assert claims.oid == user.object_id and claims.sub != user.subject
        else:
            with pytest.raises(AgentFailure, match="baseline_capture_user_mismatch"):
                await verified_mcp_user(value, config, user, verifier, time.monotonic() + 10)
    assert len(calls) == 1


async def test_memory_oauth_reuses_only_existing_public_registration() -> None:
    config = settings()
    store = MemoryOAuth(config)
    assert await store.get_tokens() is None
    original = await store.get_client_info()
    await store.set_client_info(original)
    with pytest.raises(AgentFailure, match="baseline_capture_registration_forbidden"):
        await store.set_client_info(original.model_copy(update={"client_id": str(uuid4())}))
    with pytest.raises(AgentFailure, match="baseline_capture_registration_forbidden"):
        await store.set_client_info(original.model_copy(update={"client_secret": "CANARY"}))
    value = OAuthToken(access_token="TOKEN_CANARY", token_type="Bearer")
    await store.set_tokens(value)
    assert await store.get_tokens() is value
    with pytest.raises(AgentFailure, match="baseline_capture_token_not_admitted"):
        await store.set_tokens(value)
    assert "CANARY" not in repr(store)


@pytest.mark.parametrize("extra", ["", "&session_state=AUTHORED_SESSION"])
async def test_actual_loopback_callback_checks_host_and_closes_port(extra: str) -> None:
    config = settings()
    limits = CaptureLimits(deadline=time.monotonic() + 10)
    async with McpCallback(config, limits) as callback:
        reader, writer = await asyncio.open_connection("127.0.0.1", 33418)
        writer.write(
            (
                "GET /?code=CODE_CANARY&state=state"
                + extra
                + " HTTP/1.1\r\nHost: 127.0.0.1:33418\r\n\r\n"
            ).encode()
        )
        await writer.drain()
        response = await reader.read()
        assert b"200 OK" in response
        assert b"Content-Type: text/plain" in response
        assert response.endswith(b"Sign-in received. Close this tab.\n")
        assert b"CODE_CANARY" not in response and b"AUTHORED_SESSION" not in response
        result = await callback.wait()
        assert result.code == "CODE_CANARY" and result.state == "state"
        writer.close()
        await writer.wait_closed()
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", 33418)


@pytest.mark.parametrize(
    "path,host",
    [("/callback", "127.0.0.1:33418"), ("/", "attacker.invalid")],
)
async def test_callback_rejects_foreign_path_and_host(path: str, host: str) -> None:
    async with McpCallback(settings(), CaptureLimits()) as callback:
        reader, writer = await asyncio.open_connection("127.0.0.1", 33418)
        writer.write(f"GET {path}?code=a&state=b HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
        await writer.drain()
        assert b"400 Bad Request" in await reader.read()
        with pytest.raises(AgentFailure, match="baseline_capture_callback_invalid"):
            await callback.wait()
        writer.close()
        await writer.wait_closed()


@pytest.mark.parametrize(
    "extra",
    [
        "&session_state=first&session_state=second",
        "&session_state=" + "x" * 513,
        "&unexpected=AUTHORED_VALUE",
    ],
)
async def test_callback_rejects_duplicate_oversized_or_foreign_callback_fields(extra: str) -> None:
    async with McpCallback(settings(), CaptureLimits()) as callback:
        reader, writer = await asyncio.open_connection("127.0.0.1", 33418)
        writer.write(
            (
                "GET /?code=authored&state=authored"
                + extra
                + " HTTP/1.1\r\nHost: 127.0.0.1:33418\r\n\r\n"
            ).encode()
        )
        await writer.drain()
        assert b"400 Bad Request" in await reader.read()
        with pytest.raises(AgentFailure, match="baseline_capture_callback_invalid"):
            await callback.wait()
        writer.close()
        await writer.wait_closed()


@dataclass
class OAuthMcp:
    config: CaptureSettings
    access_token: str
    detail: NewsDetail
    challenge: str = ""
    token_requests: int = 0
    token_status: int = 200
    methods: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)

    def route(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        self.urls.append(url)
        tenant = str(self.config.agent.tenant)
        issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
        if url.startswith("https://mcp.test/.well-known/oauth-protected-resource"):
            return httpx2.Response(
                200,
                json={
                    "resource": self.config.agent.mcp_url,
                    "authorization_servers": [issuer],
                    "scopes_supported": [self.config.mcp_scope],
                },
            )
        if url == issuer + "/.well-known/openid-configuration":
            return httpx2.Response(
                200,
                json={
                    "issuer": issuer,
                    "authorization_endpoint": (
                        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
                    ),
                    "token_endpoint": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                    "response_types_supported": ["code"],
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none"],
                    "scopes_supported": [self.config.mcp_scope],
                },
            )
        if request.method == "GET" and url.startswith("https://login.microsoftonline.com/"):
            return httpx2.Response(404)
        if url == f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token":
            form = parse_qs(request.content.decode())
            assert form["client_id"] == [str(self.config.mcp_public_client_id)]
            assert form["redirect_uri"] == [MCP_CALLBACK]
            assert "client_secret" not in form
            assert (
                base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest())
                .decode()
                .rstrip("=")
                == self.challenge
            )
            self.token_requests += 1
            if self.token_status != 200:
                return httpx2.Response(
                    self.token_status, json={"error": "authorization_denied", "detail": "CANARY"}
                )
            return httpx2.Response(
                200,
                json={
                    "access_token": self.access_token,
                    "token_type": "Bearer",
                    "expires_in": 600,
                    "scope": self.config.mcp_scope,
                },
            )
        assert url == self.config.agent.mcp_url
        if request.headers.get("authorization") != "Bearer " + self.access_token:
            return httpx2.Response(
                401,
                headers={
                    "www-authenticate": (
                        'Bearer resource_metadata="https://mcp.test/'
                        '.well-known/oauth-protected-resource/mcp"'
                    ),
                },
            )
        if request.method in ("GET", "DELETE"):
            return httpx2.Response(405 if request.method == "GET" else 200)
        value = json.loads(request.content)
        self.methods.append(value["method"])
        if value["method"] == "notifications/initialized":
            return httpx2.Response(202)
        if value["method"] == "initialize":
            result: dict[str, object] = {
                "protocolVersion": value["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "authored-capture-test", "version": "1"},
            }
        elif value["method"] == "tools/call":
            assert value["params"]["name"] == "get_news_item"
            result = {
                "content": [],
                "isError": False,
                "structuredContent": {"found": True, "item": self.detail.model_dump(mode="json")},
            }
        else:
            raise AssertionError("unexpected_mcp_dispatch")
        return httpx2.Response(200, json={"jsonrpc": "2.0", "id": value["id"], "result": result})


async def test_actual_sdk_pkce_and_read_only_evidence_capture(
    signing_key: rsa.RSAPrivateKey,
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = settings()
    user = caller(config)
    detail = NewsDetail(
        **endpoint[1].item.model_dump(),
        author="",
        date_origin="published",
        publisher_categories=(),
    )
    server = OAuthMcp(config, token(config, user, signing_key), detail)

    async def redirect(callback: McpCallback, url: str) -> None:
        query = parse_qs(urlsplit(url).query)
        assert query["client_id"] == [str(config.mcp_public_client_id)]
        assert query["scope"] == [config.mcp_scope]
        assert query["redirect_uri"] == [MCP_CALLBACK]
        server.challenge = query["code_challenge"][0]
        callback.future.set_result(
            AuthorizationCodeResult(
                code="CODE_CANARY",
                state=query["state"][0],
            )
        )

    monkeypatch.setattr(McpCallback, "redirect", redirect)
    limits = CaptureLimits(deadline=time.monotonic() + 15)
    async with evidence_session(
        config,
        user,
        limits,
        readiness=True,
        transport=httpx2.MockTransport(server.route),
        keys_transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=jwks(signing_key))
        ),
    ) as reader:
        item = await reader.item(detail.id)
        assert item is not None
        assert fingerprint(item.model_dump(mode="json")) == fingerprint(
            detail.model_dump(mode="json")
        )
        with pytest.raises(AgentFailure, match="baseline_capture_paid_preparation_forbidden"):
            await reader.call("search_news", {"query": "not-allowed-before-paid-approval"})
        with pytest.raises(AgentFailure, match="baseline_capture_tool_forbidden"):
            await reader.call("write_news", {})
        assert reader.limits.operations == 1 and reader.limits.received > 0
        assert not reader.limits.pending_tool
        assert reader.limits.metadata_reads > 0
        assert reader.caller.object_id == user.object_id
    assert server.token_requests == 1 and server.methods.count("tools/call") == 1
    assert not any("register" in value for value in server.urls)
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err


@pytest.mark.parametrize("cancel", [False, True])
async def test_sdk_capture_denied_consent_or_cancellation_does_not_dispatch_fallback(
    signing_key: rsa.RSAPrivateKey,
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cancel: bool,
) -> None:
    config = settings()
    user = caller(config)
    detail = NewsDetail(
        **endpoint[1].item.model_dump(),
        author="",
        date_origin="published",
        publisher_categories=(),
    )
    server = OAuthMcp(config, token(config, user, signing_key), detail)
    server.token_status = 200 if cancel else 400
    entered = asyncio.Event()
    release = asyncio.Event()

    async def redirect(callback: McpCallback, url: str) -> None:
        query = parse_qs(urlsplit(url).query)
        server.challenge = query["code_challenge"][0]
        callback.future.set_result(
            AuthorizationCodeResult(
                code="CODE_CANARY",
                state=query["state"][0],
            )
        )

    async def route(request: httpx2.Request) -> httpx2.Response:
        if (
            cancel
            and request.method == "POST"
            and str(request.url) == config.agent.mcp_url
            and json.loads(request.content).get("method") == "tools/call"
        ):
            entered.set()
            await release.wait()
        return server.route(request)

    monkeypatch.setattr(McpCallback, "redirect", redirect)
    limits = CaptureLimits(deadline=time.monotonic() + 15)

    async def run() -> None:
        async with evidence_session(
            config,
            user,
            limits,
            readiness=True,
            transport=httpx2.MockTransport(route),
            keys_transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=jwks(signing_key))
            ),
        ) as reader:
            await reader.item(detail.id)

    if cancel:
        task = asyncio.create_task(run())
        await asyncio.wait_for(entered.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert limits.operations == 1
    else:
        with pytest.raises(ExceptionGroup):
            await run()
        assert limits.operations == 0
    assert server.token_requests == 1
    assert server.methods.count("tools/call") == 0
    assert not any("register" in value for value in server.urls)
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", 33418)
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err


def test_capture_limits_reject_one_over_without_dispatch() -> None:
    limits = CaptureLimits(operations=160)
    with pytest.raises(AgentFailure, match="baseline_capture_operation_limit"):
        limits.admit_tool()
    limits.auth_requests = 40
    with pytest.raises(AgentFailure, match="baseline_capture_auth_limit"):
        limits.admit_auth()
    limits.sign_ins = 4
    with pytest.raises(AgentFailure, match="baseline_capture_sign_in_limit"):
        limits.admit_sign_in()
    limits.received = 10 * 1024 * 1024
    with pytest.raises(AgentFailure, match="baseline_capture_response_limit"):
        limits.consume(1)


@pytest.mark.parametrize(
    "profile,reads,flows",
    [
        ("baseline-12x8-v1", 60, 4),
        ("baseline-12x8-v2", 120, 6),
        ("baseline-12x8-v3", 120, 7),
        ("baseline-12x8-v4", 120, 9),
        ("baseline-12x8-v5", 180, 9),
        ("baseline-12x8-v6", 180, 9),
    ],
)
def test_root_capture_profile_exact_read_and_sign_in_limits(
    profile: Literal[
        "baseline-12x8-v1",
        "baseline-12x8-v2",
        "baseline-12x8-v3",
        "baseline-12x8-v4",
        "baseline-12x8-v5",
        "baseline-12x8-v6",
    ],
    reads: int,
    flows: int,
) -> None:
    limits = CaptureLimits(limit_profile=profile, metadata_reads=reads - 1, sign_ins=flows - 1)
    limits.admit_metadata()
    limits.admit_sign_in()
    with pytest.raises(AgentFailure, match="baseline_capture_metadata_limit"):
        limits.admit_metadata()
    with pytest.raises(AgentFailure, match="baseline_capture_sign_in_limit"):
        limits.admit_sign_in()


def test_windows_browser_uses_default_handler_and_private_bounded_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    observed: list[dict[str, object]] = []

    def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        observed.append(kwargs)
        assert arguments == ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "-"]
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(subprocess, "run", run)
    browser = WindowsDefaultBrowser("powershell.exe")
    assert browser.open("https://login.microsoftonline.com/authored?state=STATE_CANARY")
    assert observed[0]["stdout"] == observed[0]["stderr"] == subprocess.DEVNULL
    assert observed[0]["timeout"] == 15
    with pytest.raises(AgentFailure, match="baseline_browser_target"):
        browser.open("https://foreign.test")


def test_worker_retains_safe_categories_inside_sdk_exception_groups() -> None:
    from scripts.agent_quality_worker import safe_failure_digest

    code = "agent_research_acceptance_response_invalid"
    grouped = ExceptionGroup("PRIVATE_CONTENT_CANARY", [AgentFailure(code)])
    assert safe_failure_digest(grouped) == hashlib.sha256(code.encode()).hexdigest()
    assert safe_failure_digest(ValueError("PRIVATE_CONTENT_CANARY")) is None
    assert (
        safe_failure_digest(
            ExceptionGroup(
                "PRIVATE_CONTENT_CANARY",
                [
                    AgentFailure("research_filter_relaxation"),
                    AgentFailure("research_unknown_item"),
                ],
            )
        )
        is None
    )


@pytest.mark.parametrize("with_token", [False, True])
async def test_actual_sdk_denial_uses_valid_research_request_without_model_work(
    delegated: DelegationCase,
    research_wire: ResearchWire,
    signing_key: rsa.RSAPrivateKey,
    with_token: bool,
) -> None:
    authorization = await delegated.authorization()
    config = CaptureSettings(
        ClientSettings(
            tenant=delegated.config.tenant,
            agent_client_id=delegated.config.agent_client_id,
            mcp_audience=delegated.config.mcp_audience,
            mcp_url=delegated.config.mcp_url,
            public_client_id=authorization.caller.client_id,
            resource_url="https://agent.test/a2a",
        ),
        uuid4(),
    )
    registry = TaskRegistry()
    seen: list[dict[str, object]] = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=config.agent.resource_url,
                registry=registry,
                research=ResearchController(delegated.adapter, research_wire.generator()),
            )
        )
    ) as app:

        async def route(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                seen.append(json.loads(request.content))
            response = await app.request(
                request.method, str(request.url), headers=request.headers, content=request.content
            )
            return httpx.Response(
                response.status_code, content=response.content, headers=response.headers
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as public:
            value = token(config, authorization.caller, signing_key) if with_token else None
            status = await capture_denial(
                config,
                public,
                ResearchRequest(operation="research", question="Authored denial control"),
                expected_status=401,
                wrong_audience_token=value,
                transport=httpx.MockTransport(route),
            )
        assert status == 401 and len(seen) == 1
        assert not delegated.mcp_methods
    await registry.close()


@dataclass
class MemoryEvidence:
    caller: Caller
    detail: NewsDetail
    change_after_first: bool
    limits: CaptureLimits = field(default_factory=CaptureLimits)
    calls: int = 0

    async def item(self, item_id: UUID) -> NewsDetail:
        assert item_id == self.detail.id
        self.calls += 1
        if self.change_after_first and self.calls > 1:
            return self.detail.model_copy(update={"summary": "CHANGED_PRIVATE_CANARY"})
        return self.detail


@pytest.mark.parametrize("changed", [False, True])
async def test_actual_a2a_capture_binds_receipt_and_before_after_evidence(
    delegated: DelegationCase,
    research_wire: ResearchWire,
    signing_key: rsa.RSAPrivateKey,
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
    changed: bool,
) -> None:
    authorization = await delegated.authorization()
    config = CaptureSettings(
        ClientSettings(
            tenant=delegated.config.tenant,
            agent_client_id=delegated.config.agent_client_id,
            mcp_audience=delegated.config.mcp_audience,
            mcp_url=delegated.config.mcp_url,
            public_client_id=authorization.caller.client_id,
            resource_url="https://agent.test/a2a",
        ),
        uuid4(),
    )
    detail = NewsDetail(
        **endpoint[1].item.model_dump(),
        author="",
        date_origin="published",
        publisher_categories=(),
    )
    evidence = MemoryEvidence(authorization.caller, detail, changed)
    admitted: list[tuple[str, int]] = []
    evidence.limits.permit = lambda operation, amount: admitted.append((operation, amount))
    registry = TaskRegistry()
    original = httpx.AsyncClient
    async with original(
        transport=httpx.ASGITransport(
            create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=config.agent.resource_url,
                registry=registry,
                research=ResearchController(delegated.adapter, research_wire.generator()),
            )
        )
    ) as app:

        async def route(request: httpx.Request) -> httpx.Response:
            if request.url.host == "login.microsoftonline.com":
                return httpx.Response(200, json=jwks(signing_key))
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
            operation = capture_research(
                config,
                authorization.caller.assertion,
                public,
                evidence,
                ResearchRequest(
                    operation="research",
                    question="Explain the selected authored item.",
                    item_ids=(detail.id,),
                ),
                {detail.id: fingerprint(detail.model_dump(mode="json"))},
            )
            if changed:
                with pytest.raises(AgentFailure, match="baseline_capture_evidence_drift"):
                    await operation
            else:
                result = await operation
                assert result.invocation.receipt is not None
                assert result.invocation.receipt.outcome == "supported"
                assert result.invocation.receipt.user_preserved
                assert result.evidence == (detail,)
                assert detail.url in result.invocation.text
                assert "CANARY" not in repr(result)
    assert evidence.calls == 2
    assert admitted == [("auth_http", 1), ("metadata_before", 1), ("task_reads", 1)]
    await registry.close()


async def test_research_http_admission_rejects_replay_and_denied_read_before_dispatch() -> None:
    admissions: list[tuple[str, int]] = []
    limits = CaptureLimits(permit=lambda operation, amount: admissions.append((operation, amount)))
    guard = ResearchHttpAdmission(limits)
    send = httpx.Request(
        "POST",
        "https://agent.test/a2a",
        json={
            "method": "SendStreamingMessage",
        },
    )
    read = httpx.Request("POST", "https://agent.test/a2a", json={"method": "GetTask"})
    await guard.request(send)
    with pytest.raises(AgentFailure, match="baseline_capture_research_dispatch_limit"):
        await guard.request(send)
    await guard.request(read)
    with pytest.raises(AgentFailure, match="baseline_capture_research_dispatch_limit"):
        await guard.request(read)
    assert admissions == [("task_reads", 1)]

    def deny(operation: str, amount: int) -> None:
        raise AgentFailure("baseline_capture_test_denied")

    limits.permit = deny
    guard = ResearchHttpAdmission(limits)
    await guard.request(send)
    with pytest.raises(AgentFailure, match="baseline_capture_test_denied"):
        await guard.request(read)
    assert guard.reads == 0


async def test_public_admission_denies_foreign_or_unfunded_requests_and_restores_hooks() -> None:
    config = settings()
    sent: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        return httpx.Response(200, json={})

    limits = CaptureLimits()
    card = config.agent.resource_url.removesuffix("/a2a") + "/.well-known/agent-card.json"
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as http:
        before = {name: list(hooks) for name, hooks in http.event_hooks.items()}
        async with public_admission(config, http, limits):
            await http.get(card)
            with pytest.raises(AgentFailure, match="baseline_capture_public_http_target"):
                await http.get("https://foreign.test/PRIVATE_CREDENTIAL_CANARY")
            limits.metadata_reads = 60
            with pytest.raises(AgentFailure, match="baseline_capture_metadata_limit"):
                await http.get(card)
        assert http.event_hooks == before
    assert sent == [card]
