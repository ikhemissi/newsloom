import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Self

import httpx2
import pytest
from azure.core.exceptions import AzureError
from fakes import Credential
from openai import OpenAIError
from pydantic import ValidationError
from test_publication import Service, selected_context, setup
from test_runner import approval_data

from agent_evaluation import cleanup as module
from agent_evaluation.cleanup import cleanup, load_cleanup
from agent_evaluation.context import Context
from agent_evaluation.inputs import source_digest
from agent_evaluation.policy import EvaluationFailure
from agent_evaluation.publication import publish
from agent_evaluation.runner import Journal, journal_lock


class Clock(datetime):
    @classmethod
    def now(cls, tz: object = None) -> Self:
        return cls.fromtimestamp((datetime.now(UTC) + timedelta(days=35)).timestamp(), UTC)


class DeleteService:
    def __init__(self, base: Service) -> None:
        self.base = base
        self.requests: list[httpx2.Request] = []
        self.unknown: str | None = None
        self.foreign_runs = False
        self.foreign_dependency = False
        self.keep: str | None = None
        self.bad_ack = False
        self.ack_shape = "complete"
        self.pending_deletions: dict[str, int] = {}
        self.async_poll_reads = 2

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        assert request.url.host == "evaluation-test.services.ai.azure.com"
        assert request.headers["Foundry-Features"] == "Evaluations=V1Preview"
        assert request.headers.get("authorization") == "Bearer evaluation-test-entra-token"
        assert "api-key" not in request.headers
        path = request.url.path
        assert "/evaluators/" not in path
        asset = "run" if path.endswith("/run_pilot") else "evaluation"
        if request.method == "GET" and asset in self.pending_deletions:
            self.pending_deletions[asset] -= 1
            if self.pending_deletions[asset] == 0:
                setattr(self.base, asset, None)
                del self.pending_deletions[asset]
        value = getattr(self.base, asset)
        if request.method == "DELETE":
            if self.ack_shape == "async":
                self.pending_deletions[asset] = self.async_poll_reads
            elif self.keep != asset:
                setattr(self.base, asset, None)
            if self.unknown == asset:
                self.unknown = None
                raise httpx2.ReadTimeout("synthetic-delete-error-canary", request=request)
            key = "run_id" if asset == "run" else "eval_id"
            acknowledgement: dict[str, object] = {
                "object": "eval.deleted",
                "deleted": 1 if self.bad_ack else True,
                key: "run_pilot" if asset == "run" else "eval_pilot",
            }
            if self.ack_shape == "omitted":
                acknowledgement = {}
            elif self.ack_shape == "null":
                acknowledgement = {"deleted": None, key: None}
            elif self.ack_shape == "id":
                acknowledgement = {"id": acknowledgement[key], "deleted": True}
            elif self.ack_shape == "foreign_id":
                acknowledgement["id"] = "foreign"
            elif self.ack_shape == "false":
                acknowledgement["deleted"] = False
            elif self.ack_shape == "async":
                acknowledgement.update(deleted=False, location="opaque-provider-operation")
            return httpx2.Response(200, json=acknowledgement)
        assert request.method == "GET"
        if path.endswith("/evals") or path.endswith("/runs"):
            is_run = path.endswith("/runs")
            retained = self.base.run if is_run else self.base.evaluation
            rows = [retained] if retained is not None else []
            if is_run and self.foreign_runs:
                assert self.base.run is not None
                rows.append({**self.base.run, "id": "run_foreign", "metadata": {}})
            if not is_run and self.foreign_dependency:
                assert self.base.evaluation is not None
                rows.append({**self.base.evaluation, "id": "eval_foreign", "metadata": {}})
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": rows,
                    "has_more": False,
                },
            )
        if value is None:
            return httpx2.Response(
                404,
                json={
                    "error": {
                        "code": "NotFound",
                        "message": "synthetic-absent-canary",
                    }
                },
            )
        return httpx2.Response(200, json=value)


async def prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, str, DeleteService]:
    path, historical, service = await setup(tmp_path, monkeypatch)
    await publish(path, historical)
    deletion = DeleteService(service)

    def inner(**kwargs: object) -> httpx2.MockTransport:
        return httpx2.MockTransport(deletion.respond)

    async def read_context() -> Context:
        return selected_context()

    def credential(*, tenant_id: str, process_timeout: int) -> Credential:
        assert process_timeout == 30
        return Credential()

    original = load_cleanup

    def load(
        directory: Path, manifest: Path, digest: str
    ) -> tuple[module.CleanupApproval, Journal, module.CleanupState]:
        return original(directory, manifest, digest, registry=tmp_path / "registry")

    monkeypatch.setattr(module, "load_cleanup", load)
    monkeypatch.setattr(module, "read_context", read_context)
    monkeypatch.setattr(module, "AzureCliCredential", credential)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", inner)
    monkeypatch.setattr(module, "datetime", Clock)
    now = Clock.now()
    context = selected_context()
    approval = {
        "schema_version": 2,
        "publication_protocol": "native-python",
        "execution_approved": True,
        "source_sha256": source_digest(),
        "context_sha256": context.digest(),
        "historical_approval_sha256": historical,
        "publication_state_sha256": hashlib.sha256(
            (path / "publication-state.json").read_bytes()
        ).hexdigest(),
        "project_id": context.environment["AGENT_EVALUATION_PROJECT_ID"],
        "project_endpoint": context.environment["AGENT_EVALUATION_PROJECT_ENDPOINT"],
        "origin": "imported_deepeval_faithfulness",
        "catalog_version": None,
        "evaluation_id": "eval_pilot",
        "run_id": "run_pilot",
        "approved_at": (now - timedelta(seconds=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "read_limit": 60,
        "mutation_limit": 2,
        "request_timeout_s": 30,
        "deadline_s": 600,
    }
    manifest = tmp_path / "cleanup-approval.json"
    data = json.dumps(approval).encode()
    manifest.write_bytes(data)
    return path, manifest, hashlib.sha256(data).hexdigest(), deletion


def replace_approval(manifest: Path, **updates: object) -> str:
    data = json.loads(manifest.read_bytes())
    manifest.write_bytes(json.dumps(data | updates).encode())
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


async def test_native_cleanup_defaults_to_reads_then_deletes_exact_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    result_bytes = (path / "results.json").read_bytes()
    receipt = await cleanup(path, manifest, digest)
    assert receipt["outcome"] == "owned_verified"
    assert all(request.method == "GET" for request in service.requests)
    first_reads = receipt["reads"]
    receipt = await cleanup(path, manifest, digest, delete=True)
    assert receipt["outcome"] == "api_absence_verified"
    assert receipt["mutations"] == 2
    assert receipt["model_calls"] == 0
    assert receipt["backup_erasure_verified"] is False
    assert int(str(receipt["reads"])) > int(str(first_reads))
    deletes = [r for r in service.requests if r.method == "DELETE"]
    assert [r.url.path.rsplit("/", 1)[-1] for r in deletes] == ["run_pilot", "eval_pilot"]
    assert not any(r.url.path.endswith("/evals") for r in service.requests)
    assert (path / "results.json").read_bytes() == result_bytes
    assert (path / "cleanup.json").stat().st_mode & 0o777 == 0o600
    before = len(deletes)
    again = await cleanup(path, manifest, digest, delete=True)
    assert again["outcome"] == "api_absence_verified"
    assert len([r for r in service.requests if r.method == "DELETE"]) == before


@pytest.mark.parametrize("asset", ["evaluation", "run"])
async def test_foreign_or_missing_owner_stops_before_deletion(
    asset: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    value = getattr(service.base, asset)
    value["metadata"] = {}
    with pytest.raises(EvaluationFailure, match="foreign_cleanup_asset"):
        await cleanup(path, manifest, digest, delete=True)
    assert not [r for r in service.requests if r.method == "DELETE"]


@pytest.mark.parametrize("asset", ["evaluation", "run"])
async def test_unknown_delete_is_reconciled_without_replaying_mutation(
    asset: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.unknown = asset
    with pytest.raises((httpx2.HTTPError, OpenAIError, AzureError)):
        await cleanup(path, manifest, digest, delete=True)
    assert json.loads((path / "cleanup-state.json").read_bytes())["outcome"] == "failed"
    first = len([r for r in service.requests if r.method == "DELETE"])
    await cleanup(path, manifest, digest)
    assert len([r for r in service.requests if r.method == "DELETE"]) == first
    receipt = await cleanup(path, manifest, digest, delete=True)
    assert receipt["outcome"] == "api_absence_verified"
    assert len([r for r in service.requests if r.method == "DELETE"]) == 2


async def test_unconfirmed_delete_is_not_replayed_or_reported_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.keep = "run"
    for _ in range(2):
        with pytest.raises(EvaluationFailure, match="cleanup_deletion_unconfirmed"):
            await cleanup(path, manifest, digest, delete=True)
    assert len([r for r in service.requests if r.method == "DELETE"]) == 1
    assert not (path / "cleanup.json").exists()


@pytest.mark.parametrize("change", ["foreign_runs"])
async def test_foreign_dependencies_are_rejected_before_any_mutation(
    change: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    setattr(service, change, True)
    with pytest.raises(EvaluationFailure, match="foreign_cleanup"):
        await cleanup(path, manifest, digest, delete=True)
    assert all(r.method == "GET" for r in service.requests)


async def test_missing_asset_is_not_claimed_as_owned_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.base.run = None
    with pytest.raises(EvaluationFailure, match="missing_cleanup_ownership"):
        await cleanup(path, manifest, digest, delete=True)
    assert all(r.method == "GET" for r in service.requests)


async def test_accepted_report_is_retained_for_thirty_days(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    receipt = json.loads((path / "publication.json").read_bytes())
    receipt["verified_at"] = Clock.now().isoformat()
    (path / "publication.json").write_text(json.dumps(receipt))
    with pytest.raises(EvaluationFailure, match="evaluation_retention_window"):
        await cleanup(path, manifest, digest, delete=True)
    assert not service.requests


async def test_historical_source_and_expired_scoring_approval_do_not_block_fresh_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, _, service = await prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "source_digest", lambda: "b" * 64)
    digest = replace_approval(manifest, source_sha256="b" * 64)
    receipt = await cleanup(path, manifest, digest, delete=True)
    assert receipt["outcome"] == "api_absence_verified"
    assert len([r for r in service.requests if r.method == "DELETE"]) == 2


async def test_publication_and_cleanup_share_the_same_exclusive_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    lock = journal_lock(path)
    try:
        with pytest.raises(EvaluationFailure, match="publication_already_running"):
            await cleanup(path, manifest, digest, delete=True)
    finally:
        lock.close()
    assert not service.requests


@pytest.mark.parametrize(
    ("field", "value", "category"),
    [
        ("execution_approved", False, "stale_or_unapproved_cleanup"),
        ("source_sha256", "b" * 64, "stale_or_unapproved_cleanup"),
        ("historical_approval_sha256", "b" * 64, "foreign_cleanup_journal"),
        ("publication_state_sha256", "b" * 64, "foreign_cleanup_publication"),
        ("evaluation_id", "eval_foreign", "foreign_cleanup_reference"),
        ("run_id", None, "foreign_cleanup_reference"),
        ("catalog_version", "2", "stale_or_unapproved_cleanup"),
        ("project_endpoint", "https://example.com", "cleanup_context_mismatch"),
        ("context_sha256", "b" * 64, "cleanup_context_mismatch"),
    ],
)
async def test_exact_approval_and_scope_are_required_before_network(
    field: str,
    value: object,
    category: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, _, service = await prepare(tmp_path, monkeypatch)
    digest = replace_approval(manifest, **{field: value})
    with pytest.raises(EvaluationFailure, match=category):
        await cleanup(path, manifest, digest, delete=True)
    assert not service.requests


async def test_boolean_delete_ack_is_checked_before_sdk_coercion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.bad_ack = True
    with pytest.raises(EvaluationFailure, match="cleanup_deletion_unconfirmed"):
        await cleanup(path, manifest, digest, delete=True)
    assert len([r for r in service.requests if r.method == "DELETE"]) == 1
    receipt = await cleanup(path, manifest, digest)
    assert receipt["outcome"] == "owned_verified"


async def test_owned_failed_run_error_is_not_an_authorization_failure_for_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    assert service.base.run is not None
    service.base.run.update(
        status="failed", error={"code": "UserError", "message": "synthetic-failure"}
    )
    result = await cleanup(path, manifest, digest, delete=True)
    assert result["outcome"] == "api_absence_verified"
    assert result["mutations"] == 2


async def test_failed_run_with_foreign_metadata_does_not_bypass_service_error_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    assert service.base.run is not None
    service.base.run.update(status="failed", metadata={}, error={"code": "PermissionDenied"})
    with pytest.raises(EvaluationFailure, match="cleanup_service_error"):
        await cleanup(path, manifest, digest, delete=True)
    assert all(request.method == "GET" for request in service.requests)


@pytest.mark.parametrize("shape", ["omitted", "null", "id"])
async def test_optional_delete_ack_fields_require_independent_absence(
    shape: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.ack_shape = shape
    result = await cleanup(path, manifest, digest, delete=True)
    assert result["outcome"] == "api_absence_verified"
    assert result["mutations"] == 2
    assert sum(request.method == "DELETE" for request in service.requests) == 2


@pytest.mark.parametrize("shape", ["omitted", "null", "id"])
async def test_optional_ack_never_substitutes_for_absence(
    shape: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.ack_shape = shape
    service.keep = "run"
    with pytest.raises(EvaluationFailure, match="cleanup_deletion_unconfirmed"):
        await cleanup(path, manifest, digest, delete=True)
    assert sum(request.method == "DELETE" for request in service.requests) == 1


@pytest.mark.parametrize("shape", ["foreign_id", "false"])
async def test_conflicting_delete_ack_is_rejected(
    shape: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.ack_shape = shape
    with pytest.raises(EvaluationFailure, match="cleanup_deletion_unconfirmed"):
        await cleanup(path, manifest, digest, delete=True)
    assert sum(request.method == "DELETE" for request in service.requests) == 1


async def test_async_delete_polls_only_owned_targets_without_replaying_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.ack_shape = "async"
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    result = await cleanup(path, manifest, digest, delete=True)
    assert result["outcome"] == "api_absence_verified"
    assert result["mutations"] == 2
    assert waits == [5, 5]
    assert sum(request.method == "DELETE" for request in service.requests) == 2
    assert service.base.run is service.base.evaluation is None


async def test_async_delete_polling_cannot_exceed_cumulative_read_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    service.ack_shape = "async"
    service.async_poll_reads = 1000

    async def sleep(seconds: float) -> None:
        assert seconds == 5

    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(EvaluationFailure, match="cleanup_read_limit"):
        await cleanup(path, manifest, digest, delete=True)
    assert sum(request.method == "GET" for request in service.requests) == 60
    assert sum(request.method == "DELETE" for request in service.requests) == 1
    state = json.loads((path / "cleanup-state.json").read_bytes())
    assert state["attempted"] == ["run"] and state["removed"] == []


async def test_sixty_reads_are_cumulative_across_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    with pytest.raises(EvaluationFailure, match="cleanup_read_limit"):
        for _ in range(20):
            await cleanup(path, manifest, digest)
    assert len(service.requests) == 60
    assert all(r.method == "GET" for r in service.requests)
    assert json.loads((path / "cleanup-state.json").read_bytes())["reads"] == 60
    with pytest.raises(EvaluationFailure, match="cleanup_read_limit"):
        await cleanup(path, manifest, digest, delete=True)
    assert len(service.requests) == 60


async def test_missing_accepted_receipt_does_not_skip_retention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    (path / "publication.json").unlink()
    with pytest.raises(EvaluationFailure, match="missing_cleanup_receipt"):
        await cleanup(path, manifest, digest, delete=True)
    assert not service.requests


async def test_cleanup_deadline_is_original_approval_time_not_restart_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    await cleanup(path, manifest, digest)
    before = len(service.requests)
    state = json.loads((path / "cleanup-state.json").read_bytes())

    class Later(Clock):
        @classmethod
        def now(cls, tz: object = None) -> Self:
            return cls.fromtimestamp(Clock.now().timestamp() + 601, UTC)

    monkeypatch.setattr(module, "datetime", Later)
    with pytest.raises(EvaluationFailure, match=r"stale_or_unapproved_cleanup|cleanup_deadline"):
        await cleanup(path, manifest, digest, delete=True)
    assert len(service.requests) == before
    assert json.loads((path / "cleanup-state.json").read_bytes()) == state


async def test_cached_instrumentation_blocks_publication_and_cleanup_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deepeval.config.settings import get_settings

    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    monkeypatch.setitem(get_settings().__dict__, "ENABLE_DEEPEVAL_CACHE", True)
    with pytest.raises(EvaluationFailure, match="evaluation_runtime_privacy_changed"):
        await cleanup(path, manifest, digest, delete=True)
    historical = json.loads(manifest.read_bytes())["historical_approval_sha256"]
    with pytest.raises(EvaluationFailure, match="evaluation_runtime_privacy_changed"):
        await publish(path, historical)
    assert not service.requests


@pytest.mark.parametrize("status", [202, 204, 206])
async def test_non_object_success_cannot_establish_asset_ownership(
    status: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)

    def respond(request: httpx2.Request) -> httpx2.Response:
        service.requests.append(request)
        return httpx2.Response(status)

    monkeypatch.setattr(service, "respond", respond)
    with pytest.raises(EvaluationFailure, match="publication_unexpected_success_status"):
        await cleanup(path, manifest, digest, delete=True)
    assert len(service.requests) == 1
    assert service.requests[0].method == "GET"


async def test_native_cleanup_rejects_catalog_protocol_without_touching_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, _, service = await prepare(tmp_path, monkeypatch)
    original = (path / "publication-state.json").read_bytes()
    digest = replace_approval(
        manifest, publication_protocol="catalog-v1", catalog_version="1", mutation_limit=3
    )
    with pytest.raises(EvaluationFailure, match="foreign_cleanup_protocol"):
        await cleanup(path, manifest, digest, delete=True)
    assert not service.requests
    assert (path / "publication-state.json").read_bytes() == original


async def test_native_protocol_marker_is_part_of_cleanup_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, digest, service = await prepare(tmp_path, monkeypatch)
    assert service.base.evaluation is not None
    metadata = service.base.evaluation["metadata"]
    assert isinstance(metadata, dict)
    metadata.pop("grader_protocol")
    with pytest.raises(EvaluationFailure, match="foreign_cleanup_asset"):
        await cleanup(path, manifest, digest, delete=True)
    assert all(r.method == "GET" for r in service.requests)


async def test_old_cleanup_manifest_cannot_silently_adopt_native_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, manifest, _, service = await prepare(tmp_path, monkeypatch)
    digest = replace_approval(manifest, schema_version=1)
    with pytest.raises(ValidationError):
        await cleanup(path, manifest, digest, delete=True)
    assert not service.requests


async def test_explicit_legacy_cleanup_retains_the_exact_catalog_only_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = selected_context()
    data = approval_data()
    data.update(schema_version=1, publication_mutation_limit=3)
    data.pop("publication_protocol")
    producer = json.dumps(data).encode()
    historical = hashlib.sha256(producer).hexdigest()
    path, registry = tmp_path / "legacy", tmp_path / "registry"
    journal = Journal(path, historical, registry=registry)
    journal.write_bytes("approval.json", producer)
    journal.write(
        "publication-state.json",
        {
            "configuration_sha256": historical,
            "mutations": ["catalog"],
            "pending": "catalog",
            "catalog_version": None,
            "evaluation_id": None,
            "run_id": None,
            "verification": "failed",
        },
    )
    original = (path / "publication-state.json").read_bytes()
    now = datetime.now(UTC)
    approval = module.CleanupApproval(
        schema_version=2,
        publication_protocol="catalog-v1",
        execution_approved=True,
        source_sha256=source_digest(),
        context_sha256=context.digest(),
        historical_approval_sha256=historical,
        publication_state_sha256=hashlib.sha256(original).hexdigest(),
        project_id=context.environment["AGENT_EVALUATION_PROJECT_ID"],
        project_endpoint=context.environment["AGENT_EVALUATION_PROJECT_ENDPOINT"],
        origin="newsloom_metadata_probe",
        catalog_version="1",
        evaluation_id=None,
        run_id=None,
        approved_at=now,
        expires_at=now + timedelta(minutes=10),
        read_limit=60,
        mutation_limit=3,
        request_timeout_s=30,
        deadline_s=600,
    )
    manifest = tmp_path / "legacy-cleanup.json"
    encoded = approval.model_dump_json().encode()
    manifest.write_bytes(encoded)
    original_load = load_cleanup

    def load(
        directory: Path, manifest: Path, digest: str
    ) -> tuple[module.CleanupApproval, Journal, module.CleanupState]:
        return original_load(directory, manifest, digest, registry=registry)

    requests: list[httpx2.Request] = []
    deleted = False

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal deleted
        requests.append(request)
        if request.url.path.endswith("/evals"):
            return httpx2.Response(200, json={"data": [], "has_more": False})
        assert request.url.path.endswith("/evaluators/" + approval.catalog() + "/versions/1")
        if request.method == "DELETE":
            deleted = True
            return httpx2.Response(204)
        if deleted:
            return httpx2.Response(404, json={"error": {"code": "NotFound"}})
        return httpx2.Response(
            200,
            json={
                "version": "1",
                "metadata": {
                    "configuration_sha256": historical,
                    "origin": "newsloom_metadata_probe",
                },
            },
        )

    async def read_context() -> Context:
        return context

    monkeypatch.setattr(module, "load_cleanup", load)
    monkeypatch.setattr(module, "read_context", read_context)
    monkeypatch.setattr(module, "AzureCliCredential", lambda **kwargs: Credential())
    monkeypatch.setattr(
        httpx2, "AsyncHTTPTransport", lambda **kwargs: httpx2.MockTransport(respond)
    )
    result = await cleanup(path, manifest, hashlib.sha256(encoded).hexdigest(), delete=True)
    assert result["outcome"] == "api_absence_verified"
    assert result["publication_protocol"] == "catalog-v1"
    assert result["mutations"] == 1
    assert [r.method for r in requests] == ["GET", "GET", "DELETE", "GET"]
    assert (path / "publication-state.json").read_bytes() == original
