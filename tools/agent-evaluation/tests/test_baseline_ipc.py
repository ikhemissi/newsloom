import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest
from pydantic import JsonValue

from agent_evaluation.baseline_ipc import (
    FRAME_LIMIT,
    TOTAL_LIMIT,
    PrivateCaptureProcess,
    PrivateFrame,
    decode_frame,
    frame_bytes,
)
from agent_evaluation.baseline_provenance import capture_source_digest, document_digest
from agent_evaluation.inputs import ROOT
from agent_evaluation.policy import EvaluationFailure

FAKE = """
import argparse, json, os, struct, sys, time
p=argparse.ArgumentParser()
for name in ("request-fd","response-fd"):
    p.add_argument("--"+name,type=int)
for name in ("source-sha256","deadline","behavior"):
    p.add_argument("--"+name)
a=p.parse_args()
print("STDOUT_CREDENTIAL_CANARY")
print("STDERR_CREDENTIAL_CANARY",file=sys.stderr)
def read(n):
    b=b""
    while len(b)<n:
        x=os.read(a.request_fd,n-len(b))
        if not x: raise SystemExit(0)
        b+=x
    return b
if a.behavior=="timeout":
    time.sleep(60)
if a.behavior=="crash":
    raise SystemExit(7)
size=struct.unpack(">I",read(4))[0]
v=json.loads(read(size));v["kind"]="reply"
if a.behavior=="oversize":
    os.write(a.response_fd,struct.pack(">I",262145))
    time.sleep(60)
if a.behavior=="malformed":
    os.write(a.response_fd,struct.pack(">I",2)+b"{}")
    raise SystemExit(0)
if a.behavior=="nonce": v["nonce"]="0"*64
if a.behavior=="sequence": v["sequence"]+=1
if a.behavior=="case": v["case_id"]="b12"
if a.behavior=="source": v["source_sha256"]="0"*64
if a.behavior=="hash": v["payload_sha256"]="0"*64
if a.behavior in ("error", "stage_error", "code_error"):
    category = "RAW_CONTENT_CANARY" if a.behavior=="error" else "capture_research_failed"
    v["kind"]="error";v["payload"]={"category":category}
    if a.behavior=="code_error":
        v["payload"]["failure_sha256"]="a"*64
    import hashlib
    v["payload_sha256"]=hashlib.sha256(json.dumps(v["payload"],sort_keys=True,separators=(",",":")).encode()).hexdigest()
b=json.dumps(v,separators=(",",":")).encode()
os.write(a.response_fd,struct.pack(">I",len(b))+b)
time.sleep(60)
"""


def frame(payload: dict[str, object] | None = None) -> PrivateFrame:
    value = {"probe": ""} if payload is None else payload
    return PrivateFrame.model_validate(
        {
            "protocol": "baseline-capture-v1",
            "kind": "request",
            "sequence": 0,
            "nonce": "1" * 64,
            "case_id": "b01",
            "source_sha256": "2" * 64,
            "request_sha256": "3" * 64,
            "evidence_sha256": "4" * 64,
            "payload_sha256": document_digest(value),
            "payload": value,
        }
    )


def child(tmp_path: Path, behavior: str, *, timeout: float = 5) -> PrivateCaptureProcess:
    path = tmp_path / "fake_worker.py"
    path.write_text(FAKE)
    return PrivateCaptureProcess(
        (sys.executable, str(path), "--behavior", behavior),
        source_sha256="2" * 64,
        deadline=time.monotonic() + timeout,
    )


async def exchange(process: PrivateCaptureProcess) -> dict[str, JsonValue]:
    return await process.exchange(
        "b01",
        {"action": "probe", "probe": "PRIVATE_CONTENT_CANARY"},
        request_sha256="3" * 64,
        evidence_sha256="4" * 64,
    )


def test_frame_exact_byte_boundary_and_hidden_payload() -> None:
    base = frame()
    empty_size = len(base.model_dump_json().encode())
    valid = frame({"probe": "x" * (FRAME_LIMIT - empty_size)})
    assert len(frame_bytes(valid)) == FRAME_LIMIT + 4
    assert "PRIVATE_CONTENT_CANARY" not in repr(frame({"probe": "PRIVATE_CONTENT_CANARY"}))
    with pytest.raises(EvaluationFailure, match="baseline_ipc_frame_limit"):
        frame_bytes(frame({"probe": "x" * (FRAME_LIMIT - empty_size + 1)}))


async def test_actual_root_environment_uses_private_descriptors_not_stdio(
    capsys: pytest.CaptureFixture[str],
) -> None:
    python = ROOT / ".venv/bin/python"
    assert python.is_file()
    async with PrivateCaptureProcess(
        (str(python), "-m", "scripts.agent_quality_protocol"),
        source_sha256=capture_source_digest(),
        deadline=time.monotonic() + 10,
    ) as process:
        result = await exchange(process)
        assert result["probe"] == "PRIVATE_CONTENT_CANARY"
        assert (
            result["environment_sha256"] == hashlib.sha256(str(ROOT / ".venv").encode()).hexdigest()
        )
        assert result["environment_sha256"] != hashlib.sha256(sys.prefix.encode()).hexdigest()
        assert process.sequence == 1 and process.sent > 0 and process.received > 0
    assert process.closed and process.process is not None
    assert process.process.returncode is not None
    assert process.request_fd is process.response_fd is None
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err


@pytest.mark.parametrize(
    ("behavior", "category"),
    [
        ("nonce", "baseline_ipc_reply_mismatch"),
        ("sequence", "baseline_ipc_reply_mismatch"),
        ("case", "baseline_ipc_reply_mismatch"),
        ("source", "baseline_ipc_reply_mismatch"),
        ("hash", "baseline_ipc_invalid_frame"),
        ("error", "baseline_ipc_invalid_frame"),
        ("stage_error", "baseline_capture_research_failed"),
        ("oversize", "baseline_ipc_frame_limit"),
        ("malformed", "baseline_ipc_invalid_frame"),
        ("crash", "baseline_ipc_worker_closed"),
    ],
)
async def test_bad_or_crashing_children_are_closed_without_leaking_stdio(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], behavior: str, category: str
) -> None:
    async with child(tmp_path, behavior) as process:
        with pytest.raises(EvaluationFailure, match=category):
            await exchange(process)
        assert process.closed and process.process is not None
        assert process.process.returncode is not None
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err


async def test_safe_failure_fingerprint_is_available_without_raw_exception(
    tmp_path: Path,
) -> None:
    observed: list[tuple[str, str | None]] = []
    async with child(tmp_path, "code_error") as process:
        with pytest.raises(EvaluationFailure, match="baseline_capture_research_failed"):
            await process.exchange(
                "b01",
                {},
                request_sha256="3" * 64,
                evidence_sha256="4" * 64,
                on_failure=lambda category, digest: observed.append((category, digest)),
            )
    assert observed == [("capture_research_failed", "a" * 64)]


@pytest.mark.parametrize("direction", ["sent", "received"])
async def test_cumulative_wire_byte_limit_closes_worker(tmp_path: Path, direction: str) -> None:
    async with child(tmp_path, "reply") as process:
        setattr(process, direction, TOTAL_LIMIT)
        with pytest.raises(EvaluationFailure, match="baseline_ipc_total_limit"):
            await exchange(process)
        assert process.closed


async def test_timeout_and_cancellation_release_fds_and_owned_process(tmp_path: Path) -> None:
    async with child(tmp_path, "timeout", timeout=0.2) as process:
        with pytest.raises(EvaluationFailure, match="baseline_ipc_deadline"):
            await exchange(process)
        assert process.closed and process.process is not None
        assert process.process.returncode is not None
    async with child(tmp_path, "timeout") as process:
        task = asyncio.create_task(exchange(process))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.closed and process.request_fd is process.response_fd is None


def test_invalid_frames_never_echo_content_or_accept_duplicate_json() -> None:
    value = frame().model_dump()
    value["unexpected"] = "PRIVATE_CONTENT_CANARY"
    with pytest.raises(EvaluationFailure, match="baseline_ipc_invalid_frame") as caught:
        decode_frame(json.dumps(value).encode())
    assert "CANARY" not in str(caught.value)
    with pytest.raises(EvaluationFailure, match="duplicate_json_field"):
        decode_frame(b'{"kind":"reply","kind":"request"}')


def test_import_overrides_and_nonfinite_deadlines_fail_before_spawn() -> None:
    for deadline in (float("nan"), float("inf"), time.monotonic() - 1):
        with pytest.raises(EvaluationFailure, match="baseline_ipc_launch_invalid"):
            PrivateCaptureProcess(("ignored",), source_sha256="2" * 64, deadline=deadline)
    with pytest.raises(EvaluationFailure, match="baseline_ipc_launch_invalid"):
        PrivateCaptureProcess(
            ("ignored",),
            source_sha256="2" * 64,
            deadline=time.monotonic() + 5,
            environment={"PYTHONPATH": str(ROOT)},
        )
    assert not any(name in os.environ for name in ("PYTHONPATH", "PYTHONHOME"))
