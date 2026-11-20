import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx2
import pytest
from azure.ai.projects.aio import AIProjectClient
from chat_fakes import scripted_chat
from fakes import PROJECT_ENDPOINT, Credential
from openai import AsyncOpenAI
from pydantic import JsonValue, ValidationError
from test_baseline_budget import Recorder, approval, ready
from test_baseline_inputs import frozen_data, result_data
from test_baseline_publication import Service
from test_baseline_scoring import SNAPSHOT, frozen_with_snapshot
from test_baseline_workflow import ROOT_WORKER, bound_fixture, workflow_context
from test_budget import Clock

from agent_evaluation import native_rows
from agent_evaluation.baseline_budget import (
    BaselineApproval,
    BaselineBudget,
    BaselineRun,
    live_requests,
    operation_limits,
)
from agent_evaluation.baseline_capture import CaptureSession
from agent_evaluation.baseline_checks import FOOTER, WEB_FOOTER, check_answer
from agent_evaluation.baseline_inputs import (
    CASE_IDS,
    CASE_IDS_V2,
    CONTROL_IDS_V2,
    FIXTURE_SHA256,
    FIXTURE_V2,
    FIXTURE_V2_SHA256,
    METRICS,
    SEMANTIC_CASES_V2,
    BaselineCase,
    BaselineResult,
    CalibrationReceipt,
    CaseReceipt,
    ControlMeasurement,
    FrozenBaseline,
    WebResult,
    fixture_digest,
    load_fixture,
    load_fixture_v2,
    parse_document,
    suite_digest,
)
from agent_evaluation.baseline_ipc import PrivateCaptureProcess
from agent_evaluation.baseline_provenance import document_digest, evaluator_source_digest
from agent_evaluation.baseline_publication import (
    BaselinePublicationReceipt,
    BaselinePublicationRow,
    BaselinePublicationRowV2,
    BaselinePublisher,
)
from agent_evaluation.baseline_scoring import (
    BaselineCompletion,
    BaselineScorer,
    EvidenceSnapshot,
    TransientAnswer,
    observed_evidence_digest,
    web_judge_evidence,
)
from agent_evaluation.baseline_workflow import execute_workflow
from agent_evaluation.budget import MODEL_SNAPSHOT
from agent_evaluation.inputs import ROOT
from agent_evaluation.judge import JudgeTransport
from agent_evaluation.policy import EvaluationFailure

WEB = (
    WebResult(
        number=1,
        title="WEB_TITLE_CANARY",
        url="https://web.test/1",
        snippet="WEB_SNIPPET_CANARY: the authored service now runs in twelve regions.",
    ),
)
STORED = (EvidenceSnapshot(alias="s1", item=SNAPSHOT),)


def to_v2(data: dict[str, JsonValue]) -> dict[str, JsonValue]:
    data = copy.deepcopy(data)
    bindings, oracles, provenance = data["bindings"], data["oracles"], data["provenance"]
    assert isinstance(bindings, dict) and isinstance(oracles, dict)
    assert isinstance(provenance, dict) and isinstance(oracles["cases"], list)
    digest = suite_digest("v2")
    bindings["fixture_sha256"] = oracles["fixture_sha256"] = digest
    oracles["cases"].extend(
        {
            "case_id": case,
            "expected_outcome": "supported",
            "expected_coverage": "discovery",
            "required_aliases": [],
            "minimum_claims": claims,
            "expected_http_status": 200,
        }
        for case, claims in (("b13", 1), ("b14", 2))
    )
    binding_hash = document_digest(bindings)
    oracles["bindings_sha256"] = binding_hash
    provenance.update(
        fixture_sha256=digest,
        evaluator_source_sha256=evaluator_source_digest("v2"),
        suite_version="v2",
        bindings_sha256=binding_hash,
        oracle_sha256=document_digest(oracles),
    )
    data["suite_version"] = "v2"
    return data


def frozen_v2(base: FrozenBaseline | None = None) -> FrozenBaseline:
    value = frozen_with_snapshot() if base is None else base
    data = to_v2(value.model_dump(mode="json", by_alias=True))
    return parse_document(FrozenBaseline, json.dumps(data).encode())


def approval_v7(
    frozen: FrozenBaseline, now: datetime | None = None, profile: str = "baseline-14x10-v7"
) -> BaselineApproval:
    data = approval(frozen, now).model_dump(mode="json")
    data.update(limit_profile=profile, maximum_usd="100")
    return BaselineApproval.model_validate_json(json.dumps(data))


def web_receipt(
    frozen: FrozenBaseline,
    case: str,
    answer: str,
    evidence: tuple[EvidenceSnapshot, ...] = STORED,
    web: tuple[WebResult, ...] = WEB,
) -> CaseReceipt:
    return CaseReceipt.model_validate(
        {
            "case_id": case,
            "modality": "live_a2a",
            "outcome": "supported",
            "request_sha256": document_digest(frozen.request_document(case)),  # type: ignore[arg-type]
            "evidence_sha256": frozen.evidence_digest(case),  # type: ignore[arg-type]
            "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
            "http_status": 200,
            "tool_calls": 3,
            "evidence_items": len(evidence),
            "validated": True,
            "generation_calls": 2,
            "usage_observed_calls": 2,
            "input_tokens": 20,
            "output_tokens": 10,
            "elapsed_ms": 100,
            "user_preserved": True,
            "no_model_work_verified": False,
            "observed_evidence_sha256": observed_evidence_digest(evidence, web),
        }
    )


def web_answer(*, stored: bool = True, web: bool = True) -> str:
    lines = ["Stored authored observation. [1]"] if stored else []
    if web:
        lines += ["From the web:", "The authored service now runs in twelve regions. [W1]"]
    lines.append(WEB_FOOTER if web else FOOTER)
    if stored:
        lines.append("[1] " + str(SNAPSHOT["url"]))
    if web:
        lines.append("[W1] https://web.test/1")
    return "\n\n".join(lines)


def test_v2_fixture_extends_the_unchanged_v1_suite() -> None:
    legacy, fixture = load_fixture(), load_fixture_v2()
    assert fixture_digest() == FIXTURE_SHA256
    assert suite_digest("v2") == FIXTURE_V2_SHA256
    assert tuple(case.case_id for case in fixture.cases) == CASE_IDS_V2
    assert tuple(control.control_id for control in fixture.controls) == CONTROL_IDS_V2
    assert fixture.cases[:12] == legacy.cases and fixture.controls[:8] == legacy.controls
    assert fixture.thresholds == legacy.thresholds
    assert [control.label for control in fixture.controls[8:]] == ["supported", "unsupported"]
    for case, sources in zip(fixture.cases[12:], ("web", "stored_and_web"), strict=True):
        assert case.kind == "web" and case.evidence_sources == sources
        assert not case.item_aliases and case.filter_alias is None
        assert case.expected_outcome == "supported"
    assert all(value.url.startswith("https://") for value in fixture.web_control_results)


def test_v2_validation_command_is_content_free_and_network_free() -> None:
    probe = """
import sys
def audit(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise RuntimeError("unexpected_network")
sys.addaudithook(audit)
from agent_evaluation.__main__ import main
sys.argv = ["evaluation", "baseline-validate", "--suite", "v2"]
assert main() == 0
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT / "tools/agent-evaluation",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert (data["cases"], data["controls"], data["suite_version"]) == (14, 10, "v2")
    assert data["fixture_sha256"] == FIXTURE_V2_SHA256 and data["model_calls"] == 0
    assert "Juniper" not in result.stdout + result.stderr


def test_edited_v2_fixture_or_web_case_with_selection_fails(tmp_path: Path) -> None:
    path = tmp_path / "edited.json"
    path.write_bytes(FIXTURE_V2.read_bytes() + b"\n")
    with pytest.raises(EvaluationFailure, match="baseline_fixture_digest_mismatch"):
        load_fixture_v2(path)
    case = load_fixture_v2().cases[12].model_dump(mode="json")
    with pytest.raises(ValidationError):
        BaselineCase.model_validate({**case, "item_aliases": ["n1"]})
    with pytest.raises(ValidationError):
        BaselineCase.model_validate({**case, "evidence_sources": "stored"})
    with pytest.raises(ValidationError):
        WebResult(number=1, title="t", url="http://web.test/1", snippet="s")


def test_v1_documents_keep_their_exact_serialization() -> None:
    data = frozen_data()
    frozen = parse_document(FrozenBaseline, json.dumps(data).encode())
    assert frozen.model_dump(mode="json", by_alias=True) == data
    result = parse_document(BaselineResult, json.dumps(result_data()).encode())
    assert result.model_dump(mode="json") == result_data()
    assert "suite_version" not in json.dumps(data)
    assert "observed_evidence_sha256" not in result.model_dump_json()
    schema = json.dumps(native_rows.wire_schema(BaselinePublicationRow))
    assert '"b12"' in schema and '"b13"' not in schema
    assert '"b14"' in json.dumps(native_rows.wire_schema(BaselinePublicationRowV2))


def test_v2_web_cases_are_unconstrained_and_bound_to_their_profile() -> None:
    frozen = frozen_v2()
    assert frozen.suite_version == "v2" and len(frozen.oracles.cases) == 14
    request = frozen.request_document("b13")
    assert request["item_ids"] is None
    assert request["filters"] == {
        "source": None,
        "category": None,
        "tags": [],
        "from": None,
        "to": None,
    }
    assert frozen.evidence_digest("b14") == document_digest({"items": [], "pool_sha256": None})
    now = datetime.now(UTC)
    approval_v7(frozen).validate_execution(now, frozen)
    with pytest.raises(EvaluationFailure, match="stale_or_unapproved_baseline"):
        approval(frozen).validate_execution(now, frozen)
    legacy = frozen_with_snapshot()
    with pytest.raises(EvaluationFailure, match="stale_or_unapproved_baseline"):
        approval_v7(legacy).validate_execution(now, legacy)
    data = to_v2(legacy.model_dump(mode="json", by_alias=True))
    oracles = data["oracles"]
    assert isinstance(oracles, dict) and isinstance(oracles["cases"], list)
    row = oracles["cases"][13]
    assert isinstance(row, dict)
    row["minimum_claims"] = 1
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(FrozenBaseline, json.dumps(data).encode())
    data = to_v2(legacy.model_dump(mode="json", by_alias=True))
    data["suite_version"] = "v1"
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(FrozenBaseline, json.dumps(data).encode())


def result_v2() -> dict[str, object]:
    data = result_data()
    cases, provenance = data["cases"], data["provenance"]
    assert isinstance(cases, list) and isinstance(provenance, dict)
    for case in ("b13", "b14"):
        row = dict(cases[0])
        row.update(case_id=case, observed_evidence_sha256="4" * 64)
        cases.append(row)
    provenance["suite_version"] = "v2"
    data["suite_version"] = "v2"
    data["scores"] = [
        {"case_id": case, "metric_id": metric, "score": 0.5}
        for metric in METRICS
        for case in (CASE_IDS_V2 if metric == "contract_adherence" else SEMANTIC_CASES_V2)
    ]
    return data


def test_v2_result_masks_and_denominators_cover_fourteen_cases() -> None:
    result = parse_document(BaselineResult, json.dumps(result_v2()).encode())
    assert len(result.cases) == 14 and len(result.scores) == 34
    assert {row.case_id for row in result.scores if row.metric_id == "faithfulness"} == set(
        SEMANTIC_CASES_V2
    )
    data = result_v2()
    scores = data["scores"]
    assert isinstance(scores, list)
    data["scores"] = [row for row in scores if row != scores[8]]
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(BaselineResult, json.dumps(data).encode())
    data = result_v2()
    data["suite_version"] = "v1"
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(BaselineResult, json.dumps(data).encode())
    data = result_v2()
    cases = data["cases"]
    assert isinstance(cases, list)
    last = cases[-1]
    assert isinstance(last, dict)
    last.pop("observed_evidence_sha256")
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(BaselineResult, json.dumps(data).encode())


@pytest.mark.parametrize("case,stored", [("b13", False), ("b13", True), ("b14", True)])
def test_web_answers_matching_their_returned_results_pass(case: str, stored: bool) -> None:
    frozen = frozen_v2()
    value = web_answer(stored=stored)
    evidence = STORED if stored else ()
    result = check_answer(frozen, web_receipt(frozen, case, value, evidence), value, evidence, WEB)
    assert result.citation_valid and result.contract_valid
    assert {row.name for row in result.checks} >= {"web_claims", "canonical_citations"}
    assert "WEB_SNIPPET_CANARY" not in result.model_dump_json()


@pytest.mark.parametrize(
    "change",
    [
        "foreign_url",
        "renumbered",
        "extra_marker",
        "missing_reference",
        "stored_footer",
        "web_before_heading",
        "stored_after_web",
        "unlisted_result",
    ],
)
def test_web_citations_that_do_not_match_the_results_fail(change: str) -> None:
    frozen = frozen_v2()
    value = web_answer()
    web: tuple[WebResult, ...] = WEB
    if change == "foreign_url":
        value = value.replace("[W1] https://web.test/1", "[W1] https://web.test/other")
    elif change == "renumbered":
        value = value.replace("[W1]", "[W2]")
    elif change == "extra_marker":
        value = value.replace("regions. [W1]", "regions. [W1] [W2]")
    elif change == "missing_reference":
        value = value.replace("\n\n[W1] https://web.test/1", "")
    elif change == "stored_footer":
        value = value.replace(WEB_FOOTER, FOOTER)
    elif change == "web_before_heading":
        value = value.replace(
            "From the web:\n\nThe authored service now runs in twelve regions. [W1]",
            "The authored service now runs in twelve regions. [W1]\n\nFrom the web:",
        )
    elif change == "stored_after_web":
        lines = value.split("\n\n")
        value = "\n\n".join([*lines[:-2], lines[-1], lines[-2]])
    else:
        web = (*WEB, WEB[0].model_copy(update={"number": 2, "url": "https://web.test/2"}))
    result = check_answer(
        frozen, web_receipt(frozen, "b14", value, STORED, web), value, STORED, web
    )
    assert not result.citation_valid and not result.contract_valid


@pytest.mark.parametrize("case,stored,web", [("b13", True, False), ("b14", False, True)])
def test_web_case_without_required_evidence_kinds_fails_contract(
    case: str, stored: bool, web: bool
) -> None:
    frozen = frozen_v2()
    value = web_answer(stored=stored, web=web)
    evidence, results = (STORED if stored else ()), (WEB if web else ())
    result = check_answer(
        frozen, web_receipt(frozen, case, value, evidence, results), value, evidence, results
    )
    assert result.citation_valid and not result.contract_valid
    assert [row.passed for row in result.checks if row.name == "web_claims"] == [False]


def test_any_web_citation_fails_a_v2_stored_case_but_not_v1_checks() -> None:
    legacy = frozen_with_snapshot()
    frozen = frozen_v2(legacy)
    clean = (
        "Supported rendered observation. [1]\n\nSelection retrieval coverage: complete.\n\n"
        + FOOTER
        + "\n\n[1] "
        + str(SNAPSHOT["url"])
    )
    evidence = (EvidenceSnapshot(alias="n1", item=SNAPSHOT),)

    def receipt(value: FrozenBaseline, answer: str) -> CaseReceipt:
        from test_baseline_checks import receipt as checked

        return checked(value, "b01", answer)

    result = check_answer(frozen, receipt(frozen, clean), clean, evidence)
    assert result.contract_valid
    assert [row.passed for row in result.checks if row.name == "no_web_citation"] == [True]
    cited = clean.replace("observation. [1]", "observation. [1] [W1]")
    result = check_answer(frozen, receipt(frozen, cited), cited, evidence)
    assert result.citation_valid and not result.contract_valid
    assert [row.passed for row in result.checks if row.name == "no_web_citation"] == [False]
    legacy_result = check_answer(legacy, receipt(legacy, cited), cited, evidence)
    assert "no_web_citation" not in {row.name for row in legacy_result.checks}
    with pytest.raises(EvaluationFailure, match="baseline_check_binding_mismatch"):
        check_answer(frozen, receipt(frozen, clean), clean, evidence, WEB)


def test_changed_web_result_is_a_binding_failure_not_a_score() -> None:
    frozen = frozen_v2()
    value = web_answer()
    changed = (WEB[0].model_copy(update={"snippet": "changed"}),)
    with pytest.raises(EvaluationFailure, match="baseline_check_binding_mismatch"):
        check_answer(frozen, web_receipt(frozen, "b14", value), value, STORED, changed)


def test_web_case_judge_evidence_has_cited_summaries_and_web_snippets() -> None:
    frozen = frozen_v2()
    value = web_answer()
    answer = TransientAnswer(
        case_id="b14",
        answer=value,
        evidence=STORED,
        receipt=web_receipt(frozen, "b14", value),
        web_results=WEB,
    )
    evidence = answer.judge_evidence()
    assert evidence.startswith(json.dumps([SNAPSHOT], sort_keys=True, separators=(",", ":")))
    assert "Web search result [W1]\nTitle: WEB_TITLE_CANARY\nURL: https://web.test/1" in evidence
    assert "Snippet: WEB_SNIPPET_CANARY" in evidence
    assert "WEB_SNIPPET_CANARY" not in repr(answer)
    control = web_judge_evidence([], load_fixture_v2().web_control_results)
    assert control.startswith("Web search result [W1]") and "twelve regions" in control


@pytest.mark.parametrize(
    "profile,attempts,retries", [("baseline-14x10-v7", 80, 0), ("baseline-14x10-v8", 96, 16)]
)
async def test_v7_profile_admits_fourteen_live_requests_with_v6_bounds(
    profile: str, attempts: int, retries: int
) -> None:
    frozen = frozen_v2()
    approved = approval_v7(frozen, profile=profile)
    assert operation_limits("baseline-14x10-v7") == operation_limits("baseline-12x8-v6")
    assert live_requests("baseline-14x10-v7") == 14
    assert live_requests("baseline-12x8-v6") == 12
    with pytest.raises(ValueError, match="baseline_profile_cost_limit"):
        BaselineApproval.model_validate_json(
            json.dumps({**approved.model_dump(mode="json"), "maximum_usd": "10"})
        )
    budget = BaselineBudget(approved, frozen, persist=Recorder(), ready=ready)
    await budget.start()
    for case in CASE_IDS_V2:
        await budget.admit_agent(case)
    assert len(budget.agents) == 14
    assert budget.judge.limits.attempts == attempts
    assert budget.judge.limits.transport_retries == retries
    assert budget.receipt().embedding_dispatches_reserved == 14 * 24
    with pytest.raises(EvaluationFailure, match="baseline_agent_slot_consumed"):
        await budget.admit_agent("b14")
    legacy = frozen_with_snapshot()
    data = approval(legacy).model_dump(mode="json")
    data.update(limit_profile="baseline-12x8-v6", maximum_usd="100")
    budget = BaselineBudget(
        BaselineApproval.model_validate_json(json.dumps(data)),
        legacy,
        persist=Recorder(),
        ready=ready,
    )
    await budget.start()
    for case in CASE_IDS:
        await budget.admit_agent(case)
    with pytest.raises(EvaluationFailure, match="baseline_agent_slot_consumed"):
        await budget.admit_agent("b13")


def test_v2_publication_receipt_reports_fourteen_case_masks() -> None:
    def receipt(cases: int, semantic: int) -> dict[str, object]:
        return {
            "protocol": "baseline-v1",
            "outcome": "api_verified",
            "ui_verified": False,
            "cases": cases,
            "metric_reports": [
                {
                    "metric_id": metric,
                    "cases": cases if metric == "contract_adherence" else semantic,
                    "evaluation_id": "eval_" + metric,
                    "run_id": "run_" + metric,
                    "report_url": "https://ai.azure.com/build/evaluations/eval_"
                    + metric
                    + "/run/run_"
                    + metric,
                }
                for metric in METRICS
            ],
            "approval_sha256": "1" * 64,
            "results_sha256": "2" * 64,
            "model_calls": 0,
        }

    BaselinePublicationReceipt.model_validate_json(json.dumps(receipt(14, 10)))
    BaselinePublicationReceipt.model_validate_json(json.dumps(receipt(12, 8)))
    for cases, semantic in ((14, 8), (12, 10), (13, 9)):
        with pytest.raises(ValidationError):
            BaselinePublicationReceipt.model_validate_json(json.dumps(receipt(cases, semantic)))


async def test_v2_calibration_uses_authored_web_controls(tmp_path: Path) -> None:
    frozen = frozen_v2()
    clock = Clock()
    start = datetime.now(UTC)
    approved = approval_v7(frozen, start)
    raw = approved.model_dump_json().encode()
    run = BaselineRun(
        tmp_path / "run",
        raw,
        hashlib.sha256(raw).hexdigest(),
        frozen,
        registry=tmp_path / "registry",
    )
    budget = BaselineBudget(
        approved,
        frozen,
        persist=run.checkpoint,
        ready=ready,
        clock=clock,
        sleep=clock.sleep,
        now=lambda: start + timedelta(seconds=clock.now),
    )
    await budget.start()
    calls: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        control = len(calls) // 4
        calls.append(request)
        return scripted_chat(
            request, unsupported=control in (4, 5, 6, 7, 9), snapshot=MODEL_SNAPSHOT
        )

    async with AsyncOpenAI(
        base_url="https://evaluation-test.openai.azure.com/openai/v1",
        api_key="synthetic",
        max_retries=0,
        http_client=httpx2.AsyncClient(
            transport=JudgeTransport(
                "https://evaluation-test.openai.azure.com",
                "test-deployment",
                budget.judge,
                httpx2.MockTransport(respond),
            ),
            follow_redirects=False,
        ),
    ) as client:
        scorer = BaselineScorer(
            budget, run, BaselineCompletion(client, "test-deployment", budget.judge)
        )
        progress = await scorer.calibrate()
    assert progress.state == "calibrated" and len(progress.controls) == 10
    assert [row.score for row in progress.controls[8:]] == [1.0, 0.0]
    assert len(calls) == 40
    assert all("Web search result [W1]" in calls[index].content.decode() for index in (32, 36))
    assert not any("Web search result" in request.content.decode() for request in calls[:32])
    saved = (tmp_path / "run/partial-results.json").read_text()
    assert '"suite_version":"v2"' in saved.replace(" ", "")
    assert "Juniper" not in saved and "twelve regions" not in saved


V2_INVOKE = """
from newsloom_agent.research_models import ResearchReceipt as _Receipt
async def invoke_v2(settings, token, public, request, *, request_hook, response_hook,
        conversation=False):
    if not conversation:
        return await invoke(settings, token, public, request,
            request_hook=request_hook, response_hook=response_hook)
    assert request.item_ids is None and request.filters.source is None
    await request_hook(httpx.Request("POST", settings.resource_url,
        json={"method": "SendStreamingMessage"}))
    stored = "stored news announcement" in request.question
    cited = [UUID(int=1)] if stored else []
    parts = ["Authored bounded evidence. [1]"] if stored else []
    parts += ["From the web:", "Web authored observation. [W1]",
        "Evidence is limited to stored summaries and metadata and the cited web search "
        "results; full articles were not accessed."]
    if stored:
        parts.append("[1] " + snapshot(1)["url"])
    parts.append("[W1] https://web.test/canary")
    web = [{"number": 1, "title": "WEB_TITLE_CANARY", "url": "https://web.test/canary",
        "snippet": "WEB_SNIPPET_CANARY"}]
    receipt = _Receipt(outcome="supported", items=len(cited), user_preserved=True,
        validated=True, tool_calls=2, generation_calls=1, usage_observed_calls=1,
        input_tokens=10, output_tokens=5)
    await request_hook(httpx.Request("POST", settings.resource_url, json={"method":"GetTask"}))
    return ResearchInvocation("\\n\\n".join(parts), {}, receipt, {"follow_ups": [],
        "cited_item_ids": [str(i) for i in cited], "web_results": web})
"""


@pytest.mark.parametrize("mode", ["v7", "v9", "v9_reuse", "v9_calibration_fails"])
async def test_real_private_worker_runs_v2_web_cases_without_persisting_web_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    frozen = frozen_v2(bound_fixture())
    context = workflow_context()
    start = datetime.now(UTC)
    first = mode != "v7"
    approved = approval_v7(frozen, start, "baseline-14x10-v9" if first else "baseline-14x10-v7")
    reused: tuple[CalibrationReceipt, str] | None = None
    if mode == "v9_reuse":
        receipt = CalibrationReceipt(
            protocol="baseline-calibration-v1",
            suite_version="v2",
            approval_sha256="1" * 64,
            evaluator_source_sha256=frozen.provenance.evaluator_source_sha256,
            fixture_sha256=frozen.provenance.fixture_sha256,
            judge_deployment_sha256="0" * 64,
            model_snapshot=MODEL_SNAPSHOT,
            completed_at=start - timedelta(hours=1),
            controls=tuple(
                ControlMeasurement(
                    control_id=control.control_id,
                    label=control.label,
                    score=1.0 if control.label == "supported" else 0.0,
                    passed=True,
                    judge_attempts=4,
                )
                for control in load_fixture_v2().controls
            ),
        )
        reused = (receipt, "2" * 64)
    encoded = approved.model_dump_json().encode()
    run = BaselineRun(
        tmp_path / "run",
        encoded,
        hashlib.sha256(encoded).hexdigest(),
        frozen,
        registry=tmp_path / "registry",
    )
    clock = Clock()
    clock.now = time.monotonic()
    initial = clock.now
    budget = BaselineBudget(
        approved,
        frozen,
        persist=run.checkpoint,
        ready=ready,
        clock=clock,
        sleep=clock.sleep,
        now=lambda: start + timedelta(seconds=clock.now - initial),
    )
    await budget.start()
    calls: list[httpx2.Request] = []
    workers: list[PrivateCaptureProcess] = []
    enter = PrivateCaptureProcess.__aenter__
    worker = ROOT_WORKER.replace("w.sign_in_agent=sign;", V2_INVOKE + "\nw.sign_in_agent=sign;")
    worker = worker.replace("c.invoke_research=invoke;", "c.invoke_research=invoke_v2;")

    async def controlled_enter(self: PrivateCaptureProcess) -> PrivateCaptureProcess:
        assert len(calls) == (0 if first else 40)
        workers.append(self)
        self.command = (str(ROOT / ".venv/bin/python"), "-c", worker)
        return await enter(self)

    monkeypatch.setattr(PrivateCaptureProcess, "__aenter__", controlled_enter)

    def respond(request: httpx2.Request) -> httpx2.Response:
        control = (len(calls) + (40 if reused else 0)) // 4
        calls.append(request)
        return scripted_chat(
            request,
            unsupported=control in (4, 5, 6, 7, 9) or mode == "v9_calibration_fails",
            snapshot=MODEL_SNAPSHOT,
        )

    service = Service()
    env = {
        **context.environment,
        "MCP_TENANT_ID": context.environment["AGENT_TENANT_ID"],
        "MCP_API_CLIENT_ID": str(UUID(int=101)),
        "AGENT_API_CLIENT_ID": str(UUID(int=102)),
        "MCP_PUBLIC_CLIENT_ID": str(UUID(int=103)),
        "AGENT_PUBLIC_CLIENT_ID": str(UUID(int=104)),
        "MCP_RESOURCE_URL": "https://mcp.test/mcp",
        "AGENT_RESOURCE_URL": "https://agent.test/a2a",
    }
    async with (
        AsyncOpenAI(
            base_url="https://evaluation-test.openai.azure.com/openai/v1",
            api_key="synthetic",
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=JudgeTransport(
                    "https://evaluation-test.openai.azure.com",
                    "test-deployment",
                    budget.judge,
                    httpx2.MockTransport(respond),
                )
            ),
        ) as client,
        Credential() as credential,
        AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=credential,
            allow_preview=True,
            retry_total=0,
            redirect_max=0,
        ) as project,
    ):
        operation = execute_workflow(
            budget,
            run,
            BaselineCompletion(client, "test-deployment", budget.judge),
            lambda: CaptureSession(budget, run, env),
            project,
            context,
            publication_transport=httpx2.MockTransport(service.respond),
            calibration=reused,
        )
        if mode == "v9_calibration_fails":
            with pytest.raises(EvaluationFailure, match="baseline_calibration_failed"):
                await operation
            assert budget.halted and len(budget.agents) == 14 and len(calls) == 4
            assert not run.load_scoring_progress().scores and not service.requests
            assert not (tmp_path / "run/calibration.json").exists()
            return
        result = await operation
    rows = BaselinePublisher(budget, run, run.load_results(), context).rows()
    if first:
        assert {row.model_dump()["calibration"] for row in rows} == {
            "reused" if reused else "fresh"
        }
        assert (tmp_path / "run/calibration.json").exists() == (reused is None)
        assert run.load_results().calibration_reuse_sha256 == (reused[1] if reused else None)
    assert result["cases"] == 14 and result["scores"] == 34 and result["reports"] == 3
    assert result["semantic_gate_passed"] and result["deterministic_gates_passed"]
    offset = 40 if reused else 0
    assert len(calls) == 80 - offset and len(budget.agents) == 14
    assert budget.counts["task_reads"] == 12
    assert workers[0].closed
    assert all("WEB_SNIPPET_CANARY" in calls[index - offset].content.decode() for index in (72, 76))
    assert not any(
        "WEB_SNIPPET_CANARY" in request.content.decode() for request in calls[: 72 - offset]
    )
    saved_result = run.load_results()
    assert saved_result.suite_version == "v2"
    assert all(
        (row.observed_evidence_sha256 is not None) == (row.case_id in ("b13", "b14"))
        for row in saved_result.cases
    )
    for path in (tmp_path / "run").iterdir():
        if path.is_file():
            saved = path.read_bytes()
            for canary in (
                b"WEB_SNIPPET_CANARY",
                b"WEB_TITLE_CANARY",
                b"web.test/canary",
                b"Authored bounded evidence",
                b"TOKEN_CANARY",
            ):
                assert canary not in saved


def reusable_receipt(frozen: FrozenBaseline, completed_at: datetime) -> CalibrationReceipt:
    return CalibrationReceipt(
        protocol="baseline-calibration-v1",
        suite_version="v2",
        approval_sha256="1" * 64,
        evaluator_source_sha256=frozen.provenance.evaluator_source_sha256,
        fixture_sha256=frozen.provenance.fixture_sha256,
        judge_deployment_sha256="0" * 64,
        model_snapshot=MODEL_SNAPSHOT,
        completed_at=completed_at,
        controls=tuple(
            ControlMeasurement(
                control_id=control.control_id,
                label=control.label,
                score=1.0 if control.label == "supported" else 0.0,
                passed=True,
                judge_attempts=4,
            )
            for control in load_fixture_v2().controls
        ),
    )


@pytest.mark.parametrize(
    "change,valid",
    [
        ({}, True),
        ({"evaluator_source_sha256": "3" * 64}, False),
        ({"fixture_sha256": "3" * 64}, False),
        ({"model_snapshot": "other"}, False),
        ({"completed_at": "late"}, False),
        ({"completed_at": "stale"}, False),
    ],
)
def test_calibration_reuse_requires_an_exact_recent_binding(
    change: dict[str, object], valid: bool
) -> None:
    from agent_evaluation.baseline_runner import verify_reusable

    frozen = frozen_v2()
    now = datetime.now(UTC)
    approved_at = now - timedelta(minutes=5)
    completed = {"late": now, "stale": now - timedelta(hours=24, seconds=1)}.get(
        str(change.get("completed_at")), now - timedelta(hours=2)
    )
    data = reusable_receipt(frozen, completed).model_dump(mode="json")
    data.update({key: value for key, value in change.items() if key != "completed_at"})
    receipt = CalibrationReceipt.model_validate_json(json.dumps(data))
    if valid:
        verify_reusable(receipt, frozen, approved_at, now)
    else:
        with pytest.raises(EvaluationFailure, match="baseline_calibration_reuse_mismatch"):
            verify_reusable(receipt, frozen, approved_at, now)


def test_calibration_reuse_is_v9_only_and_receipts_must_pass() -> None:
    frozen = frozen_v2()
    data = approval_v7(frozen).model_dump(mode="json")
    with pytest.raises(ValidationError, match="baseline_calibration_reuse_profile"):
        BaselineApproval.model_validate_json(
            json.dumps({**data, "calibration_reuse_sha256": "2" * 64})
        )
    BaselineApproval.model_validate_json(
        json.dumps(
            {**data, "limit_profile": "baseline-14x10-v9", "calibration_reuse_sha256": "2" * 64}
        )
    )
    receipt = reusable_receipt(frozen, datetime.now(UTC)).model_dump(mode="json")
    receipt["controls"][0]["passed"] = False
    with pytest.raises(ValidationError, match="invalid_baseline_calibration_receipt"):
        CalibrationReceipt.model_validate_json(json.dumps(receipt))
