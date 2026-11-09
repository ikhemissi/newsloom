"""Capped sequential enrichment with recoverable ownership and atomic writes."""

import asyncio
import time
from typing import Protocol
from uuid import UUID

from newsloom_core.diagnostics import event
from newsloom_core.entries import Entry

from newsloom_enrichment.entities import Curated, load_curated, mention_texts
from newsloom_enrichment.models import (
    DEFAULT_LIMITS,
    Announcement,
    Enrichment,
    EnrichmentFailure,
    Limits,
    Vector,
)
from newsloom_enrichment.providers import EmbeddingProvider, LlmProvider
from newsloom_enrichment.repository import (
    EnrichmentRepository,
    ModelMetadata,
    Repository,
    Untriaged,
)
from newsloom_enrichment.triage import Rating

# Title, summary and statements of one item plus the rubric; output is short.
TRIAGE_TOKENS = 5_000


class TokenBudget:
    """Paces generation below the deployment's per-minute token limit."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.window: list[tuple[float, int]] = []

    @staticmethod
    def estimate(entry: Entry) -> int:
        # Bytes/3 over-approximates tokens for English text; plus prompt, schema and output.
        return len(entry.text.encode()) // 3 + 6_000

    async def admit(self, tokens: int, deadline: float) -> None:
        while True:
            now = time.monotonic()
            self.window = [(at, used) for at, used in self.window if now - at < 60]
            if sum(used for _, used in self.window) + tokens <= self.per_minute:
                self.window.append((now, tokens))
                return
            wait = 60 - (now - self.window[0][0])
            if now + wait >= deadline:
                raise EnrichmentFailure("enrichment_token_budget")
            await asyncio.sleep(wait)


class TriageProvider(Protocol):
    async def rate(
        self,
        title: str,
        summary: str,
        article_kind: str,
        announcements: tuple[Announcement, ...],
        deadline: float,
    ) -> tuple[Rating, ...]: ...


async def rate(
    triage: TriageProvider | None,
    budget: TokenBudget,
    title: str,
    result: Enrichment,
    deadline: float,
) -> tuple[Rating, ...]:
    """Triage never blocks publication: failures leave announcements untriaged."""
    if triage is None or not result.announcements:
        return ()
    try:
        await budget.admit(TRIAGE_TOKENS, deadline)
        return await triage.rate(
            title, result.summary, result.article_kind.value, result.announcements, deadline
        )
    except EnrichmentFailure:
        return ()


async def mention_vectors(
    embeddings: EmbeddingProvider, curated: Curated, result: Enrichment, deadline: float
) -> dict[str, Vector]:
    texts = mention_texts(curated, result.announcements)
    if not texts:
        return {}
    return dict(zip(texts, await embeddings.embed_texts(texts, deadline), strict=True))


async def run(
    repository: EnrichmentRepository,
    llm: LlmProvider,
    embeddings: EmbeddingProvider,
    metadata: ModelMetadata,
    correlation: str,
    *,
    limit: int = 25,
    limits: Limits = DEFAULT_LIMITS,
    curated: Curated | None = None,
    triage: TriageProvider | None = None,
) -> dict[str, int]:
    curated = curated or load_curated()
    budget = TokenBudget(limits.tokens_per_minute)
    if isinstance(limit, bool) or not 1 <= limit <= limits.max_items:
        raise EnrichmentFailure("invalid_item_limit")
    counts = dict.fromkeys(
        (
            "claimed_run",
            "enriched_run",
            "failed_run",
            "lease_lost_run",
            "budget_exhausted",
            "triage_failed",
        ),
        0,
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
                    await budget.admit(TokenBudget.estimate(claim.entry), item_deadline)
                    generated = await llm.generate(claim.entry, item_deadline)
                    vector = await embeddings.embed(claim.entry, generated, item_deadline)
                    mentions = await mention_vectors(embeddings, curated, generated, item_deadline)
                    ratings = await rate(
                        triage, budget, claim.entry.title, generated, item_deadline
                    )
                    if triage is not None and generated.announcements and not ratings:
                        counts["triage_failed"] += 1
                    await repository.complete(
                        claim, generated, vector, metadata, correlation, mentions, ratings
                    )
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


async def backfill(
    repository: Repository,
    llm: LlmProvider,
    embeddings: EmbeddingProvider,
    correlation: str,
    *,
    limits: Limits = DEFAULT_LIMITS,
    concurrency: int = 6,
) -> dict[str, int]:
    """Announcements for recent news enriched before extraction; summaries are unchanged."""
    deadline = time.monotonic() + limits.job_seconds - limits.shutdown_seconds
    budget = TokenBudget(limits.tokens_per_minute)
    curated = repository.curated
    database = asyncio.Lock()
    slots = asyncio.Semaphore(concurrency)
    counts = dict.fromkeys(("candidates", "stored", "failed", "skipped", "deferred"), 0)

    async def one(news_id: UUID, entry: Entry) -> None:
        async with slots:
            if time.monotonic() + limits.item_seconds >= deadline:
                counts["deferred"] += 1
                return
            item_deadline = min(deadline, time.monotonic() + limits.item_seconds)
            try:
                await budget.admit(TokenBudget.estimate(entry), item_deadline)
                result = await llm.generate(entry, item_deadline)
                mentions = await mention_vectors(embeddings, curated, result, item_deadline)
            except (EnrichmentFailure, TimeoutError) as error:
                counts["failed"] += 1
                event(
                    "announcement_backfill_item",
                    correlation,
                    outcome="failure",
                    category=str(error) if isinstance(error, EnrichmentFailure) else "timeout",
                )
                return
            async with database:
                stored = await repository.store_backfill(news_id, result, mentions)
            counts["stored" if stored else "skipped"] += 1

    async with asyncio.timeout_at(deadline + limits.shutdown_seconds / 2):
        candidates = await repository.backfill_candidates(500)
        counts["candidates"] = len(candidates)
        await asyncio.gather(*(one(news_id, entry) for news_id, entry in candidates))
    counts.update({f"graph_{key}": value for key, value in repository.graph.items()})
    event("announcement_backfill", correlation, outcome="completed", counts=counts)
    return counts


async def triage_backfill(
    repository: Repository,
    triage: TriageProvider,
    correlation: str,
    *,
    limits: Limits = DEFAULT_LIMITS,
    concurrency: int = 6,
) -> dict[str, int]:
    """Triage stored announcements that predate triage or whose triage failed."""
    deadline = time.monotonic() + limits.job_seconds - limits.shutdown_seconds
    budget = TokenBudget(limits.tokens_per_minute)
    database = asyncio.Lock()
    slots = asyncio.Semaphore(concurrency)
    counts = dict.fromkeys(("items", "announcements", "failed", "deferred"), 0)

    async def one(item: Untriaged) -> None:
        async with slots:
            if time.monotonic() + limits.item_seconds >= deadline:
                counts["deferred"] += 1
                return
            item_deadline = min(deadline, time.monotonic() + limits.item_seconds)
            try:
                await budget.admit(TRIAGE_TOKENS, item_deadline)
                ratings = await triage.rate(
                    item.title,
                    item.summary,
                    item.article_kind,
                    tuple(item.announcements),
                    item_deadline,
                )
            except EnrichmentFailure, TimeoutError:
                counts["failed"] += 1
                return
            async with database:
                counts["announcements"] += await repository.store_triage(item.ids, ratings)

    async with asyncio.timeout_at(deadline + limits.shutdown_seconds / 2):
        items = await repository.untriaged(400)
        counts["items"] = len(items)
        await asyncio.gather(*(one(item) for item in items))
    event("triage_backfill", correlation, outcome="completed", counts=counts)
    return counts
