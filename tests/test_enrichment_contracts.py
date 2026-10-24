import json
from pathlib import Path

import pytest
from newsloom_core.categories import Category, load_categories
from newsloom_core.entries import Entry
from newsloom_enrichment.models import Enrichment, Vector
from newsloom_ingestion.models import Entry as IngestionEntry
from pydantic import ValidationError
from test_ingestion_database import entry


def result() -> dict[str, object]:
    return {
        "summary_sentences": ["Nova released an SDK.", "It supports asynchronous requests."],
        "category": "developer-tools",
        "tags": ["sdk", "async", "software"],
    }


def test_shared_entry_preserves_the_existing_wire_contract() -> None:
    original = entry()
    assert Entry is IngestionEntry
    assert Entry.model_validate_json(original.model_dump_json()).model_dump_json() == (
        original.model_dump_json()
    )
    assert list(json.loads(original.model_dump_json())) == [
        "source",
        "guid",
        "url",
        "title",
        "text",
        "published_at",
        "date_origin",
        "author",
        "categories",
    ]


def test_approved_catalogue_is_exact_and_governance_is_not_regulations() -> None:
    categories = load_categories()
    assert len(categories) == 11 and {item.id for item in categories} == set(Category)
    governance = next(item for item in categories if item.id == Category.GOVERNANCE)
    assert governance.label == "Governance" and "gateways" in governance.description


def test_catalogue_rejects_duplicate_missing_unknown_and_extra_fields(tmp_path: Path) -> None:
    rows = json.loads(Path("config/categories.json").read_text())
    path = tmp_path / "categories.json"
    for changed in [
        rows[:-1],
        [rows[0]] * 11,
        [{**rows[0], "id": "unknown"}, *rows[1:]],
        [{**rows[0], "extra": True}, *rows[1:]],
    ]:
        path.write_text(json.dumps(changed))
        with pytest.raises((ValueError, ValidationError)):
            load_categories(path)


def test_summary_is_plain_text_and_tags_are_normalized() -> None:
    enriched = Enrichment.model_validate({**result(), "tags": [" SDK ", "Async", "Software"]})
    assert enriched.summary == "Nova released an SDK. It supports asynchronous requests."
    assert enriched.tags == ("sdk", "async", "software")


@pytest.mark.parametrize(
    "change",
    [
        {"category": "Policy & Governance"},
        {"category": "unknown"},
        {"extra": True},
        {"summary_sentences": ["Only one sentence."]},
        {"summary_sentences": ["A.", "B.", "C.", "D."]},
        {"summary_sentences": ["A sentence. Another sentence.", "The final sentence."]},
        {"summary_sentences": ["No punctuation", "The final sentence."]},
        {"tags": ["a", "b"]},
        {"tags": ["a", "b", "c", "d", "e", "f"]},
        {"tags": ["a", "A", "b"]},
        {"tags": ["", "a", "b"]},
        {"summary_sentences": [1, "A sentence."]},
    ],
)
def test_invalid_outputs_are_not_silently_repaired(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Enrichment.model_validate({**result(), **change})


@pytest.mark.parametrize("words,valid", [(100, True), (101, False)])
def test_exact_summary_word_boundary(words: int, valid: bool) -> None:
    value = {
        **result(),
        "summary_sentences": [" ".join(["word"] * (words - 2)) + ".", "Two words."],
    }
    if valid:
        assert len(Enrichment.model_validate(value).summary.split()) == words
    else:
        with pytest.raises(ValidationError, match="summary_word_limit"):
            Enrichment.model_validate(value)


def test_sentence_units_preserve_abbreviations_and_decimal_versions() -> None:
    value = {
        **result(),
        "summary_sentences": [
            "The U.S. company released Nova 1.25.",
            "Dr. Lee reported lower latency.",
        ],
    }
    assert len(Enrichment.model_validate(value).summary_sentences) == 2


@pytest.mark.parametrize("size", [1535, 1537])
def test_embedding_dimensions_are_exact(size: int) -> None:
    with pytest.raises(ValidationError):
        Vector(values=tuple([0.1] * size))


@pytest.mark.parametrize("invalid", [True, "0.1", float("nan"), float("inf")])
def test_embedding_rejects_invalid_components(invalid: object) -> None:
    with pytest.raises(ValidationError):
        Vector.model_validate({"values": [invalid] + [0.1] * 1535})


def test_embedding_is_nonzero() -> None:
    with pytest.raises(ValidationError, match="zero_embedding"):
        Vector(values=tuple([0.0] * 1536))
    assert len(Vector(values=tuple([0.1] * 1536)).values) == 1536
