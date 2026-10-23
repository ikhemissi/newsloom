import argparse
import json
import logging
import sys
from pathlib import Path

import httpx
import pytest
from newsloom_core.feeds import load_feed_catalogue
from newsloom_ingestion import cli
from newsloom_ingestion.job import select_sources
from newsloom_ingestion.models import IngestionFailure
from newsloom_ingestion.telemetry import SafeHandler


def test_source_selection_is_exact() -> None:
    sources = load_feed_catalogue(Path("config/feeds.json"))
    assert len(select_sources(sources, ["vertex-ai-release-notes"])) == 1
    with pytest.raises(IngestionFailure, match="unknown_source"):
        select_sources(sources, ["unknown"])


async def test_local_smoke_cannot_default_to_all_sources() -> None:
    with pytest.raises(IngestionFailure, match="local_smoke_requires_one_rss_one_atom"):
        await cli.runtime(
            argparse.Namespace(
                catalogue=Path("config/feeds.json"),
                source=[],
                command="fetch",
            ),
            "fixture",
        )


@pytest.mark.parametrize("invalid", [True, False])
def test_cli_and_dependency_failures_exclude_payloads(
    invalid: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fail(args: argparse.Namespace, correlation: str) -> None:
        raise httpx.ReadError("NEWSLOOM_CREDENTIAL_CANARY NEWSLOOM_CONTENT_CANARY")

    monkeypatch.setattr(cli, "runtime", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        ["newsloom-ingestion", "NEWSLOOM_CONTENT_CANARY"]
        if invalid
        else ["newsloom-ingestion", "run"],
    )
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 1
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err
    assert json.loads(output.out)["outcome"] == "failure"
    handler = SafeHandler()
    handler.emit(
        logging.LogRecord(
            "httpx",
            logging.ERROR,
            "",
            1,
            "NEWSLOOM_CONTENT_CANARY %s",
            ("NEWSLOOM_CREDENTIAL_CANARY",),
            None,
        )
    )
    assert "CANARY" not in capsys.readouterr().out


async def test_local_fetch_command_uses_shared_recovery(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from newsloom_core.feeds import FeedSource
    from newsloom_ingestion.models import Document
    from newsloom_ingestion.retrieval import PublicClient
    from test_ingestion_feeds import rss

    feeds = tuple(
        FeedSource.model_validate(
            {"id": kind, "kind": kind, "title": kind, "url": f"https://example.com/{kind}"}
        )
        for kind in ("rss", "atom")
    )
    requests: list[str] = []

    class Client(PublicClient):
        async def fetch(
            self, url: str, headers: dict[str, str], deadline: float, *, robots: bool = False
        ) -> Document:
            if robots:
                return Document(404, url, b"", {})
            body = (
                rss().replace(b"News title", b"")
                if url.endswith("/rss")
                else (
                    b'<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
                    b'<title>Atom</title><link href="/atom-entry"/>'
                    b"<content>Text</content></entry></feed>"
                )
            )
            return Document(200, url, body, {})

        async def request(self, url: str, headers: dict[str, str], limit: int) -> Document:
            requests.append(url)
            return Document(200, url, b'<meta property="og:title" content="Recovered">', {})

    monkeypatch.setattr(cli, "load_feed_catalogue", lambda path: feeds)
    monkeypatch.setattr(cli, "PublicClient", Client)
    await cli.runtime(
        argparse.Namespace(catalogue=Path("unused"), source=[], command="fetch"), "fixture"
    )
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(requests) == 1
    assert [item["counts"]["entries"] for item in events] == [1, 1]
    assert events[0]["counts"]["article_metadata"] == 1
