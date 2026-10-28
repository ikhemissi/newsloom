import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from azure.core.exceptions import AzureError
from fakes import PROJECT_ENDPOINT, TOKEN, Credential
from openai import APIConnectionError
from pydantic import ValidationError
from test_budget import PRICES
from test_runner import approval_data

from agent_evaluation import publication
from agent_evaluation.budget import MODEL_SNAPSHOT, Budget, Usage
from agent_evaluation.context import BOUND_ENVIRONMENT, Context
from agent_evaluation.grader import grade
from agent_evaluation.inputs import FIXTURE_SHA256
from agent_evaluation.policy import EvaluationFailure
from agent_evaluation.publication import Bundle, Publisher, load_bundle, publish
from agent_evaluation.runner import Journal, MeasuredCase, PilotResult, metric_digest


class Service:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.catalog: dict[str, object] | None = None
        self.evaluation: dict[str, object] | None = None
        self.run: dict[str, object] | None = None
        self.rows: list[dict[str, object]] = []
        self.timeout_run = False
        self.timeout_stage: str | None = None
        self.change: str | None = None

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "evaluation-test.services.ai.azure.com"
        assert request.headers["authorization"] == "Bearer " + TOKEN
        assert "api-key" not in request.headers
        self.requests.append(request)
        path = request.url.path
        if "/evaluators/" in path:
            if request.method == "POST":
                if self.change == "catalog_denied":
                    return httpx2.Response(
                        401,
                        json={
                            "error": {
                                "message": "synthetic-provider-error-canary",
                            }
                        },
                    )
                if self.change == "catalog_redirect":
                    return httpx2.Response(302, headers={"location": "https://example.com/foreign"})
                body = json.loads(request.content)
                self.catalog = {**body, "version": "1", "id": "evaluator_pilot"}
                if self.timeout_stage == "catalog":
                    self.timeout_stage = None
                    raise httpx2.ReadTimeout("synthetic-provider-error-canary", request=request)
                return httpx2.Response(201, json=self.catalog)
            return httpx2.Response(200, json={"value": [self.catalog]})
        if path.endswith("/output_items"):
            index = 1 if request.url.params.get("after") == "item_one" else 0
            row = dict(self.rows[index])
            if self.change == "duplicate" and index == 1:
                row = dict(self.rows[0])
            if self.change == "stale" and index == 1:
                row["source_sha256"] = "b" * 64
            metric: dict[str, object] = {
                "name": publication.ORIGIN,
                "score": row["score"],
                "passed": index == 0,
            }
            if self.change == "boolean":
                metric["score"] = True
            if self.change == "nan":
                metric["score"] = float("nan")
            if self.change == "range":
                metric["score"] = 1.01
            if self.change == "sandbox":
                metric["score"] = 0.0
                metric["error"] = {"message": "synthetic-provider-error-canary"}
            identifier = "item_two" if index else "item_one"
            return httpx2.Response(
                200,
                headers={"content-type": "application/json"},
                content=json.dumps(
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": identifier,
                                "object": "eval.run.output_item",
                                "created_at": 1,
                                "eval_id": "eval_pilot",
                                "run_id": "run_pilot",
                                "datasource_item_id": index,
                                "datasource_item": row,
                                "status": "pass" if index == 0 else "fail",
                                "results": [metric],
                                "sample": {},
                            }
                        ],
                        "first_id": identifier,
                        "last_id": identifier,
                        "has_more": index == 0 and self.change != "missing",
                    }
                ),
            )
        if path.endswith("/evals"):
            if request.method == "GET":
                return httpx2.Response(
                    200,
                    json={
                        "object": "list",
                        "data": [self.evaluation],
                        "first_id": "eval_pilot",
                        "last_id": "eval_pilot",
                        "has_more": False,
                    },
                )
            body = json.loads(request.content)
            self.evaluation = {
                **body,
                "id": "eval_pilot",
                "object": "eval",
                "created_at": 1,
            }
            if self.timeout_stage == "evaluation":
                self.timeout_stage = None
                raise httpx2.ReadTimeout("synthetic-provider-error-canary", request=request)
            return httpx2.Response(200, json=self.evaluation)
        if path.endswith("/runs"):
            if request.method == "GET":
                return httpx2.Response(
                    200,
                    json={
                        "object": "list",
                        "data": [self.run],
                        "first_id": "run_pilot",
                        "last_id": "run_pilot",
                        "has_more": False,
                    },
                )
            body = json.loads(request.content)
            self.rows = [entry["item"] for entry in body["data_source"]["source"]["content"]]
            self.run = {
                **body,
                "id": "run_pilot",
                "object": "eval.run",
                "created_at": 1,
                "eval_id": "eval_pilot",
                "status": "completed",
                "report_url": "https://ai.azure.com/synthetic-report",
                "result_counts": {"errored": 0, "passed": 1, "failed": 1, "total": 2},
            }
            if self.timeout_run:
                self.timeout_run = False
                raise httpx2.ReadTimeout("synthetic-provider-error-canary", request=request)
            return httpx2.Response(200, json=self.run)
        if path.endswith("/run_pilot") and self.change in ("queued", "run_failed"):
            assert self.run is not None
            return httpx2.Response(
                200,
                json=self.run
                | {
                    "status": "queued" if self.change == "queued" else "failed",
                },
            )
        if path.endswith("/eval_pilot") and self.change == "definition":
            assert self.evaluation is not None
            return httpx2.Response(200, json=self.evaluation | {"testing_criteria": []})
        return httpx2.Response(
            200, json=self.run if path.endswith("/run_pilot") else self.evaluation
        )


def selected_context() -> Context:
    class LocalContext(Context):
        async def verify_deployment(self) -> None:
            return None

    environment = dict.fromkeys(BOUND_ENVIRONMENT, "synthetic")
    environment["MODEL_ENDPOINT"] = "https://evaluation-test.services.ai.azure.com"
    environment["AGENT_EVALUATION_PROJECT_ENDPOINT"] = PROJECT_ENDPOINT
    environment["AGENT_EVALUATION_PROJECT_ID"] = (
        "/subscriptions/synthetic/accounts/shared/projects/pilot"
    )
    return LocalContext(environment, "synthetic")


async def setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, age_minutes: int = 0
) -> tuple[Path, str, Service]:
    context = selected_context()
    data = approval_data()
    started = datetime.now(UTC) - timedelta(minutes=age_minutes)
    if age_minutes:
        data["approved_at"] = (started - timedelta(seconds=2)).isoformat()
        data["price_verified_at"] = (started - timedelta(seconds=1)).isoformat()
    data["context_sha256"] = context.digest()
    encoded = json.dumps(data).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    registry = tmp_path / "registry"
    path = tmp_path / "pilot"
    journal = Journal(path, digest, registry=registry)
    journal.write_bytes("approval.json", encoded)
    budget = Budget(PRICES)
    for _ in range(8):
        row = await budget.admit(100)
        budget.consume(row, 200)
        row.response_complete = True
        budget.observe(row, Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    now = started
    result = PilotResult(
        schema_version=1,
        source_sha256=str(data["source_sha256"]),
        fixture_sha256=FIXTURE_SHA256,
        metric_sha256=metric_digest(),
        configuration_sha256=digest,
        context_sha256=context.digest(),
        judge_snapshot=MODEL_SNAPSHOT,
        started_at=now,
        deadline=now + timedelta(minutes=30),
        cases=(
            MeasuredCase(case_id="p01", score=1.0, reason="Synthetic supported explanation."),
            MeasuredCase(case_id="p02", score=0.0, reason="Synthetic unsupported explanation."),
        ),
        budget=budget.receipt(),
    )
    journal.write("results.json", result.model_dump(mode="json"))
    service = Service()
    original_load = load_bundle

    def load(directory: Path, approved_sha256: str) -> Bundle:
        return original_load(directory, approved_sha256, registry=registry)

    async def read_context() -> Context:
        return context

    def credential(*, tenant_id: str) -> Credential:
        return Credential()

    def inner(**kwargs: object) -> httpx2.MockTransport:
        return httpx2.MockTransport(service.respond)

    monkeypatch.setattr(publication, "load_bundle", load)
    monkeypatch.setattr(publication, "read_context", read_context)
    monkeypatch.setattr(publication, "AzureCliCredential", credential)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", inner)
    return path, digest, service


async def test_real_native_catalog_and_evaluation_sdk_preserve_both_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    original = (path / "results.json").read_bytes()
    receipt = await publish(path, digest)
    assert receipt["outcome"] == "api_verified"
    assert receipt["ui_verified"] is False
    assert receipt["cases"] == 2
    assert [row["score"] for row in service.rows] == [1.0, 0.0]
    assert [row["case_id"] for row in service.rows] == ["p01", "p02"]
    assert all(row["metric_origin"] == publication.ORIGIN for row in service.rows)
    assert [row["reason"] for row in service.rows] == [
        "Synthetic supported explanation.",
        "Synthetic unsupported explanation.",
    ]
    assert len([r for r in service.requests if r.method == "POST"]) == 3
    assert all(r.headers["accept-encoding"] == "identity" for r in service.requests)
    assert len([r for r in service.requests if r.url.path.endswith("/output_items")]) == 2
    assert (path / "results.json").read_bytes() == original
    assert json.loads((path / "publication-state.json").read_bytes())["pending"] is None
    assert (path / "publication.json").stat().st_mode & 0o777 == 0o600


async def test_ambiguous_submission_reconciles_using_reads_only_and_keeps_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    original = (path / "results.json").read_bytes()
    service.timeout_run = True
    with pytest.raises(APIConnectionError):
        await publish(path, digest)
    state = json.loads((path / "publication-state.json").read_bytes())
    assert state["pending"] == "run"
    assert state["run_id"] is None
    checkpoint = len(service.requests)
    receipt = await publish(path, digest)
    assert receipt["outcome"] == "api_verified"
    assert all(request.method == "GET" for request in service.requests[checkpoint:])
    assert len([r for r in service.requests if r.method == "POST"]) == 3
    assert (path / "results.json").read_bytes() == original
    assert receipt["budget"] == json.loads(original)["budget"]


@pytest.mark.parametrize(
    "change", ["boolean", "nan", "range", "sandbox", "duplicate", "stale", "missing"]
)
async def test_failed_or_malformed_readback_is_never_a_valid_zero(
    change: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.change = change
    with pytest.raises((EvaluationFailure, ValidationError)):
        await publish(path, digest)
    assert not (path / "publication.json").exists()


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), -0.01, 1.01, "1"])
def test_sandbox_code_has_no_success_shaped_invalid_input_fallback(value: object) -> None:
    with pytest.raises(ValueError):
        grade({}, {"score": value})


def test_imported_score_code_does_not_rejudge_or_reinterpret() -> None:
    assert grade({}, {"score": 0.0}) == 0.0
    assert grade({}, {"score": 0.375}) == 0.375
    assert grade({}, {"score": 1}) == 1.0


async def test_read_budget_persists_at_exact_limit_and_does_not_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, _ = await setup(tmp_path, monkeypatch)
    bundle = publication.load_bundle(path, digest)
    context = selected_context()
    publisher = Publisher(bundle, context)
    publisher.state = publisher.state.model_copy(
        update={
            "reads": 59,
            "evaluation_id": "eval_pilot",
            "mutations": ("catalog", "evaluation"),
            "catalog_version": "1",
        }
    )
    await publisher.admit(httpx2.Request("GET", PROJECT_ENDPOINT + "/openai/v1/evals/eval_pilot"))
    assert publisher.state.reads == 60
    recovered = Publisher(publication.load_bundle(path, digest), context)
    with pytest.raises(EvaluationFailure, match="publication_read_limit"):
        await recovered.admit(
            httpx2.Request("GET", PROJECT_ENDPOINT + "/openai/v1/evals/eval_pilot")
        )


async def test_foreign_endpoints_never_dispatch_or_consume_mutation_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, _ = await setup(tmp_path, monkeypatch)
    publisher = Publisher(publication.load_bundle(path, digest), selected_context())
    with pytest.raises(EvaluationFailure, match="publication_endpoint_rejected"):
        await publisher.admit(httpx2.Request("POST", "https://example.com/openai/v1/evals"))
    assert publisher.state.mutations == ()


@pytest.mark.parametrize("change", ["run_failed", "definition"])
async def test_partial_run_and_changed_definition_block_acceptance(
    change: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.change = change
    with pytest.raises(EvaluationFailure):
        await publish(path, digest)
    assert not (path / "publication.json").exists()
    state = json.loads((path / "publication-state.json").read_bytes())
    assert state["verification"] == "failed"
    if change == "definition":
        assert service.run is None


async def test_polling_is_bounded_and_recovery_cannot_reset_sixty_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.change = "queued"
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(EvaluationFailure, match="publication_read_limit"):
        await publish(path, digest)
    state = json.loads((path / "publication-state.json").read_bytes())
    assert state["reads"] == 60
    assert waits and all(wait == 5 for wait in waits)
    before = len(service.requests)
    with pytest.raises(EvaluationFailure, match="publication_read_limit"):
        await publish(path, digest)
    assert len(service.requests) == before


@pytest.mark.parametrize(
    "field",
    ["source_sha256", "fixture_sha256", "metric_sha256", "configuration_sha256", "context_sha256"],
)
async def test_foreign_local_lineage_never_reaches_azure(
    field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    data = json.loads((path / "results.json").read_bytes())
    data[field] = "b" * 64
    (path / "results.json").write_text(json.dumps(data))
    with pytest.raises(EvaluationFailure, match="stale_or_foreign_evaluation_results"):
        await publish(path, digest)
    assert not service.requests
    assert not (path / "publication.lock").exists()


async def test_changed_case_set_and_changed_accounting_block_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    original = json.loads((path / "results.json").read_bytes())
    changed = json.loads(json.dumps(original))
    changed["cases"][1]["case_id"] = "p01"
    (path / "results.json").write_text(json.dumps(changed))
    with pytest.raises(EvaluationFailure, match="stale_or_foreign_evaluation_results"):
        await publish(path, digest)
    changed = json.loads(json.dumps(original))
    changed["budget"]["estimated_total_exposure_usd"] = "0"
    (path / "results.json").write_text(json.dumps(changed))
    with pytest.raises(EvaluationFailure, match="invalid_persisted_evaluation_accounting"):
        await publish(path, digest)
    assert not service.requests


@pytest.mark.parametrize("stage", ["catalog", "evaluation"])
async def test_early_ambiguity_requires_opt_in_for_only_never_attempted_metadata(
    stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    original = (path / "results.json").read_bytes()
    service.timeout_stage = stage
    with pytest.raises((httpx2.ReadTimeout, APIConnectionError)):
        await publish(path, digest)
    checkpoint = len(service.requests)
    with pytest.raises(EvaluationFailure, match="publication_mutation_replay_rejected"):
        await publish(path, digest)
    assert all(request.method == "GET" for request in service.requests[checkpoint:])
    receipt = await publish(path, digest, continue_unsubmitted=True)
    assert receipt["outcome"] == "api_verified"
    assert len([r for r in service.requests if r.method == "POST"]) == 3
    assert (path / "results.json").read_bytes() == original


async def test_fractional_scores_are_imported_exactly_without_display_rounding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    data = json.loads((path / "results.json").read_bytes())
    data["cases"][0]["score"] = 0.875
    data["cases"][1]["score"] = 0.125
    (path / "results.json").write_text(json.dumps(data))
    await publish(path, digest)
    assert [row["score"] for row in service.rows] == [0.875, 0.125]


async def test_original_deadline_is_not_renewed_by_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch, age_minutes=40)
    with pytest.raises(EvaluationFailure, match="evaluation_deadline"):
        await publish(path, digest)
    assert not service.requests


async def test_unknown_judge_usage_stays_reserved_after_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, _ = await setup(tmp_path, monkeypatch)
    data = json.loads((path / "results.json").read_bytes())
    receipt = data["budget"]
    observed = PRICES.cost(70, 35)
    reserved = PRICES.cost(400000, 1024)
    receipt.update(
        {
            "usage_observed": 7,
            "usage_unknown": 1,
            "usage_complete": False,
            "input_tokens_observed": 70,
            "output_tokens_observed": 35,
            "estimated_observed_usd": str(observed),
            "estimated_reserved_unknown_usd": str(reserved),
            "estimated_total_exposure_usd": str(observed + reserved),
        }
    )
    (path / "results.json").write_text(json.dumps(data))
    published = await publish(path, digest)
    assert published["budget"] == receipt


@pytest.mark.parametrize("change", ["catalog_denied", "catalog_redirect"])
async def test_catalog_authentication_failure_and_redirect_are_never_retried(
    change: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.change = change
    with pytest.raises((AzureError, EvaluationFailure)):
        await publish(path, digest)
    assert len(service.requests) == 1
    assert not (path / "publication.json").exists()
    captured = capsys.readouterr()
    assert "synthetic-provider-error-canary" not in captured.out + captured.err
