import base64
import hashlib
import json
import re
import sys
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
from newsloom_platform import agent_evaluation, cli, control
from newsloom_platform.config import PlatformFailure


@dataclass
class Foundation:
    env: dict[str, str]
    context: dict[str, object]
    operator: str
    account: dict[str, object]
    deployment: dict[str, object]
    updates: dict[str, str] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)


def data_environment(foundation: Foundation) -> dict[str, str]:
    return {
        **foundation.env,
        "AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID": "-".join(
            ["53ca6127", "db72", "4b80", "b1b0", "d745d6d5456d"]
        ),
        "AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID": "-".join(
            ["eadc314b", "1a2d", "4efa", "be10", "5d325db5065e"]
        ),
        "AGENT_EVALUATION_DATA_RESOURCES_ENABLED": "true",
        "AGENT_EVALUATION_IMPORT_EXISTING_DATA_RESOURCES": "true",
        "AGENT_EVALUATION_STORAGE_ACCOUNT_NAME": "stnewsloomevaltest",
        "AGENT_EVALUATION_STORAGE_CONNECTION_NAME": "stnewsloomevaltestmanual",
        "AGENT_EVALUATION_STORAGE_GRANT_NAME": str(uuid4()),
        "AGENT_EVALUATION_ACCOUNT_USER_GRANT_NAME": str(uuid4()),
        "AGENT_EVALUATION_ACCOUNT_MANAGER_GRANT_NAME": str(uuid4()),
        "AGENT_EVALUATION_STORAGE_ROLE_ID": "-".join(
            ["ba92f5b4", "2d11", "453d", "a403", "e96b0029c9fe"]
        ),
    }


def test_data_adoption_configuration_preserves_exact_names_without_cloud_reads(
    foundation: Foundation,
) -> None:
    env = data_environment(foundation)
    original = deepcopy(env)
    values = agent_evaluation.data_configuration(env)
    assert values["enabled"] == values["import_existing"] == "true"
    assert values["connection_name"] == env["AGENT_EVALUATION_STORAGE_CONNECTION_NAME"]
    assert values["storage_grant_name"] == env["AGENT_EVALUATION_STORAGE_GRANT_NAME"]
    assert values["retain_experimental_appinsights_grants"] == "false"
    assert env == original and not foundation.calls and not foundation.updates


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enabled", "invalid"),
        ("storage_name", "foreign/parent"),
        ("connection_name", "foreign/connection"),
        ("storage_grant_name", ""),
        ("account_user_grant_name", "invalid"),
        ("storage_role_id", str(uuid4())),
    ],
)
def test_data_adoption_rejects_bad_inputs_before_cloud_reads(
    foundation: Foundation, field: str, value: str
) -> None:
    env = data_environment(foundation)
    env[agent_evaluation.DATA_INPUTS[field]] = value
    with pytest.raises(PlatformFailure):
        agent_evaluation.data_configuration(env)
    assert not foundation.calls and not foundation.updates


def test_diagnostic_grants_cannot_expand_to_another_component(foundation: Foundation) -> None:
    env = data_environment(foundation)
    env.update(
        {
            "AGENT_EVALUATION_RETAIN_DIAGNOSTIC_GRANTS": "true",
            "AGENT_EVALUATION_DIAGNOSTIC_APPINSIGHTS_ID": "/foreign/component",
        }
    )
    with pytest.raises(PlatformFailure, match="agent_evaluation_diagnostic_scope_invalid"):
        agent_evaluation.data_configuration(env)
    assert not foundation.calls and not foundation.updates


@pytest.fixture
def foundation(monkeypatch: pytest.MonkeyPatch) -> Foundation:
    subscription, tenant, operator = (str(uuid4()) for _ in range(3))
    name = "test"
    suffix = hashlib.sha256(f"{subscription}/{name}".encode()).hexdigest()[:8]
    account_name = f"ai-newsloom-{name}-{suffix}"
    account_id = (
        f"/subscriptions/{subscription}/resourceGroups/rg-newsloom-test"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
    )
    env = {
        "AGENT_EVALUATION_ENABLED": "true",
        "AZURE_SUBSCRIPTION_ID": subscription,
        "AGENT_TENANT_ID": tenant,
        "AZURE_ENV_NAME": name,
        "AZURE_RESOURCE_GROUP": "rg-newsloom-test",
        "AZURE_LOCATION": "francecentral",
        "MODEL_ACCOUNT_ID": account_id,
        "MODEL_ACCOUNT_NAME": account_name,
        "MODEL_ENDPOINT": f"https://{account_name}.services.ai.azure.com/",
        "ENRICHMENT_DEPLOYMENT": "existing-chat",
        "ENRICHMENT_MODEL": "gpt-5.4-mini",
        "ENRICHMENT_VERSION": "2026-03-17",
        "ENRICHMENT_FORMAT": "OpenAI",
        "ENRICHMENT_SKU": "DataZoneStandard",
        "ENRICHMENT_CAPACITY": "10",
    }
    result = Foundation(
        env=env,
        context={
            "id": subscription,
            "tenantId": tenant,
            "state": "Enabled",
            "user": {"type": "user"},
        },
        operator=operator,
        account={
            "id": account_id,
            "name": account_name,
            "kind": "AIServices",
            "location": "francecentral",
            "identity": {"type": "None"},
            "properties": {
                "customSubDomainName": account_name,
                "disableLocalAuth": True,
                "allowProjectManagement": False,
                "provisioningState": "Succeeded",
            },
        },
        deployment={
            "id": f"{account_id}/deployments/existing-chat",
            "name": "existing-chat",
            "sku": {"name": "DataZoneStandard", "capacity": 10},
            "properties": {
                "provisioningState": "Succeeded",
                "versionUpgradeOption": "NoAutoUpgrade",
                "capabilities": {"chatCompletion": "true"},
                "model": {"name": "gpt-5.4-mini", "version": "2026-03-17", "format": "OpenAI"},
            },
        },
    )

    def azure(arguments: list[str], category: str) -> object:
        result.calls.append(arguments)
        if arguments == ["account", "show"]:
            return result.context
        if arguments == agent_evaluation.OPERATOR_TOKEN:
            claims = {
                "oid": result.operator,
                "tid": result.context["tenantId"],
                "exp": time.time() + 600,
            }
            payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
            return f"header.{payload}.signature"
        raise AssertionError("unexpected_azure_command")

    def rest(url: str, category: str, *, body: object | None = None) -> object:
        assert body is None, "metadata_preparation_must_not_mutate"
        result.calls.append(["GET", url])
        prefix = f"https://management.azure.com{account_id}"
        if url == f"{prefix}?api-version={agent_evaluation.ARM_API}":
            return result.account
        if url == f"{prefix}/deployments/existing-chat?api-version={agent_evaluation.ARM_API}":
            return result.deployment
        raise AssertionError("unexpected_arm_route")

    monkeypatch.setattr(control, "azure", azure)
    monkeypatch.setattr(control, "rest", rest)
    monkeypatch.setattr(
        control, "set_environment", lambda key, value: result.updates.update({key: value})
    )
    return result


def test_default_disabled_preparation_has_no_azure_calls(foundation: Foundation) -> None:
    agent_evaluation.prepare({}, "local")
    assert not foundation.calls
    assert foundation.updates == {
        "AGENT_EVALUATION_ENABLED": "false",
        "AGENT_EVALUATION_TENANT_ID": "",
        "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID": "",
        "AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID": "",
        "AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID": "",
        **{
            name: "false" if key in agent_evaluation.DATA_BOOLEAN_INPUTS else ""
            for key, name in agent_evaluation.DATA_INPUTS.items()
        },
    }


@pytest.mark.parametrize("role", ["foreign", str(uuid4()), "Foundry User"])
def test_unapproved_foundry_role_is_rejected_before_cloud(
    foundation: Foundation, role: str
) -> None:
    foundation.env["AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID"] = role
    with pytest.raises(PlatformFailure, match="agent_evaluation_foundry_user_role_invalid"):
        agent_evaluation.prepare(foundation.env, "local")
    assert not foundation.calls and not foundation.updates


@pytest.mark.parametrize("role", ["foreign", str(uuid4()), "Foundry Project Manager"])
def test_unapproved_project_manager_role_is_rejected_before_cloud(
    foundation: Foundation, role: str
) -> None:
    foundation.env["AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID"] = role
    with pytest.raises(
        PlatformFailure, match="agent_evaluation_foundry_project_manager_role_invalid"
    ):
        agent_evaluation.prepare(foundation.env, "local")
    assert not foundation.calls and not foundation.updates


@pytest.mark.parametrize(
    "change", [{"tid": str(uuid4())}, {"exp": 0}, {"exp": True}, {"oid": "foreign"}]
)
def test_operator_binding_uses_cli_token_without_directory_reads(
    foundation: Foundation, change: dict[str, object]
) -> None:
    claims = {
        "oid": foundation.operator,
        "tid": foundation.env["AGENT_TENANT_ID"],
        "exp": time.time() + 600,
        **change,
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    with pytest.raises(PlatformFailure):
        agent_evaluation.operator_from_token(
            f"header.{payload}.signature", foundation.env["AGENT_TENANT_ID"]
        )
    assert not foundation.calls


def test_disabled_preparation_retains_existing_operator_and_outputs(foundation: Foundation) -> None:
    env = {
        "AGENT_EVALUATION_ENABLED": "false",
        "AGENT_EVALUATION_TENANT_ID": foundation.env["AGENT_TENANT_ID"],
        "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID": foundation.operator,
        "AGENT_EVALUATION_PROJECT_ID": "PRIVATE_PROJECT_CANARY",
        "AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID": "",
        "AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID": "",
        **{
            name: "false" if key in agent_evaluation.DATA_BOOLEAN_INPUTS else ""
            for key, name in agent_evaluation.DATA_INPUTS.items()
        },
    }
    before = dict(env)
    agent_evaluation.prepare(env, "local")
    assert not foundation.calls and not foundation.updates
    assert env == before


def test_preparation_is_read_only_and_allows_staged_parent_preview(
    foundation: Foundation, capsys: pytest.CaptureFixture[str]
) -> None:
    foundation.env["AGENT_EVALUATION_TENANT_ID"] = ""
    foundation.env["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID"] = ""
    before = deepcopy((foundation.env, foundation.account, foundation.deployment))
    agent_evaluation.prepare(foundation.env, "local")
    assert (foundation.env, foundation.account, foundation.deployment) == before
    assert len(foundation.calls) == 4
    assert foundation.updates == {
        "AGENT_EVALUATION_TENANT_ID": foundation.env["AGENT_TENANT_ID"],
        "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID": foundation.operator,
        "AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID": "",
        "AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID": "",
        **{
            name: "false" if key in agent_evaluation.DATA_BOOLEAN_INPUTS else ""
            for key, name in agent_evaluation.DATA_INPUTS.items()
        },
    }
    output = capsys.readouterr().out
    assert json.loads(output)["counts"] == {
        "metadata_reads": 4,
        "account_prerequisites_ready": 0,
        "resource_mutations": 0,
        "model_calls": 0,
    }
    for value in (
        foundation.operator,
        foundation.env["MODEL_ENDPOINT"],
        foundation.env["AGENT_TENANT_ID"],
    ):
        assert value not in output


def test_ready_parent_is_observed_not_reconfigured(
    foundation: Foundation, capsys: pytest.CaptureFixture[str]
) -> None:
    foundation.account["identity"] = {
        "type": "SystemAssigned",
        "principalId": str(uuid4()),
        "tenantId": foundation.env["AGENT_TENANT_ID"],
    }
    properties = foundation.account["properties"]
    assert isinstance(properties, dict)
    properties["allowProjectManagement"] = True
    agent_evaluation.prepare(foundation.env, "local")
    assert json.loads(capsys.readouterr().out)["counts"]["account_prerequisites_ready"] == 1


@pytest.mark.parametrize("value", ["", "TRUE", "yes", "1", "false "])
def test_invalid_enablement_has_no_side_effects(foundation: Foundation, value: str) -> None:
    foundation.env["AGENT_EVALUATION_ENABLED"] = value
    with pytest.raises(PlatformFailure, match="invalid_agent_evaluation_enabled_setting"):
        agent_evaluation.prepare(foundation.env, "local")
    assert not foundation.calls and not foundation.updates


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MODEL_ACCOUNT_ID", "/subscriptions/foreign/resourceGroups/foreign"),
        ("MODEL_ACCOUNT_NAME", "other"),
        ("MODEL_ENDPOINT", "https://other.services.ai.azure.com/"),
        ("ENRICHMENT_DEPLOYMENT", "chat/../other"),
        ("AZURE_ENV_NAME", "../other"),
        ("AZURE_RESOURCE_GROUP", "group/../other"),
        ("ENRICHMENT_CAPACITY", "1.0"),
        ("ENRICHMENT_VERSION", ""),
    ],
)
def test_foreign_or_missing_retained_inputs_fail_before_azure(
    foundation: Foundation, key: str, value: str
) -> None:
    foundation.env[key] = value
    with pytest.raises(PlatformFailure):
        agent_evaluation.prepare(foundation.env, "local")
    assert not foundation.calls and not foundation.updates


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", "other"),
        ("tenantId", "other"),
        ("state", "Disabled"),
        ("user", {"type": "servicePrincipal"}),
    ],
)
def test_cli_context_mismatch_never_rebinds_operator(
    foundation: Foundation, key: str, value: object
) -> None:
    foundation.context[key] = value
    with pytest.raises(PlatformFailure, match="agent_evaluation_cli_context_mismatch"):
        agent_evaluation.prepare(foundation.env, "local")
    assert len(foundation.calls) == 1 and not foundation.updates


@pytest.mark.parametrize(
    "key", ["AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID", "AGENT_EVALUATION_TENANT_ID"]
)
def test_changed_previously_bound_context_fails(foundation: Foundation, key: str) -> None:
    foundation.env[key] = str(uuid4())
    with pytest.raises(PlatformFailure, match="agent_evaluation_operator_context_changed"):
        agent_evaluation.prepare(foundation.env, "local")
    assert len(foundation.calls) == 2 and not foundation.updates


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("disableLocalAuth", False),
        ("allowProjectManagement", "false"),
        ("customSubDomainName", "other"),
        ("provisioningState", "Updating"),
    ],
)
def test_parent_contract_drift_is_not_repaired(
    foundation: Foundation, key: str, value: object
) -> None:
    properties = foundation.account["properties"]
    assert isinstance(properties, dict)
    properties[key] = value
    with pytest.raises(PlatformFailure, match="agent_evaluation_retained_account_mismatch"):
        agent_evaluation.prepare(foundation.env, "local")
    assert not foundation.updates


@pytest.mark.parametrize(
    "identity",
    [
        {"type": "UserAssigned"},
        {"type": "SystemAssigned", "principalId": str(uuid4()), "tenantId": str(uuid4())},
        {"type": "SystemAssigned", "principalId": "invalid"},
    ],
)
def test_unexpected_parent_identity_is_not_granted_access(
    foundation: Foundation, identity: object
) -> None:
    foundation.account["identity"] = identity
    with pytest.raises(PlatformFailure):
        agent_evaluation.prepare(foundation.env, "local")
    assert not foundation.updates


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("model", "version", "other"),
        ("model", "name", "other"),
        ("model", "format", "other"),
        ("capabilities", "chatCompletion", "false"),
        ("sku", "capacity", True),
        ("sku", "capacity", 11),
        ("sku", "name", "ProvisionedManaged"),
        ("properties", "versionUpgradeOption", "OnceNewDefaultVersionAvailable"),
        ("properties", "provisioningState", "Updating"),
    ],
)
def test_model_capacity_or_behavior_drift_blocks_preparation(
    foundation: Foundation, section: str, key: str, value: object
) -> None:
    properties = foundation.deployment["properties"]
    assert isinstance(properties, dict)
    target = (
        foundation.deployment["sku"]
        if section == "sku"
        else properties
        if section == "properties"
        else properties[section]
    )
    assert isinstance(target, dict)
    target[key] = value
    with pytest.raises(PlatformFailure, match="agent_evaluation_retained_chat_mismatch"):
        agent_evaluation.prepare(foundation.env, "local")
    assert not foundation.updates


def test_native_failure_stops_without_environment_changes(
    foundation: Foundation, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed(*args: object, **kwargs: object) -> object:
        raise PlatformFailure("command_failed_metadata")

    monkeypatch.setattr(control, "rest", failed)
    with pytest.raises(PlatformFailure, match="command_failed_metadata"):
        agent_evaluation.prepare(foundation.env, "local")
    assert not foundation.updates


def test_cli_dispatches_preparation_without_build_or_evaluation_imports(
    foundation: Foundation, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(control, "environment", lambda: foundation.env)
    monkeypatch.setattr(sys, "argv", ["newsloom-platform", "prepare-agent-evaluation-layer"])
    cli.main()
    assert len(foundation.calls) == 4
    assert not any(
        name == "deepeval" or name.startswith("agent_evaluation.") for name in sys.modules
    )


def test_owning_layer_has_only_project_and_custom_operator_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    layer = root / "infra" / "agent-evaluation"
    resources = {
        (kind, name)
        for path in layer.glob("*.tf")
        for kind, name in re.findall(
            r'^resource "([^"]+)" "([^"]+)"', path.read_text(), re.MULTILINE
        )
    }
    assert resources == {
        ("azurerm_cognitive_account_project", "evaluation"),
        ("azurerm_role_definition", "operator"),
        ("azurerm_role_assignment", "operator"),
        ("azurerm_role_assignment", "foundry_user"),
        ("azurerm_role_assignment", "foundry_project_manager"),
        ("azapi_resource", "evaluation_storage"),
        ("azapi_resource", "evaluation_storage_connection"),
        ("azapi_resource", "data_grants"),
    }
    source = (root / "infra" / "main.tf").read_text()
    account = source.split('resource "azurerm_cognitive_account" "models" {', 1)[1].split(
        'resource "azurerm_cognitive_deployment"', 1
    )[0]
    assert "prevent_destroy = true" in account
    assert "project_management_enabled = true" in account
    assert 'type = "SystemAssigned"' in account
    assert "var.enabled" not in account and "count" not in account
    yaml = (root / "azure.yaml").read_text()
    block = yaml.split("    - name: agent-evaluation\n", 1)[1].split("    - name:", 1)[0]
    assert "      dependsOn:\n        - application\n" in block
    assert "newsloom-platform prepare-agent-evaluation-layer" in block
    assert "postprovision" not in block
    backend = json.loads((layer / "provider.conf.json").read_text())
    assert backend["use_azuread_auth"] is True
    assert backend["key"] == "newsloom/${AZURE_ENV_NAME}-agent-evaluation.tfstate"
