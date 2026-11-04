import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final, Literal, Self
from uuid import UUID

from pydantic import (
    Field,
    JsonValue,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from agent_evaluation.baseline_provenance import (
    BASELINE_FIXTURE,
    AcceptedRuntime,
    BaselineProvenance,
    Digest,
    document_digest,
)
from agent_evaluation.inputs import StrictModel, json_document
from agent_evaluation.policy import EvaluationFailure

FIXTURE: Final = BASELINE_FIXTURE
FIXTURE_SHA256: Final = "4113a28cbeef11aa19fae5ab1b7ac94dac2e96cad48815790bb8ae10ec299b28"
CaseId = Literal["b01", "b02", "b03", "b04", "b05", "b06", "b07", "b08", "b09", "b10", "b11", "b12"]
ControlId = Literal["c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08"]
MetricId = Literal["faithfulness", "citation_validity", "contract_adherence"]
Alias = Annotated[StrictStr, Field(pattern=r"^(?:n[1-9]|n10|n_missing)$")]
FilterAlias = Literal["f1", "f2", "f3"]
Score = Annotated[StrictFloat, Field(ge=0, le=1, allow_inf_nan=False)]
Outcome = Literal["supported", "limited", "no_match", "denied"]
Coverage = Literal["complete", "partial", "none", "discovery"]
CASE_IDS: Final = (
    "b01",
    "b02",
    "b03",
    "b04",
    "b05",
    "b06",
    "b07",
    "b08",
    "b09",
    "b10",
    "b11",
    "b12",
)
CONTROL_IDS: Final = ("c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08")
METRICS: Final = ("faithfulness", "citation_validity", "contract_adherence")
SEMANTIC_CASES: Final = CASE_IDS[:8]


class Thresholds(StrictModel):
    supported_min: StrictFloat = Field(ge=0.8, le=0.8)
    unsupported_max: StrictFloat = Field(ge=0.2, le=0.2)
    case_min: StrictFloat = Field(ge=0.8, le=0.8)
    macro_min: StrictFloat = Field(ge=0.9, le=0.9)


class BaselineCase(StrictModel):
    case_id: CaseId
    kind: Literal[
        "selected", "discovery", "no_match", "authority_limit", "missing_token", "wrong_audience"
    ]
    question: StrictStr = Field(min_length=1, max_length=2048, repr=False)
    item_aliases: Annotated[tuple[Alias, ...], Field(max_length=5)]
    filter_alias: FilterAlias | None
    expected_outcome: Outcome
    expected_coverage: Coverage
    detail: Literal["brief", "detailed"]
    language: Literal["English"]

    @model_validator(mode="after")
    def valid_selection(self) -> Self:
        if (
            not self.question.strip()
            or len(self.question.encode()) > 8192
            or len(set(self.item_aliases)) != len(self.item_aliases)
            or (
                self.kind in ("discovery", "no_match")
                and (self.item_aliases or self.filter_alias is None)
            )
            or (
                self.kind not in ("discovery", "no_match")
                and (not self.item_aliases or self.filter_alias is not None)
            )
        ):
            raise ValueError("invalid_baseline_selection")
        return self


class CalibrationControl(StrictModel):
    control_id: ControlId
    label: Literal["supported", "unsupported"]
    answer: StrictStr = Field(min_length=1, max_length=2048, repr=False)


class BaselineFixture(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    suite_version: Literal["v1"]
    cases: Annotated[tuple[BaselineCase, ...], Field(min_length=12, max_length=12)]
    controls: Annotated[tuple[CalibrationControl, ...], Field(min_length=8, max_length=8)]
    control_question: StrictStr = Field(min_length=1, max_length=2048, repr=False)
    control_evidence: StrictStr = Field(min_length=1, max_length=8192, repr=False)
    offline_controls: tuple[
        Literal["unknown_tool"],
        Literal["changed_endpoint"],
        Literal["scope_broadening"],
        Literal["retrieved_instruction"],
    ]
    thresholds: Thresholds

    @model_validator(mode="after")
    def fixed_case_sets(self) -> Self:
        if (
            tuple(case.case_id for case in self.cases) != CASE_IDS
            or tuple(control.control_id for control in self.controls) != CONTROL_IDS
            or tuple(control.label for control in self.controls)
            != ("supported",) * 4 + ("unsupported",) * 4
        ):
            raise ValueError("baseline_case_set_mismatch")
        return self


def load_fixture(path: Path = FIXTURE) -> BaselineFixture:
    try:
        data = path.read_bytes()
        if len(data) > 64 * 1024:
            raise EvaluationFailure("baseline_fixture_limit")
        if hashlib.sha256(data).hexdigest() != FIXTURE_SHA256:
            raise EvaluationFailure("baseline_fixture_digest_mismatch")
        json_document(data)
        return BaselineFixture.model_validate_json(data)
    except OSError, ValidationError, ValueError:
        raise EvaluationFailure("invalid_baseline_fixture") from None


def fixture_digest(path: Path = FIXTURE) -> str:
    load_fixture(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ItemBinding(StrictModel):
    alias: Alias
    item_id: UUID = Field(repr=False)
    present: StrictBool
    fingerprint: Digest | None

    @model_validator(mode="after")
    def presence_is_bound(self) -> Self:
        if self.present != (self.fingerprint is not None):
            raise ValueError("baseline_presence_fingerprint_mismatch")
        return self


class FilterBinding(StrictModel):
    alias: FilterAlias
    source: (
        Annotated[StrictStr, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)] | None
    )
    category: Annotated[StrictStr, Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")] | None
    tags: Annotated[
        tuple[Annotated[StrictStr, Field(pattern=r"^[a-z0-9][a-z0-9 +#.-]{0,47}$")], ...],
        Field(max_length=10),
    ]
    from_: datetime = Field(alias="from", repr=False)
    to: datetime = Field(repr=False)
    pool_aliases: Annotated[tuple[Alias, ...], Field(max_length=4)]
    pool_sha256: Digest

    @field_validator("from_", "to")
    @classmethod
    def normalized_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("baseline_timezone_required")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def bounded_pool(self) -> Self:
        if (
            self.from_.utcoffset() is None
            or self.to.utcoffset() is None
            or self.from_ >= self.to
            or len(set(self.pool_aliases)) != len(self.pool_aliases)
            or len(set(self.tags)) != len(self.tags)
            or any(value != " ".join(value.split()).casefold() for value in self.tags)
        ):
            raise ValueError("invalid_baseline_filter")
        return self


class PrivateBindings(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    fixture_sha256: Digest
    actor_sha256: Digest
    context_sha256: Digest
    accepted_runtime: AcceptedRuntime
    items: Annotated[tuple[ItemBinding, ...], Field(min_length=1, max_length=10)]
    filters: tuple[FilterBinding, FilterBinding, FilterBinding]

    @model_validator(mode="after")
    def consistent_bindings(self) -> Self:
        aliases = {item.alias for item in self.items}
        if (
            len(aliases) != len(self.items)
            or len({item.item_id for item in self.items}) != len(self.items)
            or any(item.present == (item.alias == "n_missing") for item in self.items)
            or tuple(value.alias for value in self.filters) != ("f1", "f2", "f3")
            or any(set(value.pool_aliases) - aliases for value in self.filters)
            or any(
                not item.present
                for value in self.filters
                for item in self.items
                if item.alias in value.pool_aliases
            )
            or not self.filters[0].pool_aliases
            or not self.filters[1].pool_aliases
            or self.filters[2].pool_aliases
        ):
            raise ValueError("baseline_bindings_mismatch")
        return self


class CaseOracle(StrictModel):
    case_id: CaseId
    expected_outcome: Outcome
    expected_coverage: Coverage
    required_aliases: Annotated[tuple[Alias, ...], Field(max_length=10)]
    minimum_claims: StrictInt = Field(ge=0, le=10)
    expected_http_status: Literal[200, 401, 403]

    @field_validator("required_aliases")
    @classmethod
    def unique_aliases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("baseline_oracle_duplicate_alias")
        return value


class Oracles(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    fixture_sha256: Digest
    bindings_sha256: Digest
    cases: Annotated[tuple[CaseOracle, ...], Field(min_length=12, max_length=12)]


class FrozenBaseline(StrictModel):
    protocol: Literal["baseline-v1"]
    provenance: BaselineProvenance
    bindings: PrivateBindings
    oracles: Oracles
    snapshot_version: StrictInt = Field(default=1, ge=1, exclude_if=lambda value: value == 1)

    @model_validator(mode="after")
    def frozen_integrity(self) -> Self:
        self.provenance.verify_current(self.bindings.accepted_runtime)
        fixture = load_fixture()
        digest = fixture_digest()
        bindings_hash = document_digest(self.bindings.model_dump(mode="json", by_alias=True))
        oracle_hash = document_digest(self.oracles.model_dump(mode="json"))
        if (
            any(
                value != digest
                for value in (
                    self.provenance.fixture_sha256,
                    self.bindings.fixture_sha256,
                    self.oracles.fixture_sha256,
                )
            )
            or self.provenance.accepted_runtime != self.bindings.accepted_runtime
            or self.provenance.bindings_sha256 != bindings_hash
            or self.oracles.bindings_sha256 != bindings_hash
            or self.provenance.oracle_sha256 != oracle_hash
            or tuple(case.case_id for case in self.oracles.cases) != CASE_IDS
        ):
            raise ValueError("baseline_frozen_digest_mismatch")
        items = {item.alias: item for item in self.bindings.items}
        filters = {value.alias: value for value in self.bindings.filters}
        for case, oracle in zip(fixture.cases, self.oracles.cases, strict=True):
            allowed = (
                case.item_aliases
                if case.filter_alias is None
                else filters[case.filter_alias].pool_aliases
            )
            required = {alias for alias in allowed if alias in items and items[alias].present}
            if (
                set(allowed) - items.keys()
                or set(oracle.required_aliases)
                != (required if case.expected_outcome != "denied" else set())
                or oracle.expected_outcome != case.expected_outcome
                or oracle.expected_coverage != case.expected_coverage
                or oracle.minimum_claims
                != (
                    2
                    if case.case_id == "b02"
                    else int(case.expected_outcome not in ("no_match", "denied"))
                )
                or (oracle.expected_http_status != 200) != (case.expected_outcome == "denied")
            ):
                raise ValueError("baseline_oracle_mismatch")
        return self

    def request_document(self, case_id: CaseId) -> dict[str, JsonValue]:
        case = next(case for case in load_fixture().cases if case.case_id == case_id)
        items = {item.alias: str(item.item_id) for item in self.bindings.items}
        filters: dict[str, JsonValue] = {
            "source": None,
            "category": None,
            "tags": [],
            "from": None,
            "to": None,
        }
        if case.filter_alias is not None:
            selected = next(
                value for value in self.bindings.filters if value.alias == case.filter_alias
            )
            filters = {
                "source": selected.source,
                "category": selected.category,
                "tags": list(selected.tags),
                "from": selected.from_.isoformat().replace("+00:00", "Z"),
                "to": selected.to.isoformat().replace("+00:00", "Z"),
            }
        return {
            "operation": "research",
            "question": case.question,
            "item_ids": [items[alias] for alias in case.item_aliases] or None,
            "filters": filters,
            "preferences": {
                "detail": case.detail,
                "language": case.language,
                "audience": None,
                "focus": None,
            },
        }

    def evidence_digest(self, case_id: CaseId) -> str:
        case = next(case for case in load_fixture().cases if case.case_id == case_id)
        selected = next(
            (value for value in self.bindings.filters if value.alias == case.filter_alias), None
        )
        aliases = case.item_aliases if selected is None else selected.pool_aliases
        return document_digest(
            {
                "items": [
                    item.model_dump(mode="json")
                    for alias in aliases
                    for item in self.bindings.items
                    if item.alias == alias
                ],
                "pool_sha256": None if selected is None else selected.pool_sha256,
            }
        )


class CaseReceipt(StrictModel):
    case_id: CaseId
    modality: Literal["live_a2a"]
    outcome: Outcome
    request_sha256: Digest
    evidence_sha256: Digest
    answer_sha256: Digest | None
    http_status: Literal[200, 401, 403]
    tool_calls: StrictInt = Field(ge=0, le=8)
    evidence_items: StrictInt = Field(ge=0, le=10)
    validated: StrictBool
    generation_calls: StrictInt = Field(ge=0, le=4)
    usage_observed_calls: StrictInt = Field(ge=0, le=4)
    input_tokens: StrictInt = Field(ge=0, le=262144)
    output_tokens: StrictInt = Field(ge=0, le=4096)
    elapsed_ms: StrictInt = Field(ge=0, le=120000)
    user_preserved: StrictBool
    no_model_work_verified: StrictBool

    @model_validator(mode="after")
    def receipt_matches_outcome(self) -> Self:
        denied = self.outcome == "denied"
        if (
            denied != (self.http_status != 200)
            or denied != (self.answer_sha256 is None)
            or self.usage_observed_calls != self.generation_calls
            or (not self.generation_calls and (self.input_tokens or self.output_tokens))
            or (not denied and not self.user_preserved)
            or (not denied and self.tool_calls < 1)
            or (not denied and not self.validated)
            or (denied and (self.evidence_items or self.validated))
            or (denied and (self.generation_calls or self.tool_calls))
            or (not denied and self.no_model_work_verified)
        ):
            raise ValueError("invalid_baseline_case_receipt")
        return self


class MetricScore(StrictModel):
    case_id: CaseId
    metric_id: MetricId
    score: Score

    @model_validator(mode="after")
    def declared_applicability(self) -> Self:
        if self.metric_id != "contract_adherence" and self.case_id not in SEMANTIC_CASES:
            raise ValueError("baseline_metric_not_applicable")
        return self


class BaselineResult(StrictModel):
    protocol: Literal["baseline-v1"]
    provenance: BaselineProvenance
    frozen_sha256: Digest
    cases: Annotated[tuple[CaseReceipt, ...], Field(min_length=12, max_length=12)]
    scores: Annotated[tuple[MetricScore, ...], Field(min_length=28, max_length=28)]

    @model_validator(mode="after")
    def complete_denominators(self) -> Self:
        expected = {
            (case, metric)
            for metric in METRICS
            for case in (CASE_IDS if metric == "contract_adherence" else SEMANTIC_CASES)
        }
        if (
            tuple(case.case_id for case in self.cases) != CASE_IDS
            or {(row.case_id, row.metric_id) for row in self.scores} != expected
        ):
            raise ValueError("baseline_result_case_set_mismatch")
        return self

    def verify_frozen(self, frozen: FrozenBaseline) -> None:
        if (
            self.provenance != frozen.provenance
            or self.frozen_sha256 != document_digest(frozen.model_dump(mode="json", by_alias=True))
            or any(
                case.request_sha256 != document_digest(frozen.request_document(case.case_id))
                or case.evidence_sha256 != frozen.evidence_digest(case.case_id)
                or (case.outcome == "denied") != (oracle.expected_outcome == "denied")
                or (case.outcome == "denied" and case.http_status != oracle.expected_http_status)
                for case, oracle in zip(self.cases, frozen.oracles.cases, strict=True)
            )
        ):
            raise EvaluationFailure("baseline_result_binding_mismatch")


class ControlMeasurement(StrictModel):
    control_id: ControlId
    label: Literal["supported", "unsupported"]
    score: Score
    passed: StrictBool
    judge_attempts: StrictInt = Field(ge=1, le=80)


class ScoringProgress(StrictModel):
    protocol: Literal["baseline-v1"]
    approval_sha256: Digest
    frozen_sha256: Digest
    state: Literal["new", "calibrating", "calibrated", "scoring", "failed", "completed"]
    pending_control: ControlId | None
    pending_case: CaseId | None
    controls: Annotated[tuple[ControlMeasurement, ...], Field(max_length=8)]
    scores: Annotated[tuple[MetricScore, ...], Field(max_length=28)]

    @model_validator(mode="after")
    def immutable_progress_sets(self) -> Self:
        if (
            tuple(value.control_id for value in self.controls) != CONTROL_IDS[: len(self.controls)]
            or len({(value.case_id, value.metric_id) for value in self.scores}) != len(self.scores)
            or (
                self.state in ("calibrated", "scoring", "completed")
                and (len(self.controls) != 8 or not all(value.passed for value in self.controls))
            )
        ):
            raise ValueError("invalid_baseline_scoring_progress")
        return self


def parse_document[Model: StrictModel](model: type[Model], data: bytes) -> Model:
    if len(data) > 256 * 1024:
        raise EvaluationFailure("baseline_document_limit")
    json_document(data)
    try:
        return model.model_validate_json(data)
    except ValidationError:
        raise EvaluationFailure("invalid_baseline_document") from None
