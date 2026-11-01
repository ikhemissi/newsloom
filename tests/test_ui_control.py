import base64
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
from newsloom_platform import agent_identity, control, mcp_identity, ui
from newsloom_platform.config import PlatformFailure


@dataclass
class UiCase:
    env: dict[str, str]
    app: dict[str, object]
    registration: dict[str, object]
    grants: list[dict[str, str]]
    consents: list[dict[str, object]] = field(default_factory=list)


def test_ui_layers_use_native_distinct_secretless_state_templates() -> None:
    keys: set[str] = set()
    for name in ("ui-identity", "ui"):
        path = Path(__file__).resolve().parents[1] / "infra" / name / "provider.conf.json"
        config = json.loads(path.read_text())
        assert config == {
            "resource_group_name": "${RS_RESOURCE_GROUP}",
            "storage_account_name": "${RS_STORAGE_ACCOUNT}",
            "container_name": "${RS_CONTAINER_NAME}",
            "key": f"newsloom/${{AZURE_ENV_NAME}}-{name}.tfstate",
            "use_azuread_auth": True,
        }
        keys.add(config["key"])
    assert len(keys) == 2


@pytest.fixture
def ui_case(monkeypatch: pytest.MonkeyPatch) -> UiCase:
    (
        subscription,
        tenant,
        api,
        client,
        scope,
        api_principal,
        client_principal,
        mi_client,
        mi_principal,
    ) = (str(uuid4()) for _ in range(9))
    group = f"/subscriptions/{subscription}/resourceGroups/rg-newsloom-test"
    registry = f"acrnewsloomtest{hashlib.sha256(f'{subscription}/test'.encode()).hexdigest()[:8]}"
    identity_id = (
        f"{group}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-newsloom-test-ui"
    )
    env = {
        "UI_ENABLED": "true",
        "UI_CONSENT_ENABLED": "true",
        "AZURE_ENV_NAME": "test",
        "AZURE_SUBSCRIPTION_ID": subscription,
        "AZURE_RESOURCE_GROUP": "rg-newsloom-test",
        "AZURE_CONTAINER_APPS_ENVIRONMENT_ID": (
            f"{group}/providers/Microsoft.App/managedEnvironments/cae-newsloom-test"
        ),
        "AZURE_CONTAINER_REGISTRY_ID": (
            f"{group}/providers/Microsoft.ContainerRegistry/registries/{registry}"
        ),
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": f"{registry}.azurecr.io",
        "AGENT_TENANT_ID": tenant,
        "AGENT_API_CLIENT_ID": api,
        "AGENT_RESOURCE_URL": "https://agent.test/a2a",
        "UI_AGENT_API_PRINCIPAL_ID": api_principal,
        "UI_AGENT_SCOPE_ID": scope,
        "UI_CLIENT_ID": client,
        "UI_ORIGIN": "https://web-newsloom-test.owned.azurecontainerapps.io",
        "UI_DEPLOYED_ORIGIN": "https://web-newsloom-test.owned.azurecontainerapps.io",
        "UI_APP_ID": f"{group}/providers/Microsoft.App/containerApps/web-newsloom-test",
        "UI_APP_NAME": "web-newsloom-test",
        "WEB_IMAGE_REVISION": "2" * 64,
        "WEB_IMAGE": f"{registry}.azurecr.io/newsloom-web@sha256:" + "1" * 64,
        "UI_IDENTITY_BASE64": base64.b64encode(
            json.dumps(
                {
                    "id": identity_id,
                    "client_id": mi_client,
                    "principal_id": mi_principal,
                }
            ).encode()
        ).decode(),
    }
    registration: dict[str, object] = {
        "id": str(uuid4()),
        "appId": client,
        "displayName": "newsloom-test-ui",
        "signInAudience": "AzureADMyOrg",
        "passwordCredentials": [],
        "keyCredentials": [],
        "spa": {"redirectUris": [env["UI_ORIGIN"] + "/auth/callback", env["UI_ORIGIN"] + "/"]},
        "web": {"redirectUris": []},
        "publicClient": {"redirectUris": []},
        "requiredResourceAccess": [
            {
                "resourceAppId": api,
                "resourceAccess": [{"id": scope, "type": "Scope"}],
            }
        ],
    }
    app: dict[str, object] = {
        "id": env["UI_APP_ID"],
        "identity": {
            "type": "UserAssigned",
            "userAssignedIdentities": {
                identity_id: {"clientId": mi_client, "principalId": mi_principal},
            },
        },
        "properties": {
            "environmentId": env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"],
            "provisioningState": "Succeeded",
            "latestReadyRevisionName": "ui--ready",
            "latestRevisionName": "ui--ready",
            "workloadProfileName": "Consumption",
            "configuration": {
                "activeRevisionsMode": "Single",
                "registries": [
                    {"server": env["AZURE_CONTAINER_REGISTRY_ENDPOINT"], "identity": identity_id}
                ],
                "ingress": {
                    "external": True,
                    "allowInsecure": False,
                    "targetPort": 8080,
                    "fqdn": env["UI_ORIGIN"].removeprefix("https://"),
                },
            },
            "template": {
                "scale": {"minReplicas": 0, "maxReplicas": 1},
                "containers": [
                    {
                        "name": "web",
                        "image": env["WEB_IMAGE"],
                        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                        "env": [
                            {"name": key, "value": value}
                            for key, value in {
                                "UI_CONFIG_BASE64": ui.encoded_config(env),
                                "AGENT_ORIGIN": "https://agent.test",
                                "UI_RUNTIME_REVISION": env["WEB_IMAGE_REVISION"],
                            }.items()
                        ],
                    }
                ],
            },
        },
    }
    grants = [{"roleDefinitionName": "AcrPull", "scope": env["AZURE_CONTAINER_REGISTRY_ID"]}]
    consents: list[dict[str, object]] = [
        {
            "id": "fixture-consent",
            "clientId": client_principal,
            "resourceId": api_principal,
            "scope": "news.agent",
            "consentType": "AllPrincipals",
            "principalId": None,
        }
    ]
    case = UiCase(env, app, registration, grants, consents)
    monkeypatch.setattr(
        agent_identity,
        "inventory",
        lambda _: {
            "AGENT_EXISTING_API_PRINCIPAL_ID": api_principal,
            "AGENT_EXISTING_SCOPE_ID": scope,
        },
    )

    def azure(arguments: list[str], category: str) -> object:
        if category == "ui_registration_discovery":
            return [case.registration]
        if category == "ui_exact_registration_inventory":
            return case.registration
        if category == "ui_principal_inventory":
            return [{"appId": client, "id": client_principal, "accountEnabled": True}]
        if category == "ui_registry_role_readback":
            return case.grants
        if category == "ui_delegated_consent_inventory":
            return case.consents
        raise AssertionError(category)

    def rest(url: str, category: str) -> object:
        if category == "ui_environment_inventory":
            return {
                "id": env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"],
                "properties": {"defaultDomain": "owned.azurecontainerapps.io"},
            }
        assert category == "ui_app_readback"
        return case.app

    monkeypatch.setattr(control, "azure", azure)
    monkeypatch.setattr(control, "rest", rest)
    return case


def test_exact_ui_readback_is_content_free_and_read_only(
    ui_case: UiCase, capsys: pytest.CaptureFixture[str]
) -> None:
    before = deepcopy(ui_case.app)
    ui.verify(ui_case.env, "local")
    assert before == ui_case.app
    output = capsys.readouterr().out
    assert "ui_deployment_readback" in output
    assert ui_case.env["UI_CLIENT_ID"] not in output
    assert ui_case.env["AGENT_TENANT_ID"] not in output


@pytest.mark.parametrize("minimum", [None, 0, 1])
def test_azure_omitted_zero_minimum_replica_is_not_profile_drift(
    ui_case: UiCase,
    minimum: int | None,
) -> None:
    properties = ui_case.app["properties"]
    assert isinstance(properties, dict)
    template = properties["template"]
    assert isinstance(template, dict)
    template["scale"] = {"minReplicas": minimum, "maxReplicas": 1}
    if minimum in (None, 0):
        ui.verify(ui_case.env, "local")
    else:
        with pytest.raises(PlatformFailure, match="ui_deployment_readback_mismatch"):
            ui.verify(ui_case.env, "local")


@pytest.mark.parametrize("field", ["passwordCredentials", "keyCredentials"])
def test_ui_registration_never_adopts_secrets(ui_case: UiCase, field: str) -> None:
    ui_case.registration[field] = [{"canary": "secret-canary"}]
    with pytest.raises(PlatformFailure, match="ui_registration_contract_mismatch"):
        ui.identity_inventory(ui_case.env)


def test_ui_config_requires_a_separate_client_and_fixed_agent(ui_case: UiCase) -> None:
    config = ui.public_config(ui_case.env)
    assert set(config) == {"tenantId", "clientId", "agentUrl", "agentScope"}
    with pytest.raises(PlatformFailure, match="separate_ui_client_required"):
        ui.public_config({**ui_case.env, "UI_CLIENT_ID": ui_case.env["AGENT_API_CLIENT_ID"]})
    with pytest.raises(PlatformFailure, match="invalid_ui_agent_interface"):
        ui.public_config({**ui_case.env, "AGENT_RESOURCE_URL": "https://user@agent.test/a2a"})


def test_ui_adoption_requires_explicit_identity_and_exact_permissions(ui_case: UiCase) -> None:
    with pytest.raises(PlatformFailure, match="requires_explicit_identity"):
        ui.identity_inventory(
            {key: value for key, value in ui_case.env.items() if key != "UI_CLIENT_ID"}
        )
    ui_case.registration["requiredResourceAccess"] = []
    with pytest.raises(PlatformFailure, match="delegated_permission_mismatch"):
        ui.identity_inventory(ui_case.env)


def test_ui_adoption_rejects_native_or_foreign_redirects(ui_case: UiCase) -> None:
    ui_case.registration["spa"] = {"redirectUris": ["http://127.0.0.1:8400/callback"]}
    with pytest.raises(PlatformFailure, match="ui_registration_contract_mismatch"):
        ui.identity_inventory(ui_case.env)


def test_ui_news_permission_transition_is_exact_and_preserves_agent(
    ui_case: UiCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp, principal, scope = str(uuid4()), str(uuid4()), str(uuid4())
    ui_case.env.update(
        {
            "UI_NEWS_ENABLED": "true",
            "UI_MCP_PERMISSION_ENABLED": "true",
            "MCP_API_CLIENT_ID": mcp,
            "MCP_RESOURCE_URL": "https://mcp.test/mcp",
        }
    )
    monkeypatch.setattr(
        mcp_identity,
        "inventory",
        lambda _: {
            "MCP_EXISTING_API_PRINCIPAL_ID": principal,
            "MCP_EXISTING_SCOPE_ID": scope,
        },
    )
    initial = ui.identity_inventory(ui_case.env)
    assert initial["UI_NEWS_PERMISSION_PRESENT"] == "false"
    access = ui_case.registration["requiredResourceAccess"]
    assert isinstance(access, list)
    access.append({"resourceAppId": mcp, "resourceAccess": [{"id": scope, "type": "Scope"}]})
    ui_case.consents.append(
        {
            "id": "fixture-mcp-consent",
            "clientId": ui_case.consents[0]["clientId"],
            "resourceId": principal,
            "scope": "news.read",
            "consentType": "AllPrincipals",
            "principalId": None,
        }
    )
    final = ui.identity_inventory(ui_case.env)
    assert final["UI_NEWS_PERMISSION_PRESENT"] == "true"
    assert final["UI_EXISTING_MCP_CONSENT_ID"] == "fixture-mcp-consent"
    assert final["UI_EXISTING_CONSENT_ID"] == "fixture-consent"
    assert ui.public_config(ui_case.env)["mcpScope"] == f"api://{mcp}/news.read"
    rollback = {**ui_case.env, "UI_NEWS_ENABLED": "false"}
    assert ui.identity_inventory(rollback)["UI_NEWS_PERMISSION_PRESENT"] == "true"
    assert len(ui.public_config(rollback)) == 4
    access.append({"resourceAppId": str(uuid4()), "resourceAccess": []})
    with pytest.raises(PlatformFailure, match="ui_delegated_permission_mismatch"):
        ui.identity_inventory(ui_case.env)


@pytest.mark.parametrize("change", ["foreign_resource", "broader_scope", "duplicate"])
def test_ui_consent_inventory_rejects_grants_outside_its_exact_resources(
    ui_case: UiCase,
    change: str,
) -> None:
    row = dict(ui_case.consents[0])
    if change == "foreign_resource":
        row["resourceId"] = str(uuid4())
    elif change == "broader_scope":
        row["scope"] = "news.agent foreign.scope"
    else:
        ui_case.consents.append(row)
    if change != "duplicate":
        ui_case.consents[0] = row
    with pytest.raises(PlatformFailure, match="ui_delegated_consent_mismatch"):
        ui.identity_inventory(ui_case.env)


def test_ui_layer_preparation_binds_source_and_validated_runtime_config(
    ui_case: UiCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: dict[str, str] = {}
    monkeypatch.setattr(control, "run", lambda *_: "/tmp/ui-test-source")
    monkeypatch.setattr(control, "source_hash", lambda _: "2" * 64)
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    ui.prepare(ui_case.env, "local")
    assert json.loads(base64.b64decode(updates["UI_CONFIG_BASE64"])) == ui.public_config(
        ui_case.env
    )
    monkeypatch.setattr(control, "source_hash", lambda _: "3" * 64)
    with pytest.raises(PlatformFailure, match="ui_image_source_mismatch"):
        ui.prepare(ui_case.env, "local")


def test_ui_readback_rejects_image_and_grant_drift(ui_case: UiCase) -> None:
    with pytest.raises(PlatformFailure, match="ui_deployment_readback_mismatch"):
        ui.verify({**ui_case.env, "WEB_IMAGE_REVISION": "3" * 64}, "local")
    ui_case.grants[0]["roleDefinitionName"] = "Owner"
    with pytest.raises(PlatformFailure, match="ui_registry_role_mismatch"):
        ui.verify(ui_case.env, "local")


def test_disabled_ui_has_no_inventory_or_image_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: dict[str, str] = {}
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    ui.prepare({}, "local")
    assert updates == {
        "UI_ENABLED": "false",
        "WEB_IMAGE": "",
        "WEB_IMAGE_REVISION": "",
        "UI_CONFIG_BASE64": "",
    }
    with pytest.raises(PlatformFailure, match="ui_layer_not_enabled"):
        ui.build({}, "local")
