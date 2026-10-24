"""Explicit registration inventory/adoption; no directory mutation or name-based selection."""

import re
from uuid import UUID

from newsloom_platform import control
from newsloom_platform.config import PlatformFailure, json_object

CALLBACKS = {"http://localhost", "http://127.0.0.1:33418", "https://vscode.dev/redirect"}


def identifier(value: object) -> str:
    if not isinstance(value, str):
        raise PlatformFailure("invalid_registration_identifier")
    try:
        return str(UUID(value))
    except ValueError:
        raise PlatformFailure("invalid_registration_identifier") from None


def inventory(env: dict[str, str]) -> dict[str, str]:
    resource_url = env.get("MCP_RESOURCE_URL", "")
    if resource_url and not re.fullmatch(r"https://[a-z0-9]+([.-][a-z0-9]+)*/mcp", resource_url):
        raise PlatformFailure("invalid_mcp_resource_identifier")
    tenant = identifier(
        control.azure(["account", "show", "--query", "tenantId"], "mcp_tenant_inventory")
    )
    selected = {key: env.get(key, "") for key in ("MCP_API_CLIENT_ID", "MCP_PUBLIC_CLIENT_ID")}
    existing = control.azure(
        ["ad", "app", "list", "--filter", "startswith(displayName, 'newsloom')"],
        "mcp_registration_discovery",
    )
    if not isinstance(existing, list):
        raise PlatformFailure("invalid_registration_inventory")
    expected_names = {
        f"newsloom-{env['AZURE_ENV_NAME']}-api",
        f"newsloom-{env['AZURE_ENV_NAME']}-vscode",
    }
    for row in existing:
        app = json_object(row)
        if app.get("displayName") in expected_names and app.get("appId") not in selected.values():
            raise PlatformFailure("existing_registration_requires_explicit_identity")
    result = {
        "MCP_TENANT_ID": tenant,
        "MCP_EXISTING_API_OBJECT_ID": "",
        "MCP_EXISTING_CLIENT_OBJECT_ID": "",
        "MCP_EXISTING_API_PRINCIPAL_ID": "",
        "MCP_EXISTING_CLIENT_PRINCIPAL_ID": "",
        "MCP_EXISTING_API_CLIENT_ID": "",
        "MCP_EXISTING_SCOPE_ID": "",
        "MCP_RESOURCE_IDENTIFIER_URI": resource_url,
        "MCP_EXISTING_RESOURCE_IDENTIFIER": "false",
    }
    for key, label in (("MCP_API_CLIENT_ID", "API"), ("MCP_PUBLIC_CLIENT_ID", "CLIENT")):
        if not selected[key]:
            continue
        client_id = identifier(selected[key])
        app = json_object(
            control.azure(
                ["ad", "app", "show", "--id", client_id], "mcp_exact_registration_inventory"
            )
        )
        if identifier(app.get("appId")) != client_id or app.get("signInAudience") != "AzureADMyOrg":
            raise PlatformFailure("registration_contract_mismatch")
        object_id = identifier(app.get("id"))
        if label == "API":
            api = json_object(app.get("api"))
            scopes = api.get("oauth2PermissionScopes")
            if not isinstance(scopes, list) or len(scopes) != 1:
                raise PlatformFailure("registration_scope_mismatch")
            scope = json_object(scopes[0])
            identifiers = app.get("identifierUris")
            expected_identifiers = {"api://" + client_id}
            if resource_url:
                expected_identifiers.add(resource_url)
            if (
                scope.get("value") != "news.read"
                or scope.get("isEnabled") is not True
                or scope.get("type") != "User"
                or api.get("requestedAccessTokenVersion") != 2
                or not isinstance(identifiers, list)
                or any(
                    not isinstance(uri, str) or uri not in expected_identifiers
                    for uri in identifiers
                )
                or "api://" + client_id not in identifiers
                or len(identifiers) != len(set(identifiers))
            ):
                raise PlatformFailure("registration_scope_mismatch")
            result["MCP_EXISTING_RESOURCE_IDENTIFIER"] = (
                "true" if resource_url and resource_url in identifiers else "false"
            )
            result["MCP_EXISTING_API_CLIENT_ID"] = client_id
            result["MCP_EXISTING_SCOPE_ID"] = identifier(scope.get("id"))
        else:
            public = json_object(app.get("publicClient"))
            redirects = public.get("redirectUris")
            if (
                not isinstance(redirects, list)
                or not redirects
                or app.get("isFallbackPublicClient") is not True
                or any(not isinstance(uri, str) or uri not in CALLBACKS for uri in redirects)
                or app.get("passwordCredentials") not in ([], None)
                or app.get("keyCredentials") not in ([], None)
            ):
                raise PlatformFailure("public_registration_contract_mismatch")
            access = app.get("requiredResourceAccess")
            if not isinstance(access, list) or len(access) != 1:
                raise PlatformFailure("public_registration_scope_mismatch")
            resource = json_object(access[0])
            permissions = resource.get("resourceAccess")
            if (
                resource.get("resourceAppId") != selected["MCP_API_CLIENT_ID"]
                or not isinstance(permissions, list)
                or len(permissions) != 1
                or json_object(permissions[0])
                != {"id": result["MCP_EXISTING_SCOPE_ID"], "type": "Scope"}
            ):
                raise PlatformFailure("public_registration_scope_mismatch")
        result[f"MCP_EXISTING_{label}_OBJECT_ID"] = object_id
        principals = control.azure(
            ["ad", "sp", "list", "--filter", f"appId eq '{client_id}'"],
            "mcp_exact_service_principal_inventory",
        )
        if not isinstance(principals, list) or len(principals) > 1:
            raise PlatformFailure("invalid_service_principal_inventory")
        if principals:
            principal = json_object(principals[0])
            if identifier(principal.get("appId")) != client_id:
                raise PlatformFailure("service_principal_mismatch")
            result[f"MCP_EXISTING_{label}_PRINCIPAL_ID"] = identifier(principal.get("id"))
    return result


def prepare(env: dict[str, str], correlation: str) -> None:
    from newsloom_platform.events import event

    values = inventory(env)
    for key, value in values.items():
        control.set_environment(key, value)
    event(
        "mcp_identity_inventory",
        "success",
        correlation,
        checks=2,
        counts={
            "api_adopted": int(bool(values["MCP_EXISTING_API_OBJECT_ID"])),
            "client_adopted": int(bool(values["MCP_EXISTING_CLIENT_OBJECT_ID"])),
            "approved_callback_count": len(CALLBACKS),
        },
    )
