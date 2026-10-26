import base64
import json
import re
import subprocess
import sys
import textwrap
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import IO, Literal
from uuid import uuid4

import pytest
from newsloom_core.phase1_contracts import (
    EXPECTED,
    AcceptanceFailure,
    CaseResult,
    Report,
    Stage,
    TestConfig,
)
from pydantic import ValidationError
from test_phase1_contracts import phase_config as phase_config

from scripts import phase1_workflow as workflow


class Clock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.origin = datetime.now(UTC)

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.elapsed += seconds


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    value = Clock()
    real_datetime = datetime

    class DateTime:
        @staticmethod
        def now(tz: tzinfo | None = None) -> datetime:
            current = value.origin + timedelta(seconds=value.elapsed)
            return current.astimezone(tz) if tz is not None else current.replace(tzinfo=None)

        @staticmethod
        def fromisoformat(text: str) -> datetime:
            return real_datetime.fromisoformat(text)

    monkeypatch.setattr(workflow, "time", value)
    monkeypatch.setattr(workflow, "datetime", DateTime)
    monkeypatch.setattr(sys.modules[__name__], "datetime", DateTime)
    return value


@pytest.fixture
def inputs(
    phase_config: TestConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> workflow.Inputs:
    subscription = str(uuid4())
    values = {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "ikhemissi/newsloom",
        "GITHUB_SHA": "c" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "PHASE1_WORKFLOW_STARTED_AT": datetime.now(UTC).isoformat(),
        "PHASE1_WORKFLOW_DEADLINE": (datetime.now(UTC) + timedelta(minutes=28)).isoformat(),
        "PHASE1_CLIENT_ID": str(phase_config.client_id),
        "PHASE1_RUN_ID": phase_config.run_id,
        "PHASE1_SCENARIO": "acceptance",
        "PHASE1_JOB_ID": (
            f"/subscriptions/{subscription}/resourceGroups/rg-newsloom-test/"
            "providers/Microsoft.App/jobs/accept-newsloom-test"
        ),
        "PHASE1_IMAGE": "test.azurecr.io/newsloom-phase1@sha256:" + "a" * 64,
        "PHASE1_IMAGE_REVISION": phase_config.image_revision,
        "PHASE1_FIXTURE_REVISION": "e" * 64,
        "PHASE1_SCHEMA_REVISION": "d" * 64,
        "PHASE1_MODEL_REVISION": phase_config.model_revision(),
        "PHASE1_LOG_WORKSPACE_ID": str(uuid4()),
        "PHASE1_LOG_ENVIRONMENT": "synthetic-environment",
        "AZURE_SUBSCRIPTION_ID": subscription,
        "RUNNER_TEMP": str(tmp_path),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return workflow.Inputs.environment()


def report(inputs: workflow.Inputs) -> Report:
    return Report(
        run_id=inputs.run_id,
        scenario=inputs.scenario,
        outcome="success",
        fixture_revision=inputs.fixture_revision,
        schema_revision=inputs.schema_revision,
        model_revision=inputs.model_revision,
        image_revision=inputs.image_revision,
        stages=tuple(
            Stage.model_validate({"name": name, "counts": counts, "elapsed_seconds": 0.1})
            for name, counts in EXPECTED.items()
        ),
        cases=tuple(
            CaseResult.model_validate(
                {
                    "id": name,
                    "disposition": "rejected" if name.endswith("hostile") else "accepted",
                    "reason": "screened",
                    "score": 0.9 if name.endswith("hostile") else 0.1,
                    "threshold": 0.5,
                }
            )
            for name in ("rss-benign", "rss-hostile", "atom-benign", "atom-hostile")
        ),
    )


def job(inputs: workflow.Inputs, config: TestConfig, fault: str = "") -> dict[str, object]:
    if fault == "client":
        config = config.model_copy(update={"client_id": uuid4()})
    encoded = base64.b64encode(
        config.model_dump_json(exclude={"run_id", "scenario"}).encode()
    ).decode()
    identity_id = inputs.job_id.split("/providers/")[0] + (
        "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/phase1-newsloom-test"
    )
    if fault == "identity":
        identity_id = identity_id.replace("phase1-newsloom-test", "production")
    return {
        "id": inputs.job_id,
        "identity": {
            "userAssignedIdentities": {
                identity_id: {
                    "clientId": str(config.client_id),
                    "principalId": str(config.principal_id),
                }
            }
        },
        "properties": {
            "environmentId": inputs.job_id.split("/providers/")[0]
            + "/providers/Microsoft.App/managedEnvironments/"
            + ("foreign" if fault == "environment" else "cae-newsloom-test"),
            "configuration": {"triggerType": "Schedule" if fault == "schedule" else "Manual"},
            "template": {
                "containers": [
                    {
                        "name": "acceptance",
                        "image": "test.azurecr.io/newsloom-phase1:latest"
                        if fault == "image"
                        else inputs.image,
                        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                        "args": ["run"],
                        "env": [{"name": "PHASE1_CONFIG_BASE64", "value": encoded}],
                    }
                ]
            },
        },
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_REF", "refs/heads/unapproved"),
        ("GITHUB_REF", "refs/pull/1/merge"),
        ("GITHUB_REPOSITORY", "unapproved/fork"),
        ("PHASE1_RUN_ID", "newsloom"),
        ("PHASE1_JOB_ID", "https://unapproved.invalid/job"),
        ("PHASE1_IMAGE", "test.azurecr.io/newsloom-phase1:latest"),
        ("PHASE1_IMAGE_REVISION", "unbound"),
        ("PHASE1_LOG_WORKSPACE_ID", "https://unapproved.invalid/query"),
        ("PHASE1_LOG_ENVIRONMENT", "foreign' OR 'true"),
        ("GITHUB_SHA", "not-a-commit"),
    ],
)
def test_untrusted_inputs_fail_before_azure(
    inputs: workflow.Inputs,
    key: str,
    value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(key, value)
    with pytest.raises((workflow.WorkflowFailure, AcceptanceFailure, ValidationError, ValueError)):
        workflow.Inputs.environment()


@pytest.mark.parametrize("fault", ["image", "identity", "client", "schedule", "environment"])
def test_live_job_contract_cannot_substitute_image_identity_or_schedule(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflow, "api", lambda *args, **kwargs: job(inputs, phase_config, fault))
    with pytest.raises(workflow.WorkflowFailure):
        workflow.Controller(inputs).template()
    assert not inputs.state_path.exists()


def query_response(
    inputs: workflow.Inputs, execution: str, records: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "tables": [
            {
                "name": "PrimaryResult",
                "columns": workflow.LOG_COLUMNS,
                "rows": [
                    [
                        inputs.job_name,
                        inputs.log_environment,
                        execution + "-replica",
                        "acceptance",
                        datetime.now(UTC).isoformat(),
                        json.dumps(record),
                    ]
                    for record in records
                ],
            }
        ]
    }


def query_execution(body: object) -> str:
    assert isinstance(body, dict) and set(body) == {"query"}
    expression = body["query"]
    assert isinstance(expression, str)
    match = re.search(r"ContainerGroupName startswith '(accept-newsloom-test-[a-z]+)-'", expression)
    assert match is not None
    return match[1]


def fake_api(
    inputs: workflow.Inputs,
    config: TestConfig,
    *,
    main_status: str = "Succeeded",
) -> tuple[Callable[..., dict[str, object]], list[str]]:
    starts: list[str] = []

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if url.startswith("https://api.loganalytics.azure.com/"):
            assert url.endswith(f"/{inputs.log_workspace_id}/query")
            assert resource == "https://api.loganalytics.io"
            execution = query_execution(body)
            value = (
                {"event": "phase1_cleanup", "run_id": inputs.run_id, "absent": 1}
                if execution.endswith("cleanup")
                else report(inputs).model_dump(mode="json")
            )
            return query_response(inputs, execution, [value])
        if "/start?" in url:
            assert isinstance(body, dict)
            containers = body["containers"]
            assert isinstance(containers, list) and len(containers) == 1
            container = workflow.object_value(containers[0])
            assert container["image"] == inputs.image and "command" not in container
            args = container["args"]
            assert isinstance(args, list) and args[0] in ("run", "cleanup")
            assert args[1:3] == ["--run-id", inputs.run_id]
            starts.append(args[0])
            return {"name": "accept-newsloom-test-" + args[0]}
        if "/executions/" in url:
            return {"properties": {"status": "Succeeded" if "-cleanup?" in url else main_status}}
        return job(inputs, config)

    return api, starts


def test_success_requires_bound_report_job_success_and_independent_cleanup(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, starts = fake_api(inputs, phase_config)
    monkeypatch.setattr(workflow, "api", api)

    controller = workflow.Controller(inputs)
    controller.run()
    workflow.Controller(inputs).cleanup()
    receipt = json.loads(inputs.report_path.read_text())
    assert starts == ["run", "cleanup"] and receipt["outcome"] == "success"
    assert receipt["cleanup_verified"] is True
    assert inputs.state_path.stat().st_mode & 0o777 == 0o600
    assert str(phase_config.client_id) not in inputs.report_path.read_text()
    assert str(phase_config.principal_id) not in inputs.report_path.read_text()
    assert "PHASE1_CONFIG_BASE64" not in inputs.report_path.read_text()
    assert str(inputs.log_workspace_id) not in inputs.report_path.read_text()


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "revision",
        "run",
        "boolean",
        "incomplete",
        "job_failed",
        "log_failed",
    ],
)
def test_incomplete_stale_or_failed_proof_cannot_report_success(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api, _ = fake_api(
        inputs, phase_config, main_status="Failed" if fault == "job_failed" else "Succeeded"
    )
    monkeypatch.setattr(workflow, "api", api)
    value = report(inputs).model_dump(mode="json")
    if fault == "revision":
        value["image_revision"] = "d" * 64
    if fault == "run":
        value["run_id"] = uuid4().hex
    if fault == "boolean":
        value["stages"][-1]["counts"]["absent"] = True
    if fault == "incomplete":
        value["stages"] = value["stages"][:-1]

    def logs(self: workflow.Controller, execution: str) -> list[dict[str, object]]:
        if fault == "log_failed":
            raise workflow.WorkflowFailure("phase1_azure_command_failed")
        if fault == "missing":
            return []
        return [value] * (2 if fault == "duplicate" else 1)

    monkeypatch.setattr(workflow.Controller, "logs", logs)
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "run"])
    with pytest.raises(SystemExit) as result:
        workflow.main()
    assert result.value.code == 1
    receipt = json.loads(inputs.report_path.read_text())
    assert receipt["outcome"] == "failure"
    assert "CANARY" not in capsys.readouterr().out


def test_stale_success_file_is_not_a_success_shaped_fallback(
    inputs: workflow.Inputs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs.report_path.write_text('{"outcome":"success","untrusted":"NEWSLOOM_CONTENT_CANARY"}')
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "run"])
    with pytest.raises(SystemExit):
        workflow.main()
    receipt = json.loads(inputs.report_path.read_text())
    assert receipt["outcome"] == "failure"
    assert receipt["category"] == "phase1_execution_state_already_exists"
    assert "CANARY" not in inputs.report_path.read_text()


@pytest.mark.parametrize(
    "fault", ["missing_state", "wrong_state", "wrong_cleanup", "boolean_cleanup"]
)
def test_cleanup_does_not_touch_foreign_targets_or_accept_ambiguous_absence(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, starts = fake_api(inputs, phase_config)
    monkeypatch.setattr(workflow, "api", api)
    controller = workflow.Controller(inputs)
    if fault != "missing_state":
        state = dict(controller.state)
        if fault == "wrong_state":
            state["run_id"] = uuid4().hex
        workflow.save(inputs.state_path, state)
        controller.envelope(outcome="failure", category="original_test_failure")
    value = {"event": "phase1_cleanup", "run_id": inputs.run_id, "absent": 1}
    if fault == "wrong_cleanup":
        value["run_id"] = uuid4().hex
    if fault == "boolean_cleanup":
        value["absent"] = True
    monkeypatch.setattr(workflow.Controller, "logs", lambda *args, **kwargs: [value])
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "cleanup"])
    with pytest.raises(SystemExit):
        workflow.main()
    receipt = json.loads(inputs.report_path.read_text())
    assert receipt["outcome"] == "failure"
    if fault in ("missing_state", "wrong_state"):
        assert not starts
    else:
        assert receipt["category"] == "original_test_failure"
        assert receipt["cleanup_category"] == "phase1_cleanup_not_verified"


def test_upstream_errors_are_not_printed_or_written_as_payloads(
    inputs: workflow.Inputs,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["az"], 1, "", "NEWSLOOM_CREDENTIAL_CANARY")

    monkeypatch.setattr(subprocess, "run", failed)
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "run"])
    with pytest.raises(SystemExit):
        workflow.main()
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err + inputs.report_path.read_text()


def test_workflow_has_only_manual_main_no_environment_or_static_credentials() -> None:
    text = Path(".github/workflows/phase1-acceptance.yml").read_text()
    assert "workflow_dispatch:" in text and "github.ref == 'refs/heads/main'" in text
    assert "pull_request" not in text and "schedule:" not in text and "\n  push:" not in text
    assert not re.search(r"^\s+environment:", text, re.M)
    assert "secrets." not in text and "id-token: write" in text
    assert "cancel-in-progress: false" in text and "retention-days: 7" in text
    assert len(re.findall(r"uses: [\w/-]+@[a-f0-9]{40}", text)) == 4


@pytest.mark.parametrize("scenario", ["failure-after-ingestion", "cancel-after-claim"])
def test_negative_drills_stay_failed_while_same_identity_cleanup_is_verified(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = report(inputs).model_dump(mode="json")
    monkeypatch.setenv("PHASE1_SCENARIO", scenario)
    current = workflow.Inputs.environment()
    stopped = False
    starts: list[str] = []

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if url.startswith("https://api.loganalytics.azure.com/"):
            assert resource == "https://api.loganalytics.io"
            execution = query_execution(body)
            if execution.endswith("cleanup"):
                value = {"event": "phase1_cleanup", "run_id": inputs.run_id, "absent": 1}
            elif scenario == "cancel-after-claim":
                value = {"event": "phase1_checkpoint", "stage": "claim_committed"}
            else:
                value = failure.model_dump(mode="json")
            return query_response(current, execution, [value])
        if "/start?" in url:
            assert isinstance(body, dict) and isinstance(body["containers"], list)
            first = workflow.object_value(body["containers"][0])
            args = first["args"]
            assert isinstance(args, list)
            operation = str(args[0])
            starts.append(operation)
            return {"name": "accept-newsloom-test-" + operation}
        if "/executions/" in url:
            if "-cleanup?" in url:
                status = "Succeeded"
            elif scenario == "failure-after-ingestion":
                status = "Failed"
            else:
                status = "Stopped" if stopped else "Running"
            return {"properties": {"status": status}}
        return job(current, phase_config)

    failure = Report.model_validate(
        {
            **base,
            "scenario": scenario,
            "outcome": "failure",
            "category": "intentional_failure_after_ingestion",
            "stages": [
                stage
                for stage in base["stages"]
                if stage["name"]
                in (
                    "prepared",
                    "isolation",
                    "ingestion",
                    "cleanup",
                )
            ],
        }
    )

    def command(arguments: list[str], **kwargs: object) -> str:
        nonlocal stopped
        if arguments[:3] == ["containerapp", "job", "stop"]:
            assert (
                arguments[arguments.index("--job-execution-name") + 1] == "accept-newsloom-test-run"
            )
            stopped = True
            return "{}"
        raise AssertionError("unexpected_development_api_command")

    monkeypatch.setattr(workflow, "api", api)
    monkeypatch.setattr(workflow, "command", command)
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "run"])
    with pytest.raises(SystemExit) as failed:
        workflow.main()
    assert failed.value.code == 1
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "cleanup"])
    workflow.main()
    receipt = json.loads(inputs.report_path.read_text())
    assert receipt["outcome"] == "failure" and receipt["cleanup_verified"] is True
    assert starts == ["run", "cleanup"]
    assert stopped == (scenario == "cancel-after-claim")
    if scenario == "failure-after-ingestion":
        assert receipt["report"]["category"] == "intentional_failure_after_ingestion"


@pytest.mark.parametrize(
    "fault",
    [
        "partial",
        "tables",
        "columns",
        "rows",
        "too_many",
        "row_shape",
        "typed",
        "job",
        "environment",
        "replica",
        "container",
        "naive_time",
        "past",
        "future",
        "oversized_message",
    ],
)
def test_log_query_rejects_partial_or_foreign_platform_evidence(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _ = fake_api(inputs, phase_config)
    monkeypatch.setattr(workflow, "api", api)
    controller = workflow.Controller(inputs)
    execution = controller.start()
    response = query_response(inputs, execution, [report(inputs).model_dump(mode="json")])
    tables = response["tables"]
    assert isinstance(tables, list)
    table = workflow.object_value(tables[0])
    tables[0] = table
    rows = table["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, list)
    if fault == "partial":
        response["error"] = {"code": "PartialError", "message": "NEWSLOOM_CREDENTIAL_CANARY"}
    elif fault == "tables":
        response["tables"] = []
    elif fault == "columns":
        table["columns"] = []
    elif fault == "rows":
        table["rows"] = {}
    elif fault == "too_many":
        table["rows"] = rows * 301
    elif fault == "row_shape":
        rows[0] = row[:-1]
    elif fault == "typed":
        row[0] = True
    elif fault == "naive_time":
        row[4] = datetime.now().isoformat()
    elif fault in ("past", "future"):
        row[4] = (datetime.now(UTC) + timedelta(hours=1 if fault == "future" else -1)).isoformat()
    elif fault == "oversized_message":
        row[5] = "x" * 32769
    else:
        row[{"job": 0, "environment": 1, "replica": 2, "container": 3}[fault]] = "foreign"
    monkeypatch.setattr(workflow, "api", lambda *args, **kwargs: response)
    with pytest.raises(workflow.WorkflowFailure, match="phase1_log_"):
        controller.logs(execution)
    assert not inputs.report_path.exists()


def test_queries_use_fixed_entra_audience_and_bounded_exact_execution_metadata(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _ = fake_api(inputs, phase_config)
    expressions = []

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if resource:
            assert resource == "https://api.loganalytics.io"
            assert url == (
                f"https://api.loganalytics.azure.com/v1/workspaces/{inputs.log_workspace_id}/query"
            )
            query_execution(body)
            assert isinstance(body, dict)
            expression = str(body["query"])
            expressions.append(expression)
            assert expression.startswith("ContainerAppConsoleLogs | where TimeGenerated between")
            assert f"JobName == '{inputs.job_name}'" in expression
            assert f"EnvironmentName == '{inputs.log_environment}'" in expression
            assert "ContainerName == 'acceptance'" in expression
            assert expression.endswith("TimeGenerated, Log | take 301")
            assert "getAuthToken" not in expression and "union" not in expression
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)
    workflow.Controller(inputs).run()
    workflow.Controller(inputs).cleanup()
    assert len(expressions) == 2


def test_terminal_status_still_polls_for_delayed_reports_and_cleanup(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, starts = fake_api(inputs, phase_config)
    calls: dict[str, int] = {}

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if resource:
            execution = query_execution(body)
            calls[execution] = calls.get(execution, 0) + 1
            if calls[execution] < 4:
                return query_response(inputs, execution, [])
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)
    workflow.Controller(inputs).run()
    workflow.Controller(inputs).cleanup()
    assert starts == ["run", "cleanup"] and clock.elapsed == 30
    assert json.loads(inputs.report_path.read_text())["cleanup_verified"] is True


@pytest.mark.parametrize("cleanup", [False, True])
def test_missing_query_evidence_expires_without_success_or_category_loss(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    cleanup: bool,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _ = fake_api(inputs, phase_config)

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if resource:
            return query_response(inputs, query_execution(body), [])
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)
    if cleanup:
        controller = workflow.Controller(inputs)
        workflow.save(inputs.state_path, controller.state)
        controller.envelope(outcome="failure", category="original_failure")
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "cleanup" if cleanup else "run"])
    with pytest.raises(SystemExit):
        workflow.main()
    receipt = json.loads(inputs.report_path.read_text())
    assert receipt["outcome"] == "failure" and receipt["cleanup_verified"] is False
    assert clock.elapsed == (600 if cleanup else 1260)
    if cleanup:
        assert receipt["category"] == "original_failure"
        assert receipt["cleanup_category"] == "phase1_cleanup_deadline"
    else:
        assert receipt["category"] == "phase1_execution_report_missing"


@pytest.mark.parametrize("setting", ["PHASE1_LOG_WORKSPACE_ID", "PHASE1_LOG_ENVIRONMENT"])
def test_changed_log_binding_cannot_reuse_another_execution_state(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    setting: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, starts = fake_api(inputs, phase_config)
    monkeypatch.setattr(workflow, "api", base)
    workflow.Controller(inputs).run()
    monkeypatch.setenv(
        setting, str(uuid4()) if setting == "PHASE1_LOG_WORKSPACE_ID" else "foreign-environment"
    )
    with pytest.raises(workflow.WorkflowFailure, match="phase1_cleanup_state_mismatch"):
        workflow.Controller(workflow.Inputs.environment()).cleanup()
    assert starts == ["run"]


def test_oversized_cli_response_is_not_a_valid_query_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(["az"], 0, "x" * 262145, ""),
    )
    with pytest.raises(workflow.WorkflowFailure, match="phase1_command_response_limit"):
        workflow.command(["rest", "--url", "https://api.loganalytics.azure.com"])


def test_query_api_does_not_print_private_error_payloads(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base, _ = fake_api(inputs, phase_config)

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if resource:
            return {"error": {"code": "PartialError", "message": "NEWSLOOM_CONTENT_CANARY"}}
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "run"])
    with pytest.raises(SystemExit):
        workflow.main()
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err + inputs.report_path.read_text()


@pytest.mark.parametrize("fault", ["missing", "naive", "extended", "future", "run", "attempt"])
def test_invalid_deadline_or_workflow_identity_fails_before_azure(
    inputs: workflow.Inputs,
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if fault == "missing":
        monkeypatch.delenv("PHASE1_WORKFLOW_DEADLINE")
    elif fault == "naive":
        monkeypatch.setenv(
            "PHASE1_WORKFLOW_STARTED_AT",
            inputs.workflow_started_at.replace(tzinfo=None).isoformat(),
        )
    elif fault == "extended":
        monkeypatch.setenv(
            "PHASE1_WORKFLOW_DEADLINE",
            (inputs.workflow_deadline + timedelta(seconds=1)).isoformat(),
        )
    elif fault == "future":
        for key, value in (
            ("PHASE1_WORKFLOW_STARTED_AT", inputs.workflow_started_at),
            ("PHASE1_WORKFLOW_DEADLINE", inputs.workflow_deadline),
        ):
            monkeypatch.setenv(key, (value + timedelta(seconds=1)).isoformat())
    else:
        monkeypatch.setenv("GITHUB_RUN_ID" if fault == "run" else "GITHUB_RUN_ATTEMPT", "untrusted")
    with pytest.raises((workflow.WorkflowFailure, KeyError)):
        workflow.Inputs.environment()


@pytest.mark.parametrize(
    "setting", ["GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "PHASE1_WORKFLOW_DEADLINE"]
)
def test_cleanup_cannot_reset_deadline_or_reuse_a_foreign_workflow(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    setting: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, starts = fake_api(inputs, phase_config)
    monkeypatch.setattr(workflow, "api", base)
    workflow.Controller(inputs).run()
    if setting == "PHASE1_WORKFLOW_DEADLINE":
        for key, value in (
            ("PHASE1_WORKFLOW_STARTED_AT", inputs.workflow_started_at),
            ("PHASE1_WORKFLOW_DEADLINE", inputs.workflow_deadline),
        ):
            monkeypatch.setenv(key, (value - timedelta(seconds=1)).isoformat())
    else:
        monkeypatch.setenv(setting, "d" * 40 if setting == "GITHUB_SHA" else "2")
    expected = (
        "stale_phase1_workflow_receipt"
        if setting == "GITHUB_SHA"
        else "phase1_cleanup_state_mismatch"
    )
    with pytest.raises(workflow.WorkflowFailure, match=expected):
        workflow.Controller(workflow.Inputs.environment()).cleanup()
    assert starts == ["run"]


def test_measured_delivery_delays_fit_the_shared_budget(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, starts = fake_api(inputs, phase_config)
    cleanup_available = 0.0

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        nonlocal cleanup_available
        if "/start?" in url:
            result = base(url, body=body, resource=resource)
            if starts[-1] == "cleanup":
                cleanup_available = clock.elapsed + 35 + 218
                clock.sleep(35)
            return result
        if resource:
            execution = query_execution(body)
            available = cleanup_available if execution.endswith("cleanup") else 359 + 271
            if clock.elapsed < available:
                return query_response(inputs, execution, [])
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)
    workflow.Controller(inputs).run()
    assert clock.elapsed == 630
    workflow.Controller(inputs).cleanup()
    assert 883 <= clock.elapsed < 890 and starts == ["run", "cleanup"]
    assert json.loads(inputs.report_path.read_text())["cleanup_verified"] is True


def test_template_and_start_time_are_inside_the_main_phase(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _ = fake_api(inputs, phase_config)

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if resource:
            return query_response(inputs, query_execution(body), [])
        if "/executions/" not in url:
            clock.sleep(40)
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)
    with pytest.raises(workflow.WorkflowFailure, match="phase1_execution_report_missing"):
        workflow.Controller(inputs).run()
    assert clock.elapsed == 1260


@pytest.mark.parametrize("elapsed", [1100, 1679, 1680])
def test_cleanup_uses_only_original_shared_remaining_time(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    elapsed: int,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, starts = fake_api(inputs, phase_config)
    controller = workflow.Controller(inputs)
    workflow.save(inputs.state_path, controller.state)
    controller.envelope(outcome="failure", category="original_failure")
    clock.sleep(elapsed)

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        assert 0 < timeout <= min(60, 1680 - clock.elapsed)
        if resource:
            return query_response(inputs, query_execution(body), [])
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)
    monkeypatch.setattr("sys.argv", ["phase1_workflow.py", "cleanup"])
    with pytest.raises(SystemExit):
        workflow.main()
    receipt = json.loads(inputs.report_path.read_text())
    assert clock.elapsed == 1680 and receipt["category"] == "original_failure"
    assert receipt["cleanup_category"] == "phase1_cleanup_deadline"
    assert starts == ([] if elapsed == 1680 else ["cleanup"])


@pytest.mark.parametrize("operation", ["template", "start", "status", "query"])
def test_only_read_only_timeouts_have_bounded_retries(
    inputs: workflow.Inputs,
    operation: Literal["template", "start", "status", "query"],
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        calls.append(timeout)
        clock.sleep(timeout)
        raise subprocess.TimeoutExpired(["NEWSLOOM_CREDENTIAL_CANARY"], timeout)

    monkeypatch.setattr(workflow, "api", api)
    with pytest.raises(workflow.WorkflowFailure, match=f"phase1_{operation}_timeout"):
        workflow.Controller(inputs).request("https://management.azure.com", operation)
    count = 3 if operation in ("status", "query") else 1
    assert calls == [60] * count and clock.elapsed == count * 60 + (count - 1) * 5
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err


def test_read_timeout_retry_cannot_extend_the_shared_deadline(
    inputs: workflow.Inputs,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    clock.sleep(1619)

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        calls.append(timeout)
        clock.sleep(timeout)
        raise subprocess.TimeoutExpired(["az"], timeout)

    monkeypatch.setattr(workflow, "api", api)
    with pytest.raises(workflow.WorkflowFailure, match="phase1_workflow_deadline"):
        workflow.Controller(inputs).request("https://management.azure.com", "query")
    assert calls == [60] and clock.elapsed == 1680


@pytest.mark.parametrize("fault", ["json", "exit", "foreign"])
def test_bad_responses_are_not_retried_or_exposed(
    inputs: workflow.Inputs,
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def api(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if fault == "json":
            raise json.JSONDecodeError("private", "NEWSLOOM_CONTENT_CANARY", 0)
        raise workflow.WorkflowFailure(
            "phase1_azure_command_failed"
            if fault == "exit"
            else "phase1_log_record_metadata_mismatch"
        )

    monkeypatch.setattr(workflow, "api", api)
    with pytest.raises(workflow.WorkflowFailure):
        workflow.Controller(inputs).request("https://management.azure.com", "query")
    assert calls == 1
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err


def test_uncertain_start_is_not_replayed_by_cleanup(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _ = fake_api(inputs, phase_config)
    starts = 0

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        nonlocal starts
        if "/start?" in url:
            starts += 1
            raise subprocess.TimeoutExpired(["az"], timeout)
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)
    for operation in ("run", "cleanup"):
        monkeypatch.setattr("sys.argv", ["phase1_workflow.py", operation])
        with pytest.raises(SystemExit):
            workflow.main()
    receipt = json.loads(inputs.report_path.read_text())
    assert starts == 1 and receipt["category"] == "phase1_start_timeout"
    assert receipt["cleanup_category"] == "phase1_start_outcome_needs_operator"


def test_late_api_result_cannot_be_accepted_after_the_deadline(
    inputs: workflow.Inputs,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock.sleep(1679)
    calls = []

    def api(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs["timeout"])
        clock.sleep(2)
        return {"properties": {"status": "Succeeded"}}

    monkeypatch.setattr(workflow, "api", api)
    with pytest.raises(workflow.WorkflowFailure, match="phase1_workflow_deadline"):
        workflow.Controller(inputs).request("https://management.azure.com", "status")
    assert calls == [1]


def test_claim_delivery_delay_does_not_reset_the_original_deadline(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHASE1_SCENARIO", "cancel-after-claim")
    inputs = workflow.Inputs.environment()
    base, starts = fake_api(inputs, phase_config, main_status="Running")
    stops = []

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if resource:
            records: list[dict[str, object]] = (
                [{"event": "phase1_checkpoint", "stage": "claim_committed"}]
                if clock.elapsed >= 43 + 289
                else []
            )
            return query_response(inputs, query_execution(body), records)
        return base(url, body=body, resource=resource)

    monkeypatch.setattr(workflow, "api", api)

    def stop(args: list[str], *, timeout: float = 60) -> str:
        stops.append(timeout)
        return ""

    monkeypatch.setattr(workflow, "command", stop)
    with pytest.raises(workflow.WorkflowFailure, match="intentional_phase1_cancellation_drill"):
        workflow.Controller(inputs).run()
    state = json.loads(inputs.state_path.read_text())
    assert clock.elapsed == 335 and starts == ["run"] and len(stops) == 1
    assert state["workflow_deadline"] == inputs.workflow_deadline.isoformat()


def test_uncertain_stop_is_not_replayed_and_stop_wait_is_bounded(
    inputs: workflow.Inputs,
    phase_config: TestConfig,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHASE1_SCENARIO", "cancel-after-claim")
    inputs = workflow.Inputs.environment()
    base, starts = fake_api(inputs, phase_config, main_status="Running")
    stops = []

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        if resource:
            return query_response(
                inputs,
                query_execution(body),
                [{"event": "phase1_checkpoint", "stage": "claim_committed"}],
            )
        return base(url, body=body, resource=resource)

    def stop(args: list[str], *, timeout: float = 60) -> str:
        stops.append(timeout)
        clock.sleep(20)
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(workflow, "api", api)
    monkeypatch.setattr(workflow, "command", stop)
    for operation in ("run", "cleanup"):
        monkeypatch.setattr("sys.argv", ["phase1_workflow.py", operation])
        with pytest.raises(SystemExit):
            workflow.main()
    receipt = json.loads(inputs.report_path.read_text())
    assert stops == [60] and starts == ["run"] and clock.elapsed == 110
    assert receipt["category"] == "phase1_stop_timeout"
    assert receipt["cleanup_category"] == "phase1_execution_stop_not_verified"


def test_exact_stop_cap_includes_status_and_mutation_time(
    inputs: workflow.Inputs,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = workflow.Controller(inputs)
    workflow.save(inputs.state_path, {**controller.state, "execution": "accept-newsloom-main"})
    controller.envelope(outcome="failure", category="original_failure")
    calls = []

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        calls.append(timeout)
        clock.sleep(min(40, timeout))
        return {"properties": {"status": "Running"}}

    def stop(args: list[str], *, timeout: float = 60) -> str:
        calls.append(timeout)
        clock.sleep(40)
        return ""

    monkeypatch.setattr(workflow, "api", api)
    monkeypatch.setattr(workflow, "command", stop)
    with pytest.raises(workflow.WorkflowFailure, match="phase1_execution_stop_not_verified"):
        workflow.Controller(inputs).cleanup()
    assert clock.elapsed == 90 and calls == [60, 50, 10]


def test_read_only_query_can_recover_on_the_last_timeout_retry(
    inputs: workflow.Inputs,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def api(
        url: str, *, body: object | None = None, resource: str = "", timeout: float = 60
    ) -> dict[str, object]:
        calls.append(timeout)
        if len(calls) < 3:
            clock.sleep(timeout)
            raise subprocess.TimeoutExpired(["az"], timeout)
        return {"tables": []}

    monkeypatch.setattr(workflow, "api", api)
    assert workflow.Controller(inputs).request("https://api.loganalytics.azure.com", "query") == {
        "tables": []
    }
    assert calls == [60, 60, 60] and clock.elapsed == 130


def test_request_preparation_cannot_start_a_command_after_expiration(
    inputs: workflow.Inputs,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock.sleep(1679)
    dump = json.dump

    def slow_dump(value: object, stream: IO[str]) -> None:
        dump(value, stream)
        clock.sleep(2)

    monkeypatch.setattr(json, "dump", slow_dump)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("late command"))
    with pytest.raises(workflow.WorkflowFailure, match="phase1_workflow_deadline"):
        workflow.Controller(inputs).request(
            "https://api.loganalytics.azure.com", "query", body={"query": "content-free"}
        )


def test_first_workflow_step_generates_the_fixed_utc_deadline(tmp_path: Path) -> None:
    text = Path(".github/workflows/phase1-acceptance.yml").read_text()
    assert text.index("Establish the shared acceptance deadline") < text.index(
        "uses: actions/checkout"
    )
    program = textwrap.dedent(text.split("run: |\n", 1)[1].split("      - uses:", 1)[0])
    destination = tmp_path / "environment"
    subprocess.run(
        [sys.executable, "-c", program],
        env={"GITHUB_ENV": str(destination)},
        check=True,
        capture_output=True,
        timeout=5,
    )
    values = dict(line.split("=", 1) for line in destination.read_text().splitlines())
    start = datetime.fromisoformat(values["PHASE1_WORKFLOW_STARTED_AT"])
    end = datetime.fromisoformat(values["PHASE1_WORKFLOW_DEADLINE"])
    assert start.utcoffset() == end.utcoffset() == timedelta(0)
    assert end - start == timedelta(seconds=1680)
    assert "timeout-minutes: 30" in text
