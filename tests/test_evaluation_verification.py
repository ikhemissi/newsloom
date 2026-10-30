import base64
import hashlib
import io
import json
import os
import sys
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from newsloom_platform import cli, control, evaluation_role
from newsloom_platform import evaluation_verification as verification
from newsloom_platform.config import PlatformFailure, json_object

PROVIDER = "registry.terraform.io/hashicorp/azurerm"
FOUNDRY_USER = str(UUID(int=0x53CA6127DB724B80B1B0D745D6D5456D))


@pytest.fixture
def env() -> dict[str, str]:
    subscription, tenant, operator = (str(uuid4()) for _ in range(3))
    name = "test"
    suffix = hashlib.sha256(f"{subscription}/{name}".encode()).hexdigest()[:8]
    account = f"ai-newsloom-{name}-{suffix}"
    group = f"/subscriptions/{subscription}/resourceGroups/rg-newsloom-test"
    return {
        "AZURE_SUBSCRIPTION_ID": subscription,
        "AZURE_ENV_NAME": name,
        "AZURE_RESOURCE_GROUP": "rg-newsloom-test",
        "AZURE_LOCATION": "francecentral",
        "AGENT_TENANT_ID": tenant,
        "AGENT_EVALUATION_TENANT_ID": tenant,
        "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID": operator,
        "MODEL_ACCOUNT_ID": group + "/providers/Microsoft.CognitiveServices/accounts/" + account,
        "MODEL_ACCOUNT_NAME": account,
        "MODEL_ENDPOINT": f"https://{account}.services.ai.azure.com/",
        "ENRICHMENT_DEPLOYMENT": "chat",
        "ENRICHMENT_MODEL": "gpt-5.4-mini",
        "ENRICHMENT_VERSION": "2026-03-17",
        "ENRICHMENT_FORMAT": "OpenAI",
        "ENRICHMENT_SKU": "DataZoneStandard",
        "ENRICHMENT_CAPACITY": "10",
        "POSTGRES_SERVER_NAME": "postgres-retained",
        "POSTGRES_DATABASE": "newsloom",
        **{
            key: str(uuid4())
            for key in (
                "MCP_API_CLIENT_ID",
                "MCP_PUBLIC_CLIENT_ID",
                "AGENT_API_CLIENT_ID",
                "AGENT_PUBLIC_CLIENT_ID",
            )
        },
    }


def account_values(env: dict[str, str]) -> dict[str, object]:
    return {
        "id": env["MODEL_ACCOUNT_ID"],
        "name": env["MODEL_ACCOUNT_NAME"],
        "kind": "AIServices",
        "sku_name": "S0",
        "local_auth_enabled": False,
        "project_management_enabled": False,
        "identity": [],
        "custom_subdomain_name": env["MODEL_ACCOUNT_NAME"],
        "endpoint": "https://retained.invalid/",
        "tags": {"project": "newsloom"},
    }


def plan_for(env: dict[str, str], layer: str) -> dict[str, object]:
    changes: list[dict[str, object]] = []
    prior: list[dict[str, object]] = []
    planned: list[dict[str, object]] = []

    def add(address: str, after: dict[str, object], unknown: dict[str, object]) -> None:
        before = None
        if layer == "application":
            before = deepcopy(after)
            if address == "azurerm_cognitive_account.models":
                before = account_values(env)
            prior.append({"address": address, "mode": "managed", "values": before})
        action = "update" if layer == "application" else "create"
        if before == after:
            action = "no-op"
        changes.append(
            {
                "address": address,
                "mode": "managed",
                "provider_name": PROVIDER,
                "change": {
                    "actions": [action],
                    "before": before,
                    "after": after,
                    "after_unknown": unknown,
                },
            }
        )
        planned.append({"address": address, "mode": "managed", "values": after})

    if layer == "application":
        for address in sorted(verification.application_addresses()):
            after: dict[str, object] = {"id": address}
            unknown: dict[str, object] = {}
            if address == "azurerm_cognitive_account.models":
                after = account_values(env)
                after["project_management_enabled"] = True
                after["identity"] = [
                    {
                        "type": "SystemAssigned",
                        "identity_ids": [],
                        "principal_id": None,
                        "tenant_id": None,
                    }
                ]
                unknown = {"identity": [{"principal_id": True, "tenant_id": True}]}
            add(address, after, unknown)
    else:
        add(
            "azurerm_cognitive_account_project.evaluation[0]",
            {
                "id": None,
                "name": "eval-newsloom-test",
                "cognitive_account_id": env["MODEL_ACCOUNT_ID"],
                "location": env["AZURE_LOCATION"],
                "identity": [{"type": "SystemAssigned"}],
            },
            {
                "id": True,
                "default": True,
                "endpoints": True,
                "identity": [{"principal_id": True, "tenant_id": True}],
            },
        )
        for label in verification.PERMISSIONS:
            add(
                f'azurerm_role_definition.operator["{label}"]',
                {
                    "id": None,
                    "role_definition_resource_id": None,
                    "name": f"newsloom-test-agent-evaluation-{label}",
                    "scope": verification.group_id(env),
                    "assignable_scopes": [verification.group_id(env)],
                    "permissions": [
                        {**verification.permission_row(label), "not_data_actions": None}
                    ],
                },
                {"id": True, "role_definition_resource_id": True, "role_definition_id": True},
            )
            add(
                f'azurerm_role_assignment.operator["{label}"]',
                {
                    "id": None,
                    "role_definition_id": None,
                    "scope": env["MODEL_ACCOUNT_ID"] if label == "chat" else None,
                    "principal_id": env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
                    "principal_type": "User",
                },
                {
                    "id": True,
                    "name": True,
                    "role_definition_id": True,
                    **({"scope": True} if label == "evaluations" else {}),
                },
            )
    configuration = {
        "provider_config": {
            "azurerm": {
                "version_constraint": "5.10.0",
            }
        },
        "root_module": {
            "resources": [
                {
                    "address": "azurerm_role_assignment.operator",
                    "expressions": {
                        "scope": {
                            "references": [
                                "each.key",
                                "var.model_account_id",
                                "azurerm_cognitive_account_project.evaluation[0].id",
                            ]
                        },
                        "role_definition_id": {
                            "references": ["each.key", "azurerm_role_definition.operator"]
                        },
                    },
                }
            ]
        },
    }
    inputs: dict[str, object] = {
        "subscription_id": env["AZURE_SUBSCRIPTION_ID"],
        "environment_name": "test",
        "resource_group_name": env["AZURE_RESOURCE_GROUP"],
        "location": env["AZURE_LOCATION"],
    }
    if layer != "application":
        inputs.update(
            enabled=True,
            tenant_id=env["AGENT_TENANT_ID"],
            operator_principal_id=env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
            model_account_id=env["MODEL_ACCOUNT_ID"],
            model_endpoint=env["MODEL_ENDPOINT"],
        )
    return {
        "format_version": "1.2",
        "terraform_version": "1.15.8",
        "complete": True,
        "errored": False,
        "timestamp": datetime.now(UTC).isoformat(),
        "variables": {key: {"value": value} for key, value in inputs.items()},
        "configuration": configuration,
        "resource_changes": changes,
        "prior_state": {"values": {"root_module": {"resources": prior}}},
        "planned_values": {"root_module": {"resources": planned}},
    }


def change(plan: dict[str, object], address: str) -> dict[str, object]:
    result = verification.indexed(plan["resource_changes"])[address]["change"]
    assert isinstance(result, dict)
    return result


@pytest.fixture
def role_plan(env: dict[str, str]) -> dict[str, object]:
    env["AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID"] = FOUNDRY_USER
    plan = plan_for(env, "agent-evaluation")
    changes = verification.rows(plan["resource_changes"])
    for row in changes:
        address = str(row["address"])
        current = json_object(row["change"])
        after = json_object(current["after"])
        after["id"] = after.get("id") or str(uuid4())
        if address.startswith("azurerm_cognitive_account_project"):
            after["id"] = verification.project_id(env)
        if address.startswith("azurerm_role_assignment"):
            label = "chat" if address.endswith('["chat"]') else "evaluations"
            after["scope"] = (
                env["MODEL_ACCOUNT_ID"] if label == "chat" else verification.project_id(env)
            )
            after["role_definition_id"] = str(uuid4())
            after["role_definition_name"] = f"newsloom-test-agent-evaluation-{label}"
        current.update(actions=["no-op"], before=deepcopy(after), after=after, after_unknown={})
        row["change"] = current
    planned: dict[str, object] = {
        "resources": [
            {
                "address": row["address"],
                "mode": "managed",
                "values": json_object(row["change"])["after"],
            }
            for row in changes
        ]
    }
    plan["planned_values"] = {"root_module": planned}
    plan["prior_state"] = {"values": {"root_module": deepcopy(planned)}}
    wanted = evaluation_role.expected(env)
    after = {**wanted, "id": None, "name": wanted["id"].rsplit("/", 1)[1]}
    changes.append(
        {
            "address": evaluation_role.ADDRESS,
            "mode": "managed",
            "provider_name": PROVIDER,
            "change": {
                "actions": ["create"],
                "before": None,
                "after": after,
                "after_unknown": {"id": True, "role_definition_name": True},
            },
        }
    )
    plan["resource_changes"] = changes
    planned["resources"] = [
        *verification.rows(planned["resources"]),
        {"address": evaluation_role.ADDRESS, "mode": "managed", "values": after},
    ]
    plan["variables"] = {
        **json_object(plan["variables"]),
        "foundry_user_role_id": {"value": FOUNDRY_USER},
    }
    plan["output_changes"] = {
        evaluation_role.OUTPUT: {"actions": ["create"], "after_unknown": True}
    }
    return plan


def test_foundry_user_exact_additive_plan(
    env: dict[str, str], role_plan: dict[str, object]
) -> None:
    inventory = evaluation_role.plan_inventory(role_plan, env)
    assert inventory == {
        "additions": 1,
        "changes": 0,
        "destroys": 0,
        "assignment": evaluation_role.expected(env),
        "empty_set_state_refreshes": 0,
        "empty_exclusion_output_refresh": False,
    }


def manager_plan(plan: dict[str, object], env: dict[str, str]) -> dict[str, object]:
    env["AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID"] = "-".join(
        ["eadc314b", "1a2d", "4efa", "be10", "5d325db5065e"]
    )
    result = deepcopy(plan)
    retained = change(result, evaluation_role.ADDRESS)
    retained["after"] = {
        **json_object(retained["after"]),
        "id": evaluation_role.expected(env)["id"],
    }
    retained.update(actions=["no-op"], before=deepcopy(retained["after"]), after_unknown={})
    planned = json_object(json_object(result["planned_values"])["root_module"])
    entries = verification.rows(planned["resources"])
    entries[-1]["values"] = retained["after"]
    planned["resources"] = entries
    prior = json_object(json_object(json_object(result["prior_state"])["values"])["root_module"])
    prior["resources"] = deepcopy(planned["resources"])
    result["prior_state"] = {"values": {"root_module": prior}}
    wanted = evaluation_role.expected(env, "foundry-project-manager")
    after = {**wanted, "id": None, "name": wanted["id"].rsplit("/", 1)[1]}
    changes = verification.rows(result["resource_changes"])
    changes.append(
        {
            "address": evaluation_role.MANAGER_ADDRESS,
            "mode": "managed",
            "provider_name": PROVIDER,
            "change": {
                "actions": ["create"],
                "before": None,
                "after": after,
                "after_unknown": {"id": True, "role_definition_name": True},
            },
        }
    )
    result["resource_changes"] = changes
    entries.append(
        {
            "address": evaluation_role.MANAGER_ADDRESS,
            "mode": "managed",
            "values": after,
        }
    )
    planned["resources"] = entries
    result["planned_values"] = {"root_module": planned}
    result["variables"] = {
        **json_object(result["variables"]),
        "foundry_project_manager_role_id": {
            "value": env["AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID"],
        },
    }
    result["output_changes"] = {
        evaluation_role.OUTPUT: {
            "actions": ["no-op"],
            "before": "retained",
            "after": "retained",
            "after_unknown": False,
        },
        evaluation_role.MANAGER_OUTPUT: {"actions": ["create"], "after_unknown": True},
    }
    return result


@pytest.mark.parametrize("surface", ["valid", "scope", "principal", "retained-user", "extra"])
def test_project_manager_exact_transition_preserves_existing_user(
    env: dict[str, str], role_plan: dict[str, object], surface: str
) -> None:
    plan = manager_plan(role_plan, env)
    manager = change(plan, evaluation_role.MANAGER_ADDRESS)
    if surface in ("scope", "principal"):
        field = "scope" if surface == "scope" else "principal_id"
        manager["after"] = {**json_object(manager["after"]), field: "foreign"}
    elif surface == "retained-user":
        change(plan, evaluation_role.ADDRESS)["actions"] = ["update"]
    elif surface == "extra":
        plan["output_changes"] = {
            **json_object(plan["output_changes"]),
            "foreign": {"actions": ["create"]},
        }
    if surface == "valid":
        inventory = evaluation_role.plan_inventory(plan, env, "foundry-project-manager")
        assert inventory["additions"] == 1
        assert inventory["assignment"] == evaluation_role.expected(env, "foundry-project-manager")
    else:
        with pytest.raises(PlatformFailure):
            evaluation_role.plan_inventory(plan, env, "foundry-project-manager")


@pytest.mark.parametrize(
    "address,block,field",
    [
        ("azurerm_cognitive_account_project.evaluation[0]", "identity", "identity_ids"),
        ('azurerm_role_definition.operator["chat"]', "permissions", "not_data_actions"),
        ('azurerm_role_definition.operator["evaluations"]', "permissions", "not_data_actions"),
    ],
)
@pytest.mark.parametrize("foreign", [False, True])
def test_foundry_user_exact_empty_set_refresh(
    env: dict[str, str],
    role_plan: dict[str, object],
    address: str,
    block: str,
    field: str,
    foreign: bool,
) -> None:
    before = {"stable": "unchanged", block: [{field: None}]}
    after: dict[str, object] = {
        "stable": "changed" if foreign else "unchanged",
        block: [{field: []}],
    }
    role_plan["resource_drift"] = [
        {"address": address, "change": {"actions": ["update"], "before": before, "after": after}}
    ]
    if foreign:
        with pytest.raises(PlatformFailure, match="evaluation_role_unapproved_refresh_drift"):
            evaluation_role.plan_inventory(role_plan, env)
    else:
        assert evaluation_role.plan_inventory(role_plan, env)["empty_set_state_refreshes"] == 1


@pytest.mark.parametrize("foreign", [False, True])
def test_foundry_user_exact_empty_exclusion_output(
    env: dict[str, str], role_plan: dict[str, object], foreign: bool
) -> None:
    before = {
        label: {"not_data_actions": None, "scope": "retained"} for label in verification.PERMISSIONS
    }
    after: dict[str, dict[str, object]] = {
        label: {**value, "not_data_actions": []} for label, value in before.items()
    }
    if foreign:
        after["chat"]["scope"] = "foreign"
    outputs = json_object(role_plan["output_changes"])
    outputs["AGENT_EVALUATION_GRANTS_BASE64"] = {
        "actions": ["update"],
        "before": base64.b64encode(json.dumps(before).encode()).decode(),
        "after": base64.b64encode(json.dumps(after).encode()).decode(),
        "after_unknown": False,
    }
    role_plan["output_changes"] = outputs
    if foreign:
        with pytest.raises(PlatformFailure, match="evaluation_role_unrelated_output_change"):
            evaluation_role.plan_inventory(role_plan, env)
    else:
        assert (
            evaluation_role.plan_inventory(role_plan, env)["empty_exclusion_output_refresh"] is True
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("principal_id", str(uuid4())),
        ("principal_type", "ServicePrincipal"),
        ("role_definition_id", "foreign"),
        ("scope", "foreign"),
        ("condition", "foreign"),
        ("condition_version", "2.0"),
        ("delegated_managed_identity_resource_id", "foreign"),
        ("name", str(uuid4())),
        ("skip_service_principal_aad_check", True),
    ],
)
def test_foundry_user_rejects_foreign_assignment(
    env: dict[str, str], role_plan: dict[str, object], field: str, value: object
) -> None:
    current = change(role_plan, evaluation_role.ADDRESS)
    current["after"] = {**json_object(current["after"]), field: value}
    with pytest.raises(PlatformFailure, match="evaluation_role_assignment_plan_mismatch"):
        evaluation_role.plan_inventory(role_plan, env)


@pytest.mark.parametrize("surface", ["retained", "output", "role-input", "extra", "drift"])
def test_foundry_user_rejects_other_changes(
    env: dict[str, str], role_plan: dict[str, object], surface: str
) -> None:
    if surface == "retained":
        change(role_plan, 'azurerm_role_assignment.operator["chat"]')["actions"] = ["update"]
    elif surface == "output":
        role_plan["output_changes"] = {
            **json_object(role_plan["output_changes"]),
            "unrelated": {"actions": ["create"], "after": "foreign"},
        }
    elif surface == "role-input":
        role_plan["variables"] = {
            **json_object(role_plan["variables"]),
            "foundry_user_role_id": {"value": str(uuid4())},
        }
    elif surface == "drift":
        role_plan["resource_drift"] = [{"change": {"actions": ["update"]}}]
    else:
        rows = verification.rows(role_plan["resource_changes"])
        rows.append({**deepcopy(rows[-1]), "address": "azurerm_role_assignment.foreign"})
        role_plan["resource_changes"] = rows
    with pytest.raises(PlatformFailure):
        evaluation_role.plan_inventory(role_plan, env)


@pytest.mark.parametrize("surface", ["native", "output", "condition", "valid"])
def test_foundry_user_independent_readback(
    env: dict[str, str], role_plan: dict[str, object], surface: str
) -> None:
    wanted = evaluation_role.expected(env)
    env[evaluation_role.OUTPUT] = base64.b64encode(json.dumps(wanted).encode()).decode()
    native: dict[str, object] = {
        "id": wanted["id"],
        "properties": {
            "principalId": wanted["principal_id"],
            "principalType": wanted["principal_type"],
            "roleDefinitionId": wanted["role_definition_id"],
            "scope": wanted["scope"],
        },
    }
    if surface == "native":
        native["properties"] = {
            **json_object(native["properties"]),
            "scope": env["MODEL_ACCOUNT_ID"],
        }
    elif surface == "condition":
        native["properties"] = {**json_object(native["properties"]), "condition": "foreign"}
    elif surface == "output":
        env[evaluation_role.OUTPUT] = base64.b64encode(b"{}").decode()
    if surface == "valid":
        assert evaluation_role.assignment(native, env) == wanted
    else:
        with pytest.raises(PlatformFailure):
            evaluation_role.assignment(native, env)


@pytest.mark.parametrize("relabel_source", [False, True])
def test_foundry_user_source_bound_transition(
    env: dict[str, str],
    role_plan: dict[str, object],
    evidence: verification.Evidence,
    monkeypatch: pytest.MonkeyPatch,
    relabel_source: bool,
) -> None:
    original = {
        "mode": "readback",
        "layer": "agent-evaluation",
        "outcome": "success",
        "context_sha256": verification.context(env),
        "source_sha256": "a" * 64,
        "verification_scope": verification.verification_scope(env),
    }

    def path(name: str) -> str:
        return str(evidence.directory / name)

    evidence.write(path("foundation.json"), original)
    binary = Path(path("role.tfplan"))
    binary.write_bytes(b"native_plan_fixture")
    binary.chmod(0o600)
    manifest = {
        "mode": "plan",
        "foundation": path("foundation.json"),
        "foundation_sha256": hashlib.sha256(evidence.read(path("foundation.json"))).hexdigest(),
        "plan": str(binary),
        "output": path("role-review.json"),
    }
    evidence.write(path("manifest.json"), manifest)

    def run(arguments: list[str], category: str, **kwargs: object) -> str:
        if arguments[0] == "terraform":
            return json.dumps(role_plan)
        return str(evidence.root) if category == "project_root" else ""

    monkeypatch.setattr(control, "run", run)
    monkeypatch.setattr(verification, "binary_source", lambda *args: None)
    monkeypatch.setattr(verification, "source", lambda root: "b" * 64)
    monkeypatch.setattr(verification, "operator", lambda *args: None)
    evaluation_role.verify(env, "local", path("manifest.json"))
    review = evidence.document(path("role-review.json"))
    assert review["foundation_source_sha256"] == "a" * 64
    assert review["source_sha256"] == "b" * 64
    assert evidence.document(path("foundation.json")) == original
    if relabel_source:
        monkeypatch.setattr(verification, "source", lambda root: "c" * 64)
    evidence.write(
        path("apply.json"),
        {
            "azd_exit_code": 0,
            "source_sha256": "b" * 64,
            "plan_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "review_sha256": hashlib.sha256(evidence.read(path("role-review.json"))).hexdigest(),
            "completed_utc": datetime.now(UTC).isoformat(),
        },
    )
    evidence.write(
        path("readback-manifest.json"),
        {
            **manifest,
            "mode": "readback",
            "review": path("role-review.json"),
            "apply_receipt": path("apply.json"),
            "output": path("role-readback.json"),
        },
    )
    wanted = evaluation_role.expected(env)
    env[evaluation_role.OUTPUT] = base64.b64encode(json.dumps(wanted).encode()).decode()
    calls: list[str] = []

    def get(reader: verification.Reader, identifier: str, api: str) -> dict[str, object]:
        calls.append(identifier)
        return {
            "id": wanted["id"],
            "properties": {
                "principalId": wanted["principal_id"],
                "principalType": "User",
                "roleDefinitionId": wanted["role_definition_id"],
                "scope": wanted["scope"],
            },
        }

    monkeypatch.setattr(verification.Reader, "get", get)
    if relabel_source:
        with pytest.raises(PlatformFailure, match="evaluation_role_review_binding_changed"):
            evaluation_role.verify(env, "local", path("readback-manifest.json"))
        assert not calls
    else:
        evaluation_role.verify(env, "local", path("readback-manifest.json"))
        assert calls == [wanted["id"]]


def test_foundry_user_cli_dispatch(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(control, "environment", lambda: env)
    monkeypatch.setattr(
        evaluation_role, "verify", lambda selected, correlation, path: calls.append(path)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["newsloom-platform", "verify-agent-evaluation-role", "--manifest", "private.json"],
    )
    cli.main()
    assert calls == ["private.json"]


@pytest.mark.parametrize("layer,count", [("application", 32), ("agent-evaluation", 5)])
def test_native_plan_exact_inventory(env: dict[str, str], layer: str, count: int) -> None:
    result = verification.verify_plan(plan_for(env, layer), env, layer)
    assert result["managed_resources"] == count
    assert result["mutations"] == (1 if layer == "application" else 5)


@pytest.mark.parametrize("constraint", ["~> 5.10", ">= 5.10.0", "5.11.0"])
@pytest.mark.parametrize("layer", ["application", "agent-evaluation"])
def test_native_plan_requires_exact_provider_pin(
    env: dict[str, str], layer: str, constraint: str
) -> None:
    plan = plan_for(env, layer)
    configuration = json_object(plan["configuration"])
    configuration["provider_config"] = {"azurerm": {"version_constraint": constraint}}
    plan["configuration"] = configuration
    with pytest.raises(PlatformFailure, match="provider_mismatch"):
        verification.verify_plan(plan, env, layer)


@pytest.mark.parametrize("field", ["actions", "not_actions", "data_actions", "not_data_actions"])
def test_native_empty_optional_not_data_actions(field: str) -> None:
    row = verification.permission_row("chat")
    row[field] = None
    if field == "not_data_actions":
        assert verification.normalized_permissions([row]) == [verification.permission_row("chat")]
    else:
        with pytest.raises(PlatformFailure, match="invalid_permissions"):
            verification.normalized_permissions([row])


@pytest.mark.parametrize(
    "value,valid",
    [
        (True, True),
        ("true", True),
        (False, False),
        ("false", False),
        ("True", False),
        (1, False),
        (None, False),
    ],
)
def test_native_plan_enabled_input_preserves_azd_raw_string(
    env: dict[str, str], value: object, valid: bool
) -> None:
    plan = plan_for(env, "agent-evaluation")
    variables = json_object(plan["variables"])
    variables["enabled"] = {"value": value}
    plan["variables"] = variables
    if valid:
        assert verification.verify_plan(plan, env, "agent-evaluation")["mutations"] == 5
    else:
        with pytest.raises(PlatformFailure, match="plan_context_mismatch"):
            verification.verify_plan(plan, env, "agent-evaluation")


@pytest.mark.parametrize(
    "actions",
    [
        ["delete", "create"],
        ["create", "delete"],
        ["delete"],
        ["create"],
        ["forget"],
        ["read"],
    ],
)
def test_account_never_replaced_or_destroyed(env: dict[str, str], actions: list[str]) -> None:
    plan = plan_for(env, "application")
    change(plan, "azurerm_cognitive_account.models")["actions"] = actions
    with pytest.raises(PlatformFailure, match="account_change_boundary"):
        verification.verify_plan(plan, env, "application")


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "FOREIGN_ACCOUNT_CANARY"),
        ("name", "foreign"),
        ("local_auth_enabled", True),
        ("custom_subdomain_name", "foreign"),
        ("endpoint", "https://foreign.invalid/"),
        ("project_management_enabled", False),
        ("sku_name", "S1"),
        ("identity", [{"type": "UserAssigned"}]),
    ],
)
def test_account_unrelated_change_rejected(env: dict[str, str], field: str, value: object) -> None:
    plan = plan_for(env, "application")
    after = change(plan, "azurerm_cognitive_account.models")["after"]
    assert isinstance(after, dict)
    after[field] = value
    with pytest.raises(PlatformFailure):
        verification.verify_plan(plan, env, "application")


@pytest.mark.parametrize(
    "address",
    sorted(
        verification.application_addresses()
        - {
            "azurerm_cognitive_account.models",
        }
    ),
)
def test_every_other_application_resource_must_be_noop(env: dict[str, str], address: str) -> None:
    plan = plan_for(env, "application")
    change(plan, address)["actions"] = ["update"]
    with pytest.raises(PlatformFailure, match="unrelated_application_change"):
        verification.verify_plan(plan, env, "application")


@pytest.mark.parametrize(
    "field,value",
    [
        ("complete", False),
        ("errored", True),
        ("format_version", "9"),
        ("terraform_version", "1.17.0"),
        ("deferred_changes", [{}]),
        ("resource_changes", []),
        ("prior_state", {}),
        ("planned_values", {}),
        ("resource_drift", [{"change": {"actions": ["update"]}}]),
    ],
)
def test_missing_or_unreviewed_native_evidence(
    env: dict[str, str], field: str, value: object
) -> None:
    plan = plan_for(env, "application")
    plan[field] = value
    with pytest.raises(PlatformFailure):
        verification.verify_plan(plan, env, "application")


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "/subscriptions/foreign"),
        ("principal_id", "foreign"),
        ("principal_type", "ServicePrincipal"),
        ("condition", "foreign"),
        ("role_definition_name", "Foundry User"),
        ("delegated_managed_identity_resource_id", "foreign"),
        ("skip_service_principal_aad_check", True),
    ],
)
def test_assignment_boundaries(env: dict[str, str], field: str, value: object) -> None:
    plan = plan_for(env, "agent-evaluation")
    after = change(plan, 'azurerm_role_assignment.operator["chat"]')["after"]
    assert isinstance(after, dict)
    after[field] = value
    with pytest.raises(PlatformFailure):
        verification.verify_plan(plan, env, "agent-evaluation")


@pytest.mark.parametrize(
    "field,value",
    [
        ("permissions", [{"actions": ["*"], "data_actions": ["*"]}]),
        ("scope", "/subscriptions/foreign"),
        ("assignable_scopes", ["/"]),
        ("name", "Foundry User"),
    ],
)
def test_role_definitions_cannot_broaden(env: dict[str, str], field: str, value: object) -> None:
    plan = plan_for(env, "agent-evaluation")
    after = change(plan, 'azurerm_role_definition.operator["evaluations"]')["after"]
    assert isinstance(after, dict)
    after[field] = value
    with pytest.raises(PlatformFailure):
        verification.verify_plan(plan, env, "agent-evaluation")


def test_unknown_permissions_and_extra_project_rejected(env: dict[str, str]) -> None:
    plan = plan_for(env, "agent-evaluation")
    change(plan, 'azurerm_role_definition.operator["chat"]')["after_unknown"] = {
        "permissions": True
    }
    with pytest.raises(PlatformFailure):
        verification.verify_plan(plan, env, "agent-evaluation")
    plan = plan_for(env, "agent-evaluation")
    resources = plan["resource_changes"]
    assert isinstance(resources, list)
    resources.append({**resources[0], "address": "azurerm_cognitive_account.foreign"})
    with pytest.raises(PlatformFailure, match="resource_boundary"):
        verification.verify_plan(plan, env, "agent-evaluation")


def test_unknown_scope_requires_own_project_reference(env: dict[str, str]) -> None:
    plan = plan_for(env, "agent-evaluation")
    configuration = json_object(json_object(plan["configuration"])["root_module"])
    resource = verification.rows(configuration["resources"])[0]
    expressions = json_object(resource["expressions"])
    scope = expressions["scope"]
    assert isinstance(scope, dict)
    scope["references"] = ["var.foreign_project"]
    with pytest.raises(PlatformFailure, match="unbound_computed_reference"):
        verification.verify_plan(plan, env, "agent-evaluation")


def data_receipt() -> dict[str, object]:
    return {
        "verified_utc": datetime.now(UTC).isoformat(),
        "outcome": "success",
        "probe": "independent_stored_record",
        "mcp_read_identity_verified": True,
        "news_count": 2101,
        "news_metadata_fingerprint": "a" * 64,
        "recent_id_sha256": "b" * 64,
        "recent_url_sha256": "c" * 64,
        "writes_performed": 0,
        "model_calls": 0,
    }


def identity(env: dict[str, str]) -> dict[str, object]:
    return {
        "type": "SystemAssigned",
        "principalId": str(uuid4()),
        "tenantId": env["AGENT_TENANT_ID"],
    }


def preserved(env: dict[str, str]) -> dict[str, object]:
    return {
        "verification_scope": verification.verification_scope(env),
        "account": "a" * 64,
        "models": {},
        "workloads": {"app": "b" * 64},
        "directory": "c" * 64,
        "production_principals": [str(uuid4())],
        "account_identity": {},
        "project_management": False,
        "resources": {"retained": "d" * 64},
        "projects": {},
        "grants": {},
        "definitions": {},
        "histories": {"job": {}},
        "data_boundaries": {"postgres-retained": "e" * 64},
        "stored_record": data_receipt(),
    }


def after_parent(before: dict[str, object], env: dict[str, str]) -> dict[str, object]:
    after = deepcopy(before)
    after.update(account_identity=identity(env), project_management=True)
    after["stored_record"] = data_receipt()
    native_identity = json_object(after["account_identity"])
    env.update(
        MODEL_PROJECT_MANAGEMENT_ENABLED="true",
        MODEL_ACCOUNT_IDENTITY_PRINCIPAL_ID=str(native_identity["principalId"]),
        MODEL_ACCOUNT_IDENTITY_TENANT_ID=str(native_identity["tenantId"]),
    )
    return after


def after_project(before: dict[str, object], env: dict[str, str]) -> dict[str, object]:
    after = deepcopy(before)
    endpoint = env["MODEL_ENDPOINT"].rstrip("/") + "/api/projects/eval-newsloom-test"
    native_endpoints = {"AI Foundry API": endpoint}
    project_identity = identity(env)
    after["project"] = {
        "id": verification.project_id(env),
        "name": "eval-newsloom-test",
        "location": env["AZURE_LOCATION"],
        "identity": project_identity,
        "properties": {"provisioningState": "Succeeded", "endpoints": native_endpoints},
    }
    after["projects"] = {verification.project_id(env): "e" * 64}
    after["resources"] = {
        **json_object(before["resources"]),
        verification.project_id(env): "f" * 64,
    }
    grants: dict[str, object] = {}
    definitions: dict[str, object] = {}
    outputs: dict[str, object] = {}
    for label in verification.PERMISSIONS:
        definition_id = (
            f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
            f"/providers/Microsoft.Authorization/roleDefinitions/{uuid4()}"
        )
        assignment_id = (
            verification.group_id(env)
            + f"/providers/Microsoft.Authorization/roleAssignments/{uuid4()}"
        )
        scope = env["MODEL_ACCOUNT_ID"] if label == "chat" else verification.project_id(env)
        grants[assignment_id] = {
            "id": assignment_id,
            "scope": scope,
            "roleDefinitionId": definition_id,
            "principalId": env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
            "principalType": "User",
        }
        definitions[definition_id] = {
            "properties": {
                "roleName": f"newsloom-test-agent-evaluation-{label}",
                "type": "CustomRole",
                "assignableScopes": [verification.group_id(env)],
                "permissions": [
                    {
                        "actions": [],
                        "notActions": [],
                        "dataActions": verification.PERMISSIONS[label],
                        "notDataActions": [],
                    }
                ],
            }
        }
        outputs[label] = {
            "principal_id": env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
            "principal_type": "User",
            "scope": scope,
            "role_definition_id": definition_id,
            **verification.permission_row(label),
        }
    after.update(grants=grants, definitions=definitions, stored_record=data_receipt())
    env.update(
        AGENT_EVALUATION_PROJECT_ID=verification.project_id(env),
        AGENT_EVALUATION_PROJECT_ENDPOINT=endpoint,
        AGENT_EVALUATION_PROJECT_PRINCIPAL_ID=str(project_identity["principalId"]),
        AGENT_EVALUATION_PROJECT_ENDPOINTS_BASE64=base64.b64encode(
            json.dumps(native_endpoints).encode()
        ).decode(),
        AGENT_EVALUATION_GRANTS_BASE64=base64.b64encode(json.dumps(outputs).encode()).decode(),
    )
    return after


def test_independent_parent_and_project_readback(env: dict[str, str]) -> None:
    before = preserved(env)
    parent = after_parent(before, env)
    verification.compare(before, parent, env, "application")
    project = after_project(parent, env)
    original = deepcopy(project)
    verification.compare(parent, project, env, "agent-evaluation")
    assert project == original


@pytest.mark.parametrize("label", list(verification.PERMISSIONS))
def test_native_null_permission_exclusions(env: dict[str, str], label: str) -> None:
    before = after_parent(preserved(env), env)
    after = after_project(before, env)
    outputs = json.loads(base64.b64decode(env["AGENT_EVALUATION_GRANTS_BASE64"]))
    outputs[label]["not_data_actions"] = None
    env["AGENT_EVALUATION_GRANTS_BASE64"] = base64.b64encode(json.dumps(outputs).encode()).decode()
    verification.compare(before, after, env, "agent-evaluation")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actions", None),
        ("not_actions", None),
        ("data_actions", None),
        ("not_data_actions", ["FOREIGN_OPERATION"]),
        ("not_data_actions", False),
        ("unexpected", None),
    ],
)
def test_grant_output_normalization_rejects_drift(
    env: dict[str, str], field: str, value: object
) -> None:
    before = after_parent(preserved(env), env)
    after = after_project(before, env)
    outputs = json.loads(base64.b64decode(env["AGENT_EVALUATION_GRANTS_BASE64"]))
    outputs["chat"][field] = value
    env["AGENT_EVALUATION_GRANTS_BASE64"] = base64.b64encode(json.dumps(outputs).encode()).decode()
    with pytest.raises(PlatformFailure):
        verification.compare(before, after, env, "agent-evaluation")


@pytest.mark.parametrize(
    "key",
    [
        "account",
        "models",
        "workloads",
        "directory",
        "production_principals",
        "resources",
        "grants",
        "definitions",
        "projects",
    ],
)
def test_preservation_drift_fails(env: dict[str, str], key: str) -> None:
    before = preserved(env)
    after = after_parent(before, env)
    after[key] = {"FOREIGN_CONTENT_CANARY": "changed"}
    with pytest.raises(PlatformFailure):
        verification.compare(before, after, env, "application")


def test_new_identity_or_foreign_service_assignment_never_accepted(env: dict[str, str]) -> None:
    before = after_parent(preserved(env), env)
    for principal in (str(uuid4()), json_object(before["account_identity"])["principalId"]):
        after = after_project(before, env)
        grants = after["grants"]
        assert isinstance(grants, dict)
        grants["unexpected"] = {"principalId": principal, "scope": env["MODEL_ACCOUNT_ID"]}
        with pytest.raises(PlatformFailure, match="unexpected_resource_or_authority"):
            verification.compare(before, after, env, "agent-evaluation")


@pytest.mark.parametrize(
    "key",
    [
        "AGENT_EVALUATION_PROJECT_ID",
        "AGENT_EVALUATION_PROJECT_ENDPOINT",
        "AGENT_EVALUATION_PROJECT_PRINCIPAL_ID",
    ],
)
def test_project_outputs_are_not_native_readback_evidence(env: dict[str, str], key: str) -> None:
    before = after_parent(preserved(env), env)
    after = after_project(before, env)
    env[key] = "FOREIGN_PROJECT_CANARY"
    with pytest.raises(PlatformFailure, match="project_readback_mismatch"):
        verification.compare(before, after, env, "agent-evaluation")


@pytest.mark.parametrize("name", ["leaf", "qualified", "foreign", "suffix"])
def test_project_name_is_exactly_bound_to_its_parent(env: dict[str, str], name: str) -> None:
    before = after_parent(preserved(env), env)
    after = after_project(before, env)
    project = json_object(after["project"])
    leaf = verification.project_id(env).rsplit("/", 1)[1]
    project["name"] = {
        "leaf": leaf,
        "qualified": env["MODEL_ACCOUNT_NAME"] + "/" + leaf,
        "foreign": "foreign/" + leaf,
        "suffix": env["MODEL_ACCOUNT_NAME"] + "/foreign/" + leaf,
    }[name]
    after["project"] = project
    if name in ("foreign", "suffix"):
        with pytest.raises(PlatformFailure, match="project_readback_mismatch"):
            verification.compare(before, after, env, "agent-evaluation")
    else:
        verification.compare(before, after, env, "agent-evaluation")


def test_stored_data_drift_requires_reconciliation_even_with_completed_schedule(
    env: dict[str, str],
) -> None:
    before = preserved(env)
    after = after_parent(before, env)
    after["histories"] = {"job": {"new-execution": {"status": "Succeeded"}}}
    receipt = after["stored_record"]
    assert isinstance(receipt, dict)
    receipt["news_count"] = 2102
    with pytest.raises(PlatformFailure, match="stored_record_reconciliation_required"):
        verification.compare(before, after, env, "application")


@pytest.fixture
def evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> verification.Evidence:
    directory = tmp_path / ".azure" / "test" / "evaluation-verification"
    directory.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(control, "run", lambda *args, **kwargs: "")
    return verification.Evidence(tmp_path, "test")


def test_private_evidence_is_exclusive_and_rejects_nonprivate_or_symlink(
    evidence: verification.Evidence,
) -> None:
    path = str(evidence.directory / "receipt.json")
    evidence.write(path, {"outcome": "success"})
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert evidence.document(path) == {"outcome": "success"}
    with pytest.raises(FileExistsError):
        evidence.write(path, {})
    Path(path).chmod(0o644)
    with pytest.raises(PlatformFailure, match="private_file_required"):
        evidence.read(path)
    link = evidence.directory / "link.json"
    link.symlink_to(path)
    with pytest.raises(PlatformFailure, match="private_path_required"):
        evidence.read(str(link))
    with pytest.raises(PlatformFailure, match="private_path_required"):
        evidence.write(str(evidence.directory / "../foreign.json"), {})


def test_duplicate_json_and_oversized_evidence_rejected(evidence: verification.Evidence) -> None:
    path = evidence.directory / "duplicate.json"
    path.write_text('{"mode":"baseline","mode":"readback"}')
    path.chmod(0o600)
    with pytest.raises(PlatformFailure, match="duplicate_field"):
        evidence.document(str(path))
    with path.open("wb") as stream:
        stream.truncate(verification.MAX_BYTES + 1)
    with pytest.raises(PlatformFailure, match="private_file_required"):
        evidence.read(str(path))


@pytest.mark.parametrize(
    "field,value",
    [
        ("news_count", True),
        ("mcp_read_identity_verified", False),
        ("writes_performed", 1),
        ("model_calls", True),
        ("news_metadata_fingerprint", "ARTICLE_TEXT_CANARY"),
        ("verified_utc", (datetime.now(UTC) - timedelta(minutes=16)).isoformat()),
        ("prompt", "CONTENT_CANARY"),
    ],
)
def test_independent_data_receipt_is_strict(
    evidence: verification.Evidence, field: str, value: object
) -> None:
    receipt = data_receipt()
    receipt[field] = value
    path = str(evidence.directory / "data.json")
    evidence.write(path, receipt)
    with pytest.raises(PlatformFailure):
        verification.stored_record(evidence, path)


def test_native_pagination_is_complete_and_read_only(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    identifier = verification.group_id(env) + "/resources"
    url = f"{verification.ARM}{identifier}?api-version=2021-04-01&$skiptoken=next"
    pages = [{"value": [{"id": "one"}], "nextLink": url}, {"value": [{"id": "two"}]}]
    calls: list[list[str]] = []

    def azure(arguments: list[str], category: str, *, timeout: int) -> object:
        calls.append(arguments)
        assert 1 <= timeout <= 30
        return pages.pop(0)

    monkeypatch.setattr(control, "azure", azure)
    reader = verification.Reader(env)
    assert reader.listing(identifier, "2021-04-01") == [{"id": "one"}, {"id": "two"}]
    assert reader.calls == 2 and not pages
    assert all(arguments[:3] == ["rest", "--method", "get"] for arguments in calls)


@pytest.mark.parametrize(
    "link",
    [
        "https://foreign.invalid/resources?api-version=2021-04-01",
        "https://management.azure.com/foreign?api-version=2021-04-01",
        "http://management.azure.com/foreign?api-version=2021-04-01",
    ],
)
def test_foreign_pagination_rejected(
    monkeypatch: pytest.MonkeyPatch, link: str, env: dict[str, str]
) -> None:
    monkeypatch.setattr(control, "azure", lambda *args, **kwargs: {"value": [], "nextLink": link})
    with pytest.raises(PlatformFailure, match="foreign_next_link"):
        verification.Reader(env).listing(verification.group_id(env) + "/resources", "2021-04-01")


def test_metadata_attempt_and_deadline_limits(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    monkeypatch.setattr(control, "azure", lambda *args, **kwargs: pytest.fail("not dispatched"))
    reader = verification.Reader(env)
    reader.calls = 100
    with pytest.raises(PlatformFailure, match="metadata_limit"):
        reader.cli(["account", "show"])
    reader.calls = 0
    reader.deadline = time.monotonic() - 1
    with pytest.raises(PlatformFailure, match="metadata_limit"):
        reader.cli(["account", "show"])


@pytest.mark.parametrize(
    "kind",
    [
        "subscription",
        "subscription_roles",
        "broad_cli_roles",
        "other_group",
        "prefix_group",
        "builtin_definition",
        "all_definitions",
        "users",
        "foreign_app",
        "foreign_app_object",
        "other_server",
        "other_database",
        "all_databases",
        "encoded",
        "traversal",
        "write",
    ],
)
def test_outside_scope_requests_never_dispatch(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    group = verification.group_id(env)
    database = (
        group
        + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/"
        + env["POSTGRES_SERVER_NAME"]
    )

    def get(path: str) -> list[str]:
        return [
            "rest",
            "--method",
            "get",
            "--url",
            verification.ARM + path + "?api-version=2022-04-01",
        ]

    arguments = {
        "subscription": get(f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}/resources"),
        "subscription_roles": get(
            f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}/providers/Microsoft.Authorization/roleAssignments"
        ),
        "broad_cli_roles": ["role", "assignment", "list", "--all", "--include-inherited"],
        "other_group": get(group.rsplit("/", 1)[0] + "/foreign/resources"),
        "prefix_group": get(group + "-foreign/resources"),
        "builtin_definition": get(
            group + "/providers/Microsoft.Authorization/roleDefinitions/" + str(uuid4())
        ),
        "all_definitions": get(group + "/providers/Microsoft.Authorization/roleDefinitions"),
        "users": ["ad", "signed-in-user", "show", "--query", "id"],
        "foreign_app": ["ad", "app", "show", "--id", str(uuid4())],
        "foreign_app_object": ["ad", "app", "federated-credential", "list", "--id", str(uuid4())],
        "other_server": ["postgres", "flexible-server", "show", "--ids", database + "-foreign"],
        "other_database": get(database + "/databases/foreign"),
        "all_databases": get(database + "/databases"),
        "encoded": get(group + "/%2e%2e/resources"),
        "traversal": get(group + "/../resources"),
        "write": ["rest", "--method", "post", "--url", verification.ARM + group],
    }[kind]
    monkeypatch.setattr(
        control, "azure", lambda *args, **kwargs: pytest.fail("outside scope dispatched")
    )
    reader = verification.Reader(env)
    with pytest.raises(PlatformFailure, match="outside_scope"):
        reader.cli(arguments)
    assert reader.calls == 0


def test_current_evidence_requires_the_exact_reduced_scope(env: dict[str, str]) -> None:
    value = preserved(env)
    value.pop("verification_scope")
    with pytest.raises(PlatformFailure, match="scope_evidence_required"):
        verification.scoped_snapshot(value, env)
    assert verification.scoped_snapshot(value, env, historical=True)[
        "verification_scope"
    ] == verification.verification_scope(env)
    value = preserved(env)
    value["verification_scope"] = {**verification.verification_scope(env), "database": "foreign"}
    with pytest.raises(PlatformFailure, match="scope_evidence_required"):
        verification.scoped_snapshot(value, env, historical=True)


@pytest.mark.parametrize(
    "field", ["actions", "notActions", "dataActions", "notDataActions", "assignableScopes"]
)
def test_project_custom_role_authority_remains_exact(env: dict[str, str], field: str) -> None:
    before = after_parent(preserved(env), env)
    after = after_project(before, env)
    definitions = json_object(after["definitions"])
    identifier = next(iter(definitions))
    definition = json_object(definitions[identifier])
    properties = json_object(definition["properties"])
    if field == "assignableScopes":
        properties[field] = [f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"]
    else:
        permissions = verification.rows(properties["permissions"])
        permissions[0][field] = ["unapproved"]
        properties["permissions"] = permissions
    definition["properties"] = properties
    definitions[identifier] = definition
    after["definitions"] = definitions
    with pytest.raises(PlatformFailure, match="native_grant_mismatch"):
        verification.compare(before, after, env, "agent-evaluation")


def test_fresh_native_evaluation_plan_has_no_prior_state(env: dict[str, str]) -> None:
    plan = plan_for(env, "agent-evaluation")
    plan.pop("prior_state")
    for label in verification.PERMISSIONS:
        assignment = change(plan, f'azurerm_role_assignment.operator["{label}"]')
        unknown = assignment["after_unknown"]
        assert isinstance(unknown, dict)
        unknown.update(
            condition_version=True, role_definition_name=True, skip_service_principal_aad_check=True
        )
    assert verification.verify_plan(plan, env, "agent-evaluation")["managed_resources"] == 5


def native_binary(root: Path) -> bytes:
    data = io.BytesIO()
    with ZipFile(data, "w") as archive:
        for path in root.glob("*.tf"):
            archive.writestr(f"tfconfig/m-/{path.name}", path.read_bytes())
        archive.writestr(".terraform.lock.hcl", (root / ".terraform.lock.hcl").read_bytes())
    return data.getvalue()


def test_binary_is_bound_to_embedded_source_and_provider(tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text('resource "test" "owned" {}')
    (tmp_path / ".terraform.lock.hcl").write_text(
        'provider "registry.terraform.io/hashicorp/azurerm" {\n  version = "5.10.0"\n}'
    )
    binary = native_binary(tmp_path)
    verification.binary_source(binary, tmp_path)
    (tmp_path / "main.tf").write_text("CHANGED_SOURCE_CANARY")
    with pytest.raises(PlatformFailure, match="native_source_mismatch"):
        verification.binary_source(binary, tmp_path)
    with pytest.raises(PlatformFailure, match="native_binary_required"):
        verification.binary_source(b'{"resource_changes":[]}', tmp_path)
    (tmp_path / ".terraform.lock.hcl").write_text(
        'provider "registry.terraform.io/hashicorp/azurerm" {\n  version = "5.11.0"\n}'
    )
    with pytest.raises(PlatformFailure, match="provider_lock_mismatch"):
        verification.binary_source(binary, tmp_path)


@pytest.mark.parametrize("retained_verification_identity", [False, True])
def test_live_snapshot_reads_complete_runtime_inventory(
    env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    retained_verification_identity: bool,
) -> None:
    account_id = env["MODEL_ACCOUNT_ID"]
    directory_ids = {
        env[key]: str(uuid4())
        for key in (
            "MCP_API_CLIENT_ID",
            "MCP_PUBLIC_CLIENT_ID",
            "AGENT_API_CLIENT_ID",
            "AGENT_PUBLIC_CLIENT_ID",
        )
    }
    resources: list[dict[str, object]] = []
    native: dict[str, object] = {
        account_id: {
            "id": account_id,
            "name": env["MODEL_ACCOUNT_NAME"],
            "kind": "AIServices",
            "location": env["AZURE_LOCATION"],
            "sku": {"name": "S0"},
            "identity": {"type": "None"},
            "properties": {
                "provisioningState": "Succeeded",
                "allowProjectManagement": False,
                "disableLocalAuth": True,
                "customSubDomainName": env["MODEL_ACCOUNT_NAME"],
                "endpoints": {"AI Foundry API": env["MODEL_ENDPOINT"]},
            },
        },
        account_id + "/projects": {"value": []},
    }
    chat = {
        "id": account_id + "/deployments/chat",
        "name": "chat",
        "sku": {"name": env["ENRICHMENT_SKU"], "capacity": 10},
        "properties": {
            "provisioningState": "Succeeded",
            "versionUpgradeOption": "NoAutoUpgrade",
            "capabilities": {"chatCompletion": "true"},
            "model": {
                "name": env["ENRICHMENT_MODEL"],
                "format": "OpenAI",
                "version": env["ENRICHMENT_VERSION"],
            },
        },
    }
    models = [chat]
    for name in ("embeddings", "screening"):
        model = deepcopy(chat)
        model.update(id=account_id + "/deployments/" + name, name=name)
        models.append(model)
    native[account_id + "/deployments"] = {"value": models}
    identity_names = [
        f"id-newsloom-{env['AZURE_ENV_NAME']}-{workload}"
        for workload in ("ingestion", "enrichment", "mcp", "migrations", "agent")
    ]
    if retained_verification_identity:
        identity_names.append(f"phase1-newsloom-{env['AZURE_ENV_NAME']}")
    for name in identity_names:
        identifier = (
            verification.group_id(env)
            + f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{name}"
        )
        resources.append(
            {"id": identifier, "type": "Microsoft.ManagedIdentity/userAssignedIdentities"}
        )
        native[identifier] = {"properties": {"principalId": str(uuid4()), "clientId": str(uuid4())}}
    for index in range(6):
        kind = "jobs" if index < 4 else "containerApps"
        identifier = verification.group_id(env) + f"/providers/Microsoft.App/{kind}/app-{index}"
        resources.append({"id": identifier, "type": "Microsoft.App/" + kind})
        native[identifier] = {
            "identity": {"type": "UserAssigned"},
            "properties": {
                "provisioningState": "Succeeded",
                "latestRevisionName": "ready",
                "latestReadyRevisionName": "ready",
                "environmentId": "retained-environment",
                "configuration": {"triggerType": "Schedule"},
                "template": {"containers": [{"image": "retained@sha256:" + "a" * 64}]},
            },
        }
        native[identifier + "/executions"] = {"value": []}
    native[verification.group_id(env) + "/resources"] = {"value": resources}
    database_id = (
        verification.group_id(env)
        + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/"
        + env["POSTGRES_SERVER_NAME"]
    )
    resources.append({"id": database_id, "type": "Microsoft.DBforPostgreSQL/flexibleServers"})
    foreign_role = (
        f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
        f"/providers/Microsoft.Authorization/roleDefinitions/{uuid4()}"
    )
    native[foreign_role] = {"properties": {"permissions": []}}
    foreign_assignment = {
        "id": "foreign-service-added-assignment",
        "roleDefinitionId": foreign_role,
        "principalId": str(uuid4()),
        "principalType": "ServicePrincipal",
        "scope": account_id,
    }
    native[verification.group_id(env) + "/providers/Microsoft.Authorization/roleAssignments"] = {
        "value": [
            {
                "id": row["id"],
                "properties": {key: value for key, value in row.items() if key != "id"},
            }
            for row in [
                foreign_assignment,
                {
                    **foreign_assignment,
                    "id": "inherited-not-verified",
                    "scope": f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}",
                },
                {
                    **foreign_assignment,
                    "id": "operator-other-rg-not-verified",
                    "principalId": env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"],
                    "scope": verification.group_id(env) + "-other",
                },
            ]
        ]
    }
    calls: list[list[str]] = []

    def azure(arguments: list[str], category: str, *, timeout: int) -> object:
        calls.append(arguments)
        if arguments[:3] == ["rest", "--method", "get"]:
            from urllib.parse import urlsplit

            return native[urlsplit(arguments[4]).path]
        if arguments[:3] == ["postgres", "flexible-server", "show"]:
            return {
                "id": database_id,
                "state": "Ready",
                "authConfig": {
                    "passwordAuth": "Disabled",
                    "activeDirectoryAuth": "Enabled",
                    "tenantId": env["AGENT_TENANT_ID"],
                },
            }
        if arguments[:2] == ["postgres", "flexible-server"]:
            return []
        if arguments[:3] == ["ad", "app", "show"]:
            return {"appId": arguments[-1], "id": directory_ids[arguments[-1]]}
        if arguments[:2] == ["ad", "app"]:
            return []
        raise AssertionError("unexpected_or_mutating_command")

    monkeypatch.setattr(control, "azure", azure)
    reader = verification.Reader(env)
    result = verification.snapshot(reader, env)
    assert len(json_object(result["workloads"])) == 11 + retained_verification_identity
    assert isinstance(result["production_principals"], list)
    assert len(result["production_principals"]) == 5 + retained_verification_identity
    assert foreign_assignment["id"] in json_object(result["grants"])
    assert set(json_object(result["grants"])) == {foreign_assignment["id"]}
    grant = json_object(json_object(result["grants"])[foreign_assignment["id"]])
    assert {key: value for key, value in grant.items() if value is not None} == foreign_assignment
    assert result["definitions"] == {}
    assert result["verification_scope"] == verification.verification_scope(env)
    assert reader.calls == len(calls) < 100
    assert all("post" not in arguments and "create" not in arguments for arguments in calls)
    missing = next(row for row in resources if str(row["id"]).endswith("-migrations"))
    resources.remove(missing)
    with pytest.raises(PlatformFailure, match="runtime_inventory"):
        verification.snapshot(verification.Reader(env), env)
    resources.append(missing)
    properties = json_object(native[account_id])["properties"]
    assert isinstance(properties, dict)
    properties["disableLocalAuth"] = False
    with pytest.raises(PlatformFailure, match="account_readback"):
        verification.snapshot(verification.Reader(env), env)


@pytest.mark.parametrize("staged", [False, True])
def test_full_review_and_readback_are_source_bound_and_private(
    env: dict[str, str],
    evidence: verification.Evidence,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    staged: bool,
) -> None:
    root = evidence.root
    owning_root = root / "infra" / "agent-evaluation"
    owning_root.mkdir(parents=True)
    (owning_root / "main.tf").write_text("SOURCE_CANARY")
    (owning_root / ".terraform.lock.hcl").write_text(
        'provider "registry.terraform.io/hashicorp/azurerm" {\n  version = "5.10.0"\n}'
    )
    initial = preserved(env)
    parent = after_parent(initial, env)
    before = initial if staged else parent
    plan = plan_for(env, "agent-evaluation")
    after = after_project(parent, env)
    source_sha = "d" * 64
    monkeypatch.setattr(verification, "source", lambda root: source_sha)
    monkeypatch.setattr(verification, "operator", lambda *args: None)
    monkeypatch.setattr(verification, "snapshot", lambda *args: deepcopy(after))
    calls: list[list[str]] = []

    def run(arguments: list[str], category: str, *, timeout: int = 300) -> str:
        calls.append(arguments)
        if arguments == ["git", "rev-parse", "--show-toplevel"]:
            return str(root)
        if arguments[0] == "terraform":
            assert arguments[2:4] == ["show", "-json"]
            return json.dumps(plan)
        if "check-ignore" in arguments:
            return ""
        raise AssertionError("unexpected_or_mutating_command")

    monkeypatch.setattr(control, "run", run)
    directory = evidence.directory
    baseline = str(directory / "baseline.json")
    verified = datetime.now(UTC) - timedelta(seconds=1)
    evidence.write(
        baseline,
        {
            "outcome": "success",
            "mode": "baseline",
            "layer": "agent-evaluation",
            "context_sha256": verification.context(env),
            "source_sha256": source_sha,
            "verification_scope": verification.verification_scope(env),
            "verified_utc": verified.isoformat(),
            "snapshot": before,
        },
    )
    binary_path = directory / "native.tfplan"
    binary_path.write_bytes(native_binary(owning_root))
    binary_path.chmod(0o600)
    review = str(directory / "review.json")
    manifest_path = str(directory / "review-manifest.json")
    evidence.write(
        manifest_path,
        {
            "mode": "plan",
            "layer": "agent-evaluation",
            "output": review,
            "baseline": baseline,
            "plan": str(binary_path),
        },
    )
    verification.verify(env, "local", manifest_path)
    assert (
        evidence.document(review)["plan_sha256"]
        == hashlib.sha256(binary_path.read_bytes()).hexdigest()
    )
    data_path = str(directory / "stored-after.json")
    evidence.write(data_path, data_receipt())
    readback = str(directory / "readback.json")
    manifest_path = str(directory / "readback-manifest.json")
    parent_arguments: dict[str, str] = {}
    if staged:
        parent_path = str(directory / "parent-readback.json")
        evidence.write(
            parent_path,
            {
                "outcome": "success",
                "mode": "readback",
                "layer": "application",
                "context_sha256": verification.context(env),
                "source_sha256": source_sha,
                "verification_scope": verification.verification_scope(env),
                "verified_utc": datetime.now(UTC).isoformat(),
                "snapshot": parent,
                "plan_sha256": "a" * 64,
                "baseline_sha256": "b" * 64,
                "plan_inventory": {"managed_resources": 32, "mutations": 1, "inventory": {}},
            },
        )
        parent_arguments["parent_readback"] = parent_path
    evidence.write(
        manifest_path,
        {
            "mode": "readback",
            "layer": "agent-evaluation",
            "output": readback,
            "baseline": baseline,
            "plan": str(binary_path),
            "review": review,
            "stored_record": data_path,
            **parent_arguments,
        },
    )
    verification.verify(env, "local", manifest_path)
    assert evidence.document(readback)["outcome"] == "success"
    assert "SOURCE_CANARY" not in capsys.readouterr().out
    drifted = deepcopy(after)
    drifted["workloads"] = {"app": "f" * 64}
    monkeypatch.setattr(verification, "snapshot", lambda *args: drifted)
    failure_manifest = evidence.document(manifest_path)
    failure_output = str(directory / "failure.json")
    failure_manifest["output"] = failure_output
    failure_path = str(directory / "failure-manifest.json")
    evidence.write(failure_path, failure_manifest)
    with pytest.raises(PlatformFailure, match="preservation_drift"):
        verification.verify(env, "local", failure_path)
    assert evidence.document(failure_output)["outcome"] == "failure"
    stale_manifest = evidence.document(manifest_path)
    stale_manifest["output"] = str(directory / "stale.json")
    stale_path = str(directory / "stale-manifest.json")
    evidence.write(stale_path, stale_manifest)
    monkeypatch.setattr(verification, "source", lambda root: "e" * 64)
    with pytest.raises(PlatformFailure, match="binding_mismatch"):
        verification.verify(env, "local", stale_path)
    assert all(arguments[0] in ("git", "terraform") for arguments in calls)


def test_cli_dispatches_verifier_without_provisioning(
    env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[dict[str, str], str, str]] = []
    monkeypatch.setattr(control, "environment", lambda: env)
    monkeypatch.setattr(verification, "verify", lambda *args: calls.append(args))
    monkeypatch.setattr(
        sys,
        "argv",
        ["newsloom-platform", "verify-agent-evaluation", "--manifest", "private-manifest.json"],
    )
    cli.main()
    assert len(calls) == 1
    assert calls[0][0] == env and calls[0][2] == "private-manifest.json"


@pytest.mark.parametrize(
    "arguments",
    [
        ["verify-agent-evaluation"],
        ["prepare-agent-evaluation-layer", "--manifest", "CONTENT_CANARY"],
    ],
)
def test_cli_rejects_invalid_manifest_usage_without_leaking(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["newsloom-platform", *arguments])
    with pytest.raises(SystemExit):
        cli.main()
    output = capsys.readouterr().out
    assert "failure" in output and "CONTENT_CANARY" not in output
