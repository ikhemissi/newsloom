"""Loopback-only authored MCP SDK contract fixture; never production news or identity."""

import asyncio
import json
import socket
from uuid import uuid4

import uvicorn
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    Tool,
)
from newsloom_mcp.models import NewsResults, RecentInput, SearchInput, SearchResults
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send


async def tools(
    context: ServerRequestContext[None],
    params: PaginatedRequestParams | None,
) -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(
                name="get_recent_news",
                input_schema=RecentInput.model_json_schema(),
                output_schema=NewsResults.model_json_schema(),
            ),
            Tool(
                name="search_news",
                input_schema=SearchInput.model_json_schema(),
                output_schema=SearchResults.model_json_schema(),
            ),
        ]
    )


async def call(
    context: ServerRequestContext[None], params: CallToolRequestParams
) -> CallToolResult:
    values = dict(params.arguments or {})
    if params.name == "search_news":
        SearchInput.model_validate(values)
        if values.get("query") == "empty":
            return CallToolResult(content=[], structured_content={"items": []})
        if values.get("query") == "delay":
            await asyncio.sleep(5)
    else:
        RecentInput.model_validate(values)
    return CallToolResult(
        content=[],
        structured_content={
            "items": [
                {
                    "id": str(uuid4()),
                    "title": "Authored SDK result",
                    "summary": "Authored summary.",
                    "source": "fixture-source",
                    "category": "agents",
                    "tags": [],
                    "published_at": "2026-11-01T08:00:00Z",
                    "url": "https://publisher.test/article",
                    **({"similarity": 0.9} if params.name == "search_news" else {}),
                }
            ]
        },
    )


server = Server[None](
    "authored-browser-contract",
    version="0.1.0",
    on_list_tools=tools,
    on_call_tool=call,
    get_tool_input_schema=lambda name: (
        SearchInput.model_json_schema()
        if name == "search_news"
        else RecentInput.model_json_schema()
    ),
)
app = server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(allowed_hosts=["127.0.0.1:*"]),
)


async def authorized(scope: Scope, receive: Receive, send: Send) -> None:
    if (
        scope["type"] == "http"
        and Headers(scope=scope).get("authorization") != "Bearer fixture-news-token"
    ):
        await JSONResponse({"error": "authored_auth_denied"}, status_code=401)(scope, receive, send)
        return
    await app(scope, receive, send)


if __name__ == "__main__":
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        print(json.dumps({"port": listener.getsockname()[1]}), flush=True)
        uvicorn.Server(
            uvicorn.Config(authorized, log_config=None, log_level="critical", access_log=False)
        ).run(sockets=[listener])
