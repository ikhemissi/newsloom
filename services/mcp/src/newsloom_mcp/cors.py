"""Modern MCP CORS using the shared exact-origin policy and standard ASGI middleware."""

from newsloom_core.origins import BrowserPolicy
from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

HEADERS = frozenset(
    {
        "authorization",
        "content-type",
        "accept",
        "mcp-protocol-version",
        "mcp-method",
        "mcp-name",
    }
)


class McpBrowserCors(CORSMiddleware):
    def __init__(self, app: ASGIApp, allowed_origins: tuple[str, ...]) -> None:
        self.policy = BrowserPolicy(allowed_origins, {"/mcp": "POST"}, HEADERS)
        super().__init__(
            app,
            allow_origins=list(self.policy.origins),
            allow_methods=["POST"],
            allow_headers=list(HEADERS),
            allow_credentials=False,
            max_age=300,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            values = headers.getlist("origin")
            if values:
                try:
                    origin = self.policy.origin(values)
                except ValueError:
                    await JSONResponse({"error": "origin_denied"}, status_code=403)(
                        scope, receive, send
                    )
                    return
                if scope["method"] == "OPTIONS":
                    if not self.policy.accepts_preflight(
                        scope["path"],
                        headers.getlist("access-control-request-method"),
                        headers.getlist("access-control-request-headers"),
                    ):
                        await JSONResponse(
                            {"error": "preflight_denied"},
                            status_code=400,
                            headers={"Access-Control-Allow-Origin": origin, "Vary": "Origin"},
                        )(scope, receive, send)
                        return
                    await Response(
                        status_code=204,
                        headers={
                            "Access-Control-Allow-Origin": origin,
                            **self.policy.preflight_headers(),
                        },
                    )(scope, receive, send)
                    return
                if scope["path"] != "/mcp" or scope["method"] != "POST":
                    await JSONResponse(
                        {"error": "browser_method_denied"},
                        status_code=405,
                        headers={"Access-Control-Allow-Origin": origin, "Vary": "Origin"},
                    )(scope, receive, send)
                    return
        await super().__call__(scope, receive, send)
