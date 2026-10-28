import asyncio
import hashlib
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

import httpx2
from azure.ai.projects.aio import AIProjectClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import AzureCliCredential
from openai import NotFoundError
from pydantic import Field, JsonValue, StrictBool, StrictInt, StrictStr, field_validator

from agent_evaluation.context import read_context
from agent_evaluation.foundry import CatalogTransport, ProjectTransport, project_endpoint
from agent_evaluation.inputs import StrictModel, json_document, source_digest
from agent_evaluation.policy import EvaluationFailure, verify_privacy
from agent_evaluation.runner import Digest, Journal, journal_lock, read_approval, read_file

Reference = Annotated[StrictStr, Field(pattern=r"^[a-zA-Z0-9_-]{1,256}$")]
Asset = Literal["run", "evaluation", "catalog"]


class CleanupApproval(StrictModel):
    schema_version: StrictInt = Field(ge=1, le=1)
    execution_approved: StrictBool
    source_sha256: Digest
    context_sha256: Digest
    historical_approval_sha256: Digest
    publication_state_sha256: Digest
    project_id: StrictStr
    project_endpoint: StrictStr
    origin: Literal["imported_deepeval_faithfulness", "newsloom_metadata_probe"]
    catalog_version: Reference
    evaluation_id: Reference | None
    run_id: Reference | None
    approved_at: datetime
    expires_at: datetime
    read_limit: StrictInt = Field(ge=60, le=60)
    mutation_limit: StrictInt = Field(ge=3, le=3)
    request_timeout_s: StrictInt = Field(ge=30, le=30)
    deadline_s: StrictInt = Field(ge=600, le=600)

    @field_validator("approved_at", "expires_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timezone_required")
        return value

    def validate_execution(self) -> None:
        verify_privacy()
        now = datetime.now(UTC)
        if (
            not self.execution_approved
            or not self.approved_at <= now < self.expires_at
            or not timedelta(0) < self.expires_at - self.approved_at <= timedelta(days=1)
            or self.source_sha256 != source_digest()
            or (self.run_id is not None and self.evaluation_id is None)
        ):
            raise EvaluationFailure("stale_or_unapproved_cleanup")

    def catalog(self) -> str:
        prefix = "newsloom_pilot_" if self.origin.startswith("imported_") else "newsloom_probe_"
        return prefix + self.historical_approval_sha256[:24]


class CleanupState(StrictModel):
    approval_sha256: Digest
    deadline: datetime
    reads: StrictInt = Field(ge=0, le=60)
    owned: tuple[Asset, ...]
    attempted: tuple[Asset, ...]
    removed: tuple[Asset, ...]
    outcome: Literal["pending", "owned_verified", "api_absence_verified", "failed"]


def load_cleanup(
    path: Path, manifest: Path, approved_sha256: str, *, registry: Path | None = None
) -> tuple[CleanupApproval, Journal, CleanupState]:
    data = read_approval(manifest)
    if hashlib.sha256(data).hexdigest() != approved_sha256:
        raise EvaluationFailure("cleanup_approval_digest_mismatch")
    json_document(data)
    approval = CleanupApproval.model_validate_json(data)
    approval.validate_execution()
    historical = read_approval(path / "approval.json")
    if hashlib.sha256(historical).hexdigest() != approval.historical_approval_sha256:
        raise EvaluationFailure("foreign_cleanup_journal")
    journal = Journal.reopen(path, approval.historical_approval_sha256, registry=registry)
    publication = read_file(path / "publication-state.json", 64 * 1024)
    value = json_document(publication)
    if (
        hashlib.sha256(publication).hexdigest() != approval.publication_state_sha256
        or not isinstance(value, dict)
        or value.get("configuration_sha256") != approval.historical_approval_sha256
        or not isinstance(value.get("mutations"), list)
        or value["mutations"]
        not in (["catalog"], ["catalog", "evaluation"], ["catalog", "evaluation", "run"])
    ):
        raise EvaluationFailure("foreign_cleanup_publication")
    for key in ("catalog_version", "evaluation_id", "run_id"):
        expected = getattr(approval, key)
        if value.get(key) is not None and value[key] != expected:
            raise EvaluationFailure("foreign_cleanup_reference")
    for key, stage in (("evaluation_id", "evaluation"), ("run_id", "run")):
        if (stage in value["mutations"]) != (getattr(approval, key) is not None):
            raise EvaluationFailure("missing_cleanup_reference")
    receipt = path / "publication.json"
    if (
        approval.origin == "imported_deepeval_faithfulness"
        and value.get("verification") == "api_verified"
        and not receipt.exists()
    ):
        raise EvaluationFailure("missing_cleanup_receipt")
    if receipt.exists():
        published = json_document(read_file(receipt, 64 * 1024))
        if (
            not isinstance(published, dict)
            or published.get("configuration_sha256") != approval.historical_approval_sha256
            or not isinstance(published.get("verified_at"), str)
        ):
            raise EvaluationFailure("foreign_cleanup_receipt")
        verified = datetime.fromisoformat(published["verified_at"])
        if verified.utcoffset() is None or datetime.now(UTC) < verified + timedelta(days=30):
            raise EvaluationFailure("evaluation_retention_window")
    state_path = path / "cleanup-state.json"
    if state_path.is_symlink():
        raise EvaluationFailure("foreign_cleanup_state")
    if state_path.exists():
        state_bytes = read_file(state_path, 16 * 1024)
        json_document(state_bytes)
        state = CleanupState.model_validate_json(state_bytes)
        expected_assets = {"catalog"}
        if approval.evaluation_id is not None:
            expected_assets.add("evaluation")
        if approval.run_id is not None:
            expected_assets.add("run")
        order = tuple(
            asset for asset in ("run", "evaluation", "catalog") if asset in expected_assets
        )
        if (
            state.approval_sha256 != approved_sha256
            or state.deadline.utcoffset() is None
            or state.deadline > approval.expires_at
            or state.deadline
            != min(approval.approved_at + timedelta(seconds=600), approval.expires_at)
            or not set(state.removed) <= set(state.attempted) <= set(state.owned) <= expected_assets
            or state.attempted != order[: len(state.attempted)]
            or state.removed != state.attempted[: len(state.removed)]
            or (state.owned and set(state.owned) != expected_assets)
            or any(
                len(set(values)) != len(values)
                for values in (state.owned, state.attempted, state.removed)
            )
        ):
            raise EvaluationFailure("foreign_cleanup_state")
    else:
        state = CleanupState(
            approval_sha256=approved_sha256,
            deadline=min(approval.approved_at + timedelta(seconds=600), approval.expires_at),
            reads=0,
            owned=(),
            attempted=(),
            removed=(),
            outcome="pending",
        )
    return approval, journal, state


class Cleaner:
    def __init__(
        self, approval: CleanupApproval, journal: Journal, state: CleanupState, *, delete: bool
    ) -> None:
        self.approval, self.journal, self.state, self.delete = approval, journal, state, delete
        self.prefix = httpx2.URL(approval.project_endpoint)
        root = self.prefix.path
        self.evals = root + "/openai/v1/evals"
        self.paths: dict[Asset, str] = {
            "catalog": root
            + "/evaluators/"
            + approval.catalog()
            + "/versions/"
            + approval.catalog_version
        }
        if approval.evaluation_id is not None:
            self.paths["evaluation"] = self.evals + "/" + approval.evaluation_id
        if approval.run_id is not None:
            self.paths["run"] = self.paths["evaluation"] + "/runs/" + approval.run_id
        self.deadline = time.monotonic() + self.remaining()

    def remaining(self) -> float:
        value = (self.state.deadline - datetime.now(UTC)).total_seconds()
        if hasattr(self, "deadline"):
            value = min(value, self.deadline - time.monotonic())
        if value <= 0:
            raise EvaluationFailure("cleanup_deadline")
        return value

    async def save(self, **updates: object) -> None:
        self.state = self.state.model_copy(update=updates)
        await self.journal.persist("cleanup-state.json", self.state.model_dump(mode="json"))

    def owns(self, value: object) -> bool:
        return isinstance(value, dict) and (
            value.get("configuration_sha256") == self.approval.historical_approval_sha256
            and value.get("origin") == self.approval.origin
        )

    async def admit(self, request: httpx2.Request) -> float:
        await asyncio.to_thread(self.approval.validate_execution)
        url = request.url
        if (url.scheme, url.host, url.port) != (
            self.prefix.scheme,
            self.prefix.host,
            self.prefix.port,
        ) or set(url.params.keys()) - {"api-version", "after", "limit", "order", "order_by"}:
            raise EvaluationFailure("cleanup_endpoint_rejected")
        self.remaining()
        if request.method == "GET" and url.path in (
            *self.paths.values(),
            self.evals,
            self.paths.get("evaluation", "") + "/runs",
        ):
            if self.state.reads >= self.approval.read_limit:
                raise EvaluationFailure("cleanup_read_limit")
            await self.save(reads=self.state.reads + 1)
        elif request.method == "DELETE" and url.path in self.paths.values():
            asset = next(key for key, path in self.paths.items() if path == url.path)
            if (
                not self.delete
                or asset not in self.state.owned
                or asset in self.state.attempted
                or len(self.state.attempted) >= self.approval.mutation_limit
            ):
                raise EvaluationFailure("cleanup_mutation_replay_rejected")
            await self.save(attempted=(*self.state.attempted, asset))
        else:
            raise EvaluationFailure("cleanup_endpoint_rejected")
        return min(self.remaining(), self.approval.request_timeout_s)

    def inspect(self, request: httpx2.Request, value: dict[str, JsonValue]) -> None:
        path = request.url.path
        if value.get("error"):
            raise EvaluationFailure("cleanup_service_error")
        if request.method == "DELETE":
            asset = next(key for key, target in self.paths.items() if target == path)
            key = "run_id" if asset == "run" else "eval_id"
            expected = self.approval.run_id if asset == "run" else self.approval.evaluation_id
            if value.get("deleted") is not True or value.get(key) != expected:
                raise EvaluationFailure("cleanup_deletion_unconfirmed")
        elif path in self.paths.values():
            asset = next(key for key, target in self.paths.items() if target == path)
            if not self.owns(value.get("metadata")):
                raise EvaluationFailure("foreign_cleanup_asset")
            if asset == "catalog":
                valid = value.get("version") == self.approval.catalog_version
            elif asset == "evaluation":
                valid = value.get("id") == self.approval.evaluation_id and (
                    value.get("name") == self.approval.catalog()
                )
            else:
                valid = (
                    value.get("id") == self.approval.run_id
                    and value.get("eval_id") == self.approval.evaluation_id
                    and value.get("status") in ("completed", "failed", "cancelled")
                )
            if not valid:
                raise EvaluationFailure("foreign_or_active_cleanup_asset")
        elif path == self.evals:
            rows = value.get("data")
            if not isinstance(rows, list) or type(value.get("has_more")) is not bool:
                raise EvaluationFailure("incomplete_cleanup_inventory")
            for row in rows:
                if not isinstance(row, dict):
                    raise EvaluationFailure("incomplete_cleanup_inventory")
                criteria = row.get("testing_criteria")
                if not isinstance(criteria, list):
                    raise EvaluationFailure("incomplete_cleanup_inventory")
                if row.get("id") != self.approval.evaluation_id and any(
                    isinstance(item, dict) and item.get("evaluator_name") == self.approval.catalog()
                    for item in criteria
                ):
                    raise EvaluationFailure("foreign_cleanup_dependency")

    async def exists(self, project: AIProjectClient, asset: Asset) -> bool:
        a = self.approval
        async with project.get_openai_client(
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=ProjectTransport(
                    httpx2.AsyncHTTPTransport(retries=0, trust_env=False), self.admit, self.inspect
                ),
                trust_env=False,
                follow_redirects=False,
            ),
        ) as client:
            try:
                if asset == "catalog":
                    await project.evaluators.get_version(a.catalog(), a.catalog_version)
                elif asset == "evaluation":
                    assert a.evaluation_id is not None
                    await client.evals.retrieve(a.evaluation_id)
                else:
                    assert a.run_id is not None and a.evaluation_id is not None
                    await client.evals.runs.retrieve(a.run_id, eval_id=a.evaluation_id)
            except ResourceNotFoundError, NotFoundError:
                if asset not in self.state.attempted or asset not in self.state.owned:
                    raise EvaluationFailure("missing_cleanup_ownership") from None
                return False
        if asset in self.state.attempted:
            raise EvaluationFailure("cleanup_deletion_unconfirmed")
        return True

    async def execute(self, project: AIProjectClient) -> dict[str, object]:
        a = self.approval
        present: list[Asset] = []
        for asset in self.paths:
            if await self.exists(project, asset):
                present.append(asset)
            elif asset not in self.state.removed:
                await self.save(removed=(*self.state.removed, asset))
        await self.save(owned=tuple(self.paths))
        async with project.get_openai_client(
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=ProjectTransport(
                    httpx2.AsyncHTTPTransport(retries=0, trust_env=False), self.admit, self.inspect
                ),
                trust_env=False,
                follow_redirects=False,
            ),
        ) as client:
            async for _ in client.evals.list(limit=100):
                pass
            if "evaluation" in present:
                assert a.evaluation_id is not None
                initial_runs = [
                    row.id async for row in client.evals.runs.list(a.evaluation_id, limit=100)
                ]
                if initial_runs != ([a.run_id] if "run" in present else []):
                    raise EvaluationFailure("foreign_cleanup_runs")
            for asset in ("run", "evaluation", "catalog"):
                if asset not in present:
                    continue
                if asset == "evaluation":
                    assert a.evaluation_id is not None
                    runs = [
                        row.id async for row in client.evals.runs.list(a.evaluation_id, limit=100)
                    ]
                    expected = (
                        [a.run_id]
                        if "run" in present and a.run_id is not None and not self.delete
                        else []
                    )
                    if sorted(runs) != sorted(expected):
                        raise EvaluationFailure("foreign_cleanup_runs")
                if not self.delete:
                    continue
                if asset == "run":
                    assert a.run_id is not None and a.evaluation_id is not None
                    await client.evals.runs.delete(a.run_id, eval_id=a.evaluation_id)
                elif asset == "evaluation":
                    assert a.evaluation_id is not None
                    await client.evals.delete(a.evaluation_id)
                else:
                    await project.evaluators.delete_version(a.catalog(), a.catalog_version)
                if await self.exists(project, asset):
                    raise EvaluationFailure("cleanup_deletion_unconfirmed")
                await self.save(removed=(*self.state.removed, asset))
        outcome = (
            "api_absence_verified"
            if set(self.state.removed) == set(self.paths)
            else "owned_verified"
        )
        await self.save(outcome=outcome)
        receipt: dict[str, object] = {
            "outcome": outcome,
            "assets": len(self.paths),
            "reads": self.state.reads,
            "mutations": len(self.state.attempted),
            "model_calls": 0,
            "verified_at": datetime.now(UTC).isoformat(),
            "backup_erasure_verified": False,
            "approval_sha256": self.state.approval_sha256,
        }
        await self.journal.persist("cleanup.json", receipt)
        return receipt


async def cleanup(
    path: Path, manifest: Path, approved_sha256: str, *, delete: bool = False
) -> dict[str, object]:
    await asyncio.to_thread(load_cleanup, path, manifest, approved_sha256)
    lock = await asyncio.to_thread(journal_lock, path)
    cleaner: Cleaner | None = None
    completed = False
    try:
        approval, journal, state = await asyncio.to_thread(
            load_cleanup, path, manifest, approved_sha256
        )
        cleaner = Cleaner(approval, journal, state, delete=delete)
        await cleaner.save(outcome="pending")
        async with asyncio.timeout(cleaner.remaining()):
            context = await read_context()
            if (
                context.digest() != approval.context_sha256
                or context.environment["AGENT_EVALUATION_PROJECT_ID"] != approval.project_id
                or project_endpoint(
                    context.environment["AGENT_EVALUATION_PROJECT_ENDPOINT"],
                    context.environment["MODEL_ENDPOINT"],
                    approval.project_id,
                )
                != approval.project_endpoint
            ):
                raise EvaluationFailure("cleanup_context_mismatch")
            transport = CatalogTransport(
                ProjectTransport(
                    httpx2.AsyncHTTPTransport(retries=0, trust_env=False),
                    cleaner.admit,
                    cleaner.inspect,
                )
            )
            async with (
                AzureCliCredential(tenant_id=context.environment["AGENT_TENANT_ID"]) as credential,
                AIProjectClient(
                    endpoint=approval.project_endpoint,
                    credential=credential,
                    allow_preview=True,
                    retry_total=0,
                    redirect_max=0,
                    transport=transport,
                ) as project,
            ):
                receipt = await cleaner.execute(project)
                completed = True
                return receipt
    finally:
        try:
            if cleaner is not None and not completed:
                await cleaner.save(outcome="failed")
        finally:
            await asyncio.to_thread(lock.close)
