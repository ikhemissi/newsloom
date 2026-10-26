import base64
import json
from pathlib import Path

import pytest
from newsloom_core.phase1_contracts import TestConfig, fixture_revision
from newsloom_platform import control
from newsloom_platform.config import PlatformFailure
from newsloom_platform.phase1_database import schema_revision
from test_phase1_contracts import phase_config as phase_config


@pytest.mark.parametrize("cleanup", [False, True])
def test_admin_preparation_and_recovery_target_only_the_explicit_run(
    cleanup: bool,
    phase_config: TestConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = phase_config
    env = {
        "PHASE1_RUN_ID": cfg.run_id,
        "PHASE1_PRINCIPAL_ID": str(cfg.principal_id),
        "PHASE1_CLIENT_ID": str(cfg.client_id),
        "POSTGRES_HOST": cfg.postgres_host,
        "MODEL_ENDPOINT": cfg.model_endpoint,
        "ENRICHMENT_DEPLOYMENT": cfg.generation_deployment,
        "ENRICHMENT_MODEL": cfg.generation_model,
        "ENRICHMENT_VERSION": cfg.generation_version,
        "EMBEDDINGS_DEPLOYMENT": cfg.embedding_deployment,
        "EMBEDDINGS_MODEL": cfg.embedding_model,
        "EMBEDDINGS_VERSION": cfg.embedding_version,
        "SCREENING_DEPLOYMENT": cfg.screening_deployment,
        "SCREENING_MODEL": cfg.screening_model,
        "SCREENING_VERSION": cfg.screening_version,
        "SCANNER_THRESHOLD": str(cfg.scanner_threshold),
        "SCANNER_CALIBRATION_ID": cfg.scanner_calibration_id,
        "PHASE1_IMAGE_REVISION": cfg.image_revision,
        "MIGRATION_JOB_ID": "migration-job",
    }
    calls = []
    updates: dict[str, str] = {}

    def execute(
        job: str,
        correlation: str,
        *,
        arguments: list[str] | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> str:
        assert job == "migration-job" and correlation == cfg.run_id
        assert extra_environment is not None and set(extra_environment) == {"PHASE1_CONFIG_BASE64"}
        assert (
            TestConfig.from_encoded(extra_environment["PHASE1_CONFIG_BASE64"], correlation) == cfg
        )
        values = json.loads(base64.b64decode(extra_environment["PHASE1_CONFIG_BASE64"]))
        assert "run_id" not in values and "database" not in values
        calls.append(arguments)
        return "phase1-execution"

    monkeypatch.setattr(control, "environment", lambda: env)
    monkeypatch.setattr(control, "execute_job", execute)
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    control.control(
        "cleanup-phase1-acceptance" if cleanup else "prepare-phase1-acceptance", cfg.run_id
    )
    assert calls == [["phase1-cleanup" if cleanup else "phase1-prepare"]]
    assert updates == {
        "PHASE1_RUN_ID": cfg.run_id,
        "PHASE1_ADMIN_LAST_EXECUTION": "phase1-execution",
        "PHASE1_FIXTURE_REVISION": fixture_revision(),
        "PHASE1_SCHEMA_REVISION": schema_revision(),
        "PHASE1_MODEL_REVISION": cfg.model_revision(),
    }


def test_shared_execution_helper_cannot_override_a_production_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args: object, **kwargs: object) -> object:
        raise AssertionError("unsafe_override_reached_azure")

    monkeypatch.setattr(control, "rest", unexpected)
    with pytest.raises(PlatformFailure, match="unsafe_execution_environment_override"):
        control.execute_job(
            "migration-job", "run", extra_environment={"AZURE_CLIENT_ID": "untrusted"}
        )


def test_acceptance_assets_are_part_of_immutable_build_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("pyproject.toml", "uv.lock", "README.md", ".dockerignore"):
        (tmp_path / name).write_text(name)
    files = (
        "config/phase1-acceptance.json",
        "tests/azure/Dockerfile",
        "tests/azure/phase1_acceptance/run.py",
    )
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("first")
    monkeypatch.setattr(control, "run", lambda arguments, category: "\0".join(files) + "\0")
    first = control.source_hash(tmp_path)
    for name in files:
        path = tmp_path / name
        path.write_text("second")
        second = control.source_hash(tmp_path)
        assert second != first
        first = second


def test_layer_default_is_disabled_without_building_or_changing_existing_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: dict[str, str] = {}
    monkeypatch.setattr(control, "environment", lambda: {"MCP_IMAGE": "existing-image"})
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("disabled_layer_attempted_build")

    monkeypatch.setattr(control, "build", unexpected)
    control.control("prepare-phase1-layer", "test")
    assert updates == {"PHASE1_ENABLED": "false", "PHASE1_IMAGE": "", "PHASE1_IMAGE_REVISION": ""}


@pytest.mark.parametrize(
    "fault",
    [
        "",
        "conflict",
        "missing",
        "readback",
        "workspace_conflict",
        "workspace_missing",
        "environment_conflict",
        "environment_mismatch",
        "invalid_environment",
    ],
)
def test_github_repository_settings_are_private_verified_and_never_blindly_overwritten(
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {
        key: "a" * 64
        for key in (
            "PHASE1_CLIENT_ID",
            "PHASE1_JOB_ID",
            "PHASE1_IMAGE",
            "PHASE1_IMAGE_REVISION",
            "PHASE1_FIXTURE_REVISION",
            "PHASE1_SCHEMA_REVISION",
            "PHASE1_MODEL_REVISION",
            "AZURE_SUBSCRIPTION_ID",
        )
    }
    env["LOG_ANALYTICS_WORKSPACE_ID"] = "private-workspace"
    env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"] = "existing-environment"
    if fault == "missing":
        env["PHASE1_JOB_ID"] = ""
    if fault == "workspace_missing":
        env["LOG_ANALYTICS_WORKSPACE_ID"] = ""
    created: dict[str, str] = {}

    def azure(arguments: list[str], *args: object, **kwargs: object) -> object:
        if arguments[:3] == ["containerapp", "env", "show"]:
            return {
                "id": "foreign-environment"
                if fault == "environment_mismatch"
                else env["AZURE_CONTAINER_APPS_ENVIRONMENT_ID"],
                "properties": {
                    "defaultDomain": "untrusted' domain"
                    if fault == "invalid_environment"
                    else "synthetic-environment.francecentral.azurecontainerapps.io"
                },
            }
        return "synthetic-tenant"

    monkeypatch.setattr(control, "azure", azure)
    lists = 0

    def run(arguments: list[str], category: str, **kwargs: object) -> str:
        nonlocal lists
        assert arguments[:2] == ["gh", "variable"] and "ikhemissi/newsloom" in arguments
        if arguments[2] == "list":
            lists += 1
            if fault == "conflict" and lists == 1:
                return json.dumps([{"name": "PHASE1_JOB_ID", "value": "foreign-existing"}])
            if fault == "workspace_conflict" and lists == 1:
                return json.dumps(
                    [{"name": "PHASE1_LOG_WORKSPACE_ID", "value": "foreign-existing"}]
                )
            if fault == "environment_conflict" and lists == 1:
                return json.dumps([{"name": "PHASE1_LOG_ENVIRONMENT", "value": "foreign-existing"}])
            if fault == "readback" and lists > 1:
                return "[]"
            return json.dumps(
                [
                    {"name": "UNRELATED", "value": "NEWSLOOM_CREDENTIAL_CANARY"},
                    *({"name": key, "value": value} for key, value in created.items()),
                ]
            )
        assert arguments[2] == "set"
        created[arguments[3]] = arguments[arguments.index("--body") + 1]
        return ""

    monkeypatch.setattr(control, "run", run)
    if fault:
        with pytest.raises(PlatformFailure):
            control.configure_phase1_github(env, "test")
        if fault != "readback":
            assert not created
    else:
        control.configure_phase1_github(env, "test")
        expected = {
            key: value
            for key, value in env.items()
            if key not in ("LOG_ANALYTICS_WORKSPACE_ID", "AZURE_CONTAINER_APPS_ENVIRONMENT_ID")
        }
        expected["PHASE1_LOG_WORKSPACE_ID"] = env["LOG_ANALYTICS_WORKSPACE_ID"]
        expected["PHASE1_LOG_ENVIRONMENT"] = "synthetic-environment"
        expected["AZURE_TENANT_ID"] = "synthetic-tenant"
        assert created == expected and lists == 2
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err
    if fault:
        assert '"outcome": "success"' not in output.out
