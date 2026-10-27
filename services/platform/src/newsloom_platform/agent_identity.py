"""Read-only exact agent inventory; prepare only updates retained private azd inputs."""

import re

from newsloom_platform import control, mcp_identity
from newsloom_platform.config import PlatformFailure, json_object
from newsloom_platform.events import event

CALLBACK = "http://127.0.0.1:8400/callback"
ADOPTION_FIELDS = (
    "api_object_id",
    "api_client_id",
    "api_principal_id",
    "scope_id",
    "client_object_id",
    "client_client_id",
    "client_principal_id",
    "federation_id",
    "mcp_consent_id",
    "client_consent_id",
)


def rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise PlatformFailure("invalid_agent_identity_inventory")
    return [json_object(row) for row in value]


def permission(app: dict[str, object], resource: str, scope: str) -> None:
    access = rows(app.get("requiredResourceAccess"))
    if len(access) != 1 or access[0].get("resourceAppId") != resource:
        raise PlatformFailure("agent_delegated_permission_mismatch")
    if rows(access[0].get("resourceAccess")) != [{"id": scope, "type": "Scope"}]:
        raise PlatformFailure("agent_delegated_permission_mismatch")


def opaque_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise PlatformFailure("invalid_consent_identifier")
    return value


def consent(client: str, resource: str, scope: str) -> str:
    grants = rows(
        control.azure(
            [
                "rest",
                "--url",
                "https://graph.microsoft.com/v1.0/oauth2PermissionGrants"
                f"?$filter=clientId%20eq%20'{client}'",
                "--query",
                "value",
            ],
            "agent_delegated_consent_inventory",
        )
    )
    if not grants:
        return ""
    if len(grants) != 1:
        raise PlatformFailure("agent_consent_mismatch")
    grant = grants[0]
    if (
        grant.get("clientId") != client
        or grant.get("resourceId") != resource
        or grant.get("consentType") != "AllPrincipals"
        or grant.get("principalId") is not None
        or grant.get("scope") != scope
    ):
        raise PlatformFailure("agent_consent_mismatch")
    return opaque_id(grant.get("id"))


def inventory(env: dict[str, str]) -> dict[str, str]:
    identify = mcp_identity.identifier
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", env.get("AZURE_ENV_NAME", "")):
        raise PlatformFailure("invalid_agent_environment_name")
    if not env.get("MCP_API_CLIENT_ID") or not env.get("MCP_PUBLIC_CLIENT_ID"):
        raise PlatformFailure("existing_mcp_registrations_required")
    mcp = mcp_identity.inventory(env)
    tenant = mcp["MCP_TENANT_ID"]
    if env.get("MCP_TENANT_ID") != tenant:
        raise PlatformFailure("agent_tenant_mismatch")
    if not mcp["MCP_EXISTING_API_PRINCIPAL_ID"]:
        raise PlatformFailure("existing_mcp_principal_required")
    values = {field: "" for field in ADOPTION_FIELDS}
    result = {
        "AGENT_TENANT_ID": tenant,
        "AGENT_MCP_API_PRINCIPAL_ID": mcp["MCP_EXISTING_API_PRINCIPAL_ID"],
        "AGENT_MCP_SCOPE_ID": mcp["MCP_EXISTING_SCOPE_ID"],
    }
    selected = {
        label: identify(env[key]) if env.get(key) else ""
        for label, key in (("api", "AGENT_API_CLIENT_ID"), ("client", "AGENT_PUBLIC_CLIENT_ID"))
    }
    if (
        any(
            value in (env["MCP_API_CLIENT_ID"], env["MCP_PUBLIC_CLIENT_ID"])
            for value in selected.values()
            if value
        )
        or (selected["api"] and selected["api"] == selected["client"])
        or (selected["client"] and not selected["api"])
    ):
        raise PlatformFailure("separate_agent_registrations_required")
    prefix = f"newsloom-{env['AZURE_ENV_NAME']}"
    names = {"api": f"{prefix}-agent-api", "client": f"{prefix}-agent-acceptance"}
    discovered = rows(
        control.azure(
            ["ad", "app", "list", "--filter", f"startswith(displayName, '{prefix}-agent')"],
            "agent_registration_discovery",
        )
    )
    for app in discovered:
        for label, name in names.items():
            if app.get("displayName") == name and app.get("appId") != selected[label]:
                raise PlatformFailure("existing_agent_registration_requires_explicit_identity")
    operator = (
        identify(
            control.azure(
                ["ad", "signed-in-user", "show", "--query", "id"],
                "agent_registration_owner_inventory",
            )
        )
        if any(selected.values())
        else ""
    )
    for label, client_id in selected.items():
        if not client_id:
            continue
        app = json_object(
            control.azure(["ad", "app", "show", "--id", client_id], "agent_exact_app_inventory")
        )
        if (
            identify(app.get("appId")) != client_id
            or app.get("displayName") != names[label]
            or app.get("signInAudience") != "AzureADMyOrg"
            or app.get("passwordCredentials") not in ([], None)
            or app.get("keyCredentials") not in ([], None)
            or app.get("appRoles") not in ([], None)
        ):
            raise PlatformFailure("agent_registration_contract_mismatch")
        owners = rows(
            control.azure(
                ["ad", "app", "owner", "list", "--id", client_id],
                "agent_exact_owner_inventory",
            )
        )
        if len(owners) != 1 or owners[0].get("id") != operator:
            raise PlatformFailure("agent_registration_ownership_mismatch")
        for surface in ("web", "spa"):
            configuration = app.get(surface)
            if configuration is not None and json_object(configuration).get("redirectUris") not in (
                [],
                None,
            ):
                raise PlatformFailure("agent_registration_contract_mismatch")
        values[f"{label}_object_id"] = identify(app.get("id"))
        values[f"{label}_client_id"] = client_id
        if label == "api":
            api = json_object(app.get("api"))
            scopes = rows(api.get("oauth2PermissionScopes"))
            if (
                len(scopes) != 1
                or scopes[0].get("value") != "news.agent"
                or scopes[0].get("isEnabled") is not True
                or scopes[0].get("type") != "User"
                or api.get("requestedAccessTokenVersion") != 2
                or app.get("identifierUris") != [f"api://{client_id}"]
                or app.get("isFallbackPublicClient") not in (False, None)
                or json_object(app.get("publicClient")).get("redirectUris") not in ([], None)
            ):
                raise PlatformFailure("agent_scope_contract_mismatch")
            values["scope_id"] = identify(scopes[0].get("id"))
            permission(app, env["MCP_API_CLIENT_ID"], mcp["MCP_EXISTING_SCOPE_ID"])
        else:
            if (
                json_object(app.get("publicClient")).get("redirectUris") != [CALLBACK]
                or app.get("isFallbackPublicClient") is not True
                or app.get("identifierUris") not in ([], None)
                or json_object(app.get("api")).get("oauth2PermissionScopes") not in ([], None)
            ):
                raise PlatformFailure("agent_pkce_contract_mismatch")
            permission(app, selected["api"], values["scope_id"])
        principals = rows(
            control.azure(
                ["ad", "sp", "list", "--filter", f"appId eq '{client_id}'"],
                "agent_exact_principal_inventory",
            )
        )
        if len(principals) > 1:
            raise PlatformFailure("agent_principal_contract_mismatch")
        if principals:
            principal = principals[0]
            if (
                principal.get("appId") != client_id
                or principal.get("appOwnerOrganizationId") != tenant
                or principal.get("accountEnabled") is not True
            ):
                raise PlatformFailure("agent_principal_contract_mismatch")
            values[f"{label}_principal_id"] = identify(principal.get("id"))
    if selected["api"]:
        federations = rows(
            control.azure(
                ["ad", "app", "federated-credential", "list", "--id", selected["api"]],
                "agent_federation_inventory",
            )
        )
        if federations:
            identities = rows(
                control.azure(
                    ["identity", "list", "--resource-group", env["AZURE_RESOURCE_GROUP"]],
                    "agent_managed_identity_inventory",
                )
            )
            exact_id = (
                f"/subscriptions/{identify(env['AZURE_SUBSCRIPTION_ID'])}"
                f"/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
                f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-{prefix}-agent"
            )
            owned = [
                row
                for row in identities
                if isinstance(resource_id := row.get("id"), str)
                and resource_id.casefold() == exact_id.casefold()
            ]
            if (
                len(owned) != 1
                or owned[0].get("tenantId") != tenant
                or len(federations) != 1
                or federations[0].get("issuer")
                != f"https://login.microsoftonline.com/{tenant}/v2.0"
                or federations[0].get("subject") != identify(owned[0].get("principalId"))
                or federations[0].get("audiences") != ["api://AzureADTokenExchange"]
                or federations[0].get("name") != "agent-managed-identity"
            ):
                raise PlatformFailure("agent_federation_contract_mismatch")
            values["federation_id"] = identify(federations[0].get("id"))
    if values["api_principal_id"]:
        values["mcp_consent_id"] = consent(
            values["api_principal_id"], result["AGENT_MCP_API_PRINCIPAL_ID"], "news.read"
        )
    if values["client_principal_id"]:
        if not values["api_principal_id"]:
            raise PlatformFailure("agent_principal_contract_mismatch")
        values["client_consent_id"] = consent(
            values["client_principal_id"], values["api_principal_id"], "news.agent"
        )
    return {
        **result,
        **{f"AGENT_EXISTING_{key.upper()}": value for key, value in values.items()},
    }


def prepare(env: dict[str, str], correlation: str) -> None:
    enabled = env.get("AGENT_ENABLED", "false")
    consent_enabled = env.get("AGENT_CONSENT_ENABLED", "false")
    if enabled not in ("true", "false") or consent_enabled not in ("true", "false"):
        raise PlatformFailure("invalid_agent_enabled_setting")
    values = {
        "AGENT_ENABLED": enabled,
        "AGENT_CONSENT_ENABLED": consent_enabled,
        **{f"AGENT_EXISTING_{field.upper()}": "" for field in ADOPTION_FIELDS},
        "AGENT_TENANT_ID": env.get("MCP_TENANT_ID", ""),
        "AGENT_MCP_API_PRINCIPAL_ID": "",
        "AGENT_MCP_SCOPE_ID": "",
    }
    if enabled == "true":
        values.update(inventory(env))
        if consent_enabled != "true" and (
            values["AGENT_EXISTING_MCP_CONSENT_ID"] or values["AGENT_EXISTING_CLIENT_CONSENT_ID"]
        ):
            raise PlatformFailure("existing_agent_consent_requires_retained_opt_in")
    for key, value in values.items():
        control.set_environment(key, value)
    event(
        "agent_identity_inventory",
        "success" if enabled == "true" else "disabled",
        correlation,
        counts={
            "api_adopted": int(bool(values["AGENT_EXISTING_API_OBJECT_ID"])),
            "client_adopted": int(bool(values["AGENT_EXISTING_CLIENT_OBJECT_ID"])),
            "consent_enabled": int(consent_enabled == "true"),
        },
    )
