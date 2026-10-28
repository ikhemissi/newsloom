import asyncio
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue, TypeAdapter, ValidationError

from agent_evaluation.inputs import ROOT, json_document
from agent_evaluation.policy import EvaluationFailure, verify_privacy

ARM = "https://management.azure.com"
API = "2025-06-01"
APP_API = "2025-07-01"
BOUND_ENVIRONMENT = (
    "AZURE_ENV_NAME",
    "AZURE_SUBSCRIPTION_ID",
    "AGENT_TENANT_ID",
    "MODEL_ACCOUNT_ID",
    "MODEL_ENDPOINT",
    "ENRICHMENT_DEPLOYMENT",
    "ENRICHMENT_JOB_ID",
    "AGENT_EVALUATION_PROJECT_ID",
    "AGENT_EVALUATION_PROJECT_ENDPOINT",
    "AGENT_IMAGE",
    "AGENT_IMAGE_REVISION",
)


def object_value(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise EvaluationFailure("invalid_control_object")
    return value


def text(value: dict[str, JsonValue], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise EvaluationFailure("missing_control_field")
    return result


def _read_command(arguments: list[str]) -> bytes:
    try:
        result = subprocess.run(arguments, cwd=ROOT, capture_output=True, check=False, timeout=45)
    except subprocess.TimeoutExpired:
        raise EvaluationFailure("evaluation_control_deadline") from None
    if result.returncode or len(result.stdout) > 256 * 1024:
        raise EvaluationFailure("evaluation_control_failed")
    return result.stdout


async def command(arguments: list[str]) -> dict[str, JsonValue]:
    verify_privacy()
    data = await asyncio.to_thread(_read_command, arguments)
    json_document(data)
    try:
        return object_value(TypeAdapter(JsonValue).validate_json(data, strict=True))
    except ValidationError:
        raise EvaluationFailure("invalid_control_response") from None


async def resource(identifier: str, api: str = API) -> dict[str, JsonValue]:
    if not identifier.startswith("/subscriptions/") or any(
        character in identifier for character in ("?", "#", "%", "\n", "\r", " ")
    ):
        raise EvaluationFailure("invalid_control_resource")
    return await command(
        [
            "az",
            "rest",
            "--method",
            "get",
            "--url",
            f"{ARM}{identifier}?api-version={api}",
            "--only-show-errors",
            "--output",
            "json",
        ]
    )


@dataclass(frozen=True)
class Context:
    environment: dict[str, str]
    operator: str

    def digest(self) -> str:
        value = {key: self.environment[key] for key in BOUND_ENVIRONMENT}
        value["operator"] = self.operator
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def verify_deployment(self) -> None:
        env = self.environment
        deployment = await resource(
            env["MODEL_ACCOUNT_ID"] + "/deployments/" + env["ENRICHMENT_DEPLOYMENT"]
        )
        properties = object_value(deployment.get("properties"))
        model = object_value(properties.get("model"))
        sku = object_value(deployment.get("sku"))
        if (
            text(model, "name") != "gpt-5.4-mini"
            or text(model, "version") != "2026-03-17"
            or text(model, "format") != "OpenAI"
            or text(sku, "name") != "DataZoneStandard"
            or sku.get("capacity") != 10
            or properties.get("provisioningState") != "Succeeded"
        ):
            raise EvaluationFailure("judge_deployment_drift")

    async def ensure_ready(self) -> None:
        await self.verify_deployment()
        env = self.environment
        executions = await resource(env["ENRICHMENT_JOB_ID"] + "/executions", APP_API)
        values = executions.get("value")
        if executions.get("nextLink") or not isinstance(values, list):
            raise EvaluationFailure("shared_workload_inventory_incomplete")
        for value in values:
            status = object_value(object_value(value).get("properties")).get("status")
            if status not in ("Succeeded", "Failed", "Stopped"):
                raise EvaluationFailure("shared_deployment_busy")
        within_half_hour = datetime.now(UTC).timestamp() % 1800
        if not 70 <= within_half_hour <= 1730:
            raise EvaluationFailure("shared_deployment_schedule_window")


async def read_context() -> Context:
    raw = await command(["azd", "env", "get-values", "--environment", "dev", "--output", "json"])
    env: dict[str, str] = {}
    for key in BOUND_ENVIRONMENT:
        env[key] = text(raw, key)
    if env["AZURE_ENV_NAME"] != "dev":
        raise EvaluationFailure("evaluation_environment_mismatch")
    for name in ("AZURE_SUBSCRIPTION_ID", "AGENT_TENANT_ID"):
        try:
            UUID(env[name])
        except ValueError:
            raise EvaluationFailure("invalid_evaluation_identity_context") from None
    account = await command(["az", "account", "show", "--only-show-errors", "--output", "json"])
    user = object_value(account.get("user"))
    if (
        account.get("id") != env["AZURE_SUBSCRIPTION_ID"]
        or account.get("tenantId") != env["AGENT_TENANT_ID"]
        or account.get("state") != "Enabled"
        or user.get("type") != "user"
    ):
        raise EvaluationFailure("evaluation_account_context_mismatch")
    operator = await command(
        ["az", "ad", "signed-in-user", "show", "--only-show-errors", "--output", "json"]
    )
    parent = await resource(env["MODEL_ACCOUNT_ID"])
    properties = object_value(parent.get("properties"))
    identity = object_value(parent.get("identity"))
    endpoints = object_value(properties.get("endpoints"))
    if (
        parent.get("kind") != "AIServices"
        or parent.get("location") != "francecentral"
        or properties.get("disableLocalAuth") is not True
        or properties.get("allowProjectManagement") is not True
        or identity.get("type") != "SystemAssigned"
        or text(endpoints, "AI Foundry API").rstrip("/") != env["MODEL_ENDPOINT"].rstrip("/")
    ):
        raise EvaluationFailure("evaluation_account_foundation_drift")
    project_id = env["AGENT_EVALUATION_PROJECT_ID"]
    if not project_id.startswith(env["MODEL_ACCOUNT_ID"] + "/projects/"):
        raise EvaluationFailure("foreign_evaluation_project")
    project = await resource(project_id)
    if text(project, "id").casefold() != project_id.casefold():
        raise EvaluationFailure("foreign_evaluation_project")
    return Context(env, text(operator, "id"))
