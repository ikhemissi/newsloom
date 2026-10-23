import time

import pytest
from newsloom_ingestion.articles import RecoveryDeferred, extract, recover
from newsloom_ingestion.job import process_items
from newsloom_ingestion.models import Document, IngestionFailure, Limits, source_counts
from newsloom_ingestion.parsing import parse
from test_ingestion_feeds import NOW, FakeClient, document, rss, source


def test_article_metadata_and_body_selection_and_bounds() -> None:
    body = b"""<html><head>
    <meta property="og:title" content="OG title">
    <meta property="og:description" content="OG text">
    <script type="application/ld+json">{"@graph":[
      {"@type":"Organization","headline":"Wrong","description":"Wrong"},
      {"@type":["Thing","BlogPosting"],"headline":"Research R&D","articleBody":"Article text"}
    ]}</script></head><body><nav>Navigation</nav>
    <article><h1>Heading</h1><div class="article-content">Visible &amp; text
    <script>NOT ARTICLE</script><style>NOT ARTICLE</style>
    <aside>NOT ARTICLE</aside></div></article><footer>Footer</footer></body></html>"""
    fields = extract(body, Limits())
    assert fields.title == "Research R&D" and fields.text == "Article text"
    assert fields.heading == "Heading" and fields.body == "Heading Visible & text"
    assert not fields.invalid_metadata
    assert (
        len(
            extract(
                b"<article>" + "é".encode() * 100 + b"</article>", Limits(text_bytes=3)
            ).body.encode()
        )
        == 2
    )


def test_invalid_or_unrelated_metadata_still_allows_visible_body() -> None:
    fields = extract(
        b"""<script type="application/ld+json">{invalid</script>
    <script type="application/ld+json">{"@type":"Organization","headline":"Wrong"}</script>
    <main><h1>Real title</h1><p>Real text</p></main>""",
        Limits(),
    )
    assert fields.title == fields.text == ""
    assert fields.invalid_metadata and fields.heading == "Real title"
    assert fields.body == "Real title Real text"


@pytest.mark.parametrize(
    ("html", "path"),
    [
        (
            b"""<meta property="og:title" content="Recovered title">
          <meta property="og:description" content="Recovered text">""",
            "article_metadata",
        ),
        (
            b"""<script type="application/ld+json">{"@type":"Article","headline":"Recovered title"}
          </script><div class="article-content">Recovered text</div>""",
            "article_body",
        ),
        (b"<main><h1>Recovered title</h1>Recovered text</main>", "article_body"),
    ],
)
async def test_one_response_supplies_missing_fields(html: bytes, path: str) -> None:
    candidate = parse(
        source(),
        rss().replace(b"News title", b"").replace(b"News text", b""),
        str(source().url),
        NOW,
    ).candidates[0]
    client = FakeClient([document(404), document(body=html)])
    result, selected = await recover(candidate, client, time.monotonic() + 60, "fixture")
    assert selected == path and result.title == "Recovered title" and result.text
    assert result.entry().url == candidate.url
    assert client.urls == ["https://example.com/robots.txt", candidate.url]


async def test_preserves_feed_fields_and_never_follows_article_links() -> None:
    candidate = parse(source(), rss(""), str(source().url), NOW).candidates[0]
    html = b"""<meta property="og:title" content="Do not overwrite">
    <meta property="og:description" content="Recovered text">
    <link rel="canonical" href="https://127.0.0.1/">
    <script type="application/ld+json">{"@context":"https://127.0.0.1/"}</script>
    <img src="https://127.0.0.1/"><script src="https://127.0.0.1/"></script>"""
    client = FakeClient([document(404), document(body=html)])
    result, path = await recover(candidate, client, time.monotonic() + 60, "fixture")
    assert result.title == candidate.title and result.text == "Recovered text"
    assert path == "article_metadata" and len(client.urls) == 2


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_article_redirects_are_not_followed(status: int) -> None:
    client = FakeClient([document(404), document(status, location="https://127.0.0.1/")])
    with pytest.raises(IngestionFailure, match=f"article_http_{status}"):
        await client.article("https://example.com/article", time.monotonic() + 60)
    assert client.urls == ["https://example.com/robots.txt", "https://example.com/article"]


async def test_article_robots_denial_and_nonpublic_destination() -> None:
    client = FakeClient([document(body=b"User-agent: *\nDisallow: /article")])
    with pytest.raises(IngestionFailure, match="robots_denied"):
        await client.article("https://example.com/article", time.monotonic() + 60)
    assert len(client.urls) == 1
    with pytest.raises(IngestionFailure, match="nonpublic_address"):
        await client.article("https://127.0.0.1/", time.monotonic() + 60)
    assert len(client.urls) == 1


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
async def test_retryable_article_status_is_not_malformed(status: int) -> None:
    candidate = parse(source(), rss(""), str(source().url), NOW).candidates[0]
    client = FakeClient([document(404), document(status)])
    with pytest.raises(RecoveryDeferred):
        await recover(candidate, client, time.monotonic() + 60, "fixture")
    assert len(client.urls) == 2


async def test_sufficient_feed_fields_do_not_request_article() -> None:
    client = FakeClient([])
    counts = source_counts()
    await process_items(
        source(), document(body=rss()), client, counts, time.monotonic() + 60, "fixture"
    )
    assert client.urls == []
    assert counts["entries"] == counts["feed_item"] == 1


async def test_recovery_failure_retains_title_only_entry_and_logs_no_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient([document(404), document(302, location="NEWSLOOM_CONTENT_CANARY")])
    counts = source_counts()
    await process_items(
        source(), document(body=rss("")), client, counts, time.monotonic() + 60, "fixture"
    )
    assert counts["entries"] == counts["feed_item"] == counts["recovery_failed"] == 1
    assert counts["malformed_rejected"] == 0
    assert "CANARY" not in capsys.readouterr().out


async def test_missing_title_transient_recovery_and_permanent_failure() -> None:
    body = rss().replace(b"News title", b"")
    for status, counter in [(503, "recovery_deferred"), (404, "malformed_rejected")]:
        client = FakeClient([document(404), document(status)])
        counts = source_counts()
        await process_items(
            source(), document(body=body), client, counts, time.monotonic() + 60, "fixture"
        )
        assert counts[counter] == 1 and counts["staged"] == 0


async def test_article_deadline_is_shared_and_explicit() -> None:
    candidate = parse(source(), rss(""), str(source().url), NOW).candidates[0]
    client = FakeClient([])
    with pytest.raises(RecoveryDeferred):
        await recover(candidate, client, time.monotonic() - 1, "fixture")
    assert not client.urls


async def test_filtered_items_skip_recovery() -> None:
    client = FakeClient([])
    counts = source_counts()
    config = source().model_copy(update={"include_categories": ("not-present",)})
    await process_items(
        config, document(body=rss("")), client, counts, time.monotonic() + 60, "fixture"
    )
    assert counts["filtered"] == 1 and counts["recovery_attempted"] == 0
    assert not client.urls


async def test_article_uses_existing_byte_limit_and_rejects_non_html() -> None:
    class Client(FakeClient):
        async def request(self, url: str, headers: dict[str, str], limit: int) -> Document:
            assert limit == (17 if url.endswith("robots.txt") else 23)
            return await super().request(url, headers, limit)

    client = Client(
        [
            document(404),
            Document(
                200,
                "https://example.com/article",
                b"binary",
                {"content-type": "application/octet-stream"},
            ),
        ],
        Limits(body_bytes=23, robots_bytes=17),
    )
    with pytest.raises(IngestionFailure, match="article_content_type"):
        await client.article("https://example.com/article", time.monotonic() + 60)
