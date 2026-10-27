from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
from newsloom_platform import agent_identity, control
from newsloom_platform.config import PlatformFailure


@dataclass
class Directory:
    operator: str
    env: dict[str, str]
    apps: dict[str, dict[str, object]]
    principals: dict[str, dict[str, object]]
    federation: dict[str, object]
    identity: dict[str, object]
    grants: list[dict[str, object]]
    calls: list[list[str]] = field(default_factory=list)
    updates: dict[str, str] = field(default_factory=dict)

    def azure(self, arguments: list[str], category: str, **kwargs: object) -> object:
        self.calls.append(arguments)
        if arguments[:2] == ["account", "show"]:
            return self.env["MCP_TENANT_ID"]
        if arguments[:3] == ["ad", "app", "list"]:
            return list(self.apps.values())
        if arguments[:3] == ["ad", "app", "show"]:
            return self.apps[arguments[-1]]
        if arguments[:3] == ["ad", "signed-in-user", "show"]:
            return self.operator
        if arguments[:4] == ["ad", "app", "owner", "list"]:
            return self.apps[arguments[-1]].get("owners", [{"id": self.operator}])
        if arguments[:3] == ["ad", "sp", "list"]:
            return [
                principal
                for client, principal in self.principals.items()
                if client in arguments[-1]
            ]
        if arguments[:4] == ["ad", "app", "federated-credential", "list"]:
            return [self.federation] if self.federation else []
        if arguments[:2] == ["identity", "list"]:
            return [self.identity]
        if arguments[0] == "rest":
            assert arguments[1] == "--url"
            assert arguments[2].startswith(
                "https://graph.microsoft.com/v1.0/oauth2PermissionGrants?$filter=clientId%20eq%20'"
            )
            return [grant for grant in self.grants if str(grant["clientId"]) in arguments[2]]
        raise AssertionError(f"unexpected_inventory_command: {arguments[:3]}")


@pytest.fixture
def directory(monkeypatch: pytest.MonkeyPatch) -> Directory:
    tenant, subscription, mcp, mcp_public, api, public, news_scope, invoke_scope = (
        str(uuid4()) for _ in range(8)
    )
    principal_ids = {client: str(uuid4()) for client in (mcp, mcp_public, api, public)}

    def resource(client: str, scope: str) -> list[dict[str, object]]:
        return [{"resourceAppId": client, "resourceAccess": [{"id": scope, "type": "Scope"}]}]

    def app(client: str, name: str) -> dict[str, object]:
        return {
            "id": str(uuid4()),
            "appId": client,
            "displayName": name,
            "signInAudience": "AzureADMyOrg",
            "passwordCredentials": [],
            "keyCredentials": [],
            "appRoles": [],
            "publicClient": {"redirectUris": []},
            "api": {},
            "web": {"redirectUris": []},
            "spa": {"redirectUris": []},
        }

    apps = {
        mcp: app(mcp, "newsloom-test-api"),
        mcp_public: app(mcp_public, "newsloom-test-vscode"),
        api: app(api, "newsloom-test-agent-api"),
        public: app(public, "newsloom-test-agent-acceptance"),
    }
    for client, scope, value in (
        (mcp, news_scope, "news.read"),
        (api, invoke_scope, "news.agent"),
    ):
        apps[client].update(
            {
                "identifierUris": [f"api://{client}"],
                "api": {
                    "requestedAccessTokenVersion": 2,
                    "oauth2PermissionScopes": [
                        {"id": scope, "value": value, "type": "User", "isEnabled": True}
                    ],
                },
            }
        )
    apps[api]["requiredResourceAccess"] = resource(mcp, news_scope)
    for client, target, scope, callback in (
        (mcp_public, mcp, news_scope, "http://localhost"),
        (public, api, invoke_scope, agent_identity.CALLBACK),
    ):
        apps[client].update(
            {
                "isFallbackPublicClient": True,
                "publicClient": {"redirectUris": [callback]},
                "requiredResourceAccess": resource(target, scope),
            }
        )
    principal = str(uuid4())
    env = {
        "AZURE_ENV_NAME": "test",
        "AZURE_SUBSCRIPTION_ID": subscription,
        "AZURE_RESOURCE_GROUP": "rg-newsloom-test",
        "MCP_TENANT_ID": tenant,
        "MCP_API_CLIENT_ID": mcp,
        "MCP_PUBLIC_CLIENT_ID": mcp_public,
        "AGENT_API_CLIENT_ID": api,
        "AGENT_PUBLIC_CLIENT_ID": public,
        "AGENT_ENABLED": "true",
        "AGENT_CONSENT_ENABLED": "true",
    }
    result = Directory(
        operator=str(uuid4()),
        env=env,
        apps=apps,
        principals={
            client: {
                "appId": client,
                "id": object_id,
                "appOwnerOrganizationId": tenant,
                "accountEnabled": True,
            }
            for client, object_id in principal_ids.items()
        },
        federation={
            "id": str(uuid4()),
            "name": "agent-managed-identity",
            "issuer": f"https://login.microsoftonline.com/{tenant}/v2.0",
            "subject": principal,
            "audiences": ["api://AzureADTokenExchange"],
        },
        identity={
            "id": f"/subscriptions/{subscription}/resourceGroups/rg-newsloom-test"
            "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-newsloom-test-agent",
            "tenantId": tenant,
            "principalId": principal,
        },
        grants=[
            {
                "id": f"opaque_consent_{index}",
                "clientId": principal_ids[client],
                "resourceId": principal_ids[target],
                "scope": scope,
                "consentType": "AllPrincipals",
                "principalId": None,
            }
            for index, (client, target, scope) in enumerate(
                [(api, mcp, "news.read"), (public, api, "news.agent")]
            )
        ],
    )
    monkeypatch.setattr(control, "azure", result.azure)
    monkeypatch.setattr(
        control, "set_environment", lambda key, value: result.updates.update({key: value})
    )
    return result


def test_disabled_layer_never_inventories_or_changes_cloud(directory: Directory) -> None:
    agent_identity.prepare({}, "local")
    assert not directory.calls
    assert directory.updates["AGENT_ENABLED"] == "false"
    assert directory.updates["AGENT_CONSENT_ENABLED"] == "false"
    assert directory.updates["AGENT_EXISTING_API_OBJECT_ID"] == ""


def test_exact_owning_inventory_and_private_retained_inputs(
    directory: Directory, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = deepcopy((directory.apps, directory.principals, directory.grants))
    agent_identity.prepare(directory.env, "local")
    assert directory.updates["AGENT_TENANT_ID"] == directory.env["MCP_TENANT_ID"]
    assert directory.updates["AGENT_EXISTING_API_CLIENT_ID"] == directory.env["AGENT_API_CLIENT_ID"]
    assert directory.updates["AGENT_EXISTING_FEDERATION_ID"] == directory.federation["id"]
    assert directory.updates["AGENT_EXISTING_MCP_CONSENT_ID"] == "opaque_consent_0"
    assert directory.updates["AGENT_EXISTING_CLIENT_CONSENT_ID"] == "opaque_consent_1"
    assert baseline == (directory.apps, directory.principals, directory.grants)
    assert not any(
        word in call
        for call in directory.calls
        for word in ("create", "update", "delete", "add", "grant")
    )
    output = capsys.readouterr().out
    assert all(value not in output for value in directory.env.values() if len(value) == 36)


def test_new_registrations_are_not_selected_by_display_name(directory: Directory) -> None:
    for label in ("AGENT_API_CLIENT_ID", "AGENT_PUBLIC_CLIENT_ID"):
        directory.apps.pop(directory.env[label])
        directory.env.pop(label)
    agent_identity.prepare(directory.env, "local")
    assert directory.updates["AGENT_EXISTING_API_OBJECT_ID"] == ""
    assert directory.updates["AGENT_MCP_SCOPE_ID"]


def test_legacy_agent_scope_is_not_adopted(directory: Directory) -> None:
    directory.apps[directory.env["AGENT_API_CLIENT_ID"]]["api"] = {
        "requestedAccessTokenVersion": 2,
        "oauth2PermissionScopes": [
            {"id": str(uuid4()), "value": "agent.invoke", "type": "User", "isEnabled": True}
        ],
    }
    with pytest.raises(PlatformFailure, match="agent_scope_contract_mismatch"):
        agent_identity.inventory(directory.env)
    assert not directory.updates


def test_legacy_agent_consent_is_not_adopted(directory: Directory) -> None:
    directory.grants[1]["scope"] = "agent.invoke"
    with pytest.raises(PlatformFailure, match="agent_consent_mismatch"):
        agent_identity.inventory(directory.env)
    assert not directory.updates


def test_name_collision_requires_explicit_identity(directory: Directory) -> None:
    directory.env.pop("AGENT_API_CLIENT_ID")
    directory.env.pop("AGENT_PUBLIC_CLIENT_ID")
    with pytest.raises(PlatformFailure, match="requires_explicit_identity"):
        agent_identity.inventory(directory.env)
    assert not directory.updates


@pytest.mark.parametrize(
    "owners", [[], [{"id": str(uuid4())}], [{"id": str(uuid4())}, {"id": str(uuid4())}]]
)
def test_foreign_or_shared_ownership_requires_explicit_review(
    directory: Directory, owners: list[dict[str, str]]
) -> None:
    directory.apps[directory.env["AGENT_API_CLIENT_ID"]]["owners"] = owners
    with pytest.raises(PlatformFailure, match="agent_registration_ownership_mismatch"):
        agent_identity.inventory(directory.env)
    assert not directory.updates


@pytest.mark.parametrize("setting", ["AGENT_ENABLED", "AGENT_CONSENT_ENABLED"])
def test_invalid_opt_in_never_calls_cloud(directory: Directory, setting: str) -> None:
    with pytest.raises(PlatformFailure, match="invalid_agent_enabled_setting"):
        agent_identity.prepare({setting: "yes"}, "local")
    assert not directory.calls


@pytest.mark.parametrize(
    "field",
    ["MCP_API_CLIENT_ID", "MCP_PUBLIC_CLIENT_ID", "AGENT_PUBLIC_CLIENT_ID"],
)
def test_existing_registration_cannot_be_repurposed(directory: Directory, field: str) -> None:
    directory.env["AGENT_API_CLIENT_ID"] = directory.env[field]
    with pytest.raises(PlatformFailure, match="separate_agent_registrations_required"):
        agent_identity.inventory(directory.env)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("passwordCredentials", [{"keyId": "PRIVATE_CREDENTIAL_CANARY"}]),
        ("keyCredentials", [{"keyId": "PRIVATE_CERT_CANARY"}]),
        ("appRoles", [{"value": "news.read"}]),
        ("signInAudience", "AzureADMultipleOrgs"),
        ("appId", str(uuid4())),
        ("displayName", "another-owned-app"),
        ("web", {"redirectUris": ["https://unapproved.invalid/callback"]}),
        ("spa", {"redirectUris": ["http://127.0.0.1:8400/callback"]}),
    ],
)
@pytest.mark.parametrize("label", ["AGENT_API_CLIENT_ID", "AGENT_PUBLIC_CLIENT_ID"])
def test_adoption_rejects_secrets_app_roles_and_unapproved_surfaces(
    directory: Directory, field: str, value: object, label: str
) -> None:
    directory.apps[directory.env[label]][field] = value
    with pytest.raises(PlatformFailure):
        agent_identity.inventory(directory.env)


@pytest.mark.parametrize(
    "callback",
    [
        "http://localhost:*",
        "http://127.0.0.1:8401/callback",
        "http://127.0.0.1:8400/other",
        "http://localhost.attacker.invalid/callback",
        "https://vscode.dev/redirect",
    ],
)
def test_exact_separate_pkce_callback(directory: Directory, callback: str) -> None:
    directory.apps[directory.env["AGENT_PUBLIC_CLIENT_ID"]]["publicClient"] = {
        "redirectUris": [callback]
    }
    with pytest.raises(PlatformFailure, match="agent_pkce_contract_mismatch"):
        agent_identity.inventory(directory.env)


@pytest.mark.parametrize("mismatch", ["tenant", "client", "disabled"])
def test_foreign_or_wrong_principal_is_not_adopted(directory: Directory, mismatch: str) -> None:
    principal = directory.principals[directory.env["AGENT_API_CLIENT_ID"]]
    principal[
        {"tenant": "appOwnerOrganizationId", "client": "appId", "disabled": "accountEnabled"}[
            mismatch
        ]
    ] = False if mismatch == "disabled" else str(uuid4())
    with pytest.raises(PlatformFailure, match="agent_principal_contract_mismatch"):
        agent_identity.inventory(directory.env)


@pytest.mark.parametrize("mismatch", ["issuer", "subject", "audiences", "name", "tenant"])
def test_federation_must_match_exact_tenant_identity_and_exchange_audience(
    directory: Directory, mismatch: str
) -> None:
    if mismatch == "tenant":
        directory.identity["tenantId"] = str(uuid4())
    else:
        directory.federation[mismatch] = {
            "issuer": "https://token.actions.githubusercontent.com",
            "subject": directory.env["AGENT_API_CLIENT_ID"],
            "audiences": ["api://AzureADTokenExchange", "api://other"],
            "name": "another-credential",
        }[mismatch]
    with pytest.raises(PlatformFailure, match="agent_federation_contract_mismatch"):
        agent_identity.inventory(directory.env)


def test_federation_accepts_case_equivalent_arm_identity_path(directory: Directory) -> None:
    resource_id = directory.identity["id"]
    assert isinstance(resource_id, str)
    directory.identity["id"] = resource_id.replace("/resourceGroups/", "/resourcegroups/")
    inventory = agent_identity.inventory(directory.env)
    assert inventory["AGENT_EXISTING_FEDERATION_ID"] == directory.federation["id"]


@pytest.mark.parametrize("resource_id", [None, 7, "/subscriptions/foreign/identities/agent"])
def test_federation_rejects_foreign_or_malformed_arm_identity_path(
    directory: Directory, resource_id: object
) -> None:
    directory.identity["id"] = resource_id
    with pytest.raises(PlatformFailure, match="agent_federation_contract_mismatch"):
        agent_identity.inventory(directory.env)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope", "news.read news.write"),
        ("resourceId", str(uuid4())),
        ("consentType", "Principal"),
        ("principalId", str(uuid4())),
    ],
)
def test_consent_inventory_never_adopts_broader_or_other_user_grants(
    directory: Directory, field: str, value: object
) -> None:
    directory.grants[0][field] = value
    with pytest.raises(PlatformFailure, match="agent_consent_mismatch"):
        agent_identity.inventory(directory.env)


def test_existing_consent_cannot_be_disabled_silently(directory: Directory) -> None:
    directory.env["AGENT_CONSENT_ENABLED"] = "false"
    with pytest.raises(PlatformFailure, match="retained_opt_in"):
        agent_identity.prepare(directory.env, "local")
    assert not directory.updates


def test_directory_permission_and_federation_errors_are_not_swallowed(
    directory: Directory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(*args: object, **kwargs: object) -> object:
        raise PlatformFailure("command_failed_directory_permission")

    monkeypatch.setattr(control, "azure", denied)
    with pytest.raises(PlatformFailure, match="directory_permission"):
        agent_identity.prepare(directory.env, "local")
    assert not directory.updates


def test_owning_layers_do_not_change_shared_identity_set_or_mcp_configuration() -> None:
    root = Path(__file__).parents[1]
    shared = (root / "infra/main.tf").read_text()
    assert 'workloads = toset(["ingestion", "enrichment", "mcp", "migrations"])' in shared
    identity = (root / "infra/agent-identity/main.tf").read_text()
    for forbidden in (
        'resource "azurerm_cognitive_deployment"',
        'resource "azurerm_postgresql',
        'resource "azuread_app_role_assignment"',
        'resource "azuread_application_password"',
        'resource "azuread_application_certificate"',
        'resource "azurerm_container_app"',
    ):
        assert forbidden not in identity
    yaml = (root / "azure.yaml").read_text()
    assert "newsloom-platform prepare-agent-identity" in yaml
    assert (
        '"key": "newsloom/${AZURE_ENV_NAME}-agent-identity.tfstate"'
        in (root / "infra/agent-identity/provider.conf.json").read_text()
    )
