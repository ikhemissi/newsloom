import asyncio
import fcntl
import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, BinaryIO, Literal

from azure.identity.aio import AzureCliCredential
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator

from agent_evaluation.budget import MODEL_SNAPSHOT, Budget, BudgetReceipt, Prices
from agent_evaluation.context import read_context
from agent_evaluation.inputs import (
    FIXTURE_SHA256,
    ROOT,
    StrictModel,
    json_document,
    load_pilot,
    source_digest,
)
from agent_evaluation.judge import Completion, model_client
from agent_evaluation.metric import measure
from agent_evaluation.policy import EvaluationFailure, verify_privacy

Digest = Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Approval(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    execution_approved: StrictBool
    source_sha256: Digest
    fixture_sha256: Digest
    context_sha256: Digest
    approved_at: datetime
    expires_at: datetime
    price_verified_at: datetime
    input_per_million_usd: StrictStr
    output_per_million_usd: StrictStr
    publication_read_limit: StrictInt = Field(ge=60, le=60)
    publication_mutation_limit: StrictInt = Field(ge=3, le=3)
    publication_request_timeout_s: StrictInt = Field(ge=30, le=30)
    publication_poll_spacing_s: StrictInt = Field(ge=5, le=5)

    @field_validator("approved_at", "expires_at", "price_verified_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timezone_required")
        return value

    def validate_execution(self, now: datetime) -> Prices:
        verify_privacy()
        if (
            not self.execution_approved
            or not self.approved_at <= now < self.expires_at
            or self.expires_at - self.approved_at > timedelta(days=1)
            or not timedelta(0) <= now - self.price_verified_at <= timedelta(days=1)
            or self.fixture_sha256 != FIXTURE_SHA256
            or self.source_sha256 != source_digest()
        ):
            raise EvaluationFailure("stale_or_unapproved_execution")
        try:
            return Prices(Decimal(self.input_per_million_usd), Decimal(self.output_per_million_usd))
        except InvalidOperation:
            raise EvaluationFailure("invalid_evaluation_prices") from None


class MeasuredCase(StrictModel):
    case_id: Literal["p01", "p02"]
    score: StrictFloat = Field(ge=0, le=1, allow_inf_nan=False)
    reason: StrictStr

    @field_validator("reason")
    @classmethod
    def bounded_reason(cls, value: str) -> str:
        if not value.strip() or not 1 <= len(value.encode()) <= 4096:
            raise ValueError("invalid_synthetic_reason")
        return value


class PilotResult(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    source_sha256: Digest
    fixture_sha256: Digest
    metric_sha256: Digest
    configuration_sha256: Digest
    context_sha256: Digest
    judge_snapshot: Literal["gpt-5.4-mini-2026-03-17"]
    started_at: datetime
    deadline: datetime
    cases: tuple[MeasuredCase, MeasuredCase]
    budget: BudgetReceipt


class Journal:
    def __init__(self, path: Path, approval_sha256: str, *, registry: Path | None = None) -> None:
        if path.absolute() != path.resolve() or path.parent.stat().st_mode & 0o022:
            raise EvaluationFailure("unsafe_evaluation_output_directory")
        if path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / ".azure"):
            raise EvaluationFailure("evaluation_output_must_be_private")
        self.path = path
        if registry is None:
            registry = ROOT / ".azure" / "agent-evaluation"
        registry.mkdir(mode=0o700, exist_ok=True)
        if (
            registry.absolute() != registry.resolve()
            or registry.stat().st_uid != os.getuid()
            or registry.stat().st_mode & 0o022
        ):
            raise EvaluationFailure("unsafe_evaluation_registry")
        sync_directory(registry.parent)
        descriptor = os.open(
            registry / (approval_sha256 + ".json"),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"approval_sha256": approval_sha256, "journal": str(path)}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(registry)
        path.mkdir(mode=0o700)
        sync_directory(path.parent)

    @classmethod
    def reopen(cls, path: Path, approval_sha256: str, *, registry: Path | None = None) -> Journal:
        if (
            path.absolute() != path.resolve()
            or path.stat().st_uid != os.getuid()
            or path.stat().st_mode & 0o077
            or not path.is_dir()
        ):
            raise EvaluationFailure("unsafe_evaluation_output_directory")
        if registry is None:
            registry = ROOT / ".azure" / "agent-evaluation"
        if (
            registry.absolute() != registry.resolve()
            or registry.stat().st_uid != os.getuid()
            or registry.stat().st_mode & 0o077
        ):
            raise EvaluationFailure("unsafe_evaluation_registry")
        data = read_file(registry / (approval_sha256 + ".json"), 16 * 1024)
        if json_document(data) != {"approval_sha256": approval_sha256, "journal": str(path)}:
            raise EvaluationFailure("foreign_evaluation_journal")
        instance = cls.__new__(cls)
        instance.path = path
        return instance

    def write(self, name: str, value: dict[str, object]) -> None:
        self.write_bytes(name, json.dumps(value, sort_keys=True, allow_nan=False).encode())

    async def persist(self, name: str, value: dict[str, object]) -> None:
        task = asyncio.create_task(asyncio.to_thread(self.write, name, value))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    def write_bytes(self, name: str, data: bytes) -> None:
        if name not in (
            "approval.json",
            "budget.json",
            "partial-results.json",
            "results.json",
            "publication-state.json",
            "publication.json",
            "cleanup-state.json",
            "cleanup.json",
        ):
            raise EvaluationFailure("foreign_evaluation_journal_target")
        temporary = self.path / (name + ".next")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path / name)
            sync_directory(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()


def metric_digest() -> str:
    value = {
        "metric": "FaithfulnessMetric",
        "deepeval": version("deepeval"),
        "eval_mode": "llm",
        "async_mode": True,
        "include_reason": True,
        "judge_snapshot": MODEL_SNAPSHOT,
        "max_completion_tokens": 1024,
        "reasoning_effort": "none",
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def read_file(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise EvaluationFailure("invalid_evaluation_manifest_file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise EvaluationFailure("invalid_evaluation_manifest_file")
    return data


def read_approval(path: Path) -> bytes:
    return read_file(path, 16 * 1024)


def journal_lock(path: Path) -> BinaryIO:
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(directory)
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise EvaluationFailure("unsafe_evaluation_output_directory")
        descriptor = os.open(
            "publication.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
    finally:
        os.close(directory)
    stream = os.fdopen(descriptor, "r+b")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        raise EvaluationFailure("publication_already_running") from None
    return stream


async def score(manifest: Path, approved_sha256: str, output: Path) -> PilotResult:
    data = await asyncio.to_thread(read_approval, manifest)
    digest = hashlib.sha256(data).hexdigest()
    if digest != approved_sha256:
        raise EvaluationFailure("execution_approval_digest_mismatch")
    json_document(data)
    approval = Approval.model_validate_json(data)
    started = datetime.now(UTC)
    prices = await asyncio.to_thread(approval.validate_execution, started)
    pilot = await asyncio.to_thread(load_pilot)
    journal = await asyncio.to_thread(Journal, output, digest)
    await asyncio.to_thread(journal.write_bytes, "approval.json", data)
    deadline = min(started + timedelta(minutes=30), approval.expires_at)

    async def persist(receipt: BudgetReceipt) -> None:
        await journal.persist(
            "budget.json",
            {
                "configuration_sha256": digest,
                "source_sha256": approval.source_sha256,
                "fixture_sha256": approval.fixture_sha256,
                "started_at": started.isoformat(),
                "deadline": deadline.isoformat(),
                "budget": receipt.model_dump(mode="json"),
            },
        )

    budget = Budget(prices, persist=persist)
    budget.deadline = min(
        budget.deadline, budget.clock() + (deadline - datetime.now(UTC)).total_seconds()
    )
    await budget.checkpoint()
    rows: list[MeasuredCase] = []
    completed = False
    try:
        async with asyncio.timeout(budget.remaining()):
            context = await read_context()
            if context.digest() != approval.context_sha256:
                raise EvaluationFailure("execution_context_digest_mismatch")

            async def ready() -> None:
                await asyncio.to_thread(approval.validate_execution, datetime.now(UTC))
                await context.ensure_ready()

            budget.ready = ready
            async with (
                AzureCliCredential(tenant_id=context.environment["AGENT_TENANT_ID"]) as credential,
                model_client(
                    context.environment["MODEL_ENDPOINT"],
                    context.environment["ENRICHMENT_DEPLOYMENT"],
                    credential,
                    budget,
                ) as client,
            ):
                completion = Completion(
                    client, context.environment["ENRICHMENT_DEPLOYMENT"], budget
                )
                for case in pilot.cases:
                    value, reason = await measure(
                        completion,
                        question=pilot.question,
                        evidence=pilot.evidence,
                        answer=case.answer,
                    )
                    rows.append(MeasuredCase(case_id=case.case_id, score=value, reason=reason))
                    await journal.persist(
                        "partial-results.json",
                        {
                            "outcome": "partial",
                            "expected_cases": 2,
                            "configuration_sha256": digest,
                            "cases": [row.model_dump(mode="json") for row in rows],
                        },
                    )
            await asyncio.to_thread(approval.validate_execution, datetime.now(UTC))
            budget.remaining()
            result = PilotResult(
                schema_version=1,
                source_sha256=approval.source_sha256,
                fixture_sha256=FIXTURE_SHA256,
                metric_sha256=metric_digest(),
                configuration_sha256=digest,
                context_sha256=approval.context_sha256,
                judge_snapshot=MODEL_SNAPSHOT,
                started_at=started,
                deadline=deadline,
                cases=(rows[0], rows[1]),
                budget=budget.receipt(),
            )
            await journal.persist("results.json", result.model_dump(mode="json"))
            completed = True
            return result
    finally:
        if not completed:
            budget.halted = True
        await budget.checkpoint()
