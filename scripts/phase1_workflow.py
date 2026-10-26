"""Manual OIDC launcher; never provisions resources or accepts arbitrary commands."""

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Never
from uuid import UUID

from newsloom_core.phase1_contracts import (
    AcceptanceFailure,
    Report,
    Scenario,
    TestConfig,
    WorkflowReceipt,
    database_name,
)
from pydantic import TypeAdapter, ValidationError

API = "2025-07-01"
TERMINAL = {"Succeeded", "Failed", "Stopped", "Canceled"}
LOG_COLUMNS = [
    {"name": "JobName", "type": "string"},
    {"name": "EnvironmentName", "type": "string"},
    {"name": "ContainerGroupName", "type": "string"},
    {"name": "ContainerName", "type": "string"},
    {"name": "TimeGenerated", "type": "datetime"},
    {"name": "Log", "type": "string"},
]


class WorkflowFailure(Exception):
    pass


def object_value(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise WorkflowFailure("invalid_phase1_api_object")
    return dict(value)


def command(arguments: list[str], *, timeout: int = 60) -> str:
    result = subprocess.run(
        ["az", *arguments, "--only-show-errors"],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode:
        raise WorkflowFailure("phase1_azure_command_failed")
    if len(result.stdout) > 262144:
        raise WorkflowFailure("phase1_command_response_limit")
    return result.stdout.strip()


def api(url: str, *, body: object | None = None, resource: str = "") -> dict[str, object]:
    arguments = ["rest", "--url", url, "--output", "json"]
    if resource:
        arguments.extend(["--resource", resource])
    if body is None:
        output = command(arguments)
    else:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as current:
            json.dump(body, current)
            current.flush()
            output = command([*arguments, "--method", "post", "--body", "@" + current.name])
    return object_value(json.loads(output))


@dataclass(frozen=True)
class Inputs:
    run_id: str
    scenario: Scenario
    job_id: str
    image: str
    image_revision: str
    fixture_revision: str
    schema_revision: str
    model_revision: str
    workflow_sha: str
    temporary: Path
    client_id: UUID
    log_workspace_id: UUID
    log_environment: str

    @classmethod
    def environment(cls) -> Inputs:
        env = os.environ
        if (
            env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or env.get("GITHUB_REF") != "refs/heads/main"
            or env.get("GITHUB_REPOSITORY") != "ikhemissi/newsloom"
        ):
            raise WorkflowFailure("untrusted_phase1_workflow_context")
        run_id = env["PHASE1_RUN_ID"]
        database_name(run_id)
        scenario = TypeAdapter(Scenario).validate_python(env["PHASE1_SCENARIO"])
        job = env["PHASE1_JOB_ID"]
        match = re.fullmatch(
            r"/subscriptions/([^/]+)/resourceGroups/([a-zA-Z0-9_.()-]+)/providers/"
            r"Microsoft\.App/jobs/(accept-newsloom-[a-z0-9-]+)",
            job,
        )
        if match is None or UUID(match[1]) != UUID(env["AZURE_SUBSCRIPTION_ID"]):
            raise WorkflowFailure("unapproved_phase1_job_target")
        image = env["PHASE1_IMAGE"]
        if not re.fullmatch(r"[a-z0-9]+\.azurecr\.io/newsloom-phase1@sha256:[a-f0-9]{64}", image):
            raise WorkflowFailure("invalid_phase1_workflow_image")
        fingerprints = [
            env["PHASE1_" + field + "_REVISION"]
            for field in ("IMAGE", "FIXTURE", "SCHEMA", "MODEL")
        ]
        if any(not re.fullmatch(r"[a-f0-9]{64}", item) for item in fingerprints):
            raise WorkflowFailure("invalid_phase1_workflow_revision")
        if not re.fullmatch(r"[a-f0-9]{40}", env["GITHUB_SHA"]):
            raise WorkflowFailure("invalid_phase1_workflow_sha")
        log_environment = env["PHASE1_LOG_ENVIRONMENT"]
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", log_environment):
            raise WorkflowFailure("invalid_phase1_log_environment")
        return cls(
            run_id=run_id,
            scenario=scenario,
            job_id=job,
            image=image,
            image_revision=fingerprints[0],
            fixture_revision=fingerprints[1],
            schema_revision=fingerprints[2],
            model_revision=fingerprints[3],
            workflow_sha=env["GITHUB_SHA"],
            temporary=Path(env["RUNNER_TEMP"]),
            client_id=UUID(env["PHASE1_CLIENT_ID"]),
            log_workspace_id=UUID(env["PHASE1_LOG_WORKSPACE_ID"]),
            log_environment=log_environment,
        )

    @property
    def state_path(self) -> Path:
        return self.temporary / "newsloom-phase1-execution.json"

    @property
    def report_path(self) -> Path:
        return self.temporary / "newsloom-phase1-report.json"

    @property
    def group(self) -> str:
        return self.job_id.split("/")[4]

    @property
    def job_name(self) -> str:
        return self.job_id.rsplit("/", 1)[1]


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as current:
        json.dump(value, current, indent=2, allow_nan=False)
        current.write("\n")
    path.chmod(0o600)


def log_records(output: str) -> list[dict[str, object]]:
    records = []
    for line in output.splitlines():
        start = line.find("{")
        if start < 0:
            continue
        try:
            value: object = json.loads(line[start:])
            if isinstance(value, dict) and isinstance(value.get("Log"), str):
                value = json.loads(value["Log"])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(object_value(value))
    return records


class Controller:
    def __init__(self, inputs: Inputs) -> None:
        self.inputs = inputs
        self.base = "https://management.azure.com" + inputs.job_id
        self.state: dict[str, object] = {
            "run_id": inputs.run_id,
            "scenario": inputs.scenario,
            "job_id": inputs.job_id,
            "image": inputs.image,
            "log_workspace_id": str(inputs.log_workspace_id),
            "log_environment": inputs.log_environment,
        }
        self.receipt: WorkflowReceipt | None = None

    def template(self) -> dict[str, object]:
        row = api(self.base + "?api-version=" + API)
        if str(row.get("id", "")).casefold() != self.inputs.job_id.casefold():
            raise WorkflowFailure("phase1_job_identity_mismatch")
        properties = object_value(row.get("properties"))
        expected_environment = self.inputs.job_id.split("/providers/")[0] + (
            "/providers/Microsoft.App/managedEnvironments/cae-"
            + self.inputs.job_name.removeprefix("accept-")
        )
        if str(properties.get("environmentId", "")).casefold() != expected_environment.casefold():
            raise WorkflowFailure("phase1_job_environment_mismatch")
        if object_value(properties.get("configuration")).get("triggerType") != "Manual":
            raise WorkflowFailure("phase1_job_not_manual")
        template = object_value(properties.get("template"))
        containers = template.get("containers")
        if (
            template.get("initContainers") not in (None, [])
            or template.get("volumes") not in (None, [])
            or not isinstance(containers, list)
            or len(containers) != 1
        ):
            raise WorkflowFailure("phase1_job_template_mismatch")
        container = object_value(containers[0])
        if (
            container.get("name") != "acceptance"
            or container.get("image") != self.inputs.image
            or container.get("command") not in (None, [])
        ):
            raise WorkflowFailure("phase1_job_image_mismatch")
        values = container.get("env")
        if not isinstance(values, list):
            raise WorkflowFailure("phase1_job_configuration_missing")
        settings = {}
        for value in values:
            field = object_value(value)
            if field.get("secretRef") not in (None, ""):
                raise WorkflowFailure("phase1_unexpected_job_secret")
            settings[str(field.get("name"))] = field.get("value")
        encoded = settings.get("PHASE1_CONFIG_BASE64")
        if not isinstance(encoded, str):
            raise WorkflowFailure("phase1_job_configuration_missing")
        config = TestConfig.from_encoded(encoded, self.inputs.run_id)
        if (
            config.image_revision != self.inputs.image_revision
            or config.model_revision() != self.inputs.model_revision
            or config.client_id != self.inputs.client_id
        ):
            raise WorkflowFailure("phase1_job_revision_mismatch")
        identity = object_value(row.get("identity"))
        assigned = object_value(identity.get("userAssignedIdentities"))
        expected_identity = self.inputs.job_id.split("/providers/")[0] + (
            "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/phase1-"
            + self.inputs.job_name.removeprefix("accept-")
        )
        if len(assigned) != 1 or {name.casefold() for name in assigned} != {
            expected_identity.casefold()
        }:
            raise WorkflowFailure("phase1_job_workload_identity_mismatch")
        details = object_value(next(iter(assigned.values())))
        if details.get("clientId") != str(config.client_id) or details.get("principalId") != str(
            config.principal_id
        ):
            raise WorkflowFailure("phase1_job_workload_identity_mismatch")
        return container

    def start(self, *, cleanup: bool = False) -> str:
        container = self.template()
        execution: dict[str, object] = {
            key: container[key] for key in ("name", "image", "resources", "env") if key in container
        }
        arguments = ["cleanup" if cleanup else "run", "--run-id", self.inputs.run_id]
        if not cleanup:
            arguments += ["--scenario", self.inputs.scenario]
        execution["args"] = arguments
        self.state["run_id"] = self.inputs.run_id
        self.state["cleanup_started_at" if cleanup else "execution_started_at"] = datetime.now(
            UTC
        ).isoformat()
        save(self.inputs.state_path, self.state)
        row = api(self.base + "/start?api-version=" + API, body={"containers": [execution]})
        name = row.get("name")
        if not isinstance(name, str) or not re.fullmatch(
            re.escape(self.inputs.job_name) + r"-[a-z0-9]{1,20}", name
        ):
            raise WorkflowFailure("phase1_execution_name_invalid")
        self.state["cleanup_execution" if cleanup else "execution"] = name
        save(self.inputs.state_path, self.state)
        return name

    def status(self, execution: str) -> str:
        row = api(self.base + "/executions/" + execution + "?api-version=" + API)
        result = object_value(row.get("properties")).get("status")
        if not isinstance(result, str) or result not in TERMINAL | {
            "Processing",
            "Running",
            "Unknown",
        }:
            raise WorkflowFailure("unknown_phase1_execution_status")
        return str(result)

    def logs(self, execution: str) -> list[dict[str, object]]:
        if not re.fullmatch(re.escape(self.inputs.job_name) + r"-[a-z0-9]{1,20}", execution):
            raise WorkflowFailure("phase1_log_execution_mismatch")
        if self.state.get("execution") == execution:
            start = self.state.get("execution_started_at")
        elif self.state.get("cleanup_execution") == execution:
            start = self.state.get("cleanup_started_at")
        else:
            raise WorkflowFailure("phase1_log_execution_mismatch")
        if not isinstance(start, str):
            raise WorkflowFailure("phase1_log_start_missing")
        started_at = datetime.fromisoformat(start)
        now = datetime.now(UTC)
        if started_at.tzinfo is None or started_at > now or now - started_at > timedelta(hours=2):
            raise WorkflowFailure("phase1_log_time_window_invalid")
        lower_bound = started_at - timedelta(minutes=1)
        upper_bound = now + timedelta(minutes=1)
        expression = (
            "ContainerAppConsoleLogs "
            f"| where TimeGenerated between (datetime({lower_bound.isoformat()}) "
            f".. datetime({upper_bound.isoformat()})) "
            f"| where JobName == '{self.inputs.job_name}' "
            f"and EnvironmentName == '{self.inputs.log_environment}' "
            "and ContainerName == 'acceptance' "
            f"and ContainerGroupName startswith '{execution}-' "
            "| project JobName, EnvironmentName, ContainerGroupName, ContainerName, "
            "TimeGenerated, Log | take 301"
        )
        response = api(
            f"https://api.loganalytics.azure.com/v1/workspaces/{self.inputs.log_workspace_id}/query",
            body={"query": expression},
            resource="https://api.loganalytics.io",
        )
        tables = response.get("tables")
        if "error" in response or not isinstance(tables, list) or len(tables) != 1:
            raise WorkflowFailure("phase1_log_query_incomplete")
        table = object_value(tables[0])
        rows = table.get("rows")
        if table.get("columns") != LOG_COLUMNS or not isinstance(rows, list) or len(rows) > 300:
            raise WorkflowFailure("phase1_log_query_shape_invalid")
        records = []
        for row in rows:
            if (
                not isinstance(row, list)
                or len(row) != 6
                or any(not isinstance(value, str) for value in row)
            ):
                raise WorkflowFailure("phase1_log_record_shape_invalid")
            job_name, environment, replica, container, timestamp, message = row
            observed_at = datetime.fromisoformat(timestamp)
            if (
                job_name != self.inputs.job_name
                or environment != self.inputs.log_environment
                or not re.fullmatch(re.escape(execution) + r"-[a-z0-9]{1,20}", replica)
                or container != "acceptance"
                or observed_at.tzinfo is None
                or not lower_bound <= observed_at <= upper_bound
                or len(message) > 32768
            ):
                raise WorkflowFailure("phase1_log_record_metadata_mismatch")
            records.extend(log_records(message))
        return records

    def stop(self, execution: str) -> None:
        command(
            [
                "containerapp",
                "job",
                "stop",
                "--name",
                self.inputs.job_name,
                "--resource-group",
                self.inputs.group,
                "--job-execution-name",
                execution,
                "--output",
                "json",
            ]
        )

    def report(self, value: dict[str, object]) -> Report:
        report = Report.model_validate(value)
        if (
            report.run_id != self.inputs.run_id
            or report.scenario != self.inputs.scenario
            or report.fixture_revision != self.inputs.fixture_revision
            or report.schema_revision != self.inputs.schema_revision
            or report.model_revision != self.inputs.model_revision
            or report.image_revision != self.inputs.image_revision
        ):
            raise WorkflowFailure("phase1_report_revision_mismatch")
        return report

    def envelope(
        self,
        *,
        outcome: Literal["success", "failure"],
        category: str = "",
        report: Report | None = None,
    ) -> None:
        self.receipt = WorkflowReceipt(
            outcome=outcome,
            category=category,
            workflow_sha=self.inputs.workflow_sha,
            run_id=self.inputs.run_id,
            scenario=self.inputs.scenario,
            report=report,
            cleanup_verified=bool(report and any(item.name == "cleanup" for item in report.stages)),
        )
        save(self.inputs.report_path, self.receipt.model_dump(mode="json"))

    def failure(self, category: str, *, cleanup: bool) -> None:
        old = self.receipt
        self.receipt = WorkflowReceipt(
            outcome="failure",
            category=old.category if old is not None and old.outcome == "failure" else category,
            cleanup_category=category if cleanup else "",
            workflow_sha=self.inputs.workflow_sha,
            run_id=self.inputs.run_id,
            scenario=self.inputs.scenario,
            report=old.report if old else None,
            cleanup_verified=old.cleanup_verified if old is not None and not cleanup else False,
        )
        save(self.inputs.report_path, self.receipt.model_dump(mode="json"))

    def run(self) -> None:
        if self.inputs.state_path.exists() or self.inputs.report_path.exists():
            raise WorkflowFailure("phase1_execution_state_already_exists")
        execution = self.start()
        deadline = time.monotonic() + 1260
        terminal_deadline = deadline
        report = None
        while time.monotonic() < deadline:
            status = self.status(execution)
            if status in ("Processing", "Unknown"):
                time.sleep(5)
                continue
            records = self.logs(execution)
            if self.inputs.scenario == "cancel-after-claim" and any(
                row.get("event") == "phase1_checkpoint" and row.get("stage") == "claim_committed"
                for row in records
            ):
                self.stop(execution)
                raise WorkflowFailure("intentional_phase1_cancellation_drill")
            reports = [
                self.report(row)
                for row in records
                if row.get("event") == "phase1_acceptance_report"
            ]
            if len(reports) > 1:
                raise WorkflowFailure("duplicate_phase1_execution_report")
            if reports:
                report = reports[0]
            if status in TERMINAL:
                if report is None:
                    terminal_deadline = min(terminal_deadline, time.monotonic() + 240)
                    if time.monotonic() >= terminal_deadline:
                        raise WorkflowFailure("phase1_execution_report_missing")
                    time.sleep(5)
                    continue
                if status != "Succeeded" or report.outcome != "success":
                    self.envelope(outcome="failure", category=report.category, report=report)
                    raise WorkflowFailure("phase1_execution_failed")
                self.envelope(outcome="success", report=report)
                return
            time.sleep(5)
        raise WorkflowFailure("phase1_execution_deadline")

    def cleanup(self) -> None:
        if not self.inputs.state_path.is_file():
            raise WorkflowFailure("phase1_cleanup_needs_operator")
        state = object_value(json.loads(self.inputs.state_path.read_text()))
        if any(state.get(key) != value for key, value in self.state.items()):
            raise WorkflowFailure("phase1_cleanup_state_mismatch")
        self.state = state
        if self.inputs.report_path.is_file():
            receipt = WorkflowReceipt.model_validate_json(self.inputs.report_path.read_bytes())
            if (
                receipt.run_id != self.inputs.run_id
                or receipt.scenario != self.inputs.scenario
                or receipt.workflow_sha != self.inputs.workflow_sha
            ):
                raise WorkflowFailure("stale_phase1_workflow_receipt")
            self.receipt = receipt
        else:
            self.envelope(outcome="failure", category="phase1_main_execution_incomplete")
        execution = state.get("execution")
        if isinstance(execution, str):
            if not re.fullmatch(r"[a-z0-9-]{1,80}", execution):
                raise WorkflowFailure("phase1_cleanup_execution_mismatch")
            if self.status(execution) not in TERMINAL:
                self.stop(execution)
                deadline = time.monotonic() + 90
                while self.status(execution) not in TERMINAL:
                    if time.monotonic() >= deadline:
                        raise WorkflowFailure("phase1_execution_stop_not_verified")
                    time.sleep(2)
        execution = self.start(cleanup=True)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            status = self.status(execution)
            if status in TERMINAL:
                records = self.logs(execution)
                cleaned = [row for row in records if row.get("event") == "phase1_cleanup"]
                if not cleaned:
                    time.sleep(5)
                    continue
                if (
                    status != "Succeeded"
                    or len(cleaned) != 1
                    or cleaned[0].get("run_id") != self.inputs.run_id
                    or type(cleaned[0].get("absent")) is not int
                    or cleaned[0]["absent"] != 1
                ):
                    raise WorkflowFailure("phase1_cleanup_not_verified")
                if self.receipt is None:
                    raise WorkflowFailure("phase1_workflow_receipt_missing")
                self.receipt = WorkflowReceipt.model_validate(
                    {
                        **self.receipt.model_dump(),
                        "cleanup_verified": True,
                    }
                )
                save(self.inputs.report_path, self.receipt.model_dump(mode="json"))
                return
            time.sleep(5)
        raise WorkflowFailure("phase1_cleanup_deadline")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise WorkflowFailure("invalid_phase1_launcher_arguments")


def main() -> None:
    controller = None
    operation = "run"
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("command", choices=["run", "cleanup"])
        args = parser.parse_args()
        operation = args.command
        controller = Controller(Inputs.environment())
        if args.command == "run":
            controller.run()
        else:
            controller.cleanup()
        print(
            json.dumps(
                {"event": "phase1_launcher", "outcome": "success", "operation": args.command}
            )
        )
    except (
        WorkflowFailure,
        AcceptanceFailure,
        ValidationError,
        KeyError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        category = (
            str(error)
            if isinstance(error, (WorkflowFailure, AcceptanceFailure))
            else "phase1_launcher_input_or_api_error"
        )
        if controller is not None:
            controller.failure(category, cleanup=operation == "cleanup")
        print(json.dumps({"event": "phase1_launcher", "outcome": "failure", "category": category}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
