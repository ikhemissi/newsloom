import json
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from newsloom_mcp.auth import EntraVerifier


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks(key: rsa.RSAPrivateKey) -> dict[str, object]:
    value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {"keys": [{**value, "kid": "local-test-key", "use": "sig"}]}


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"exp": 1},
        {"nbf": int(time.time()) + 3600},
        {"aud": "wrong-audience"},
        {"iss": "https://wrong.invalid"},
        {"tid": str(uuid4())},
        {"ver": "1.0"},
        {"scp": ""},
        {"scp": "profile other.read"},
        {"azp": "invalid"},
    ],
)
async def test_claim_verification_never_substitutes_resources(
    change: dict[str, object],
    signing_key: rsa.RSAPrivateKey,
) -> None:
    tenant, audience = uuid4(), uuid4()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=jwks(signing_key))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = EntraVerifier(client, tenant, audience)
        claims = {
            "iss": verifier.issuer,
            "aud": str(audience),
            "tid": str(tenant),
            "sub": "synthetic-subject",
            "azp": str(uuid4()),
            "exp": int(time.time()) + 300,
            "nbf": int(time.time()) - 5,
            "ver": "2.0",
            "scp": "news.read",
            **change,
        }
        token = jwt.encode(
            claims, signing_key, algorithm="RS256", headers={"kid": "local-test-key"}
        )
        result = await verifier.verify_token(token)
        if not change:
            assert result is not None and result.resource == str(audience)
            assert result.scopes == [f"api://{audience}/news.read"]
        elif "scp" in change:
            assert result is not None and result.scopes == []
        else:
            assert result is None
        assert calls == [verifier.jwks_url]


async def test_unsafe_headers_and_forged_tokens_cannot_retrieve_caller_urls(
    signing_key: rsa.RSAPrivateKey,
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=jwks(signing_key))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = EntraVerifier(client, uuid4(), uuid4())
        headers: list[dict[str, object]] = [
            {"jku": "https://attacker.invalid/keys"},
            {"x5u": "https://attacker.invalid/cert"},
            {"jwk": jwks(signing_key)},
            {"alg": "HS256"},
        ]
        for header in headers:
            if header.get("alg") == "HS256":
                token = jwt.encode(
                    {"scp": "news.read"},
                    "synthetic-local-test-secret-value",
                    algorithm="HS256",
                    headers={"kid": "local-test-key"},
                )
            else:
                token = jwt.encode(
                    {"scp": "news.read"},
                    signing_key,
                    algorithm="RS256",
                    headers={"kid": "local-test-key", **header},
                )
            assert await verifier.verify_token(token) is None
        assert calls == []
        assert await verifier.verify_token("not-a-token") is None
        assert await verifier.verify_token("x" * (16 * 1024 + 1)) is None


async def test_unknown_key_refresh_is_bounded_and_key_failure_is_safe(
    signing_key: rsa.RSAPrivateKey,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=jwks(signing_key))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = EntraVerifier(client, uuid4(), uuid4())
        token = jwt.encode(
            {"scp": "news.read"}, signing_key, algorithm="RS256", headers={"kid": "unknown"}
        )
        assert await verifier.verify_token(token) is None
        assert await verifier.verify_token(token) is None
        assert len(calls) == 1
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(503, text="NEWSLOOM_CREDENTIAL_CANARY")
        )
    ) as client:
        verifier = EntraVerifier(client, uuid4(), uuid4())
        assert await verifier.verify_token(token) is None
    assert "CANARY" not in capsys.readouterr().out
