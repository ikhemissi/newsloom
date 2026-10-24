from uuid import uuid4

import pytest
from newsloom_platform import control, mcp_identity
from newsloom_platform.config import PlatformFailure


def test_missing_registrations_prepare_only_private_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tenant = str(uuid4())
    calls: list[list[str]] = []

    def azure(arguments: list[str], category: str, **kwargs: object) -> object:
        calls.append(arguments)
        return tenant if arguments[:2] == ["account", "show"] else []

    updates: dict[str, str] = {}
    monkeypatch.setattr(control, "azure", azure)
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    mcp_identity.prepare({"AZURE_ENV_NAME": "test"}, "fixture")
    assert updates["MCP_TENANT_ID"] == tenant
    assert updates["MCP_EXISTING_RESOURCE_IDENTIFIER"] == "false"
    assert all(
        not value
        for key, value in updates.items()
        if key not in ("MCP_TENANT_ID", "MCP_EXISTING_RESOURCE_IDENTIFIER")
    )
    assert not any("create" in call or "update" in call for call in calls)
    output = capsys.readouterr().out
    assert tenant not in output
    first = dict(updates)
    mcp_identity.prepare({"AZURE_ENV_NAME": "test"}, "fixture")
    assert updates == first


def test_name_discovery_cannot_choose_or_overwrite_a_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def azure(arguments: list[str], category: str, **kwargs: object) -> object:
        return (
            str(uuid4())
            if arguments[:2] == ["account", "show"]
            else [{"displayName": "newsloom-test-api", "appId": str(uuid4())}]
        )

    monkeypatch.setattr(control, "azure", azure)
    with pytest.raises(PlatformFailure, match="requires_explicit_identity"):
        mcp_identity.inventory({"AZURE_ENV_NAME": "test"})


@pytest.mark.parametrize("callback", sorted(mcp_identity.CALLBACKS))
@pytest.mark.parametrize("resource_alias", [False, True])
@pytest.mark.parametrize(
    "mismatch",
    [
        "",
        "scope",
        "callback",
        "permission",
        "ephemeral",
        "lookalike",
        "wildcard",
        "path",
        "resource",
        "missing-base",
    ],
)
def test_exact_registration_adoption_preserves_existing_scope(
    mismatch: str,
    callback: str,
    resource_alias: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, api_id, client_id, api_object, client_object, scope, principal = (
        str(uuid4()) for _ in range(7)
    )
    api = {
        "id": api_object,
        "appId": api_id,
        "signInAudience": "AzureADMyOrg",
        "identifierUris": ["api://" + api_id]
        + (["https://newsloom.test/mcp"] if resource_alias else []),
        "api": {
            "requestedAccessTokenVersion": 2,
            "oauth2PermissionScopes": [
                {
                    "id": scope,
                    "value": "news.read" if mismatch != "scope" else "admin",
                    "isEnabled": True,
                    "type": "User",
                }
            ],
        },
    }
    if mismatch == "resource":
        api["identifierUris"] = ["api://" + api_id, "https://unapproved.test/mcp"]
    if mismatch == "missing-base":
        api["identifierUris"] = ["https://newsloom.test/mcp"]
    client = {
        "id": client_object,
        "appId": client_id,
        "signInAudience": "AzureADMyOrg",
        "isFallbackPublicClient": True,
        "passwordCredentials": [],
        "keyCredentials": [],
        "publicClient": {
            "redirectUris": [
                {
                    "callback": "https://evil.invalid",
                    "ephemeral": "http://localhost:53995",
                    "lookalike": "http://localhost.attacker.invalid",
                    "wildcard": "http://localhost:*",
                    "path": "http://localhost/unapproved",
                }.get(mismatch, callback)
            ]
        },
        "requiredResourceAccess": [
            {
                "resourceAppId": api_id,
                "resourceAccess": [
                    {"id": scope if mismatch != "permission" else str(uuid4()), "type": "Scope"}
                ],
            }
        ],
    }

    def azure(arguments: list[str], category: str, **kwargs: object) -> object:
        if arguments[:2] == ["account", "show"]:
            return tenant
        if arguments[:3] == ["ad", "app", "list"]:
            return []
        if arguments[:3] == ["ad", "app", "show"]:
            return api if arguments[-1] == api_id else client
        return [{"id": principal, "appId": api_id}] if api_id in arguments[-1] else []

    monkeypatch.setattr(control, "azure", azure)
    env = {
        "AZURE_ENV_NAME": "test",
        "MCP_API_CLIENT_ID": api_id,
        "MCP_PUBLIC_CLIENT_ID": client_id,
        "MCP_RESOURCE_URL": "https://newsloom.test/mcp",
    }
    if mismatch:
        with pytest.raises(PlatformFailure):
            mcp_identity.inventory(env)
    else:
        values = mcp_identity.inventory(env)
        assert values["MCP_EXISTING_API_OBJECT_ID"] == api_object
        assert values["MCP_EXISTING_CLIENT_OBJECT_ID"] == client_object
        assert values["MCP_EXISTING_SCOPE_ID"] == scope
        assert values["MCP_EXISTING_API_PRINCIPAL_ID"] == principal
        assert values["MCP_EXISTING_CLIENT_PRINCIPAL_ID"] == ""
        assert values["MCP_RESOURCE_IDENTIFIER_URI"] == "https://newsloom.test/mcp"
        assert values["MCP_EXISTING_RESOURCE_IDENTIFIER"] == str(resource_alias).lower()


@pytest.mark.parametrize(
    "resource",
    [
        "http://newsloom.test/mcp",
        "https://user:secret@newsloom.test/mcp",
        "https://newsloom.test/mcp/",
        "https://newsloom.test/mcp?extra=1",
        "https://newsloom.test/mcp#extra",
        "https://newsloom.test:443/mcp",
        "https://*/mcp",
    ],
)
def test_unapproved_resource_identifier_fails_before_directory_access(
    resource: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args: object, **kwargs: object) -> object:
        raise AssertionError("invalid_resource_reached_directory")

    monkeypatch.setattr(control, "azure", unexpected)
    with pytest.raises(PlatformFailure, match="invalid_mcp_resource_identifier"):
        mcp_identity.inventory({"AZURE_ENV_NAME": "test", "MCP_RESOURCE_URL": resource})
