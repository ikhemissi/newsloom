"""Capped sequential enrichment with recoverable ownership and atomic writes."""

import asyncio
import time

from newsloom_core.diagnostics import event

from newsloom_enrichment.models import DEFAULT_LIMITS, EnrichmentFailure, Limits
from newsloom_enrichment.providers import EmbeddingProvider, LlmProvider
from newsloom_enrichment.repository import EnrichmentRepository, ModelMetadata


async def run(
    repository: EnrichmentRepository,
    llm: LlmProvider,
    embeddings: EmbeddingProvider,
    metadata: ModelMetadata,
    correlation: str,
    *,
    limit: int = 25,
    limits: Limits = DEFAULT_LIMITS,
) -> dict[str, int]:
    if isinstance(limit, bool) or not 1 <= limit <= limits.max_items:
        raise EnrichmentFailure("invalid_item_limit")
    counts = dict.fromkeys(
        ("claimed_run", "enriched_run", "failed_run", "lease_lost_run", "budget_exhausted"), 0
    )
    deadline = time.monotonic() + limits.job_seconds - limits.shutdown_seconds
    async with asyncio.timeout_at(deadline):
        for _ in range(limit):
            if time.monotonic() + limits.item_seconds + limits.shutdown_seconds >= deadline:
                counts["budget_exhausted"] = 1
                break
            claim = await repository.claim(correlation)
            if claim is None:
                break
            counts["claimed_run"] += 1
            event(
                "enrichment_claim",
                correlation,
                outcome="processing",
                counts={"queue_id": claim.id.hex, "attempt": claim.attempts},
            )
            failure: EnrichmentFailure | None = None
            try:
                item_deadline = min(deadline, time.monotonic() + limits.item_seconds)
                async with asyncio.timeout_at(item_deadline):
                    generated = await llm.generate(claim.entry, item_deadline)
                    vector = await embeddings.embed(claim.entry, generated, item_deadline)
                    await repository.complete(claim, generated, vector, metadata, correlation)
            except TimeoutError:
                failure = EnrichmentFailure("enrichment_item_deadline")
            except EnrichmentFailure as error:
                failure = error
            if failure is not None:
                if str(failure) == "enrichment_lease_lost":
                    counts["lease_lost_run"] += 1
                else:
                    try:
                        await repository.fail(claim, str(failure), failure.retry_after, correlation)
                        counts["failed_run"] += 1
                    except EnrichmentFailure as error:
                        if str(error) != "enrichment_lease_lost":
                            raise
                        counts["lease_lost_run"] += 1
                event("enrichment_item", correlation, outcome="failure", category=str(failure))
            else:
                counts["enriched_run"] += 1
    counts.update(await repository.counts())
    event(
        "enrichment",
        correlation,
        outcome=(
            "partial"
            if counts["failed_run"] or counts["lease_lost_run"] or counts["budget_exhausted"]
            else "success"
        ),
        counts=counts,
    )
    return counts
