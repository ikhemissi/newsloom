import json
import logging

import pytest
from newsloom_platform.events import SafeDependencyHandler
from newsloom_platform.models import validate_contract
from pydantic import ValidationError


@pytest.mark.parametrize("size", [1535, 1537])
def test_embedding_dimensions_are_exact(size: int) -> None:
    with pytest.raises(ValidationError):
        validate_contract("embeddings", {"data": [{"embedding": [0.0] * size}]})


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True, "0.5"])
def test_embedding_rejects_nonfinite_or_non_numeric_values(invalid: object) -> None:
    vector: list[object] = [0.0] * 1535 + [invalid]
    with pytest.raises(ValidationError):
        validate_contract("embeddings", {"data": [{"embedding": vector}]})


def test_valid_embedding_contract() -> None:
    validate_contract("embeddings", {"data": [{"embedding": [0.0] * 1536}]})


@pytest.mark.parametrize("probability", [-0.1, 1.1, float("nan"), float("inf"), True, "0.5"])
def test_invalid_decision_probability_fails(probability: object) -> None:
    with pytest.raises(ValidationError):
        validate_contract(
            "screening", {"answers": {"ready": {"type": "noul", "noul": probability}}}
        )


@pytest.mark.parametrize("probability", [0.0, 0.5, 1.0])
def test_valid_decision_probability(probability: float) -> None:
    validate_contract("screening", {"answers": {"ready": {"type": "noul", "noul": probability}}})


def test_decision_requires_the_observed_typed_noul_field() -> None:
    with pytest.raises(ValidationError):
        validate_contract("screening", {"answers": {"ready": {"type": "noul", "probability": 0.5}}})


@pytest.mark.parametrize(
    "content", ['{"ready":false}', '{"ready":1}', '{"ready":true,"extra":"canary"}', "not JSON"]
)
def test_enrichment_requires_closed_affirmative_schema(content: str) -> None:
    with pytest.raises((ValidationError, json.JSONDecodeError)):
        validate_contract(
            "enrichment",
            {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
        )


def test_dependency_messages_cannot_expose_payloads(capsys: pytest.CaptureFixture[str]) -> None:
    record = logging.LogRecord(
        "httpx", logging.WARNING, __file__, 1, "CONTENT_TOKEN_CANARY %s", ("prompt",), None
    )
    SafeDependencyHandler().handle(record)
    output = capsys.readouterr().out
    assert "CONTENT_TOKEN_CANARY" not in output
    assert "prompt" not in output
    assert json.loads(output)["outcome"] == "warning"
