import subprocess
from datetime import UTC, datetime, timedelta, tzinfo

import pytest
from pydantic import JsonValue

from agent_evaluation import context
from agent_evaluation.context import APP_API, BOUND_ENVIRONMENT, Context
from agent_evaluation.policy import EvaluationFailure


def environment() -> dict[str, str]:
    result = dict.fromkeys(BOUND_ENVIRONMENT, "synthetic")
    result["MODEL_ACCOUNT_ID"] = "/subscriptions/synthetic/accounts/synthetic"
    result["ENRICHMENT_JOB_ID"] = "/subscriptions/synthetic/jobs/synthetic"
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

    async def resource(identifier: str, api: str = context.API) -> dict[str, JsonValue]:
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

    async def resource(identifier: str, api: str = context.API) -> dict[str, JsonValue]:
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
    async def resource(identifier: str, api: str = context.API) -> dict[str, JsonValue]:
        return executions if identifier.endswith("/executions") else deployment()

    monkeypatch.setattr(context, "resource", resource)
    with pytest.raises(EvaluationFailure, match=category):
        await Context(environment(), "synthetic").ensure_ready()


@pytest.mark.parametrize(
    "identifier", ["/foreign", "/subscriptions/test?x=1", "/subscriptions/%2e"]
)
async def test_foreign_resource_identifiers_never_reach_cli(identifier: str) -> None:
    with pytest.raises(EvaluationFailure, match="invalid_control_resource"):
        await context.resource(identifier)


def test_control_command_timeout_does_not_expose_raw_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired("synthetic-control-canary", 45)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(EvaluationFailure, match=r"^evaluation_control_deadline$"):
        context._read_command(["az", "account", "show"])
