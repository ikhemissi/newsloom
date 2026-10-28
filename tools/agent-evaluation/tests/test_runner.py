import asyncio
import hashlib
import json
import subprocess
import sys
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import get_bearer_token_provider
from chat_fakes import scripted_chat
from fakes import Credential
from openai import AsyncOpenAI
from pydantic import ValidationError
from test_budget import Clock

from agent_evaluation import __main__, inputs, runner
from agent_evaluation.budget import MODEL_SNAPSHOT, Budget, BudgetReceipt, Prices
from agent_evaluation.context import BOUND_ENVIRONMENT, Context
from agent_evaluation.inputs import FIXTURE_SHA256, ROOT, load_pilot, source_digest
from agent_evaluation.judge import JudgeTransport
from agent_evaluation.policy import EvaluationFailure
from agent_evaluation.runner import Approval, Journal, MeasuredCase, read_approval, score


def approval_data() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "schema_version": 1,
        "execution_approved": True,
        "source_sha256": source_digest(),
        "fixture_sha256": FIXTURE_SHA256,
        "context_sha256": "a" * 64,
        "approved_at": (now - timedelta(seconds=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "price_verified_at": now.isoformat(),
        "input_per_million_usd": "0.825",
        "output_per_million_usd": "4.95",
        "publication_read_limit": 60,
        "publication_mutation_limit": 3,
        "publication_request_timeout_s": 30,
        "publication_poll_spacing_s": 5,
    }


def test_approval_is_source_fixture_time_and_price_bound() -> None:
    data = approval_data()
    approval = Approval.model_validate_json(json.dumps(data))
    approval.validate_execution(datetime.now(UTC))
    for field in ("source_sha256", "fixture_sha256"):
        changed = dict(data)
        changed[field] = "b" * 64
        with pytest.raises(EvaluationFailure, match="stale_or_unapproved_execution"):
            Approval.model_validate_json(json.dumps(changed)).validate_execution(datetime.now(UTC))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unexpected", True),
        ("schema_version", True),
        ("execution_approved", 1),
        ("input_per_million_usd", 0.825),
        ("approved_at", "2026-10-28T00:00:00"),
    ],
)
def test_unknown_or_coerced_configuration_is_rejected(field: str, value: object) -> None:
    data = approval_data()
    data[field] = value
    with pytest.raises(ValidationError):
        Approval.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-1", "0", "not-a-price"])
def test_invalid_prices_are_rejected(price: str) -> None:
    data = approval_data()
    data["input_per_million_usd"] = price
    with pytest.raises(EvaluationFailure, match="invalid_evaluation_prices"):
        Approval.model_validate_json(json.dumps(data)).validate_execution(datetime.now(UTC))


def test_unapproved_or_expired_configuration_is_rejected() -> None:
    data = approval_data()
    data["execution_approved"] = False
    with pytest.raises(EvaluationFailure, match="stale_or_unapproved_execution"):
        Approval.model_validate_json(json.dumps(data)).validate_execution(datetime.now(UTC))
    data = approval_data()
    data["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with pytest.raises(EvaluationFailure, match="stale_or_unapproved_execution"):
        Approval.model_validate_json(json.dumps(data)).validate_execution(datetime.now(UTC))


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -0.01, 1.01])
def test_invalid_scores_are_not_zero_or_success(value: object) -> None:
    with pytest.raises(ValidationError):
        MeasuredCase.model_validate({"case_id": "p01", "score": value, "reason": "Synthetic"})


@pytest.mark.parametrize("reason", ["", " ", "x" * 4097, "\u00e9" * 2049])
def test_synthetic_reason_is_nonempty_and_byte_bounded(reason: str) -> None:
    with pytest.raises(ValidationError):
        MeasuredCase(case_id="p01", score=0.0, reason=reason)


def test_fixture_edits_fail_before_judging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    edited = tmp_path / "edited.json"
    edited.write_bytes(inputs.FIXTURE.read_bytes() + b"\n")
    monkeypatch.setattr(inputs, "FIXTURE", edited)
    with pytest.raises(EvaluationFailure, match="pilot_fixture_digest_mismatch"):
        load_pilot()


def test_duplicate_case_ids_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(inputs.FIXTURE.read_bytes())
    data["cases"][1]["case_id"] = "p01"
    encoded = json.dumps(data).encode()
    edited = tmp_path / "duplicate.json"
    edited.write_bytes(encoded)
    monkeypatch.setattr(inputs, "FIXTURE", edited)
    monkeypatch.setattr(inputs, "FIXTURE_SHA256", hashlib.sha256(encoded).hexdigest())
    with pytest.raises(EvaluationFailure, match="pilot_case_set_mismatch"):
        load_pilot()


def test_one_approval_cannot_restart_inference_with_another_output_directory(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    journal = Journal(tmp_path / "evaluation-first", "a" * 64, registry=registry)
    journal.write("budget.json", {"attempts": 1, "usage_unknown": 1})
    original = (journal.path / "budget.json").read_bytes()
    with pytest.raises(FileExistsError):
        Journal(tmp_path / "evaluation-second", "a" * 64, registry=registry)
    assert not (tmp_path / "evaluation-second").exists()
    assert (journal.path / "budget.json").read_bytes() == original
    assert (journal.path / "budget.json").stat().st_mode & 0o777 == 0o600


def test_foreign_journal_targets_are_rejected(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "evaluation", "a" * 64, registry=tmp_path / "registry")
    with pytest.raises(EvaluationFailure, match="foreign_evaluation_journal_target"):
        journal.write("../foreign.json", {})
    assert not (tmp_path / "foreign.json").exists()


async def test_unapproved_manifest_digest_never_creates_a_run(tmp_path: Path) -> None:
    manifest = tmp_path / "approval.json"
    manifest.write_text(json.dumps(approval_data()))
    target = tmp_path / "evaluation"
    with pytest.raises(EvaluationFailure, match="execution_approval_digest_mismatch"):
        await score(manifest, "b" * 64, target)
    assert not target.exists()


def test_offline_cli_validation_emits_only_fingerprints_and_counts() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "agent_evaluation", "validate"],
        cwd=ROOT / "tools/agent-evaluation",
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    receipt = json.loads(result.stdout)
    assert receipt["outcome"] == "validated"
    assert receipt["cases"] == 2
    assert receipt["model_calls"] == 0
    assert "Loomhaven" not in result.stdout + result.stderr


def test_cli_argument_errors_never_echo_values() -> None:
    canary = "synthetic-argument-credential-canary"
    result = subprocess.run(
        [sys.executable, "-m", "agent_evaluation", "validate", "--foreign", canary],
        cwd=ROOT / "tools/agent-evaluation",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 2
    assert canary not in result.stdout + result.stderr
    assert "invalid_evaluation_arguments" in result.stderr


def test_offline_validation_failure_is_content_free(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    canary = "synthetic-validation-error-canary"

    def fail() -> None:
        raise EvaluationFailure(canary)

    monkeypatch.setattr(__main__, "load_pilot", fail)
    monkeypatch.setattr(sys, "argv", ["agent_evaluation", "validate"])
    assert __main__.main() == 1
    captured = capsys.readouterr()
    assert canary not in captured.out + captured.err
    assert json.loads(captured.out)["category"] == "evaluation_validation_error"


def test_manifest_file_is_bounded_regular_and_not_symlinked(tmp_path: Path) -> None:
    manifest = tmp_path / "approval.json"
    manifest.write_bytes(b"x" * (16 * 1024))
    assert len(read_approval(manifest)) == 16 * 1024
    manifest.write_bytes(b"x" * (16 * 1024 + 1))
    with pytest.raises(EvaluationFailure, match="invalid_evaluation_manifest_file"):
        read_approval(manifest)
    linked = tmp_path / "linked"
    linked.symlink_to(manifest)
    with pytest.raises(OSError):
        read_approval(linked)


async def test_score_runs_real_metric_and_sdk_with_private_durable_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready_calls: list[int] = []
    requests: list[httpx2.Request] = []
    clock = Clock()

    class LocalContext(Context):
        async def ensure_ready(self) -> None:
            ready_calls.append(1)

    environment = dict.fromkeys(BOUND_ENVIRONMENT, "synthetic")
    environment["MODEL_ENDPOINT"] = "https://evaluation-test.openai.azure.com"
    environment["ENRICHMENT_DEPLOYMENT"] = "test-deployment"
    context = LocalContext(environment, "synthetic-operator")

    async def read_context() -> Context:
        return context

    def create_budget(
        prices: Prices, *, persist: Callable[[BudgetReceipt], Awaitable[None]]
    ) -> Budget:
        return Budget(prices, clock=clock, sleep=clock.sleep, persist=persist)

    def create_journal(path: Path, approval_sha256: str) -> Journal:
        return Journal(path, approval_sha256, registry=tmp_path / "registry")

    def credential(*, tenant_id: str) -> Credential:
        return Credential()

    def client(
        endpoint: str,
        deployment: str,
        credential: AsyncTokenCredential,
        budget: Budget,
    ) -> AsyncOpenAI:
        def respond(request: httpx2.Request) -> httpx2.Response:
            unsupported = len(requests) >= 4
            requests.append(request)
            return scripted_chat(request, unsupported=unsupported, snapshot=MODEL_SNAPSHOT)

        return AsyncOpenAI(
            base_url=endpoint + "/openai/v1",
            api_key=get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            ),
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=JudgeTransport(
                    endpoint, deployment, budget, httpx2.MockTransport(respond)
                ),
                trust_env=False,
                follow_redirects=False,
            ),
        )

    monkeypatch.setattr(runner, "read_context", read_context)
    monkeypatch.setattr(runner, "Budget", create_budget)
    monkeypatch.setattr(runner, "Journal", create_journal)
    monkeypatch.setattr(runner, "AzureCliCredential", credential)
    monkeypatch.setattr(runner, "model_client", client)
    data = approval_data()
    data["context_sha256"] = context.digest()
    manifest = tmp_path / "approval.json"
    encoded = json.dumps(data).encode()
    manifest.write_bytes(encoded)
    target = tmp_path / "evaluation"
    result = await score(manifest, hashlib.sha256(encoded).hexdigest(), target)
    assert tuple(row.score for row in result.cases) == (1.0, 0.0)
    assert len(requests) == len(ready_calls) == result.budget.attempts == 8
    assert result.budget.usage_complete
    assert (target / "approval.json").read_bytes() == encoded
    persisted = json.loads((target / "results.json").read_bytes())
    assert persisted["fixture_sha256"] == FIXTURE_SHA256
    assert tuple(row["case_id"] for row in persisted["cases"]) == ("p01", "p02")
    assert json.loads((target / "budget.json").read_bytes())["budget"]["usage_unknown"] == 0


async def test_cancelled_journal_write_finishes_before_final_failure_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = Journal(tmp_path / "pilot", "a" * 64, registry=tmp_path / "registry")
    entered, release = threading.Event(), threading.Event()
    original = journal.write

    def blocked(name: str, value: dict[str, object]) -> None:
        entered.set()
        assert release.wait(5)
        original(name, value)

    monkeypatch.setattr(journal, "write", blocked)
    task = asyncio.create_task(journal.persist("budget.json", {"attempts": 1}))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await journal.persist("budget.json", {"attempts": 1, "admission_halted": True})
    assert json.loads((journal.path / "budget.json").read_bytes())["admission_halted"]
    assert not (journal.path / "budget.json.next").exists()
