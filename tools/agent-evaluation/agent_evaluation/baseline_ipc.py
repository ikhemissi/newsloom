import asyncio
import hashlib
import json
import math
import os
import re
import secrets
import struct
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import Field, JsonValue, StrictInt, model_validator

from agent_evaluation.baseline_inputs import CaseId
from agent_evaluation.baseline_provenance import (
    Digest,
    capture_source_digest,
    document_digest,
    verify_production_inputs,
)
from agent_evaluation.inputs import ROOT, StrictModel, json_document
from agent_evaluation.policy import EvaluationFailure

FRAME_LIMIT: Final = 256 * 1024
TOTAL_LIMIT: Final = 8 * 1024 * 1024
CaseToken = CaseId | Literal["preflight"]
SAFE_ERRORS: Final = {
    "capture_not_approved",
    "capture_invalid_request",
    "capture_worker_failed",
    "capture_open_failed",
    "capture_pool_before_failed",
    "capture_research_failed",
    "capture_pool_after_failed",
    "capture_cleanup_failed",
}


class PrivateFrame(StrictModel):
    protocol: Literal["baseline-capture-v1"]
    kind: Literal["request", "reply", "error", "admission", "permit"]
    sequence: StrictInt = Field(ge=0, le=2047)
    nonce: Digest
    case_id: CaseToken
    source_sha256: Digest
    request_sha256: Digest
    evidence_sha256: Digest
    payload_sha256: Digest
    payload: dict[str, JsonValue] = Field(repr=False)

    @model_validator(mode="after")
    def payload_is_bound(self) -> Self:
        if self.payload_sha256 != document_digest(self.payload):
            raise ValueError("baseline_ipc_payload_hash")
        if self.kind == "error":
            category = self.payload.get("category")
            cause = self.payload.get("failure_sha256")
            if (
                set(self.payload) not in ({"category"}, {"category", "failure_sha256"})
                or not isinstance(category, str)
                or category not in SAFE_ERRORS
                or (
                    cause is not None
                    and (not isinstance(cause, str) or re.fullmatch(r"[a-f0-9]{64}", cause) is None)
                )
            ):
                raise ValueError("baseline_ipc_error_schema")
        return self


class CaptureAdmission(StrictModel):
    index: StrictInt = Field(ge=0, le=2047)
    operation: Literal[
        "evidence",
        "semantic_evidence",
        "auth_http",
        "sign_ins",
        "task_reads",
        "metadata_before",
        "metadata_after",
        "evidence_bytes",
    ]
    amount: StrictInt = Field(ge=1, le=64 * 1024)

    @model_validator(mode="after")
    def exact_operation_amount(self) -> Self:
        if self.operation != "evidence_bytes" and self.amount != 1:
            raise ValueError("baseline_capture_admission_amount")
        return self


def frame_bytes(frame: PrivateFrame) -> bytes:
    data = frame.model_dump_json().encode()
    if not 0 < len(data) <= FRAME_LIMIT:
        raise EvaluationFailure("baseline_ipc_frame_limit")
    return struct.pack(">I", len(data)) + data


def decode_frame(data: bytes) -> PrivateFrame:
    if not 0 < len(data) <= FRAME_LIMIT:
        raise EvaluationFailure("baseline_ipc_frame_limit")
    try:
        json_document(data)
        return PrivateFrame.model_validate_json(data)
    except ValueError, RecursionError:
        raise EvaluationFailure("baseline_ipc_invalid_frame") from None


def read_exact(descriptor: int, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        try:
            data = os.read(descriptor, size - len(result))
        except OSError:
            raise EvaluationFailure("baseline_ipc_read_failed") from None
        if not data:
            raise EvaluationFailure("baseline_ipc_worker_closed")
        result.extend(data)
    return bytes(result)


def write_exact(descriptor: int, data: bytes) -> None:
    position = 0
    while position < len(data):
        try:
            size = os.write(descriptor, data[position:])
        except OSError:
            raise EvaluationFailure("baseline_ipc_write_failed") from None
        if size <= 0:
            raise EvaluationFailure("baseline_ipc_write_failed")
        position += size


class PrivateCaptureProcess:
    def __init__(
        self,
        command: Sequence[str],
        *,
        source_sha256: str,
        deadline: float,
        environment: Mapping[str, str] | None = None,
        cwd: Path = ROOT,
        initial_sent: int = 0,
        initial_received: int = 0,
        account_wire: Callable[[Literal["ipc_sent", "ipc_received"], int], Awaitable[None]]
        | None = None,
    ) -> None:
        if (
            not command
            or not math.isfinite(deadline)
            or deadline <= time.monotonic()
            or deadline - time.monotonic() > 10800
            or re.fullmatch(r"[a-f0-9]{64}", source_sha256) is None
            or any(
                type(value) is not int or not 0 <= value <= TOTAL_LIMIT
                for value in (initial_sent, initial_received)
            )
            or any(
                name in (os.environ if environment is None else environment)
                for name in ("PYTHONPATH", "PYTHONHOME")
            )
        ):
            raise EvaluationFailure("baseline_ipc_launch_invalid")
        self.command = tuple(command)
        self.source = source_sha256
        self.deadline, self.environment, self.cwd = deadline, environment, cwd
        self.process: asyncio.subprocess.Process | None = None
        self.request_fd: int | None = None
        self.response_fd: int | None = None
        self.sent, self.received, self.sequence = initial_sent, initial_received, 0
        self.account_wire = account_wire
        self.lock = asyncio.Lock()
        self.closed = False

    async def __aenter__(self) -> Self:
        request_read, request_write = os.pipe()
        response_read, response_write = os.pipe()
        self.request_fd, self.response_fd = request_write, response_read
        initial = (
            (
                "--initial-sent",
                str(self.received),
                "--initial-received",
                str(self.sent),
            )
            if self.sent or self.received
            else ()
        )
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                "--request-fd",
                str(request_read),
                "--response-fd",
                str(response_write),
                "--source-sha256",
                self.source,
                "--deadline",
                repr(self.deadline),
                *initial,
                pass_fds=(request_read, response_write),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=self.cwd,
                env=None if self.environment is None else dict(self.environment),
            )
        except OSError:
            await self.close()
            raise EvaluationFailure("baseline_ipc_launch_failed") from None
        except asyncio.CancelledError:
            await self.close()
            raise
        finally:
            os.close(request_read)
            os.close(response_write)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.process is not None and self.process.returncode is None:
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    await self.process.wait()
                try:
                    await asyncio.wait_for(self.process.wait(), 2)
                except TimeoutError:
                    self.process.kill()
                    await asyncio.wait_for(self.process.wait(), 2)
        finally:
            for descriptor in (self.request_fd, self.response_fd):
                if descriptor is not None:
                    os.close(descriptor)
            self.request_fd = self.response_fd = None

    def read_reply(self) -> PrivateFrame:
        if self.response_fd is None:
            raise EvaluationFailure("baseline_ipc_closed")
        header = read_exact(self.response_fd, 4)
        size = struct.unpack(">I", header)[0]
        if not 0 < size <= FRAME_LIMIT:
            raise EvaluationFailure("baseline_ipc_frame_limit")
        if self.received + 4 + size > TOTAL_LIMIT:
            raise EvaluationFailure("baseline_ipc_total_limit")
        self.received += 4 + size
        return decode_frame(read_exact(self.response_fd, size))

    async def send_frame(self, frame: PrivateFrame) -> None:
        if self.request_fd is None:
            raise EvaluationFailure("baseline_ipc_closed")
        data = frame_bytes(frame)
        if self.sent + len(data) > TOTAL_LIMIT:
            raise EvaluationFailure("baseline_ipc_total_limit")
        self.sent += len(data)
        if self.account_wire is not None:
            await self.account_wire("ipc_sent", len(data))
        await asyncio.to_thread(write_exact, self.request_fd, data)

    async def exchange(
        self,
        case_id: CaseToken,
        payload: dict[str, JsonValue],
        *,
        request_sha256: str,
        evidence_sha256: str,
        admit: Callable[[CaptureAdmission], Awaitable[None]] | None = None,
        on_failure: Callable[[str, str | None], None] | None = None,
    ) -> dict[str, JsonValue]:
        async with self.lock:
            if self.closed or self.process is None or self.request_fd is None:
                raise EvaluationFailure("baseline_ipc_closed")
            completed = False
            try:
                if time.monotonic() >= self.deadline:
                    raise EvaluationFailure("baseline_ipc_deadline")
                request = PrivateFrame(
                    protocol="baseline-capture-v1",
                    kind="request",
                    sequence=self.sequence,
                    nonce=secrets.token_hex(32),
                    case_id=case_id,
                    source_sha256=self.source,
                    request_sha256=request_sha256,
                    evidence_sha256=evidence_sha256,
                    payload_sha256=document_digest(payload),
                    payload=payload,
                )
                self.sequence += 1
                async with asyncio.timeout_at(self.deadline):
                    await self.send_frame(request)
                    for index in range(2049):
                        before = self.received
                        reply = await asyncio.to_thread(self.read_reply)
                        if self.account_wire is not None:
                            await self.account_wire("ipc_received", self.received - before)
                        if any(
                            getattr(reply, field) != getattr(request, field)
                            for field in (
                                "sequence",
                                "nonce",
                                "case_id",
                                "source_sha256",
                                "request_sha256",
                                "evidence_sha256",
                            )
                        ):
                            raise EvaluationFailure("baseline_ipc_reply_mismatch")
                        if reply.kind == "admission":
                            try:
                                event = CaptureAdmission.model_validate_json(
                                    json.dumps(reply.payload)
                                )
                            except ValueError:
                                raise EvaluationFailure("baseline_ipc_admission_invalid") from None
                            if admit is None or event.index != index:
                                raise EvaluationFailure("baseline_ipc_admission_invalid")
                            await admit(event)
                            permit = request.model_copy(
                                update={
                                    "kind": "permit",
                                    "payload": event.model_dump(mode="json"),
                                    "payload_sha256": document_digest(
                                        event.model_dump(mode="json")
                                    ),
                                }
                            )
                            await self.send_frame(permit)
                            continue
                        if reply.kind == "error":
                            if on_failure is not None:
                                cause = reply.payload.get("failure_sha256")
                                on_failure(
                                    str(reply.payload["category"]),
                                    cause if isinstance(cause, str) else None,
                                )
                            if reply.payload["category"] != "capture_worker_failed":
                                raise EvaluationFailure(
                                    "baseline_" + str(reply.payload["category"])
                                )
                            raise EvaluationFailure("baseline_ipc_worker_failed")
                        if reply.kind != "reply":
                            raise EvaluationFailure("baseline_ipc_reply_mismatch")
                        completed = True
                        return reply.payload
                    raise EvaluationFailure("baseline_ipc_admission_limit")
            except TimeoutError:
                raise EvaluationFailure("baseline_ipc_deadline") from None
            finally:
                if not completed:
                    await self.close()


async def probe_capture_environment() -> dict[str, object]:
    verify_production_inputs()
    python = ROOT / ".venv/bin/python"
    if not python.is_file():
        raise EvaluationFailure("baseline_capture_environment_missing")
    async with PrivateCaptureProcess(
        (str(python), "-m", "scripts.agent_quality_protocol"),
        source_sha256=capture_source_digest(),
        deadline=time.monotonic() + 10,
    ) as process:
        result = await process.exchange(
            "preflight",
            {"action": "probe", "probe": "baseline-protocol-self-test"},
            request_sha256="0" * 64,
            evidence_sha256="0" * 64,
        )
        if (
            set(result) != {"probe", "environment_sha256"}
            or result["probe"] != "baseline-protocol-self-test"
            or result["environment_sha256"]
            != hashlib.sha256(str(ROOT / ".venv").encode()).hexdigest()
        ):
            raise EvaluationFailure("baseline_capture_environment_mismatch")
        sent, received = process.sent, process.received
    return {
        "protocol": "baseline-capture-v1",
        "outcome": "validated",
        "messages": 1,
        "sent_bytes": sent,
        "received_bytes": received,
        "owned_process_closed": process.closed,
        "model_calls": 0,
    }
