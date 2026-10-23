"""RSS/Atom normalization without external entity or article-page retrieval."""

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Never
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET
from xml.parsers import expat

from newsloom_core.feeds import FeedSource

from newsloom_ingestion.models import DEFAULT_LIMITS, Entry, IngestionFailure, Limits

XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.hidden += 1
        elif not self.hidden:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        elif not self.hidden:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def plain(value: str, limit: int) -> str:
    parser = PlainText()
    parser.feed(value)
    return (
        re.sub(r"\s+", " ", "".join(parser.parts))
        .strip()
        .encode()[:limit]
        .decode("utf-8", errors="ignore")
    )


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if local_name(child) == name]


def value(element: ET.Element, *names: str) -> str:
    for name in names:
        for child in children(element, name):
            text = " ".join(child.itertext()).strip()
            if text:
                return text
    return ""


def canonical_url(value: str, base: str) -> str:
    parts = urlsplit(urljoin(base, value))
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise IngestionFailure("invalid_entry_url")
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    if port is not None and (parts.scheme, port) not in (("http", 80), ("https", 443)):
        host += f":{port}"
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, parts.fragment))


def timestamp(text: str) -> datetime:
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(text)
        except ValueError, TypeError, OverflowError:
            raise IngestionFailure("invalid_entry_date") from None
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def forbid_declaration(*args: object) -> Never:
    raise IngestionFailure("xml_declaration_forbidden")


def parse(
    source: FeedSource, body: bytes, url: str, fetched_at: datetime, limits: Limits = DEFAULT_LIMITS
) -> tuple[tuple[Entry, ...], int]:
    if len(body) > limits.body_bytes:
        raise IngestionFailure("body_limit")
    try:
        validator = expat.ParserCreate()
        validator.StartDoctypeDeclHandler = forbid_declaration
        validator.EntityDeclHandler = forbid_declaration
        validator.ExternalEntityRefHandler = forbid_declaration
        validator.Parse(body, True)
        root = ET.fromstring(body)
    except expat.ExpatError, ET.ParseError:
        raise IngestionFailure("invalid_xml") from None
    expected = "feed" if source.kind == "atom" else "rss"
    if local_name(root) != expected:
        raise IngestionFailure("feed_kind_mismatch")
    base = urljoin(url, root.get(XML_BASE, ""))
    container = root if source.kind == "atom" else next(iter(children(root, "channel")), root)
    base = urljoin(base, container.get(XML_BASE, ""))
    nodes = children(container, "entry" if source.kind == "atom" else "item")
    if len(nodes) > limits.entries:
        raise IngestionFailure("entry_limit")
    entries: list[Entry] = []
    for node in nodes:
        entry_base = urljoin(base, node.get(XML_BASE, ""))
        links = children(node, "link")
        link = next(
            (
                urljoin(urljoin(entry_base, item.get(XML_BASE, "")), item.get("href", ""))
                for item in links
                if item.get("href") and item.get("rel", "alternate") == "alternate"
            ),
            value(node, "link"),
        )
        guid = value(node, "id", "guid") or None
        if not link:
            link = guid or ""
        if not link:
            raise IngestionFailure("missing_entry_url")
        published = value(node, "published", "pubDate", "date")
        updated = value(node, "updated")
        categories = tuple(
            term.strip()
            for item in children(node, "category")
            for term in (item.get("term") or "".join(item.itertext())).split(",")
            if term.strip()
        )
        title = plain(value(node, "title"), 2048)
        if not title:
            raise IngestionFailure("missing_entry_title")
        entries.append(
            Entry(
                source=source.id,
                guid=guid,
                url=canonical_url(link, entry_base),
                title=title,
                text=plain(
                    value(node, "encoded", "content", "description", "summary"), limits.text_bytes
                ),
                published_at=timestamp(published or updated)
                if published or updated
                else fetched_at,
                date_origin="published" if published else "updated" if updated else "retrieved",
                author=plain(value(node, "author", "creator"), 2048),
                categories=categories,
            )
        )
    return tuple(entries), len(nodes)


def included(source: FeedSource, entry: Entry) -> bool:
    if source.include_categories is None:
        return True
    allowed = {term.strip().casefold() for term in source.include_categories}
    return any(term.casefold() in allowed for term in entry.categories)
