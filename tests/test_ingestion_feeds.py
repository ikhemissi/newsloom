import asyncio
import gzip
import socket
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from newsloom_core.feeds import FeedSource
from newsloom_ingestion.models import DEFAULT_LIMITS, Document, IngestionFailure, Limits
from newsloom_ingestion.parsing import canonical_url, included, parse, plain
from newsloom_ingestion.retrieval import (
    PublicClient,
    PublicResolver,
    check_url,
    public_address,
    retry_delay,
)

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def source(kind: str = "rss") -> FeedSource:
    return FeedSource.model_validate(
        {"id": "example-feed", "title": "Example", "url": "https://example.com/feed", "kind": kind}
    )


def rss(text: str = "News text", *, category: str = "AI, Research") -> bytes:
    return (
        '<rss version="2.0"><channel><item><guid>entry-one</guid><title>News title</title>'
        f"<link>/article#part</link><description>{text}</description>"
        f"<category>{category}</category><pubDate>Thu, 22 Oct 2026 09:00:00 GMT</pubDate>"
        "</item></channel></rss>"
    ).encode()


def test_rss_metadata_and_category_matching() -> None:
    config = source().model_copy(update={"include_categories": ("ai",)})
    parsed = parse(config, rss(), str(config.url), NOW)
    assert parsed.found == 1 and not parsed.malformed
    entry = parsed.candidates[0]
    assert entry.url == "https://example.com/article#part"
    assert entry.guid == "entry-one"
    assert entry.published_at == datetime(2026, 10, 22, 9, tzinfo=UTC)
    assert entry.date_origin == "published"
    assert included(config, entry)
    assert not included(config.model_copy(update={"include_categories": ("artificial",)}), entry)


def test_atom_namespace_base_xhtml_and_date_fallback() -> None:
    body = b"""<feed xmlns="http://www.w3.org/2005/Atom" xml:base="/base/">
      <entry xml:base="nested/"><id>tag:example</id><title>Title</title>
      <link href="item"/><updated>2026-10-22T09:00:00Z</updated>
      <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">
      <p>First</p><p>Second</p></div></content></entry></feed>"""
    entries = parse(source("atom"), body, "https://example.com/feed", NOW).candidates
    assert entries[0].url == "https://example.com/base/nested/item"
    assert entries[0].text == "First Second"
    assert entries[0].date_origin == "updated"


@pytest.mark.parametrize(
    "body",
    [
        b'<!DOCTYPE rss [<!ENTITY e "expanded">]><rss>&e;</rss>',
        b'<!DOCTYPE rss SYSTEM "https://example.com/dtd"><rss/>',
        "<!DOCTYPE rss><rss/>".encode("utf-16"),
        b"<rss><unclosed>",
        b"<feed/>",
    ],
)
def test_hostile_or_wrong_documents_fail(body: bytes) -> None:
    with pytest.raises(IngestionFailure):
        parse(source(), body, "https://example.com/feed", NOW)


def test_large_fulltext_and_exact_body_entry_text_limits() -> None:
    body = rss("synthetic full text " * 225000)
    assert len(body) >= 4_000_000
    entries = parse(source(), body, "https://example.com/feed", NOW).candidates
    assert len(entries[0].text.encode()) == 32768
    parse(source(), body, "https://example.com/feed", NOW, Limits(body_bytes=len(body)))
    with pytest.raises(IngestionFailure, match="body_limit"):
        parse(source(), body, "https://example.com/feed", NOW, Limits(body_bytes=len(body) - 1))
    assert len(plain("é" * 100, 3).encode()) == 2
    two = rss().replace(
        b"</channel>", rss().split(b"<channel>")[1].split(b"</channel>")[0] + b"</channel>"
    )
    parse(source(), two, "https://example.com/feed", NOW, Limits(entries=2))
    with pytest.raises(IngestionFailure, match="entry_limit"):
        parse(source(), two, "https://example.com/feed", NOW, Limits(entries=1))


def test_empty_feed_and_html_and_canonicalization() -> None:
    parsed = parse(source(), b"<rss><channel/></rss>", "https://example.com/feed", NOW)
    assert not parsed.candidates and not parsed.malformed and parsed.found == 0
    assert plain("<script>hidden</script><p>Hello &amp; world</p>", 100) == "Hello & world"
    assert (
        canonical_url("https://EXAMPLE.com:443/item?q=1#x", "") == "https://example.com/item?q=1#x"
    )
    with pytest.raises(IngestionFailure):
        canonical_url("javascript:alert(1)", "https://example.com")


def test_distinct_anchored_atom_releases_preserve_identity() -> None:
    body = b"""<feed xmlns="http://www.w3.org/2005/Atom">
    <entry><id>one</id><title>Release one</title><link href="/releases#one"/></entry>
    <entry><id>two</id><title>Release two</title><link href="/releases#two"/></entry>
    </feed>"""
    parsed = parse(source("atom"), body, "https://example.com/feed", NOW)
    assert parsed.found == 2
    assert {entry.url for entry in parsed.candidates} == {
        "https://example.com/releases#one",
        "https://example.com/releases#two",
    }


def test_normalizer_flushes_final_ampersand_in_title_and_body() -> None:
    assert plain("Research R&D", 2048) == "Research R&D"
    parsed = parse(
        source(),
        rss("Research R&amp;D").replace(b"News title", b"Research R&amp;D"),
        str(source().url),
        NOW,
    )
    assert parsed.candidates[0].title == parsed.candidates[0].text == "Research R&D"


def test_usable_feed_summary_precedes_article_recovery() -> None:
    body = rss("Summary").replace(
        b"<description>", b"<content>&lt;p&gt;&lt;/p&gt;</content><description>"
    )
    assert parse(source(), body, str(source().url), NOW).candidates[0].text == "Summary"


@pytest.mark.parametrize("kind", ["rss", "atom"])
def test_malformed_items_do_not_discard_siblings(kind: str) -> None:
    if kind == "rss":
        body = b"""<rss><channel>
        <item><title>First</title><link>/first</link></item>
        <item><title>Bad date</title><link>/bad</link><pubDate>invalid</pubDate></item>
        <item><title>Bad port</title><link>https://example.com:bad/</link></item>
        <item><title>Missing link</title></item>
        <item><title>Last</title><link>/last</link></item>
        </channel></rss>"""
    else:
        body = b"""<feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>First</title><link href="/first"/></entry>
        <entry><title>Bad date</title><link href="/bad"/><updated>invalid</updated></entry>
        <entry><title>Bad port</title><link href="https://example.com:bad/"/></entry>
        <entry><title>Missing link</title></entry>
        <entry><title>Last</title><link href="/last"/></entry></feed>"""
    parsed = parse(source(kind), body, str(source(kind).url), NOW)
    assert parsed.found == 5 and len(parsed.malformed) == 3
    assert [entry.title for entry in parsed.candidates] == ["First", "Last"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://127.0.0.1",
        "https://169.254.169.254",
        "https://[::1]",
        "https://[::ffff:127.0.0.1]",
        "https://example.com:444",
        "https://user:password@example.com",
    ],
)
def test_unsafe_urls_are_rejected(url: str) -> None:
    with pytest.raises(IngestionFailure):
        check_url(url)


def test_public_addresses_and_retry_delays() -> None:
    assert public_address("1.1.1.1")
    assert not public_address("224.0.0.1")
    assert retry_delay(None, 1) == 2
    assert retry_delay("3", 0) == 3
    for invalid in ("nan", "inf", "-1", "not-a-date"):
        with pytest.raises(IngestionFailure):
            retry_delay(invalid, 0)


async def test_dns_rejects_a_mixed_public_private_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    async def answers(
        *args: object, **kwargs: object
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(2, 1, 6, "", ("1.1.1.1", 443)), (2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
    with pytest.raises(IngestionFailure, match="nonpublic_dns"):
        await PublicResolver().resolve("example.com", 443, socket.AF_INET)


class FakeClient(PublicClient):
    def __init__(self, responses: list[Document], limits: Limits = DEFAULT_LIMITS) -> None:
        super().__init__(limits)
        self.responses = responses
        self.urls: list[str] = []

    async def request(self, url: str, headers: dict[str, str], limit: int) -> Document:
        self.urls.append(url)
        return self.responses.pop(0)


def document(status: int = 200, body: bytes = b"", **headers: str) -> Document:
    return Document(status, "https://example.com/feed", body, headers)


async def test_robots_denial_and_missing_policy() -> None:
    client = FakeClient([document(body=b"User-agent: *\nDisallow: /feed")])
    with pytest.raises(IngestionFailure, match="robots_denied"):
        await client.fetch("https://example.com/feed", {}, time.monotonic() + 60)
    assert len(client.urls) == 1
    client = FakeClient([document(404), document(body=b"body")])
    assert (
        await client.fetch("https://example.com/feed", {}, time.monotonic() + 60)
    ).body == b"body"


async def test_redirect_revalidation_and_exact_redirect_limit() -> None:
    client = FakeClient([document(404), document(302, location="https://127.0.0.1")])
    with pytest.raises(IngestionFailure, match="nonpublic_address"):
        await client.fetch("https://example.com/feed", {}, time.monotonic() + 60)
    assert len(client.urls) == 2
    client = FakeClient(
        [document(302, location="/two"), document(302, location="/three"), document()],
        Limits(redirects=2),
    )
    assert (
        await client.fetch("https://example.com/robots.txt", {}, time.monotonic() + 60, robots=True)
    ).status == 200
    client = FakeClient(
        [document(302, location="/two"), document(302, location="/three")], Limits(redirects=1)
    )
    with pytest.raises(IngestionFailure, match="redirect_limit"):
        await client.fetch("https://example.com/robots.txt", {}, time.monotonic() + 60, robots=True)


async def test_retry_after_and_expired_deadline_do_not_sleep() -> None:
    client = FakeClient([Document(429, "https://example.com/feed", b"", {"retry-after": "300"})])
    with pytest.raises(IngestionFailure, match="retry_deferred"):
        await client.fetch("https://example.com/robots.txt", {}, time.monotonic() + 1, robots=True)
    client = FakeClient([])
    with pytest.raises(IngestionFailure, match="feed_deadline"):
        await client.fetch("https://example.com/robots.txt", {}, time.monotonic() - 1, robots=True)


@pytest.mark.parametrize(
    "size,limit,encoding",
    [
        (1024, 1024, "gzip"),
        (1025, 1024, "gzip"),
        (1024, 1024, "identity"),
        (1025, 1024, "identity"),
    ],
)
async def test_actual_stream_reader_enforces_expanded_and_wire_limits(
    size: int, limit: int, encoding: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aiohttp

    body = b"x" * size
    wire = gzip.compress(body) if encoding == "gzip" else body

    class Content:
        async def iter_chunked(self, size: int) -> AsyncIterator[bytes]:
            for offset in range(0, len(wire), 17):
                yield wire[offset : offset + 17]

    class Response:
        def __init__(self) -> None:
            self.headers = {"Content-Encoding": encoding}

        status = 200
        content = Content()

        async def __aenter__(self) -> Response:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    class Session:
        def __init__(self, **kwargs: object) -> None:
            self.connector = kwargs["connector"]
            assert kwargs["auto_decompress"] is False
            assert kwargs["trust_env"] is False
            timeout = kwargs["timeout"]
            assert isinstance(timeout, aiohttp.ClientTimeout)
            assert timeout.total == 30 and timeout.connect == timeout.sock_connect == 5

        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *args: object) -> None:
            if isinstance(self.connector, aiohttp.TCPConnector):
                await self.connector.close()

        def get(self, *args: object, **kwargs: object) -> Response:
            assert kwargs["allow_redirects"] is False
            assert kwargs["ssl"] is True
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", Session)
    if size > limit:
        with pytest.raises(IngestionFailure, match="body_limit"):
            await PublicClient().request("https://example.com/feed", {}, limit)
    else:
        assert (await PublicClient().request("https://example.com/feed", {}, limit)).body == body


async def test_public_dns_results_pin_numeric_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    async def answers(
        *args: object, **kwargs: object
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(2, 1, 6, "", ("1.1.1.1", 443)), (2, 1, 6, "", ("8.8.8.8", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
    results = await PublicResolver().resolve("example.com", 443)
    assert {result["host"] for result in results} == {"1.1.1.1", "8.8.8.8"}
    assert all(result["hostname"] == "example.com" for result in results)
