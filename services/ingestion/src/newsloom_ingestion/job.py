"""Fetch configured feeds, persist before advancing validators, then screen."""

import asyncio
import time
from datetime import UTC, datetime

from newsloom_core.feeds import FeedSource
from pydantic import ValidationError

from newsloom_ingestion.models import DEFAULT_LIMITS, IngestionFailure, Limits
from newsloom_ingestion.parsing import included, parse
from newsloom_ingestion.repository import Repository
from newsloom_ingestion.retrieval import PublicClient
from newsloom_ingestion.scanner import ContentSecurityScanner
from newsloom_ingestion.telemetry import event


def select_sources(sources: tuple[FeedSource, ...], selected: list[str]) -> tuple[FeedSource, ...]:
    if set(selected) - {source.id for source in sources}:
        raise IngestionFailure("unknown_source")
    return tuple(source for source in sources if not selected or source.id in selected)


async def ingest_source(
    source: FeedSource,
    client: PublicClient,
    repository: Repository,
    correlation: str,
    force: bool,
    limits: Limits,
) -> dict[str, int]:
    counts = {"found": 0, "filtered": 0, "duplicates": 0, "staged": 0, "feeds_ok": 0}
    headers = await repository.source(source)
    deadline = time.monotonic() + limits.feed_seconds
    try:
        async with asyncio.timeout_at(deadline):
            document = await client.fetch(str(source.url), {} if force else headers, deadline)
            if document.status == 304:
                if not headers or force:
                    raise IngestionFailure("unexpected_not_modified")
                counts["feeds_ok"] = 1
                await repository.finish_source(source.id, correlation, "not_modified", counts)
                event("feed", correlation, source=source.id, outcome="not_modified", counts=counts)
                return counts
            if document.status != 200:
                raise IngestionFailure(f"feed_http_{document.status}")
            entries, parsed = parse(source, document.body, document.url, datetime.now(UTC), limits)
            if time.monotonic() >= deadline:
                raise IngestionFailure("feed_deadline")
        counts["found"] = parsed
        for entry in entries:
            if not included(source, entry):
                counts["filtered"] += 1
            elif await repository.stage(entry, correlation):
                counts["staged"] += 1
            else:
                counts["duplicates"] += 1
        outcome = "fetched" if parsed else "empty"
        counts["feeds_ok"] = 1
        await repository.finish_source(
            source.id, correlation, outcome, counts, document.headers if parsed else None
        )
        event("feed", correlation, source=source.id, outcome=outcome, counts=counts)
        return counts
    except (IngestionFailure, ValidationError, TimeoutError) as error:
        category = str(error) if isinstance(error, IngestionFailure) else type(error).__name__
        await repository.finish_source(source.id, correlation, category, counts)
        event(
            "feed",
            correlation,
            source=source.id,
            outcome="failed",
            category=category,
            counts=counts,
        )
        return {**counts, "feeds_failed": 1}


async def run(
    sources: tuple[FeedSource, ...],
    repository: Repository,
    scanner: ContentSecurityScanner,
    correlation: str,
    *,
    force: bool = False,
    limits: Limits = DEFAULT_LIMITS,
) -> dict[str, int]:
    await repository.acquire()
    start = time.monotonic()
    deadline = start + limits.job_seconds - 20
    totals: dict[str, int] = {
        "found": 0,
        "filtered": 0,
        "duplicates": 0,
        "staged": 0,
        "feeds_failed": 0,
        "feeds_ok": 0,
        "accepted_run": 0,
        "rejected_run": 0,
        "deferred_run": 0,
    }
    semaphore = asyncio.Semaphore(limits.concurrency)
    client = PublicClient(limits)

    async def fetch(source: FeedSource) -> dict[str, int]:
        async with semaphore:
            return await ingest_source(source, client, repository, correlation, force, limits)

    try:
        async with asyncio.timeout_at(deadline):
            tasks = [asyncio.create_task(fetch(source)) for source in sources]
            try:
                results = await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                for key, value in result.items():
                    totals[key] += value
            while time.monotonic() + limits.request_seconds + 1 < deadline:
                pending = await repository.deferred([source.id for source in sources])
                if pending is None:
                    break
                identifier, entry = pending
                decision = await scanner.scan(entry, deadline)
                await repository.decide(identifier, entry, decision, correlation)
                totals[f"{decision.disposition}_run"] += 1
                if decision.disposition == "deferred":
                    event("scanner", correlation, outcome="deferred", category=decision.reason)
        totals.update(await repository.counts())
        event(
            "ingestion",
            correlation,
            outcome="partial" if totals["feeds_failed"] else "completed",
            counts=totals,
        )
        if totals["feeds_failed"] == len(sources):
            raise IngestionFailure("all_sources_failed")
        return totals
    finally:
        await repository.release()
