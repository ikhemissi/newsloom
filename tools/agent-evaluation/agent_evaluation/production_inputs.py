"""Versioned production manifest pins without evaluation execution or mutable history."""

import hashlib
import json
from pathlib import Path
from typing import Final

from agent_evaluation.inputs import ROOT
from agent_evaluation.policy import EvaluationFailure

PRODUCTION_INPUTS: Final = {
    "pyproject.toml": "0e676e369ce0abd956518993ad40fb112bc1f5084abb3f52c55e72dbab8aef59",
    "uv.lock": "6cab3f29a6220f1e3c92585df919ccda964752eb7ee94790d78fddb3648a1aed",
    "packages/newsloom-core/pyproject.toml": (
        "2e4fb451d4cdc36b2d65be7e7d9509455e0efe45fc527b34adeb7aed66d9a8ff"
    ),
    "services/ingestion/pyproject.toml": (
        "098191abd85efaf3860f2bfbdd4d74bc05436a66d00c5f68542ffc484bff66a6"
    ),
    "services/enrichment/pyproject.toml": (
        "42d70e5fb3d4fe386560efe45c94d813b84c6c0f044427650ec8f46e30f13a09"
    ),
    "services/mcp/pyproject.toml": (
        "6de4a007830b10a17bcbaff17628dfc5f9ae2efe8c728d967db96797c32d0056"
    ),
    "services/agent/pyproject.toml": (
        "9829cd98e4e83d366a7d59763bb1a3c4f1b71bc7eca886fc7da9dd37e40a613b"
    ),
    "services/platform/pyproject.toml": (
        "f85c57fee0f15704135dab3b1c79f1aae81aae399b855e70ce79109d4fd13617"
    ),
}
PRODUCTION_INPUTS_V2: Final = {
    **PRODUCTION_INPUTS,
    "pyproject.toml": "6e5752df055ffe2ce652b35093ab00953ea6a467a01a52225a92b368501c5cbe",
}


def document_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def verify_production_inputs(root: Path = ROOT, *, expected_sha256: str | None = None) -> str:
    try:
        actual = {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in PRODUCTION_INPUTS
        }
    except OSError:
        raise EvaluationFailure("baseline_production_inputs_unavailable") from None
    if actual not in (PRODUCTION_INPUTS, PRODUCTION_INPUTS_V2):
        raise EvaluationFailure("baseline_production_inputs_changed")
    digest = document_digest(actual)
    if expected_sha256 is not None and expected_sha256 != digest:
        raise EvaluationFailure("baseline_provenance_mismatch")
    return digest
