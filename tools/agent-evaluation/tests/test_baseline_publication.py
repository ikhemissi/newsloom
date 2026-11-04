import asyncio
import copy
import hashlib
import json
from pathlib import Path

import httpx2
import pytest
from azure.ai.projects.aio import AIProjectClient
from fakes import PROJECT_ENDPOINT, TOKEN, Credential
from openai import APIConnectionError
from test_baseline_budget import approval, ready
from test_baseline_inputs import frozen_data, result_data
from test_publication import selected_context

from agent_evaluation.baseline_budget import BaselineBudget, BaselineRun
from agent_evaluation.baseline_inputs import (
    CONTROL_IDS,
    METRICS,
    BaselineResult,
    ControlMeasurement,
    FrozenBaseline,
    ScoringProgress,
    parse_document,
)
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.baseline_publication import BaselinePublisher
from agent_evaluation.budget import Usage
from agent_evaluation.policy import EvaluationFailure


async def setup(
    tmp_path: Path,
) -> tuple[BaselineBudget, BaselineRun, BaselineResult]:
    context = selected_context()
    data = frozen_data()
    bindings = data["bindings"]
    oracles = data["oracles"]
    provenance = data["provenance"]
    assert isinstance(bindings, dict) and isinstance(oracles, dict) and isinstance(provenance, dict)
    bindings["context_sha256"] = context.digest()
    binding_hash = document_digest(bindings)
    oracles["bindings_sha256"] = binding_hash
    provenance["bindings_sha256"] = binding_hash
    provenance["oracle_sha256"] = document_digest(oracles)
    frozen = parse_document(FrozenBaseline, json.dumps(data).encode())
    approved = approval(frozen)
    encoded = approved.model_dump_json().encode()
    run = BaselineRun(
        tmp_path / "run",
        encoded,
        hashlib.sha256(encoded).hexdigest(),
        frozen,
        registry=tmp_path / "registry",
    )
    budget = BaselineBudget(approved, frozen, persist=run.checkpoint, ready=ready)
    await budget.start()
    data = result_data()
    data["provenance"] = frozen.provenance.model_dump(mode="json")
    data["frozen_sha256"] = approved.frozen_sha256
    cases, scores = data["cases"], data["scores"]
    assert isinstance(cases, list) and isinstance(scores, list)
    fractions = (0.0, 0.1, 0.125, 0.49999999999999994, 0.5, 0.5000000000000001, 0.875, 1.0)
    for row in cases:
        row["request_sha256"] = document_digest(frozen.request_document(row["case_id"]))
        row["evidence_sha256"] = frozen.evidence_digest(row["case_id"])
    index = 0
    for row in scores:
        if row["metric_id"] == "faithfulness":
            row["score"] = fractions[index]
            index += 1
        else:
            row["score"] = 1.0
    result = parse_document(BaselineResult, json.dumps(data).encode())
    await run.save_results(result)
    for row in result.cases:
        await budget.admit_agent(row.case_id)
        await budget.observe_agent(row)
    for _ in range(16):
        admitted = await budget.judge.admit(100)
        budget.judge.observe(
            admitted, Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        )
    run.claim_scoring()
    await run.scoring_checkpoint(
        ScoringProgress(
            protocol="baseline-v1",
            approval_sha256=run.canonical_sha256,
            frozen_sha256=approved.frozen_sha256,
            state="completed",
            pending_control=None,
            pending_case=None,
            controls=tuple(
                ControlMeasurement.model_validate(
                    {
                        "control_id": control,
                        "label": "supported" if index < 4 else "unsupported",
                        "score": 1.0 if index < 4 else 0.0,
                        "passed": True,
                        "judge_attempts": 1,
                    }
                )
                for index, control in enumerate(CONTROL_IDS)
            ),
            scores=result.scores,
        )
    )
    return budget, run, result


class Service:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.evaluations: dict[str, dict[str, object]] = {}
        self.runs: dict[str, dict[str, object]] = {}
        self.rows: dict[str, list[dict[str, object]]] = {}
        self.change: str | None = None
        self.timeout_run = False

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "evaluation-test.services.ai.azure.com"
        assert request.headers["authorization"] == "Bearer " + TOKEN
        assert request.headers["Foundry-Features"] == "Evaluations=V1Preview"
        assert "api-key" not in request.headers
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/evals"):
            if request.method == "GET":
                return httpx2.Response(
                    200,
                    json={
                        "object": "list",
                        "data": list(self.evaluations.values()),
                        "has_more": False,
                    },
                )
            data = json.loads(request.content)
            metric = data["metadata"]["metric_id"]
            identifier = "eval_" + metric
            value = {"object": "eval", "id": identifier, "created_at": 1, **data}
            self.evaluations[identifier] = value
            return httpx2.Response(201, json=value)
        if path.endswith("/runs"):
            evaluation_id = path.rsplit("/", 2)[-2]
            if request.method == "GET":
                return httpx2.Response(
                    200,
                    json={
                        "object": "list",
                        "data": [
                            value
                            for value in self.runs.values()
                            if value["eval_id"] == evaluation_id
                        ],
                        "has_more": False,
                    },
                )
            data = json.loads(request.content)
            metric = data["metadata"]["metric_id"]
            identifier = "run_" + metric
            rows = [value["item"] for value in data["data_source"]["source"]["content"]]
            self.rows[identifier] = rows
            threshold = 0.8 if metric == "faithfulness" else 1.0
            passed = sum(float(str(row["score"])) >= threshold for row in rows)
            value = {
                "id": identifier,
                "object": "eval.run",
                "created_at": 1,
                "eval_id": evaluation_id,
                "status": "completed",
                **data,
                "result_counts": {
                    "total": len(rows),
                    "passed": passed,
                    "failed": len(rows) - passed,
                    "errored": 0,
                    "skipped": 0,
                },
                "report_url": (
                    "https://ai.azure.com/nextgen/r/authored/build/evaluations/"
                    + evaluation_id
                    + "/run/"
                    + identifier
                ),
            }
            self.runs[identifier] = value
            if self.timeout_run:
                raise httpx2.ReadTimeout("REMOTE_CONTENT_CANARY", request=request)
            return httpx2.Response(201, json=value)
        if path.endswith("/output_items"):
            run_id = path.rsplit("/", 2)[-2]
            run = self.runs[run_id]
            after = request.url.params.get("after")
            start = 0 if after is None else int(after.removeprefix("item_")) + 1
            rows = self.rows[run_id]
            batch = []
            evaluation_id = str(run["eval_id"])
            criterion = self.evaluations[evaluation_id]["testing_criteria"]
            assert isinstance(criterion, list)
            for index in range(start, min(start + 2, len(rows))):
                row = dict(rows[index])
                if self.change == "duplicate" and index == len(rows) - 1:
                    row = dict(rows[0])
                if self.change == "stale" and index == 0:
                    row["capture_source_sha256"] = "0" * 64
                score: object = float(str(row["score"]))
                if self.change == "boolean":
                    score = True
                if self.change == "precision":
                    row["score"] = "0.49999999999999906"
                if self.change == "noncanonical":
                    row["score"] = "1"
                result: dict[str, object] = {
                    "type": "python",
                    "status": "completed",
                    "name": criterion[0]["name"],
                    "score": score,
                    "passed": float(str(rows[index]["score"])) >= criterion[0]["pass_threshold"],
                }
                if self.change == "nested_error":
                    result["sample"] = {"error": {"message": "REMOTE_CONTENT_CANARY"}}
                batch.append(
                    {
                        "id": "item_" + str(index),
                        "object": "eval.run.output_item",
                        "created_at": 1,
                        "eval_id": evaluation_id,
                        "run_id": run_id,
                        "status": "completed",
                        "datasource_item": {"item": row},
                        "results": [result],
                        "sample": {},
                    }
                )
            has_more = start + len(batch) < len(rows)
            if self.change == "missing":
                has_more = False
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": batch,
                    "first_id": batch[0]["id"],
                    "last_id": batch[-1]["id"],
                    "has_more": has_more,
                },
            )
        identifier = path.rsplit("/", 1)[-1]
        retained_value = self.evaluations.get(identifier) or self.runs.get(identifier)
        assert retained_value is not None
        changed = copy.deepcopy(retained_value)
        if self.change == "definition" and identifier in self.evaluations:
            criteria = changed["testing_criteria"]
            assert isinstance(criteria, list)
            criteria[0]["source"] = "foreign grader"
        if self.change == "counts" and identifier in self.runs:
            counts = changed["result_counts"]
            assert isinstance(counts, dict)
            counts["total"] = True
        return httpx2.Response(200, json=changed)


async def execute(publisher: BaselinePublisher, service: Service) -> dict[str, object]:
    async with (
        Credential() as credential,
        AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=credential,
            allow_preview=True,
            retry_total=0,
            redirect_max=0,
        ) as project,
    ):
        return await publisher.execute(project, inner=httpx2.MockTransport(service.respond))


async def test_actual_sdk_publishes_all_three_exact_metadata_only_reports(tmp_path: Path) -> None:
    budget, run, result = await setup(tmp_path)
    publisher = BaselinePublisher(budget, run, result, selected_context())
    service = Service()
    receipt = await execute(publisher, service)
    assert receipt["outcome"] == "api_verified" and receipt["ui_verified"] is False
    assert budget.counts["publication_creates"] == 6
    assert budget.counts["publication_reads"] == sum(row.reads for row in publisher.state.reports)
    assert {key: len(rows) for key, rows in service.rows.items()} == {
        "run_faithfulness": 8,
        "run_citation_validity": 8,
        "run_contract_adherence": 12,
    }
    for metric in METRICS:
        expected = [row for row in result.scores if row.metric_id == metric]
        remote = service.rows["run_" + metric]
        assert [row["score"] for row in remote] == [repr(row.score) for row in expected]
        assert all(
            not (set(row) & {"answer", "question", "reason", "evidence", "summary"})
            for row in remote
        )
    before = len([request for request in service.requests if request.method == "POST"])
    recovery = BaselinePublisher(budget, run, result, selected_context())
    assert recovery.recovery
    await execute(recovery, service)
    assert len([request for request in service.requests if request.method == "POST"]) == before == 6


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "stale",
        "boolean",
        "precision",
        "noncanonical",
        "nested_error",
        "missing",
        "definition",
        "counts",
    ],
)
async def test_partial_or_changed_publication_is_never_accepted(
    tmp_path: Path, change: str
) -> None:
    budget, run, result = await setup(tmp_path)
    service = Service()
    service.change = change
    publisher = BaselinePublisher(budget, run, result, selected_context())
    with pytest.raises((EvaluationFailure, ValueError)):
        await execute(publisher, service)
    assert not (tmp_path / "run/publication.json").exists()
    assert budget.counts["publication_creates"] <= 2
    assert budget.counts["publication_reads"] <= 180


async def test_unknown_create_recovers_only_by_reads_without_replaying_mutations(
    tmp_path: Path,
) -> None:
    budget, run, result = await setup(tmp_path)
    service = Service()
    service.timeout_run = True
    publisher = BaselinePublisher(budget, run, result, selected_context())
    with pytest.raises(APIConnectionError):
        await execute(publisher, service)
    assert publisher.report.pending == "run" and publisher.report.run_id is None
    assert budget.counts["publication_creates"] == 2
    posts = len([request for request in service.requests if request.method == "POST"])
    service.timeout_run = False
    recovery = BaselinePublisher(budget, run, result, selected_context())
    with pytest.raises(EvaluationFailure, match="publication_mutation_replay_rejected"):
        await execute(recovery, service)
    assert recovery.state.reports[0].verification == "api_verified"
    assert recovery.state.reports[0].run_id is not None
    assert len([request for request in service.requests if request.method == "POST"]) == posts == 2
    assert budget.counts["publication_creates"] == 2
    assert not (tmp_path / "run/publication.json").exists()


async def test_pilot_state_is_not_silently_adopted_as_baseline_state(tmp_path: Path) -> None:
    budget, run, result = await setup(tmp_path)
    (tmp_path / "run/publication-state.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "publication_protocol": "native-python",
                "configuration_sha256": run.canonical_sha256,
            }
        )
    )
    with pytest.raises(EvaluationFailure, match="invalid_baseline_publication_state"):
        BaselinePublisher(budget, run, result, selected_context())


@pytest.mark.parametrize("cancel", [False, True])
async def test_publication_raw_errors_and_cancellation_keep_only_metadata(
    tmp_path: Path,
    cancel: bool,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budget, run, result = await setup(tmp_path)
    service = Service()

    def fail(request: httpx2.Request) -> httpx2.Response:
        if cancel:
            raise asyncio.CancelledError("PRIVATE_PROVIDER_ERROR_CANARY")
        raise httpx2.ReadTimeout("PRIVATE_PROVIDER_ERROR_CANARY", request=request)

    monkeypatch.setattr(service, "respond", fail)
    publisher = BaselinePublisher(budget, run, result, selected_context())
    with pytest.raises((APIConnectionError, asyncio.CancelledError)):
        await execute(publisher, service)
    state = run.load_publication_state()
    assert state is not None
    assert state.reports[0].mutations == ("evaluation",)
    assert state.reports[0].pending == "evaluation"
    assert state.reports[0].verification == "failed"
    assert budget.counts["publication_creates"] == 1
    assert not (tmp_path / "run/publication.json").exists()
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err
    for path in (tmp_path / "run").iterdir():
        if path.is_file():
            assert b"CANARY" not in path.read_bytes()
