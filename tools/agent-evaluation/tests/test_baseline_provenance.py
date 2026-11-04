import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_evaluation import production_inputs
from agent_evaluation.baseline_provenance import (
    BASELINE_FIXTURE,
    PRODUCTION_INPUTS,
    PRODUCTION_INPUTS_V2,
    AcceptedRuntime,
    BaselineProvenance,
    capture_source_digest,
    document_digest,
    evaluator_source_digest,
    verify_production_inputs,
)
from agent_evaluation.inputs import FIXTURE, FIXTURE_SHA256, ROOT, load_pilot
from agent_evaluation.policy import EvaluationFailure
from agent_evaluation.production_inputs import PRODUCTION_INPUTS_V3


def runtime() -> AcceptedRuntime:
    return AcceptedRuntime(
        receipt_sha256="a" * 64,
        image_sha256="b" * 64,
        configuration_sha256="c" * 64,
        source_sha256="d" * 64,
    )


def provenance() -> BaselineProvenance:
    return BaselineProvenance(
        schema_version=1,
        protocol="baseline-v1",
        foundation_archive_commit="95570c48fa7bf7a16e2778be7d49d938a2fd9ea5",
        accepted_runtime=runtime(),
        evaluator_source_sha256=evaluator_source_digest(),
        capture_source_sha256=capture_source_digest(),
        production_inputs_sha256=verify_production_inputs(),
        fixture_sha256=hashlib.sha256(BASELINE_FIXTURE.read_bytes()).hexdigest(),
        bindings_sha256="f" * 64,
        oracle_sha256="a" * 64,
    )


def test_current_inputs_and_legacy_fixture_remain_immutable() -> None:
    assert len(PRODUCTION_INPUTS) == 8
    assert verify_production_inputs() == document_digest(PRODUCTION_INPUTS_V3)
    assert PRODUCTION_INPUTS["pyproject.toml"] == (
        "0e676e369ce0abd956518993ad40fb112bc1f5084abb3f52c55e72dbab8aef59"
    )
    assert {
        key for key in PRODUCTION_INPUTS if PRODUCTION_INPUTS[key] != PRODUCTION_INPUTS_V2[key]
    } == {"pyproject.toml"}
    assert set(PRODUCTION_INPUTS_V3) - set(PRODUCTION_INPUTS_V2) == {
        "services/briefing/pyproject.toml"
    }
    assert {
        key
        for key in PRODUCTION_INPUTS_V2
        if PRODUCTION_INPUTS_V2[key] != PRODUCTION_INPUTS_V3[key]
    } == {"pyproject.toml", "uv.lock"}
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    assert tuple(case.case_id for case in load_pilot().cases) == ("p01", "p02")


@pytest.mark.parametrize("pin_set", ["PRODUCTION_INPUTS", "PRODUCTION_INPUTS_V2"])
def test_historical_manifest_pins_remain_verifiable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pin_set: str
) -> None:
    # Synthetic bytes stand in for historical manifests; literal pins are asserted above.
    pins = {}
    for path in PRODUCTION_INPUTS:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        data = f"historical {pin_set} {path}".encode()
        target.write_bytes(data)
        pins[path] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(production_inputs, pin_set, pins)
    assert verify_production_inputs(tmp_path) == document_digest(pins)
    (tmp_path / "uv.lock").write_bytes(b"changed")
    with pytest.raises(EvaluationFailure, match="baseline_production_inputs_changed"):
        verify_production_inputs(tmp_path)


def test_historical_provenance_cannot_authorize_changed_ui_workspace_source() -> None:
    value = provenance().model_copy(
        update={
            "production_inputs_sha256": document_digest(PRODUCTION_INPUTS),
        }
    )
    assert value.production_inputs_sha256 != verify_production_inputs()
    with pytest.raises(EvaluationFailure, match="baseline_provenance_mismatch"):
        value.verify_current(runtime())


def test_runtime_provenance_is_not_relabelled_as_evaluator_source() -> None:
    value = provenance()
    value.verify_current(runtime())
    assert value.accepted_runtime.source_sha256 == "d" * 64
    assert value.accepted_runtime.source_sha256 != value.evaluator_source_sha256
    changed = runtime().model_copy(update={"image_sha256": "e" * 64})
    with pytest.raises(EvaluationFailure, match="baseline_provenance_mismatch"):
        value.verify_current(changed)


@pytest.mark.parametrize(
    "field",
    ("evaluator_source_sha256", "capture_source_sha256", "production_inputs_sha256"),
)
def test_stale_local_source_is_rejected(field: str) -> None:
    value = provenance().model_copy(update={field: "0" * 64})
    with pytest.raises(EvaluationFailure, match="baseline_provenance_mismatch"):
        value.verify_current(runtime())


@pytest.mark.parametrize("name", tuple(PRODUCTION_INPUTS))
def test_changed_production_input_fails_without_modifying_real_inputs(
    name: str, tmp_path: Path
) -> None:
    for path in PRODUCTION_INPUTS:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    (tmp_path / name).write_bytes(b"changed")
    with pytest.raises(EvaluationFailure, match="baseline_production_inputs_changed"):
        verify_production_inputs(tmp_path)


def test_missing_inputs_fail_explicitly(tmp_path: Path) -> None:
    with pytest.raises(EvaluationFailure, match="baseline_production_inputs_unavailable"):
        verify_production_inputs(tmp_path)
    with pytest.raises(EvaluationFailure, match="baseline_capture_source_unavailable"):
        capture_source_digest(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("protocol", "native-python"),
        ("foundation_archive_commit", "f" * 40),
        ("evaluator_source_sha256", "content-that-is-not-a-fingerprint"),
        ("unexpected", "content-canary"),
    ],
)
def test_provenance_schema_rejects_foreign_or_unbounded_fields(field: str, value: object) -> None:
    data = provenance().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        BaselineProvenance.model_validate(data)
