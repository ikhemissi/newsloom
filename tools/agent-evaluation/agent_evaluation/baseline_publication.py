import asyncio
import json
from pathlib import Path
from typing import Final, Literal, Self
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx2
from azure.ai.projects.aio import AIProjectClient
from pydantic import Field, JsonValue, StrictBool, StrictInt, model_validator

from agent_evaluation import grader, native_rows
from agent_evaluation.baseline_budget import BaselineBudget, BaselineRun
from agent_evaluation.baseline_inputs import (
    METRICS,
    BaselineResult,
    CaseId,
    MetricId,
    Score,
)
from agent_evaluation.baseline_provenance import Digest, document_digest
from agent_evaluation.context import Context
from agent_evaluation.foundry import ProjectTransport, project_endpoint
from agent_evaluation.inputs import StrictModel
from agent_evaluation.policy import EvaluationFailure

MetricOrigin = Literal[
    "imported_deepeval_faithfulness", "baseline_citation_validity", "baseline_contract_adherence"
]
ORIGINS: Final[dict[MetricId, MetricOrigin]] = {
    "faithfulness": "imported_deepeval_faithfulness",
    "citation_validity": "baseline_citation_validity",
    "contract_adherence": "baseline_contract_adherence",
}
Mutation = Literal["evaluation", "run"]


class BaselinePublicationRow(StrictModel):
    protocol: Literal["baseline-v1"]
    case_id: CaseId
    metric_id: MetricId
    metric_origin: MetricOrigin
    score: Score
    fixture_sha256: Digest
    frozen_sha256: Digest
    configuration_sha256: Digest
    results_sha256: Digest
    evaluator_source_sha256: Digest
    capture_source_sha256: Digest
    accepted_image_sha256: Digest

    @model_validator(mode="after")
    def metric_lineage(self) -> Self:
        if self.metric_origin != ORIGINS[self.metric_id]:
            raise ValueError("baseline_metric_origin_mismatch")
        return self


class ReportState(StrictModel):
    metric_id: MetricId
    mutations: tuple[Mutation, ...]
    pending: Mutation | None
    evaluation_id: str | None
    run_id: str | None
    reads: StrictInt = Field(ge=0, le=180)
    verification: Literal["pending", "api_verified", "failed"]

    @model_validator(mode="after")
    def exact_owned_intents(self) -> Self:
        if (
            self.mutations != ("evaluation", "run")[: len(self.mutations)]
            or len(self.mutations) > 2
            or (
                self.pending is not None
                and (not self.mutations or self.pending != self.mutations[-1])
            )
            or (
                self.run_id is not None and (self.evaluation_id is None or len(self.mutations) != 2)
            )
            or (self.evaluation_id is not None and not self.mutations)
        ):
            raise ValueError("invalid_baseline_publication_intents")
        for value in (self.evaluation_id, self.run_id):
            if value is not None:
                native_rows.identifier(value)
        return self


class BaselinePublicationState(StrictModel):
    protocol: Literal["baseline-v1"]
    approval_sha256: Digest
    frozen_sha256: Digest
    results_sha256: Digest
    reports: tuple[ReportState, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def exact_metrics(self) -> Self:
        if tuple(value.metric_id for value in self.reports) != METRICS:
            raise ValueError("baseline_report_set_mismatch")
        return self


class ReportReference(StrictModel):
    metric_id: MetricId
    cases: StrictInt = Field(ge=8, le=12)
    evaluation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,256}$")
    run_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,256}$")
    report_url: str = Field(max_length=4096)

    @model_validator(mode="after")
    def exact_report_reference(self) -> Self:
        url = urlsplit(self.report_url)
        query = parse_qs(url.query, strict_parsing=True, max_num_fields=1, keep_blank_values=True)
        if (
            self.cases != (12 if self.metric_id == "contract_adherence" else 8)
            or url.scheme != "https"
            or url.netloc != "ai.azure.com"
            or self.report_url != url.geturl()
            or url.fragment
            or not url.path.endswith(
                "/build/evaluations/" + self.evaluation_id + "/run/" + self.run_id
            )
            or set(query) - {"tid"}
        ):
            raise ValueError("invalid_baseline_report_reference")
        if "tid" in query:
            if len(query["tid"]) != 1:
                raise ValueError("invalid_baseline_report_reference")
            UUID(query["tid"][0])
        return self


class BaselinePublicationReceipt(StrictModel):
    protocol: Literal["baseline-v1"]
    outcome: Literal["api_verified"]
    ui_verified: StrictBool
    cases: StrictInt = Field(ge=12, le=12)
    metric_reports: tuple[ReportReference, ...] = Field(min_length=3, max_length=3)
    approval_sha256: Digest
    results_sha256: Digest
    model_calls: StrictInt = Field(ge=0, le=0)

    @model_validator(mode="after")
    def actual_api_not_ui_claim(self) -> Self:
        if self.ui_verified or tuple(row.metric_id for row in self.metric_reports) != METRICS:
            raise ValueError("invalid_baseline_publication_receipt")
        return self


class BaselinePublisher:
    def __init__(
        self,
        budget: BaselineBudget,
        run: BaselineRun,
        result: BaselineResult,
        context: Context,
        *,
        state: BaselinePublicationState | None = None,
    ) -> None:
        result = run.validated_metadata(result)
        result.verify_frozen(budget.frozen)
        if (
            context.digest() != budget.frozen.bindings.context_sha256
            or run.canonical_sha256 != document_digest(budget.approval.model_dump(mode="json"))
        ):
            raise EvaluationFailure("baseline_publication_context_mismatch")
        progress = run.load_scoring_progress()
        usage = budget.judge.receipt()
        stored = run.load_publication_state()
        if (
            progress.state != "completed"
            or progress.scores != result.scores
            or not usage.usage_complete
            or (usage.admission_halted and stored is None)
            or usage.attempts < sum(row.judge_attempts for row in progress.controls) + 8
            or tuple(row.receipt for row in budget.agents.values()) != result.cases
        ):
            raise EvaluationFailure("baseline_publication_measurement_incomplete")
        self.budget, self.run, self.result = budget, run, result
        self.result_hash = document_digest(result.model_dump(mode="json"))
        self.endpoint = project_endpoint(
            context.environment["AGENT_EVALUATION_PROJECT_ENDPOINT"],
            context.environment["MODEL_ENDPOINT"],
            context.environment["AGENT_EVALUATION_PROJECT_ID"],
        )
        self.prefix = httpx2.URL(self.endpoint)
        self.eval_path = self.prefix.path + "/openai/v1/evals"
        if state is not None and state != stored:
            raise EvaluationFailure("baseline_publication_state_mismatch")
        state = stored
        if state is None and budget.counts["publication_creates"]:
            raise EvaluationFailure("baseline_publication_state_missing")
        self.state = (
            state
            if state is not None
            else BaselinePublicationState(
                protocol="baseline-v1",
                approval_sha256=run.canonical_sha256,
                frozen_sha256=budget.approval.frozen_sha256,
                results_sha256=self.result_hash,
                reports=tuple(
                    ReportState(
                        metric_id=metric,
                        mutations=(),
                        pending=None,
                        evaluation_id=None,
                        run_id=None,
                        reads=0,
                        verification="pending",
                    )
                    for metric in ORIGINS
                ),
            )
        )
        if (
            self.state.approval_sha256 != run.canonical_sha256
            or self.state.frozen_sha256 != budget.approval.frozen_sha256
            or self.state.results_sha256 != self.result_hash
        ):
            raise EvaluationFailure("baseline_publication_state_mismatch")
        if (
            sum(row.reads for row in self.state.reports) != budget.counts["publication_reads"]
            or sum(len(row.mutations) for row in self.state.reports)
            != budget.counts["publication_creates"]
        ):
            raise EvaluationFailure("baseline_publication_counter_mismatch")
        self.recovery = state is not None
        self.current: MetricId = "faithfulness"
        self.seen: set[str] = set()
        self.code = Path(grader.__file__).read_text()

    @property
    def report(self) -> ReportState:
        return next(value for value in self.state.reports if value.metric_id == self.current)

    @property
    def threshold(self) -> float:
        return 0.8 if self.current == "faithfulness" else 1.0

    def rows(self) -> tuple[BaselinePublicationRow, ...]:
        proof = self.result.provenance
        return tuple(
            BaselinePublicationRow(
                protocol="baseline-v1",
                case_id=value.case_id,
                metric_id=value.metric_id,
                metric_origin=ORIGINS[value.metric_id],
                score=value.score,
                fixture_sha256=proof.fixture_sha256,
                frozen_sha256=self.budget.approval.frozen_sha256,
                configuration_sha256=self.run.canonical_sha256,
                results_sha256=self.result_hash,
                evaluator_source_sha256=proof.evaluator_source_sha256,
                capture_source_sha256=proof.capture_source_sha256,
                accepted_image_sha256=proof.accepted_runtime.image_sha256,
            )
            for value in self.result.scores
            if value.metric_id == self.current
        )

    @property
    def name(self) -> str:
        return "newsloom_baseline_" + self.run.canonical_sha256[:16] + "_" + self.current

    def metadata(self) -> dict[str, str]:
        return {
            "grader_protocol": "baseline-v1",
            "configuration_sha256": self.run.canonical_sha256,
            "results_sha256": self.result_hash,
            "metric_id": self.current,
        }

    def owned(self, metadata: dict[str, str] | None) -> bool:
        return metadata is not None and all(
            metadata.get(key) == value for key, value in self.metadata().items()
        )

    async def save(self, **updates: object) -> None:
        reports = [
            value.model_copy(update=updates) if value.metric_id == self.current else value
            for value in self.state.reports
        ]
        self.state = BaselinePublicationState.model_validate_json(
            json.dumps(
                {
                    **self.state.model_dump(mode="json"),
                    "reports": [value.model_dump(mode="json") for value in reports],
                }
            )
        )
        await self.run.publication_checkpoint(self.state)

    async def admit(self, request: httpx2.Request) -> float:
        request.headers["Foundry-Features"] = "Evaluations=V1Preview"
        url = request.url
        if (url.scheme, url.host, url.port) != (
            self.prefix.scheme,
            self.prefix.host,
            self.prefix.port,
        ) or set(url.params.keys()) - {"api-version", "after", "limit", "order", "order_by"}:
            raise EvaluationFailure("publication_endpoint_rejected")
        state = self.report
        mutation: Mutation | None = None
        allowed = request.method == "GET" and url.path == self.eval_path and self.recovery
        if request.method == "POST" and url.path == self.eval_path:
            mutation = "evaluation"
        if state.evaluation_id is not None:
            evaluation = self.eval_path + "/" + state.evaluation_id
            runs = evaluation + "/runs"
            allowed |= request.method == "GET" and url.path in (evaluation, runs)
            if request.method == "POST" and url.path == runs:
                mutation = "run"
            if state.run_id is not None:
                path = runs + "/" + state.run_id
                allowed |= request.method == "GET" and url.path in (path, path + "/output_items")
        if mutation is not None:
            if (
                self.recovery
                or state.pending is not None
                or len(state.mutations) >= 2
                or mutation != ("evaluation", "run")[len(state.mutations)]
            ):
                raise EvaluationFailure("publication_mutation_replay_rejected")
            await self.save(mutations=(*state.mutations, mutation), pending=mutation)
            await self.budget.admit("publication_creates")
        elif allowed:
            await self.budget.admit("publication_reads", recovery=self.recovery)
            await self.save(reads=state.reads + 1)
        else:
            raise EvaluationFailure("publication_endpoint_rejected")
        remaining = self.budget.deadline - self.budget.clock()
        if remaining <= 0:
            raise EvaluationFailure("baseline_execution_deadline")
        return min(30.0, remaining)

    def inspect(self, request: httpx2.Request, value: dict[str, JsonValue]) -> None:
        if native_rows.has_error(value.get("error")):
            raise EvaluationFailure("publication_service_error")
        state = self.report
        if request.url.path == self.eval_path + "/" + str(state.evaluation_id):
            criteria = value.get("testing_criteria")
            config = value.get("data_source_config")
            schema = native_rows.wire_schema(BaselinePublicationRow)
            if (
                not isinstance(criteria, list)
                or len(criteria) != 1
                or not isinstance(criteria[0], dict)
                or set(criteria[0]) - {"id", "type", "name", "source", "pass_threshold"}
                or criteria[0].get("type") != "python"
                or criteria[0].get("name") != ORIGINS[self.current]
                or criteria[0].get("source") != self.code
                or type(criteria[0].get("pass_threshold")) not in (int, float)
                or criteria[0].get("pass_threshold") != self.threshold
                or not isinstance(config, dict)
                or config.get("type") != "custom"
                or config.get("item_schema") not in ({}, schema)
                or ("schema" in config and config["schema"] != {"item": schema})
                or (config.get("item_schema") == {} and config.get("schema") != {"item": schema})
                or config.get("include_sample_schema") not in (None, False)
            ):
                raise EvaluationFailure("evaluation_definition_drift")
        counts = value.get("result_counts")
        if isinstance(counts, dict) and counts.get("errored") not in (None, 0):
            raise EvaluationFailure("publication_item_execution_error")
        if (
            state.evaluation_id is not None
            and state.run_id is not None
            and request.url.path
            == self.eval_path + "/" + state.evaluation_id + "/runs/" + state.run_id
            and value.get("status") == "completed"
        ):
            rows = self.rows()
            passed = sum(row.score >= self.threshold for row in rows)
            expected_counts = {
                "total": len(rows),
                "passed": passed,
                "failed": len(rows) - passed,
                "errored": 0,
            }
            if (
                not isinstance(counts, dict)
                or any(
                    type(counts.get(key)) is not int or counts[key] != expected
                    for key, expected in expected_counts.items()
                )
                or (
                    "skipped" in counts
                    and (type(counts["skipped"]) is not int or counts["skipped"] != 0)
                )
            ):
                raise EvaluationFailure("publication_result_counts_mismatch")
        if request.url.path.endswith("/output_items"):
            data = value.get("data")
            if (
                not isinstance(data, list)
                or type(value.get("has_more")) is not bool
                or (
                    value["has_more"]
                    and (
                        not data
                        or not isinstance(data[-1], dict)
                        or value.get("last_id") != data[-1].get("id")
                    )
                )
            ):
                raise EvaluationFailure("incomplete_publication_page")
            for item in data:
                self.validate_item(item)

    def validate_item(self, item: JsonValue) -> None:
        if not isinstance(item, dict):
            raise EvaluationFailure("invalid_publication_item")
        results = item.get("results")
        if (
            item.get("eval_id") != self.report.evaluation_id
            or item.get("run_id") != self.report.run_id
            or item.get("status") != "completed"
            or native_rows.has_error(item.get("error"))
            or item.get("errors")
            or not isinstance(results, list)
            or len(results) != 1
            or not isinstance(results[0], dict)
        ):
            raise EvaluationFailure("publication_item_execution_error")
        metric = results[0]
        for sample in (item.get("sample"), metric.get("sample")):
            if sample is not None and not isinstance(sample, dict):
                raise EvaluationFailure("invalid_publication_sample")
            if isinstance(sample, dict) and (
                native_rows.has_error(sample.get("error")) or sample.get("errors")
            ):
                raise EvaluationFailure("publication_item_execution_error")
        row = native_rows.read_row(
            BaselinePublicationRow, item.get("datasource_item"), canonical_text_only=True
        )
        expected = {value.case_id: value for value in self.rows()}
        score = metric.get("score")
        if (
            row.case_id in self.seen
            or row != expected.get(row.case_id)
            or metric.get("type") != "python"
            or metric.get("status") != "completed"
            or metric.get("name") != ORIGINS[self.current]
            or type(score) not in (int, float)
            or score != row.score
            or type(metric.get("passed")) is not bool
            or metric["passed"] != (row.score >= self.threshold)
            or native_rows.has_error(metric.get("error"))
            or metric.get("errors")
            or metric.get("error_message")
        ):
            raise EvaluationFailure("publication_score_or_lineage_mismatch")
        self.seen.add(row.case_id)

    async def execute(
        self, project: AIProjectClient, *, inner: httpx2.AsyncBaseTransport | None = None
    ) -> dict[str, object]:
        completed = False
        try:
            receipt = await self._execute(project, inner=inner)
            completed = True
            return receipt
        finally:
            if not completed:
                await self.save(verification="failed")

    async def _execute(
        self, project: AIProjectClient, *, inner: httpx2.AsyncBaseTransport | None = None
    ) -> dict[str, object]:
        receipts: list[ReportReference] = []
        async with project.get_openai_client(
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=ProjectTransport(
                    httpx2.AsyncHTTPTransport(retries=0, trust_env=False)
                    if inner is None
                    else inner,
                    self.admit,
                    self.inspect,
                ),
                trust_env=False,
                follow_redirects=False,
            ),
        ) as client:
            for metric in ORIGINS:
                self.current = metric
                self.seen.clear()
                state = self.report
                if self.recovery and state.evaluation_id is None and state.mutations:
                    found = [
                        value
                        async for value in client.evals.list(limit=100)
                        if self.owned(value.metadata)
                    ]
                    if len(found) != 1:
                        raise EvaluationFailure("ambiguous_evaluation_publication")
                    await self.save(evaluation_id=native_rows.identifier(found[0].id), pending=None)
                if self.report.evaluation_id is None:
                    value = await client.evals.create(
                        name=self.name,
                        metadata=self.metadata(),
                        data_source_config={
                            "type": "custom",
                            "item_schema": native_rows.wire_schema(BaselinePublicationRow),
                        },
                        testing_criteria=[
                            {
                                "type": "python",
                                "name": ORIGINS[metric],
                                "source": self.code,
                                "pass_threshold": self.threshold,
                            }
                        ],
                    )
                    if not self.owned(value.metadata):
                        raise EvaluationFailure("foreign_evaluation_publication")
                    await self.save(evaluation_id=native_rows.identifier(value.id), pending=None)
                evaluation_id = native_rows.identifier(self.report.evaluation_id)
                retained = await client.evals.retrieve(evaluation_id)
                if (
                    not self.owned(retained.metadata)
                    or retained.name != self.name
                    or retained.id != evaluation_id
                ):
                    raise EvaluationFailure("foreign_evaluation_publication")
                if self.recovery and self.report.run_id is None and "run" in self.report.mutations:
                    found_runs = [
                        value
                        async for value in client.evals.runs.list(evaluation_id, limit=100)
                        if self.owned(value.metadata)
                    ]
                    if len(found_runs) != 1:
                        raise EvaluationFailure("ambiguous_run_publication")
                    await self.save(run_id=native_rows.identifier(found_runs[0].id), pending=None)
                if self.report.run_id is None:
                    value_run = await client.evals.runs.create(
                        evaluation_id,
                        name=self.name,
                        metadata=self.metadata(),
                        data_source={
                            "type": "jsonl",
                            "source": {
                                "type": "file_content",
                                "content": [
                                    {"item": native_rows.wire_row(row)} for row in self.rows()
                                ],
                            },
                        },
                    )
                    if not self.owned(value_run.metadata):
                        raise EvaluationFailure("foreign_run_publication")
                    await self.save(run_id=native_rows.identifier(value_run.id), pending=None)
                run_id = native_rows.identifier(self.report.run_id)
                while True:
                    completed = await client.evals.runs.retrieve(run_id, eval_id=evaluation_id)
                    if (
                        not self.owned(completed.metadata)
                        or completed.id != run_id
                        or completed.eval_id != evaluation_id
                        or completed.name != self.name
                    ):
                        raise EvaluationFailure("foreign_run_publication")
                    if completed.status == "completed":
                        break
                    if completed.status not in ("queued", "in_progress"):
                        raise EvaluationFailure("publication_run_failed")
                    if self.budget.deadline - self.budget.clock() <= 5:
                        raise EvaluationFailure("baseline_execution_deadline")
                    await asyncio.sleep(5)
                async for _ in client.evals.runs.output_items.list(
                    run_id, eval_id=evaluation_id, limit=100
                ):
                    pass
                counts = completed.result_counts
                rows = self.rows()
                passed = sum(row.score >= self.threshold for row in rows)
                if (
                    self.seen != {row.case_id for row in rows}
                    or counts is None
                    or counts.total != len(rows)
                    or counts.passed != passed
                    or counts.failed != len(rows) - passed
                    or counts.errored != 0
                    or getattr(counts, "skipped", 0) != 0
                ):
                    raise EvaluationFailure("publication_result_counts_mismatch")
                report_url = urlsplit(completed.report_url or "")
                if report_url.scheme != "https" or report_url.netloc != "ai.azure.com":
                    raise EvaluationFailure("invalid_publication_report_reference")
                await self.save(verification="api_verified")
                receipts.append(
                    ReportReference(
                        metric_id=metric,
                        cases=len(rows),
                        evaluation_id=evaluation_id,
                        run_id=run_id,
                        report_url=completed.report_url or "",
                    )
                )
        receipt = BaselinePublicationReceipt(
            protocol="baseline-v1",
            outcome="api_verified",
            ui_verified=False,
            cases=12,
            metric_reports=tuple(receipts),
            approval_sha256=self.run.canonical_sha256,
            results_sha256=self.result_hash,
            model_calls=0,
        )
        await self.run.publication_receipt(receipt)
        return receipt.model_dump(mode="json")
