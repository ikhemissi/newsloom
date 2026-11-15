"""Web IQ search with the agent's managed identity; results are untrusted public data."""

from typing import Protocol
from urllib.parse import urlsplit

import httpx
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import AzureError

from newsloom_agent.research_models import MAX_WEB_RESULTS

ENDPOINT = "https://api.microsoft.ai/v3/search/web"
SCOPE = "https://api.microsoft.ai/.default"
MAX_RESPONSE_BYTES = 1024 * 1024


class WebUnavailable(Exception):
    """Web search failed; research continues with stored news only."""


class Found:
    __slots__ = ("snippet", "title", "updated", "url")

    def __init__(self, title: str, url: str, snippet: str, updated: str | None) -> None:
        self.title, self.url, self.snippet, self.updated = title, url, snippet, updated


class WebSearch(Protocol):
    async def search(self, query: str) -> tuple[Found, ...]: ...


def parse(document: object) -> tuple[Found, ...]:
    if not isinstance(document, dict) or not isinstance(document.get("webResults"), list):
        raise WebUnavailable("web_response_invalid")
    found: list[Found] = []
    for row in document["webResults"]:
        if len(found) >= MAX_WEB_RESULTS:
            break
        if not isinstance(row, dict) or row.get("isAdult") is True:
            continue
        title, url, content = row.get("title"), row.get("url"), row.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            continue
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
            continue
        updated = row.get("lastUpdatedAt")
        found.append(
            Found(
                " ".join(title.split())[:200],
                url,
                " ".join(content.split())[:1000] if isinstance(content, str) else "",
                updated[:40] if isinstance(updated, str) and updated else None,
            )
        )
    return tuple(found)


class WebIq:
    def __init__(
        self, client: httpx.AsyncClient, credential: AsyncTokenCredential, timeout: float = 10
    ) -> None:
        self.client, self.credential, self.timeout = client, credential, timeout

    async def search(self, query: str) -> tuple[Found, ...]:
        try:
            token = (await self.credential.get_token(SCOPE)).token
            async with self.client.stream(
                "POST",
                ENDPOINT,
                json={"query": query},
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout,
            ) as response:
                if response.status_code != 200:
                    raise WebUnavailable(f"web_status_{response.status_code}")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise WebUnavailable("web_response_limit")
            return parse(httpx.Response(200, content=bytes(body)).json())
        except (httpx.HTTPError, AzureError, ValueError) as error:
            raise WebUnavailable(f"web_{type(error).__name__}") from None
