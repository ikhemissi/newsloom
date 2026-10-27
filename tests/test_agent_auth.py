import asyncio
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from newsloom_agent.auth import (
    AgentAuthentication,
    AgentVerifier,
    Authorization,
    request_authorization,
)
from newsloom_agent.models import AgentFailure
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Message as ASGIMessage
from test_mcp_auth import jwks
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Endpoint
from test_mcp_http import endpoint as endpoint


@dataclass
class EndpointState:
    verifier: AgentVerifier
    key: rsa.RSAPrivateKey
    calls: list[tuple[str, UUID]] = field(default_factory=list)
    authorizations: list[Authorization] = field(default_factory=list)
    key_urls: list[str] = field(default_factory=list)


def signed(
    state: EndpointState,
    changes: Mapping[str, object] | None = None,
    *,
    headers: Mapping[str, object] | None = None,
    remove: tuple[str, ...] = (),
    key: rsa.RSAPrivateKey | None = None,
) -> str:
    claims: dict[str, object] = {
        "iss": state.verifier.issuer,
        "aud": state.verifier.audience,
        "tid": str(state.verifier.tenant),
        "oid": str(uuid4()),
        "sub": "LOCAL_SUBJECT_CANARY",
        "azp": str(uuid4()),
        "exp": int(time.time()) + 600,
        "nbf": int(time.time()) - 1,
        "ver": "2.0",
        "scp": "news.agent",
        **(changes or {}),
    }
    for name in remove:
        del claims[name]
    return jwt.encode(
        claims,
        key or state.key,
        algorithm="RS256",
        headers={"kid": "local-test-key", **(headers or {})},
    )


def guarded(state: EndpointState) -> AgentAuthentication:
    async def downstream(request: Request) -> JSONResponse:
        if request.url.path in ("/.well-known/agent-card.json", "/health/live"):
            return JSONResponse({"static": True})
        authorization = request_authorization(request.scope)
        await asyncio.sleep(0)
        state.authorizations.append(authorization)
        for operation in ("obo", "mcp", "model"):
            state.calls.append((operation, authorization.caller.object_id))
        return JSONResponse({"authorized": True})

    app = Starlette(
        routes=[Route("/{path:path}", downstream, methods=["GET", "POST", "DELETE", "OPTIONS"])]
    )
    return AgentAuthentication(app, state.verifier)


@pytest.fixture
async def authority(
    signing_key: rsa.RSAPrivateKey,
) -> AsyncIterator[tuple[httpx.AsyncClient, EndpointState]]:
    urls: list[str] = []

    def keys(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=jwks(signing_key))

    async with httpx.AsyncClient(transport=httpx.MockTransport(keys)) as trusted:
        state = EndpointState(AgentVerifier(trusted, uuid4(), uuid4()), signing_key, key_urls=urls)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(guarded(state)), base_url="https://agent.test"
        ) as client:
            yield client, state


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"exp": 1}, 401),
        ({"nbf": int(time.time()) + 3600}, 401),
        ({"aud": str(uuid4())}, 401),
        ({"iss": "https://wrong.invalid"}, 401),
        ({"tid": str(uuid4())}, 401),
        ({"ver": "1.0"}, 401),
        ({"oid": "invalid"}, 401),
        ({"oid": None}, 401),
        ({"azp": "invalid"}, 401),
        ({"sub": ""}, 401),
        ({"sub": "x" * 257}, 401),
        ({"scp": "news.read"}, 403),
        ({"scp": "news.agent.extra"}, 403),
        ({"scp": "agent.invoke"}, 403),
        ({"scp": "profile offline_access"}, 403),
        ({"scp": ""}, 403),
        ({"scp": "x" * 2049}, 401),
        ({"idtyp": "app", "roles": ["news.agent"]}, 401),
        ({"nonce": "LOCAL_ID_TOKEN_CANARY"}, 401),
        ({"exp": True}, 401),
        ({"nbf": False}, 401),
        ({"exp": str(int(time.time()) + 600)}, 401),
    ],
)
async def test_invalid_claims_are_refused_before_downstream_work(
    authority: tuple[httpx.AsyncClient, EndpointState],
    change: dict[str, object],
    status: int,
) -> None:
    client, state = authority
    response = await client.post(
        "/a2a", headers={"Authorization": f"Bearer {signed(state, change)}"}
    )
    assert response.status_code == status
    assert not state.calls and not state.authorizations
    assert state.key_urls == [state.verifier.jwks_url]
    assert "CANARY" not in response.text


@pytest.mark.parametrize("name", ["exp", "nbf", "iss", "aud", "sub", "tid", "azp", "ver", "oid"])
async def test_required_identity_claims_cannot_be_omitted(
    authority: tuple[httpx.AsyncClient, EndpointState], name: str
) -> None:
    client, state = authority
    response = await client.post(
        "/a2a", headers={"Authorization": f"Bearer {signed(state, remove=(name,))}"}
    )
    assert response.status_code == 401
    assert not state.calls


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("path", ["/a2a", "/tasks/private", "/agent/authenticatedExtendedCard"])
async def test_every_protected_method_is_guarded_before_the_application(
    authority: tuple[httpx.AsyncClient, EndpointState], method: str, path: str
) -> None:
    client, state = authority
    response = await client.request(method, path)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert not state.calls and not state.key_urls


async def test_only_static_discovery_and_liveness_are_public(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    client, state = authority
    for path in ("/.well-known/agent-card.json", "/health/live"):
        response = await client.get(path)
        assert response.json() == {"static": True}
        assert (await client.post(path)).status_code == 401
    assert not state.calls and not state.key_urls


@pytest.mark.parametrize(
    "headers",
    [
        [("Authorization", "Basic NEWSLOOM_HEADER_CANARY")],
        [("Authorization", "Bearer ")],
        [("Authorization", "Bearer a b")],
        [("Authorization", "Bearer first"), ("Authorization", "Bearer second")],
    ],
)
async def test_invalid_and_duplicate_authorization_headers_are_not_forwarded(
    authority: tuple[httpx.AsyncClient, EndpointState],
    headers: list[tuple[str, str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    client, state = authority
    response = await client.post("/a2a", headers=headers)
    assert response.status_code == 401
    assert not state.calls and not state.key_urls
    captured = capsys.readouterr()
    assert "CANARY" not in response.text + captured.out + captured.err


async def test_unsupported_websocket_cannot_enter_the_application(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    _, state = authority
    messages: list[ASGIMessage] = []

    async def receive() -> ASGIMessage:
        pytest.fail("Unsupported WebSocket must not consume application input")

    async def send(message: ASGIMessage) -> None:
        messages.append(message)

    await guarded(state)({"type": "websocket", "path": "/a2a"}, receive, send)
    assert messages == [{"type": "websocket.close", "code": 1008}]
    assert not state.calls and not state.key_urls


async def test_two_users_remain_request_private_and_share_only_trusted_keys(
    authority: tuple[httpx.AsyncClient, EndpointState],
    capsys: pytest.CaptureFixture[str],
) -> None:
    client, state = authority
    users = (uuid4(), uuid4())
    tokens = [signed(state, {"oid": str(user)}) for user in users]
    before = time.monotonic()
    responses = await asyncio.gather(
        *(client.post("/a2a", headers={"Authorization": f"Bearer {token}"}) for token in tokens)
    )
    assert all(response.status_code == 200 for response in responses)
    assert {authorization.caller.object_id for authorization in state.authorizations} == set(users)
    assert {authorization.caller.assertion for authorization in state.authorizations} == set(tokens)
    for authorization in state.authorizations:
        assert before < authorization.deadline <= time.monotonic() + 120
        assert authorization.caller.tenant == state.verifier.tenant
        assert state.calls.count(("obo", authorization.caller.object_id)) == 1
        assert state.calls.count(("mcp", authorization.caller.object_id)) == 1
        assert state.calls.count(("model", authorization.caller.object_id)) == 1
        assert authorization.caller.assertion not in repr(authorization)
        assert str(authorization.caller.object_id) not in repr(authorization.caller)
    assert state.key_urls == [state.verifier.jwks_url]
    captured = capsys.readouterr()
    assert not any(
        value in captured.out + captured.err for value in [*tokens, *(str(u) for u in users)]
    )


async def test_mcp_and_agent_audiences_and_scopes_remain_separate(
    authority: tuple[httpx.AsyncClient, EndpointState],
    endpoint: Endpoint,
) -> None:
    agent_http, state = authority
    mcp_http, reader, embeddings, mcp_token, mcp_verifier, key = endpoint
    assert key is state.key
    state.verifier = AgentVerifier(state.verifier.client, mcp_verifier.tenant, uuid4())
    agent_http = httpx.AsyncClient(
        transport=httpx.ASGITransport(guarded(state)), base_url="https://agent.test"
    )
    async with agent_http:
        assert (
            await agent_http.post("/a2a", headers={"Authorization": f"Bearer {mcp_token}"})
        ).status_code == 401
        agent_token = signed(state)
        for token, status in (
            (agent_token, 401),
            (signed(state, {"aud": mcp_verifier.audience, "scp": "news.agent"}), 403),
        ):
            response = await mcp_http.post(
                "/mcp",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert response.status_code == status
    assert not state.calls and not reader.calls and not embeddings.calls


@pytest.mark.parametrize(
    "headers",
    [
        {"jku": "https://attacker.invalid/keys"},
        {"x5u": "https://attacker.invalid/cert"},
        {"jwk": {"kty": "RSA", "kid": "injected"}},
        {"kid": ""},
        {"kid": "x" * 257},
    ],
)
async def test_token_cannot_direct_signing_key_requests(
    authority: tuple[httpx.AsyncClient, EndpointState], headers: dict[str, object]
) -> None:
    client, state = authority
    response = await client.post(
        "/a2a", headers={"Authorization": f"Bearer {signed(state, headers=headers)}"}
    )
    assert response.status_code == 401
    assert not state.calls and not state.key_urls


async def test_forgery_unknown_key_algorithms_and_token_size_fail_closed(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    client, state = authority
    unknown = signed(state, headers={"kid": "unknown"})
    for token in [
        unknown,
        unknown,
        signed(state, key=rsa.generate_private_key(public_exponent=65537, key_size=2048)),
        jwt.encode(
            {"scp": "news.agent"},
            "local-synthetic-hmac-signing-material-only",
            algorithm="HS256",
            headers={"kid": "local-test-key"},
        ),
        "not-a-token",
        "x" * (16 * 1024 + 1),
    ]:
        assert (
            await client.post("/a2a", headers={"Authorization": f"Bearer {token}"})
        ).status_code == 401
    assert not state.calls
    assert state.key_urls == [state.verifier.jwks_url]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="NEWSLOOM_TRUSTED_KEY_CREDENTIAL_CANARY"),
        httpx.Response(200, content=b"NEWSLOOM_TRUSTED_KEY_CREDENTIAL_CANARY"),
        httpx.Response(200, content=b"x" * (128 * 1024 + 1)),
        httpx.Response(200, json={"keys": []}),
        httpx.Response(200, json={"keys": [{"kty": "EC"}]}),
    ],
)
async def test_key_failures_have_safe_explicit_availability_outcomes(
    response: httpx.Response,
    signing_key: rsa.RSAPrivateKey,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as trusted:
        state = EndpointState(AgentVerifier(trusted, uuid4(), uuid4()), signing_key)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(guarded(state)), base_url="https://agent.test"
        ) as client:
            result = await client.post("/a2a", headers={"Authorization": f"Bearer {signed(state)}"})
        assert result.status_code == 503
        assert result.json() == {"error": "trusted_keys_unavailable"}
        assert not state.calls
    captured = capsys.readouterr()
    assert "CANARY" not in result.text + captured.out + captured.err


async def test_token_and_request_deadlines_cannot_be_reset(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    client, state = authority
    token = signed(state, {"exp": int(time.time()) + 10})
    with pytest.raises(AgentFailure, match="authorization_timeout"):
        await state.verifier.authenticate(token, time.monotonic() - 1)
    assert not state.key_urls
    assert (
        await client.post("/a2a", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 200
    authorization = state.authorizations[0]
    assert 0 < authorization.deadline - time.monotonic() <= 10
    state.verifier.refreshed_at = time.monotonic() - 3601
    assert (
        await client.post("/a2a", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401
    assert len(state.authorizations) == 1


async def test_far_future_signed_expiry_still_has_a_finite_request_budget(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    client, state = authority
    token = signed(state, {"exp": 10**350})
    response = await client.post("/a2a", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert 0 < state.authorizations[0].deadline - time.monotonic() <= 120
