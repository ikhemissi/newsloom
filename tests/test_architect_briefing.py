import json
import time
from datetime import UTC, datetime, timedelta
from typing import TypeVar
from uuid import UUID, uuid4

import pytest
from newsloom_briefing.editorial import Facts, Selection, Signal, select, select_cases, vendor
from newsloom_briefing.generation import (
    DraftParagraph,
    DraftSection,
    Failure,
    Summary,
    Tldr,
    evidence_schema,
    synthesize,
    validate_signals,
)
from newsloom_briefing.repository import Evidence
from newsloom_core.briefing import Briefing, BriefingRead
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
CUTOFF = datetime(2026, 11, 3, 5, tzinfo=UTC)


def item(title: str, summary: str) -> Evidence:
    return Evidence(
        id=uuid4(),
        title=title,
        summary=summary,
        source="authored",
        category="developer-tools",
        published_at=CUTOFF - timedelta(days=1),
        url="https://publisher.test/" + uuid4().hex,
    )


def material(evidence: Evidence) -> Signal:
    return Signal(
        kind="change",
        services=(),
        product="Nimbus SDK",
        event_key="nimbus-2.1-delegated-auth",
        change="Nimbus SDK 2.1 adds delegated authentication",
        implication="Evaluate delegated integration subject to preview and EU-only constraints.",
        protected_facts=("2.1", "512 KB", "EU-only"),
        caveats=("Preview; not proven production-ready",),
        availability="preview",
        significance="material",
        impact="high",
        confidence="explicit",
        sources=(evidence.id,),
    )


class EditorialProvider:
    def __init__(
        self,
        signals: dict[str, Signal],
        *,
        generic_summary: bool = False,
        generic_tldr: bool = False,
    ) -> None:
        self.signals = signals
        self.generic_summary = generic_summary
        self.generic_tldr = generic_tldr
        self.calls: list[tuple[str, str]] = []

    async def generate(
        self, stage: str, task: str, value: str, schema: type[T], deadline: float
    ) -> T:
        self.calls.append((stage, value))
        data = json.loads(value)
        if stage == "notes":
            ids = tuple(row["id"] for row in data)
            result: BaseModel = Facts(
                reviewed_sources=ids,
                signals=tuple(
                    self.signals[identifier] for identifier in ids if identifier in self.signals
                ),
            )
        elif stage == "reduce":
            result = Selection(signals=tuple(select([Signal.model_validate(row) for row in data])))
        elif stage == "summary":
            assert all("event_key" not in row and "significance" not in row for row in data)
            first_sources = tuple(UUID(source) for source in data[0]["sources"])
            text = (
                "AI adoption is evolving and governance is increasingly important."
                if self.generic_summary
                else "Nimbus SDK 2.1 adds delegated authentication in preview, with 512 KB "
                "requests and EU-only deployment. "
                "Evaluate delegated integration subject to preview and EU-only constraints. "
                "This is not a proven production replacement."
            )
            result = Summary(
                coverage="full",
                sections=(
                    DraftSection(
                        heading="Nimbus SDK: delegated authentication",
                        paragraphs=(DraftParagraph(text=text, sources=first_sources),),
                    ),
                ),
            )
        else:
            summary = Summary.model_validate(data)
            text = (
                "AI continues to evolve."
                if self.generic_tldr
                else "Nimbus SDK 2.1 adds delegated authentication, but preview and EU-only "
                "deployment constrain immediate production adoption."
            )
            result = Tldr(
                paragraph=DraftParagraph(
                    text=text,
                    sources=summary.sections[0].paragraphs[0].sources,
                )
            )
        return schema.model_validate_json(result.model_dump_json())


def corpus() -> tuple[list[Evidence], dict[str, Signal]]:
    first = item(
        "Nimbus SDK 2.1 adds delegated authentication",
        "Nimbus SDK 2.1 is in preview, supports 512 KB requests and EU-only deployment.",
    )
    duplicate = item("Nimbus SDK 2.1 preview", first.summary)
    routine = item(
        "Vanta Labs funding", "Vanta Labs raises capital. No product change is described."
    )
    signals = {str(first.id): material(first), str(duplicate.id): material(duplicate)}
    signals[str(routine.id)] = Signal(
        kind="change",
        services=(),
        product="Vanta Labs",
        event_key="funding",
        change="Raises capital",
        implication="",
        protected_facts=("raises capital",),
        caveats=(),
        availability="unknown",
        significance="routine",
        impact="low",
        confidence="explicit",
        sources=(routine.id,),
    )
    return [first, duplicate, routine], signals


async def test_material_change_specifics_survive_dedup_selection_summary_and_tldr() -> None:
    evidence, signals = corpus()
    provider = EditorialProvider(signals)
    result = await synthesize(provider, evidence, CUTOFF, time.monotonic() + 30)
    assert result.editorial_policy == "architect-v1" and result.coverage == "full"
    assert result.evidence_count == 3
    assert len(result.sections) == 1 and len(result.citations) == 2
    text = result.sections[0].paragraphs[0].text
    for fact in ("Nimbus SDK", "2.1", "preview", "512 KB", "EU-only"):
        assert fact in text
    assert "Vanta" not in text
    assert len(text.split()) < 900
    assert result.tldr is not None and "Nimbus SDK 2.1" in result.tldr.text
    assert provider.calls[-1][0] == "tldr"
    assert set(json.loads(provider.calls[-1][1])) == {"coverage", "sections"}
    reviewed = [
        row["id"] for stage, raw in provider.calls if stage == "notes" for row in json.loads(raw)
    ]
    assert reviewed == [str(row.id) for row in evidence]
    assert result.sections[0].paragraphs[0].references == (1, 2)


@pytest.mark.parametrize(
    "generic_summary,generic_tldr,error",
    [
        (True, False, "generic_or_missing_change"),
        (False, True, "generic_tldr"),
    ],
)
async def test_schema_valid_generic_prose_fails_editorial_quality(
    generic_summary: bool,
    generic_tldr: bool,
    error: str,
) -> None:
    evidence, signals = corpus()
    with pytest.raises(Failure, match=error):
        await synthesize(
            EditorialProvider(signals, generic_summary=generic_summary, generic_tldr=generic_tldr),
            evidence,
            CUTOFF,
            time.monotonic() + 30,
        )


async def test_routine_review_is_distinct_from_empty_news_or_failed_generation() -> None:
    evidence, _ = corpus()
    provider = EditorialProvider({})
    result = await synthesize(provider, evidence, CUTOFF, time.monotonic() + 30)
    assert result.coverage == "no_material_changes" and result.evidence_count == 3
    assert result.tldr is None and not result.sections and not result.citations
    assert [stage for stage, _ in provider.calls] == ["notes"]
    empty = await synthesize(provider, [], CUTOFF, time.monotonic() + 30)
    assert empty.coverage == "empty" and empty.evidence_count == 0
    BriefingRead.model_validate(
        {
            "briefing": result,
            "refresh": {"expected_cutoff": CUTOFF, "state": "ready", "stale": False},
        }
    )


def test_unsupported_specifics_are_dropped_and_invented_ga_is_downgraded() -> None:
    evidence, signals = corpus()
    signal = signals[str(evidence[0].id)]
    rows = {row.id: row for row in evidence}
    for updated in (
        signal.model_copy(update={"protected_facts": ("2.2",)}),
        signal.model_copy(update={"product": "Invented Platform"}),
        signal.model_copy(update={"change": "Nimbus SDK cuts cost by 50%"}),
    ):
        assert validate_signals((updated, signal), rows) == [signal]
    mixed = signal.model_copy(update={"protected_facts": ("2.2", *signal.protected_facts)})
    assert validate_signals((mixed,), rows)[0].protected_facts == signal.protected_facts
    (downgraded,) = validate_signals((signal.model_copy(update={"availability": "ga"}),), rows)
    assert downgraded.availability == "unknown"
    with pytest.raises(Failure, match="foreign_citation"):
        validate_signals((signal.model_copy(update={"sources": (uuid4(),)}),), rows)


def test_source_enumeration_covers_new_factual_candidates_and_review_lists() -> None:
    evidence, _ = corpus()
    schema = evidence_schema(
        Facts, "notes", json.dumps([row.model_dump(mode="json") for row in evidence])
    )
    definitions = schema["$defs"]
    properties = schema["properties"]
    assert isinstance(definitions, dict) and isinstance(properties, dict)
    expected = {str(row.id) for row in evidence}
    assert set(definitions["Signal"]["properties"]["sources"]["items"]["enum"]) == expected
    assert set(properties["reviewed_sources"]["items"]["enum"]) == expected


def test_duplicate_unknown_status_does_not_erase_explicit_availability() -> None:
    evidence, signals = corpus()
    first = signals[str(evidence[0].id)]
    unknown = signals[str(evidence[1].id)].model_copy(update={"availability": "unknown"})
    assert select([first, unknown])[0].availability == "preview"
    assert select([unknown, first])[0].availability == "preview"
    conflicting = first.model_copy(update={"availability": "ga"})
    merged = select([first, conflicting])[0]
    assert merged.availability == "unknown"
    assert any("disagree" in caveat for caveat in merged.caveats)


async def test_new_combined_word_boundary_and_legacy_read_compatibility() -> None:
    evidence, signals = corpus()
    artifact = await synthesize(EditorialProvider(signals), evidence, CUTOFF, time.monotonic() + 30)
    value = artifact.model_dump()
    value["tldr"] = {"text": " ".join(["TLDR"] * 82), "references": [1]}
    value["sections"] = [
        {
            "heading": "Authored",
            "paragraphs": [
                {"text": " ".join(["word"] * 918), "references": [1, 2]},
            ],
        }
    ]
    assert Briefing.model_validate(value).editorial_policy == "architect-v1"
    value["sections"][0]["paragraphs"][0]["text"] += " extra"
    with pytest.raises(ValidationError, match="length"):
        Briefing.model_validate(value)
    value["editorial_policy"] = None
    value["sections"][0]["paragraphs"][0]["text"] = " ".join(["word"] * 1026)
    legacy = Briefing.model_validate(value)
    assert "editorial_policy" not in json.loads(legacy.model_dump_json())
    assert Briefing.model_validate_json(legacy.model_dump_json()).editorial_policy is None
    value["editorial_policy"] = "unknown-v2"
    with pytest.raises(ValidationError):
        Briefing.model_validate(value)


def test_case_studies_keep_grounded_services_and_vendor_cap_limits_one_vendor() -> None:
    case_source = item(
        "How Acme automated freight with Amazon Bedrock",
        "Acme used Amazon Bedrock and Amazon EC2 with human approval to automate exceptions.",
    )
    rows = {case_source.id: case_source}
    case = Signal(
        kind="case_study",
        services=("Amazon Bedrock", "Amazon EC2", "Invented Service"),
        product="Acme",
        event_key="acme freight",
        change="Automated freight exceptions with human approval",
        implication="Pattern for back-office agents",
        protected_facts=("human approval",),
        caveats=(),
        availability="unknown",
        significance="watch",
        impact="medium",
        confidence="explicit",
        sources=(case_source.id,),
    )
    (grounded_case,) = validate_signals((case,), rows)
    assert grounded_case.services == ("Amazon Bedrock", "Amazon EC2")
    assert select_cases([grounded_case]) == [grounded_case] and select([grounded_case]) == []
    assert validate_signals((case.model_copy(update={"services": ("Nope",)}),), rows) == []
    changes = [
        case.model_copy(
            update={
                "kind": "change",
                "services": (),
                "significance": "material",
                "product": f"{vendor_name} Product {index}",
                "event_key": f"{vendor_name}-{index}",
            }
        )
        for vendor_name in ("Amazon", "AWS", "OpenAI")
        for index in range(3)
    ]
    chosen = select(changes)
    assert sum(vendor(s.product) == "amazon" for s in chosen) == 3
    assert sum(vendor(s.product) == "openai" for s in chosen) == 3


def test_same_product_reports_merge_into_one_item() -> None:
    evidence, signals = corpus()
    base = signals[str(evidence[0].id)]
    other = base.model_copy(
        update={"event_key": "different key", "change": "Adds async subagents", "impact": "high"}
    )
    many = tuple(f"fact {index}" for index in range(8))
    other = other.model_copy(update={"protected_facts": many, "caveats": ("a", "b", "c", "d", "e")})
    (merged,) = select([base, other])
    assert len(merged.protected_facts) == 8 and len(merged.caveats) == 5
    assert "Adds async subagents" in merged.change and base.change.rstrip(". ") in merged.change
