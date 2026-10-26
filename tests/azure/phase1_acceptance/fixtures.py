"""Authored feed transport only; scanner, parser and durable paths remain real."""

from datetime import UTC
from typing import Literal
from xml.etree.ElementTree import Element, SubElement, tostring

from newsloom_core.feeds import FeedSource
from newsloom_core.phase1_contracts import AcceptanceFailure, Fixtures, load_fixtures
from newsloom_ingestion.models import Document, Limits
from newsloom_ingestion.retrieval import PublicClient
from pydantic import HttpUrl

ATOM = "http://www.w3.org/2005/Atom"
KINDS: tuple[Literal["rss", "atom"], ...] = ("rss", "atom")


def sources() -> tuple[FeedSource, ...]:
    return tuple(
        FeedSource(
            id="acceptance-" + kind,
            title="Authored acceptance " + kind,
            kind=kind,
            url=HttpUrl("https://example.com/newsloom/phase1/" + kind),
        )
        for kind in KINDS
    )


def documents(fixtures: Fixtures) -> dict[str, bytes]:
    result = {}
    for kind in KINDS:
        root = Element("rss", version="2.0") if kind == "rss" else Element("{" + ATOM + "}feed")
        parent = SubElement(root, "channel") if kind == "rss" else root

        def name(value: str, current: str = kind) -> str:
            return value if current == "rss" else "{" + ATOM + "}" + value

        SubElement(parent, name("title")).text = "Authored acceptance feed"
        if kind == "atom":
            SubElement(parent, name("id")).text = "urn:newsloom:phase1:atom"
            SubElement(parent, name("updated")).text = "2026-01-13T12:00:00Z"
        for case in fixtures.cases:
            if case.kind != kind:
                continue
            entry = SubElement(parent, name("item" if kind == "rss" else "entry"))
            SubElement(entry, name("title")).text = case.title
            SubElement(entry, name("guid" if kind == "rss" else "id")).text = case.id
            timestamp = case.published_at.astimezone(UTC)
            SubElement(entry, name("pubDate" if kind == "rss" else "published")).text = (
                timestamp.strftime("%a, %d %b %Y %H:%M:%S GMT")
                if kind == "rss"
                else timestamp.isoformat()
            )
            if kind == "rss":
                SubElement(entry, "link").text = case.url
                SubElement(entry, "description").text = case.text
                SubElement(entry, "author").text = case.author
            else:
                SubElement(entry, name("link"), href=case.url, rel="alternate")
                SubElement(entry, name("content"), type="text").text = case.text
                SubElement(SubElement(entry, name("author")), name("name")).text = case.author
        result["https://example.com/newsloom/phase1/" + kind] = tostring(root, encoding="utf-8")
    return result


class FixtureClient(PublicClient):
    def __init__(self, limits: Limits) -> None:
        super().__init__(limits)
        self.documents = documents(load_fixtures())

    async def fetch(
        self,
        url: str,
        headers: dict[str, str],
        deadline: float,
        *,
        robots: bool = False,
    ) -> Document:
        if robots or url not in self.documents:
            raise AcceptanceFailure("unexpected_acceptance_network_request")
        return Document(200, url, self.documents[url], {})
