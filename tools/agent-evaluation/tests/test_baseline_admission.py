import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest
from pydantic import JsonValue
from test_baseline_budget import approval, frozen

from agent_evaluation.baseline_admission import (
    LayerAdmission,
    ReadinessReceipt,
    admit_native_plan,
    infrastructure_digest,
)
from agent_evaluation.baseline_runner import run
from agent_evaluation.policy import EvaluationFailure

Layer = Literal["application", "agent", "agent-evaluation"]
LAYERS: tuple[Layer, Layer, Layer] = ("application", "agent", "agent-evaluation")


def native(
    layer: Literal["application", "agent", "agent-evaluation"],
    *,
    image: str = "a" * 64,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    address = {
        "application": "azurerm_cognitive_account.models",
        "agent": "azurerm_container_app.agent[0]",
        "agent-evaluation": "azurerm_cognitive_account_project.evaluation[0]",
    }[layer]
    value: dict[str, JsonValue] = {
        "id": "authored-retained-resource",
        "template": [{"container": [{"image": "registry.test/agent@sha256:" + image}]}],
    }
    state: dict[str, JsonValue] = {
        "root_module": {
            "resources": [
                {"address": address, "mode": "managed", "values": value},
            ]
        },
    }
    return {
        "format_version": "1.2",
        "terraform_version": "1.15.8",
        "complete": True,
        "errored": False,
        "timestamp": datetime.now(UTC).isoformat(),
        "prior_state": {"values": state},
        "planned_values": copy.deepcopy(state),
        "resource_changes": [
            {
                "address": address,
                "mode": "managed",
                "provider_name": "registry.terraform.io/hashicorp/azurerm",
                "change": {
                    "actions": ["no-op"],
                    "before": value,
                    "after": copy.deepcopy(value),
                    "after_unknown": {},
                },
            }
        ],
    }, {address: value}


@pytest.mark.parametrize("layer", ["application", "agent", "agent-evaluation"])
def test_native_no_change_plan_requires_exact_retained_values(
    layer: Literal["application", "agent", "agent-evaluation"],
) -> None:
    plan, retained = native(layer)
    result = admit_native_plan(
        plan, retained, layer, reviewed_at=datetime.now(UTC), image_sha256="a" * 64
    )
    assert result.layer == layer and result.managed_resources == 1
    assert len(result.plan_sha256) == len(result.retained_resources_sha256) == 64


@pytest.mark.parametrize(
    "change",
    [
        "create",
        "update",
        "delete",
        "replace",
        "unknown",
        "import",
        "moved",
        "scope",
        "model",
        "schedule",
        "foreign",
        "failed_check",
        "drift",
        "outputs",
        "stale",
        "image",
    ],
)
def test_native_changes_and_unapproved_scope_never_admit(change: str) -> None:
    plan, retained = native("agent")
    changes = plan["resource_changes"]
    assert isinstance(changes, list) and isinstance(changes[0], dict)
    item = changes[0]
    body = item["change"]
    assert isinstance(body, dict)
    if change in ("create", "update", "delete"):
        body["actions"] = [change]
    elif change == "replace":
        body["actions"] = ["delete", "create"]
    elif change == "unknown":
        body["after_unknown"] = {"scope": True}
    elif change == "import":
        body["importing"] = {"id": "foreign"}
    elif change == "moved":
        item["previous_address"] = "foreign.resource"
    elif change in ("scope", "model", "schedule"):
        value = body["after"]
        assert isinstance(value, dict)
        value[change] = "changed"
    elif change == "foreign":
        item["provider_name"] = "registry.terraform.io/foreign/provider"
    elif change == "failed_check":
        plan["checks"] = [{"status": "fail"}]
    elif change == "drift":
        plan["resource_drift"] = [{"change": {"actions": ["update"]}}]
    elif change == "outputs":
        plan["output_changes"] = {"value": {"actions": ["create"]}}
    elif change == "stale":
        plan["timestamp"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    with pytest.raises(EvaluationFailure):
        admit_native_plan(
            plan,
            retained,
            "agent",
            reviewed_at=datetime.now(UTC),
            image_sha256="b" * 64 if change == "image" else "a" * 64,
        )


def test_source_bound_readback_rejects_configuration_or_source_drift() -> None:
    value = frozen()
    target = value.provenance.accepted_runtime
    now = datetime.now(UTC)
    receipt = ReadinessReceipt(
        protocol="baseline-readiness-v1",
        observed_at=now,
        context_sha256=value.bindings.context_sha256,
        capture_environment_sha256="b" * 64,
        evaluator_source_sha256=value.provenance.evaluator_source_sha256,
        capture_source_sha256=value.provenance.capture_source_sha256,
        production_inputs_sha256=value.provenance.production_inputs_sha256,
        infrastructure_source_sha256=infrastructure_digest(),
        runtime_receipt_sha256=target.receipt_sha256,
        image_sha256=target.image_sha256,
        configuration_sha256=target.configuration_sha256,
        scoped_before_sha256="a" * 64,
        layers=(
            LayerAdmission(
                layer="application",
                plan_sha256="1" * 64,
                retained_resources_sha256="2" * 64,
                managed_resources=1,
            ),
            LayerAdmission(
                layer="agent",
                plan_sha256="1" * 64,
                retained_resources_sha256="2" * 64,
                managed_resources=1,
            ),
            LayerAdmission(
                layer="agent-evaluation",
                plan_sha256="1" * 64,
                retained_resources_sha256="2" * 64,
                managed_resources=1,
            ),
        ),
    )
    receipt.verify(value, now)
    for field in ("configuration_sha256", "infrastructure_source_sha256", "image_sha256"):
        with pytest.raises(EvaluationFailure, match="baseline_admission_readback_mismatch"):
            receipt.model_copy(update={field: "f" * 64}).verify(value, now)


async def test_bad_approval_stops_before_any_command_or_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_evaluation.context as context

    commands: list[list[str]] = []

    def forbidden(arguments: list[str]) -> bytes:
        commands.append(arguments)
        raise AssertionError("unexpected_control_command")

    monkeypatch.setattr(context, "_read_command", forbidden)
    path = tmp_path / "approval.json"
    path.write_text(approval(frozen()).model_dump_json())
    with pytest.raises(EvaluationFailure, match="baseline_approval_fingerprint_mismatch"):
        await run(path, path, path, path, "0" * 64, tmp_path / "output")
    assert not commands and not (tmp_path / "output").exists()


async def test_mutating_plan_stops_before_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_baseline_inputs import frozen_data

    import agent_evaluation.context as context
    from agent_evaluation.baseline_inputs import FrozenBaseline

    data = frozen_data()
    target = FrozenBaseline.model_validate_json(json.dumps(data)).provenance.accepted_runtime
    plans: dict[str, JsonValue] = {}
    layers: list[LayerAdmission] = []
    now = datetime.now(UTC)
    for layer in LAYERS:
        plan, retained = native(layer, image=target.image_sha256)
        layers.append(
            admit_native_plan(
                plan,
                retained,
                layer,
                reviewed_at=datetime.now(UTC),
                image_sha256=target.image_sha256,
            )
        )
        plans[layer] = {"plan": plan, "retained": retained}
    now = datetime.now(UTC)
    value = frozen()
    receipt = ReadinessReceipt(
        protocol="baseline-readiness-v1",
        observed_at=now,
        context_sha256=value.bindings.context_sha256,
        capture_environment_sha256="b" * 64,
        evaluator_source_sha256=value.provenance.evaluator_source_sha256,
        capture_source_sha256=value.provenance.capture_source_sha256,
        production_inputs_sha256=value.provenance.production_inputs_sha256,
        infrastructure_source_sha256=infrastructure_digest(),
        runtime_receipt_sha256=target.receipt_sha256,
        image_sha256=target.image_sha256,
        configuration_sha256=target.configuration_sha256,
        scoped_before_sha256="a" * 64,
        layers=(layers[0], layers[1], layers[2]),
    )
    receipt_bytes = receipt.model_dump_json().encode()
    approved = approval(value, now).model_copy(
        update={
            "readiness_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "approved_at": now,
        }
    )
    files = [tmp_path / name for name in ("approval", "frozen", "readiness", "plans")]
    files[0].write_text(approved.model_dump_json())
    files[1].write_text(value.model_dump_json(by_alias=True))
    files[2].write_bytes(receipt_bytes)
    entry = plans["agent"]
    assert isinstance(entry, dict) and isinstance(entry["plan"], dict)
    entry["plan"]["complete"] = False
    files[3].write_text(json.dumps(plans))
    calls: list[list[str]] = []

    def forbidden(arguments: list[str]) -> bytes:
        calls.append(arguments)
        raise AssertionError("unexpected_control_command")

    monkeypatch.setattr(context, "_read_command", forbidden)
    with pytest.raises(EvaluationFailure, match="baseline_admission_incomplete_plan"):
        await run(
            files[0],
            files[1],
            files[2],
            files[3],
            hashlib.sha256(files[0].read_bytes()).hexdigest(),
            tmp_path / "output",
        )
    assert not calls and not (tmp_path / "output").exists()
