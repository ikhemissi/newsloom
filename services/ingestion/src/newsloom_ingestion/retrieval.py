"""Public-only, DNS-pinned, bounded HTTPS retrieval including robots policy."""

import asyncio
import ipaddress
import socket
import time
import zlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult

from newsloom_ingestion.models import DEFAULT_LIMITS, Document, IngestionFailure, Limits

USER_AGENT = "Newsloom/0.1"
RETRYABLE = {408, 429, 500, 502, 503, 504}


def public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    return address.is_global and not address.is_multicast and (mapped is None or mapped.is_global)


def check_url(url: str) -> None:
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 443)
        ):
            raise IngestionFailure("unsafe_url")
        try:
            ipaddress.ip_address(parts.hostname)
        except ValueError:
            if "%" in parts.hostname or "\\" in parts.netloc:
                raise IngestionFailure("unsafe_url") from None
        else:
            if not public_address(parts.hostname):
                raise IngestionFailure("nonpublic_address")
    except ValueError:
        raise IngestionFailure("invalid_url") from None


class PublicResolver(AbstractResolver):
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        answers = await asyncio.get_running_loop().getaddrinfo(
            host, port, family=family, type=socket.SOCK_STREAM
        )
        if not answers or any(not public_address(str(answer[4][0])) for answer in answers):
            raise IngestionFailure("nonpublic_dns")
        return [
            ResolveResult(
                hostname=host,
                host=str(address[0]),
                port=port,
                family=int(answer_family),
                proto=protocol,
                flags=socket.AI_NUMERICHOST,
            )
            for answer_family, _, protocol, _, address in answers
        ]

    async def close(self) -> None:
        return None


def retry_delay(value: str | None, attempt: int) -> float:
    if value is None:
        return float(2**attempt)
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except ValueError, TypeError, OverflowError:
            raise IngestionFailure("invalid_retry_after") from None
    if not 0 <= seconds < float("inf"):
        raise IngestionFailure("invalid_retry_after")
    return seconds


class PublicClient:
    def __init__(self, limits: Limits = DEFAULT_LIMITS) -> None:
        self.limits = limits

    async def request(self, url: str, headers: dict[str, str], limit: int) -> Document:
        check_url(url)
        timeout = aiohttp.ClientTimeout(
            total=self.limits.request_seconds,
            connect=self.limits.connect_seconds,
            sock_connect=self.limits.connect_seconds,
        )
        connector = aiohttp.TCPConnector(
            resolver=PublicResolver(), use_dns_cache=False, force_close=True
        )
        async with (
            aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                auto_decompress=False,
                cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=False,
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
            ) as client,
            client.get(url, headers=headers, allow_redirects=False, ssl=True) as response,
        ):
            encoding = response.headers.get("Content-Encoding", "identity").lower()
            if encoding not in ("identity", "gzip", "deflate"):
                raise IngestionFailure("unsupported_content_encoding")
            decoder = (
                zlib.decompressobj(31 if encoding == "gzip" else 15)
                if encoding != "identity"
                else None
            )
            body = bytearray()
            wire_size = 0
            try:
                async for chunk in response.content.iter_chunked(65536):
                    wire_size += len(chunk)
                    if wire_size > limit:
                        raise IngestionFailure("body_limit")
                    body.extend(
                        decoder.decompress(chunk, limit + 1 - len(body))
                        if decoder is not None
                        else chunk
                    )
                    if len(body) > limit:
                        raise IngestionFailure("body_limit")
                if decoder is not None and (not decoder.eof or decoder.unused_data):
                    raise IngestionFailure("invalid_compressed_body")
            except zlib.error:
                raise IngestionFailure("invalid_compressed_body") from None
            return Document(
                response.status,
                url,
                bytes(body),
                {key.lower(): value for key, value in response.headers.items()},
            )

    async def robots(self, url: str, deadline: float) -> None:
        parts = urlsplit(url)
        policy_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        response = await self.fetch(policy_url, {}, deadline, robots=True)
        if response.status in (404, 410):
            return
        if response.status != 200:
            raise IngestionFailure(f"robots_http_{response.status}")
        policy = RobotFileParser()
        policy.parse(response.body.decode("utf-8", errors="replace").splitlines())
        if not policy.can_fetch(USER_AGENT, url):
            raise IngestionFailure("robots_denied")

    async def fetch(
        self, url: str, headers: dict[str, str], deadline: float, *, robots: bool = False
    ) -> Document:
        for redirect in range(self.limits.redirects + 1):
            check_url(url)
            if not robots:
                await self.robots(url, deadline)
            response: Document | None = None
            for attempt in range(self.limits.retries + 1):
                if time.monotonic() >= deadline:
                    raise IngestionFailure("feed_deadline")
                try:
                    async with asyncio.timeout_at(deadline):
                        response = await self.request(
                            url,
                            headers,
                            self.limits.robots_bytes if robots else self.limits.body_bytes,
                        )
                except aiohttp.ClientError, TimeoutError, OSError:
                    if attempt == self.limits.retries:
                        raise IngestionFailure("retrieval_failed") from None
                    delay = retry_delay(None, attempt)
                else:
                    if response.status not in RETRYABLE:
                        break
                    if attempt == self.limits.retries:
                        raise IngestionFailure(f"http_{response.status}")
                    delay = retry_delay(response.headers.get("retry-after"), attempt)
                if time.monotonic() + delay >= deadline:
                    raise IngestionFailure("retry_deferred")
                await asyncio.sleep(delay)
            if response is None:
                raise IngestionFailure("missing_response")
            if response.status not in (301, 302, 303, 307, 308):
                return response
            if redirect == self.limits.redirects:
                raise IngestionFailure("redirect_limit")
            location = response.headers.get("location")
            if not location:
                raise IngestionFailure("missing_redirect")
            url = urljoin(url, location)
            headers = {}
        raise IngestionFailure("redirect_limit")
