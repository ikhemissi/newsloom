"""Metadata-only preparation for the retained evaluation layer, never provisioning."""

import hashlib
import re
import time

from newsloom_platform import control, mcp_identity, probe
from newsloom_platform.config import PlatformFailure, json_object
from newsloom_platform.events import event

ARM_API = "2025-06-01"
# Fingerprint of Microsoft's public Foundry User (formerly Azure AI User) role ID.
FOUNDRY_USER_ROLE_SHA256 = "1b2c85d975c797931286727893ff9d47615ac3276658f4aeb3c20ffcd44422dd"
FOUNDRY_PROJECT_MANAGER_ROLE_SHA256 = (
    "3513cfcf768dd13c016590ae6bc57b6870e9f0d04bce2ee2458f13473ee64610"
)
OPERATOR_TOKEN = [
    "account",
    "get-access-token",
    "--resource",
    "https://management.azure.com/",
    "--query",
    "accessToken",
]
DATA_INPUTS = {
    "enabled": "AGENT_EVALUATION_DATA_RESOURCES_ENABLED",
    "import_existing": "AGENT_EVALUATION_IMPORT_EXISTING_DATA_RESOURCES",
    "storage_name": "AGENT_EVALUATION_STORAGE_ACCOUNT_NAME",
    "connection_name": "AGENT_EVALUATION_STORAGE_CONNECTION_NAME",
    "storage_grant_name": "AGENT_EVALUATION_STORAGE_GRANT_NAME",
    "account_user_grant_name": "AGENT_EVALUATION_ACCOUNT_USER_GRANT_NAME",
    "account_manager_grant_name": "AGENT_EVALUATION_ACCOUNT_MANAGER_GRANT_NAME",
    "storage_role_id": "AGENT_EVALUATION_STORAGE_ROLE_ID",
    "appinsights_id": "AGENT_EVALUATION_DIAGNOSTIC_APPINSIGHTS_ID",
    "appinsights_reader_name": "AGENT_EVALUATION_DIAGNOSTIC_READER_GRANT_NAME",
    "appinsights_publisher_name": "AGENT_EVALUATION_DIAGNOSTIC_PUBLISHER_GRANT_NAME",
    "appinsights_reader_role_id": "AGENT_EVALUATION_DIAGNOSTIC_READER_ROLE_ID",
    "appinsights_publisher_role_id": "AGENT_EVALUATION_DIAGNOSTIC_PUBLISHER_ROLE_ID",
    "retain_experimental_appinsights_grants": "AGENT_EVALUATION_RETAIN_DIAGNOSTIC_GRANTS",
}
DATA_BOOLEAN_INPUTS = {"enabled", "import_existing", "retain_experimental_appinsights_grants"}
DATA_ROLE_HASHES = {
    "storage_role_id": "fe1e07b465de108d9fbd5aa7a702768beecabda8211f3a72a19c624a97a0d0cd",
    "appinsights_reader_role_id": (
        "ff5a1403c3544342c98473431511f4589219ab5ba57f30e7624c3c6e6d6bf8b3"
    ),
    "appinsights_publisher_role_id": (
        "451512f3ee32ea6c09538a7f7cc2f3269c8d67fcf337fd1939ab9ba665e320ee"
    ),
}


def data_configuration(env: dict[str, str]) -> dict[str, str]:
    values = {
        key: env.get(name, "false" if key in DATA_BOOLEAN_INPUTS else "")
        for key, name in DATA_INPUTS.items()
    }
    if any(values[key] not in ("true", "false") for key in DATA_BOOLEAN_INPUTS):
        raise PlatformFailure("invalid_agent_evaluation_data_setting")
    if values["enabled"] == "false":
        if (
            values["import_existing"] == "true"
            or values["retain_experimental_appinsights_grants"] == "true"
        ):
            raise PlatformFailure("agent_evaluation_data_required")
        return values
    if env.get("AGENT_EVALUATION_ENABLED") != "true":
        raise PlatformFailure("agent_evaluation_foundation_required")
    if not foundry_user_role_id(env) or not foundry_project_manager_role_id(env):
        raise PlatformFailure("agent_evaluation_data_operator_roles_required")
    if values["storage_name"] and not re.fullmatch(r"[a-z0-9]{3,24}", values["storage_name"]):
        raise PlatformFailure("agent_evaluation_storage_name_invalid")
    if values["connection_name"] and not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,32}", values["connection_name"]
    ):
        raise PlatformFailure("agent_evaluation_storage_connection_invalid")
    for key in ("storage_grant_name", "account_user_grant_name", "account_manager_grant_name"):
        if values[key] or values["import_existing"] == "true":
            mcp_identity.identifier(values[key])
    required_roles = {"storage_role_id"}
    if values["retain_experimental_appinsights_grants"] == "true":
        if any(
            not env.get(key)
            for key in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZURE_ENV_NAME")
        ):
            raise PlatformFailure("agent_evaluation_retained_inputs_required")
        required_roles |= {"appinsights_reader_role_id", "appinsights_publisher_role_id"}
        expected = (
            f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
            f"/providers/Microsoft.Insights/components/appi-newsloom-{env['AZURE_ENV_NAME']}"
        )
        if values["appinsights_id"].lower() != expected.lower():
            raise PlatformFailure("agent_evaluation_diagnostic_scope_invalid")
        for key in ("appinsights_reader_name", "appinsights_publisher_name"):
            mcp_identity.identifier(values[key])
    if any(
        hashlib.sha256(values[key].encode()).hexdigest() != DATA_ROLE_HASHES[key]
        for key in required_roles
    ):
        raise PlatformFailure("agent_evaluation_data_role_invalid")
    return values


def set_data_defaults(env: dict[str, str], values: dict[str, str]) -> None:
    for key, name in DATA_INPUTS.items():
        if name not in env:
            control.set_environment(name, values[key])


def foundry_user_role_id(env: dict[str, str]) -> str:
    value = env.get("AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID", "")
    if value and hashlib.sha256(value.encode()).hexdigest() != FOUNDRY_USER_ROLE_SHA256:
        raise PlatformFailure("agent_evaluation_foundry_user_role_invalid")
    return value


def foundry_project_manager_role_id(env: dict[str, str]) -> str:
    value = env.get("AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID", "")
    if value and hashlib.sha256(value.encode()).hexdigest() != FOUNDRY_PROJECT_MANAGER_ROLE_SHA256:
        raise PlatformFailure("agent_evaluation_foundry_project_manager_role_invalid")
    return value


def operator_from_token(value: object, tenant: str) -> str:
    if not isinstance(value, str):
        raise PlatformFailure("agent_evaluation_operator_context_invalid")
    try:
        claims = probe.token_claims(value)
    except ValueError:
        raise PlatformFailure("agent_evaluation_operator_context_invalid") from None
    expires = claims.get("exp")
    if (
        claims.get("tid") != tenant
        or type(expires) not in (int, float)
        or float(str(expires)) <= time.time()
    ):
        raise PlatformFailure("agent_evaluation_operator_context_invalid")
    return mcp_identity.identifier(claims.get("oid"))


def prepare(env: dict[str, str], correlation: str) -> None:
    foundry_user_role_id(env)
    foundry_project_manager_role_id(env)
    data = data_configuration(env)
    enabled = env.get("AGENT_EVALUATION_ENABLED", "false")
    if enabled not in ("true", "false"):
        raise PlatformFailure("invalid_agent_evaluation_enabled_setting")
    if enabled == "false":
        for key in (
            "AGENT_EVALUATION_ENABLED",
            "AGENT_EVALUATION_TENANT_ID",
            "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID",
            "AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID",
            "AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID",
        ):
            if key not in env:
                control.set_environment(key, "false" if key.endswith("ENABLED") else "")
        set_data_defaults(env, data)
        event("agent_evaluation_layer", "disabled", correlation)
        return

    required = (
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_ENV_NAME",
        "AZURE_RESOURCE_GROUP",
        "AZURE_LOCATION",
        "AGENT_TENANT_ID",
        "MODEL_ACCOUNT_ID",
        "MODEL_ACCOUNT_NAME",
        "MODEL_ENDPOINT",
        "ENRICHMENT_DEPLOYMENT",
        "ENRICHMENT_MODEL",
        "ENRICHMENT_VERSION",
        "ENRICHMENT_FORMAT",
        "ENRICHMENT_SKU",
        "ENRICHMENT_CAPACITY",
    )
    if any(not env.get(key) for key in required):
        raise PlatformFailure("agent_evaluation_retained_inputs_required")
    subscription = mcp_identity.identifier(env["AZURE_SUBSCRIPTION_ID"])
    tenant = mcp_identity.identifier(env["AGENT_TENANT_ID"])
    name = env["AZURE_ENV_NAME"]
    group = env["AZURE_RESOURCE_GROUP"]
    if (
        subscription != env["AZURE_SUBSCRIPTION_ID"]
        or tenant != env["AGENT_TENANT_ID"]
        or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name)
        or not re.fullmatch(r"[A-Za-z0-9_().-]{1,90}", group)
        or not re.fullmatch(r"[a-z0-9]+", env["AZURE_LOCATION"])
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", env["ENRICHMENT_DEPLOYMENT"])
        or not re.fullmatch(r"[1-9][0-9]*", env["ENRICHMENT_CAPACITY"])
    ):
        raise PlatformFailure("invalid_agent_evaluation_retained_context")
    suffix = hashlib.sha256(f"{subscription}/{name}".encode()).hexdigest()[:8]
    account_name = f"ai-newsloom-{name}-{suffix}"
    account_id = (
        f"/subscriptions/{subscription}/resourceGroups/{group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
    )
    endpoint = f"https://{account_name}.services.ai.azure.com/"
    if (
        env["MODEL_ACCOUNT_ID"] != account_id
        or env["MODEL_ACCOUNT_NAME"] != account_name
        or env["MODEL_ENDPOINT"] != endpoint
    ):
        raise PlatformFailure("agent_evaluation_account_boundary_mismatch")
    context = json_object(control.azure(["account", "show"], "agent_evaluation_cli_context"))
    if (
        context.get("id") != subscription
        or context.get("tenantId") != tenant
        or context.get("state") != "Enabled"
        or json_object(context.get("user")).get("type") != "user"
    ):
        raise PlatformFailure("agent_evaluation_cli_context_mismatch")
    operator = operator_from_token(
        control.azure(OPERATOR_TOKEN, "agent_evaluation_operator_context"),
        tenant,
    )
    if env.get("AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID", "") not in ("", operator) or env.get(
        "AGENT_EVALUATION_TENANT_ID", ""
    ) not in ("", tenant):
        raise PlatformFailure("agent_evaluation_operator_context_changed")
    account = json_object(
        control.rest(
            f"https://management.azure.com{account_id}?api-version={ARM_API}",
            "agent_evaluation_retained_account",
        )
    )
    properties = json_object(account.get("properties"))
    project_management = properties.get("allowProjectManagement")
    identity = account.get("identity")
    if identity is not None:
        identity = json_object(identity)
        if identity.get("type") not in ("None", "SystemAssigned"):
            raise PlatformFailure("agent_evaluation_account_identity_mismatch")
        if identity.get("type") == "SystemAssigned":
            mcp_identity.identifier(identity.get("principalId"))
            if identity.get("tenantId") != tenant:
                raise PlatformFailure("agent_evaluation_account_identity_mismatch")
    if (
        account.get("id") != account_id
        or account.get("name") != account_name
        or account.get("kind") != "AIServices"
        or account.get("location") != env["AZURE_LOCATION"]
        or properties.get("customSubDomainName") != account_name
        or properties.get("disableLocalAuth") is not True
        or properties.get("provisioningState") != "Succeeded"
        or not isinstance(project_management, bool)
    ):
        raise PlatformFailure("agent_evaluation_retained_account_mismatch")
    deployment_id = f"{account_id}/deployments/{env['ENRICHMENT_DEPLOYMENT']}"
    deployment = json_object(
        control.rest(
            f"https://management.azure.com{deployment_id}?api-version={ARM_API}",
            "agent_evaluation_retained_chat",
        )
    )
    deployment_properties = json_object(deployment.get("properties"))
    model = json_object(deployment_properties.get("model"))
    sku = json_object(deployment.get("sku"))
    capacity = sku.get("capacity")
    if (
        deployment.get("id") != deployment_id
        or deployment.get("name") != env["ENRICHMENT_DEPLOYMENT"]
        or deployment_properties.get("provisioningState") != "Succeeded"
        or deployment_properties.get("versionUpgradeOption") != "NoAutoUpgrade"
        or model.get("name") != env["ENRICHMENT_MODEL"]
        or model.get("version") != env["ENRICHMENT_VERSION"]
        or model.get("format") != env["ENRICHMENT_FORMAT"]
        or json_object(deployment_properties.get("capabilities")).get("chatCompletion") != "true"
        or sku.get("name") != env["ENRICHMENT_SKU"]
        or type(capacity) is not int
        or capacity != int(env["ENRICHMENT_CAPACITY"])
    ):
        raise PlatformFailure("agent_evaluation_retained_chat_mismatch")
    for key, value in {
        "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID": operator,
        "AGENT_EVALUATION_TENANT_ID": tenant,
        **(
            {"AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID": ""}
            if "AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID" not in env
            else {}
        ),
        **(
            {"AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID": ""}
            if "AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID" not in env
            else {}
        ),
    }.items():
        control.set_environment(key, value)
    set_data_defaults(env, data)
    event(
        "agent_evaluation_layer",
        "prepared",
        correlation,
        counts={
            "metadata_reads": 4,
            "account_prerequisites_ready": int(
                project_management
                and identity is not None
                and identity.get("type") == "SystemAssigned"
            ),
            "resource_mutations": 0,
            "model_calls": 0,
        },
    )
