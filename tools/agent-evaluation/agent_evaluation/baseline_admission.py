import hashlib
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, JsonValue, StrictInt, model_validator

from agent_evaluation.baseline_inputs import FrozenBaseline
from agent_evaluation.baseline_provenance import Digest, document_digest
from agent_evaluation.inputs import ROOT, StrictModel
from agent_evaluation.policy import EvaluationFailure


def infrastructure_paths() -> list[Path]:
    return [
        ROOT / "azure.yaml",
        *sorted(
            {
                path
                for directory in (
                    ROOT / "infra",
                    ROOT / "infra/agent",
                    ROOT / "infra/agent-evaluation",
                )
                for path in (*directory.glob("*.tf"), directory / ".terraform.lock.hcl")
            }
        ),
    ]


def infrastructure_digest() -> str:
    try:
        return document_digest(
            {
                path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in infrastructure_paths()
            }
        )
    except OSError:
        raise EvaluationFailure("baseline_admission_source_unavailable") from None


def owning_addresses(layer: str) -> set[str]:
    directory = (
        ROOT
        / {
            "application": "infra",
            "agent": "infra/agent",
            "agent-evaluation": "infra/agent-evaluation",
        }[layer]
    )
    try:
        return {
            kind + "." + name
            for path in directory.glob("*.tf")
            for kind, name in re.findall(
                r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*\{',
                path.read_text(),
                re.MULTILINE,
            )
        }
    except OSError:
        raise EvaluationFailure("baseline_admission_source_unavailable") from None


def object_value(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise EvaluationFailure("baseline_admission_object_required")
    return value


def resources(value: JsonValue) -> dict[str, dict[str, JsonValue]]:
    if not isinstance(value, list) or not value:
        raise EvaluationFailure("baseline_admission_resources_required")
    result: dict[str, dict[str, JsonValue]] = {}
    for row in value:
        item = object_value(row)
        address = item.get("address")
        if not isinstance(address, str) or address in result:
            raise EvaluationFailure("baseline_admission_resource_inventory")
        result[address] = item
    return result


class LayerAdmission(StrictModel):
    layer: Literal["application", "agent", "agent-evaluation"]
    plan_sha256: Digest
    retained_resources_sha256: Digest
    managed_resources: StrictInt = Field(ge=1, le=128)


class ReadinessReceipt(StrictModel):
    protocol: Literal["baseline-readiness-v1"]
    observed_at: datetime
    context_sha256: Digest
    capture_environment_sha256: Digest
    evaluator_source_sha256: Digest
    capture_source_sha256: Digest
    production_inputs_sha256: Digest
    infrastructure_source_sha256: Digest
    runtime_receipt_sha256: Digest
    image_sha256: Digest
    configuration_sha256: Digest
    scoped_before_sha256: Digest
    layers: tuple[LayerAdmission, LayerAdmission, LayerAdmission]

    @model_validator(mode="after")
    def exact_layers(self) -> Self:
        if tuple(row.layer for row in self.layers) != (
            "application",
            "agent",
            "agent-evaluation",
        ) or self.observed_at.utcoffset() != UTC.utcoffset(None):
            raise ValueError("baseline_admission_layer_set")
        return self

    def verify(self, frozen: FrozenBaseline, approved_at: datetime) -> None:
        provenance = frozen.provenance
        runtime = frozen.bindings.accepted_runtime
        if (
            not timedelta(0) <= approved_at - self.observed_at <= timedelta(hours=1)
            or self.context_sha256 != frozen.bindings.context_sha256
            or self.evaluator_source_sha256 != provenance.evaluator_source_sha256
            or self.capture_source_sha256 != provenance.capture_source_sha256
            or self.production_inputs_sha256 != provenance.production_inputs_sha256
            or self.infrastructure_source_sha256 != infrastructure_digest()
            or self.runtime_receipt_sha256 != runtime.receipt_sha256
            or self.image_sha256 != runtime.image_sha256
            or self.configuration_sha256 != runtime.configuration_sha256
        ):
            raise EvaluationFailure("baseline_admission_readback_mismatch")
        provenance.verify_current(runtime)


def admit_native_plan(
    plan: dict[str, JsonValue],
    retained: dict[str, JsonValue],
    layer: Literal["application", "agent", "agent-evaluation"],
    *,
    reviewed_at: datetime,
    image_sha256: str,
) -> LayerAdmission:
    try:
        timestamp = plan.get("timestamp")
        observed = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else None
        if (
            plan.get("format_version") != "1.2"
            or plan.get("terraform_version") != "1.15.8"
            or plan.get("complete") is not True
            or plan.get("errored") is not False
            or plan.get("deferred_changes")
            or plan.get("resource_drift")
            or observed is None
            or observed.utcoffset() != UTC.utcoffset(None)
            or not timedelta(0) <= reviewed_at - observed <= timedelta(hours=1)
        ):
            raise EvaluationFailure("baseline_admission_incomplete_plan")
        checks = plan.get("checks", [])
        if not isinstance(checks, list) or any(
            object_value(row).get("status") != "pass" for row in checks
        ):
            raise EvaluationFailure("baseline_admission_failed_check")
        prior = object_value(object_value(plan["prior_state"])["values"])
        after = object_value(plan["planned_values"])
        before_module = object_value(prior["root_module"])
        after_module = object_value(after["root_module"])
        if before_module.get("child_modules") or after_module.get("child_modules"):
            raise EvaluationFailure("baseline_admission_foreign_module")
        before = {
            key: row["values"]
            for key, row in resources(before_module["resources"]).items()
            if row.get("mode") == "managed"
        }
        planned = {
            key: row["values"]
            for key, row in resources(after_module["resources"]).items()
            if row.get("mode") == "managed"
        }
        if before != retained or planned != retained:
            raise EvaluationFailure("baseline_admission_retained_state_mismatch")
        managed: set[str] = set()
        owned = owning_addresses(layer)
        for address, row in resources(plan["resource_changes"]).items():
            change = object_value(row["change"])
            if (
                row.get("previous_address")
                or change.get("importing")
                or change.get("replace_paths")
                or change.get("actions") != ["no-op"]
                or change.get("before") != change.get("after")
                or change.get("after_unknown") not in (None, False, {})
            ):
                raise EvaluationFailure("baseline_admission_mutation_rejected")
            if row.get("mode") == "managed":
                provider = (
                    "registry.terraform.io/hashicorp/azurerm"
                    if address.startswith("azurerm_")
                    else "registry.terraform.io/azure/azapi"
                    if address.startswith("azapi_")
                    else None
                )
                if (
                    address.split("[", 1)[0] not in owned
                    or provider is None
                    or row.get("provider_name") != provider
                ):
                    raise EvaluationFailure("baseline_admission_foreign_resource")
                managed.add(address)
                if change.get("before") != retained.get(address):
                    raise EvaluationFailure("baseline_admission_resource_mismatch")
            elif (
                row.get("mode") != "data"
                or address
                not in {
                    "data.azurerm_client_config.current",
                    "data.azurerm_client_config.current[0]",
                    "data.azurerm_container_app_environment.existing[0]",
                }
                or row.get("provider_name") != "registry.terraform.io/hashicorp/azurerm"
            ):
                raise EvaluationFailure("baseline_admission_resource_mode")
        if managed != set(retained):
            raise EvaluationFailure("baseline_admission_resource_inventory")
        outputs = plan.get("output_changes", {})
        if not isinstance(outputs, dict) or any(
            object_value(row).get("actions") != ["no-op"]
            or object_value(row).get("before") != object_value(row).get("after")
            or object_value(row).get("after_unknown") not in (None, False, {})
            for row in outputs.values()
        ):
            raise EvaluationFailure("baseline_admission_output_change")
        if layer == "agent":
            app = object_value(retained["azurerm_container_app.agent[0]"])
            templates = app.get("template")
            if not isinstance(templates, list) or len(templates) != 1:
                raise EvaluationFailure("baseline_admission_agent_template")
            containers = object_value(templates[0]).get("container")
            if not isinstance(containers, list) or len(containers) != 1:
                raise EvaluationFailure("baseline_admission_agent_template")
            image = object_value(containers[0]).get("image")
            if not isinstance(image, str) or not image.endswith("@sha256:" + image_sha256):
                raise EvaluationFailure("baseline_admission_agent_image")
        return LayerAdmission(
            layer=layer,
            plan_sha256=document_digest(plan),
            retained_resources_sha256=document_digest(retained),
            managed_resources=len(managed),
        )
    except KeyError, TypeError, ValueError:
        raise EvaluationFailure("baseline_admission_invalid_plan") from None
