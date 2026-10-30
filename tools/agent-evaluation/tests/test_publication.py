import ast
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from fakes import PROJECT_ENDPOINT, TOKEN, Credential
from openai import APIConnectionError, AuthenticationError
from pydantic import ValidationError
from test_budget import PRICES
from test_runner import approval_data

from agent_evaluation import grader, publication
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
        self.evaluation: dict[str, object] | None = None
        self.run: dict[str, object] | None = None
        self.rows: list[dict[str, object]] = []
        self.timeout_run = False
        self.timeout_stage: str | None = None
        self.change: str | None = None
        self.count_change: dict[str, object] | None = None
        self.wrapped = True
        self.null_error = False

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "evaluation-test.services.ai.azure.com"
        assert request.headers["authorization"] == "Bearer " + TOKEN
        assert "api-key" not in request.headers
        self.requests.append(request)
        path = request.url.path
        assert "/evaluators/" not in path
        if path.endswith("/output_items"):
            index = 1 if request.url.params.get("after") == "item_one" else 0
            row = dict(self.rows[index])
            if self.change == "duplicate" and index == 1:
                row = dict(self.rows[0])
            if self.change == "stale" and index == 1:
                row["source_sha256"] = "b" * 64
            metric: dict[str, object] = {
                "name": publication.ORIGIN,
                "type": "python",
                "status": "completed",
                "score": float(str(row["score"])),
                "passed": float(str(row["score"])) >= 0.5,
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
            if self.change == "sandbox_status":
                metric["status"] = "failed"
            if self.change == "sandbox_type":
                metric["type"] = "azure_ai_evaluator"
            if self.change == "metric_nested_error":
                metric["sample"] = {"error": {"message": "synthetic-provider-error-canary"}}
            sample: dict[str, object] = {}
            if self.change == "item_nested_error":
                sample["error"] = {"message": "synthetic-provider-error-canary"}
            if self.change == "input_boolean":
                row["score"] = True
            if self.change == "input_numeric_string":
                row["score"] = "1"
            if self.change == "input_nonfinite_string":
                row["score"] = "nan"
            if self.change == "input_precision_changed":
                row["score"] = "0.9999999999999999"
            datasource: object = {"item": row} if self.wrapped else row
            if self.change == "wrapper_extra":
                datasource = {"item": row, "unexpected": True}
            if self.change == "wrapper_nonobject":
                datasource = {"item": "invalid"}
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
                                "datasource_item": datasource,
                                "status": "failed" if self.change == "item_status" else "completed",
                                "results": [metric],
                                "sample": sample,
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
            if self.change == "evaluation_denied":
                return httpx2.Response(
                    401, json={"error": {"message": "synthetic-provider-error-canary"}}
                )
            if self.change == "evaluation_redirect":
                return httpx2.Response(302, headers={"location": "https://example.com/foreign"})
            body = json.loads(request.content)
            assert body["testing_criteria"] == [
                {
                    "type": "python",
                    "name": publication.ORIGIN,
                    "source": Path(str(grader.__file__)).read_text(),
                    "pass_threshold": 0.5,
                }
            ]
            self.evaluation = {
                **body,
                "data_source_config": {
                    "type": "custom",
                    "include_sample_schema": False,
                    "item_schema": {},
                    "schema": {"item": body["data_source_config"]["item_schema"]},
                },
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
            if self.null_error:
                self.run["error"] = {"code": None, "message": None, "inner_error": {"code": None}}
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
        if path.endswith("/run_pilot") and self.count_change is not None:
            assert self.run is not None
            return httpx2.Response(200, json=self.run | {"result_counts": self.count_change})
        if path.endswith("/eval_pilot") and self.change in (
            "definition",
            "source",
            "threshold",
            "schema",
            "criterion_type",
            "model",
            "schema_conflict",
            "sample_schema",
            "echo_schema",
        ):
            assert self.evaluation is not None
            changed = json.loads(json.dumps(self.evaluation))
            if self.change == "definition":
                changed["testing_criteria"] = []
            elif self.change == "schema":
                changed["data_source_config"]["schema"]["item"] = {}
            elif self.change == "schema_conflict":
                changed["data_source_config"]["item_schema"] = changed["data_source_config"][
                    "schema"
                ]["item"]
                changed["data_source_config"]["schema"]["item"] = {}
            elif self.change == "sample_schema":
                changed["data_source_config"]["include_sample_schema"] = True
            elif self.change == "echo_schema":
                changed["data_source_config"]["item_schema"] = changed["data_source_config"].pop(
                    "schema"
                )["item"]
            else:
                field, value = {
                    "source": ("source", "def grade(sample, item):\n    return 0.0\n"),
                    "threshold": ("pass_threshold", 0.6),
                    "criterion_type": ("type", "azure_ai_evaluator"),
                    "model": ("model", "foreign-deployment"),
                }[self.change]
                changed["testing_criteria"][0][field] = value
            return httpx2.Response(200, json=changed)
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

    def credential(*, tenant_id: str, process_timeout: int) -> Credential:
        assert process_timeout == 30
        return Credential()

    def inner(**kwargs: object) -> httpx2.MockTransport:
        return httpx2.MockTransport(service.respond)

    monkeypatch.setattr(publication, "load_bundle", load)
    monkeypatch.setattr(publication, "read_context", read_context)
    monkeypatch.setattr(publication, "AzureCliCredential", credential)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", inner)
    return path, digest, service


async def test_real_native_python_evaluation_sdk_preserves_both_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.null_error = True
    original = (path / "results.json").read_bytes()
    receipt = await publish(path, digest)
    assert receipt["outcome"] == "api_verified"
    assert receipt["ui_verified"] is False
    assert receipt["cases"] == 2
    assert [row["score"] for row in service.rows] == ["1.0", "0.0"]
    assert all(
        request.headers["Foundry-Features"] == "Evaluations=V1Preview"
        for request in service.requests
    )
    assert service.evaluation is not None
    config = service.evaluation["data_source_config"]
    assert isinstance(config, dict)
    assert config["schema"]["item"]["properties"]["score"] == {"type": "string"}
    assert [row["case_id"] for row in service.rows] == ["p01", "p02"]
    assert all(row["metric_origin"] == publication.ORIGIN for row in service.rows)
    assert [row["reason"] for row in service.rows] == [
        "Synthetic supported explanation.",
        "Synthetic unsupported explanation.",
    ]
    assert len([r for r in service.requests if r.method == "POST"]) == 2
    assert receipt["publication_protocol"] == "native-python"
    assert all("/evaluators/" not in r.url.path for r in service.requests)
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
    assert len([r for r in service.requests if r.method == "POST"]) == 2
    assert (path / "results.json").read_bytes() == original
    assert receipt["budget"] == json.loads(original)["budget"]


@pytest.mark.parametrize(
    "change",
    [
        "boolean",
        "nan",
        "range",
        "sandbox",
        "sandbox_status",
        "sandbox_type",
        "item_status",
        "duplicate",
        "stale",
        "missing",
        "metric_nested_error",
        "item_nested_error",
        "input_boolean",
        "input_numeric_string",
        "input_nonfinite_string",
        "input_precision_changed",
        "wrapper_extra",
        "wrapper_nonobject",
    ],
)
async def test_failed_or_malformed_readback_is_never_a_valid_zero(
    change: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.change = change
    with pytest.raises((EvaluationFailure, ValidationError)):
        await publish(path, digest)
    assert not (path / "publication.json").exists()


@pytest.mark.parametrize(
    "value",
    [True, False, None, {}, [], float("nan"), float("inf"), -0.01, 1.01, "nan", "inf", "invalid"],
)
def test_sandbox_code_has_no_success_shaped_invalid_input_fallback(value: object) -> None:
    with pytest.raises(ValueError):
        grade({}, {"score": value})


def test_imported_score_code_does_not_rejudge_or_reinterpret() -> None:
    assert grade({}, {"score": 0.0}) == 0.0
    assert grade({}, {"score": 0.375}) == 0.375
    assert grade({}, {"score": 1}) == 1.0


@pytest.mark.parametrize(
    "value", [0.0, 0.1, 0.125, 0.375, 0.49999999999999994, 0.5, 0.5000000000000001, 0.875, 1.0]
)
def test_submitted_grader_parses_canonical_strings_without_precision_loss(value: float) -> None:
    source = Path(str(grader.__file__)).read_text()
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Import | ast.ImportFrom) for node in ast.walk(tree))
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    assert function.returns is None
    assert all(argument.annotation is None for argument in function.args.args)
    namespace: dict[str, object] = {}
    exec(source, namespace)
    submitted_grade = namespace["grade"]
    assert callable(submitted_grade)
    assert submitted_grade({}, {"score": repr(value)}) == value
    assert grade({}, {"score": repr(value)}) == value


async def test_flat_legacy_response_shape_remains_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.wrapped = False
    receipt = await publish(path, digest)
    assert receipt["outcome"] == "api_verified"


@pytest.mark.parametrize(
    "error", [None, {}, {"code": None, "message": None, "inner_error": {"code": None}}]
)
async def test_null_error_placeholders_are_not_service_failures(
    error: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, _ = await setup(tmp_path, monkeypatch)
    publisher = Publisher(publication.load_bundle(path, digest), selected_context())
    publisher.inspect(
        httpx2.Request("GET", publisher.eval_path),
        {"error": json.loads(json.dumps(error)), "status": "queued"},
    )


@pytest.mark.parametrize("error", ["invalid", {"code": "UserError"}, {"unexpected": True}])
async def test_populated_service_errors_still_fail_closed(
    error: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, _ = await setup(tmp_path, monkeypatch)
    publisher = Publisher(publication.load_bundle(path, digest), selected_context())
    with pytest.raises(EvaluationFailure, match="publication_service_error"):
        publisher.inspect(
            httpx2.Request("GET", publisher.eval_path),
            {"error": json.loads(json.dumps(error))},
        )


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
            "mutations": ("evaluation",),
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


@pytest.mark.parametrize(
    "change",
    [
        "run_failed",
        "definition",
        "source",
        "threshold",
        "schema",
        "criterion_type",
        "model",
        "schema_conflict",
        "sample_schema",
    ],
)
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
    if change != "run_failed":
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


@pytest.mark.parametrize("stage", ["evaluation"])
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
    assert len([r for r in service.requests if r.method == "POST"]) == 2
    assert (path / "results.json").read_bytes() == original


@pytest.mark.parametrize(
    ("supported", "unsupported"),
    [(0.875, 0.125), (0.5, 0.1), (0.5000000000000001, 0.49999999999999994)],
)
async def test_fractional_scores_are_imported_exactly_without_display_rounding(
    supported: float, unsupported: float, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    data = json.loads((path / "results.json").read_bytes())
    data["cases"][0]["score"] = supported
    data["cases"][1]["score"] = unsupported
    (path / "results.json").write_text(json.dumps(data))
    await publish(path, digest)
    assert [row["score"] for row in service.rows] == [repr(supported), repr(unsupported)]
    assert [grade({}, row) for row in service.rows] == [supported, unsupported]


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


@pytest.mark.parametrize("change", ["evaluation_denied", "evaluation_redirect"])
async def test_authentication_failure_and_redirect_are_never_retried(
    change: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.change = change
    with pytest.raises((AuthenticationError, EvaluationFailure)):
        await publish(path, digest)
    assert len(service.requests) == 1
    assert not (path / "publication.json").exists()
    captured = capsys.readouterr()
    assert "synthetic-provider-error-canary" not in captured.out + captured.err


@pytest.mark.parametrize("stage", ["evaluation", "run"])
async def test_exact_two_mutation_slots_never_allow_a_third_dispatch(
    stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    await publish(path, digest)
    publisher = Publisher(
        publication.load_bundle(path, digest), selected_context(), continue_unsubmitted=True
    )
    target = publisher.eval_path + ("/eval_pilot/runs" if stage == "run" else "")
    with pytest.raises(EvaluationFailure, match="publication_mutation_replay_rejected"):
        await publisher.admit(httpx2.Request("POST", PROJECT_ENDPOINT.split("/api/")[0] + target))
    assert len([r for r in service.requests if r.method == "POST"]) == 2


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
async def test_catalog_routes_are_rejected_without_dispatch_or_budget_use(
    method: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    publisher = Publisher(publication.load_bundle(path, digest), selected_context())
    with pytest.raises(EvaluationFailure, match="publication_endpoint_rejected"):
        await publisher.admit(
            httpx2.Request(method, PROJECT_ENDPOINT + "/evaluators/owned/versions")
        )
    assert not service.requests
    assert publisher.state.mutations == ()
    assert publisher.state.reads == 0


async def test_historical_catalog_journal_is_rejected_without_rewriting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    state = publication.load_bundle(path, digest).state.model_dump(mode="json")
    state.pop("schema_version")
    state.pop("publication_protocol")
    state.update(mutations=["catalog"], pending="catalog", catalog_version=None)
    original = json.dumps(state).encode()
    (path / "publication-state.json").write_bytes(original)
    with pytest.raises(ValidationError):
        await publish(path, digest)
    assert not service.requests
    assert (path / "publication-state.json").read_bytes() == original


@pytest.mark.parametrize(
    "counts",
    [
        {},
        {"total": 2, "passed": 1, "failed": 1, "errored": False},
        {"total": 2, "passed": 1, "failed": 1, "errored": 1},
        {"total": 1, "passed": 1, "failed": 0, "errored": 0},
        {"total": 2, "passed": 1, "failed": 1, "errored": 0, "skipped": 1},
    ],
)
async def test_terminal_counts_cannot_hide_errors_or_missing_cases(
    counts: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.count_change = counts
    with pytest.raises(EvaluationFailure):
        await publish(path, digest)
    assert not (path / "publication.json").exists()


async def test_exact_echoed_item_schema_is_also_supported_without_canonical_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, service = await setup(tmp_path, monkeypatch)
    service.change = "echo_schema"
    receipt = await publish(path, digest)
    assert receipt["outcome"] == "api_verified"
