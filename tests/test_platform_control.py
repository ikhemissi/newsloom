import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg
import pytest
from newsloom_platform import cli, control
from newsloom_platform.config import PlatformFailure
from newsloom_platform.probe import credential_rejected, require_denied


@pytest.mark.parametrize("status", [200, 400, 404, 429, 500])
def test_failed_or_invalid_requests_do_not_prove_denied_access(status: int) -> None:
    with pytest.raises(PlatformFailure, match="denial_not_proven"):
        require_denied(httpx.Response(status))


@pytest.mark.parametrize("status", [401, 403])
def test_actual_authorization_denial(status: int) -> None:
    require_denied(httpx.Response(status))


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('connection failed: FATAL:  password authentication failed for user "probe"', True),
        ("connection failed: FATAL:  The access token is invalid.", True),
        ("connection failed: FATAL:  Invalid token format", True),
        ("connection failed: FATAL:  JWT token is invalid.", True),
        ("FATAL: authentication failed: access token has invalid format", True),
        ("FATAL: authentication failed: access token is in an invalid format", True),
        ('connection failed: FATAL: password authentication failed for user "other"', False),
        ("connection timed out", False),
        ("SSL error: certificate verify failed", False),
        ("connection failed: FATAL: database is starting up", False),
        ("token validation service unavailable", False),
        ("FATAL: token service certificate has invalid format", False),
    ],
)
def test_only_explicit_server_authentication_errors_prove_credential_rejection(
    message: str, expected: bool
) -> None:
    assert credential_rejected(psycopg.OperationalError(message), "probe") is expected


def test_command_failure_does_not_print_upstream_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 1, "", "CONTENT_CREDENTIAL_CANARY")

    monkeypatch.setattr(subprocess, "run", failed_run)
    with pytest.raises(PlatformFailure, match=r"^command_failed_build$"):
        control.run(["az", "acr", "build"], "build")


def test_invalid_command_response_identifies_stage_without_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(control, "run", lambda *args, **kwargs: "CONTENT_CREDENTIAL_CANARY")
    with pytest.raises(PlatformFailure, match=r"^invalid_command_response_image_build$"):
        control.azure(["acr", "build"], "image_build")


def test_service_exception_is_reported_without_content(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fail_runtime(command: str, workload: str, correlation: str) -> None:
        raise httpx.HTTPStatusError(
            "CONTENT_CREDENTIAL_CANARY",
            request=httpx.Request("POST", "https://test.invalid"),
            response=httpx.Response(500),
        )

    monkeypatch.setattr(cli, "runtime", fail_runtime)
    monkeypatch.setattr(sys, "argv", ["newsloom-platform", "probe", "mcp"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 1
    output = capsys.readouterr().out
    assert "CONTENT_CREDENTIAL_CANARY" not in output
    assert json.loads(output)["category"] == "HTTPStatusError"


def job_environment() -> dict[str, str]:
    parent = "/subscriptions/test/resourceGroups/application/providers/Microsoft.App/jobs/"
    return {
        "MIGRATION_JOB_ID": parent + "migrate-newsloom-test",
        "PLATFORM_VERIFICATION_JOBS": json.dumps(
            {
                name: parent + f"verify-newsloom-test-{name}"
                for name in ["ingestion", "enrichment", "mcp", "migrations"]
            }
        ),
    }


@pytest.mark.parametrize(
    "replacement",
    [
        "/subscriptions/test/resourceGroups/state/providers/Microsoft.Storage/storageAccounts/state",
        "/subscriptions/test/resourceGroups/application/providers/Microsoft.App/jobs/migrate-newsloom-test",
        "/subscriptions/test/resourceGroups/other/providers/Microsoft.App/jobs/verify-other",
        "/subscriptions/test/resourceGroups/application/providers/Microsoft.App/jobs/verify-escape/../verify-test-mcp",
    ],
)
def test_cleanup_allowlist_rejects_shared_or_foreign_resources(replacement: str) -> None:
    env = job_environment()
    jobs = json.loads(env["PLATFORM_VERIFICATION_JOBS"])
    jobs["mcp"] = replacement
    env["PLATFORM_VERIFICATION_JOBS"] = json.dumps(jobs)
    with pytest.raises(PlatformFailure, match="unsafe_verification_job_scope"):
        control.temporary_jobs(env)


def test_cleanup_inventory_has_exactly_the_four_temporary_jobs() -> None:
    assert set(control.temporary_jobs(job_environment())) == {
        "ingestion",
        "enrichment",
        "mcp",
        "migrations",
    }


@pytest.mark.parametrize("terminal", ["Failed", "Stopped", "Canceled"])
def test_failed_execution_cannot_report_success(
    terminal: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    results: list[object] = [
        {"properties": {"template": {"containers": [{"env": []}]}}},
        {"name": "verify-test-execution"},
        {"properties": {"status": terminal}},
    ]

    def fake_rest(url: str, category: str, **kwargs: object) -> object:
        return results.pop(0)

    monkeypatch.setattr(control, "rest", fake_rest)
    with pytest.raises(PlatformFailure, match="execution_failed_verify-test-execution"):
        control.execute_job("/test/job", "synthetic-correlation")


def test_image_source_hash_is_stable_and_tracks_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ["pyproject.toml", "uv.lock", "README.md", ".dockerignore"]:
        (tmp_path / name).write_text(name)
    source = tmp_path / "services/platform/source.py"
    source.parent.mkdir(parents=True)
    source.write_text("first")
    monkeypatch.setattr(control, "run", lambda arguments, category: "services/platform/source.py\0")
    first = control.source_hash(tmp_path)
    monkeypatch.chdir(source.parent)
    assert first == control.source_hash(tmp_path)
    source.write_text("second")
    assert first != control.source_hash(tmp_path)


def test_failed_build_never_sets_an_image(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: list[object] = [[], {"runId": "synthetic-build", "status": "Failed"}]
    updates: list[tuple[str, str]] = []
    monkeypatch.setattr(control, "run", lambda arguments, category: str(Path.cwd()))
    monkeypatch.setattr(control, "source_hash", lambda root: "a" * 64)
    monkeypatch.setattr(control, "azure", lambda arguments, category, **kwargs: responses.pop(0))
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.append((key, value)))
    with pytest.raises(PlatformFailure, match="image_build_failed_synthetic-build"):
        control.build(
            {
                "AZURE_CONTAINER_REGISTRY_NAME": "test",
                "AZURE_CONTAINER_REGISTRY_ENDPOINT": "test.azurecr.io",
            },
            "synthetic-correlation",
        )
    assert not updates


def test_running_execution_times_out_at_its_exact_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[object] = [
        {"properties": {"template": {"containers": [{"env": []}]}}},
        {"name": "verify-test-execution"},
        {"properties": {"status": "Running"}},
        {"properties": {"status": "Running"}},
    ]
    clock = iter([100.0, 1059.9, 1060.0])
    monkeypatch.setattr(control, "rest", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    with pytest.raises(PlatformFailure, match="execution_failed_verify-test-execution"):
        control.execute_job("/test/job", "synthetic-correlation")
    assert not responses


def test_execution_override_uses_only_start_contract_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_rest(url: str, category: str, **kwargs: object) -> object:
        if category == "job_definition":
            return {
                "properties": {
                    "template": {
                        "volumes": [],
                        "initContainers": [],
                        "containers": [{"name": "platform", "probes": [], "env": []}],
                    }
                }
            }
        if category == "job_start":
            assert kwargs["body"] == {
                "containers": [
                    {
                        "name": "platform",
                        "env": [{"name": "PLATFORM_PROBE_RUN_ID", "value": "correlation"}],
                    }
                ]
            }
            return {"name": "test-execution"}
        return {"properties": {"status": "Succeeded"}}

    monkeypatch.setattr(control, "rest", fake_rest)
    assert control.execute_job("/test/job", "correlation") == "test-execution"
