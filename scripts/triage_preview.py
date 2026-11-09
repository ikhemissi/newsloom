"""Local triage preview over the recorded announcement week; never writes to Azure.

Reads `.cache/announcement-preview/` (from scripts/announcement-preview.sh), rates
each item's grounded announcements with the production triage call and writes a
review plus a radar fixture for the local mock-up under `.cache/triage-preview/`.

    bash scripts/triage-preview.sh            # live model calls
    bash scripts/triage-preview.sh --replay   # rebuild review/fixture, no model calls
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

import httpx
from newsloom_core.entries import Entry
from newsloom_core.model_transport import ModelClient, ModelFailure, TransportLimits
from newsloom_enrichment.entities import load_curated
from newsloom_enrichment.models import Enrichment, grounded
from newsloom_enrichment.triage import FoundryTriage

SOURCE = Path(".cache/announcement-preview")
OUTPUT = Path(".cache/triage-preview")


def load() -> list[tuple[Entry, Enrichment]]:
    entries = {
        entry.url: entry
        for entry in (
            Entry.model_validate_json(line)
            for line in (SOURCE / "entries.jsonl").read_text().splitlines()
        )
    }
    items: list[tuple[Entry, Enrichment]] = []
    for url, result in json.loads((SOURCE / "results.json").read_text()).items():
        if "raw" not in result or url not in entries:
            continue
        raw = Enrichment.model_validate(result["raw"])
        kept, _ = grounded(raw.announcements, entries[url])
        items.append((entries[url], raw.model_copy(update={"announcements": kept})))
    return items


async def rate(
    items: list[tuple[Entry, Enrichment]], endpoint: str, deployment: str
) -> dict[str, dict[str, object]]:
    from azure.identity.aio import AzureCliCredential

    results: dict[str, dict[str, object]] = {}
    slots = asyncio.Semaphore(8)
    limits = TransportLimits(request_seconds=120, transport_attempts=2)
    async with AzureCliCredential() as credential, httpx.AsyncClient(trust_env=False) as http:

        async def one(entry: Entry, result: Enrichment) -> None:
            if not result.announcements:
                return
            async with slots:
                transport = ModelClient(http, credential, endpoint, limits)
                try:
                    ratings = await FoundryTriage(transport, deployment).rate(
                        entry.title,
                        result.summary,
                        result.article_kind.value,
                        result.announcements,
                        time.monotonic() + 180,
                    )
                except ModelFailure as error:
                    results[entry.url] = {"error": str(error)}
                    return
                results[entry.url] = {
                    "ratings": [rating.model_dump() for rating in ratings],
                    "input_tokens": transport.observations.input_tokens,
                    "output_tokens": transport.observations.output_tokens,
                }
                print(f"rated {len(results)}", file=sys.stderr)

        await asyncio.gather(*(one(entry, result) for entry, result in items))
    return results


def report(
    items: list[tuple[Entry, Enrichment]],
    results: dict[str, dict[str, object]],
    prices: tuple[Decimal, Decimal],
) -> dict[str, object]:
    curated = load_curated()
    tiers: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    tokens = [0, 0]
    cards: list[dict[str, object]] = []
    lines = ["# Triage preview", ""]
    for entry, result in items:
        rated = results.get(entry.url)
        if rated is None:
            continue
        if "ratings" not in rated:
            errors[str(rated.get("error"))] += 1
            continue
        tokens[0] += int(str(rated["input_tokens"]))
        tokens[1] += int(str(rated["output_tokens"]))
        lines += [f"## {entry.title}", f"{entry.source} · {result.article_kind.value}", ""]
        for item, rating in zip(result.announcements, rated["ratings"], strict=True):  # type: ignore[call-overload]
            tiers[rating["tier"]] += 1
            lines.append(
                f"- **{rating['tier']}** [{rating['capability']}] {item.statement} "
                f"_Why: {rating['reason']}_"
            )
            cards.append(
                {
                    "id": f"{entry.url}#{len(cards)}",
                    "news_id": entry.url,
                    "title": entry.title,
                    "url": entry.url,
                    "source": entry.source,
                    "published_at": entry.published_at.isoformat(),
                    "article_kind": result.article_kind.value,
                    "statement": item.statement,
                    "status": item.status.value,
                    "effective_date": item.effective_date,
                    "deadline": item.deadline,
                    "products": [
                        {"name": m.product, "vendor": curated.vendor(m.vendor)[0]}
                        for m in item.products
                    ],
                    "tier": rating["tier"],
                    "reason": rating["reason"],
                    "capability": rating["capability"],
                }
            )
        lines.append("")
    (OUTPUT / "review.md").write_text("\n".join(lines))
    (OUTPUT / "radar-fixture.json").write_text(json.dumps({"cards": cards}, indent=1))
    total = sum(tiers.values())
    return {
        "items_rated": sum(1 for r in results.values() if "ratings" in r),
        "errors": dict(errors),
        "announcements": total,
        "tiers": {
            tier: f"{count} ({100 * count / max(total, 1):.0f}%)"
            for tier, count in tiers.most_common()
        },
        "input_tokens": tokens[0],
        "output_tokens": tokens[1],
        "estimated_cost_usd": float(
            (tokens[0] * prices[0] + tokens[1] * prices[1]) / Decimal(1_000_000)
        ),
        "review": str(OUTPUT / "review.md"),
        "fixture": str(OUTPUT / "radar-fixture.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true")
    arguments = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    items = load()
    recorded = OUTPUT / "results.json"
    if arguments.replay:
        results = json.loads(recorded.read_text())
    else:
        results = asyncio.run(
            rate(items, os.environ["MODEL_ENDPOINT"], os.environ["ENRICHMENT_DEPLOYMENT"])
        )
        recorded.write_text(json.dumps(results))
    prices = (
        Decimal(os.environ.get("INPUT_PRICE", "0")),
        Decimal(os.environ.get("OUTPUT_PRICE", "0")),
    )
    print(json.dumps(report(items, results, prices), indent=2))


if __name__ == "__main__":
    main()
