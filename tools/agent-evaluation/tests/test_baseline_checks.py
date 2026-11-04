import hashlib
import json

import pytest
from test_baseline_budget import case_receipt
from test_baseline_scoring import SNAPSHOT, frozen_with_snapshot

from agent_evaluation.baseline_checks import FOOTER, check_answer
from agent_evaluation.baseline_inputs import CaseReceipt, FrozenBaseline
from agent_evaluation.baseline_scoring import EvidenceSnapshot
from agent_evaluation.policy import EvaluationFailure


def receipt(frozen: FrozenBaseline, case: str, answer: str | None) -> CaseReceipt:
    value = case_receipt(frozen, case)
    return value.model_copy(
        update={
            "answer_sha256": None
            if answer is None
            else hashlib.sha256(answer.encode()).hexdigest(),
            "evidence_items": 0 if case in ("b09", "b11", "b12") else 1,
        }
    )


def answer(*, claims: int = 1, coverage: str = "complete", url: str | None = None) -> str:
    body = "\n\n".join(
        f"Supported rendered observation {index + 1}. [1]" for index in range(claims)
    )
    return (
        body
        + "\n\nSelection retrieval coverage: "
        + coverage
        + ".\n\n"
        + FOOTER
        + "\n\n[1] "
        + str(SNAPSHOT["url"] if url is None else url)
    )


def test_citation_membership_is_not_claimed_as_semantic_support() -> None:
    frozen = frozen_with_snapshot()
    value = answer()
    result = check_answer(
        frozen,
        receipt(frozen, "b01", value),
        value,
        (EvidenceSnapshot(alias="n1", item=SNAPSHOT),),
    )
    assert result.citation_valid and result.contract_valid
    assert [row.metric_id for row in result.metric_scores()] == [
        "citation_validity",
        "contract_adherence",
    ]
    assert all(row.score == 1 for row in result.metric_scores())
    encoded = result.model_dump_json()
    assert "Supported rendered" not in encoded and "example.com" not in encoded


@pytest.mark.parametrize(
    "change",
    ["foreign_url", "foreign_marker", "missing_footer", "duplicate_reference", "wrong_coverage"],
)
def test_changed_visible_citation_or_contract_is_failed_quality(change: str) -> None:
    frozen = frozen_with_snapshot()
    value = answer()
    if change == "foreign_url":
        value = answer(url="https://not-approved.invalid/news")
    elif change == "foreign_marker":
        value = value.replace("observation 1. [1]", "observation 1. [99]")
    elif change == "missing_footer":
        value = value.replace(FOOTER, "")
    elif change == "duplicate_reference":
        value += "\n\n[1] " + str(SNAPSHOT["url"])
    else:
        value = answer(coverage="partial")
    result = check_answer(
        frozen,
        receipt(frozen, "b01", value),
        value,
        (EvidenceSnapshot(alias="n1", item=SNAPSHOT),),
    )
    assert not result.contract_valid
    assert result.metric_scores()[-1].score == 0
    if change != "wrong_coverage":
        assert not result.citation_valid


def test_minimum_counts_rendered_cited_statements_not_internal_tool_traces() -> None:
    frozen = frozen_with_snapshot()
    one = answer()
    missing = check_answer(
        frozen,
        receipt(frozen, "b02", one),
        one,
        (EvidenceSnapshot(alias="n1", item=SNAPSHOT),),
    )
    assert missing.citation_valid and not missing.contract_valid
    two = answer(claims=2)
    complete = check_answer(
        frozen,
        receipt(frozen, "b02", two),
        two,
        (EvidenceSnapshot(alias="n1", item=SNAPSHOT),),
    )
    assert complete.contract_valid


def test_partial_selection_and_no_match_remain_distinct() -> None:
    frozen = frozen_with_snapshot()
    missing_id = next(item.item_id for item in frozen.bindings.items if not item.present)
    value = (
        "Supported observation. [1]\n\nLimitation: a selected item is missing.\n\n"
        "Selection retrieval coverage: partial.\n\nMissing selected items: "
        + str(missing_id)
        + ".\n\n"
        + FOOTER
        + "\n\n[1] "
        + str(SNAPSHOT["url"])
    )
    result = check_answer(
        frozen,
        receipt(frozen, "b07", value),
        value,
        (EvidenceSnapshot(alias="n1", item=SNAPSHOT),),
    )
    assert result.contract_valid
    no_match = "Limitation: no matching stored evidence.\n\n" + FOOTER
    result = check_answer(frozen, receipt(frozen, "b09", no_match), no_match, ())
    assert result.contract_valid and result.citation_valid is None
    assert len(result.metric_scores()) == 1


def test_expected_denial_has_no_invented_answer_or_semantic_zero() -> None:
    frozen = frozen_with_snapshot()
    result = check_answer(frozen, receipt(frozen, "b11", None), None, ())
    assert result.contract_valid and result.citation_valid is None
    assert result.metric_scores()[0].metric_id == "contract_adherence"


def test_unbound_answer_or_snapshot_is_not_a_valid_zero_score() -> None:
    frozen = frozen_with_snapshot()
    value = answer()
    with pytest.raises(EvaluationFailure, match="baseline_check_binding_mismatch"):
        check_answer(
            frozen,
            receipt(frozen, "b01", value),
            value + "changed",
            (EvidenceSnapshot(alias="n1", item=SNAPSHOT),),
        )
    changed = dict(SNAPSHOT)
    changed["summary"] = "PRIVATE_CHANGED_CONTENT"
    with pytest.raises(EvaluationFailure, match="baseline_check_evidence_mismatch"):
        check_answer(
            frozen,
            receipt(frozen, "b01", value),
            value,
            (EvidenceSnapshot(alias="n1", item=changed),),
        )
    assert "PRIVATE_CHANGED_CONTENT" not in json.dumps(frozen.model_dump(mode="json"))
