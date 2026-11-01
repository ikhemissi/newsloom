"""Exact browser CORS without application admission or authorization fallback."""

from newsloom_core.origins import BrowserPolicy
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PATH_METHODS = {"/a2a": "POST", "/.well-known/agent-card.json": "GET"}
ALLOW_HEADERS = {"authorization", "content-type", "a2a-version", "accept"}


class BrowserCors:
    def __init__(self, app: ASGIApp, allowed_origins: tuple[str, ...]) -> None:
        self.app = app
        self.policy = BrowserPolicy(allowed_origins, PATH_METHODS, frozenset(ALLOW_HEADERS))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origins = headers.getlist("origin")
        if not origins:
            await self.app(scope, receive, send)
            return
        try:
            origin = self.policy.origin(origins)
        except ValueError:
            await JSONResponse({"error": "origin_denied"}, status_code=403)(scope, receive, send)
            return

        async def cors_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["Access-Control-Allow-Origin"] = origin
                if "origin" not in {
                    value.strip().lower() for value in response_headers.get("vary", "").split(",")
                }:
                    response_headers.add_vary_header("Origin")
            await send(message)

        if scope["method"] == "OPTIONS":
            methods = headers.getlist("access-control-request-method")
            requested = headers.getlist("access-control-request-headers")
            if not self.policy.accepts_preflight(scope["path"], methods, requested):
                await JSONResponse({"error": "preflight_denied"}, status_code=400)(
                    scope, receive, cors_send
                )
                return
            await Response(
                status_code=204,
                headers=self.policy.preflight_headers(),
            )(scope, receive, cors_send)
            return
        await self.app(scope, receive, cors_send)
