import json
from pathlib import Path
from uuid import uuid4

import pytest
from newsloom_core.retrieval_fixtures import fixture_revision, load_fixtures
from newsloom_platform import control
from newsloom_platform.config import PlatformFailure


@pytest.mark.parametrize(
    "fault",
    [
        "",
        "prepare",
        "exec",
        "interrupt",
        "incomplete",
        "gate",
        "cleanup",
        "group",
        "case-error",
        "recall",
        "summary",
    ],
)
def test_native_replica_evaluation_cleans_schema_and_preserves_safe_case_evidence(
    fault: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = uuid4().hex
    (tmp_path / "config").mkdir()
    (tmp_path / "config/mcp-evaluation.json").write_bytes(
        Path("config/mcp-evaluation.json").read_bytes()
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".azure/test").mkdir(parents=True)
    jobs: list[list[str] | None] = []
    updates: dict[str, str] = {}

    def execute(job: str, correlation: str, *, arguments: list[str] | None = None) -> str:
        assert job == "migration-job" and correlation == run_id
        jobs.append(arguments)
        if fault == "prepare" and arguments == ["mcp-eval-prepare"]:
            raise PlatformFailure("prepare_failed")
        if fault == "cleanup" and arguments == ["mcp-eval-cleanup"]:
            raise PlatformFailure("cleanup_not_verified")
        return "test-execution"

    records = []
    for case in load_fixtures().queries:
        records.append(
            {
                "event": "mcp_evaluation_case",
                "correlation_id": run_id,
                "category": case.id,
                "counts": {
                    "group": "filtered" if fault == "group" else case.group,
                    "relevant": ",".join(case.relevant),
                    "retrieved": "" if fault == "recall" else ",".join(case.relevant),
                    "similarities": ""
                    if fault == "recall"
                    else ",".join("0.900000" for _ in case.relevant),
                    "recall_at_5": 1.0,
                    "error": "embedding_http_429" if fault == "case-error" else "",
                },
            }
        )
    records.append(
        {
            "event": "mcp_evaluation",
            "correlation_id": run_id,
            "counts": {
                "passed": 0 if fault == "gate" else 1,
                "filtered_cases": 10,
                "unfiltered_cases": 10,
                "filtered_recall_at_5": 1.0,
                "unfiltered_recall_at_5": 0.9 if fault == "summary" else 1.0,
                "filter_violations": 0,
                "errors": 0,
                "fixture_revision": fixture_revision(),
            },
        }
    )

    def run(arguments: list[str], category: str, **kwargs: object) -> str:
        if arguments[:2] == ["git", "check-ignore"]:
            return arguments[-1]
        assert arguments[:3] == ["az", "containerapp", "exec"]
        if fault == "exec":
            raise PlatformFailure("replica_exec_failed")
        if fault == "interrupt":
            raise KeyboardInterrupt()
        selected = records[1:] if fault == "incomplete" else records
        return "Connecting to replica\n" + "\n".join(json.dumps(row) for row in selected)

    monkeypatch.setattr(control, "execute_job", execute)
    monkeypatch.setattr(control, "run", run)
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    env = {
        "MIGRATION_JOB_ID": "migration-job",
        "MCP_APP_NAME": "mcp-test",
        "AZURE_RESOURCE_GROUP": "test-group",
        "AZURE_ENV_NAME": "test",
    }
    if fault == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            control.evaluate_mcp(env, run_id)
    elif fault:
        with pytest.raises(PlatformFailure):
            control.evaluate_mcp(env, run_id)
    else:
        control.evaluate_mcp(env, run_id)
        path = tmp_path / ".azure/test" / f"mcp-evaluation-{run_id}.json"
        report = json.loads(path.read_text())
        assert (
            len(report["cases"]) == 20
            and report["summary"]["fixture_revision"] == fixture_revision()
        )
        assert path.stat().st_mode & 0o777 == 0o600
    assert jobs == [["mcp-eval-prepare"], ["mcp-eval-cleanup"]]
    assert updates == {"MCP_EVALUATION_RUN_ID": run_id}
    output = capsys.readouterr().out
    if fault:
        assert '"outcome": "success"' not in output


@pytest.mark.parametrize(
    "fault",
    ["", "missing", "duplicate", "failure", "boolean", "incomplete", "count", "unsafe_error"],
)
def test_private_native_access_operator_accepts_only_complete_numeric_proof(
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    counts: dict[str, object] = {
        "tool_checks": 5,
        "database_denials": 10,
        "embedding_dimensions": 1536,
        "model_denials": 2,
        "anonymous_denials": 1,
        "wrong_resource_denials": 1,
        "app_only_denials": 3,
        "cleanup_checks": 1,
        "news": 12,
        "recent_ids": 5,
    }
    if fault == "boolean":
        counts["database_denials"] = True
    if fault == "incomplete":
        counts["model_denials"] = 1
    if fault == "count":
        counts["recent_ids"] = 2
    records = [{"event": "mcp_access_verification", "outcome": "success", "counts": counts}]
    if fault == "missing":
        records = []
    if fault == "duplicate":
        records *= 2
    if fault in ("failure", "unsafe_error"):
        records = [
            {
                "event": "mcp_service",
                "outcome": "failure",
                "category": "NEWSLOOM_CREDENTIAL_CANARY"
                if fault == "unsafe_error"
                else "verification_model_denial_not_proven",
            }
        ]
    updates: dict[str, str] = {}

    def run(arguments: list[str], category: str, **kwargs: object) -> str:
        assert arguments[:3] == ["az", "containerapp", "exec"]
        assert "verify-access" in arguments[arguments.index("--command") + 1]
        assert kwargs["timeout"] == 240
        return "native console\n" + "\n".join(json.dumps(record) for record in records)

    monkeypatch.setattr(control, "run", run)
    monkeypatch.setattr(control, "set_environment", lambda key, value: updates.update({key: value}))
    env = {
        "MCP_APP_NAME": "mcp-test",
        "AZURE_RESOURCE_GROUP": "test-group",
        "MCP_EVALUATION_RUN_ID": uuid4().hex,
        "WORKLOAD_IDENTITIES": json.dumps(
            {
                name: {
                    "id": "/test/" + name,
                    "client_id": str(uuid4()),
                    "principal_id": str(uuid4()),
                }
                for name in ("ingestion", "enrichment", "mcp", "migrations")
            }
        ),
        "POSTGRES_HOST": "test.postgres.database.azure.com",
        "POSTGRES_DATABASE": "newsloom",
        "POSTGRES_ADMIN_NAME": "admin",
        "MODEL_ENDPOINT": "https://models.test",
        "ENRICHMENT_DEPLOYMENT": "generation",
        "EMBEDDINGS_DEPLOYMENT": "embedding",
        "SCREENING_DEPLOYMENT": "screening",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "test.azurecr.io",
        "MODEL_ACCOUNT_ID": "/test/account",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "synthetic",
    }
    correlation = uuid4().hex
    if fault:
        with pytest.raises(PlatformFailure) as error:
            control.verify_mcp(env, correlation)
        assert not updates and "CANARY" not in str(error.value)
    else:
        control.verify_mcp(env, correlation)
        assert updates["MCP_ACCESS_LAST_RUN_ID"] == correlation
        assert json.loads(updates["MCP_ACCESS_LAST_COUNTS"]) == counts
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err
    if fault:
        assert '"outcome": "success"' not in captured.out
