import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import baseline_evaluator_step as step
from scripts import baseline_prepare as bp

START = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    value = Clock()
    monkeypatch.setattr(bp, "utcnow", value)
    return value


def record(calls: list[str], name: str, value: dict[str, object]) -> dict[str, object]:
    calls.append(name)
    return value


def prior(tmp_path: Path) -> tuple[Path, Path]:
    run = tmp_path / "old/frozen-v4/run-v4"
    run.mkdir(parents=True)
    budget = {
        "approval_sha256": "a" * 64,
        "halted": True,
        "counts": {"metadata_before": 88, "auth_http": 12, "sign_ins": 3},
        "original_expires_at": "2026-11-20T14:21:54Z",
    }
    budget_bytes = json.dumps(budget).encode()
    (run / "budget.json").write_bytes(budget_bytes)
    (tmp_path / "old/prior-history.json").write_text(
        json.dumps({"snapshot4_prior_approvals": ["b" * 64]})
    )
    usage = tmp_path / "usage.json"
    usage.write_text(
        json.dumps(
            {
                "outcome": "halted",
                "failure_category": "baseline_provenance_mismatch",
                "budget_receipt_sha256": hashlib.sha256(budget_bytes).hexdigest(),
                "estimated_usd": {
                    "total_observed_chat": "0.145509375",
                    "total_unmeasured_reserved": "2.566027776",
                    "conservative_combined_exposure": "2.711537151",
                },
            }
        )
    )
    return usage, run


@pytest.fixture
def snapshot(tmp_path: Path, clock: Clock) -> bp.Snapshot:
    usage, run = prior(tmp_path)
    value = bp.Snapshot(tmp_path / "repo", "s9a")
    bp.start(value, usage, run, "go ahead")
    return value


def output(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    lines = capsys.readouterr().out.strip().splitlines()
    result: dict[str, Any] = json.loads(lines[-1])
    return result


def test_start_binds_prior_usage_and_writes_private_files(snapshot: bp.Snapshot) -> None:
    base = snapshot.base
    assert stat.S_IMODE(base.stat().st_mode) == 0o700
    for name in ("authorization-v2.json", "prior-history.json", "operations.json"):
        assert stat.S_IMODE((base / name).stat().st_mode) == 0o600
    authorization = snapshot.load("authorization-v2.json")
    history = snapshot.read("prior-history.json")
    assert authorization["limit_profile"] == "baseline-14x10-v9"
    assert authorization["readiness_expires_at"] == (START + timedelta(minutes=30)).isoformat()
    assert (
        authorization["prior_history_sha256"]
        == hashlib.sha256(json.dumps(json.loads(history), sort_keys=True).encode()).hexdigest()
    )
    loaded = json.loads(history)
    assert loaded["snapshot4_prior_approvals"] == ["b" * 64, "a" * 64]
    assert loaded["prior_halt"] == "baseline_provenance_mismatch"
    assert snapshot.load("operations.json")["counts"] == {
        "metadata_before": 0,
        "auth_http": 0,
        "evidence": 0,
        "sign_ins": 0,
    }


def test_start_refuses_existing_snapshot_and_inconsistent_usage(
    tmp_path: Path, snapshot: bp.Snapshot
) -> None:
    usage, run = tmp_path / "usage.json", tmp_path / "old/frozen-v4/run-v4"
    with pytest.raises(bp.PrepareFailure, match="baseline_snapshot_exists"):
        bp.start(snapshot, usage, run, "again")
    data = json.loads(usage.read_text())
    data["estimated_usd"]["total_observed_chat"] = "0.1"
    usage.write_text(json.dumps(data))
    with pytest.raises(bp.PrepareFailure, match="baseline_start_prior_usage_mismatch"):
        bp.start(bp.Snapshot(snapshot.root, "s9b"), usage, run, "go")


def test_readiness_refuses_after_window_expiry(
    snapshot: bp.Snapshot,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(bp, "ROOT", snapshot.root)
    called: list[str] = []
    monkeypatch.setattr(bp, "observe_metadata", lambda _: record(called, "metadata", {}))
    clock.now = START + timedelta(minutes=30)
    assert bp.main(["readiness", "--snapshot", "s9a"]) == 1
    assert output(capsys) == {
        "outcome": "failure",
        "category": "baseline_readiness_authorization_expired",
    }
    assert called == []
    with pytest.raises(bp.PrepareFailure, match="authorization_expired"):
        snapshot.reserve("metadata_before")


@pytest.mark.parametrize(
    ("operation", "maximum"), [("metadata_before", 180), ("auth_http", 40), ("sign_ins", 9)]
)
def test_counters_stop_at_profile_limits(
    snapshot: bp.Snapshot, operation: str, maximum: int
) -> None:
    snapshot.reserve(operation, maximum - 1)
    snapshot.reserve(operation)
    with pytest.raises(bp.PrepareFailure, match="baseline_readiness_operation_limit"):
        snapshot.reserve(operation)
    assert snapshot.load("operations.json")["counts"][operation] == maximum
    assert not (snapshot.base / "operations.next").exists()


def test_evidence_bytes_and_inference_are_bounded(snapshot: bp.Snapshot) -> None:
    snapshot.reserve("evidence_bytes", 10 * 1024 * 1024)
    with pytest.raises(bp.PrepareFailure, match="byte_limit"):
        snapshot.reserve("evidence_bytes", 1)
    with pytest.raises(bp.PrepareFailure, match="inference_forbidden"):
        snapshot.reserve("semantic_evidence")
    with pytest.raises(bp.PrepareFailure, match="operation_limit"):
        snapshot.reserve("publication_creates")


def test_private_records_are_written_once(snapshot: bp.Snapshot, tmp_path: Path) -> None:
    snapshot.save("record.json", {"a": 1})
    with pytest.raises(bp.PrepareFailure, match="baseline_record_exists"):
        snapshot.save("record.json", {"a": 2})
    assert snapshot.load("record.json") == {"a": 1}
    os.symlink(tmp_path / "elsewhere.json", snapshot.base / "link.json")
    with pytest.raises(bp.PrepareFailure, match="baseline_record_exists"):
        snapshot.save("link.json", {})
    assert not (tmp_path / "elsewhere.json").exists()


def plan(*actions: str) -> dict[str, object]:
    return {
        "resource_changes": [
            {"mode": "managed", "change": {"actions": [action]}} for action in actions
        ]
    }


def fake_previews(
    monkeypatch: pytest.MonkeyPatch, snapshot: bp.Snapshot, plans: dict[str, dict[str, object]]
) -> list[list[str]]:
    from newsloom_platform import evaluation_verification

    monkeypatch.setattr(evaluation_verification, "binary_source", lambda raw, owning: None)
    calls: list[list[str]] = []

    def run(
        arguments: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
        env: dict[str, str] | None = None,
        log: Path | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(arguments))
        if arguments[:2] == ["azd", "provision"]:
            assert log is not None and env is not None
            assert env["AZURE_DEV_USER_AGENT"] == "microsoft_foundry_skill"
            log.write_bytes(b"preview")
            cached = snapshot.root / ".azure/dev" / bp.OWNING[arguments[2]] / "main.tfplan"
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(b"plan-" + arguments[2].encode())
            return subprocess.CompletedProcess(arguments, 0, b"", b"")
        layer = Path(arguments[-1]).name.removesuffix(".tfplan")
        return subprocess.CompletedProcess(arguments, 0, json.dumps(plans[layer]).encode(), b"")

    monkeypatch.setattr(bp, "run", run)
    return calls


def test_previews_accept_only_no_op_plans(
    snapshot: bp.Snapshot, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_previews(monkeypatch, snapshot, {layer: plan("no-op") for layer in step.LAYERS})
    clock.now = datetime.fromtimestamp(0, UTC).replace(year=2026, month=11, day=20, hour=12)
    result = bp.run_previews(snapshot)
    assert result["outcome"] == "previews_no_op"
    assert [call[2] for call in calls if call[0] == "azd"] == list(step.LAYERS)
    assert bp.previews_complete(snapshot)
    assert snapshot.load("operations.json")["counts"]["metadata_before"] == 3


def test_previews_refuse_changes(
    snapshot: bp.Snapshot, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_previews(
        monkeypatch,
        snapshot,
        {"application": plan("no-op", "update"), "agent": plan("no-op")},
    )
    with pytest.raises(bp.PrepareFailure, match="baseline_readiness_plan_not_noop"):
        bp.run_previews(snapshot)
    status = snapshot.load("previews/application-status.json")
    assert status["actions"] == {"no-op": 1, "update": 1}
    assert not (snapshot.base / "previews/agent-status.json").exists()
    assert not bp.previews_complete(snapshot)


def test_previews_refuse_stale_cached_plan(
    snapshot: bp.Snapshot, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_previews(monkeypatch, snapshot, {layer: plan("no-op") for layer in step.LAYERS})
    clock.now = datetime.now(UTC) + timedelta(hours=1)
    authorization = snapshot.base / "authorization-v2.json"
    record = json.loads(authorization.read_bytes())
    record["readiness_expires_at"] = (clock.now + timedelta(minutes=30)).isoformat()
    authorization.write_text(json.dumps(record))
    with pytest.raises(bp.PrepareFailure, match="baseline_readiness_stale_cached_plan"):
        bp.run_previews(snapshot)
    assert not (snapshot.base / "previews/application.tfplan").exists()


def test_readiness_rotates_partial_directories_and_stops_at_first_failure(
    snapshot: bp.Snapshot, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(bp, "ROOT", snapshot.root)
    snapshot.directory("observations")
    snapshot.save("observations/context-status.json", {"outcome": "observed"})
    calls: list[str] = []

    def failing_evidence(value: bp.Snapshot) -> dict[str, object]:
        calls.append("evidence")
        value.directory("evidence")
        value.save("evidence/failure.json", {"outcome": "failure"})
        raise bp.PrepareFailure("baseline_capture_sign_in_limit")

    monkeypatch.setattr(bp, "observe_metadata", lambda _: record(calls, "metadata", {}))
    monkeypatch.setattr(bp, "prepare_evidence", failing_evidence)
    monkeypatch.setattr(bp, "run_previews", lambda _: record(calls, "previews", {}))
    for attempt in (1, 2):
        assert bp.main(["readiness", "--snapshot", "s9a"]) == 1
        assert output(capsys)["category"] == "baseline_capture_sign_in_limit"
        assert (snapshot.base / "evidence/failure.json").is_file()
        # A retry moves the earlier partial attempt aside before starting again.
        assert (snapshot.base / "failed-evidence-1/failure.json").is_file() == (attempt == 2)
    assert calls == ["evidence", "evidence"]

    def evidence(value: bp.Snapshot) -> dict[str, object]:
        value.directory("evidence")
        value.save("evidence/status.json", {"outcome": "prepared"})
        return {"outcome": "evidence_prepared"}

    def step(name: str) -> Any:
        return lambda _: record(calls, name, {"outcome": name + "_done"})

    monkeypatch.setattr(bp, "prepare_evidence", evidence)
    monkeypatch.setattr(bp, "run_previews", step("previews"))
    monkeypatch.setattr(bp, "verify_runtime", step("runtime"))
    monkeypatch.setattr(bp, "verify_prices", step("prices"))
    assert bp.main(["readiness", "--snapshot", "s9a"]) == 0
    result = output(capsys)
    assert result["steps"] == {
        "metadata": "already_complete",
        "evidence": "evidence_prepared",
        "previews": "previews_done",
        "runtime": "runtime_done",
        "prices": "prices_done",
    }
    assert result["rotated"] == ["failed-evidence-2"]
    assert calls[2:] == ["previews", "runtime", "prices"]


def test_readiness_hides_unexpected_errors(
    snapshot: bp.Snapshot, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(bp, "ROOT", snapshot.root)

    def broken(_: bp.Snapshot) -> dict[str, object]:
        raise KeyError("https://secret.example/token")

    monkeypatch.setattr(bp, "observe_metadata", broken)
    assert bp.main(["readiness", "--snapshot", "s9a"]) == 1
    captured = capsys.readouterr().out
    assert "secret" not in captured
    assert json.loads(captured)["category"] == "baseline_readiness_metadata_failed"


def run_budget(**changes: object) -> dict[str, object]:
    budget: dict[str, object] = {
        "halted": True,
        "limit_profile": "baseline-14x10-v9",
        "approval_sha256": "c" * 64,
        "original_expires_at": "2026-11-20T15:00:00Z",
        "prior_model_exposure_usd": "2.711537151",
        "counts": {"publication_creates": 0},
        "operator_embedding_usd_reserved": "0.1",
        "agents": [
            {
                "observed_chat_usd": "0.01",
                "reserved_chat_usd": "0.3",
                "reserved_embedding_usd": "0.2",
                "embedding_unused_verified": True,
                "receipt": {"input_tokens": 100, "output_tokens": 10},
            },
            {
                "observed_chat_usd": None,
                "reserved_chat_usd": "0.3",
                "reserved_embedding_usd": "0.2",
                "embedding_unused_verified": False,
                "receipt": None,
            },
        ],
        "judge": {
            "attempts": 12,
            "transport_retries": 0,
            "input_tokens_observed": 1000,
            "output_tokens_observed": 100,
            "estimated_observed_usd": "0.02",
            "estimated_reserved_unknown_usd": "0.4",
        },
        # 2.711537151 + 0.02 + 0.01 + 0.4 + 0.3 + 0.1 + 0.2
        "combined_exposure_usd": "3.741537151",
    }
    budget.update(changes)
    return budget


def write_run(path: Path, budget: dict[str, object]) -> Path:
    path.mkdir(parents=True)
    (path / "budget.json").write_text(json.dumps(budget))
    (path / "partial-results.json").write_text(
        json.dumps({"state": "capturing", "controls": [{"passed": True}], "scores": []})
    )
    return path


def test_record_usage_carries_exposure_once(snapshot: bp.Snapshot, tmp_path: Path) -> None:
    run = write_run(tmp_path / "run", run_budget())
    result = bp.record_usage(snapshot, run)
    usage = result["estimated_usd"]
    assert usage == snapshot.load("usage-report.json")["estimated_usd"]
    assert isinstance(usage, dict)
    assert usage["total_observed_chat"] == "0.175509375"
    assert usage["total_unmeasured_reserved"] == "3.566027776"
    assert usage["conservative_combined_exposure"] == "3.741537151"
    report = snapshot.load("usage-report.json")
    assert (
        report["budget_receipt_sha256"]
        == hashlib.sha256((run / "budget.json").read_bytes()).hexdigest()
    )
    assert (
        report["previous_usage_sha256"]
        == hashlib.sha256(snapshot.read("prior-history.json")).hexdigest()
    )
    with pytest.raises(bp.PrepareFailure, match="baseline_record_exists"):
        bp.record_usage(snapshot, run)


@pytest.mark.parametrize(
    ("changes", "category"),
    [
        ({"combined_exposure_usd": "3.741537150"}, "baseline_usage_exposure_mismatch"),
        ({"prior_model_exposure_usd": "2"}, "baseline_usage_prior_mismatch"),
        ({"halted": False}, "baseline_usage_run_not_halted"),
    ],
)
def test_record_usage_refuses_inconsistent_runs(
    snapshot: bp.Snapshot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    changes: dict[str, object],
    category: str,
) -> None:
    monkeypatch.setattr(bp, "ROOT", snapshot.root)
    run = write_run(tmp_path / "run", run_budget(**changes))
    assert bp.main(["record-usage", "--snapshot", "s9a", "--run", str(run)]) == 1
    assert output(capsys) == {"outcome": "failure", "category": category}
    assert not (snapshot.base / "usage-report.json").exists()


def fake_evaluator(
    monkeypatch: pytest.MonkeyPatch, stdout: dict[str, object], code: int = 0
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def run(
        arguments: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
        env: dict[str, str] | None = None,
        log: Path | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append({"arguments": list(arguments), "cwd": cwd, "env": env})
        return subprocess.CompletedProcess(arguments, code, json.dumps(stdout).encode(), b"")

    monkeypatch.setattr(bp, "run", run)
    return calls


def test_approve_binds_reused_calibration_hash(
    snapshot: bp.Snapshot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/elsewhere")
    calls = fake_evaluator(monkeypatch, {"outcome": "approved"})
    receipt = tmp_path / "calibration.json"
    receipt.write_bytes(b'{"controls":10}')
    bp.approve(snapshot, "approve", receipt)
    call = calls[0]
    assert call["cwd"] == snapshot.root / "tools/agent-evaluation"
    assert call["arguments"][0] == str(snapshot.root / "tools/agent-evaluation/.venv/bin/python")
    assert "PYTHONPATH" not in call["env"]
    assert call["arguments"][-2:] == [
        "--calibration-reuse-sha256",
        hashlib.sha256(b'{"controls":10}').hexdigest(),
    ]
    bp.approve(snapshot, "approve", None)
    assert "--calibration-reuse-sha256" not in calls[1]["arguments"]


def test_evaluator_failure_category_is_passed_through(
    snapshot: bp.Snapshot, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_evaluator(monkeypatch, {"outcome": "failure", "category": "stale_or_unapproved"}, 1)
    with pytest.raises(bp.PrepareFailure, match=r"^stale_or_unapproved$"):
        bp.approve(snapshot, "approve", None)


def test_freeze_requires_complete_readiness(
    snapshot: bp.Snapshot, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_evaluator(monkeypatch, {"outcome": "frozen_not_executed"})
    with pytest.raises(bp.PrepareFailure, match="baseline_freeze_readiness_incomplete"):
        bp.freeze(snapshot)
    assert calls == []


def test_freeze_keeps_a_failed_partial_aside_but_never_replaces_an_approval(
    snapshot: bp.Snapshot, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_evaluator(monkeypatch, {"outcome": "frozen_not_executed"})
    monkeypatch.setattr(bp, "_exists", lambda *_: True)
    monkeypatch.setattr(bp, "previews_complete", lambda _: True)
    frozen = snapshot.base / step.FROZEN
    frozen.mkdir(mode=0o700, parents=True)
    bp.freeze(snapshot)
    assert (snapshot.base / ("failed-" + step.FROZEN + "-1")).is_dir() and len(calls) == 1
    frozen.mkdir(mode=0o700)
    (frozen / "execution-approval.json").write_text("{}")
    with pytest.raises(bp.PrepareFailure, match="baseline_freeze_exists"):
        bp.freeze(snapshot)
    assert len(calls) == 1


class Model:
    def __init__(self, **values: object) -> None:
        self.values = values
        self.__dict__.update(values)

    def model_dump_json(self) -> str:
        return json.dumps({key: str(value) for key, value in self.values.items()}, sort_keys=True)

    def validate_execution(self, now: datetime, frozen: object) -> None:
        assert now == START


def fake_api() -> Any:
    readiness = SimpleNamespace(verify=lambda frozen, now: None)
    return SimpleNamespace(
        FrozenBaseline="frozen",
        ReadinessReceipt="readiness",
        parse_document=lambda model, data: readiness if model == "readiness" else object(),
        BaselineApproval=Model,
        OperationCounts=SimpleNamespace(model_validate=lambda value: value),
        EvaluationFailure=RuntimeError,
    )


def approval_state(tmp_path: Path) -> Path:
    target = tmp_path / "state/frozen-v4"
    target.mkdir(parents=True)
    for name in ("frozen.json", "readiness.json"):
        (target / name).write_text("{}")
    (target / "admission-summary.json").write_text(
        json.dumps(
            {
                "limit_profile": "baseline-14x10-v9",
                "frozen_sha256": "f" * 64,
                "readiness_receipt_sha256": "r" * 64,
                "prices_verified_at": START.isoformat(),
                "input_per_million_usd": "0.75",
                "output_per_million_usd": "4.5",
                "embedding_input_per_million_usd": "0.13",
                "preparation_counts": {"metadata_before": 70},
                "preparation_evidence_bytes": 4000,
                "prior_usage_sha256": "p" * 64,
                "prior_model_exposure_usd": "2.7",
            }
        )
    )
    return tmp_path / "state"


def test_evaluator_approval_binds_calibration_reuse(tmp_path: Path) -> None:
    base = approval_state(tmp_path)
    reused = "e" * 64
    authorization = step.approve(base, fake_api(), "approved", reused, lambda: START)
    raw = (base / "frozen-v4/execution-approval.json").read_bytes()
    approval = json.loads(raw)
    assert approval["calibration_reuse_sha256"] == reused
    assert approval["limit_profile"] == "baseline-14x10-v9"
    assert approval["expires_at"] == str(START + timedelta(hours=3))
    assert authorization["calibration_reuse_sha256"] == reused
    assert authorization["approval_sha256"] == hashlib.sha256(raw).hexdigest()
    assert json.loads((base / "frozen-v4/execution-authorization.json").read_bytes()) == (
        authorization
    )
    assert (
        step.main(["approve", "--state", str(base), "--instruction", "again"], api=fake_api()) == 1
    )


def test_evaluator_approval_omits_absent_calibration_reuse(tmp_path: Path) -> None:
    base = approval_state(tmp_path)
    step.approve(base, fake_api(), "approved", None, lambda: START)
    approval = json.loads((base / "frozen-v4/execution-approval.json").read_bytes())
    assert "calibration_reuse_sha256" not in approval
