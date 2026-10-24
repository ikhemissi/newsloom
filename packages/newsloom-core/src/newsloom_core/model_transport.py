"""Bounded Entra Foundry transport and strict shared embedding values."""

import asyncio
import json
import math
import re
import time
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

import httpx
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import AzureError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from newsloom_core.retry import retry_delay

SCOPE = "https://cognitiveservices.azure.com/.default"
Count = Annotated[int, Field(strict=True, ge=0)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class ModelFailure(Exception):
    def __init__(self, category: str, *, retry_after: float = 0) -> None:
        if (
            not re.fullmatch(r"[a-z0-9_]+", category)
            or not math.isfinite(retry_after)
            or not 0 <= retry_after <= 2147483647
        ):
            raise ValueError("invalid_model_failure")
        super().__init__(category)
        self.retry_after = retry_after


class ServiceSafetyBlock(ModelFailure):
    def __init__(self) -> None:
        super().__init__("generation_jailbreak_filtered")


class Vector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    values: Annotated[tuple[Number, ...], Field(min_length=1536, max_length=1536)]

    @model_validator(mode="after")
    def nonzero(self) -> Vector:
        if not any(value != 0 for value in self.values):
            raise ValueError("zero_embedding")
        return self


class Usage(BaseModel):
    prompt_tokens: Count
    completion_tokens: Count


class EmbeddingUsage(BaseModel):
    prompt_tokens: Count


class EmbeddingItem(BaseModel):
    embedding: list[object]


class EmbeddingResponse(BaseModel):
    data: Annotated[list[EmbeddingItem], Field(min_length=1, max_length=1)]
    usage: EmbeddingUsage


class RequestLimits(Protocol):
    @property
    def request_seconds(self) -> float: ...
    @property
    def transport_attempts(self) -> int: ...


@dataclass(frozen=True)
class TransportLimits:
    request_seconds: float = 30
    transport_attempts: int = 3


DEFAULT_TRANSPORT_LIMITS = TransportLimits()


@dataclass
class Observations:
    generation_calls: int = 0
    embedding_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    generation_seconds: float = 0
    embedding_seconds: float = 0


def confirmed_jailbreak_block(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    error = value.get("error")
    if not isinstance(error, dict) or error.get("code") != "content_filter":
        return False
    inner = error.get("innererror")
    if not isinstance(inner, dict) or inner.get("code") != "ResponsibleAIPolicyViolation":
        return False
    filters = inner.get("content_filter_result")
    jailbreak = filters.get("jailbreak") if isinstance(filters, dict) else None
    return (
        isinstance(jailbreak, dict)
        and jailbreak.get("detected") is True
        and jailbreak.get("filtered") is True
    )


class ModelClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        credential: AsyncTokenCredential,
        endpoint: str,
        limits: RequestLimits = DEFAULT_TRANSPORT_LIMITS,
    ) -> None:
        url = httpx.URL(endpoint)
        if url.scheme != "https" or not url.host or url.userinfo or url.query or url.fragment:
            raise ModelFailure("invalid_model_endpoint")
        self.client, self.credential = client, credential
        self.endpoint = endpoint.rstrip("/")
        self.limits = limits
        self.observations = Observations()

    async def request(
        self,
        stage: Literal["generation", "embedding"],
        path: str,
        body: dict[str, object],
        deadline: float,
    ) -> object:
        for attempt in range(self.limits.transport_attempts):
            if time.monotonic() + 1 >= deadline:
                raise ModelFailure(f"{stage}_deadline")
            started = time.monotonic()
            try:
                async with asyncio.timeout_at(deadline):
                    token = await self.credential.get_token(SCOPE)
                    if stage == "generation":
                        self.observations.generation_calls += 1
                    else:
                        self.observations.embedding_calls += 1
                    async with self.client.stream(
                        "POST",
                        self.endpoint + path,
                        headers={"Authorization": f"Bearer {token.token}"},
                        json=body,
                        timeout=min(self.limits.request_seconds, deadline - time.monotonic()),
                    ) as response:
                        status = response.status_code
                        retry_header = response.headers.get("retry-after")
                        if status == 200 or (stage == "generation" and status == 400):
                            data = bytearray()
                            async for chunk in response.aiter_bytes():
                                data.extend(chunk)
                                if len(data) > 256 * 1024:
                                    raise ModelFailure(f"{stage}_response_limit")
                            try:
                                value: object = json.loads(data)
                            except ValueError:
                                raise ModelFailure(f"{stage}_invalid_json") from None
                            if status == 200:
                                return value
                            if confirmed_jailbreak_block(value):
                                raise ServiceSafetyBlock()
            except httpx.HTTPError, AzureError, TimeoutError:
                if attempt + 1 == self.limits.transport_attempts:
                    raise ModelFailure(f"{stage}_unavailable") from None
                delay = float(2**attempt)
                reason = f"{stage}_unavailable"
            else:
                reason = f"{stage}_http_{status}"
                try:
                    delay = retry_delay(retry_header, attempt)
                    if delay > 2147483647:
                        raise ValueError("invalid_retry_after")
                except ValueError:
                    raise ModelFailure(f"{stage}_invalid_retry_after") from None
                if (
                    status not in (408, 429, 500, 502, 503, 504)
                    or attempt + 1 == self.limits.transport_attempts
                ):
                    raise ModelFailure(reason, retry_after=delay)
            finally:
                elapsed = time.monotonic() - started
                if stage == "generation":
                    self.observations.generation_seconds += elapsed
                else:
                    self.observations.embedding_seconds += elapsed
            if time.monotonic() + delay + 1 >= deadline:
                raise ModelFailure(reason, retry_after=delay)
            await asyncio.sleep(delay)
        raise ModelFailure(f"{stage}_unavailable")

    def record_usage(self, usage: Usage) -> None:
        self.observations.input_tokens += usage.prompt_tokens
        self.observations.output_tokens += usage.completion_tokens
