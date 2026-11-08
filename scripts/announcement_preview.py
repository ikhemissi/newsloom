"""Local announcement-extraction preview over a real recent week; never writes to Azure.

Rebuilds enrichment input the way ingestion does (catalogue feeds, then one article
per item under robots/Content-Signal rules), runs the production extraction with
the developer's Azure CLI identity and writes a private review under the ignored
`.cache/announcement-preview/`. Recorded entries and raw model outputs replay
grounding changes without network or model cost.

    bash scripts/announcement-preview.sh --days 7
    bash scripts/announcement-preview.sh --replay
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from newsloom_core.entries import Entry
from newsloom_core.feeds import load_feed_catalogue
from newsloom_core.model_transport import ModelClient, ModelFailure, TransportLimits
from newsloom_enrichment import providers
from newsloom_enrichment.models import Enrichment, grounded
from newsloom_enrichment.providers import FoundryLlm
from newsloom_ingestion.articles import RecoveryDeferred, acquire
from newsloom_ingestion.models import IngestionFailure
from newsloom_ingestion.parsing import included, parse
from newsloom_ingestion.retrieval import PublicClient
from pydantic import ValidationError

OUTPUT = Path(".cache/announcement-preview")


async def collect(days: int) -> list[Entry]:
    since = datetime.now(UTC) - timedelta(days=days)
    client = PublicClient()
    feeds = asyncio.Semaphore(4)
    entries: list[Entry] = []
    outcomes: Counter[str] = Counter()

    async def one(source: object) -> None:
        async with feeds:
            deadline = time.monotonic() + 120
            try:
                document = await client.fetch(str(source.url), {}, deadline)  # type: ignore[attr-defined]
                parsed = parse(source, document.body, document.url, datetime.now(UTC))  # type: ignore[arg-type]
            except IngestionFailure, TimeoutError, OSError:
                outcomes["feed_failed"] += 1
                return
            for candidate in parsed.candidates:
                if candidate.published_at < since or not included(source, candidate):  # type: ignore[arg-type]
                    continue
                try:
                    candidate = (
                        await acquire(candidate, client, deadline + 120, "preview")
                    ).candidate
                    outcomes["article_acquired"] += 1
                except RecoveryDeferred, IngestionFailure, TimeoutError:
                    outcomes["feed_text_kept"] += 1
                try:
                    entries.append(candidate.entry())
                except ValueError:
                    outcomes["malformed"] += 1

    await asyncio.gather(
        *(one(source) for source in load_feed_catalogue(Path("config/feeds.json")))
    )
    print(json.dumps({"collected": len(entries), **outcomes}), file=sys.stderr)
    return sorted(entries, key=lambda item: item.published_at)


class Diagnosing(Enrichment):
    """Records only failing field locations and error types, never model content."""

    @classmethod
    def model_validate_json(cls, *args: object, **kwargs: object) -> Enrichment:  # type: ignore[override]
        try:
            return Enrichment.model_validate_json(*args, **kwargs)  # type: ignore[arg-type]
        except ValidationError as error:
            failures.extend(
                ".".join(str(part) for part in item["loc"]) + ":" + item["type"]
                for item in error.errors()
            )
            raise


failures: list[str] = []


async def extract(
    entries: list[Entry], endpoint: str, deployment: str
) -> dict[str, dict[str, object]]:
    from azure.identity.aio import AzureCliCredential

    results: dict[str, dict[str, object]] = {}
    calls = asyncio.Semaphore(8)
    async with AzureCliCredential() as credential, httpx.AsyncClient(trust_env=False) as http:
        limits = TransportLimits(request_seconds=120, transport_attempts=2)

        async def one(entry: Entry) -> None:
            async with calls:
                # One client per item so concurrent calls never share usage counters.
                transport = ModelClient(http, credential, endpoint, limits)
                failures.clear()
                try:
                    raw = await FoundryLlm(transport, deployment).extract(
                        entry, time.monotonic() + 240
                    )
                except ModelFailure as error:
                    results[entry.url] = {"error": str(error), "fields": list(failures)}
                    return
                results[entry.url] = {
                    "raw": raw.model_dump(mode="json"),
                    "input_tokens": transport.observations.input_tokens,
                    "output_tokens": transport.observations.output_tokens,
                }
                print(f"extracted {len(results)}/{len(entries)}", file=sys.stderr)

        await asyncio.gather(*(one(entry) for entry in entries))
    return results


def review(
    entries: list[Entry], results: dict[str, dict[str, object]], prices: tuple[Decimal, Decimal]
) -> dict[str, object]:
    kinds: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    drops: Counter[str] = Counter()
    vendors: Counter[str] = Counter()
    products: set[tuple[str, str]] = set()
    tokens = [0, 0]
    errors: Counter[str] = Counter()
    raw_count = kept_count = 0
    lines = ["# Announcement preview", ""]
    for entry in entries:
        result = results.get(entry.url, {})
        if "raw" not in result:
            errors[str(result.get("error", "missing"))] += 1
            continue
        raw = Enrichment.model_validate(result["raw"])
        tokens[0] += int(result["input_tokens"])  # type: ignore[call-overload]
        tokens[1] += int(result["output_tokens"])  # type: ignore[call-overload]
        kept, dropped = grounded(raw.announcements, entry)
        drops.update(dropped)
        raw_count += len(raw.announcements)
        kept_count += len(kept)
        kinds[raw.article_kind.value] += 1
        lines += [
            f"## {entry.title}",
            "",
            f"{entry.source} · {entry.published_at:%Y-%m-%d} · {raw.article_kind.value} · "
            f"{len(entry.text.split())} words · [source]({entry.url})",
            "",
            raw.summary,
            "",
        ]
        for item in kept:
            statuses[item.status.value] += 1
            for mention in item.products:
                vendors[mention.vendor] += 1
                products.add((mention.vendor, mention.product))
            dates = ", ".join(
                f"{label} {value}"
                for label, value in (
                    ("effective", item.effective_date),
                    ("deadline", item.deadline),
                )
                if value
            )
            names = "; ".join(f"{m.product} ({m.vendor})" for m in item.products)
            lines.append(
                f"- **{item.status.value}** {item.statement} _{names}_"
                + (f" [{dates}]" if dates else "")
            )
        dropped_total = sum(dropped.values())
        if dropped_total:
            lines.append(f"- _{dropped_total} unsupported announcement(s) dropped_")
        lines.append("")
    (OUTPUT / "review.md").write_text("\n".join(lines))
    return {
        "items": len(entries),
        "errors": dict(errors),
        "article_kinds": dict(kinds.most_common()),
        "announcements_raw": raw_count,
        "announcements_kept": kept_count,
        "dropped": dict(drops),
        "statuses": dict(statuses.most_common()),
        "distinct_products": len(products),
        "top_vendors": dict(vendors.most_common(10)),
        "input_tokens": tokens[0],
        "output_tokens": tokens[1],
        "estimated_cost_usd": float(
            (tokens[0] * prices[0] + tokens[1] * prices[1]) / Decimal(1_000_000)
        ),
        "review": str(OUTPUT / "review.md"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--replay", action="store_true", help="reuse recorded entries and outputs")
    parser.add_argument(
        "--reuse-entries", action="store_true", help="reuse recorded entries, rerun extraction"
    )
    arguments = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries_path, results_path = OUTPUT / "entries.jsonl", OUTPUT / "results.json"
    if arguments.replay:
        entries = [
            Entry.model_validate_json(line) for line in entries_path.read_text().splitlines()
        ]
        results = json.loads(results_path.read_text())
    else:
        setattr(providers, "Enrichment", Diagnosing)  # noqa: B010
        if arguments.reuse_entries:
            lines = entries_path.read_text().splitlines()
            entries = [Entry.model_validate_json(line) for line in lines]
        else:
            entries = asyncio.run(collect(arguments.days))
            entries_path.write_text("".join(entry.model_dump_json() + "\n" for entry in entries))
        results = asyncio.run(
            extract(entries, os.environ["MODEL_ENDPOINT"], os.environ["ENRICHMENT_DEPLOYMENT"])
        )
        results_path.write_text(json.dumps(results))
        print(
            json.dumps({url: r["fields"] for url, r in results.items() if "fields" in r}),
            file=sys.stderr,
        )
    prices = (
        Decimal(os.environ.get("INPUT_PRICE", "0")),
        Decimal(os.environ.get("OUTPUT_PRICE", "0")),
    )
    print(json.dumps(review(entries, results, prices), indent=2))


if __name__ == "__main__":
    main()
