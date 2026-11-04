"""Fact-preserving architectural relevance contracts and deterministic selection."""

from typing import Annotated, Literal
from uuid import UUID

from newsloom_core.briefing import BriefingContract
from pydantic import Field

Short = Annotated[str, Field(strict=True, max_length=400)]

FACT_TASK = (
    "Review EVERY supplied stored-news item for an AI solution architect. Return every input "
    "UUID exactly once in reviewed_sources. Extract concise signals. kind=change: a vendor "
    "announces a concrete new/changed product, API, model, limit, price, availability, "
    "deprecation or security incident; product is the named product verbatim from the source. "
    "kind=case_study: a named CUSTOMER organization (not the vendor publishing the post) "
    "describes how it uses vendor products; product is the customer name verbatim, change is "
    "one short line on what it built or achieved (without repeating the customer name), and "
    "services lists up to 6 main named vendor products/services used (not use cases), each "
    "verbatim from the source. Vendor showcases without a named customer are routine. For "
    "kind=change, services is empty. protected_facts are short VERBATIM spans (no added quotes) "
    "with essential versions, numbers/units, capabilities or limits. event_key combines product, "
    "changed feature and version for duplicate consolidation. Mark material only concrete "
    "changes affecting model/platform choice, deployment, agent integration, security, pricing, "
    "deprecation or implementation. Security incidents, compromised or malicious releases and "
    "vulnerabilities are ALWAYS material with high impact. Case studies are "
    "significance=watch unless they announce a "
    "product change. Tutorials/how-to posts without a product change, marketing, funding, "
    "generic trends and opinion are routine. Never invent novelty, baselines, metrics or GA; "
    "availability is unknown unless explicit; preview is not GA. Implications are conditional "
    "analysis. Signals may be empty. Original UUIDs only, no tools."
)
SELECTION_TASK = (
    "Consolidate duplicate reports of the same named product/feature/version. Preserve kind, "
    "services, exact protected_facts, availability, caveats and original UUIDs. Rank concrete "
    "architectural changes by practical impact and confidence, not hype, recency or vendor. "
    "Remove routine and unsupported signals. Only use supplied facts; never upgrade preview to "
    "GA, invent baselines or add numbers."
)
SUMMARY_TASK = (
    "Write a selective English briefing for an AI solution architect from these material "
    "changes, in the given (ranked) order. For each change write ONE natural, readable paragraph: "
    "start with the named product and what concretely changed, then why it matters for "
    "architecture decisions, then essential caveats or availability. Keep the supplied numbers, "
    "versions and limits accurate; do not invent GA, performance, prices, prior versions or "
    "rollout. Never repeat a change. Group paragraphs under short plain topic headings (e.g. "
    "'Models and platforms', 'Agent tooling', 'Security'); never use internal keys or version "
    "labels as headings. No generic industry trends, filler or business-as-usual. No minimum "
    "length; at most 800 words. Cite original UUIDs only in each paragraph's sources field, "
    "never in the text. Use full when the input "
    "review completed; limited means evidence limitation, not brevity."
)
TLDR_TASK = (
    "Summarize this COMPLETED briefing in ONE concise paragraph, at most 90 words. Lead with the "
    "highest-impact product changes by exact product name, what changed and the practical "
    "consequence for an AI solution architect. Do not list customer names or case studies. "
    "Do not say merely that AI, agents or governance are evolving. No new claims, no "
    "headings/newlines. Put UUIDs only in the sources field, never in the text; cite only "
    "original UUIDs used in the completed briefing."
)


class Signal(BriefingContract):
    kind: Literal["change", "case_study"]
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
    services: Annotated[
        tuple[Annotated[str, Field(strict=True, min_length=1, max_length=80)], ...],
        Field(max_length=6),
    ]
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
            signal.kind != "change"
            or signal.significance != "material"
            or signal.confidence != "explicit"
            or not signal.change.strip()
            or not signal.implication.strip()
            or not signal.protected_facts
        ):
            continue
        key = (signal.product.casefold().strip(), "")
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
                        "sources": tuple(dict.fromkeys((*previous.sources, *signal.sources)))[:100],
                        "protected_facts": tuple(
                            dict.fromkeys((*previous.protected_facts, *signal.protected_facts))
                        )[:8],
                        "caveats": caveats[:5],
                        "change": merged_text(previous.change, signal.change),
                        "implication": merged_text(previous.implication, signal.implication),
                        "availability": availability,
                        "impact": "high"
                        if "high" in (previous.impact, signal.impact)
                        else previous.impact,
                    }
                ).model_dump()
            )
    ranked = sorted(
        selected.values(),
        key=lambda item: ({"high": 0, "medium": 1, "low": 2}[item.impact], -len(item.sources)),
    )
    per_vendor: dict[str, int] = {}
    result: list[Signal] = []
    for item in ranked:
        owner = vendor(item.product)
        if per_vendor.get(owner, 0) < VENDOR_CAP:
            per_vendor[owner] = per_vendor.get(owner, 0) + 1
            result.append(item)
    return result


VENDOR_CAP = 3


def merged_text(first: str, second: str, limit: int = 400) -> str:
    if second.casefold() in first.casefold():
        return first
    combined = f"{first.rstrip('. ')}; {second}"
    return combined if len(combined) <= limit else first


VENDOR_ALIASES = {"aws": "amazon"}


def vendor(product: str) -> str:
    first = (product.split() or [""])[0].casefold()
    return VENDOR_ALIASES.get(first, first)


def select_cases(signals: list[Signal], limit: int = 6) -> list[Signal]:
    cases: dict[str, Signal] = {}
    for signal in signals:
        if signal.kind == "case_study" and signal.services and signal.confidence == "explicit":
            cases.setdefault(signal.product.casefold().strip(), signal)
    return sorted(cases.values(), key=lambda item: -len(item.sources))[:limit]
