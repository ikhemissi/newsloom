import asyncio
from typing import Final, Literal
from urllib.parse import urlsplit

import httpx2
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import get_bearer_token_provider
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError

from agent_evaluation.budget import MODEL_SNAPSHOT, Budget, Usage
from agent_evaluation.inputs import json_document
from agent_evaluation.policy import EvaluationFailure, verify_privacy


class _Envelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    model: StrictStr
    usage: Usage | None = None


class _Message(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    role: Literal["user"]
    content: StrictStr


class _Request(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model: StrictStr
    messages: tuple[_Message]
    max_completion_tokens: int
    n: int
    stream: Literal[False]
    store: Literal[False]
    reasoning_effort: Literal["none"]
    response_format: dict[str, object]


def chat_endpoint(account_endpoint: str) -> str:
    try:
        parts = urlsplit(account_endpoint)
        port = parts.port
    except ValueError:
        raise EvaluationFailure("invalid_fixed_judge_endpoint") from None
    if (
        parts.scheme != "https"
        or parts.hostname is None
        or not parts.hostname.endswith((".openai.azure.com", ".services.ai.azure.com"))
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise EvaluationFailure("invalid_fixed_judge_endpoint")
    return account_endpoint.rstrip("/") + "/openai/v1/chat/completions"


RETRYABLE_STATUS: Final = frozenset({429, 500, 502, 503, 504})


class _Retryable(Exception):
    """A lost or throttled judge response that the budget may retry once."""


class JudgeTransport(httpx2.AsyncBaseTransport):
    def __init__(
        self,
        endpoint: str,
        deployment: str,
        budget: Budget,
        inner: httpx2.AsyncBaseTransport,
    ) -> None:
        self.url = httpx2.URL(chat_endpoint(endpoint))
        self.deployment = deployment
        self.budget = budget
        self.inner = inner

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        verify_privacy()
        if request.method != "POST" or request.url != self.url:
            raise EvaluationFailure("judge_endpoint_or_method_rejected")
        content = await request.aread()
        json_document(content)
        try:
            payload = _Request.model_validate_json(content)
        except ValidationError:
            raise EvaluationFailure("invalid_fixed_judge_request") from None
        if (
            payload.model != self.deployment
            or payload.n != 1
            or payload.max_completion_tokens != self.budget.limits.output_tokens
            or payload.response_format.get("type") != "json_schema"
        ):
            raise EvaluationFailure("judge_configuration_mismatch")
        async with self.budget.lock:
            retried = False
            while True:
                try:
                    return await self.dispatch(request, content)
                except _Retryable:
                    if retried or self.retries_used() >= self.budget.limits.transport_retries:
                        self.budget.halted = True
                        await self.budget.checkpoint()
                        raise EvaluationFailure("judge_transport_failed") from None
                    retried = True
                    self.budget.attempts[-1].superseded = True
                    await self.budget.checkpoint()

    def retries_used(self) -> int:
        return sum(row.superseded for row in self.budget.attempts)

    async def dispatch(self, request: httpx2.Request, content: bytes) -> httpx2.Response:
        try:
            async with asyncio.timeout(self.budget.remaining()):
                await self.budget.pace()
                if self.budget.ready is not None:
                    await self.budget.ready()
                row = await self.budget.admit(len(content))
                succeeded = False
                retryable = False
                # Profiles without retries keep their original error paths.
                allow = self.budget.limits.transport_retries > 0
                try:
                    try:
                        response = await self.inner.handle_async_request(request)
                    except httpx2.TransportError:
                        if not allow:
                            raise
                        retryable = True
                        raise _Retryable from None
                    try:
                        if response.is_redirect:
                            raise EvaluationFailure("judge_redirect_rejected")
                        if response.headers.get("content-encoding", "identity") != "identity":
                            raise EvaluationFailure("judge_encoded_response_rejected")
                        body = bytearray()
                        try:
                            async for chunk in response.aiter_bytes(chunk_size=1024):
                                self.budget.consume(row, len(chunk))
                                body.extend(chunk)
                        except httpx2.TransportError:
                            if not allow:
                                raise
                            retryable = True
                            raise _Retryable from None
                        self.budget.remaining()
                        row.response_complete = True
                        if allow and response.status_code in RETRYABLE_STATUS:
                            retryable = True
                            raise _Retryable
                        if response.status_code == 200:
                            json_document(bytes(body))
                            try:
                                envelope = _Envelope.model_validate_json(body)
                            except ValidationError:
                                raise EvaluationFailure("invalid_judge_usage") from None
                            if envelope.model != MODEL_SNAPSHOT:
                                raise EvaluationFailure("judge_model_snapshot_mismatch")
                            if envelope.usage is not None:
                                self.budget.observe(row, envelope.usage)
                        result = httpx2.Response(
                            response.status_code,
                            headers=response.headers,
                            content=bytes(body),
                            request=request,
                        )
                    finally:
                        await response.aclose()
                    succeeded = response.status_code == 200
                    return result
                finally:
                    if not succeeded and not retryable:
                        self.budget.halted = True
                    await self.budget.checkpoint()
        except TimeoutError:
            raise EvaluationFailure("evaluation_deadline") from None

    async def aclose(self) -> None:
        await self.inner.aclose()


class Completion:
    def __init__(self, client: AsyncOpenAI, deployment: str, budget: Budget) -> None:
        self.client = client
        self.deployment = deployment
        self.budget = budget

    async def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        async with self.budget.operation_lock:
            succeeded = False
            try:
                verify_privacy()
                if self.budget.halted:
                    raise EvaluationFailure("judge_admission_halted")
                response = await self.client.chat.completions.parse(
                    model=self.deployment,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=schema,
                    max_completion_tokens=self.budget.limits.output_tokens,
                    n=1,
                    store=False,
                    reasoning_effort="none",
                )
                if len(response.choices) != 1 or response.choices[0].message.parsed is None:
                    raise EvaluationFailure("missing_structured_judge_response")
                succeeded = True
                return response.choices[0].message.parsed
            finally:
                if not succeeded:
                    self.budget.halted = True
                    await self.budget.checkpoint()


def model_client(
    endpoint: str, deployment: str, credential: AsyncTokenCredential, budget: Budget
) -> AsyncOpenAI:
    verify_privacy()
    url = chat_endpoint(endpoint)
    return AsyncOpenAI(
        base_url=url.removesuffix("/chat/completions"),
        api_key=get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        ),
        max_retries=0,
        organization="",
        project="",
        timeout=min(60.0, budget.remaining()),
        http_client=httpx2.AsyncClient(
            transport=JudgeTransport(
                endpoint,
                deployment,
                budget,
                httpx2.AsyncHTTPTransport(retries=0, trust_env=False),
            ),
            follow_redirects=False,
            trust_env=False,
            headers={"Accept-Encoding": "identity"},
        ),
    )
