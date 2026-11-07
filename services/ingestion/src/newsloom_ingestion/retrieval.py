"""Public-only, DNS-pinned, bounded HTTPS retrieval including robots policy."""

import asyncio
import ipaddress
import socket
import time
import zlib
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from newsloom_core.retry import retry_delay as shared_retry_delay

from newsloom_ingestion.models import DEFAULT_LIMITS, Document, IngestionFailure, Limits

USER_AGENT = "Newsloom/0.2 (+https://github.com/ikhemissi/newsloom)"
ROBOTS_TOKEN = "Newsloom"
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


def content_signals(text: str) -> dict[str, str]:
    """Content-Signal values of the robots group that applies to Newsloom, else `*`."""
    groups: list[tuple[list[str], dict[str, str]]] = []
    agents: list[str] = []
    signals: dict[str, str] = {}
    shared: dict[str, str] = {}
    previous_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.casefold()
        if key == "user-agent":
            if not previous_agent:
                agents, signals = [], {}
                groups.append((agents, signals))
            agents.append(value.casefold())
            previous_agent = True
            continue
        previous_agent = False
        if key == "content-signal":
            target = signals if groups else shared
            for item in value.split(","):
                name, _, setting = item.partition("=")
                if name.strip() and setting.strip():
                    target[name.strip().casefold()] = setting.strip().casefold()
    token = ROBOTS_TOKEN.casefold()
    chosen = next(
        (found for names, found in groups if any(n != "*" and n in token for n in names)), None
    )
    if chosen is None:
        chosen = next((found for names, found in groups if "*" in names), {})
    return {**shared, **chosen}


@dataclass(frozen=True)
class RobotsDecision:
    policy: RobotFileParser | None
    failure: str | None = None
    ai_input: bool = True


def retry_delay(value: str | None, attempt: int) -> float:
    try:
        return shared_retry_delay(value, attempt)
    except ValueError:
        raise IngestionFailure("invalid_retry_after") from None


class PublicClient:
    def __init__(self, limits: Limits = DEFAULT_LIMITS) -> None:
        self.limits = limits
        self.robots_cache: dict[str, RobotsDecision] = {}
        self.robots_locks: dict[str, asyncio.Lock] = {}
        self.host_locks: dict[str, asyncio.Lock] = {}

    async def article(self, url: str, deadline: float) -> Document:
        check_url(url)
        host = urlsplit(url).netloc.casefold()
        async with asyncio.timeout_at(deadline), self.host_locks.setdefault(host, asyncio.Lock()):
            await self.robots(url, deadline, article=True)
            for attempt in range(2):
                try:
                    response = await self.request(url, {}, self.limits.body_bytes)
                except aiohttp.ClientError, OSError:
                    raise IngestionFailure("article_unavailable") from None
                if response.status not in (429, 503) or attempt:
                    break
                # One polite retry when the publisher asks us to wait briefly.
                delay = retry_delay(response.headers.get("retry-after"), attempt)
                if delay > 60 or time.monotonic() + delay >= deadline:
                    raise IngestionFailure("article_throttled")
                await asyncio.sleep(delay)
        if response.status in (429, 503):
            raise IngestionFailure("article_throttled")
        if response.status in (301, 302, 303, 307, 308):
            raise IngestionFailure("article_redirect")
        if response.status != 200:
            raise IngestionFailure(f"article_http_{response.status}")
        content_type = response.headers.get("content-type", "text/html").split(";", 1)[0].strip()
        if content_type not in ("text/html", "application/xhtml+xml"):
            raise IngestionFailure("article_content_type")
        return response

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

    async def robots(self, url: str, deadline: float, *, article: bool = False) -> None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}".casefold()
        async with self.robots_locks.setdefault(origin, asyncio.Lock()):
            decision = self.robots_cache.get(origin)
            if decision is None:
                decision = await self.load_robots(origin, deadline)
                self.robots_cache[origin] = decision
        if decision.failure is not None:
            raise IngestionFailure(decision.failure)
        if decision.policy is not None and not decision.policy.can_fetch(ROBOTS_TOKEN, url):
            raise IngestionFailure("robots_denied")
        if article and not decision.ai_input:
            raise IngestionFailure("content_signal_denied")

    async def load_robots(self, origin: str, deadline: float) -> RobotsDecision:
        """One robots.txt per origin per run; transient failures are not cached."""
        response = await self.fetch(f"{origin}/robots.txt", {}, deadline, robots=True)
        if response.status in (404, 410):
            return RobotsDecision(None)
        if response.status != 200:
            raise IngestionFailure(f"robots_http_{response.status}")
        text = response.body.decode("utf-8", errors="replace")
        policy = RobotFileParser()
        policy.parse(text.splitlines())
        return RobotsDecision(policy, ai_input=content_signals(text).get("ai-input") != "no")

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
