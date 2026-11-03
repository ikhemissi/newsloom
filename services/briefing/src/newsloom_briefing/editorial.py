"""Fact-preserving architectural relevance contracts and deterministic selection."""

from typing import Annotated, Literal
from uuid import UUID

from newsloom_core.briefing import BriefingContract
from pydantic import Field

Short = Annotated[str, Field(strict=True, max_length=400)]

FACT_TASK = (
    "Review EVERY supplied stored-news item for an AI solution architect. Return every input "
    "UUID exactly once in reviewed_sources. Extract concise signals with the named product, "
    "specific new change, practical architecture implication, release status and important "
    "caveats. Product names must appear verbatim in supplied titles/summaries. "
    "protected_facts must be short VERBATIM spans from supplied titles/summaries "
    "containing essential versions, numbers/units, capabilities or limits. Use an event_key "
    "combining the named product, changed feature and version for duplicate consolidation. "
    "Mark material only supported concrete changes affecting model/platform choice, deployment, "
    "agent integration, security, pricing, deprecation or implementation. Routine marketing, "
    "funding with no design impact, generic trends and unchanged capability are routine, not "
    "material. Watch uncertain future claims; never invent novelty, baselines, metrics or GA. "
    "Availability is unknown unless explicit; preview is not GA. Implications are conditional "
    "analysis, not reported guarantees. Signals may be empty when all items are routine. "
    "Keep each signal compact; no prose roundup. Original UUIDs only, no tools."
)
SELECTION_TASK = (
    "Consolidate duplicate reports of the same named product/feature/version. Preserve exact "
    "protected_facts, availability, caveats and original UUIDs. Rank concrete architectural "
    "changes by practical impact and confidence, not hype or recency. Remove routine and "
    "unsupported signals. Select only changes that can be clearly explained in up to five "
    "minutes, with no target item count; omit lower-impact items rather than padding. "
    "Keep high-impact facts, not generic thematic prose. Only use supplied "
    "facts; never upgrade preview to GA, invent baselines or add numbers."
)
SUMMARY_TASK = (
    "Write a selective English briefing for an AI solution architect using these material "
    "signals. Lead each item with its NAMED PRODUCT and CONCRETE CHANGE, then explain why it "
    "matters for architecture decisions and the essential caveats. Include all supplied "
    "protected_facts verbatim, including units/versions. Include the supplied change and "
    "implication text verbatim, with the implication clearly conditional analysis. "
    "Preserve explicit preview/announced "
    "status; do not invent GA, performance, price comparisons, prior versions or rollout. "
    "Separate conditional architectural implications from sourced facts. No generic industry "
    "trends, adoption/governance filler, marketing roundup or business-as-usual. There is NO "
    "minimum length: one change needs only a short specific item. Use at most 850 narrative "
    "words to leave room for the TLDR; do not pad. Cite original UUIDs per paragraph. "
    "Use full when the input review completed; limited means evidence limitation, not brevity."
)
TLDR_TASK = (
    "Summarize this COMPLETED selected briefing in ONE concise paragraph, at most 100 words "
    "and shorter for few changes. Use the exact product names from the summary. "
    "Name the highest-impact products and what actually changed, "
    "with practical consequences/caveats for an AI solution architect. Do not say merely that "
    "AI, agents or governance are evolving. No new claims, no headings/newlines. Cite only "
    "original UUIDs used in the completed summary."
)


class Signal(BriefingContract):
    product: Annotated[str, Field(strict=True, min_length=1, max_length=120)]
    event_key: Annotated[str, Field(strict=True, min_length=1, max_length=180)]
    change: Short
    implication: Short
    protected_facts: Annotated[tuple[Short, ...], Field(max_length=8)]
    caveats: Annotated[tuple[Short, ...], Field(max_length=5)]
    availability: Literal["ga", "preview", "announced", "unknown"]
    significance: Literal["material", "watch", "routine"]
    impact: Literal["high", "medium", "low"]
    confidence: Literal["explicit", "uncertain"]
    sources: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=100)]


class Facts(BriefingContract):
    reviewed_sources: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=100)]
    signals: Annotated[tuple[Signal, ...], Field(max_length=30)]


class Selection(BriefingContract):
    signals: Annotated[tuple[Signal, ...], Field(max_length=30)]


def select(signals: list[Signal]) -> list[Signal]:
    selected: dict[tuple[str, str], Signal] = {}
    for signal in signals:
        if (
            signal.significance != "material"
            or signal.confidence != "explicit"
            or not signal.change.strip()
            or not signal.implication.strip()
            or not signal.protected_facts
        ):
            continue
        key = (signal.product.casefold().strip(), signal.event_key.casefold().strip())
        previous = selected.get(key)
        if previous is None:
            selected[key] = signal
        else:
            availability = previous.availability
            caveats = tuple(dict.fromkeys((*previous.caveats, *signal.caveats)))
            if availability in ("unknown", "announced"):
                availability = (
                    signal.availability if signal.availability != "unknown" else availability
                )
            elif {availability, signal.availability} == {"ga", "preview"}:
                availability = "unknown"
                caveats = (*caveats, "Sources disagree on GA versus preview; do not assume GA.")
            selected[key] = Signal.model_validate(
                previous.model_copy(
                    update={
                        "sources": tuple(dict.fromkeys((*previous.sources, *signal.sources))),
                        "protected_facts": tuple(
                            dict.fromkeys((*previous.protected_facts, *signal.protected_facts))
                        ),
                        "caveats": caveats,
                        "availability": availability,
                        "impact": "high"
                        if "high" in (previous.impact, signal.impact)
                        else previous.impact,
                    }
                ).model_dump()
            )
    return sorted(
        selected.values(),
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}[item.impact],
            item.product.casefold(),
            item.event_key,
        ),
    )
