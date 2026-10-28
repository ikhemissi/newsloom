import asyncio
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit

import httpx2
from azure.core.pipeline.transport import AsyncHttpResponse, AsyncHttpTransport, HttpRequest
from pydantic import JsonValue, TypeAdapter

from agent_evaluation.inputs import json_document
from agent_evaluation.policy import EvaluationFailure, verify_privacy


def project_endpoint(endpoint: str, account_endpoint: str, project_id: str) -> str:
    account = urlsplit(account_endpoint)
    selected = urlsplit(endpoint)
    if (
        selected.scheme != "https"
        or selected.hostname != account.hostname
        or not selected.hostname
        or not selected.hostname.endswith(".services.ai.azure.com")
        or selected.netloc != account.netloc
        or selected.path != "/api/projects/" + project_id.rsplit("/", 1)[-1]
        or selected.query
        or selected.fragment
        or selected.username is not None
        or selected.password is not None
    ):
        raise EvaluationFailure("foreign_evaluation_project_endpoint")
    return endpoint


class ProjectTransport(httpx2.AsyncBaseTransport):
    def __init__(
        self,
        inner: httpx2.AsyncBaseTransport,
        admit: Callable[[httpx2.Request], Awaitable[float]],
        inspect: Callable[[httpx2.Request, dict[str, JsonValue]], None],
    ) -> None:
        self.inner = inner
        self.admit = admit
        self.inspect = inspect

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        verify_privacy()
        timeout = await self.admit(request)
        if len(await request.aread()) > 64 * 1024:
            raise EvaluationFailure("publication_request_byte_limit")
        request.headers["Accept-Encoding"] = "identity"
        async with asyncio.timeout(timeout):
            response = await self.inner.handle_async_request(request)
            try:
                if response.is_redirect:
                    raise EvaluationFailure("publication_redirect_rejected")
                expected = {
                    "GET": (200,),
                    "POST": (200, 201),
                    "DELETE": (200, 204),
                }.get(request.method, ())
                if 200 <= response.status_code < 300 and response.status_code not in expected:
                    raise EvaluationFailure("publication_unexpected_success_status")
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise EvaluationFailure("publication_encoded_response_rejected")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if len(body) + len(chunk) > 1024 * 1024:
                        raise EvaluationFailure("publication_response_byte_limit")
                    body.extend(chunk)
                if response.status_code in (200, 201):
                    json_document(bytes(body))
                    value = TypeAdapter(JsonValue).validate_json(body, strict=True)
                    if not isinstance(value, dict):
                        raise EvaluationFailure("invalid_publication_response")
                    self.inspect(request, value)
                return httpx2.Response(
                    response.status_code,
                    headers=response.headers,
                    content=bytes(body),
                    request=request,
                )
            finally:
                await response.aclose()

    async def aclose(self) -> None:
        await self.inner.aclose()


class _Response(AsyncHttpResponse):
    def __init__(self, request: HttpRequest, response: httpx2.Response) -> None:
        super().__init__(request, internal_response=None)
        self.status_code = response.status_code
        self.headers = dict(response.headers)
        self.reason = response.reason_phrase
        self.content_type = response.headers.get("content-type", "application/json")
        self._body = response.content

    def body(self) -> bytes:
        return self._body

    def json(self) -> JsonValue:
        return TypeAdapter(JsonValue).validate_json(self._body, strict=True)


class CatalogTransport(AsyncHttpTransport[HttpRequest, AsyncHttpResponse]):
    def __init__(self, transport: ProjectTransport) -> None:
        self.client = httpx2.AsyncClient(
            transport=transport, trust_env=False, follow_redirects=False
        )

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.close()

    async def send(self, request: HttpRequest, **kwargs: object) -> AsyncHttpResponse:
        content = request.body
        if content is not None and not isinstance(content, str | bytes):
            raise EvaluationFailure("invalid_catalog_request_body")
        response = await self.client.request(
            request.method,
            request.url,
            headers=request.headers,
            content=content,
        )
        return _Response(request, response)
