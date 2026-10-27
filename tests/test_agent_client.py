import asyncio
import base64
import hashlib
import socket
import time
from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import httpx
import pytest
from mcp.types import CallToolResult
from newsloom_agent import client as acceptance
from newsloom_agent.app import create_app
from newsloom_agent.client import ClientSettings, ProofKey, callback_code, sign_in
from newsloom_agent.models import AgentFailure
from pydantic import ValidationError
from test_agent_auth import EndpointState, signed
from test_agent_auth import authority as authority
from test_agent_delegation import DelegationCase
from test_agent_delegation import delegated as delegated
from test_agent_generation import Model
from test_agent_generation import model as model
from test_mcp_auth import jwks
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import endpoint as endpoint


def settings(state: EndpointState) -> ClientSettings:
    return ClientSettings(
        tenant=state.verifier.tenant,
        agent_client_id=uuid4(),
        mcp_audience=uuid4(),
        mcp_url="https://mcp.test/mcp",
        public_client_id=uuid4(),
        resource_url="https://agent.test/a2a",
    )


def header(query: dict[str, str], path: str = "/callback", host: str = "127.0.0.1:8400") -> bytes:
    return f"GET {path}?{urlencode(query)} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()


def test_s256_state_and_public_client_scope_have_no_secret_or_offline_access(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    config = settings(authority[1])
    proof = ProofKey.create()
    other = ProofKey.create()
    url = urlsplit(proof.authorization_url(config))
    query = parse_qs(url.query)
    assert url.scheme == "https"
    assert url.hostname == "login.microsoftonline.com"
    assert url.path == f"/{config.tenant}/oauth2/v2.0/authorize"
    assert config.invoke_scope == f"api://{config.agent_client_id}/news.agent"
    assert query["scope"] == [config.invoke_scope]
    assert query["redirect_uri"] == [acceptance.CALLBACK]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [
        base64.urlsafe_b64encode(hashlib.sha256(proof.verifier.encode()).digest())
        .decode()
        .rstrip("=")
    ]
    assert query["state"] == [proof.state]
    assert query["prompt"] == ["select_account"]
    assert "secret" not in query and "client_secret" not in query
    assert "offline_access" not in url.query
    assert proof.verifier != other.verifier and proof.state != other.state
    assert proof.verifier not in repr(proof)
    assert proof.state not in repr(proof)


@pytest.mark.parametrize(
    "change",
    [
        {"state": "wrong"},
        {"code": ""},
        {"error": "NEWSLOOM_ERROR_CANARY"},
    ],
)
def test_callback_rejects_bad_state_missing_code_and_provider_errors(
    change: dict[str, str],
) -> None:
    with pytest.raises(AgentFailure, match="browser_callback_invalid"):
        callback_code(
            header({"code": "NEWSLOOM_CODE_CANARY", "state": "expected", **change}), "expected"
        )


@pytest.mark.parametrize(
    "raw",
    [
        b"GET /callback?code=a&state=s&state=other HTTP/1.1\r\nHost: 127.0.0.1:8400\r\n\r\n",
        b"GET /callback?code=a&state=s HTTP/1.1\r\nHost: attacker.invalid\r\n\r\n",
        (
            b"GET https://attacker.invalid/callback?code=a&state=s HTTP/1.1\r\n"
            b"Host: 127.0.0.1:8400\r\n\r\n"
        ),
        b"GET /other?code=a&state=s HTTP/1.1\r\nHost: 127.0.0.1:8400\r\n\r\n",
        b"\xff",
    ],
)
def test_callback_refuses_cross_origin_duplicate_and_malformed_requests(raw: bytes) -> None:
    with pytest.raises(AgentFailure, match="browser_callback_invalid"):
        callback_code(raw, "s")


@pytest.mark.parametrize("outcome", ["success", "invalid", "unavailable", "timeout"])
async def test_actual_loopback_callback_is_closed_after_explicit_browser_sign_in(
    authority: tuple[httpx.AsyncClient, EndpointState],
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    config, proof = settings(authority[1]), ProofKey.create()
    original = asyncio.start_server
    port = 0
    callback_tasks: list[asyncio.Task[None]] = []

    async def ephemeral(
        callback: Callable[[asyncio.StreamReader, asyncio.StreamWriter], None],
        host: str,
        requested: int,
        *,
        limit: int,
        backlog: int,
    ) -> asyncio.Server:
        nonlocal port
        assert host == "127.0.0.1" and requested == 8400
        server = await original(callback, host, 0, limit=limit, backlog=backlog)
        port = server.sockets[0].getsockname()[1]
        return server

    async def browser_callback() -> None:
        async with httpx.AsyncClient(trust_env=False) as http:
            response = await http.get(
                f"http://127.0.0.1:{port}/callback",
                headers={"Host": "127.0.0.1:8400"},
                params={
                    "state": proof.state if outcome == "success" else "wrong",
                    "code": "NEWSLOOM_CODE_CANARY",
                },
            )
            assert response.status_code == (200 if outcome == "success" else 400)
            assert "NEWSLOOM_CODE_CANARY" not in response.text

    def browser(url: str) -> bool:
        assert url == proof.authorization_url(config)
        if outcome in ("success", "invalid"):
            loop.call_soon_threadsafe(
                lambda: callback_tasks.append(asyncio.create_task(browser_callback()))
            )
        return outcome != "unavailable"

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(asyncio, "start_server", ephemeral)
    monkeypatch.setattr("webbrowser.open", browser)
    if outcome == "success":
        assert (
            await acceptance.authorization_code(config, proof, time.monotonic() + 3)
            == "NEWSLOOM_CODE_CANARY"
        )
    else:
        error = TimeoutError if outcome == "timeout" else AgentFailure
        with pytest.raises(error):
            await acceptance.authorization_code(
                config, proof, time.monotonic() + (0.1 if outcome == "timeout" else 3)
            )
    await asyncio.gather(*callback_tasks)
    with socket.socket() as probe:
        probe.settimeout(0.1)
        assert probe.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.parametrize("wrong_client", [False, True])
async def test_real_public_token_exchange_checks_pkce_and_verified_client_identity(
    authority: tuple[httpx.AsyncClient, EndpointState],
    wrong_client: bool,
) -> None:
    state = authority[1]
    config = settings(state).model_copy(update={"agent_client_id": state.verifier.tenant})
    calls: list[str] = []
    selected: list[ProofKey] = []
    token = signed(
        state,
        {
            "aud": str(config.agent_client_id),
            "azp": str(uuid4() if wrong_client else config.public_client_id),
        },
    )

    async def code(settings: ClientSettings, proof: ProofKey, deadline: float) -> str:
        selected.append(proof)
        return "NEWSLOOM_CODE_CANARY"

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.method == "POST":
            assert (
                str(request.url)
                == f"https://login.microsoftonline.com/{config.tenant}/oauth2/v2.0/token"
            )
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["authorization_code"]
            assert form["code_verifier"] == [selected[0].verifier]
            assert form["client_id"] == [str(config.public_client_id)]
            assert form["scope"] == [config.invoke_scope]
            assert form["redirect_uri"] == [acceptance.CALLBACK]
            assert "client_secret" not in form
            return httpx.Response(200, json={"access_token": token, "token_type": "Bearer"})
        return httpx.Response(200, json=jwks(state.key))

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        if wrong_client:
            with pytest.raises(AgentFailure, match="browser_client_mismatch"):
                await sign_in(config, http, code)
        else:
            assert await sign_in(config, http, code) == token
    assert len(calls) == 2


async def test_occupied_callback_port_never_opens_browser(
    authority: tuple[httpx.AsyncClient, EndpointState], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def occupied(*args: object, **kwargs: object) -> asyncio.Server:
        raise OSError("PRIVATE_PORT_ERROR_CANARY")

    monkeypatch.setattr(asyncio, "start_server", occupied)
    with pytest.raises(AgentFailure, match="browser_callback_port_unavailable"):
        await acceptance.authorization_code(
            settings(authority[1]), ProofKey.create(), time.monotonic() + 3
        )


async def test_token_response_byte_limit_precedes_verification(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    async def code(settings: ClientSettings, proof: ProofKey, deadline: float) -> str:
        return "NEWSLOOM_CODE_CANARY"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * (acceptance.MAX_SIGN_IN_BYTES + 1))
        )
    ) as http:
        with pytest.raises(AgentFailure, match="browser_token_response_limit"):
            await sign_in(settings(authority[1]), http, code)


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"error": "NEWSLOOM_ERROR_CANARY"}, 400),
        ({"access_token": True, "token_type": "Bearer"}, 200),
        ({"access_token": "invalid", "token_type": "Bearer"}, 200),
        ({"access_token": "invalid", "token_type": "other"}, 200),
        ({"access_token": "invalid", "token_type": "Bearer", "refresh_token": "PRIVATE"}, 200),
        ({"access_token": "invalid", "token_type": "Bearer"}, 302),
        ([], 200),
    ],
)
async def test_denied_invalid_and_persistent_token_responses_have_no_fallback(
    authority: tuple[httpx.AsyncClient, EndpointState],
    payload: object,
    status: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = settings(authority[1])

    async def code(settings: ClientSettings, proof: ProofKey, deadline: float) -> str:
        return "NEWSLOOM_CODE_CANARY"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
    ) as http:
        with pytest.raises(AgentFailure):
            await sign_in(config, http, code)
    assert "CANARY" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "empty",
        "denied",
        "streaming",
        "streaming-empty",
        "streaming-denied",
        "streaming-throttled",
    ],
)
async def test_acceptance_uses_actual_local_a2a_obo_mcp_and_never_exports_content(
    delegated: DelegationCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outcome: str,
    model: Model,
) -> None:
    authorization = await delegated.authorization()
    config = ClientSettings(
        tenant=delegated.config.tenant,
        agent_client_id=delegated.config.agent_client_id,
        mcp_audience=delegated.config.mcp_audience,
        mcp_url=delegated.config.mcp_url,
        public_client_id=authorization.caller.client_id,
        resource_url="https://agent.test/a2a",
    )
    original = httpx.AsyncClient
    streaming = outcome.startswith("streaming")
    if outcome in ("empty", "streaming-empty"):
        delegated.mcp_result = CallToolResult(
            content=[], structured_content={"items": []}
        ).model_dump(mode="json", by_alias=True, exclude_none=True)
    elif outcome in ("denied", "streaming-denied"):
        delegated.exchange_status = 400
        delegated.exchange_payload = {"error": "invalid_grant", "error_description": "CANARY"}
    elif outcome == "streaming-throttled":
        model.status = 429
    async with original(
        transport=httpx.ASGITransport(
            create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=config.resource_url,
                generator=model.generator() if streaming else None,
            )
        ),
        base_url="https://agent.test",
    ) as app:

        async def route(request: httpx.Request) -> httpx.Response:
            target = app if request.url.host == "agent.test" else delegated.mcp_http
            response = await target.request(
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
            if outcome in ("success", "streaming"):
                result = await acceptance.invoke(
                    config, authorization.caller.assertion, public, streaming=streaming
                )
                assert result == {
                    "items": 1,
                    "user_preserved": 1,
                    "agent_auth_denials": 2,
                    "cross_audience_denials": 1,
                    "task_reads": 1,
                    **(
                        {"artifact_events": 2, "generation_calls": 1, "output_tokens": 4}
                        if streaming
                        else {}
                    ),
                }
            else:
                with pytest.raises(AgentFailure):
                    await acceptance.invoke(
                        config, authorization.caller.assertion, public, streaming=streaming
                    )
        assert len(delegated.forms) == 1
        assert all(transport.closed for transport in delegated.identity_transports)
    assert "CANARY" not in capsys.readouterr().out


@pytest.mark.parametrize("url", ["http://agent.test/a2a", "https://agent.test/a2a?other=1"])
def test_acceptance_settings_are_https_and_fixed(
    authority: tuple[httpx.AsyncClient, EndpointState], url: str
) -> None:
    with pytest.raises(ValidationError):
        ClientSettings.model_validate({**settings(authority[1]).model_dump(), "resource_url": url})
