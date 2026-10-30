import base64
import json
import subprocess
import time
from datetime import UTC, datetime, timedelta, tzinfo
from uuid import uuid4

import pytest
from pydantic import JsonValue

from agent_evaluation import context
from agent_evaluation.context import APP_API, BOUND_ENVIRONMENT, Context
from agent_evaluation.policy import EvaluationFailure


def environment() -> dict[str, str]:
    result = dict.fromkeys(BOUND_ENVIRONMENT, "synthetic")
    group = "/subscriptions/synthetic/resourceGroups/synthetic"
    result["MODEL_ACCOUNT_ID"] = group + "/providers/Microsoft.CognitiveServices/accounts/synthetic"
    result["ENRICHMENT_JOB_ID"] = group + "/providers/Microsoft.App/jobs/synthetic"
    return result


def deployment() -> dict[str, JsonValue]:
    return {
        "properties": {
            "model": {"name": "gpt-5.4-mini", "version": "2026-03-17", "format": "OpenAI"},
            "provisioningState": "Succeeded",
        },
        "sku": {"name": "DataZoneStandard", "capacity": 10},
    }


@pytest.mark.parametrize("seconds", [0, 69.999, 70, 900, 1730, 1730.001, 1799.999])
async def test_shared_schedule_exact_boundaries(
    seconds: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DateTime:
        @staticmethod
        def now(tz: tzinfo | None = None) -> datetime:
            return datetime(2026, 10, 28, tzinfo=UTC) + timedelta(seconds=seconds)

    async def resource(
        identifier: str, api: str = context.API, *, group: str
    ) -> dict[str, JsonValue]:
        if identifier.endswith("/executions"):
            assert api == APP_API
            return {"value": []}
        return deployment()

    monkeypatch.setattr(context, "datetime", DateTime)
    monkeypatch.setattr(context, "resource", resource)
    selected = Context(environment(), "synthetic")
    if 70 <= seconds <= 1730:
        await selected.ensure_ready()
    else:
        with pytest.raises(EvaluationFailure, match="shared_deployment_schedule_window"):
            await selected.ensure_ready()


@pytest.mark.parametrize(
    "change",
    [
        {"sku": {"name": "Standard", "capacity": 10}},
        {"sku": {"name": "DataZoneStandard", "capacity": 11}},
        {"properties": {"model": {"name": "foreign", "version": "2026-03-17", "format": "OpenAI"}}},
        {
            "properties": {
                "model": {"name": "gpt-5.4-mini", "version": "foreign", "format": "OpenAI"}
            }
        },
    ],
)
async def test_deployment_drift_blocks_before_shared_workload_read(
    change: dict[str, JsonValue], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def resource(
        identifier: str, api: str = context.API, *, group: str
    ) -> dict[str, JsonValue]:
        calls.append(identifier)
        return deployment() | change

    monkeypatch.setattr(context, "resource", resource)
    with pytest.raises(EvaluationFailure, match="judge_deployment_drift"):
        await Context(environment(), "synthetic").ensure_ready()
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("executions", "category"),
    [
        ({"value": [], "nextLink": "synthetic"}, "shared_workload_inventory_incomplete"),
        ({"value": {}}, "shared_workload_inventory_incomplete"),
        ({"value": [{"properties": {"status": "Running"}}]}, "shared_deployment_busy"),
        ({"value": [{"properties": {"status": "Unknown"}}]}, "shared_deployment_busy"),
        ({"value": [{"properties": {}}]}, "shared_deployment_busy"),
    ],
)
async def test_incomplete_or_active_shared_workloads_block(
    executions: dict[str, JsonValue], category: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def resource(
        identifier: str, api: str = context.API, *, group: str
    ) -> dict[str, JsonValue]:
        return executions if identifier.endswith("/executions") else deployment()

    monkeypatch.setattr(context, "resource", resource)
    with pytest.raises(EvaluationFailure, match=category):
        await Context(environment(), "synthetic").ensure_ready()


@pytest.mark.parametrize(
    "identifier",
    [
        "/foreign",
        "/subscriptions/test?x=1",
        "/subscriptions/%2e",
        "/subscriptions/test/resourceGroups/foreign/resources",
        "/subscriptions/test/resourceGroups/test-other/resources",
        "/subscriptions/test/resourceGroups/test/../resources",
        "/subscriptions/test/providers/Microsoft.Authorization/roleAssignments",
    ],
)
async def test_foreign_resource_identifiers_never_reach_cli(identifier: str) -> None:
    with pytest.raises(EvaluationFailure, match="invalid_control_resource"):
        await context.resource(identifier, group="/subscriptions/test/resourceGroups/test")


async def test_context_uses_only_rg_resources_and_cli_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscription, tenant, operator = (str(uuid4()) for _ in range(3))
    env = environment() | {
        "AZURE_ENV_NAME": "dev",
        "AZURE_SUBSCRIPTION_ID": subscription,
        "AGENT_TENANT_ID": tenant,
        "AZURE_RESOURCE_GROUP": "rg-newsloom-test",
    }
    group = f"/subscriptions/{subscription}/resourceGroups/rg-newsloom-test"
    account = group + "/providers/Microsoft.CognitiveServices/accounts/synthetic"
    project = account + "/projects/eval-newsloom-test"
    env.update(
        MODEL_ACCOUNT_ID=account,
        AGENT_EVALUATION_PROJECT_ID=project,
        ENRICHMENT_JOB_ID=group + "/providers/Microsoft.App/jobs/synthetic",
    )
    calls: list[list[str]] = []

    async def command(arguments: list[str]) -> dict[str, JsonValue]:
        calls.append(arguments)
        if arguments[0] == "azd":
            return dict(env)
        if arguments[:3] == ["az", "account", "show"]:
            return {
                "id": subscription,
                "tenantId": tenant,
                "state": "Enabled",
                "user": {"type": "user"},
            }
        if arguments[:3] == ["az", "account", "get-access-token"]:
            claims = {"oid": operator, "tid": tenant, "exp": time.time() + 600}
            payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
            return {"accessToken": f"header.{payload}.signature"}
        if arguments[:4] == ["az", "rest", "--method", "get"]:
            assert arguments[5].startswith(context.ARM + group + "/")
            if arguments[5].startswith(context.ARM + project + "?"):
                return {"id": project}
            assert arguments[5].startswith(context.ARM + account + "?")
            return {
                "kind": "AIServices",
                "location": "francecentral",
                "identity": {"type": "SystemAssigned"},
                "properties": {
                    "disableLocalAuth": True,
                    "allowProjectManagement": True,
                    "endpoints": {"AI Foundry API": env["MODEL_ENDPOINT"]},
                },
            }
        pytest.fail("outside-scope command")

    monkeypatch.setattr(context, "command", command)
    result = await context.read_context()
    assert result.operator == operator
    assert len(calls) == 5
    assert all(arguments[:2] != ["az", "ad"] for arguments in calls)


def test_control_command_timeout_does_not_expose_raw_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired("synthetic-control-canary", 45)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(EvaluationFailure, match=r"^evaluation_control_deadline$"):
        context._read_command(["az", "account", "show"])


@pytest.mark.parametrize("size", [256 * 1024 + 1, 1024 * 1024, 1024 * 1024 + 1])
def test_control_response_size_bound(size: int, monkeypatch: pytest.MonkeyPatch) -> None:
    def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(arguments, 0, stdout=b" " * size, stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    if size > 1024 * 1024:
        with pytest.raises(EvaluationFailure, match=r"^evaluation_control_failed$"):
            context._read_command(["az", "account", "show"])
    else:
        assert len(context._read_command(["az", "account", "show"])) == size


async def test_large_complete_execution_history_keeps_final_active_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executions = {
        "value": [
            {"properties": {"status": "Succeeded"}, "padding": "x" * 1024} for _ in range(300)
        ]
        + [{"properties": {"status": "Running"}}]
    }
    data = json.dumps(executions).encode()
    assert 256 * 1024 < len(data) < 1024 * 1024
    calls: list[list[str]] = []

    def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(arguments)
        response = data if "/executions?" in arguments[5] else json.dumps(deployment()).encode()
        return subprocess.CompletedProcess(arguments, 0, stdout=response, stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(EvaluationFailure, match=r"^shared_deployment_busy$"):
        await Context(environment(), "synthetic").ensure_ready()
    assert len(calls) == 2
    assert calls[-1][5].endswith("/executions?api-version=" + APP_API)
