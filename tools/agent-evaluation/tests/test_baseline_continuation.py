import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from test_baseline_budget import Recorder, approval, frozen, ready

from agent_evaluation.baseline_budget import BaselineApproval, BaselineBudget, BaselineBudgetReceipt
from agent_evaluation.baseline_inputs import FrozenBaseline
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.baseline_runner import run
from agent_evaluation.policy import EvaluationFailure


def test_legacy_default_serialization_keeps_prior_hash_and_snapshot_shape() -> None:
    value = frozen()
    approved = approval(value)
    raw = approved.model_dump(mode="json")
    assert "prior_usage_sha256" not in raw and "prior_model_exposure_usd" not in raw
    assert "snapshot_version" not in value.model_dump(mode="json")
    restored = BaselineApproval.model_validate_json(approved.model_dump_json())
    assert document_digest(restored.model_dump(mode="json")) == document_digest(raw)
    upgraded = value.model_copy(update={"snapshot_version": 2})
    upgraded = FrozenBaseline.model_validate_json(upgraded.model_dump_json(by_alias=True))
    assert upgraded.snapshot_version == 2
    assert document_digest(upgraded.model_dump(mode="json", by_alias=True)) != document_digest(
        value.model_dump(mode="json", by_alias=True)
    )
    assert upgraded.request_document("b05") == value.request_document("b05")


async def test_prior_unknown_exposure_remains_inside_combined_ceiling() -> None:
    value = frozen()
    data = approval(value).model_dump(mode="json")
    data.update(
        {
            "limit_profile": "baseline-12x8-v6",
            "maximum_usd": "100",
            "prior_usage_sha256": "a" * 64,
            "prior_model_exposure_usd": "1",
        }
    )
    approved = BaselineApproval.model_validate_json(json.dumps(data))
    recorder = Recorder()
    budget = BaselineBudget(approved, value, persist=recorder, ready=ready)
    await budget.start()
    assert budget.receipt().combined_exposure_usd == "1"
    assert budget.receipt().prior_model_exposure_usd == "1"
    budget.check_extra_cost(Decimal("99"))
    with pytest.raises(EvaluationFailure, match="baseline_combined_reservation_limit"):
        budget.check_extra_cost(Decimal("99.000000001"))
    await budget.admit_agent("b01")
    assert Decimal(budget.receipt().combined_exposure_usd) > 1
    restored = BaselineBudgetReceipt.model_validate_json(budget.receipt().model_dump_json())
    assert restored.prior_model_exposure_usd == "1"
    assert restored.original_expires_at == approved.expires_at
    assert budget.judge.receipt().estimated_observed_usd == "0"


async def test_snapshot2_cannot_omit_prior_history(tmp_path: Path) -> None:
    value = frozen().model_copy(update={"snapshot_version": 2})
    data = approval(frozen()).model_dump(mode="json")
    data["frozen_sha256"] = document_digest(value.model_dump(mode="json", by_alias=True))
    encoded = BaselineApproval.model_validate_json(json.dumps(data)).model_dump_json().encode()
    manifest, inputs = tmp_path / "approval.json", tmp_path / "frozen.json"
    manifest.write_bytes(encoded)
    inputs.write_text(value.model_dump_json(by_alias=True))
    with pytest.raises(EvaluationFailure, match="baseline_prior_usage_required"):
        await run(
            manifest,
            inputs,
            tmp_path / "unused",
            tmp_path / "unused",
            hashlib.sha256(encoded).hexdigest(),
            tmp_path / "output",
        )
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("amount", ["101", "PRIVATE_CONTENT", "-1"])
def test_unbounded_or_unbound_prior_exposure_is_rejected(amount: str) -> None:
    data = approval(frozen()).model_dump(mode="json")
    data.update(
        {
            "limit_profile": "baseline-12x8-v6",
            "maximum_usd": "100",
            "prior_model_exposure_usd": amount,
        }
    )
    with pytest.raises(ValueError):
        BaselineApproval.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("failure", ["missing", "hash", "amount"])
async def test_prior_receipt_fails_closed_before_any_environment_or_model_call(
    tmp_path: Path,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_evaluation import context

    def forbidden(arguments: list[str]) -> bytes:
        raise AssertionError("unexpected_environment_or_model_work")

    monkeypatch.setattr(context, "_read_command", forbidden)
    value = frozen()
    previous = json.dumps(
        {
            "estimated_usd": {
                "conservative_combined_exposure": "2" if failure == "amount" else "1"
            },
        }
    ).encode()
    data = approval(value, datetime.now(UTC)).model_dump(mode="json")
    data.update(
        {
            "limit_profile": "baseline-12x8-v6",
            "maximum_usd": "100",
            "prior_usage_sha256": "0" * 64
            if failure == "hash"
            else hashlib.sha256(previous).hexdigest(),
            "prior_model_exposure_usd": "1",
        }
    )
    encoded = BaselineApproval.model_validate_json(json.dumps(data)).model_dump_json().encode()
    manifest, frozen_path, prior = (
        tmp_path / "approval.json",
        tmp_path / "frozen.json",
        tmp_path / "prior.json",
    )
    manifest.write_bytes(encoded)
    frozen_path.write_text(value.model_dump_json(by_alias=True))
    prior.write_bytes(previous)
    with pytest.raises(EvaluationFailure, match="baseline_prior_usage"):
        await run(
            manifest,
            frozen_path,
            tmp_path / "unused-readiness",
            tmp_path / "unused-plans",
            hashlib.sha256(encoded).hexdigest(),
            tmp_path / "output",
            prior_usage=None if failure == "missing" else prior,
        )
    assert not (tmp_path / "output").exists()
