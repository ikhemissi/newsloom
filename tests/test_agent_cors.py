import httpx
import pytest
from newsloom_agent.app import create_app
from newsloom_agent.cors import BrowserCors
from newsloom_agent.serving import TaskRegistry
from newsloom_core.origins import normalize_origins
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send
from test_agent_auth import EndpointState
from test_agent_auth import authority as authority
from test_agent_serving import Reader
from test_mcp_auth import signing_key as signing_key


@pytest.mark.parametrize(
    ("path", "method", "fields", "status"),
    [
        ("/a2a", "POST", "Authorization, Content-Type, A2A-Version, Accept", 204),
        ("/.well-known/agent-card.json", "GET", "A2A-Version", 204),
        ("/a2a", "DELETE", "", 400),
        ("/other", "POST", "", 400),
        ("/a2a", "POST", "A2A-Extensions", 400),
        ("/a2a", "POST", "Cookie", 400),
        ("/a2a", "POST", "authorization,", 400),
    ],
)
async def test_preflight_never_enters_application(
    path: str, method: str, fields: str, status: int
) -> None:
    calls: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append(scope["method"])
        await JSONResponse({"error": "denied"}, status_code=401)(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(BrowserCors(app, ("https://ui.test",))),
        base_url="https://agent.test",
    ) as client:
        response = await client.options(
            path,
            headers={
                "Origin": "https://ui.test",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": fields,
            },
        )
    assert response.status_code == status
    assert calls == []
    assert response.headers["Access-Control-Allow-Origin"] == "https://ui.test"
    assert "Access-Control-Allow-Credentials" not in response.headers
    if status == 204:
        assert response.headers["Access-Control-Max-Age"] == "300"
        assert "Origin" in response.headers["Vary"]


async def test_real_auth_denial_is_visible_without_read_or_model(
    authority: tuple[httpx.AsyncClient, EndpointState],
) -> None:
    _, state = authority
    reader, registry = Reader(), TaskRegistry()
    app = create_app(
        reader,
        state.verifier,
        registry=registry,
        public_url="https://agent.test/a2a",
        allowed_origins=("https://ui.test",),
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://agent.test"
        ) as client:
            response = await client.post("/a2a", headers={"Origin": "https://ui.test"})
            assert response.status_code == 401
            assert response.headers["Access-Control-Allow-Origin"] == "https://ui.test"
            for origins in (
                [("Origin", "https://other.test")],
                [("Origin", "https://ui.test"), ("Origin", "https://ui.test")],
            ):
                denied = await client.options(
                    "/a2a", headers=[*origins, ("Access-Control-Request-Method", "POST")]
                )
                assert denied.status_code == 403
                assert "Access-Control-Allow-Origin" not in denied.headers
            public = await client.get("/.well-known/agent-card.json")
            assert public.status_code == 200
            assert "Access-Control-Allow-Origin" not in public.headers
        assert reader.calls == []
        assert registry.records == {}
    finally:
        await registry.close()


@pytest.mark.parametrize(
    "value",
    [
        "http://ui.test",
        "https://*.test",
        "https://ui.test/",
        "https://ui.test:443",
        "https://ui.test:65536",
        "https://user@ui.test",
        "https://ui.test?x=1",
        "",
    ],
)
def test_invalid_origin_configuration_fails(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_origins([value])


def test_origin_configuration_is_canonical_and_ordered() -> None:
    assert normalize_origins(["https://b.test", "https://a.test", "https://a.test"]) == (
        "https://a.test",
        "https://b.test",
    )


@pytest.mark.parametrize("status", [200, 401, 403, 429, 504])
async def test_allowed_browser_can_observe_real_response_status(status: int) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse({"outcome": "fixture"}, status_code=status)(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(BrowserCors(app, ("https://ui.test",))),
        base_url="https://agent.test",
    ) as client:
        response = await client.post("/a2a", headers={"Origin": "https://ui.test"})
    assert response.status_code == status
    assert response.headers["Access-Control-Allow-Origin"] == "https://ui.test"
    assert response.headers["Vary"] == "Origin"
    assert "Access-Control-Allow-Credentials" not in response.headers
