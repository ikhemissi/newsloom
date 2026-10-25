"""Private acceptance contracts shared by operators, the test image and its launcher."""

import base64
import binascii
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROLE = "newsloom_phase1_acceptance"
HexDigest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RunId = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
Count = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
Scenario = Literal["acceptance", "failure-after-ingestion", "cancel-after-claim"]
CASE_IDS = {"rss-benign", "rss-hostile", "atom-benign", "atom-hostile"}
EXPECTED: dict[str, dict[str, int]] = {
    "prepared": {"manifest": 1},
    "isolation": {"production_denials": 1, "role_denials": 4},
    "ingestion": {"found": 4, "accepted": 2, "rejected": 2, "deferred": 0},
    "replay": {"duplicates": 4, "staged": 0},
    "concurrency": {"distinct_claims": 2, "lost_workers": 1},
    "recovery": {
        "attempt": 2,
        "completed": 2,
        "unfinished": 0,
        "duplicates": 0,
        "published_rejections": 0,
    },
    "queries": {"checks": 5, "news": 2, "vectors": 2},
    "cleanup": {"absent": 1},
}


class AcceptanceFailure(Exception):
    def __init__(self, category: str) -> None:
        if not re.fullmatch(r"[a-z0-9_]{1,80}", category):
            raise ValueError("invalid_acceptance_category")
        super().__init__(category)


def database_name(run_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise AcceptanceFailure("invalid_acceptance_run_id")
    return "newsloom_phase1_" + run_id


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class FixtureCase(Contract):
    id: Literal["rss-benign", "rss-hostile", "atom-benign", "atom-hostile"]
    kind: Literal["rss", "atom"]
    hostile: Annotated[bool, Field(strict=True)]
    title: Annotated[str, Field(min_length=1, max_length=256)]
    text: Annotated[str, Field(min_length=1, max_length=4096)]
    author: Annotated[str, Field(min_length=1, max_length=1024)]
    published_at: datetime

    @model_validator(mode="after")
    def fixed_identity(self) -> Self:
        if self.id != f"{self.kind}-{'hostile' if self.hostile else 'benign'}":
            raise ValueError("fixture_identity_mismatch")
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("fixture_timezone_required")
        return self

    @property
    def url(self) -> str:
        return "https://example.com/newsloom/phase1/" + self.id


class Fixtures(Contract):
    revision: Literal["phase1-v1"]
    cases: Annotated[tuple[FixtureCase, ...], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def complete(self) -> Self:
        if {item.id for item in self.cases} != CASE_IDS:
            raise ValueError("acceptance_cases_incomplete")
        return self


def load_fixtures(path: Path = Path("config/phase1-acceptance.json")) -> Fixtures:
    return Fixtures.model_validate_json(path.read_bytes())


def fixture_revision(path: Path = Path("config/phase1-acceptance.json")) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Manifest(Contract):
    run_id: RunId
    database: str
    principal_id: UUID
    fixture_revision: HexDigest
    schema_revision: HexDigest
    model_revision: HexDigest
    image_revision: HexDigest
    prepared_at: datetime

    @model_validator(mode="after")
    def exact_target(self) -> Self:
        if self.database != database_name(self.run_id):
            raise ValueError("acceptance_database_mismatch")
        if self.prepared_at.tzinfo is None or self.prepared_at.utcoffset() is None:
            raise ValueError("manifest_timezone_required")
        return self


class Stage(Contract):
    name: Literal[
        "prepared",
        "isolation",
        "ingestion",
        "replay",
        "concurrency",
        "recovery",
        "queries",
        "cleanup",
    ]
    counts: dict[str, Count]
    elapsed_seconds: Annotated[float, Field(strict=True, ge=0, le=1800, allow_inf_nan=False)]

    @model_validator(mode="after")
    def exact_counts(self) -> Self:
        if self.counts != EXPECTED[self.name]:
            raise ValueError("acceptance_stage_gate_failed")
        return self


class CaseResult(Contract):
    id: Literal["rss-benign", "rss-hostile", "atom-benign", "atom-hostile"]
    disposition: Literal["accepted", "rejected", "deferred"]
    reason: Annotated[str, Field(pattern=r"^[a-z0-9_]{1,80}$")]
    score: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None
    threshold: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None

    @model_validator(mode="after")
    def honest_decision(self) -> Self:
        if self.disposition != "deferred":
            if self.score is None or self.threshold is None:
                raise ValueError("scored_acceptance_decision_required")
            if (self.score <= self.threshold) != (self.disposition == "accepted"):
                raise ValueError("acceptance_score_disposition_mismatch")
        return self


class Report(Contract):
    event: Literal["phase1_acceptance_report"] = "phase1_acceptance_report"
    version: Literal[1] = 1
    run_id: RunId
    scenario: Scenario
    outcome: Literal["success", "failure"]
    category: Annotated[str, Field(pattern=r"^[a-z0-9_]{0,80}$")] = ""
    fixture_revision: HexDigest
    schema_revision: HexDigest
    model_revision: HexDigest
    image_revision: HexDigest
    stages: Annotated[tuple[Stage, ...], Field(max_length=8)]
    cases: Annotated[tuple[CaseResult, ...], Field(max_length=4)] = ()

    @field_validator("version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("integer_acceptance_version_required")
        return value

    @model_validator(mode="after")
    def honest_completion(self) -> Self:
        names = [stage.name for stage in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("duplicate_acceptance_stage")
        if self.outcome == "success":
            if self.scenario != "acceptance" or self.category or set(names) != set(EXPECTED):
                raise ValueError("incomplete_acceptance_report")
            if {case.id for case in self.cases} != CASE_IDS or any(
                case.disposition != ("rejected" if case.id.endswith("hostile") else "accepted")
                for case in self.cases
            ):
                raise ValueError("incomplete_or_failed_acceptance_cases")
        elif not self.category:
            raise ValueError("acceptance_failure_category_required")
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate_acceptance_case")
        return self


class WorkflowReceipt(Contract):
    outcome: Literal["success", "failure"]
    category: Annotated[str, Field(pattern=r"^[a-z0-9_]{0,80}$")] = ""
    cleanup_category: Annotated[str, Field(pattern=r"^[a-z0-9_]{0,80}$")] = ""
    workflow_sha: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    run_id: RunId
    scenario: Scenario
    report: Report | None = None
    cleanup_verified: Annotated[bool, Field(strict=True)] = False

    @model_validator(mode="after")
    def bound_receipt(self) -> Self:
        if self.report is not None and (
            self.report.run_id != self.run_id or self.report.scenario != self.scenario
        ):
            raise ValueError("workflow_receipt_identity_mismatch")
        if self.outcome == "success" and (
            self.report is None
            or self.report.outcome != "success"
            or not self.cleanup_verified
            or self.category
            or self.cleanup_category
        ):
            raise ValueError("incomplete_workflow_success")
        if self.outcome == "failure" and not self.category:
            raise ValueError("workflow_failure_category_required")
        return self


class Settings(Contract):
    __test__ = False
    principal_id: UUID
    client_id: UUID
    postgres_host: Annotated[str, Field(min_length=1, max_length=253)]
    model_endpoint: str
    generation_deployment: Annotated[str, Field(pattern=r"^[a-zA-Z0-9._-]{1,64}$")]
    embedding_deployment: Annotated[str, Field(pattern=r"^[a-zA-Z0-9._-]{1,64}$")]
    screening_deployment: Annotated[str, Field(pattern=r"^[a-zA-Z0-9._-]{1,64}$")]
    generation_model: str
    generation_version: str
    embedding_model: str
    embedding_version: str
    screening_model: str
    screening_version: str
    scanner_threshold: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    scanner_calibration_id: HexDigest
    image_revision: HexDigest

    @field_validator("model_endpoint")
    @classmethod
    def trusted_endpoint(cls, value: str) -> str:
        if not re.fullmatch(r"https://[a-z0-9]+(?:[.-][a-z0-9]+)*(?:/)?", value):
            raise ValueError("invalid_acceptance_model_endpoint")
        return value.rstrip("/")


class TestConfig(Settings):
    __test__ = False
    run_id: RunId
    scenario: Scenario = "acceptance"

    @property
    def database(self) -> str:
        return database_name(self.run_id)

    def model_revision(self) -> str:
        values = self.model_dump(
            exclude={
                "run_id",
                "scenario",
                "principal_id",
                "client_id",
                "postgres_host",
                "image_revision",
            }
        )
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_encoded(cls, value: str, run_id: str, scenario: Scenario = "acceptance") -> Self:
        database_name(run_id)
        if len(value) > 16384:
            raise AcceptanceFailure("acceptance_configuration_limit")
        try:
            settings = Settings.model_validate_json(base64.b64decode(value, validate=True))
        except binascii.Error:
            raise AcceptanceFailure("invalid_acceptance_configuration_encoding") from None
        return cls(**settings.model_dump(), run_id=run_id, scenario=scenario)


def prepared_manifest(config: TestConfig, schema_revision: str) -> Manifest:
    return Manifest(
        run_id=config.run_id,
        database=config.database,
        principal_id=config.principal_id,
        fixture_revision=fixture_revision(),
        schema_revision=schema_revision,
        model_revision=config.model_revision(),
        image_revision=config.image_revision,
        prepared_at=datetime.now(UTC),
    )
