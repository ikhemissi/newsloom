"""Private descriptor channel and network-free environment probe."""

import argparse
import hashlib
import json
import math
import os
import re
import select
import struct
import sys
import time
from collections.abc import Mapping

FRAME_LIMIT = 256 * 1024
TOTAL_LIMIT = 8 * 1024 * 1024
FIELDS = {
    "protocol",
    "kind",
    "sequence",
    "nonce",
    "case_id",
    "source_sha256",
    "request_sha256",
    "evidence_sha256",
    "payload_sha256",
    "payload",
}


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_field")
        result[key] = value
    return result


def read_exact(descriptor: int, size: int, deadline: float) -> bytes:
    value = bytearray()
    while len(value) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
            raise TimeoutError("protocol_deadline")
        part = os.read(descriptor, size - len(value))
        if not part:
            raise EOFError("protocol_closed")
        value.extend(part)
    return bytes(value)


def write_exact(descriptor: int, value: bytes, deadline: float) -> None:
    position = 0
    while position < len(value):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([], [descriptor], [], remaining)[1]:
            raise TimeoutError("protocol_deadline")
        size = os.write(descriptor, value[position : position + 4096])
        if size <= 0:
            raise EOFError("protocol_closed")
        position += size


def validate_request(
    value: object, source: str, sequence: int, *, kind: str = "request"
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("invalid_frame")
    if (
        value["protocol"] != "baseline-capture-v1"
        or value["kind"] != kind
        or type(value["sequence"]) is not int
        or value["sequence"] != sequence
        or value["source_sha256"] != source
        or not isinstance(value["case_id"], str)
        or re.fullmatch(r"(?:preflight|b0[1-9]|b1[0-2])", value["case_id"]) is None
        or any(
            not isinstance(value[field], str) or re.fullmatch(r"[a-f0-9]{64}", value[field]) is None
            for field in (
                "nonce",
                "source_sha256",
                "request_sha256",
                "evidence_sha256",
                "payload_sha256",
            )
        )
        or not isinstance(value["payload"], dict)
        or value["payload_sha256"] != digest(value["payload"])
    ):
        raise ValueError("invalid_frame")
    return value


class PrivateChannel:
    def __init__(
        self,
        request_fd: int,
        response_fd: int,
        source: str,
        deadline: float,
        *,
        sent: int = 0,
        received: int = 0,
    ) -> None:
        if (
            request_fd < 3
            or response_fd < 3
            or request_fd == response_fd
            or not math.isfinite(deadline)
            or not 0 < deadline - time.monotonic() <= 10800
            or re.fullmatch(r"[a-f0-9]{64}", source) is None
            or any(
                type(value) is not int or not 0 <= value <= TOTAL_LIMIT
                for value in (sent, received)
            )
        ):
            raise ValueError("invalid_private_channel")
        self.request_fd, self.response_fd = request_fd, response_fd
        self.source, self.deadline = source, deadline
        self.sent, self.received = sent, received
        self.sequence = self.index = 0
        self.error_category = "capture_worker_failed"
        self.request: dict[str, object] | None = None

    def read(self) -> object:
        size = struct.unpack(">I", read_exact(self.request_fd, 4, self.deadline))[0]
        if not 0 < size <= FRAME_LIMIT or self.received + size + 4 > TOTAL_LIMIT:
            raise ValueError("private_channel_limit")
        self.received += size + 4
        return json.loads(
            read_exact(self.request_fd, size, self.deadline), object_pairs_hook=unique_fields
        )

    def receive(self) -> dict[str, object]:
        if self.request is not None or self.sequence >= 2048:
            raise ValueError("private_channel_sequence")
        self.request = validate_request(self.read(), self.source, self.sequence)
        self.index = 0
        return self.request

    def send(self, kind: str, payload: Mapping[str, object]) -> None:
        payload = dict(payload)
        if self.request is None or kind not in ("reply", "error", "admission"):
            raise ValueError("private_channel_sequence")
        if kind == "error" and (
            set(payload) not in ({"category"}, {"category", "failure_sha256"})
            or (
                payload.get("failure_sha256") is not None
                and (
                    not isinstance(payload["failure_sha256"], str)
                    or re.fullmatch(r"[a-f0-9]{64}", payload["failure_sha256"]) is None
                )
            )
            or payload["category"]
            not in (
                "capture_not_approved",
                "capture_invalid_request",
                "capture_worker_failed",
                "capture_open_failed",
                "capture_pool_before_failed",
                "capture_research_failed",
                "capture_pool_after_failed",
                "capture_cleanup_failed",
            )
        ):
            raise ValueError("private_channel_error_category")
        value = {
            **self.request,
            "kind": kind,
            "payload": payload,
            "payload_sha256": digest(payload),
        }
        data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
        if not 0 < len(data) <= FRAME_LIMIT or self.sent + len(data) + 4 > TOTAL_LIMIT:
            raise ValueError("private_channel_limit")
        self.sent += len(data) + 4
        write_exact(self.response_fd, struct.pack(">I", len(data)) + data, self.deadline)
        if kind != "admission":
            self.request = None
            self.sequence += 1

    def admit(self, operation: str, amount: int = 1) -> None:
        if (
            self.request is None
            or self.index >= 2048
            or operation
            not in (
                "evidence",
                "semantic_evidence",
                "auth_http",
                "sign_ins",
                "task_reads",
                "metadata_before",
                "metadata_after",
                "evidence_bytes",
            )
            or type(amount) is not int
            or not 1 <= amount <= 64 * 1024
            or (operation != "evidence_bytes" and amount != 1)
        ):
            raise ValueError("private_channel_admission")
        event: dict[str, object] = {
            "index": self.index,
            "operation": operation,
            "amount": amount,
        }
        self.send("admission", event)
        permit = validate_request(self.read(), self.source, self.sequence, kind="permit")
        if (
            any(
                permit[key] != self.request[key]
                for key in FIELDS - {"kind", "payload", "payload_sha256"}
            )
            or permit["payload"] != event
            or time.monotonic() >= self.deadline
        ):
            raise ValueError("private_channel_permit")
        self.index += 1

    def close(self) -> None:
        os.close(self.request_fd)
        os.close(self.response_fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-fd", type=int, required=True)
    parser.add_argument("--response-fd", type=int, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--initial-sent", type=int, default=0)
    parser.add_argument("--initial-received", type=int, default=0)
    args = parser.parse_args()
    if (
        args.request_fd < 3
        or args.response_fd < 3
        or args.request_fd == args.response_fd
        or not math.isfinite(args.deadline)
        or not 0 < args.deadline - time.monotonic() <= 10800
        or re.fullmatch(r"[a-f0-9]{64}", args.source_sha256) is None
        or not 0 <= args.initial_sent <= TOTAL_LIMIT
        or not 0 <= args.initial_received <= TOTAL_LIMIT
    ):
        return 2
    received, sent = args.initial_received, args.initial_sent
    try:
        for sequence in range(2048):
            size = struct.unpack(">I", read_exact(args.request_fd, 4, args.deadline))[0]
            if not 0 < size <= FRAME_LIMIT or received + size + 4 > TOTAL_LIMIT:
                return 2
            received += size + 4
            value = validate_request(
                json.loads(
                    read_exact(args.request_fd, size, args.deadline),
                    object_pairs_hook=unique_fields,
                ),
                args.source_sha256,
                sequence,
            )
            payload = value["payload"]
            if (
                not isinstance(payload, dict)
                or set(payload) != {"action", "probe"}
                or payload["action"] != "probe"
                or not isinstance(payload["probe"], str)
            ):
                return 2
            reply = {
                **value,
                "kind": "reply",
                "payload": {
                    "probe": payload["probe"],
                    "environment_sha256": hashlib.sha256(sys.prefix.encode()).hexdigest(),
                },
            }
            reply["payload_sha256"] = digest(reply["payload"])
            data = json.dumps(reply, separators=(",", ":"), allow_nan=False).encode()
            if len(data) > FRAME_LIMIT or sent + len(data) + 4 > TOTAL_LIMIT:
                return 2
            sent += len(data) + 4
            write_exact(args.response_fd, struct.pack(">I", len(data)) + data, args.deadline)
    except EOFError:
        return 0
    except OSError, ValueError, TimeoutError, RecursionError:
        return 2
    finally:
        os.close(args.request_fd)
        os.close(args.response_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
