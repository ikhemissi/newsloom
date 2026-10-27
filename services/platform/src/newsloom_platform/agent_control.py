"""Owning image preparation and independent ARM readback, never an implicit deployment."""

import base64
import json
import re
from pathlib import Path

from newsloom_platform import control, mcp_identity
from newsloom_platform.config import PlatformFailure, json_object, text_field
from newsloom_platform.events import event


def enabled(env: dict[str, str]) -> bool:
    value = env.get("AGENT_ENABLED", "false")
    if value not in ("true", "false"):
        raise PlatformFailure("invalid_agent_enabled_setting")
    return value == "true"


def image(env: dict[str, str]) -> tuple[str, str]:
    reference = env.get("AGENT_IMAGE", "")
    revision = env.get("AGENT_IMAGE_REVISION", "")
    registry = env["AZURE_CONTAINER_REGISTRY_ENDPOINT"]
    if not re.fullmatch(
        re.escape(registry) + r"/newsloom-agent@sha256:[a-f0-9]{64}", reference
    ) or not re.fullmatch(r"[a-f0-9]{64}", revision):
        raise PlatformFailure("verified_agent_image_required")
    return reference, revision


def prepare(env: dict[str, str], correlation: str) -> None:
    if not enabled(env):
        control.set_environment("AGENT_ENABLED", "false")
        for key in ("AGENT_IMAGE", "AGENT_IMAGE_REVISION", "AGENT_IDENTITY_BASE64"):
            if key not in env:
                control.set_environment(key, "")
        event("agent_layer", "disabled", correlation)
        return
    _, revision = image(env)
    root = Path(control.run(["git", "rev-parse", "--show-toplevel"], "project_root"))
    if control.source_hash(root) != revision:
        raise PlatformFailure("agent_image_source_mismatch")
    if not env.get("AGENT_IDENTITY_BASE64"):
        raise PlatformFailure("agent_identity_layer_required")
    event("agent_layer", "prepared", correlation, category=revision)


def build(env: dict[str, str], correlation: str) -> None:
    if not enabled(env):
        raise PlatformFailure("agent_layer_not_enabled")
    control.build(env, correlation, service="agent")


def verify(env: dict[str, str], correlation: str) -> None:
    if not enabled(env):
        raise PlatformFailure("agent_layer_not_enabled")
    reference, revision = image(env)
    identify = mcp_identity.identifier
    subscription = identify(env["AZURE_SUBSCRIPTION_ID"])
    name = "agent-" + f"newsloom-{env['AZURE_ENV_NAME']}"[:23].rstrip("-")
    app_id = (
        f"/subscriptions/{subscription}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
        f"/providers/Microsoft.App/containerApps/{name}"
    )
    if env.get("AGENT_APP_ID") != app_id or env.get("AGENT_APP_NAME") != name:
        raise PlatformFailure("agent_app_inventory_mismatch")
    identity = json_object(
        json.loads(base64.b64decode(env["AGENT_IDENTITY_BASE64"], validate=True))
    )
    identity_id = text_field(identity, "id")
    if identity_id != (
        f"/subscriptions/{subscription}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
        f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-newsloom-{env['AZURE_ENV_NAME']}-agent"
    ):
        raise PlatformFailure("agent_identity_inventory_mismatch")
    application = json_object(
        control.rest(
            f"https://management.azure.com{app_id}?api-version={control.API_VERSION}",
            "agent_app_readback",
        )
    )
    properties = json_object(application.get("properties"))
    assignments = json_object(
        json_object(application.get("identity")).get("userAssignedIdentities")
    )
    owned = [
        value for key, value in assignments.items() if key.casefold() == identity_id.casefold()
    ]
    if len(assignments) != 1 or len(owned) != 1:
        raise PlatformFailure("agent_identity_readback_mismatch")
    assigned = json_object(owned[0])
    if (
        text_field(application, "id").casefold() != app_id.casefold()
        or json_object(application.get("identity")).get("type") != "UserAssigned"
        or assigned.get("clientId") != identity.get("client_id")
        or assigned.get("principalId") != identity.get("principal_id")
    ):
        raise PlatformFailure("agent_identity_readback_mismatch")
    configuration = json_object(properties.get("configuration"))
    ingress = json_object(configuration.get("ingress"))
    template = json_object(properties.get("template"))
    containers = template.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise PlatformFailure("agent_container_inventory_mismatch")
    container = json_object(containers[0])
    raw_environment = container.get("env")
    if not isinstance(raw_environment, list):
        raise PlatformFailure("agent_environment_inventory_mismatch")
    actual: dict[str, str] = {}
    for value in raw_environment:
        row = json_object(value)
        key, content = row.get("name"), row.get("value")
        if not isinstance(key, str) or not isinstance(content, str) or row.get("secretRef"):
            raise PlatformFailure("agent_environment_inventory_mismatch")
        actual[key] = content
    expected = {
        "AZURE_CLIENT_ID": identify(identity.get("client_id")),
        "AGENT_TENANT_ID": identify(env["AGENT_TENANT_ID"]),
        "AGENT_API_CLIENT_ID": identify(env["AGENT_API_CLIENT_ID"]),
        "AGENT_RESOURCE_URL": env["AGENT_RESOURCE_URL"],
        "AGENT_ALLOWED_ORIGINS": "",
        "AGENT_RUNTIME_REVISION": revision,
        "MCP_API_CLIENT_ID": identify(env["MCP_API_CLIENT_ID"]),
        "MCP_RESOURCE_URL": env["MCP_RESOURCE_URL"],
        "MODEL_ENDPOINT": env["MODEL_ENDPOINT"],
        "AGENT_CHAT_DEPLOYMENT": env["ENRICHMENT_DEPLOYMENT"],
        "APPLICATIONINSIGHTS_CONNECTION_STRING": env["APPLICATIONINSIGHTS_CONNECTION_STRING"],
    }
    if (
        container.get("image") != reference
        or container.get("name") != "agent"
        or actual != expected
        or len(actual) != len(raw_environment)
        or json_object(template.get("scale")).get("minReplicas") != 1
        or json_object(template.get("scale")).get("maxReplicas") != 1
        or ingress.get("external") is not True
        or ingress.get("allowInsecure") is not False
        or ingress.get("targetPort") != 8000
        or env["AGENT_RESOURCE_URL"] != f"https://{ingress.get('fqdn')}/a2a"
        or properties.get("provisioningState") != "Succeeded"
        or not properties.get("latestRevisionName")
        or properties.get("latestRevisionName") != properties.get("latestReadyRevisionName")
        or text_field(properties, "environmentId").casefold()
        != env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"].casefold()
        or properties.get("workloadProfileName") != "Consumption"
        or configuration.get("activeRevisionsMode") != "Single"
        or json_object(container.get("resources")).get("cpu") != 0.25
        or json_object(container.get("resources")).get("memory") != "0.5Gi"
    ):
        raise PlatformFailure("agent_deployment_readback_mismatch")
    registries = configuration.get("registries")
    if (
        not isinstance(registries, list)
        or len(registries) != 1
        or json_object(registries[0]).get("server") != env["AZURE_CONTAINER_REGISTRY_ENDPOINT"]
        or text_field(json_object(registries[0]), "identity").casefold() != identity_id.casefold()
        or json_object(registries[0]).get("username")
        or json_object(registries[0]).get("passwordSecretRef")
    ):
        raise PlatformFailure("agent_registry_readback_mismatch")
    probes = container.get("probes")
    if (
        not isinstance(probes, list)
        or len(probes) != 3
        or {json_object(probe).get("type") for probe in probes}
        != {"Startup", "Liveness", "Readiness"}
        or any(
            json_object(json_object(probe).get("httpGet")).get("path") != "/health/live"
            or json_object(json_object(probe).get("httpGet")).get("port") != 8000
            for probe in probes
        )
    ):
        raise PlatformFailure("agent_probe_readback_mismatch")
    event(
        "agent_deployment_readback",
        "success",
        correlation,
        category=revision,
        counts={"configuration_match": 1, "image_match": 1},
    )
