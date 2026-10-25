import base64
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
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


@pytest.mark.parametrize("fault", ["image", "identity", "client", "schedule"])
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


def fake_api(
    inputs: workflow.Inputs,
    config: TestConfig,
    *,
    main_status: str = "Succeeded",
) -> tuple[Callable[..., dict[str, object]], list[str]]:
    starts: list[str] = []

    def api(url: str, *, body: object | None = None) -> dict[str, object]:
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

    def command(arguments: list[str], **kwargs: object) -> str:
        assert arguments[:4] == ["containerapp", "job", "logs", "show"]
        assert arguments[arguments.index("--resource-group") + 1] == "rg-newsloom-test"
        execution = arguments[arguments.index("--execution") + 1]
        value = (
            {"event": "phase1_cleanup", "run_id": inputs.run_id, "absent": 1}
            if execution.endswith("cleanup")
            else report(inputs).model_dump(mode="json")
        )
        return json.dumps({"Log": json.dumps(value)})

    monkeypatch.setattr(workflow, "command", command)
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

    def command(*args: object, **kwargs: object) -> str:
        if fault == "log_failed":
            raise workflow.WorkflowFailure("phase1_azure_command_failed")
        if fault == "missing":
            return "no report"
        return "\n".join(json.dumps(value) for _ in range(2 if fault == "duplicate" else 1))

    monkeypatch.setattr(workflow, "command", command)
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
    monkeypatch.setattr(workflow, "command", lambda *args, **kwargs: json.dumps(value))
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

    def api(url: str, *, body: object | None = None) -> dict[str, object]:
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
        execution = arguments[arguments.index("--execution") + 1]
        if execution.endswith("cleanup"):
            return json.dumps({"event": "phase1_cleanup", "run_id": inputs.run_id, "absent": 1})
        if scenario == "cancel-after-claim":
            return json.dumps({"event": "phase1_checkpoint", "stage": "claim_committed"})
        return failure.model_dump_json()

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
