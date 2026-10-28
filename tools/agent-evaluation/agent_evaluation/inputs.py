import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from agent_evaluation.policy import EvaluationFailure

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "config/agent-evaluation-pilot.json"
FIXTURE_SHA256 = "6e10dc351672df957772e94b78c01fa912bd9fdea3d5a0952de111dcf2433c9d"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class Case(StrictModel):
    case_id: Literal["p01", "p02"]
    diagnostic_label: Literal["supported", "unsupported"]
    answer: StrictStr = Field(min_length=1, max_length=2048)


class Pilot(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    question: StrictStr = Field(min_length=1, max_length=1024)
    evidence: StrictStr = Field(min_length=1, max_length=4096)
    cases: tuple[Case, Case]


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationFailure("duplicate_json_field")
        result[key] = value
    return result


def json_document(data: bytes) -> object:
    try:
        return json.loads(data, object_pairs_hook=_unique_pairs)
    except UnicodeDecodeError, json.JSONDecodeError:
        raise EvaluationFailure("invalid_json_document") from None


def load_pilot() -> Pilot:
    data = FIXTURE.read_bytes()
    if hashlib.sha256(data).hexdigest() != FIXTURE_SHA256:
        raise EvaluationFailure("pilot_fixture_digest_mismatch")
    json_document(data)
    try:
        result = Pilot.model_validate_json(data)
    except ValidationError:
        raise EvaluationFailure("invalid_pilot_fixture") from None
    if tuple((case.case_id, case.diagnostic_label) for case in result.cases) != (
        ("p01", "supported"),
        ("p02", "unsupported"),
    ):
        raise EvaluationFailure("pilot_case_set_mismatch")
    return result


def source_digest() -> str:
    project = ROOT / "tools/agent-evaluation"
    paths = sorted(
        [
            ROOT / "pyproject.toml",
            ROOT / "scripts/check-agent-evaluation.sh",
            FIXTURE,
            project / "pyproject.toml",
            project / "uv.lock",
            *(project / "agent_evaluation").rglob("*.py"),
        ]
    )
    digest = hashlib.sha256()
    for path in paths:
        name = path.relative_to(ROOT).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big") + name + len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()
