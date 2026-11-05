"""Explicit authorization, framing and bounded execution for co-hosted HTTP news."""

import asyncio
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import psycopg
from azure.core.exceptions import AzureError
from newsloom_core.auth import TrustedKeysFailure
from newsloom_core.briefing import cutoff_at
from newsloom_core.diagnostics import event
from newsloom_core.model_transport import ModelFailure
from newsloom_core.origins import BrowserPolicy
from pydantic import BaseModel, ValidationError
from starlette.datastructures import Headers
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from newsloom_mcp.auth import Claims, EntraVerifier
from newsloom_mcp.feedback import (
    REVIEWER_ROLE,
    WRITE_SCOPE,
    FeedbackInput,
    ReviewQuery,
    export_lines,
    reader_hash,
)
from newsloom_mcp.http_models import (
    ApiFailure,
    BriefingResult,
    CatalogueResult,
    DetailResult,
    Meta,
    Page,
    ResultScope,
    SemanticInput,
    SemanticResult,
    browse_input,
    digest,
    encode_cursor,
    json_input,
    normalized,
)
from newsloom_mcp.models import DetailInput, McpFailure
from newsloom_mcp.response_cache import Entry, ResponseCache
from newsloom_mcp.services import Services

API_HEADERS = frozenset({"authorization", "accept", "content-type"})
PREFIX = "/api/v1"
SCOPES: dict[str, ResultScope] = {
    "news": "page",
    "detail": "item",
    "sources": "catalogue",
    "search": "bounded",
    "briefing": "briefing",
}


FEEDBACK_ROUTES = {
    PREFIX + "/feedback": ("feedback", "POST"),
    PREFIX + "/feedback/mine": ("feedback_mine", "GET"),
    PREFIX + "/feedback/review": ("feedback_review", "GET"),
    PREFIX + "/feedback/export": ("feedback_export", "GET"),
}


def required_scope(route: str) -> str:
    return WRITE_SCOPE if route.startswith("feedback") else "news.read"


def api_route(path: str) -> tuple[str, str] | None:
    if path in FEEDBACK_ROUTES:
        return FEEDBACK_ROUTES[path]
    if path == PREFIX + "/briefing":
        return "briefing", "GET"
    if path == PREFIX + "/news":
        return "news", "GET"
    if path.startswith(PREFIX + "/news/") and "/" not in path[len(PREFIX + "/news/") :]:
        return "detail", "GET"
    if path == PREFIX + "/sources":
        return "sources", "GET"
    if path == PREFIX + "/search":
        return "search", "POST"
    return None


def error_response(failure: ApiFailure, request_id: str, scope: str = "news.read") -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if failure.status == 401:
        headers["WWW-Authenticate"] = 'Bearer error="invalid_token"'
    if failure.status == 403 and failure.code == "insufficient_scope":
        headers["WWW-Authenticate"] = f'Bearer error="insufficient_scope", scope="{scope}"'
    return JSONResponse(
        {"error": {"code": failure.code, "request_id": request_id}},
        status_code=failure.status,
        headers=headers,
    )


class NewsApi:
    def __init__(
        self,
        app: ASGIApp,
        services: Services,
        verifier: EntraVerifier,
        semaphore: asyncio.Semaphore,
        enabled: bool,
        allowed_hosts: tuple[str, ...],
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.app, self.services, self.verifier, self.semaphore = app, services, verifier, semaphore
        self.enabled, self.allowed_hosts = enabled, allowed_hosts
        self.origins = allowed_origins
        self.cache = ResponseCache() if enabled else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope["path"] == "/api" or scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        request_id = uuid4().hex
        route = api_route(scope["path"])
        outcome, cache_state = "failure", "none"
        request = Request(scope, receive)
        origin: str | None = None
        try:
            headers = Headers(scope=scope)
            hosts = headers.getlist("host")
            if len(hosts) != 1 or hosts[0].lower() not in self.allowed_hosts:
                raise ApiFailure(403, "host_denied")
            if headers.getlist("origin"):
                try:
                    origin = BrowserPolicy(self.origins, {}, API_HEADERS).origin(
                        headers.getlist("origin")
                    )
                except ValueError:
                    raise ApiFailure(403, "origin_denied") from None
            if (
                not self.enabled
                or route is None
                or (route[0] == "briefing" and self.services.briefing is None)
                or (route[0].startswith("feedback") and self.services.feedback is None)
            ):
                raise ApiFailure(404, "not_found")
            if len(scope.get("raw_path", b"")) + len(scope.get("query_string", b"")) + 1 > 8192:
                raise ApiFailure(413, "request_limit")
            if request.method == "OPTIONS" and origin is not None:
                policy = BrowserPolicy(self.origins, {scope["path"]: route[1]}, API_HEADERS)
                if not policy.accepts_preflight(
                    scope["path"],
                    headers.getlist("access-control-request-method"),
                    headers.getlist("access-control-request-headers"),
                ):
                    raise ApiFailure(400, "preflight_denied")
                response: Response = Response(status_code=204, headers=policy.preflight_headers())
                outcome = "success"
            else:
                if request.method != route[1]:
                    raise ApiFailure(405, "method_denied")
                async with asyncio.timeout(90):
                    partition, claims = await self.authorize(headers, route[0])
                    body = bytearray()
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > 64 * 1024:
                            raise ApiFailure(413, "request_limit")
                        body.extend(chunk)
                    if request.method == "GET" and body:
                        raise ApiFailure(400, "invalid_input")
                    operation = asyncio.create_task(
                        self.execute(
                            request, bytes(body), route[0], partition, claims, started + 90
                        )
                    )
                    disconnected = asyncio.create_task(self.disconnected(receive))
                    try:
                        done, _ = await asyncio.wait(
                            (operation, disconnected),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if disconnected in done:
                            raise asyncio.CancelledError
                        response, key, entry, cache_state = operation.result()
                    finally:
                        operation.cancel()
                        disconnected.cancel()
                        await asyncio.gather(operation, disconnected, return_exceptions=True)
                # Insert only after complete execution and disconnect-task cleanup.
                if entry is not None and self.cache is not None and not self.cache.put(key, entry):
                    cache_state = "bypass"
                outcome = "success"
        except ApiFailure as failure:
            outcome = (
                "unauthorized"
                if failure.status == 401
                else "forbidden"
                if failure.status == 403
                else "failure"
            )
            response = error_response(
                failure, request_id, required_scope(route[0]) if route else "news.read"
            )
        except ValidationError, ValueError, UnicodeError, OverflowError:
            response = error_response(ApiFailure(400, "invalid_input"), request_id)
        except (
            TrustedKeysFailure,
            psycopg.Error,
            ModelFailure,
            McpFailure,
            AzureError,
            httpx.HTTPError,
        ):
            response = error_response(ApiFailure(503, "unavailable"), request_id)
        except TimeoutError:
            response = error_response(ApiFailure(504, "deadline"), request_id)
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except ClientDisconnect:
            outcome = "cancelled"
            raise asyncio.CancelledError from None
        finally:
            elapsed = time.monotonic() - started
            if self.services.observe_api is not None:
                self.services.observe_api(
                    route[0] if route else "other", outcome, cache_state, elapsed
                )
            event(
                "news_api",
                request_id,
                outcome=outcome,
                category=route[0] if route else "other",
                counts={"elapsed_seconds": round(elapsed, 3), "cache": cache_state},
            )
        if origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = (
                "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
                if request.method == "OPTIONS"
                else "Origin"
            )
        response.headers["Cache-Control"] = "no-store"
        await response(scope, receive, send)

    async def authorize(self, headers: Headers, route: str) -> tuple[str, Claims]:
        values = headers.getlist("authorization")
        if len(values) != 1 or values[0][:7].lower() != "bearer " or len(values[0]) > 16400:
            raise ApiFailure(401, "unauthorized")
        claims = await self.verifier.verify_claims(values[0][7:])
        if claims is None:
            raise ApiFailure(401, "unauthorized")
        if required_scope(route) not in claims.scp.split():
            raise ApiFailure(403, "insufficient_scope")
        if route.startswith("feedback") and claims.oid is None:
            raise ApiFailure(403, "insufficient_scope")
        if route in ("feedback_review", "feedback_export") and REVIEWER_ROLE not in claims.roles:
            raise ApiFailure(403, "forbidden")
        return digest(
            {
                "policy": 1,
                "tenant": str(claims.tid),
                "subject": claims.sub,
                "client": str(claims.azp),
                "scopes": sorted(set(claims.scp.split())),
            }
        ), claims

    async def feedback(self, request: Request, body: bytes, route: str, claims: Claims) -> Response:
        """Personal or reviewer data: never cached, never logged beyond the route outcome."""
        if self.services.feedback is None or claims.oid is None:
            raise ApiFailure(404, "not_found")
        reader = reader_hash(claims.tid, claims.oid)
        if route == "feedback":
            if request.query_params:
                raise ApiFailure(400, "invalid_input")
            types = request.headers.getlist("content-type")
            if len(types) != 1 or types[0].split(";")[0].strip().lower() != "application/json":
                raise ApiFailure(415, "unsupported_media_type")
            entry = FeedbackInput.model_validate(json_input(body))
        elif route == "feedback_mine":
            params = dict(request.query_params)
            if set(params) != {"target_type", "target_ref"}:
                raise ApiFailure(400, "invalid_input")
        else:
            query = ReviewQuery.model_validate(dict(request.query_params))
        try:
            async with asyncio.timeout(1):
                await self.semaphore.acquire()
        except TimeoutError:
            raise ApiFailure(429, "overloaded") from None
        try:
            async with self.services.feedback() as store:
                if route == "feedback":
                    if not await store.record(reader, entry):
                        raise ApiFailure(400, "invalid_input")
                    return JSONResponse({"status": "recorded"}, status_code=201)
                if route == "feedback_mine":
                    vote = await store.mine(reader, params["target_type"], params["target_ref"])
                    return JSONResponse({"vote": vote.model_dump() if vote else None})
                items = await store.review(query)
        finally:
            self.semaphore.release()
        if route == "feedback_export":
            return Response(
                export_lines(items),
                media_type="application/x-ndjson",
                headers={"Content-Disposition": 'attachment; filename="feedback.jsonl"'},
            )
        return JSONResponse({"items": [item.model_dump(mode="json") for item in items]})

    @staticmethod
    async def disconnected(receive: Receive) -> None:
        while True:
            if (await receive())["type"] == "http.disconnect":
                return

    async def execute(
        self,
        request: Request,
        body: bytes,
        route: str,
        partition: str,
        claims: Claims,
        deadline: float,
    ) -> tuple[Response, str, Entry | None, str]:
        if route.startswith("feedback"):
            return await self.feedback(request, body, route, claims), "", None, "bypass"
        cutoff = cutoff_at(datetime.now(UTC))
        args, after, identifier = None, None, None
        if route == "news":
            args, after = browse_input(request.query_params)
            parameters: object = {
                "args": normalized(args),
                "after": after.model_dump(mode="json") if after else None,
            }
        elif route == "search":
            if request.query_params:
                raise ApiFailure(400, "invalid_input")
            types = request.headers.getlist("content-type")
            if len(types) != 1 or types[0].split(";")[0].strip().lower() != "application/json":
                raise ApiFailure(415, "unsupported_media_type")
            args = SemanticInput.model_validate(json_input(body))
            parameters = normalized(args)
        else:
            if request.query_params:
                raise ApiFailure(400, "invalid_input")
            if route == "detail":
                identifier = DetailInput.model_validate({"id": request.url.path.rsplit("/", 1)[-1]})
                parameters = identifier.model_dump(mode="json")
            else:
                parameters = {"cutoff": cutoff.isoformat()} if route == "briefing" else {}
        key = digest(
            {
                "version": 1,
                "caller": partition,
                "route": route,
                "parameters": parameters,
                "model": self.services.model_revision if route == "search" else "",
            }
        )
        try:
            async with asyncio.timeout(1):
                await self.semaphore.acquire()
        except TimeoutError:
            raise ApiFailure(429, "overloaded") from None
        try:
            cached = self.cache.get(key) if self.cache is not None else None
            if cached is not None:
                return self.response(cached), key, None, "hit"
            if route == "briefing":
                if self.services.briefing is None:
                    raise ApiFailure(404, "not_found")
                started, read_at = time.monotonic(), datetime.now(UTC)
                briefing = await self.services.briefing(cutoff)
                briefing_result = BriefingResult(
                    **briefing.model_dump(),
                    meta=Meta(read_at=read_at, cache_age_seconds=0, result_scope="briefing"),
                )
                entry = Entry(
                    briefing_result.model_dump_json(exclude={"meta"}).encode(),
                    read_at,
                    started,
                    "briefing",
                )
                return self.response(entry), key, entry, "miss"
            vector = None
            if route == "search" and args is not None and args.query is not None:
                vector = (await self.services.embeddings.embed(args.query, deadline)).values
            async with self.services.repositories() as repository:
                started, read_at = time.monotonic(), datetime.now(UTC)
                meta = Meta(read_at=read_at, cache_age_seconds=0, result_scope=SCOPES[route])
                result: BaseModel
                if route == "news" and args is not None:
                    rows = await repository.browse(args, after)
                    items = rows.items[: args.limit]
                    result = Page(
                        items=items,
                        next_cursor=encode_cursor(items[-1], args)
                        if len(rows.items) > args.limit
                        else None,
                        meta=meta,
                    )
                elif route == "search" and args is not None:
                    ranked = await repository.search(args, vector)
                    result = SemanticResult(items=ranked.items, meta=meta)
                elif route == "detail" and identifier is not None:
                    detail = await repository.detail(identifier)
                    if detail.item is None:
                        raise ApiFailure(404, "not_found")
                    result = DetailResult(item=detail.item, meta=meta)
                else:
                    sources = await repository.sources()
                    result = CatalogueResult(**sources.model_dump(), meta=meta)
            payload = result.model_dump_json(exclude={"meta"}).encode()
            entry = Entry(payload, read_at, started, meta.result_scope)
            return self.response(entry), key, entry, "miss"
        except ValidationError:
            raise ApiFailure(503, "invalid_response") from None
        finally:
            self.semaphore.release()

    @staticmethod
    def response(entry: Entry) -> Response:
        value = json.loads(entry.payload)
        value["meta"] = Meta(
            read_at=entry.read_at,
            cache_age_seconds=max(0, time.monotonic() - entry.started),
            result_scope=entry.result_scope,
        ).model_dump(mode="json")
        payload = json.dumps(
            value, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
        if len(payload) > 1024 * 1024:
            raise ApiFailure(503, "response_limit")
        return Response(
            payload, media_type="application/json", headers={"Cache-Control": "no-store"}
        )
