import hashlib
import re
from pathlib import Path

import pytest

from agent_evaluation.inputs import ROOT
from agent_evaluation.policy import EvaluationFailure
from agent_evaluation.production_inputs import (
    PRODUCTION_INPUTS,
    PRODUCTION_INPUTS_V2,
    PRODUCTION_INPUTS_V3,
    document_digest,
    verify_production_inputs,
)


def test_current_and_historical_digests_are_distinct_and_preserved() -> None:
    assert verify_production_inputs() == document_digest(PRODUCTION_INPUTS_V3)
    assert PRODUCTION_INPUTS["pyproject.toml"] == (
        "0e676e369ce0abd956518993ad40fb112bc1f5084abb3f52c55e72dbab8aef59"
    )
    assert document_digest(PRODUCTION_INPUTS) != document_digest(PRODUCTION_INPUTS_V2)
    with pytest.raises(EvaluationFailure, match="baseline_provenance_mismatch"):
        verify_production_inputs(expected_sha256=document_digest(PRODUCTION_INPUTS))
    with pytest.raises(EvaluationFailure, match="baseline_provenance_mismatch"):
        verify_production_inputs(expected_sha256=document_digest(PRODUCTION_INPUTS_V2))
    assert verify_production_inputs(expected_sha256=document_digest(PRODUCTION_INPUTS_V3))


def historical_input(path: str) -> bytes:
    data = (ROOT / path).read_bytes()
    if path == "pyproject.toml":
        data = data.replace(b'    "newsloom-briefing",\n', b"").replace(
            b"newsloom-briefing = { workspace = true }\n", b""
        )
    if path == "uv.lock":
        data = re.sub(
            rb'\[\[package\]\]\nname = "(?:newsloom-briefing|tiktoken)"\n.*?(?=\[\[package\]\])',
            b"",
            data,
            flags=re.DOTALL,
        )
        data = b"".join(
            line for line in data.splitlines(keepends=True) if b'"newsloom-briefing"' not in line
        )
    return data


def test_original_workspace_still_returns_its_original_digest(tmp_path: Path) -> None:
    for path, expected in PRODUCTION_INPUTS.items():
        data = historical_input(path)
        if path == "pyproject.toml":
            data = data.replace(
                b'exclude = ["tools/agent-evaluation", "services/web"]',
                b'exclude = ["tools/agent-evaluation"]',
            )
        assert hashlib.sha256(data).hexdigest() == expected
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    assert verify_production_inputs(tmp_path) == document_digest(PRODUCTION_INPUTS)


def test_http_ui_workspace_retains_its_original_v2_digest(tmp_path: Path) -> None:
    for path, expected in PRODUCTION_INPUTS_V2.items():
        data = historical_input(path)
        assert hashlib.sha256(data).hexdigest() == expected
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    assert verify_production_inputs(tmp_path) == document_digest(PRODUCTION_INPUTS_V2)


@pytest.mark.parametrize("name", tuple(PRODUCTION_INPUTS_V3))
def test_unknown_manifest_changes_are_not_re_pinned(name: str, tmp_path: Path) -> None:
    for path in PRODUCTION_INPUTS_V3:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    (tmp_path / name).write_bytes(b"changed")
    with pytest.raises(EvaluationFailure, match="baseline_production_inputs_changed"):
        verify_production_inputs(tmp_path)


def test_missing_inputs_and_noncanonical_values_fail(tmp_path: Path) -> None:
    with pytest.raises(EvaluationFailure, match="baseline_production_inputs_unavailable"):
        verify_production_inputs(tmp_path)
    with pytest.raises(ValueError):
        document_digest(float("nan"))
