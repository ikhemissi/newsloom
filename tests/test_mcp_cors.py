import httpx
import pytest
from newsloom_mcp.cors import McpBrowserCors
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send


@pytest.mark.parametrize(
    ("path", "method", "fields", "status"),
    [
        (
            "/mcp",
            "POST",
            "Authorization, Content-Type, Accept, MCP-Protocol-Version, Mcp-Method, Mcp-Name",
            204,
        ),
        ("/mcp", "GET", "Mcp-Method", 400),
        ("/mcp", "POST", "Mcp-Session-Id", 400),
        ("/other", "POST", "Authorization", 400),
    ],
)
async def test_mcp_preflight_is_exact_and_consumes_no_application_work(
    path: str,
    method: str,
    fields: str,
    status: int,
) -> None:
    calls: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append(scope["method"])
        await JSONResponse({}, status_code=401)(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(McpBrowserCors(app, ("https://ui.test",))),
        base_url="https://mcp.test",
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
    assert "Origin" in response.headers["Vary"]


@pytest.mark.parametrize("status", [200, 401, 403, 429, 503])
async def test_mcp_cors_preserves_real_outcomes_and_existing_clients(status: int) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse({"outcome": "fixture"}, status_code=status)(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(McpBrowserCors(app, ("https://ui.test",))),
        base_url="https://mcp.test",
    ) as client:
        response = await client.post("/mcp", headers={"Origin": "https://ui.test"})
        assert response.status_code == status
        assert response.headers["Access-Control-Allow-Origin"] == "https://ui.test"
        assert "Origin" in response.headers["Vary"]
        native = await client.post("/mcp")
        assert native.status_code == status
        assert "Access-Control-Allow-Origin" not in native.headers
        duplicate = await client.post(
            "/mcp",
            headers=[
                ("Origin", "https://ui.test"),
                ("Origin", "https://ui.test"),
            ],
        )
        assert duplicate.status_code == 403
        unsupported = await client.get("/mcp", headers={"Origin": "https://ui.test"})
        assert unsupported.status_code == 405
