import asyncio
import json
import time
from pathlib import Path

import pytest
from pydantic import JsonValue
from test_baseline_budget import Recorder, approval, frozen, ready

from agent_evaluation.baseline_budget import BaselineBudget
from agent_evaluation.baseline_ipc import (
    CaptureAdmission,
    PrivateCaptureProcess,
    PrivateFrame,
)
from agent_evaluation.baseline_provenance import capture_source_digest
from agent_evaluation.inputs import ROOT
from agent_evaluation.policy import EvaluationFailure

WORKER = """
import argparse, os
from pathlib import Path
from scripts.agent_quality_protocol import PrivateChannel
from scripts.agent_quality_capture import CaptureLimits
p = argparse.ArgumentParser()
for name in ("request-fd", "response-fd"):
    p.add_argument("--" + name, type=int)
p.add_argument("--initial-sent", type=int, default=0)
p.add_argument("--initial-received", type=int, default=0)
p.add_argument("--source-sha256")
p.add_argument("--deadline", type=float)
p.add_argument("--marker")
p.add_argument("--behavior", default="normal")
a = p.parse_args()
c = PrivateChannel(
    a.request_fd, a.response_fd, a.source_sha256, a.deadline,
    sent=a.initial_sent, received=a.initial_received,
)
try:
    request = c.receive()
    limits = CaptureLimits(deadline=a.deadline, permit=c.admit)
    if a.behavior == "bad_error":
        c.send("error", {"category": "PRIVATE_CREDENTIAL_CANARY"})
        raise SystemExit(2)
    if a.behavior == "bad_index":
        c.send("admission", {"index": 1, "operation": "evidence", "amount": 1})
        c.read()
        raise SystemExit(2)
    limits.admit_sign_in()
    if a.behavior == "replay":
        c.index = 0
    limits.admit_auth()
    limits.admit_tool()
    limits.admit_tool(semantic_query=True)
    limits.consume(32)
    c.admit("task_reads")
    c.admit("metadata_before")
    c.admit("metadata_after")
    Path(a.marker).write_text("dispatched")
    c.send("reply", {"operations": limits.operations, "received": limits.received})
finally:
    c.close()
"""


def process(
    budget: BaselineBudget, tmp_path: Path, behavior: str = "normal"
) -> PrivateCaptureProcess:
    return PrivateCaptureProcess(
        (
            str(ROOT / ".venv/bin/python"),
            "-c",
            WORKER,
            "--marker",
            str(tmp_path / "dispatched"),
            "--behavior",
            behavior,
        ),
        source_sha256=capture_source_digest(),
        deadline=time.monotonic() + 10,
        initial_sent=budget.byte_counts["ipc_sent"],
        initial_received=budget.byte_counts["ipc_received"],
        account_wire=budget.account_capture_wire,
    )


async def exchange(worker: PrivateCaptureProcess, budget: BaselineBudget) -> dict[str, JsonValue]:
    return await worker.exchange(
        "b01",
        {"action": "controlled"},
        request_sha256="3" * 64,
        evidence_sha256="4" * 64,
        admit=budget.admit_capture,
    )


async def test_real_root_callbacks_wait_for_durable_shared_admission(tmp_path: Path) -> None:
    value = frozen()
    record = Recorder()
    budget = BaselineBudget(approval(value), value, persist=record, ready=ready)
    await budget.start()
    await budget.admit_agent("b01")
    budget.byte_counts["ipc_sent"] = 20
    budget.byte_counts["ipc_received"] = 30
    await budget.checkpoint()
    async with process(budget, tmp_path) as worker:
        result = await exchange(worker, budget)
        assert result == {"operations": 2, "received": 32}
        assert budget.byte_counts["ipc_sent"] == worker.sent
        assert budget.byte_counts["ipc_received"] == worker.received
    assert (tmp_path / "dispatched").read_text() == "dispatched"
    assert budget.counts == {
        "evidence": 2,
        "auth_http": 1,
        "sign_ins": 1,
        "task_reads": 1,
        "metadata_before": 1,
        "metadata_after": 1,
        "publication_reads": 0,
        "publication_creates": 0,
    }
    assert budget.byte_counts["evidence"] == 32
    assert budget.embedding_dispatches == 27
    assert record.states[-1].ipc_sent_bytes == worker.sent
    assert record.states[-1].ipc_received_bytes == worker.received
    assert record.states[-1].agents[0].receipt is None


@pytest.mark.parametrize("behavior", ["bad_index", "replay"])
async def test_reordered_or_replayed_admission_never_permits_dispatch(
    tmp_path: Path, behavior: str
) -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    async with process(budget, tmp_path, behavior) as worker:
        with pytest.raises(EvaluationFailure, match="baseline_ipc_admission_invalid"):
            await exchange(worker, budget)
        assert worker.closed
    assert not (tmp_path / "dispatched").exists()
    assert budget.counts["sign_ins"] == (1 if behavior == "replay" else 0)
    assert budget.counts["auth_http"] == 0


@pytest.mark.parametrize(
    "failure", ["count", "checkpoint", "journal_failure", "cancellation", "no_handler"]
)
async def test_no_permit_after_failure_and_no_counter_or_reservation_reset(
    tmp_path: Path, failure: str
) -> None:
    value = frozen()
    record = Recorder()
    budget = BaselineBudget(approval(value), value, persist=record, ready=ready)
    await budget.start()
    await budget.admit_agent("b01")
    exposure = budget.external_exposure()
    if failure == "count":
        budget.counts["sign_ins"] = 4
    if failure == "journal_failure":

        async def broken_journal(state: object) -> None:
            if budget.counts["sign_ins"]:
                raise OSError("PRIVATE_PERSISTENCE_CANARY")

        budget.persist = broken_journal
    async with process(budget, tmp_path) as worker:
        if failure == "checkpoint":

            async def fail(event: CaptureAdmission) -> None:
                await budget.admit_capture(event)
                raise OSError("PRIVATE_PERSISTENCE_CANARY")

            with pytest.raises(OSError):
                await worker.exchange(
                    "b01",
                    {},
                    request_sha256="3" * 64,
                    evidence_sha256="4" * 64,
                    admit=fail,
                )
        elif failure == "cancellation":
            entered = asyncio.Event()

            async def blocked(event: CaptureAdmission) -> None:
                await budget.admit_capture(event)
                entered.set()
                await asyncio.Future[None]()

            task = asyncio.create_task(
                worker.exchange(
                    "b01",
                    {},
                    request_sha256="3" * 64,
                    evidence_sha256="4" * 64,
                    admit=blocked,
                )
            )
            await asyncio.wait_for(entered.wait(), 10)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(EvaluationFailure):
                await worker.exchange(
                    "b01",
                    {},
                    request_sha256="3" * 64,
                    evidence_sha256="4" * 64,
                    admit=None if failure == "no_handler" else budget.admit_capture,
                )
            if failure == "journal_failure":
                assert budget.halted and budget.counts["sign_ins"] == 1
        assert worker.closed and worker.process is not None
        assert worker.process.returncode is not None
    assert not (tmp_path / "dispatched").exists()
    assert budget.external_exposure() == exposure
    assert budget.agents["b01"].receipt is None
    with pytest.raises(
        EvaluationFailure,
        match="baseline_admission_halted" if budget.halted else "baseline_agent_slot_consumed",
    ):
        await budget.admit_agent("b01")


async def test_worker_rejects_permit_for_another_nonce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    async with process(budget, tmp_path) as worker:
        send = worker.send_frame

        async def changed(frame: PrivateFrame) -> None:
            if frame.kind == "permit":
                frame = frame.model_copy(update={"nonce": "0" * 64})
            await send(frame)

        monkeypatch.setattr(worker, "send_frame", changed)
        with pytest.raises(EvaluationFailure, match="baseline_ipc_worker_closed"):
            await exchange(worker, budget)
    assert budget.counts["sign_ins"] == 1
    assert not (tmp_path / "dispatched").exists()


async def test_worker_refuses_raw_error_payload_before_writing_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    value = frozen()
    budget = BaselineBudget(approval(value), value, persist=Recorder(), ready=ready)
    await budget.start()
    async with process(budget, tmp_path, "bad_error") as worker:
        with pytest.raises(EvaluationFailure, match="baseline_ipc_worker_closed"):
            await exchange(worker, budget)
        assert worker.received == 0
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err


def test_admission_payload_is_closed_and_never_echoes_content() -> None:
    for data in (
        {"index": 0, "operation": "PRIVATE_CREDENTIAL_CANARY", "amount": 1},
        {"index": 0, "operation": "sign_ins", "amount": True},
        {"index": 0, "operation": "sign_ins", "amount": 2},
        {"index": 0, "operation": "evidence_bytes", "amount": 65537},
    ):
        with pytest.raises(ValueError) as caught:
            CaptureAdmission.model_validate_json(json.dumps(data))
        assert "CANARY" not in str(caught.value)
