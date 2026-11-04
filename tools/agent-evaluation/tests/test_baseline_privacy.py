import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fakes import TOKEN
from test_baseline_publication import Service, execute, setup
from test_publication import selected_context

from agent_evaluation.baseline_budget import BaselineRun
from agent_evaluation.baseline_publication import (
    BaselinePublicationReceipt,
    BaselinePublisher,
    ReportReference,
)
from agent_evaluation.inputs import ROOT
from agent_evaluation.policy import EvaluationFailure

PROCESS_PROBE = """
import sys
blocked = []
def audit(event, args):
    if event == "socket.connect":
        address = args[1]
        if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "::1"):
            blocked.append(event)
            raise RuntimeError("baseline_unexpected_network")
    if event == "socket.getaddrinfo" and args[0] not in ("127.0.0.1", "::1", "localhost"):
        blocked.append(event)
        raise RuntimeError("baseline_unexpected_network")
sys.addaudithook(audit)
import pytest
status = pytest.main(sys.argv[1:])
assert not blocked, "baseline_unexpected_network"
raise SystemExit(status)
"""


async def test_every_persistence_boundary_revalidates_unsafe_model_copies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    budget, run, result = await setup(tmp_path)
    before_progress = (tmp_path / "run/partial-results.json").read_bytes()
    before_results = (tmp_path / "run/results.json").read_bytes()
    progress = run.load_scoring_progress().model_copy(
        update={
            "pending_case": "PRIVATE_PENDING_CONTENT_CANARY",
        }
    )
    with pytest.raises(EvaluationFailure, match="invalid_baseline_persisted_metadata"):
        await run.scoring_checkpoint(progress)
    invalid_result = result.model_copy(update={"protocol": "PRIVATE_RESULT_CONTENT_CANARY"})
    with pytest.raises(EvaluationFailure, match="invalid_baseline_persisted_metadata"):
        await run.save_results(invalid_result)
    bad_judge = budget.judge.receipt().model_copy(
        update={
            "estimated_observed_usd": "PRIVATE_AMOUNT_CONTENT_CANARY",
        }
    )
    invalid_budget = budget.receipt().model_copy(update={"judge": bad_judge})
    with pytest.raises(EvaluationFailure, match="invalid_baseline_persisted_metadata"):
        await run.checkpoint(invalid_budget)
    assert (tmp_path / "run/partial-results.json").read_bytes() == before_progress
    assert (tmp_path / "run/results.json").read_bytes() == before_results
    captured = capsys.readouterr()
    assert "PRIVATE_" not in captured.out + captured.err
    for path in (tmp_path / "run").iterdir():
        if path.is_file():
            assert b"CONTENT_CANARY" not in path.read_bytes()


@pytest.mark.parametrize("environment", ["judge", "capture"])
def test_fresh_process_failure_and_success_leave_no_content_or_credential_artifacts(
    tmp_path: Path, environment: str
) -> None:
    project = ROOT / "tools/agent-evaluation"
    home = tmp_path / "home"
    home.mkdir()
    if environment == "judge":
        python = Path(sys.executable)
        cwd = project
        selectors = [
            "tests/test_baseline_scoring.py",
            "tests/test_baseline_publication.py",
            "tests/test_baseline_ipc.py",
            "tests/test_baseline_capture_admission.py",
            "tests/test_baseline_cli.py",
        ]
    else:
        python = ROOT / ".venv/bin/python"
        cwd = ROOT
        selectors = [
            "tests/test_agent_quality_capture.py",
            "tests/test_agent_research_privacy.py"
            "::test_real_research_http_content_canaries_cover_success_faults_and_overload",
        ]
    result = subprocess.run(
        [
            str(python),
            "-c",
            PROCESS_PROBE,
            "-q",
            *selectors,
            "--basetemp",
            str(tmp_path / "cases"),
            "-o",
            "cache_dir=" + str(tmp_path / "pytest-cache"),
        ],
        cwd=cwd,
        env={
            **os.environ,
            "HOME": str(home),
            "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_CACHE_HOME": str(home / "cache"),
            "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_DATA_HOME": str(home / "data"),
            # The root canary exercises actual exporters, unlike the isolated judge.
            **({"OTEL_SDK_DISABLED": "false"} if environment == "capture" else {}),
        },
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    canaries = (
        b"LIVE_ANSWER_PRIVATE_CANARY",
        b"Authored Cedar summary.",
        b"Authored bounded evidence",
        b"AGENT_CREDENTIAL_CANARY",
        b"TOKEN_CANARY",
        b"CODE_CANARY",
        b"PRIVATE_CHANGED_CONTENT",
        b"RESEARCH_NEWS_CANARY",
        b"RESEARCH_FOCUS_CANARY",
        b"RESEARCH_TITLE_CANARY",
        b"JUDGE_REASON_PRIVATE_CANARY",
        b"PRIVATE_PROVIDER_ERROR_CANARY",
        TOKEN.encode(),
    )
    diagnostics = (result.stdout + result.stderr).encode()
    assert all(value not in diagnostics for value in canaries)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert all(value not in data for value in canaries), path.name
    assert not (home / ".deepeval").exists()
    assert not (home / ".confident").exists()


def test_private_metadata_parser_never_echoes_invalid_approval_content() -> None:
    raw = b'{"protocol":"PRIVATE_APPROVAL_CANARY"}'
    with pytest.raises(EvaluationFailure, match="baseline_approval_fingerprint_mismatch") as caught:
        BaselineRun.parse_approval(raw, "0" * 64)
    assert "CANARY" not in str(caught.value)


async def test_publication_revalidates_both_state_and_final_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    budget, run, result = await setup(tmp_path)
    with pytest.raises(EvaluationFailure, match="invalid_baseline_persisted_metadata"):
        BaselinePublisher(
            budget,
            run,
            result.model_copy(update={"protocol": "PRIVATE_PUBLISH_CANARY"}),
            selected_context(),
        )
    publisher = BaselinePublisher(budget, run, result, selected_context())
    receipt = BaselinePublicationReceipt.model_validate_json(
        json.dumps(await execute(publisher, Service()))
    )
    before = {
        name: (tmp_path / "run" / name).read_bytes()
        for name in ("publication-state.json", "publication.json")
    }
    with pytest.raises(EvaluationFailure, match="invalid_baseline_persisted_metadata"):
        await run.publication_checkpoint(
            publisher.state.model_copy(update={"protocol": "PRIVATE_STATE_CANARY"})
        )
    with pytest.raises(EvaluationFailure, match="invalid_baseline_persisted_metadata"):
        await run.publication_receipt(
            receipt.model_copy(update={"outcome": "PRIVATE_RECEIPT_CANARY"})
        )
    for name, data in before.items():
        assert (tmp_path / "run" / name).read_bytes() == data
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err


@pytest.mark.parametrize(
    "suffix",
    [
        "?reason=PRIVATE_REPORT_CANARY",
        "#PRIVATE_REPORT_CANARY",
        "?tid=PRIVATE_REPORT_CANARY",
        "?tid=",
        "/PRIVATE_REPORT_CANARY",
    ],
)
def test_report_references_reject_content_bearing_fields_without_echoing(suffix: str) -> None:
    with pytest.raises(ValueError) as caught:
        ReportReference.model_validate(
            {
                "metric_id": "faithfulness",
                "cases": 8,
                "evaluation_id": "eval_authored",
                "run_id": "run_authored",
                "report_url": (
                    "https://ai.azure.com/nextgen/r/authored/build/evaluations/"
                    "eval_authored/run/run_authored" + suffix
                ),
            }
        )
    assert "CANARY" not in str(caught.value)
