import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from newsloom_core.phase1_contracts import (
    EXPECTED,
    AcceptanceFailure,
    CaseResult,
    Fixtures,
    Manifest,
    Report,
    Stage,
    TestConfig,
    database_name,
    fixture_revision,
    load_fixtures,
)
from newsloom_ingestion.scanner import calibration_id
from pydantic import ValidationError


@pytest.mark.parametrize("bad", [True, "0.1", float("inf"), float("nan"), -1.0, 1801.0])
def test_timing_requires_bounded_actual_numeric_measurements(bad: object) -> None:
    with pytest.raises(ValidationError):
        Stage.model_validate({"name": "cleanup", "counts": {"absent": 1}, "elapsed_seconds": bad})


@pytest.fixture
def phase_config() -> TestConfig:
    return TestConfig(
        run_id=uuid4().hex,
        principal_id=uuid4(),
        client_id=uuid4(),
        postgres_host="localhost",
        model_endpoint="https://models.test",
        generation_deployment="generation",
        generation_model="generation-test",
        generation_version="1",
        embedding_deployment="embedding",
        embedding_model="embedding-test",
        embedding_version="1",
        screening_deployment="screening",
        screening_model="screening-test",
        screening_version="1",
        scanner_threshold=0.5,
        scanner_calibration_id=calibration_id(
            "https://models.test",
            "screening",
            "screening-test",
            "1",
            0.5,
        ),
        image_revision="b" * 64,
    )


def test_configuration_binds_run_separately_and_has_no_database_override(
    phase_config: TestConfig,
) -> None:
    values = phase_config.model_dump(mode="json", exclude={"run_id", "scenario"})
    encoded = base64.b64encode(json.dumps(values).encode()).decode()
    assert TestConfig.from_encoded(encoded, phase_config.run_id) == phase_config
    for changed in (
        {**values, "database": "newsloom"},
        {**values, "run_id": uuid4().hex},
        {**values, "model_endpoint": "https://user:secret@models.test"},
    ):
        encoded = base64.b64encode(json.dumps(changed).encode()).decode()
        with pytest.raises(ValidationError):
            TestConfig.from_encoded(encoded, phase_config.run_id)
    with pytest.raises(AcceptanceFailure):
        TestConfig.from_encoded("!not-base64", phase_config.run_id)
    with pytest.raises(AcceptanceFailure):
        TestConfig.from_encoded("a" * 16385, phase_config.run_id)


def test_four_frozen_cases_have_complete_exact_identities() -> None:
    cases = load_fixtures()
    assert len(cases.cases) == 4
    assert sum(item.hostile for item in cases.cases) == 2
    assert all(item.title and item.text and item.author for item in cases.cases)
    assert len({item.url for item in cases.cases}) == 4
    value = cases.model_dump(mode="json")
    for changed in (
        {**value, "cases": value["cases"][:-1]},
        {**value, "cases": [value["cases"][0]] * 4},
    ):
        with pytest.raises(ValidationError):
            Fixtures.model_validate(changed)
    assert len(fixture_revision()) == 64


@pytest.mark.parametrize(
    "run_id",
    [
        "newsloom",
        "postgres",
        "template1",
        "../newsloom",
        "*" * 32,
        "A" * 32,
        "a" * 31,
        "a" * 33,
        "a" * 31 + ";",
    ],
)
def test_targets_cannot_be_arbitrary_identifiers(run_id: str) -> None:
    with pytest.raises(AcceptanceFailure):
        database_name(run_id)


def test_manifest_binds_target_owner_and_all_revisions() -> None:
    run_id = uuid4().hex
    manifest = Manifest(
        run_id=run_id,
        database=database_name(run_id),
        principal_id=uuid4(),
        fixture_revision=fixture_revision(),
        schema_revision="a" * 64,
        model_revision="b" * 64,
        image_revision="c" * 64,
        prepared_at=datetime.now(UTC),
    )
    for changed in ({"database": "newsloom"}, {"run_id": uuid4().hex}, {"schema_revision": "bad"}):
        with pytest.raises(ValidationError):
            Manifest.model_validate({**manifest.model_dump(), **changed})


def report() -> Report:
    return Report(
        run_id=uuid4().hex,
        scenario="acceptance",
        outcome="success",
        fixture_revision=fixture_revision(),
        schema_revision="a" * 64,
        model_revision="b" * 64,
        image_revision="c" * 64,
        stages=tuple(
            Stage.model_validate({"name": name, "counts": values, "elapsed_seconds": 0.1})
            for name, values in EXPECTED.items()
        ),
        cases=tuple(
            CaseResult.model_validate(
                {
                    "id": case.id,
                    "disposition": "rejected" if case.hostile else "accepted",
                    "reason": "screened",
                    "score": 0.9 if case.hostile else 0.1,
                    "threshold": 0.5,
                }
            )
            for case in load_fixtures().cases
        ),
    )


def test_missing_duplicate_or_failed_stages_never_look_successful() -> None:
    value = report().model_dump(mode="json")
    changes: tuple[dict[str, object], ...] = (
        {"stages": value["stages"][:-1]},
        {"stages": [value["stages"][0]] * 8},
        {"scenario": "failure-after-ingestion"},
        {"category": "model_unavailable"},
        {"outcome": "failure", "category": ""},
        {"version": True},
        {"cases": []},
        {"cases": [value["cases"][0]] * 4},
    )
    for changed in changes:
        with pytest.raises(ValidationError):
            Report.model_validate({**value, **changed})
    assert (
        Report.model_validate(
            {
                **value,
                "outcome": "failure",
                "category": "model_unavailable",
                "stages": [],
            }
        ).outcome
        == "failure"
    )


@pytest.mark.parametrize("bad", [True, -1, 0, 2, "1", float("nan")])
def test_counts_are_actual_exact_integers_not_coercible_values(bad: object) -> None:
    with pytest.raises(ValidationError):
        Stage.model_validate({"name": "cleanup", "counts": {"absent": bad}, "elapsed_seconds": 0})
