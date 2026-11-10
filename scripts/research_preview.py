"""Local research-conversation preview over the recorded week; never writes to Azure.

Runs a three-turn conversation through the production research controller and model,
with a local reader over `.cache/announcement-preview/` (keyword search stands in for
vector search). Writes answers, follow-ups and token usage to `.cache/research-preview/`.

    bash scripts/research-preview.sh            # live model calls
    bash scripts/research-preview.sh --replay   # rebuild the review, no model calls
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from newsloom_agent.auth import Authorization, Caller
from newsloom_agent.delegation import ResearchToolResult
from newsloom_agent.generation import GenerationConfig
from newsloom_agent.research import ResearchConnection, ResearchController, ResearchResult
from newsloom_agent.research_generation import FoundryResearchGenerator, ResearchStats
from newsloom_agent.research_models import (
    DetailCall,
    ItemResult,
    NewsDetail,
    NewsResults,
    RecentCall,
    ResearchRequest,
    SearchCall,
    SearchResults,
    SourceInfo,
    SourcesCall,
    SourcesResult,
    ToolCall,
)
from newsloom_core.categories import load_categories
from newsloom_core.entries import Entry

SOURCE = Path(".cache/announcement-preview")
CALLS: list[dict[str, object]] = []
OUTPUT = Path(".cache/research-preview")
QUESTIONS = (
    "What did Microsoft announce for Foundry agents recently?",
    "And what about AWS?",
    "Which of these would an AI solution architect need to act on first?",
)


def load() -> dict[UUID, NewsDetail]:
    entries = {
        entry.url: entry
        for entry in (
            Entry.model_validate_json(line)
            for line in (SOURCE / "entries.jsonl").read_text().splitlines()
        )
    }
    known = {category.id for category in load_categories()}
    items: dict[UUID, NewsDetail] = {}
    for url, result in json.loads((SOURCE / "results.json").read_text()).items():
        raw, entry = result.get("raw"), entries.get(url)
        if not raw or entry is None or raw.get("category") not in known:
            continue
        item = NewsDetail.model_validate(
            {
                "id": uuid5(UUID(int=0), url),
                "title": entry.title,
                "summary": " ".join(raw["summary_sentences"]),
                "source": entry.source,
                "category": raw["category"],
                "tags": raw["tags"],
                "published_at": entry.published_at,
                "url": url,
                "author": entry.author,
                "date_origin": entry.date_origin,
                "publisher_categories": list(entry.categories),
            }
        )
        items[item.id] = item
    return items


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.casefold()))


@dataclass(repr=False)
class LocalConnection:
    authorization: Authorization
    items: dict[UUID, NewsDetail]

    def metadata(self, item: NewsDetail) -> dict[str, object]:
        return item.model_dump(
            mode="json", exclude={"author", "date_origin", "publisher_categories"}
        )

    async def call(self, call: ToolCall) -> ResearchToolResult:
        CALLS.append(call.model_dump(mode="json", by_alias=True, exclude_none=True))
        newest = sorted(self.items.values(), key=lambda item: item.published_at, reverse=True)
        if isinstance(call, DetailCall):
            item = self.items.get(call.arguments.id)
            return ItemResult(found=item is not None, item=item)
        if isinstance(call, RecentCall):
            since = call.arguments.since
            chosen = [i for i in newest if since is None or i.published_at >= since]
            return NewsResults.model_validate(
                {"items": [self.metadata(i) for i in chosen[: call.arguments.limit]]}
            )
        if isinstance(call, SearchCall):
            query, args = words(call.arguments.query or ""), call.arguments
            scored = [
                (len(query & words(f"{i.title} {i.summary} {' '.join(i.tags)}")), i)
                for i in newest
                if (args.source is None or i.source == args.source)
                and (args.category is None or i.category == args.category)
                and set(args.tags) <= set(i.tags)
                and (args.from_ is None or i.published_at >= args.from_)
                and (args.to is None or i.published_at < args.to)
            ]
            ranked = [i for score, i in sorted(scored, key=lambda p: -p[0]) if score or not query]
            return SearchResults.model_validate(
                {"items": [{**self.metadata(i), "similarity": None} for i in ranked[: args.limit]]}
            )
        if isinstance(call, SourcesCall):
            by_source: dict[str, set[str]] = {}
            for item in self.items.values():
                by_source.setdefault(item.source, set()).add(item.category)
            return SourcesResult(
                sources=tuple(
                    SourceInfo.model_validate({"id": s, "categories": sorted(c)})
                    for s, c in sorted(by_source.items())
                ),
                categories=(),
            )
        raise ValueError("unsupported_call")


@dataclass(repr=False)
class LocalReader:
    items: dict[UUID, NewsDetail]

    @asynccontextmanager
    async def research(
        self, authorization: Authorization, selected_ids: tuple[UUID, ...] | None = None
    ) -> AsyncIterator[ResearchConnection]:
        yield LocalConnection(authorization, self.items)


async def converse(items: dict[UUID, NewsDetail]) -> list[dict[str, object]]:
    from azure.identity.aio import AzureCliCredential

    config = GenerationConfig(
        endpoint=os.environ["MODEL_ENDPOINT"], deployment=os.environ["ENRICHMENT_DEPLOYMENT"]
    )
    turns: list[dict[str, object]] = []
    async with AzureCliCredential() as credential:
        controller = ResearchController(
            LocalReader(items), FoundryResearchGenerator(config, credential)
        )
        for question in QUESTIONS:
            history = [
                {"question": t["question"], "answer": t["text"], "cited_item_ids": t["cited"]}
                for t in turns[-3:]
                if t.get("text")
            ]
            request = ResearchRequest.model_validate(
                {"operation": "research", "question": question, "history": history}
            )
            caller = Caller(uuid4(), uuid4(), uuid4(), "preview", int(time.time()) + 600, "local")
            stats = ResearchStats()
            record: dict[str, object] = {"question": question, "history_turns": len(history)}
            CALLS.clear()
            try:
                async for update in controller.run(
                    request, Authorization(caller, time.monotonic() + 180), stats
                ):
                    if isinstance(update, ResearchResult):
                        record["text"] = update.text
                        record["follow_ups"] = list(update.answer.follow_ups)
                        record["cited"] = sorted(
                            {str(i) for c in update.answer.claims for i in c.evidence_ids}
                        )
            except Exception as error:
                record["failure"] = str(error) or type(error).__name__
            record |= {
                "calls": list(CALLS),
                "tool_calls": stats.tool_calls,
                "model_calls": stats.calls,
                "input_tokens": stats.input_tokens,
                "output_tokens": stats.output_tokens,
            }
            turns.append(record)
            print(json.dumps({k: v for k, v in record.items() if k != "text"}), file=sys.stderr)
    return turns


def review(turns: list[dict[str, object]]) -> str:
    lines = ["# Research conversation preview", ""]
    for number, turn in enumerate(turns, 1):
        lines += [
            f"## Turn {number}: {turn['question']}",
            "",
            f"History turns sent: {turn['history_turns']}; tool calls {turn['tool_calls']}, "
            f"model calls {turn['model_calls']}, tokens in/out "
            f"{turn['input_tokens']}/{turn['output_tokens']}.",
            "",
            str(turn.get("text") or f"Failed: {turn.get('failure')}"),
            "",
            "Suggested follow-ups: " + ("; ".join(turn.get("follow_ups") or []) or "none"),  # type: ignore[arg-type]
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = OUTPUT / "results.json"
    if args.replay:
        turns = json.loads(results.read_text())
    else:
        turns = asyncio.run(converse(load()))
        results.write_text(json.dumps(turns, indent=2))
    (OUTPUT / "review.md").write_text(review(turns))
    print(f"review: {OUTPUT / 'review.md'}")


if __name__ == "__main__":
    main()
