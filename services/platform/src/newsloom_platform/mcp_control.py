"""Owning browser-origin preparation and independent MCP configuration readback."""

import base64
import json
import re
from pathlib import Path

from newsloom_core.origins import normalize_origins

from newsloom_platform import control, mcp_identity
from newsloom_platform.config import PlatformFailure, json_object, text_field
from newsloom_platform.events import event


def origins(env: dict[str, str]) -> tuple[str, ...]:
    raw = env.get("MCP_ALLOWED_ORIGINS", "")
    try:
        return normalize_origins(raw.split(",") if raw else ())
    except ValueError:
        raise PlatformFailure("invalid_mcp_allowed_origins") from None


def image(env: dict[str, str]) -> tuple[str, str]:
    reference, revision = env["MCP_IMAGE"], env.get("MCP_IMAGE_REVISION", "")
    if not re.fullmatch(
        re.escape(env["AZURE_CONTAINER_REGISTRY_ENDPOINT"]) + r"/newsloom-mcp@sha256:[a-f0-9]{64}",
        reference,
    ) or not re.fullmatch(r"[a-f0-9]{64}", revision):
        raise PlatformFailure("verified_mcp_image_required")
    return reference, revision


def prepare(env: dict[str, str], correlation: str) -> None:
    allowed = origins(env)
    flag = api_enabled(env)
    _, revision = image(env)
    root = Path(control.run(["git", "rev-parse", "--show-toplevel"], "project_root"))
    if control.source_hash(root) != revision:
        raise PlatformFailure("mcp_image_source_mismatch")
    control.set_environment(
        "MCP_ALLOWED_ORIGINS_BASE64",
        base64.b64encode(json.dumps(allowed).encode()).decode(),
    )
    control.set_environment("NEWS_API_ENABLED", flag)
    event("mcp_layer", "prepared", correlation, category=revision)


def verify(env: dict[str, str], correlation: str) -> None:
    reference, revision = image(env)
    name = "mcp-" + f"newsloom-{env['AZURE_ENV_NAME']}"[:25].rstrip("-")
    subscription = mcp_identity.identifier(env["AZURE_SUBSCRIPTION_ID"])
    group = f"/subscriptions/{subscription}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
    app_id = f"{group}/providers/Microsoft.App/containerApps/{name}"
    if env["MCP_APP_ID"] != app_id or env["MCP_APP_NAME"] != name:
        raise PlatformFailure("mcp_app_inventory_mismatch")
    identity = json_object(
        json.loads(
            base64.b64decode(
                env["WORKLOAD_IDENTITIES_BASE64"],
                validate=True,
            )
        )["mcp"]
    )
    expected_identity = (
        f"{group}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/"
        f"id-newsloom-{env['AZURE_ENV_NAME']}-mcp"
    )
    if identity.get("id") != expected_identity:
        raise PlatformFailure("mcp_identity_inventory_mismatch")
    app = json_object(
        control.rest(
            f"https://management.azure.com{app_id}?api-version={control.API_VERSION}",
            "mcp_app_readback",
        )
    )
    properties = json_object(app.get("properties"))
    configuration = json_object(properties.get("configuration"))
    template = json_object(properties.get("template"))
    containers = template.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise PlatformFailure("mcp_container_inventory_mismatch")
    container = json_object(containers[0])
    rows = container.get("env")
    if not isinstance(rows, list):
        raise PlatformFailure("mcp_environment_inventory_mismatch")
    actual = {
        text_field(json_object(row), "name"): text_field(json_object(row), "value") for row in rows
    }
    expected = {
        "NEWS_API_ENABLED": api_enabled(env),
        "AZURE_CLIENT_ID": identity["client_id"],
        "MCP_TENANT_ID": env["MCP_TENANT_ID"],
        "MCP_API_CLIENT_ID": env["MCP_API_CLIENT_ID"],
        "MCP_RESOURCE_URL": env["MCP_RESOURCE_URL"],
        "MCP_ALLOWED_ORIGINS": ",".join(origins(env)),
        "POSTGRES_HOST": env["POSTGRES_HOST"],
        "POSTGRES_DATABASE": env["POSTGRES_DATABASE"],
        "MODEL_ENDPOINT": env["MODEL_ENDPOINT"],
        "EMBEDDINGS_DEPLOYMENT": env["EMBEDDINGS_DEPLOYMENT"],
        "EMBEDDINGS_MODEL": env["EMBEDDINGS_MODEL"],
        "EMBEDDINGS_VERSION": env["EMBEDDINGS_VERSION"],
        "APPLICATIONINSIGHTS_CONNECTION_STRING": env["APPLICATIONINSIGHTS_CONNECTION_STRING"],
    }
    assignments = json_object(json_object(app.get("identity")).get("userAssignedIdentities"))
    selected = [
        json_object(value)
        for key, value in assignments.items()
        if key.casefold() == str(identity["id"]).casefold()
    ]
    registries = configuration.get("registries")
    ingress = json_object(configuration.get("ingress"))
    scale = json_object(template.get("scale"))
    environment_id = (
        f"{group}/providers/Microsoft.App/managedEnvironments/cae-newsloom-{env['AZURE_ENV_NAME']}"
    )
    if (
        text_field(app, "id").casefold() != app_id.casefold()
        or env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"] != environment_id
        or properties.get("environmentId") != environment_id
        or properties.get("provisioningState") != "Succeeded"
        or not properties.get("latestReadyRevisionName")
        or properties.get("latestReadyRevisionName") != properties.get("latestRevisionName")
        or configuration.get("activeRevisionsMode") != "Single"
        or properties.get("workloadProfileName") != "Consumption"
        or container.get("image") != reference
        or container.get("name") != "mcp"
        or json_object(container.get("resources")).get("cpu") != 0.25
        or json_object(container.get("resources")).get("memory") != "0.5Gi"
        or actual != expected
        or len(rows) != len(actual)
        or any(json_object(row).get("secretRef") for row in rows)
        or len(assignments) != 1
        or json_object(app.get("identity")).get("type") != "UserAssigned"
        or len(selected) != 1
        or selected[0].get("clientId") != identity["client_id"]
        or selected[0].get("principalId") != identity["principal_id"]
        or not isinstance(registries, list)
        or len(registries) != 1
        or json_object(registries[0]).get("server") != env["AZURE_CONTAINER_REGISTRY_ENDPOINT"]
        or json_object(registries[0]).get("identity") != identity["id"]
        or ingress.get("external") is not True
        or ingress.get("allowInsecure") is not False
        or ingress.get("targetPort") != 8000
        or env["MCP_RESOURCE_URL"] != f"https://{ingress.get('fqdn')}/mcp"
        or scale.get("minReplicas") != 1
        or scale.get("maxReplicas") != 1
    ):
        raise PlatformFailure("mcp_deployment_readback_mismatch")
    event("mcp_deployment_readback", "success", correlation, category=revision, checks=1)


def api_enabled(env: dict[str, str]) -> str:
    value = env.get("NEWS_API_ENABLED", "false")
    if value not in ("true", "false"):
        raise PlatformFailure("invalid_news_api_enabled")
    return value
