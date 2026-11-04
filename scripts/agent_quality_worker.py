"""Approved baseline capture over private descriptors; credentials stay in this process."""

import argparse
import asyncio
import hashlib
import json
import time
from contextlib import AsyncExitStack, suppress
from typing import Annotated, Literal
from uuid import UUID

import httpx
import httpx2
from newsloom_agent.client import RESEARCH_CLIENT_FAILURES
from newsloom_agent.models import AgentFailure
from newsloom_agent.research_models import ResearchContract, ResearchRequest, SearchResults
from newsloom_agent.telemetry import CATEGORIES
from pydantic import Field, JsonValue, StrictBool, field_validator

from scripts.agent_quality_capture import (
    CaptureLimits,
    CaptureSettings,
    EvidenceReader,
    capture_denial,
    capture_research,
    configure_operator_browser,
    evidence_session,
    fingerprint,
    public_admission,
    sign_in_agent,
)
from scripts.agent_quality_protocol import PrivateChannel, digest

Digest = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
Alias = Annotated[str, Field(strict=True, pattern=r"^(?:n[1-9]|n_missing)$")]


class Open(ResearchContract):
    action: Literal["open"]
    protocol: Literal["baseline-v1"]
    limit_profile: Literal[
        "baseline-12x8-v1",
        "baseline-12x8-v2",
        "baseline-12x8-v3",
        "baseline-12x8-v4",
        "baseline-12x8-v5",
        "baseline-12x8-v6",
    ] = "baseline-12x8-v1"
    execution_approved: StrictBool
    approval_sha256: Digest
    frozen_sha256: Digest
    actor_sha256: Digest
    environment: dict[str, str] = Field(repr=False)

    @field_validator("environment")
    @classmethod
    def only_capture_configuration(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != {
            "AGENT_TENANT_ID",
            "AGENT_API_CLIENT_ID",
            "MCP_API_CLIENT_ID",
            "MCP_RESOURCE_URL",
            "AGENT_PUBLIC_CLIENT_ID",
            "AGENT_RESOURCE_URL",
            "MCP_TENANT_ID",
            "MCP_PUBLIC_CLIENT_ID",
        }:
            raise ValueError("baseline_capture_environment_fields")
        return value


class Binding(ResearchContract):
    alias: Alias
    item_id: UUID
    present: StrictBool
    fingerprint: Digest | None


class Capture(ResearchContract):
    action: Literal["capture"]
    request: ResearchRequest = Field(repr=False)
    items: tuple[Binding, ...] = Field(max_length=10)
    pool_sha256: Digest | None
    expected_status: Literal[200, 401, 403]
    wrong_audience: StrictBool


async def verify_pool(reader: EvidenceReader, command: Capture) -> None:
    if command.pool_sha256 is None:
        return
    result = await reader.call(
        "search_news",
        {
            **command.request.filters.model_dump(mode="json", by_alias=True),
            "query": None,
            "limit": 5,
        },
    )
    if not isinstance(result, SearchResults) or len(result.items) >= 5:
        raise AgentFailure("baseline_capture_pool_incomplete")
    metadata = [
        item.model_dump(mode="json", exclude={"similarity"})
        for item in sorted(result.items, key=lambda value: str(value.id))
    ]
    if digest(metadata) != command.pool_sha256 or {item.id for item in result.items} != {
        item.item_id for item in command.items if item.present
    }:
        raise AgentFailure("baseline_capture_evidence_drift")


async def serve(channel: PrivateChannel) -> None:
    channel.error_category = "capture_open_failed"
    opening = await asyncio.to_thread(channel.receive)
    approved = Open.model_validate_json(json.dumps(opening["payload"]))
    if (
        not approved.execution_approved
        or opening["case_id"] != "preflight"
        or opening["request_sha256"] != approved.frozen_sha256
        or opening["evidence_sha256"] != approved.actor_sha256
    ):
        raise AgentFailure("baseline_capture_not_approved")
    settings = CaptureSettings.from_environment(approved.environment)
    limits = CaptureLimits(
        deadline=channel.deadline, permit=channel.admit, limit_profile=approved.limit_profile
    )
    async with AsyncExitStack() as stack:
        public = await stack.enter_async_context(
            httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30)
        )
        token, caller = await sign_in_agent(settings, public, limits)
        actor = fingerprint({"oid": str(caller.object_id), "tenant": str(caller.tenant)})
        if actor != approved.actor_sha256:
            raise AgentFailure("baseline_capture_user_mismatch")
        reader = await stack.enter_async_context(
            evidence_session(settings, caller, limits, readiness=False)
        )
        channel.send("reply", {"actor_sha256": actor})
        attempted: set[str] = set()
        while True:
            frame = await asyncio.to_thread(channel.receive)
            raw = frame["payload"]
            if raw == {"action": "close"} and frame["case_id"] == "preflight":
                channel.error_category = "capture_cleanup_failed"
                # Close while admission permits are still available for owned MCP cleanup.
                await stack.aclose()
                channel.send("reply", {"closed": True})
                return
            command = Capture.model_validate_json(json.dumps(raw))
            channel.error_category = "capture_pool_before_failed"
            case = frame["case_id"]
            if not isinstance(case, str) or case == "preflight" or case in attempted:
                raise AgentFailure("baseline_capture_case_replay")
            attempted.add(case)
            evidence_document = {
                "items": [row.model_dump(mode="json") for row in command.items],
                "pool_sha256": command.pool_sha256,
            }
            if (
                digest(command.request.model_dump(mode="json", by_alias=True))
                != frame["request_sha256"]
                or digest(evidence_document) != frame["evidence_sha256"]
                or len({row.item_id for row in command.items}) != len(command.items)
                or any(row.present != (row.fingerprint is not None) for row in command.items)
            ):
                raise AgentFailure("baseline_capture_binding_mismatch")

            started = time.monotonic()
            async with asyncio.timeout_at(min(channel.deadline, started + 120)):
                await verify_pool(reader, command)
                channel.error_category = "capture_research_failed"
                if command.expected_status != 200:
                    async with public_admission(settings, public, limits):
                        if command.wrong_audience:
                            if reader.denial is None:
                                raise AgentFailure("baseline_capture_token_missing")
                            status = await reader.denial(
                                public, command.request, command.expected_status
                            )
                        else:
                            status = await capture_denial(
                                settings,
                                public,
                                command.request,
                                expected_status=command.expected_status,
                                wrong_audience_token=None,
                            )
                    reply: dict[str, JsonValue] = {
                        "answer": None,
                        "evidence": [],
                        "http_status": status,
                        "receipt": None,
                    }
                else:
                    result = await capture_research(
                        settings,
                        token,
                        public,
                        reader,
                        command.request,
                        {row.item_id: row.fingerprint for row in command.items},
                    )
                    aliases = {row.item_id: row.alias for row in command.items}
                    reply = {
                        "answer": result.invocation.text,
                        "evidence": [
                            {
                                "alias": aliases[item.id],
                                "item": item.model_dump(mode="json"),
                            }
                            for item in result.evidence
                        ],
                        "http_status": 200,
                        "receipt": (
                            None
                            if result.invocation.receipt is None
                            else result.invocation.receipt.model_dump(mode="json")
                        ),
                    }
                channel.error_category = "capture_pool_after_failed"
                await verify_pool(reader, command)
            reply["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            channel.send("reply", reply)


def safe_failure_digest(error: BaseException) -> str | None:
    pending = [error]
    categories: set[str] = set()
    allowed = (
        CATEGORIES
        | RESEARCH_CLIENT_FAILURES
        | {
            "baseline_capture_evidence_drift",
            "baseline_capture_research_dispatch_limit",
            "baseline_capture_research_dispatch_incomplete",
            "baseline_capture_response_limit",
            "baseline_capture_user_mismatch",
            "baseline_capture_arguments_invalid",
        }
    )
    while pending:
        leaf = pending.pop()
        if isinstance(leaf, BaseExceptionGroup):
            pending.extend(leaf.exceptions)
        elif isinstance(leaf, AgentFailure) and str(leaf) in allowed:
            categories.add(str(leaf))
    return (
        hashlib.sha256(next(iter(categories)).encode()).hexdigest()
        if len(categories) == 1
        else None
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-fd", type=int, required=True)
    parser.add_argument("--response-fd", type=int, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--initial-sent", type=int, default=0)
    parser.add_argument("--initial-received", type=int, default=0)
    args = parser.parse_args()
    configure_operator_browser()
    channel = PrivateChannel(
        args.request_fd,
        args.response_fd,
        args.source_sha256,
        args.deadline,
        sent=args.initial_sent,
        received=args.initial_received,
    )
    try:
        asyncio.run(serve(channel))
    except (
        AgentFailure,
        OSError,
        ValueError,
        TimeoutError,
        EOFError,
        httpx.HTTPError,
        httpx2.HTTPError,
        BaseExceptionGroup,
    ) as error:
        if channel.request is not None:
            failure = safe_failure_digest(error)
            with suppress(OSError, ValueError, TimeoutError, EOFError):
                channel.send(
                    "error",
                    {
                        "category": channel.error_category,
                        "failure_sha256": failure,
                    },
                )
        return 1
    finally:
        channel.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
