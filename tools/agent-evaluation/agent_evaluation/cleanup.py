import asyncio
import hashlib
import re
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
    schema_version: StrictInt = Field(ge=2, le=2)
    publication_protocol: Literal["native-python", "catalog-v1"]
    execution_approved: StrictBool
    source_sha256: Digest
    context_sha256: Digest
    historical_approval_sha256: Digest
    publication_state_sha256: Digest
    project_id: StrictStr
    project_endpoint: StrictStr
    origin: Literal["imported_deepeval_faithfulness", "newsloom_metadata_probe"]
    catalog_version: Reference | None
    evaluation_id: Reference | None
    run_id: Reference | None
    approved_at: datetime
    expires_at: datetime
    read_limit: StrictInt = Field(ge=60, le=60)
    mutation_limit: StrictInt = Field(ge=2, le=3)
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
            or (
                self.publication_protocol == "native-python"
                and (
                    self.catalog_version is not None
                    or self.mutation_limit != 2
                    or self.evaluation_id is None
                )
            )
            or (
                self.publication_protocol == "catalog-v1"
                and (self.catalog_version is None or self.mutation_limit != 3)
            )
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
    delete_acknowledgement: dict[str, JsonValue] | None = None


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
    producer = json_document(historical)
    if (
        not isinstance(producer, dict)
        or (
            approval.publication_protocol == "native-python"
            and (
                producer.get("schema_version") != 2
                or producer.get("publication_protocol") != "native-python"
            )
        )
        or (
            approval.publication_protocol == "catalog-v1"
            and (
                producer.get("schema_version") != 1
                or producer.get("publication_protocol") is not None
            )
        )
    ):
        raise EvaluationFailure("foreign_cleanup_protocol")
    journal = Journal.reopen(path, approval.historical_approval_sha256, registry=registry)
    publication = read_file(path / "publication-state.json", 64 * 1024)
    value = json_document(publication)
    native = approval.publication_protocol == "native-python"
    stages = ("evaluation", "run") if native else ("catalog", "evaluation", "run")
    if (
        hashlib.sha256(publication).hexdigest() != approval.publication_state_sha256
        or not isinstance(value, dict)
        or value.get("configuration_sha256") != approval.historical_approval_sha256
        or not isinstance(value.get("mutations"), list)
        or value["mutations"] not in [list(stages[:count]) for count in range(1, len(stages) + 1)]
        or (
            native
            and (
                value.get("schema_version") != 2
                or value.get("publication_protocol") != "native-python"
                or "catalog_version" in value
            )
        )
        or (not native and value.get("publication_protocol") is not None)
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
        expected_assets = set() if native else {"catalog"}
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
        self.paths: dict[Asset, str] = {}
        if approval.publication_protocol == "catalog-v1":
            assert approval.catalog_version is not None
            self.paths["catalog"] = (
                root + "/evaluators/" + approval.catalog() + "/versions/" + approval.catalog_version
            )
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
            and (
                self.approval.publication_protocol == "catalog-v1"
                or value.get("grader_protocol") == "native-python"
            )
        )

    async def admit(self, request: httpx2.Request) -> float:
        if self.approval.publication_protocol == "native-python":
            request.headers["Foundry-Features"] = "Evaluations=V1Preview"
        await asyncio.to_thread(self.approval.validate_execution)
        url = request.url
        if (url.scheme, url.host, url.port) != (
            self.prefix.scheme,
            self.prefix.host,
            self.prefix.port,
        ) or set(url.params.keys()) - {"api-version", "after", "limit", "order", "order_by"}:
            raise EvaluationFailure("cleanup_endpoint_rejected")
        self.remaining()
        allowed_reads = {*self.paths.values()}
        if "catalog" in self.paths:
            allowed_reads.add(self.evals)
        if "evaluation" in self.paths:
            allowed_reads.add(self.paths["evaluation"] + "/runs")
        if request.method == "GET" and url.path in allowed_reads:
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
        owned_terminal_failure = (
            request.method == "GET"
            and path == self.paths.get("run")
            and value.get("id") == self.approval.run_id
            and value.get("eval_id") == self.approval.evaluation_id
            and value.get("status") in ("failed", "cancelled")
            and self.owns(value.get("metadata"))
        )
        if value.get("error") and not owned_terminal_failure:
            raise EvaluationFailure("cleanup_service_error")
        if request.method == "DELETE":
            asset = next(key for key, target in self.paths.items() if target == path)
            key = "run_id" if asset == "run" else "eval_id"
            expected = self.approval.run_id if asset == "run" else self.approval.evaluation_id
            references: dict[str, JsonValue] = {}
            for field in (key, "id"):
                returned = value.get(field)
                if isinstance(returned, str) and re.fullmatch(
                    r"(?:eval|evalrun)_[A-Za-z0-9_-]{1,240}", returned
                ):
                    references[field] = returned
            deleted = value.get("deleted")
            location = value.get("location")
            asynchronous = deleted is False and isinstance(location, str) and bool(location)
            self.state = self.state.model_copy(
                update={
                    "delete_acknowledgement": {
                        "asset": asset,
                        "keys": sorted(value),
                        "deleted_type": type(value.get("deleted")).__name__,
                        "deleted": deleted if type(deleted) is bool else None,
                        "asynchronous": asynchronous,
                        "location_type": type(location).__name__,
                        "references": references,
                        "reference_types": {
                            field: type(value.get(field)).__name__ for field in (key, "id")
                        },
                        "empty_reference_fields": [
                            field for field in (key, "id") if value.get(field) == ""
                        ],
                        "expected_reference_matches": value.get(key) == expected,
                    }
                }
            )
            if (
                value.get("deleted") is not None
                and value["deleted"] is not True
                and not asynchronous
            ) or any(
                value.get(field) is not None and value[field] != expected for field in (key, "id")
            ):
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
        elif path == self.evals or path == self.paths.get("evaluation", "") + "/runs":
            rows = value.get("data")
            if not isinstance(rows, list) or type(value.get("has_more")) is not bool:
                raise EvaluationFailure("incomplete_cleanup_inventory")
            if value["has_more"] and (
                not rows
                or not isinstance(rows[-1], dict)
                or not isinstance(rows[-1].get("id"), str)
                or value.get("last_id") != rows[-1]["id"]
            ):
                raise EvaluationFailure("incomplete_cleanup_inventory")
            for row in rows:
                if not isinstance(row, dict):
                    raise EvaluationFailure("incomplete_cleanup_inventory")
                if path != self.evals:
                    continue
                criteria = row.get("testing_criteria")
                if not isinstance(criteria, list):
                    raise EvaluationFailure("incomplete_cleanup_inventory")
                if row.get("id") != self.approval.evaluation_id and any(
                    isinstance(item, dict) and item.get("evaluator_name") == self.approval.catalog()
                    for item in criteria
                ):
                    raise EvaluationFailure("foreign_cleanup_dependency")

    async def exists(
        self, project: AIProjectClient, asset: Asset, *, pending_deletion: bool = False
    ) -> bool:
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
                    assert a.catalog_version is not None
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
        if asset in self.state.attempted and not pending_deletion:
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
            if "catalog" in self.paths:
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
                    assert a.catalog_version is not None
                    await project.evaluators.delete_version(a.catalog(), a.catalog_version)
                acknowledgement = self.state.delete_acknowledgement
                asynchronous = (
                    acknowledgement is not None and acknowledgement.get("asynchronous") is True
                )
                while await self.exists(project, asset, pending_deletion=asynchronous):
                    if not asynchronous:
                        raise EvaluationFailure("cleanup_deletion_unconfirmed")
                    if self.remaining() <= 5:
                        raise EvaluationFailure("cleanup_deadline")
                    await asyncio.sleep(5)
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
            "publication_protocol": self.approval.publication_protocol,
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
                AzureCliCredential(
                    tenant_id=context.environment["AGENT_TENANT_ID"], process_timeout=30
                ) as credential,
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
