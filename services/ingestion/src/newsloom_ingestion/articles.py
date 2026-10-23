"""Missing-field recovery from one bounded article response, never a crawler."""

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from newsloom_ingestion.models import Candidate, IngestionFailure, Limits
from newsloom_ingestion.parsing import plain
from newsloom_ingestion.retrieval import RETRYABLE, PublicClient
from newsloom_ingestion.telemetry import event

AcquisitionPath = Literal["feed_item", "article_metadata", "article_body"]
ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "TechArticle", "Report"}
CONTENT_CLASSES = {"article-content", "post-content", "entry-content", "gh-content", "post-body"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
HIDDEN = {"script", "style", "nav", "footer", "aside", "noscript", "svg", "form", "template"}


class RecoveryDeferred(IngestionFailure):
    """The feed body must remain retrievable for a later recovery attempt."""


class ArticleHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []
        self.meta: dict[str, str] = {}
        self.blocks: list[str] = []
        self.script: list[str] | None = None
        self.heading: list[str] = []
        self.content: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta":
            key = (attributes.get("property") or "").lower()
            if key in ("og:title", "og:description") and attributes.get("content"):
                self.meta.setdefault(key, attributes["content"] or "")
        if tag == "script" and (attributes.get("type") or "").lower() == "application/ld+json":
            self.script = []
        hidden = (self.stack[-1][1] if self.stack else False) or tag in HIDDEN
        region = (
            (self.stack[-1][2] if self.stack else False)
            or tag in ("article", "main")
            or attributes.get("itemprop") == "articleBody"
            or bool(set((attributes.get("class") or "").split()) & CONTENT_CLASSES)
        )
        if not hidden and region:
            self.content.append(" ")
        if tag not in VOID:
            self.stack.append((tag, hidden, region))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.script is not None:
            self.blocks.append("".join(self.script))
            self.script = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        self.content.append(" ")

    def handle_data(self, data: str) -> None:
        if self.script is not None:
            self.script.append(data)
        if self.stack and not self.stack[-1][1]:
            if self.stack[-1][2]:
                self.content.append(data)
            if any(tag == "h1" for tag, _, _ in self.stack):
                self.heading.append(data)


@dataclass(frozen=True)
class ArticleFields:
    title: str
    text: str
    heading: str
    body: str
    invalid_metadata: bool


def extract(body: bytes, limits: Limits) -> ArticleFields:
    parser = ArticleHTML()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    title = text = ""
    invalid = False
    for block in parser.blocks:
        try:
            root: object = json.loads(block)
        except json.JSONDecodeError, RecursionError:
            invalid = True
            continue
        nodes = [root]
        while nodes:
            node = nodes.pop()
            if isinstance(node, list):
                nodes.extend(reversed(node))
            elif isinstance(node, dict):
                kind = node.get("@type")
                kinds = kind if isinstance(kind, list) else [kind]
                if any(
                    isinstance(item, str) and item.rsplit("/", 1)[-1] in ARTICLE_TYPES
                    for item in kinds
                ):
                    headline = node.get("headline")
                    if not title and isinstance(headline, str):
                        title = plain(headline, 2048)
                    for key in ("articleBody", "description"):
                        value = node.get(key)
                        if not text and isinstance(value, str):
                            text = plain(value, limits.text_bytes)
                graph = node.get("@graph")
                if isinstance(graph, list):
                    nodes.extend(reversed(graph))
    return ArticleFields(
        title or plain(parser.meta.get("og:title", ""), 2048),
        text or plain(parser.meta.get("og:description", ""), limits.text_bytes),
        plain(" ".join(parser.heading), 2048),
        plain(" ".join(parser.content), limits.text_bytes),
        invalid,
    )


async def recover(
    candidate: Candidate, client: PublicClient, deadline: float, correlation: str
) -> tuple[Candidate, AcquisitionPath]:
    try:
        document = await client.article(candidate.url, deadline)
    except TimeoutError:
        raise RecoveryDeferred("article_timeout") from None
    except IngestionFailure as error:
        category = str(error)
        transient = {"retrieval_failed", "retry_deferred", "feed_deadline", "article_unavailable"}
        transient.update(
            f"{prefix}_{status}"
            for prefix in ("http", "robots_http", "article_http")
            for status in RETRYABLE
        )
        if category in transient:
            raise RecoveryDeferred(category) from None
        raise
    fields = extract(document.body, client.limits)
    if fields.invalid_metadata:
        event(
            "article",
            correlation,
            source=candidate.source,
            outcome="warning",
            category="invalid_article_metadata",
        )
    title = candidate.title or fields.title
    text = candidate.text or fields.text
    path: AcquisitionPath = "article_metadata"
    if not title and fields.heading:
        title = fields.heading
        path = "article_body"
    if not text and fields.body:
        text = fields.body
        path = "article_body"
    if title == candidate.title and text == candidate.text:
        raise IngestionFailure("article_fields_missing")
    return candidate.model_copy(update={"title": title, "text": text}), path
