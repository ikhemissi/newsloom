import hashlib
import re
from typing import Final, Literal

from pydantic import StrictBool

from agent_evaluation.baseline_inputs import (
    WEB_CASES,
    CaseId,
    CaseReceipt,
    FrozenBaseline,
    MetricScore,
    WebResult,
    semantic_cases,
)
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.baseline_scoring import (
    EvidenceSnapshot,
    observed_evidence_digest,
    observed_evidence_valid,
)
from agent_evaluation.inputs import StrictModel
from agent_evaluation.policy import EvaluationFailure

FOOTER: Final = (
    "Evidence is limited to stored summaries and metadata; "
    "full articles and web search were not accessed."
)
WEB_FOOTER: Final = (
    "Evidence is limited to stored summaries and metadata and the cited web search "
    "results; full articles were not accessed."
)
WEB_HEADING: Final = "From the web:"
REFERENCE: Final = re.compile(r"\[([1-9][0-9]?)\] (https://\S+)\Z")
WEB_REFERENCE: Final = re.compile(r"\[W([1-9][0-9]?)\] (https://\S+)\Z")
MARKER: Final = re.compile(r"\[([0-9]+)\]")
WEB_MARKER: Final = re.compile(r"\[W([0-9]+)\]")
CITED_STATEMENT: Final = re.compile(r"(?:\[[1-9][0-9]*\](?:\s+|$))+$")
WEB_CITED_STATEMENT: Final = re.compile(r"(?:\[W?[1-9][0-9]*\](?:\s+|$))+$")
WEB_ONLY_STATEMENT: Final = re.compile(r"(?:\[W[1-9][0-9]*\](?:\s+|$))+$")
CheckName = Literal[
    "identity",
    "validated_receipt",
    "outcome",
    "canonical_footer",
    "canonical_citations",
    "citation_coverage",
    "statement_minimum",
    "selection_coverage",
    "missing_selection",
    "limited_explanation",
    "expected_denial",
    "no_web_citation",
    "web_claims",
]


class Check(StrictModel):
    name: CheckName
    passed: StrictBool


class DeterministicResult(StrictModel):
    case_id: CaseId
    checks: tuple[Check, ...]
    citation_valid: StrictBool | None
    contract_valid: StrictBool

    def metric_scores(self) -> tuple[MetricScore, ...]:
        contract = MetricScore(
            case_id=self.case_id, metric_id="contract_adherence", score=float(self.contract_valid)
        )
        if self.citation_valid is None:
            return (contract,)
        return (
            MetricScore(
                case_id=self.case_id,
                metric_id="citation_validity",
                score=float(self.citation_valid),
            ),
            contract,
        )


def check_answer(
    frozen: FrozenBaseline,
    receipt: CaseReceipt,
    answer: str | None,
    evidence: tuple[EvidenceSnapshot, ...],
    web_results: tuple[WebResult, ...] = (),
) -> DeterministicResult:
    oracle = next(
        (value for value in frozen.oracles.cases if value.case_id == receipt.case_id), None
    )
    if oracle is None:
        raise EvaluationFailure("baseline_check_case_unknown")
    web_case = receipt.case_id in WEB_CASES
    if (
        receipt.request_sha256 != document_digest(frozen.request_document(receipt.case_id))
        or receipt.evidence_sha256 != frozen.evidence_digest(receipt.case_id)
        or receipt.answer_sha256
        != (None if answer is None else hashlib.sha256(answer.encode()).hexdigest())
        or len({item.alias for item in evidence}) != len(evidence)
        or (
            (
                not observed_evidence_valid(evidence, web_results)
                or receipt.observed_evidence_sha256
                != observed_evidence_digest(evidence, web_results)
            )
            if web_case
            else (
                {item.alias for item in evidence} != set(oracle.required_aliases)
                or bool(web_results)
            )
        )
    ):
        raise EvaluationFailure("baseline_check_binding_mismatch")
    bindings = {item.alias: item for item in frozen.bindings.items}
    for snapshot in () if web_case else evidence:
        binding = bindings.get(snapshot.alias)
        if (
            binding is None
            or document_digest(snapshot.item) != binding.fingerprint
            or snapshot.item.get("id") != str(binding.item_id)
        ):
            raise EvaluationFailure("baseline_check_evidence_mismatch")
    values: list[Check] = []

    def record(name: CheckName, passed: bool) -> None:
        values.append(Check(name=name, passed=passed))

    if oracle.expected_outcome == "denied":
        passed = (
            receipt.outcome == "denied"
            and receipt.http_status == oracle.expected_http_status
            and answer is None
            and not evidence
            and receipt.tool_calls == receipt.generation_calls == 0
        )
        record("expected_denial", passed)
        return DeterministicResult(
            case_id=receipt.case_id,
            checks=tuple(values),
            citation_valid=None,
            contract_valid=passed,
        )
    if answer is None or receipt.outcome == "denied":
        raise EvaluationFailure("baseline_check_completed_answer_required")
    if not 0 < len(answer.encode()) <= 16384:
        raise EvaluationFailure("baseline_check_answer_limit")
    record("identity", receipt.user_preserved)
    record("validated_receipt", receipt.validated and receipt.evidence_items == len(evidence))
    record("outcome", receipt.outcome == oracle.expected_outcome)
    footer = WEB_FOOTER if web_case and web_results else FOOTER
    position = answer.rfind(footer)
    record("canonical_footer", position >= 0)
    body = answer[:position].rstrip() if position >= 0 else answer
    tail = answer[position + len(footer) :].strip() if position >= 0 else ""
    expected_urls: set[str] = set()
    for snapshot in evidence:
        url = snapshot.item.get("url")
        if not isinstance(url, str):
            raise EvaluationFailure("baseline_check_evidence_url_invalid")
        expected_urls.add(url)
    references: dict[int, str] = {}
    web_references: dict[int, str] = {}
    citation_valid = position >= 0
    for line in () if not tail else tail.split("\n\n"):
        match = REFERENCE.fullmatch(line)
        if match is None:
            web_match = WEB_REFERENCE.fullmatch(line) if web_case else None
            if web_match is None or int(web_match[1]) in web_references:
                citation_valid = False
            if web_match is not None:
                web_references[int(web_match[1])] = web_match[2]
            continue
        number, url = int(match[1]), match[2]
        if number in references or url not in expected_urls:
            citation_valid = False
        if web_case and (
            web_references or number > len(evidence) or evidence[number - 1].item.get("url") != url
        ):
            citation_valid = False
        references[number] = url
    raw_markers = MARKER.findall(body)
    if any(len(value) > 2 for value in raw_markers):
        citation_valid = False
    markers = {int(value) for value in raw_markers if len(value) <= 2}
    if (
        set(references) != set(range(1, len(references) + 1))
        or markers - references.keys()
        or references.keys() - markers
    ):
        citation_valid = False
    paragraphs = body.split("\n\n")
    prefixes = ("Limitation: ", "Selection retrieval coverage: ", "Missing selected items: ")
    statement = WEB_CITED_STATEMENT if web_case else CITED_STATEMENT
    if web_case:
        raw_web = WEB_MARKER.findall(body)
        if (
            any(len(value) > 2 for value in raw_web)
            or {int(value) for value in raw_web if len(value) <= 2} != web_references.keys()
            or web_references != {value.number: value.url for value in web_results}
        ):
            citation_valid = False
        headings = [index for index, value in enumerate(paragraphs) if value == WEB_HEADING]
        start = headings[0] if headings else len(paragraphs)
        web_only = [
            WEB_ONLY_STATEMENT.search(value.rstrip()) is not None and not MARKER.search(value)
            for value in paragraphs
        ]
        if (
            len(headings) > 1
            or any(web_only[:start])
            or (headings and not any(web_only[start + 1 :]))
            or any(
                not web_only[index] and not paragraphs[index].startswith(prefixes)
                for index in range(start + 1, len(paragraphs))
            )
        ):
            citation_valid = False
    statements = [
        value
        for value in paragraphs
        if not value.startswith(prefixes) and statement.search(value.rstrip()) is not None
    ]
    record("canonical_citations", citation_valid)
    record("citation_coverage", set(references.values()) == expected_urls)
    record("statement_minimum", len(statements) >= oracle.minimum_claims)
    request = frozen.request_document(receipt.case_id)
    selection = request["item_ids"]
    template = next(case for case in frozen.fixture().cases if case.case_id == receipt.case_id)
    missing_ids = [
        str(item.item_id)
        for item in frozen.bindings.items
        if item.alias in template.item_aliases and not item.present
    ]
    if selection is not None:
        coverage = "Selection retrieval coverage: " + oracle.expected_coverage + "."
        missing = (
            "" if not missing_ids else "\n\nMissing selected items: " + ", ".join(missing_ids) + "."
        )
        record("selection_coverage", body.endswith(coverage + missing))
        record(
            "missing_selection",
            ("Missing selected items: " not in body)
            if not missing_ids
            else body.endswith(missing.lstrip()),
        )
    if oracle.expected_outcome in ("limited", "no_match"):
        record("limited_explanation", any(value.startswith("Limitation: ") for value in paragraphs))
    if web_case:
        web_claims = any(WEB_MARKER.search(value) for value in statements)
        stored_claims = any(MARKER.search(value) for value in statements)
        record(
            "web_claims",
            web_claims and (stored_claims or template.evidence_sources == "web"),
        )
    elif frozen.suite_version != "v1":
        record(
            "no_web_citation",
            WEB_MARKER.search(answer) is None
            and WEB_HEADING not in answer.split("\n\n")
            and WEB_FOOTER not in answer,
        )
    return DeterministicResult(
        case_id=receipt.case_id,
        checks=tuple(values),
        citation_valid=(
            citation_valid if receipt.case_id in semantic_cases(frozen.suite_version) else None
        ),
        contract_valid=all(value.passed for value in values),
    )
