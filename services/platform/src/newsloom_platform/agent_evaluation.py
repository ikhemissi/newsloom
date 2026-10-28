"""Metadata-only preparation for the retained evaluation layer, never provisioning."""

import hashlib
import re

from newsloom_platform import control, mcp_identity
from newsloom_platform.config import PlatformFailure, json_object
from newsloom_platform.events import event

ARM_API = "2025-06-01"


def prepare(env: dict[str, str], correlation: str) -> None:
    enabled = env.get("AGENT_EVALUATION_ENABLED", "false")
    if enabled not in ("true", "false"):
        raise PlatformFailure("invalid_agent_evaluation_enabled_setting")
    if enabled == "false":
        for key in (
            "AGENT_EVALUATION_ENABLED",
            "AGENT_EVALUATION_TENANT_ID",
            "AGENT_EVALUATION_OPERATOR_PRINCIPAL_ID",
        ):
            if key not in env:
                control.set_environment(key, "false" if key.endswith("ENABLED") else "")
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
    operator = mcp_identity.identifier(
        control.azure(
            ["ad", "signed-in-user", "show", "--query", "id"],
            "agent_evaluation_operator_inventory",
        )
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
    }.items():
        control.set_environment(key, value)
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
