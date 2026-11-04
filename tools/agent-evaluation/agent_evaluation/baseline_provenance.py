import hashlib
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import Field, StrictInt, StrictStr

from agent_evaluation.inputs import ROOT, StrictModel, load_pilot, source_digest
from agent_evaluation.policy import EvaluationFailure
from agent_evaluation.production_inputs import (
    PRODUCTION_INPUTS as PRODUCTION_INPUTS,
)
from agent_evaluation.production_inputs import (
    PRODUCTION_INPUTS_V2 as PRODUCTION_INPUTS_V2,
)
from agent_evaluation.production_inputs import (
    document_digest as document_digest,
)
from agent_evaluation.production_inputs import (
    verify_production_inputs as verify_production_inputs,
)

Digest = Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]
BASELINE_FIXTURE: Final = ROOT / "config/agent-quality-baseline.json"


def evaluator_source_digest() -> str:
    try:
        fixture_hash = hashlib.sha256(BASELINE_FIXTURE.read_bytes()).hexdigest()
    except OSError:
        raise EvaluationFailure("baseline_fixture_unavailable") from None
    return document_digest({"evaluator_sha256": source_digest(), "fixture_sha256": fixture_hash})


def capture_source_digest(root: Path = ROOT) -> str:
    paths = [root / name for name in PRODUCTION_INPUTS] + sorted(
        (root / "services/agent/src/newsloom_agent").rglob("*.py")
    )
    paths += sorted((root / "scripts").glob("*quality*.py"))
    paths += sorted((root / "packages/newsloom-core/src/newsloom_core").rglob("*.py"))
    paths += sorted((root / "services/mcp/src/newsloom_mcp").rglob("*.py"))
    paths += sorted((root / "tests").glob("test_agent_research*.py"))
    paths += [root / "tests/test_agent_delegation.py", root / "tests/test_agent_client.py"]
    if not (root / "services/agent/src/newsloom_agent/client.py").is_file():
        raise EvaluationFailure("baseline_capture_source_unavailable")
    try:
        return document_digest(
            {
                path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths
            }
        )
    except OSError:
        raise EvaluationFailure("baseline_capture_source_unavailable") from None


class AcceptedRuntime(StrictModel):
    receipt_sha256: Digest
    image_sha256: Digest
    configuration_sha256: Digest
    source_sha256: Digest


class BaselineProvenance(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    protocol: Literal["baseline-v1"]
    foundation_archive_commit: Literal["95570c48fa7bf7a16e2778be7d49d938a2fd9ea5"]
    accepted_runtime: AcceptedRuntime
    evaluator_source_sha256: Digest
    capture_source_sha256: Digest
    production_inputs_sha256: Digest
    fixture_sha256: Digest
    bindings_sha256: Digest
    oracle_sha256: Digest

    def verify_current(self, runtime: AcceptedRuntime) -> None:
        load_pilot()
        if (
            self.accepted_runtime != runtime
            or self.evaluator_source_sha256 != evaluator_source_digest()
            or self.capture_source_sha256 != capture_source_digest()
            or self.production_inputs_sha256 != verify_production_inputs()
            or self.fixture_sha256 != hashlib.sha256(BASELINE_FIXTURE.read_bytes()).hexdigest()
        ):
            raise EvaluationFailure("baseline_provenance_mismatch")
