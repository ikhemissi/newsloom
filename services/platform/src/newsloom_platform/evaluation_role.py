"""Exact additive built-in Foundry role transitions, not evaluation execution."""

import base64
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, model_validator

from newsloom_platform import agent_evaluation, control
from newsloom_platform import evaluation_verification as verification
from newsloom_platform.config import PlatformFailure, json_object
from newsloom_platform.events import event

ADDRESS = "azurerm_role_assignment.foundry_user[0]"
OUTPUT = "AGENT_EVALUATION_FOUNDRY_USER_ASSIGNMENT_BASE64"
MANAGER_ADDRESS = "azurerm_role_assignment.foundry_project_manager[0]"
MANAGER_OUTPUT = "AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ASSIGNMENT_BASE64"
Role = Literal["foundry-user", "foundry-project-manager"]


def empty_set_refresh(address: str, before: object, after: object) -> bool:
    if address == "azurerm_cognitive_account_project.evaluation[0]":
        block, field = "identity", "identity_ids"
    elif address in {
        'azurerm_role_definition.operator["chat"]',
        'azurerm_role_definition.operator["evaluations"]',
    }:
        block, field = "permissions", "not_data_actions"
    else:
        return False
    normalized = json_object(before)
    target = json_object(after)
    old_rows = verification.rows(normalized.get(block))
    new_rows = verification.rows(target.get(block))
    if (
        len(old_rows) != 1
        or len(new_rows) != 1
        or field not in old_rows[0]
        or old_rows[0][field] is not None
        or new_rows[0].get(field) != []
    ):
        return False
    old_rows[0][field] = []
    normalized[block] = old_rows
    return normalized == target


def grant_output_refresh(output: dict[str, object]) -> bool:
    if output.get("actions") != ["update"] or output.get("after_unknown") not in (False, None):
        return False
    before = json_object(json.loads(base64.b64decode(str(output["before"]), validate=True)))
    after = json_object(json.loads(base64.b64decode(str(output["after"]), validate=True)))
    if set(before) != set(verification.PERMISSIONS) or set(after) != set(before):
        return False
    for label in before:
        original, current = json_object(before[label]), json_object(after[label])
        if (
            "not_data_actions" not in original
            or original["not_data_actions"] is not None
            or current.get("not_data_actions") != []
        ):
            return False
        before[label] = {**original, "not_data_actions": []}
    return before == after


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    mode: Literal["plan", "readback"]
    role: Role = "foundry-user"
    foundation: str
    foundation_sha256: str
    plan: str
    output: str
    review: str | None = None
    apply_receipt: str | None = None

    @model_validator(mode="after")
    def boundaries(self) -> Manifest:
        if (self.review is not None, self.apply_receipt is not None) != (
            self.mode == "readback",
            self.mode == "readback",
        ):
            raise ValueError("Readback requires the review and completed apply receipts.")
        return self


def expected(env: dict[str, str], role: Role = "foundry-user") -> dict[str, str]:
    identifier = (
        agent_evaluation.foundry_user_role_id(env)
        if role == "foundry-user"
        else agent_evaluation.foundry_project_manager_role_id(env)
    )
    if not identifier:
        raise PlatformFailure("evaluation_role_explicit_approval_input_required")
    project = verification.project_id(env)
    principal = env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"]
    name = str(uuid5(NAMESPACE_URL, f"{project}/{role}/{principal}"))
    return {
        "id": f"{project}/providers/Microsoft.Authorization/roleAssignments/{name}",
        "principal_id": principal,
        "principal_type": "User",
        "role_definition_id": (
            f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
            f"/providers/Microsoft.Authorization/roleDefinitions/{identifier}"
        ),
        "scope": project,
    }


def plan_inventory(
    plan: dict[str, object], env: dict[str, str], role: Role = "foundry-user"
) -> dict[str, object]:
    wanted = expected(env, role)
    address = ADDRESS if role == "foundry-user" else MANAGER_ADDRESS
    output_name = OUTPUT if role == "foundry-user" else MANAGER_OUTPUT
    resources = verification.indexed(plan.get("resource_changes"))
    resource = resources.get(address, {})
    change = json_object(resource.get("change"))
    after = json_object(change.get("after"))
    if (
        resource.get("mode") != "managed"
        or resource.get("provider_name") != "registry.terraform.io/hashicorp/azurerm"
        or resource.get("previous_address")
        or change.get("actions") != ["create"]
        or change.get("before") is not None
        or change.get("importing")
        or change.get("replace_paths")
        or any(after.get(key) != value for key, value in wanted.items() if key != "id")
        or after.get("name") != wanted["id"].rsplit("/", 1)[1]
        or after.get("id") not in (None, wanted["id"])
        or any(
            after.get(key) not in (None, "")
            for key in ("condition", "condition_version", "delegated_managed_identity_resource_id")
        )
        or after.get("skip_service_principal_aad_check") not in (None, False)
        or not verification.unknown_paths(change.get("after_unknown"))
        <= {
            ("id",),
            ("role_definition_name",),
            ("condition_version",),
            ("skip_service_principal_aad_check",),
        }
    ):
        raise PlatformFailure("evaluation_role_assignment_plan_mismatch")
    reduced = deepcopy(plan)
    refreshes = verification.indexed(reduced.get("resource_drift", []))
    for drift_address, drift in refreshes.items():
        delta = json_object(drift.get("change"))
        if delta.get("actions") == ["no-op"]:
            continue
        if delta.get("actions") != ["update"] or not empty_set_refresh(
            drift_address, delta.get("before"), delta.get("after")
        ):
            raise PlatformFailure("evaluation_role_unapproved_refresh_drift")
        drift["change"] = {**delta, "actions": ["no-op"]}
    reduced["resource_drift"] = list(refreshes.values())
    reduced["resource_changes"] = [row for key, row in resources.items() if key != address]
    prior = json_object(
        json_object(json_object(reduced.get("prior_state")).get("values")).get("root_module")
    )
    planned = json_object(json_object(reduced.get("planned_values")).get("root_module"))
    if address in verification.indexed(prior.get("resources")):
        raise PlatformFailure("evaluation_role_assignment_already_in_state")
    planned_resources = verification.indexed(planned.get("resources"))
    if planned_resources.get(address, {}).get("values") != after:
        raise PlatformFailure("evaluation_role_plan_state_mismatch")
    planned["resources"] = [row for key, row in planned_resources.items() if key != address]
    reduced["planned_values"] = {
        **json_object(reduced.get("planned_values")),
        "root_module": planned,
    }
    if role == "foundry-project-manager":
        retained = resources.get(ADDRESS, {})
        retained_change = json_object(retained.get("change"))
        retained_after = json_object(retained_change.get("after"))
        retained_expected = expected(env)
        if (
            retained.get("mode") != "managed"
            or retained.get("provider_name") != "registry.terraform.io/hashicorp/azurerm"
            or retained.get("previous_address")
            or retained_change.get("actions") != ["no-op"]
            or retained_change.get("before") != retained_after
            or verification.unknown_paths(retained_change.get("after_unknown"))
            or retained_change.get("importing")
            or retained_change.get("replace_paths")
            or any(retained_after.get(key) != value for key, value in retained_expected.items())
            or retained_after.get("name") != retained_expected["id"].rsplit("/", 1)[1]
            or any(
                retained_after.get(key) not in (None, "")
                for key in (
                    "condition",
                    "condition_version",
                    "delegated_managed_identity_resource_id",
                )
            )
        ):
            raise PlatformFailure("evaluation_role_retained_builtin_changed")
        for module in (prior, planned):
            entries = verification.indexed(module.get("resources"))
            if entries.get(ADDRESS, {}).get("values") != retained_after:
                raise PlatformFailure("evaluation_role_retained_builtin_changed")
            module["resources"] = [row for key, row in entries.items() if key != ADDRESS]
        reduced["resource_changes"] = [
            row
            for row in verification.rows(reduced["resource_changes"])
            if row.get("address") != ADDRESS
        ]
        prior_values = json_object(json_object(reduced.get("prior_state")).get("values"))
        prior_values["root_module"] = prior
        reduced["prior_state"] = {**json_object(reduced.get("prior_state")), "values": prior_values}
    retained = verification.verify_plan(reduced, env, "agent-evaluation")
    if retained["mutations"] != 0:
        raise PlatformFailure("evaluation_role_retained_resource_mutation")
    variables = json_object(plan.get("variables"))
    input_name = (
        "foundry_user_role_id" if role == "foundry-user" else "foundry_project_manager_role_id"
    )
    if (
        json_object(variables.get(input_name)).get("value")
        != wanted["role_definition_id"].rsplit("/", 1)[1]
    ):
        raise PlatformFailure("evaluation_role_input_mismatch")
    outputs = json_object(plan.get("output_changes"))
    if json_object(outputs.get(output_name)).get("actions") != ["create"]:
        raise PlatformFailure("evaluation_role_output_mismatch")
    for key, value in outputs.items():
        if key == output_name:
            continue
        output = json_object(value)
        if key == "AGENT_EVALUATION_GRANTS_BASE64" and grant_output_refresh(output):
            continue
        if (
            output.get("actions") != ["no-op"]
            or output.get("before") != output.get("after")
            or verification.unknown_paths(output.get("after_unknown"))
        ):
            raise PlatformFailure("evaluation_role_unrelated_output_change")
    return {
        "additions": 1,
        "changes": 0,
        "destroys": 0,
        "assignment": wanted,
        "empty_set_state_refreshes": sum(
            json_object(row.get("change")).get("actions") == ["update"]
            for row in verification.rows(plan.get("resource_drift", []))
        ),
        "empty_exclusion_output_refresh": "AGENT_EVALUATION_GRANTS_BASE64" in outputs
        and grant_output_refresh(json_object(outputs["AGENT_EVALUATION_GRANTS_BASE64"])),
    }


def assignment(
    value: dict[str, object], env: dict[str, str], role: Role = "foundry-user"
) -> dict[str, str]:
    wanted = expected(env, role)
    properties = json_object(value.get("properties"))
    native = {
        "id": value.get("id"),
        "principal_id": properties.get("principalId"),
        "principal_type": properties.get("principalType"),
        "role_definition_id": properties.get("roleDefinitionId"),
        "scope": properties.get("scope"),
    }
    if native != wanted or any(
        properties.get(key) not in (None, "")
        for key in ("condition", "conditionVersion", "delegatedManagedIdentityResourceId")
    ):
        raise PlatformFailure("evaluation_role_assignment_readback_mismatch")
    exported = json.loads(
        base64.b64decode(env[OUTPUT if role == "foundry-user" else MANAGER_OUTPUT], validate=True)
    )
    if exported != wanted:
        raise PlatformFailure("evaluation_role_assignment_output_mismatch")
    return wanted


def verify(env: dict[str, str], correlation: str, manifest_path: str) -> None:
    root = Path(control.run(["git", "rev-parse", "--show-toplevel"], "project_root"))
    evidence = verification.Evidence(root, env["AZURE_ENV_NAME"])
    manifest = Manifest.model_validate(evidence.document(manifest_path))
    if evidence.path(manifest.output).exists():
        raise PlatformFailure("evaluation_role_output_already_exists")
    original = evidence.read(manifest.foundation)
    if hashlib.sha256(original).hexdigest() != verification.fingerprint(manifest.foundation_sha256):
        raise PlatformFailure("evaluation_role_foundation_changed")
    foundation = evidence.document(manifest.foundation)
    context = verification.context(env)
    if (
        foundation.get("outcome") != "success"
        or foundation.get("mode") != "readback"
        or foundation.get("layer") != "agent-evaluation"
        or foundation.get("context_sha256") != context
        or foundation.get("verification_scope") != verification.verification_scope(env)
    ):
        raise PlatformFailure("evaluation_role_historical_foundation_required")
    binary = evidence.read(manifest.plan)
    owning = root / "infra/agent-evaluation"
    verification.binary_source(binary, owning)
    native = control.run(
        ["terraform", f"-chdir={owning}", "show", "-json", str(evidence.path(manifest.plan))],
        "evaluation_role_native_plan",
        timeout=60,
    )
    if len(native.encode()) > verification.MAX_BYTES:
        raise PlatformFailure("evaluation_role_native_plan_too_large")
    inventory = plan_inventory(json_object(json.loads(native)), env, manifest.role)
    binding = {
        "source_sha256": verification.source(root),
        "context_sha256": context,
        "foundation_sha256": manifest.foundation_sha256,
        "foundation_source_sha256": verification.fingerprint(foundation.get("source_sha256")),
        "plan_sha256": hashlib.sha256(binary).hexdigest(),
        "plan_inventory": inventory,
    }
    reader = verification.Reader(env)
    verification.operator(reader, env)
    if manifest.mode == "readback":
        assert manifest.review is not None and manifest.apply_receipt is not None
        review = evidence.document(manifest.review)
        if (
            review.get("mode") != f"{manifest.role}-plan"
            or review.get("outcome") != "success"
            or any(review.get(key) != value for key, value in binding.items())
        ):
            raise PlatformFailure("evaluation_role_review_binding_changed")
        verification.fresh(review.get("verified_utc"))
        completed = evidence.document(manifest.apply_receipt)
        if (
            completed.get("azd_exit_code") != 0
            or completed.get("source_sha256") != binding["source_sha256"]
            or completed.get("plan_sha256") != binding["plan_sha256"]
            or completed.get("review_sha256")
            != hashlib.sha256(evidence.read(manifest.review)).hexdigest()
        ):
            raise PlatformFailure("evaluation_role_completed_apply_required")
        verification.fresh(completed.get("completed_utc"))
        assignment(
            reader.get(expected(env, manifest.role)["id"], verification.ROLE_API),
            env,
            manifest.role,
        )
    evidence.write(
        manifest.output,
        {
            **binding,
            "mode": f"{manifest.role}-{manifest.mode}",
            "outcome": "success",
            "verified_utc": datetime.now(UTC).isoformat(),
            "assignment_metadata_reads": int(manifest.mode == "readback"),
            "resource_mutations": 0,
            "model_calls": 0,
            "preservation_claim": "exact role delta only; historical foundation not rerun",
            "provider_exception": f"exact {manifest.role} definition GETs only; no role inventory",
        },
    )
    event("evaluation_role", manifest.mode, correlation, checks=1)
