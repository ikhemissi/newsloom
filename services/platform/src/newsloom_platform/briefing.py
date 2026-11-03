"""Additive briefing preparation and content-free immutable-job readback."""

import base64
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from newsloom_platform import control as platform
from newsloom_platform.config import Identity, PlatformFailure, json_object, text_field
from newsloom_platform.events import event

MODEL_API_VERSION = "2025-06-01"
ROLE_API_VERSION = "2022-04-01"
CHAT_ACTION = "Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action"
ACR_PULL_ROLE = "-".join(("7f951dda", "4ed3", "4680", "a7ca", "43fe172d538d"))
METRICS_ROLE = "-".join(("3913510d", "42f4", "4e42", "8a64", "420c390055eb"))


def flag(env: dict[str, str], key: str) -> bool:
    value = env.get(key, "false")
    if value not in ("true", "false"):
        raise PlatformFailure("invalid_briefing_flag")
    return value == "true"


def identity(env: dict[str, str]) -> Identity:
    result = Identity.model_validate_json(
        base64.b64decode(env["BRIEFING_IDENTITY_BASE64"], validate=True)
    )
    expected = (
        f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
        f"/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
        "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/"
        f"id-newsloom-{env['AZURE_ENV_NAME']}-briefing"
    )
    if result.id != expected:
        raise PlatformFailure("briefing_identity_inventory_mismatch")
    foundation = json_object(
        json.loads(base64.b64decode(env["WORKLOAD_IDENTITIES_BASE64"], validate=True))
    )
    if set(foundation) != {"ingestion", "enrichment", "mcp", "migrations"}:
        raise PlatformFailure("briefing_foundation_manifest_mismatch")
    for raw in foundation.values():
        existing = Identity.model_validate(raw)
        if result.principal_id == existing.principal_id or result.client_id == existing.client_id:
            raise PlatformFailure("briefing_identity_not_isolated")
    return result


def defaults(env: dict[str, str]) -> dict[str, str]:
    result = dict(env)
    values = {
        "BRIEFING_ENABLED": "false",
        "BRIEFING_SCHEDULE_ENABLED": "false",
        "BRIEFING_IDENTITY_BASE64": "",
        "BRIEFING_DEPLOYMENT": "briefing",
        "BRIEFING_IMAGE": "",
        "BRIEFING_IMAGE_REVISION": "",
        "BRIEFING_INPUT_PRICE_PER_MILLION": "",
        "BRIEFING_OUTPUT_PRICE_PER_MILLION": "",
        "BRIEFING_PRICE_BASIS": "",
        "NEWS_BRIEFING_ENABLED": "false",
    }
    for key, value in values.items():
        if key not in result:
            platform.set_environment(key, value)
            result[key] = value
    if flag(result, "BRIEFING_SCHEDULE_ENABLED") and not flag(result, "BRIEFING_ENABLED"):
        raise PlatformFailure("briefing_schedule_requires_enabled_workload")
    return result


def deployment(env: dict[str, str], name: str) -> dict[str, object]:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", name):
        raise PlatformFailure("invalid_briefing_deployment")
    document = json_object(
        platform.rest(
            f"https://management.azure.com{env['MODEL_ACCOUNT_ID']}"
            f"/deployments/{name}?api-version={MODEL_API_VERSION}",
            "briefing_model_inventory",
        )
    )
    return document


def verify_model(env: dict[str, str], *, own: bool) -> None:
    name = env["BRIEFING_DEPLOYMENT"] if own else env["ENRICHMENT_DEPLOYMENT"]
    if env["BRIEFING_DEPLOYMENT"] == env["ENRICHMENT_DEPLOYMENT"]:
        raise PlatformFailure("briefing_requires_separate_model_deployment")
    document = deployment(env, name)
    properties = json_object(document.get("properties"))
    model = json_object(properties.get("model"))
    sku = json_object(document.get("sku"))
    if (
        model.get("format") != "OpenAI"
        or model.get("name") != env["ENRICHMENT_MODEL"]
        or model.get("version") != env["ENRICHMENT_VERSION"]
        or sku.get("name") != env["ENRICHMENT_SKU"]
        or properties.get("versionUpgradeOption") != "NoAutoUpgrade"
        or (own and sku.get("capacity") != 10)
    ):
        raise PlatformFailure("briefing_model_contract_mismatch")


def preservation(env: dict[str, str]) -> str:
    document = json_object(
        platform.rest(
            f"https://management.azure.com{env['MODEL_ACCOUNT_ID']}"
            f"/deployments?api-version={MODEL_API_VERSION}",
            "briefing_preservation_inventory",
        )
    )
    rows = document.get("value")
    if not isinstance(rows, list):
        raise PlatformFailure("invalid_briefing_preservation_inventory")
    retained = []
    for raw in rows:
        row = json_object(raw)
        if row.get("name") != env["BRIEFING_DEPLOYMENT"]:
            properties = json_object(row.get("properties"))
            retained.append(
                {
                    "id": text_field(row, "id"),
                    "sku": row.get("sku"),
                    "model": properties.get("model"),
                    "versionUpgradeOption": properties.get("versionUpgradeOption"),
                }
            )
    retained.sort(key=lambda row: str(row["id"]))
    data = {"models": retained, "foundation": env["WORKLOAD_IDENTITIES_BASE64"]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def prepare_identity(env: dict[str, str], correlation: str) -> None:
    env = defaults(env)
    if not flag(env, "BRIEFING_ENABLED"):
        event("briefing_identity", "disabled", correlation)
        return
    verify_model(env, own=False)
    fingerprint = preservation(env)
    previous = env.get("BRIEFING_PRESERVATION_SHA256")
    if previous and fingerprint != previous:
        raise PlatformFailure("briefing_retained_resources_changed")
    platform.set_environment("BRIEFING_PRESERVATION_SHA256", fingerprint)
    event("briefing_identity", "prepared", correlation, category=fingerprint)


def prices(env: dict[str, str]) -> None:
    try:
        values = [
            Decimal(env[key])
            for key in ("BRIEFING_INPUT_PRICE_PER_MILLION", "BRIEFING_OUTPUT_PRICE_PER_MILLION")
        ]
        if any(not value.is_finite() or value < 0 for value in values):
            raise ValueError
    except InvalidOperation, ValueError:
        raise PlatformFailure("briefing_verified_prices_required") from None
    if not re.search(r"\d{4}-\d{2}-\d{2}", env["BRIEFING_PRICE_BASIS"]):
        raise PlatformFailure("briefing_dated_price_basis_required")


def image(env: dict[str, str]) -> tuple[str, str]:
    reference, revision = env["BRIEFING_IMAGE"], env["BRIEFING_IMAGE_REVISION"]
    if not re.fullmatch(
        re.escape(env["AZURE_CONTAINER_REGISTRY_ENDPOINT"])
        + r"/newsloom-briefing@sha256:[a-f0-9]{64}",
        reference,
    ) or not re.fullmatch(r"[a-f0-9]{64}", revision):
        raise PlatformFailure("briefing_immutable_image_required")
    return reference, revision


def prepare(env: dict[str, str], correlation: str) -> None:
    env = defaults(env)
    if not flag(env, "BRIEFING_ENABLED"):
        event("briefing_layer", "disabled", correlation)
        return
    verify_grants(env)
    verify_model(env, own=True)
    prices(env)
    if preservation(env) != env["BRIEFING_PRESERVATION_SHA256"]:
        raise PlatformFailure("briefing_retained_resources_changed")
    platform.build(env, correlation, service="briefing")
    event("briefing_layer", "prepared", correlation)


def verify_grants(env: dict[str, str]) -> None:
    selected = identity(env)
    managed = json_object(
        platform.rest(
            f"https://management.azure.com{selected.id}?api-version=2023-01-31",
            "briefing_identity_readback",
        )
    )
    properties = json_object(managed.get("properties"))
    if (
        text_field(managed, "id").casefold() != selected.id.casefold()
        or managed.get("location") != env["AZURE_LOCATION"]
        or properties.get("clientId") != str(selected.client_id)
        or properties.get("principalId") != str(selected.principal_id)
    ):
        raise PlatformFailure("briefing_identity_readback_mismatch")
    subscription = f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
    document = json_object(
        platform.rest(
            f"https://management.azure.com{subscription}"
            f"/providers/Microsoft.Authorization/roleAssignments?api-version={ROLE_API_VERSION}"
            f"&$filter=principalId%20eq%20%27{selected.principal_id}%27",
            "briefing_grant_inventory",
        )
    )
    rows = document.get("value")
    if not isinstance(rows, list) or len(rows) != 3 or document.get("nextLink"):
        raise PlatformFailure("briefing_grant_inventory_mismatch")
    expected = {
        env["AZURE_CONTAINER_REGISTRY_ID"].casefold(): ACR_PULL_ROLE,
        env["APPLICATIONINSIGHTS_ID"].casefold(): METRICS_ROLE,
        env["MODEL_ACCOUNT_ID"].casefold(): None,
    }
    seen = set()
    for row in rows:
        properties = json_object(json_object(row).get("properties"))
        scope = text_field(properties, "scope").casefold()
        role = text_field(properties, "roleDefinitionId")
        if (
            scope not in expected
            or scope in seen
            or properties.get("principalId") != str(selected.principal_id)
            or properties.get("principalType") != "ServicePrincipal"
            or properties.get("condition") not in (None, "")
        ):
            raise PlatformFailure("briefing_grant_inventory_mismatch")
        seen.add(scope)
        if expected[scope] is not None:
            if role.rsplit("/", 1)[-1].casefold() != expected[scope]:
                raise PlatformFailure("briefing_grant_inventory_mismatch")
        else:
            definition = json_object(
                platform.rest(
                    f"https://management.azure.com{role}?api-version={ROLE_API_VERSION}",
                    "briefing_chat_role_readback",
                )
            )
            definition_properties = json_object(definition.get("properties"))
            permissions = definition_properties.get("permissions")
            group = f"{subscription}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
            if (
                definition_properties.get("type") != "CustomRole"
                or definition_properties.get("roleName")
                != f"newsloom-{env['AZURE_ENV_NAME']}-briefing-chat"
                or definition_properties.get("assignableScopes") != [group]
                or not isinstance(permissions, list)
                or len(permissions) != 1
            ):
                raise PlatformFailure("briefing_chat_role_mismatch")
            permission = json_object(permissions[0])
            if permission.get("dataActions") != [CHAT_ACTION] or any(
                permission.get(key) not in ([], None)
                for key in ("actions", "notActions", "notDataActions")
            ):
                raise PlatformFailure("briefing_chat_role_mismatch")


def expected_environment(env: dict[str, str]) -> dict[str, str]:
    return {
        "AZURE_CLIENT_ID": str(identity(env).client_id),
        "POSTGRES_HOST": env["POSTGRES_HOST"],
        "POSTGRES_DATABASE": env["POSTGRES_DATABASE"],
        "MODEL_ENDPOINT": env["MODEL_ENDPOINT"],
        "BRIEFING_DEPLOYMENT": env["BRIEFING_DEPLOYMENT"],
        "BRIEFING_MODEL": env["ENRICHMENT_MODEL"],
        "BRIEFING_MODEL_VERSION": env["ENRICHMENT_VERSION"],
        "BRIEFING_INPUT_PRICE_PER_MILLION": env["BRIEFING_INPUT_PRICE_PER_MILLION"],
        "BRIEFING_OUTPUT_PRICE_PER_MILLION": env["BRIEFING_OUTPUT_PRICE_PER_MILLION"],
        "BRIEFING_PRICE_BASIS": env["BRIEFING_PRICE_BASIS"],
        "APPLICATIONINSIGHTS_CONNECTION_STRING": env["APPLICATIONINSIGHTS_CONNECTION_STRING"],
    }


def verify(env: dict[str, str], correlation: str) -> None:
    if not flag(env, "BRIEFING_ENABLED"):
        raise PlatformFailure("briefing_workload_disabled")
    selected = identity(env)
    reference, revision = image(env)
    root = Path(platform.run(["git", "rev-parse", "--show-toplevel"], "project_root"))
    if platform.source_hash(root) != revision:
        raise PlatformFailure("briefing_image_source_mismatch")
    name = "brief-" + f"newsloom-{env['AZURE_ENV_NAME']}"[:25].rstrip("-")
    expected_id = (
        f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}"
        f"/resourceGroups/{env['AZURE_RESOURCE_GROUP']}/providers/Microsoft.App/jobs/{name}"
    )
    if env["BRIEFING_JOB_ID"] != expected_id:
        raise PlatformFailure("briefing_job_inventory_mismatch")
    job = json_object(
        platform.rest(
            f"https://management.azure.com{expected_id}?api-version={platform.API_VERSION}",
            "briefing_job_readback",
        )
    )
    properties = json_object(job.get("properties"))
    configuration = json_object(properties.get("configuration"))
    template = json_object(properties.get("template"))
    containers = template.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise PlatformFailure("briefing_container_inventory_mismatch")
    container = json_object(containers[0])
    rows = container.get("env")
    if not isinstance(rows, list):
        raise PlatformFailure("briefing_environment_inventory_mismatch")
    actual = {
        text_field(json_object(row), "name"): text_field(json_object(row), "value") for row in rows
    }
    scheduled = flag(env, "BRIEFING_SCHEDULE_ENABLED")
    trigger = json_object(
        configuration.get("scheduleTriggerConfig" if scheduled else "manualTriggerConfig")
    )
    registries = configuration.get("registries")
    assignments = json_object(json_object(job.get("identity")).get("userAssignedIdentities"))
    selected_assignments = [
        json_object(value)
        for key, value in assignments.items()
        if key.casefold() == selected.id.casefold()
    ]
    resources = json_object(container.get("resources"))
    if (
        container.get("image") != reference
        or container.get("args") != ["run"]
        or container.get("command") not in (None, [])
        or actual != expected_environment(env)
        or len(rows) != len(actual)
        or any(json_object(row).get("secretRef") for row in rows)
        or configuration.get("replicaTimeout") != 3600
        or configuration.get("replicaRetryLimit") != 0
        or configuration.get("triggerType") != ("Schedule" if scheduled else "Manual")
        or trigger.get("parallelism") != 1
        or trigger.get("replicaCompletionCount") != 1
        or (scheduled and trigger.get("cronExpression") != "0 5 * * *")
        or len(assignments) != 1
        or len(selected_assignments) != 1
        or json_object(job.get("identity")).get("type") != "UserAssigned"
        or selected_assignments[0].get("clientId") != str(selected.client_id)
        or selected_assignments[0].get("principalId") != str(selected.principal_id)
        or properties.get("provisioningState") != "Succeeded"
        or not isinstance(job.get("location"), str)
        or str(job["location"]).replace(" ", "").casefold()
        != env["AZURE_LOCATION"].replace(" ", "").casefold()
        or properties.get("environmentId") != env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"]
        or properties.get("workloadProfileName") != "Consumption"
        or resources.get("cpu") != 0.5
        or resources.get("memory") != "1Gi"
        or not isinstance(registries, list)
        or len(registries) != 1
        or json_object(registries[0]).get("server") != env["AZURE_CONTAINER_REGISTRY_ENDPOINT"]
        or json_object(registries[0]).get("identity") != selected.id
        or json_object(registries[0]).get("passwordSecretRef") not in (None, "")
    ):
        raise PlatformFailure("briefing_job_configuration_mismatch")
    prices(env)
    verify_grants(env)
    verify_model(env, own=True)
    if preservation(env) != env["BRIEFING_PRESERVATION_SHA256"]:
        raise PlatformFailure("briefing_retained_resources_changed")
    event("briefing_job_readback", "success", correlation, category=revision, checks=1)


def control(command: str, env: dict[str, str], correlation: str) -> None:
    if command == "prepare-briefing-identity":
        prepare_identity(env, correlation)
    elif command == "prepare-briefing-layer":
        prepare(env, correlation)
    elif command == "build-briefing":
        if not flag(env, "BRIEFING_ENABLED"):
            raise PlatformFailure("briefing_workload_disabled")
        platform.build(env, correlation, service="briefing")
    elif command == "verify-briefing":
        verify(env, correlation)
    elif command == "execute-briefing":
        verify(env, correlation)
        name = platform.execute_job(env["BRIEFING_JOB_ID"], correlation, wait_seconds=3660)
        platform.set_environment("BRIEFING_LAST_EXECUTION", name)
        platform.execute_job(env["MIGRATION_JOB_ID"], correlation, arguments=["briefing-status"])
