"""Owning UI inventory, configuration and immutable deployment verification."""

import base64
import json
import re
from pathlib import Path

from newsloom_core.origins import normalize_origins

from newsloom_platform import agent_identity, control, mcp_identity
from newsloom_platform.config import PlatformFailure, json_object, text_field
from newsloom_platform.events import event

ADOPTION_FIELDS = ("client_object_id", "client_client_id", "client_principal_id", "consent_id")


def enabled(env: dict[str, str]) -> bool:
    value = env.get("UI_ENABLED", "false")
    if value not in ("true", "false"):
        raise PlatformFailure("invalid_ui_enabled_setting")
    return value == "true"


def news_enabled(env: dict[str, str]) -> bool:
    value = env.get("UI_NEWS_ENABLED", "false")
    if value not in ("true", "false"):
        raise PlatformFailure("invalid_ui_news_setting")
    if value == "true" and not enabled(env):
        raise PlatformFailure("ui_news_requires_enabled_ui")
    return value == "true"


def mcp_permission_enabled(env: dict[str, str]) -> bool:
    value = env.get("UI_MCP_PERMISSION_ENABLED", "false")
    if value not in ("true", "false"):
        raise PlatformFailure("invalid_ui_mcp_permission_setting")
    if news_enabled(env) and value != "true":
        raise PlatformFailure("ui_news_requires_delegated_mcp_permission")
    return value == "true"


def permissions(app: dict[str, object], resources: dict[str, str]) -> None:
    rows = agent_identity.rows(app.get("requiredResourceAccess"))
    resource_ids = [text_field(row, "resourceAppId") for row in rows]
    if len(rows) != len(resources) or set(resource_ids) != set(resources):
        raise PlatformFailure("ui_delegated_permission_mismatch")
    for row, resource in zip(rows, resource_ids, strict=True):
        agent_identity.permission({"requiredResourceAccess": [row]}, resource, resources[resource])


def delegated_consents(client: str, resources: dict[str, str]) -> dict[str, str]:
    grants = agent_identity.rows(
        control.azure(
            [
                "rest",
                "--url",
                "https://graph.microsoft.com/v1.0/oauth2PermissionGrants"
                f"?$filter=clientId%20eq%20'{client}'",
                "--query",
                "value",
            ],
            "ui_delegated_consent_inventory",
        )
    )
    result: dict[str, str] = {}
    for grant in grants:
        resource = text_field(grant, "resourceId")
        if (
            resource not in resources
            or resource in result
            or grant.get("clientId") != client
            or grant.get("consentType") != "AllPrincipals"
            or grant.get("principalId") is not None
            or grant.get("scope") != resources[resource]
        ):
            raise PlatformFailure("ui_delegated_consent_mismatch")
        result[resource] = agent_identity.opaque_id(grant.get("id"))
    return result


def name(env: dict[str, str]) -> str:
    suffix = env["AZURE_ENV_NAME"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", suffix):
        raise PlatformFailure("invalid_ui_environment_name")
    return "web-" + f"newsloom-{suffix}"[:23].rstrip("-")


def environment_document(env: dict[str, str]) -> dict[str, object]:
    subscription = mcp_identity.identifier(env["AZURE_SUBSCRIPTION_ID"])
    expected = (
        f"/subscriptions/{subscription}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
        f"/providers/Microsoft.App/managedEnvironments/cae-newsloom-{env['AZURE_ENV_NAME']}"
    )
    if env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"] != expected:
        raise PlatformFailure("ui_environment_inventory_mismatch")
    document = json_object(
        control.rest(
            f"https://management.azure.com{expected}?api-version={control.API_VERSION}",
            "ui_environment_inventory",
        )
    )
    if text_field(document, "id").casefold() != expected.casefold():
        raise PlatformFailure("ui_environment_readback_mismatch")
    return document


def origin(env: dict[str, str]) -> str:
    properties = json_object(environment_document(env)["properties"])
    value = f"https://{name(env)}.{text_field(properties, 'defaultDomain')}"
    try:
        normalize_origins((value,))
    except ValueError:
        raise PlatformFailure("ui_origin_inventory_mismatch") from None
    return value


def identity_inventory(env: dict[str, str]) -> dict[str, str]:
    active = enabled(env)
    news = mcp_permission_enabled(env)
    consent = env.get("UI_CONSENT_ENABLED", "false")
    if consent not in ("true", "false"):
        raise PlatformFailure("invalid_ui_consent_setting")
    values = {
        "UI_ENABLED": str(active).lower(),
        "UI_CONSENT_ENABLED": consent,
        "UI_AGENT_API_PRINCIPAL_ID": "",
        "UI_AGENT_SCOPE_ID": "",
        "UI_NEWS_ENABLED": str(news_enabled(env)).lower(),
        "UI_MCP_PERMISSION_ENABLED": str(news).lower(),
        "UI_MCP_API_PRINCIPAL_ID": "",
        "UI_MCP_SCOPE_ID": "",
        "UI_EXISTING_MCP_CONSENT_ID": "",
        "UI_NEWS_PERMISSION_PRESENT": "false",
        **{f"UI_EXISTING_{field.upper()}": "" for field in ADOPTION_FIELDS},
    }
    if active:
        inventory = agent_identity.inventory(env)
        principal = inventory["AGENT_EXISTING_API_PRINCIPAL_ID"]
        scope = inventory["AGENT_EXISTING_SCOPE_ID"]
        if not principal or not scope:
            raise PlatformFailure("ui_requires_existing_agent_identity")
        values.update(UI_AGENT_API_PRINCIPAL_ID=principal, UI_AGENT_SCOPE_ID=scope)
        resource_scopes = {env["AGENT_API_CLIENT_ID"]: scope}
        mcp_principal = ""
        if news:
            mcp = mcp_identity.inventory(env)
            mcp_principal = mcp["MCP_EXISTING_API_PRINCIPAL_ID"]
            mcp_scope = mcp["MCP_EXISTING_SCOPE_ID"]
            if not mcp_principal or not mcp_scope:
                raise PlatformFailure("ui_requires_existing_mcp_identity")
            values.update(UI_MCP_API_PRINCIPAL_ID=mcp_principal, UI_MCP_SCOPE_ID=mcp_scope)
            resource_scopes[env["MCP_API_CLIENT_ID"]] = mcp_scope
        ui_origin = origin(env)
        selected = env.get("UI_CLIENT_ID", "")
        display_name = f"newsloom-{env['AZURE_ENV_NAME']}-ui"
        apps = agent_identity.rows(
            control.azure(
                ["ad", "app", "list", "--filter", f"displayName eq '{display_name}'"],
                "ui_registration_discovery",
            )
        )
        if len(apps) > 1 or (apps and not selected):
            raise PlatformFailure("existing_ui_registration_requires_explicit_identity")
        if selected:
            selected = mcp_identity.identifier(selected)
            app = json_object(
                control.azure(
                    ["ad", "app", "show", "--id", selected], "ui_exact_registration_inventory"
                )
            )
            if (
                app.get("appId") != selected
                or app.get("displayName") != display_name
                or app.get("signInAudience") != "AzureADMyOrg"
                or app.get("passwordCredentials") not in ([], None)
                or app.get("keyCredentials") not in ([], None)
                or app.get("appRoles") not in ([], None)
                or json_object(app.get("spa")).get("redirectUris")
                not in (
                    [f"{ui_origin}/auth/callback", f"{ui_origin}/"],
                    [f"{ui_origin}/", f"{ui_origin}/auth/callback"],
                )
                or json_object(app.get("web", {})).get("redirectUris") not in ([], None)
                or json_object(app.get("publicClient", {})).get("redirectUris") not in ([], None)
                or app.get("isFallbackPublicClient") not in (False, None)
            ):
                raise PlatformFailure("ui_registration_contract_mismatch")
            current_access = agent_identity.rows(app.get("requiredResourceAccess"))
            if news and len(current_access) == 1:
                permissions(app, {env["AGENT_API_CLIENT_ID"]: scope})
            else:
                permissions(app, resource_scopes)
                values["UI_NEWS_PERMISSION_PRESENT"] = str(news).lower()
            values["UI_EXISTING_CLIENT_OBJECT_ID"] = mcp_identity.identifier(app.get("id"))
            values["UI_EXISTING_CLIENT_CLIENT_ID"] = selected
            principals = agent_identity.rows(
                control.azure(
                    ["ad", "sp", "list", "--filter", f"appId eq '{selected}'"],
                    "ui_principal_inventory",
                )
            )
            if len(principals) > 1:
                raise PlatformFailure("ui_principal_inventory_mismatch")
            if principals:
                row = principals[0]
                if row.get("appId") != selected or row.get("accountEnabled") is not True:
                    raise PlatformFailure("ui_principal_contract_mismatch")
                client_principal = mcp_identity.identifier(row.get("id"))
                values["UI_EXISTING_CLIENT_PRINCIPAL_ID"] = client_principal
                consent_resources = {principal: "news.agent"}
                if news:
                    consent_resources[mcp_principal] = "news.read"
                consents = delegated_consents(client_principal, consent_resources)
                grant = consents.get(principal, "")
                if grant and consent != "true":
                    raise PlatformFailure("existing_ui_consent_requires_retained_opt_in")
                values["UI_EXISTING_CONSENT_ID"] = grant
                if news:
                    mcp_grant = consents.get(mcp_principal, "")
                    if mcp_grant and consent != "true":
                        raise PlatformFailure("existing_ui_consent_requires_retained_opt_in")
                    values["UI_EXISTING_MCP_CONSENT_ID"] = mcp_grant
        values["UI_ORIGIN"] = ui_origin
    return values


def prepare_identity(env: dict[str, str], correlation: str) -> None:
    values = identity_inventory(env)
    for key, value in values.items():
        control.set_environment(key, value)
    event(
        "ui_identity_inventory",
        "success" if enabled(env) else "disabled",
        correlation,
        counts={"adopted": int(bool(values["UI_EXISTING_CLIENT_OBJECT_ID"]))},
    )


def public_config(env: dict[str, str]) -> dict[str, str]:
    client = mcp_identity.identifier(env["UI_CLIENT_ID"])
    audience = mcp_identity.identifier(env["AGENT_API_CLIENT_ID"])
    if client == audience:
        raise PlatformFailure("separate_ui_client_required")
    interface = env["AGENT_RESOURCE_URL"]
    try:
        normalize_origins((interface.removesuffix("/a2a"),))
    except ValueError:
        raise PlatformFailure("invalid_ui_agent_interface") from None
    if not interface.endswith("/a2a"):
        raise PlatformFailure("invalid_ui_agent_interface")
    result = {
        "tenantId": mcp_identity.identifier(env["AGENT_TENANT_ID"]),
        "clientId": client,
        "agentUrl": interface,
        "agentScope": f"api://{audience}/news.agent",
    }
    if news_enabled(env):
        mcp_audience = mcp_identity.identifier(env["MCP_API_CLIENT_ID"])
        if mcp_audience in (client, audience):
            raise PlatformFailure("separate_ui_resource_audiences_required")
        mcp_url = env["MCP_RESOURCE_URL"]
        try:
            normalize_origins((mcp_url.removesuffix("/mcp"),))
        except ValueError:
            raise PlatformFailure("invalid_ui_mcp_interface") from None
        if not mcp_url.endswith("/mcp"):
            raise PlatformFailure("invalid_ui_mcp_interface")
        result.update(mcpUrl=mcp_url, mcpScope=f"api://{mcp_audience}/news.read")
    return result


def encoded_config(env: dict[str, str]) -> str:
    return base64.b64encode(json.dumps(public_config(env), sort_keys=True).encode()).decode()


def image(env: dict[str, str]) -> tuple[str, str]:
    reference, revision = env.get("WEB_IMAGE", ""), env.get("WEB_IMAGE_REVISION", "")
    if not re.fullmatch(
        re.escape(env["AZURE_CONTAINER_REGISTRY_ENDPOINT"]) + r"/newsloom-web@sha256:[a-f0-9]{64}",
        reference,
    ) or not re.fullmatch(r"[a-f0-9]{64}", revision):
        raise PlatformFailure("verified_ui_image_required")
    return reference, revision


def prepare(env: dict[str, str], correlation: str) -> None:
    if not enabled(env):
        for key, value in (
            ("UI_ENABLED", "false"),
            ("WEB_IMAGE", ""),
            ("WEB_IMAGE_REVISION", ""),
            ("UI_CONFIG_BASE64", ""),
        ):
            if key not in env:
                control.set_environment(key, value)
        event("ui_layer", "disabled", correlation)
        return
    _, revision = image(env)
    root = Path(control.run(["git", "rev-parse", "--show-toplevel"], "project_root"))
    if control.source_hash(root) != revision:
        raise PlatformFailure("ui_image_source_mismatch")
    if env.get("UI_ORIGIN") != origin(env):
        raise PlatformFailure("ui_origin_readback_mismatch")
    control.set_environment("UI_CONFIG_BASE64", encoded_config(env))
    event("ui_layer", "prepared", correlation, category=revision)


def build(env: dict[str, str], correlation: str) -> None:
    if not enabled(env):
        raise PlatformFailure("ui_layer_not_enabled")
    control.build(env, correlation, service="web")


def verify(env: dict[str, str], correlation: str) -> None:
    if not enabled(env):
        raise PlatformFailure("ui_layer_not_enabled")
    reference, revision = image(env)
    inventory = identity_inventory(env)
    if (
        inventory["UI_EXISTING_CLIENT_CLIENT_ID"] != env.get("UI_CLIENT_ID")
        or inventory["UI_AGENT_API_PRINCIPAL_ID"] != env.get("UI_AGENT_API_PRINCIPAL_ID")
        or inventory["UI_AGENT_SCOPE_ID"] != env.get("UI_AGENT_SCOPE_ID")
        or (env.get("UI_CONSENT_ENABLED") == "true" and not inventory["UI_EXISTING_CONSENT_ID"])
        or (mcp_permission_enabled(env) and not inventory["UI_EXISTING_MCP_CONSENT_ID"])
        or (mcp_permission_enabled(env) and inventory["UI_NEWS_PERMISSION_PRESENT"] != "true")
    ):
        raise PlatformFailure("ui_identity_readback_mismatch")
    ui_origin = origin(env)
    app_id = (
        f"/subscriptions/{mcp_identity.identifier(env['AZURE_SUBSCRIPTION_ID'])}"
        f"/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
        f"/providers/Microsoft.App/containerApps/{name(env)}"
    )
    if env.get("UI_APP_ID") != app_id or env.get("UI_APP_NAME") != name(env):
        raise PlatformFailure("ui_app_inventory_mismatch")
    app = json_object(
        control.rest(
            f"https://management.azure.com{app_id}?api-version={control.API_VERSION}",
            "ui_app_readback",
        )
    )
    properties = json_object(app.get("properties"))
    template = json_object(properties.get("template"))
    containers = agent_identity.rows(template.get("containers"))
    identity = json_object(json.loads(base64.b64decode(env["UI_IDENTITY_BASE64"], validate=True)))
    assignments = json_object(json_object(app.get("identity")).get("userAssignedIdentities"))
    expected_identity = (
        f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
        f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-newsloom-{env['AZURE_ENV_NAME']}-ui"
    )
    selected = [
        value
        for key, value in assignments.items()
        if key.casefold() == expected_identity.casefold()
    ]
    if len(containers) != 1 or len(assignments) != 1 or len(selected) != 1:
        raise PlatformFailure("ui_workload_inventory_mismatch")
    assigned = json_object(selected[0])
    rows = agent_identity.rows(containers[0].get("env"))
    actual = {text_field(row, "name"): text_field(row, "value") for row in rows}
    configuration = json_object(properties.get("configuration"))
    ingress = json_object(configuration.get("ingress"))
    registries = agent_identity.rows(configuration.get("registries"))
    if (
        text_field(app, "id").casefold() != app_id.casefold()
        or properties.get("environmentId") != env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"]
        or properties.get("provisioningState") != "Succeeded"
        or not properties.get("latestReadyRevisionName")
        or properties.get("latestReadyRevisionName") != properties.get("latestRevisionName")
        or properties.get("workloadProfileName") != "Consumption"
        or configuration.get("activeRevisionsMode") != "Single"
        or identity.get("id") != expected_identity
        or assigned.get("clientId") != identity.get("client_id")
        or assigned.get("principalId") != identity.get("principal_id")
        or json_object(app.get("identity")).get("type") != "UserAssigned"
        or len(registries) != 1
        or registries[0].get("server") != env["AZURE_CONTAINER_REGISTRY_ENDPOINT"]
        or str(registries[0].get("identity")).casefold() != expected_identity.casefold()
        or containers[0].get("image") != reference
        or containers[0].get("name") != "web"
        or json_object(containers[0].get("resources")).get("cpu") != 0.25
        or json_object(containers[0].get("resources")).get("memory") != "0.5Gi"
        or len(rows) != len(actual)
        or any(row.get("secretRef") for row in rows)
        or actual
        != {
            "UI_CONFIG_BASE64": encoded_config(env),
            "AGENT_ORIGIN": env["AGENT_RESOURCE_URL"].removesuffix("/a2a"),
            "UI_RUNTIME_REVISION": revision,
            **(
                {"MCP_ORIGIN": env["MCP_RESOURCE_URL"].removesuffix("/mcp")}
                if news_enabled(env)
                else {}
            ),
        }
        or json_object(template.get("scale")).get("minReplicas") not in (None, 0)
        or json_object(template.get("scale")).get("maxReplicas") != 1
        or ingress.get("external") is not True
        or ingress.get("allowInsecure") is not False
        or ingress.get("targetPort") != 8080
        or ui_origin != f"https://{ingress.get('fqdn')}"
        or env.get("UI_DEPLOYED_ORIGIN") != ui_origin
        or env.get("UI_ORIGIN") != ui_origin
    ):
        raise PlatformFailure("ui_deployment_readback_mismatch")
    grants = agent_identity.rows(
        control.azure(
            [
                "role",
                "assignment",
                "list",
                "--assignee-object-id",
                mcp_identity.identifier(identity.get("principal_id")),
                "--scope",
                env["AZURE_CONTAINER_REGISTRY_ID"],
                "--include-inherited",
            ],
            "ui_registry_role_readback",
        )
    )
    if (
        len(grants) != 1
        or grants[0].get("roleDefinitionName") != "AcrPull"
        or str(grants[0].get("scope")).casefold() != env["AZURE_CONTAINER_REGISTRY_ID"].casefold()
    ):
        raise PlatformFailure("ui_registry_role_mismatch")
    event("ui_deployment_readback", "success", correlation, category=revision, checks=1)
