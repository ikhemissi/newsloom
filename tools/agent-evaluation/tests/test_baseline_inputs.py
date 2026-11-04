import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_baseline_provenance import provenance, runtime

from agent_evaluation.baseline_inputs import (
    CASE_IDS,
    CONTROL_IDS,
    FIXTURE,
    FIXTURE_SHA256,
    METRICS,
    SEMANTIC_CASES,
    BaselineResult,
    FrozenBaseline,
    MetricScore,
    Oracles,
    PrivateBindings,
    fixture_digest,
    load_fixture,
    parse_document,
)
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.policy import EvaluationFailure


def frozen_data() -> dict[str, object]:
    fixture = load_fixture()
    item_aliases = ("n1", "n2", "n3", "n_missing")
    bindings = PrivateBindings.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_sha256": fixture_digest(),
                "actor_sha256": "1" * 64,
                "context_sha256": "2" * 64,
                "accepted_runtime": runtime().model_dump(mode="json"),
                "items": [
                    {
                        "alias": alias,
                        "item_id": str(UUID(int=index + 1)),
                        "present": alias != "n_missing",
                        "fingerprint": str(index + 1) * 64 if alias != "n_missing" else None,
                    }
                    for index, alias in enumerate(item_aliases)
                ],
                "filters": [
                    {
                        "alias": alias,
                        "source": None,
                        "category": None,
                        "tags": [],
                        "from": "2030-01-01T00:00:00Z",
                        "to": "2030-02-01T00:00:00Z",
                        "pool_aliases": pool,
                        "pool_sha256": str(index + 1) * 64,
                    }
                    for index, (alias, pool) in enumerate(
                        (("f1", ["n1", "n2"]), ("f2", ["n3"]), ("f3", []))
                    )
                ],
            }
        )
    )
    binding_hash = document_digest(bindings.model_dump(mode="json", by_alias=True))
    pools = {value.alias: value.pool_aliases for value in bindings.filters}
    oracles = Oracles.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_sha256": fixture_digest(),
                "bindings_sha256": binding_hash,
                "cases": [
                    {
                        "case_id": case.case_id,
                        "expected_outcome": case.expected_outcome,
                        "expected_coverage": case.expected_coverage,
                        "required_aliases": [
                            alias
                            for alias in (
                                case.item_aliases
                                if case.filter_alias is None
                                else pools[case.filter_alias]
                            )
                            if alias != "n_missing"
                        ]
                        if case.expected_outcome != "denied"
                        else [],
                        "minimum_claims": (
                            2
                            if case.case_id == "b02"
                            else int(case.expected_outcome not in ("no_match", "denied"))
                        ),
                        "expected_http_status": 401 if case.expected_outcome == "denied" else 200,
                    }
                    for case in fixture.cases
                ],
            }
        )
    )
    value = provenance().model_copy(
        update={
            "bindings_sha256": binding_hash,
            "oracle_sha256": document_digest(oracles.model_dump(mode="json")),
        }
    )
    return {
        "protocol": "baseline-v1",
        "provenance": value.model_dump(mode="json"),
        "bindings": bindings.model_dump(mode="json", by_alias=True),
        "oracles": oracles.model_dump(mode="json"),
    }


def result_data() -> dict[str, object]:
    fixture = load_fixture()
    return {
        "protocol": "baseline-v1",
        "provenance": provenance().model_dump(mode="json"),
        "frozen_sha256": "e" * 64,
        "cases": [
            {
                "case_id": case.case_id,
                "modality": "live_a2a",
                "outcome": case.expected_outcome,
                "request_sha256": "1" * 64,
                "evidence_sha256": "2" * 64,
                "answer_sha256": None if case.expected_outcome == "denied" else "3" * 64,
                "http_status": 401 if case.expected_outcome == "denied" else 200,
                "tool_calls": 0 if case.expected_outcome == "denied" else 1,
                "evidence_items": 0 if case.expected_outcome == "denied" else 1,
                "validated": case.expected_outcome != "denied",
                "generation_calls": 0 if case.expected_outcome == "denied" else 2,
                "usage_observed_calls": 0 if case.expected_outcome == "denied" else 2,
                "input_tokens": 0 if case.expected_outcome == "denied" else 20,
                "output_tokens": 0 if case.expected_outcome == "denied" else 10,
                "elapsed_ms": 100,
                "user_preserved": case.expected_outcome != "denied",
                "no_model_work_verified": False,
            }
            for case in fixture.cases
        ],
        "scores": [
            {"case_id": case, "metric_id": metric, "score": 0.125}
            for metric in METRICS
            for case in (CASE_IDS if metric == "contract_adherence" else SEMANTIC_CASES)
        ],
    }


def test_frozen_fixture_is_authored_versioned_and_exact() -> None:
    fixture = load_fixture()
    assert tuple(case.case_id for case in fixture.cases) == CASE_IDS
    assert tuple(control.control_id for control in fixture.controls) == CONTROL_IDS
    assert fixture_digest() == FIXTURE_SHA256
    assert len(fixture.offline_controls) == 4
    assert fixture.thresholds.macro_min == 0.9


def test_baseline_validation_command_is_content_free_and_network_free() -> None:
    probe = """
import sys
def audit(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise RuntimeError("unexpected_network")
sys.addaudithook(audit)
from agent_evaluation.__main__ import main
sys.argv = ["evaluation", "baseline-validate"]
assert main() == 0
assert "deepeval.metrics" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=FIXTURE.parents[1] / "tools/agent-evaluation",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["cases"] == 12 and data["controls"] == 8
    assert data["model_calls"] == 0 and data["protocol"] == "baseline-v1"
    assert load_fixture().control_evidence not in result.stdout + result.stderr


def test_frozen_private_binding_and_oracle_are_content_free() -> None:
    value = parse_document(FrozenBaseline, json.dumps(frozen_data()).encode())
    encoded = value.model_dump_json()
    for field in ("question", "answer", "summary", "evidence", "reason", "token"):
        assert f'"{field}":' not in encoded


def test_valid_low_scores_are_not_rewritten_or_dropped() -> None:
    result = parse_document(BaselineResult, json.dumps(result_data()).encode())
    assert len(result.cases) == 12 and len(result.scores) == 28
    assert all(value.score == 0.125 for value in result.scores)
    assert {row.case_id for row in result.scores if row.metric_id == "faithfulness"} == set(
        SEMANTIC_CASES
    )


def test_result_is_bound_to_frozen_requests_evidence_and_oracles() -> None:
    frozen = parse_document(FrozenBaseline, json.dumps(frozen_data()).encode())
    data = result_data()
    data["provenance"] = frozen.provenance.model_dump(mode="json")
    data["frozen_sha256"] = document_digest(frozen.model_dump(mode="json", by_alias=True))
    cases = data["cases"]
    assert isinstance(cases, list)
    for row in cases:
        case_id = row["case_id"]
        row["request_sha256"] = document_digest(frozen.request_document(case_id))
        row["evidence_sha256"] = frozen.evidence_digest(case_id)
    result = parse_document(BaselineResult, json.dumps(data).encode())
    result.verify_frozen(frozen)
    altered = result.model_copy(update={"frozen_sha256": "0" * 64})
    with pytest.raises(EvaluationFailure, match="baseline_result_binding_mismatch"):
        altered.verify_frozen(frozen)
    changed = result.cases[0].model_copy(update={"request_sha256": "0" * 64})
    altered = result.model_copy(update={"cases": (changed, *result.cases[1:])})
    with pytest.raises(EvaluationFailure, match="baseline_result_binding_mismatch"):
        altered.verify_frozen(frozen)


def test_frozen_request_hash_matches_actual_root_research_contract() -> None:
    frozen = parse_document(FrozenBaseline, json.dumps(frozen_data()).encode())
    probe = """
import hashlib, json, sys
from newsloom_agent.research_models import ResearchRequest
data = json.loads(sys.stdin.buffer.read())
result = []
for value in data:
    parsed = ResearchRequest.model_validate_json(json.dumps(value))
    canonical = parsed.model_dump(mode="json", by_alias=True)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    result.append(hashlib.sha256(encoded).hexdigest())
print(json.dumps(result))
"""
    requests = [frozen.request_document(case.case_id) for case in load_fixture().cases]
    root = FIXTURE.parents[1]
    result = subprocess.run(
        [str(root / ".venv/bin/python"), "-c", probe],
        cwd=root,
        input=json.dumps(requests),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [document_digest(value) for value in requests]


def test_edited_same_version_fixture_fails_before_use(tmp_path: Path) -> None:
    path = tmp_path / "edited.json"
    path.write_bytes(FIXTURE.read_bytes() + b"\n")
    with pytest.raises(EvaluationFailure, match="baseline_fixture_digest_mismatch"):
        load_fixture(path)


@pytest.mark.parametrize("section", ["bindings", "oracles", "provenance"])
def test_raw_content_is_not_an_allowed_metadata_field(section: str) -> None:
    data = frozen_data()
    child = data[section]
    assert isinstance(child, dict)
    child["summary"] = "PRIVATE-CONTENT-CANARY"
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(FrozenBaseline, json.dumps(data).encode())


@pytest.mark.parametrize("field", ["fixture_sha256", "bindings_sha256", "oracle_sha256"])
def test_changed_provenance_digests_fail(field: str) -> None:
    data = frozen_data()
    child = data["provenance"]
    assert isinstance(child, dict)
    child[field] = "0" * 64
    with pytest.raises((EvaluationFailure, ValidationError)):
        FrozenBaseline.model_validate_json(json.dumps(data))


def test_changed_oracle_cannot_be_admitted_by_just_rehashing_it() -> None:
    data = frozen_data()
    oracle = data["oracles"]
    assert isinstance(oracle, dict) and isinstance(oracle["cases"], list)
    oracle["cases"][0]["expected_outcome"] = "no_match"
    proof = data["provenance"]
    assert isinstance(proof, dict)
    proof["oracle_sha256"] = document_digest(oracle)
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(FrozenBaseline, json.dumps(data).encode())


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "foreign", "reordered"])
def test_case_set_drift_is_rejected(mutation: str) -> None:
    data = result_data()
    cases = data["cases"]
    assert isinstance(cases, list)
    if mutation == "duplicate":
        cases[-1] = copy.deepcopy(cases[0])
    elif mutation == "missing":
        cases.pop()
    elif mutation == "foreign":
        cases[0]["case_id"] = "not-a-baseline-case"
    else:
        cases.reverse()
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(BaselineResult, json.dumps(data).encode())


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -0.01, 1.01, "0.5"])
def test_scores_are_strict_finite_numbers(value: object) -> None:
    with pytest.raises(ValidationError):
        MetricScore.model_validate({"case_id": "b01", "metric_id": "faithfulness", "score": value})


def test_inapplicability_and_denominators_cannot_change_after_execution() -> None:
    data = result_data()
    scores = data["scores"]
    assert isinstance(scores, list)
    scores[0]["case_id"] = "b09"
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(BaselineResult, json.dumps(data).encode())
    scores[0]["case_id"] = "b01"
    scores[-1] = copy.deepcopy(scores[0])
    with pytest.raises(EvaluationFailure, match="invalid_baseline_document"):
        parse_document(BaselineResult, json.dumps(data).encode())


def test_duplicate_json_and_oversized_documents_fail_safely() -> None:
    with pytest.raises(EvaluationFailure, match="duplicate_json_field"):
        parse_document(BaselineResult, b'{"protocol":1,"protocol":2}')
    with pytest.raises(EvaluationFailure, match="baseline_document_limit"):
        parse_document(BaselineResult, b"x" * (256 * 1024 + 1))
