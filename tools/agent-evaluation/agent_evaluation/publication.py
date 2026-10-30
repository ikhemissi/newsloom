import asyncio
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Literal
from urllib.parse import urlsplit

import httpx2
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field, JsonValue, StrictInt, StrictStr

from agent_evaluation import grader
from agent_evaluation.budget import CONTEXT_TOKEN_BOUND
from agent_evaluation.context import Context, read_context
from agent_evaluation.foundry import CatalogTransport, ProjectTransport, project_endpoint
from agent_evaluation.inputs import FIXTURE_SHA256, StrictModel, json_document, load_pilot
from agent_evaluation.policy import EvaluationFailure
from agent_evaluation.runner import (
    Approval,
    Digest,
    Journal,
    MeasuredCase,
    PilotResult,
    journal_lock,
    metric_digest,
    read_approval,
    read_file,
)

ORIGIN: Final = "imported_deepeval_faithfulness"
Mutation = Literal["evaluation", "run"]


class PublicationRow(MeasuredCase):
    metric_origin: Literal["imported_deepeval_faithfulness"]
    source_sha256: Digest
    fixture_sha256: Digest
    metric_sha256: Digest
    configuration_sha256: Digest
    context_sha256: Digest
    judge_snapshot: Literal["gpt-5.4-mini-2026-03-17"]
    question: StrictStr
    evidence: StrictStr
    answer: StrictStr


def _wire_schema() -> dict[str, object]:
    schema = PublicationRow.model_json_schema()
    schema["properties"]["score"] = {"type": "string"}
    return schema


def _wire_row(row: PublicationRow) -> dict[str, object]:
    value = row.model_dump(mode="json")
    value["score"] = repr(row.score)
    return value


def _read_row(value: JsonValue) -> PublicationRow:
    if isinstance(value, dict) and "item" in value:
        if set(value) != {"item"} or not isinstance(value["item"], dict):
            raise EvaluationFailure("invalid_publication_datasource_wrapper")
        value = value["item"]
    if isinstance(value, dict):
        raw = value.get("score")
        if isinstance(raw, str):
            try:
                score = float(raw)
            except ValueError:
                raise EvaluationFailure("invalid_publication_score_encoding") from None
            if not math.isfinite(score) or not 0 <= score <= 1 or repr(score) != raw:
                raise EvaluationFailure("invalid_publication_score_encoding")
            value = {**value, "score": score}
    return PublicationRow.model_validate_json(json.dumps(value))


def _has_error(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(_has_error(child) for child in value.values())
    return value is not None


class PublicationState(StrictModel):
    schema_version: StrictInt = Field(ge=2, le=2)
    publication_protocol: Literal["native-python"]
    configuration_sha256: Digest
    results_sha256: Digest
    reads: StrictInt = Field(ge=0, le=60)
    mutations: tuple[Mutation, ...]
    pending: Mutation | None
    evaluation_id: StrictStr | None
    run_id: StrictStr | None
    verification: Literal["pending", "api_verified", "failed"]


@dataclass(frozen=True)
class Bundle:
    approval: Approval
    result: PilotResult
    journal: Journal
    rows: tuple[PublicationRow, PublicationRow]
    state: PublicationState
    recovery: bool


def _identifier(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-zA-Z0-9_-]{1,256}", value) is None:
        raise EvaluationFailure("invalid_publication_reference")
    return value


def _validate_accounting(result: PilotResult, approval: Approval) -> None:
    receipt = result.budget
    prices = approval.validate_execution(datetime.now(UTC))
    counts = (
        receipt.usage_observed,
        receipt.usage_unknown,
        receipt.request_bytes,
        receipt.response_bytes_observed,
        receipt.response_bytes_exposure,
        receipt.input_tokens_observed,
        receipt.output_tokens_observed,
    )
    observed = prices.cost(receipt.input_tokens_observed, receipt.output_tokens_observed)
    reserved = receipt.usage_unknown * prices.cost(CONTEXT_TOKEN_BOUND, 1024)
    try:
        amounts = tuple(
            Decimal(value)
            for value in (
                receipt.estimated_observed_usd,
                receipt.estimated_reserved_unknown_usd,
                receipt.estimated_total_exposure_usd,
            )
        )
    except InvalidOperation:
        raise EvaluationFailure("invalid_persisted_evaluation_accounting") from None
    if (
        any(value < 0 for value in counts)
        or not 1 <= receipt.attempts <= 12
        or receipt.usage_observed + receipt.usage_unknown != receipt.attempts
        or receipt.usage_complete != (receipt.usage_unknown == 0)
        or receipt.admission_halted
        or not math.isfinite(receipt.remaining_s)
        or not 0 < receipt.remaining_s <= 1800
        or not receipt.usage_observed
        <= receipt.input_tokens_observed
        <= (receipt.usage_observed * CONTEXT_TOKEN_BOUND)
        or not receipt.usage_observed
        <= receipt.output_tokens_observed
        <= (receipt.usage_observed * 1024)
        or not receipt.attempts <= receipt.request_bytes <= 512 * 1024
        or receipt.response_bytes_observed > receipt.response_bytes_exposure
        or receipt.response_bytes_exposure > 512 * 1024
        or any(not value.is_finite() or value < 0 for value in amounts)
        or amounts != (observed, reserved, observed + reserved)
        or observed + reserved > Decimal(1)
    ):
        raise EvaluationFailure("invalid_persisted_evaluation_accounting")


def load_bundle(path: Path, approved_sha256: str, *, registry: Path | None = None) -> Bundle:
    approval_bytes = read_approval(path / "approval.json")
    digest = hashlib.sha256(approval_bytes).hexdigest()
    if digest != approved_sha256:
        raise EvaluationFailure("execution_approval_digest_mismatch")
    json_document(approval_bytes)
    approval = Approval.model_validate_json(approval_bytes)
    approval.validate_execution(datetime.now(UTC))
    journal = Journal.reopen(path, digest, registry=registry)
    result_bytes = read_file(path / "results.json", 64 * 1024)
    json_document(result_bytes)
    result = PilotResult.model_validate_json(result_bytes)
    if (
        result.source_sha256 != approval.source_sha256
        or result.fixture_sha256 != FIXTURE_SHA256
        or result.context_sha256 != approval.context_sha256
        or result.configuration_sha256 != digest
        or result.metric_sha256 != metric_digest()
        or tuple(row.case_id for row in result.cases) != ("p01", "p02")
        or result.started_at.utcoffset() is None
        or result.deadline.utcoffset() is None
        or not approval.approved_at <= result.started_at < result.deadline
        or result.deadline != min(result.started_at + timedelta(minutes=30), approval.expires_at)
    ):
        raise EvaluationFailure("stale_or_foreign_evaluation_results")
    approval.validate_execution(result.started_at)
    _validate_accounting(result, approval)
    pilot = load_pilot()
    rows = tuple(
        PublicationRow(
            **measured.model_dump(),
            metric_origin=ORIGIN,
            source_sha256=result.source_sha256,
            fixture_sha256=result.fixture_sha256,
            metric_sha256=result.metric_sha256,
            configuration_sha256=digest,
            context_sha256=result.context_sha256,
            judge_snapshot=result.judge_snapshot,
            question=pilot.question,
            evidence=pilot.evidence,
            answer=case.answer,
        )
        for case, measured in zip(pilot.cases, result.cases, strict=True)
    )
    results_digest = hashlib.sha256(result_bytes).hexdigest()
    state_path = path / "publication-state.json"
    if state_path.is_symlink():
        raise EvaluationFailure("foreign_publication_recovery_record")
    recovery = state_path.exists()
    if recovery:
        state_bytes = read_file(state_path, 64 * 1024)
        json_document(state_bytes)
        state = PublicationState.model_validate_json(state_bytes)
        if (
            state.configuration_sha256 != digest
            or state.results_sha256 != results_digest
            or len(set(state.mutations)) != len(state.mutations)
            or len(state.mutations) > approval.publication_mutation_limit
            or (
                state.pending is not None
                and (not state.mutations or state.pending != state.mutations[-1])
            )
            or state.mutations != ("evaluation", "run")[: len(state.mutations)]
            or (len(state.mutations) >= 2 and state.evaluation_id is None)
            or (state.evaluation_id is not None and "evaluation" not in state.mutations)
            or (state.run_id is not None and "run" not in state.mutations)
        ):
            raise EvaluationFailure("foreign_publication_recovery_record")
    else:
        state = PublicationState(
            schema_version=2,
            publication_protocol="native-python",
            configuration_sha256=digest,
            results_sha256=results_digest,
            reads=0,
            mutations=(),
            pending=None,
            evaluation_id=None,
            run_id=None,
            verification="pending",
        )
    return Bundle(approval, result, journal, (rows[0], rows[1]), state, recovery)


class Publisher:
    def __init__(
        self, bundle: Bundle, context: Context, *, continue_unsubmitted: bool = False
    ) -> None:
        self.bundle = bundle
        self.state = bundle.state
        self.continue_unsubmitted = continue_unsubmitted
        self.endpoint = project_endpoint(
            context.environment["AGENT_EVALUATION_PROJECT_ENDPOINT"],
            context.environment["MODEL_ENDPOINT"],
            context.environment["AGENT_EVALUATION_PROJECT_ID"],
        )
        self.name = "newsloom_pilot_" + bundle.result.configuration_sha256[:24]
        self.prefix = httpx2.URL(self.endpoint)
        self.eval_path = self.prefix.path + "/openai/v1/evals"
        self.deadline = time.monotonic() + self.remaining()
        self.seen: set[str] = set()
        self.code = Path(grader.__file__).read_text()

    def remaining(self) -> float:
        remaining = (self.bundle.result.deadline - datetime.now(UTC)).total_seconds()
        if hasattr(self, "deadline"):
            remaining = min(remaining, self.deadline - time.monotonic())
        if remaining <= 0:
            raise EvaluationFailure("evaluation_deadline")
        return remaining

    async def save(self, **updates: object) -> None:
        self.state = self.state.model_copy(update=updates)
        await self.bundle.journal.persist(
            "publication-state.json", self.state.model_dump(mode="json")
        )

    def metadata(self) -> dict[str, str]:
        return {
            "configuration_sha256": self.bundle.result.configuration_sha256,
            "origin": ORIGIN,
            "grader_protocol": self.bundle.approval.publication_protocol,
        }

    async def admit(self, request: httpx2.Request) -> float:
        request.headers["Foundry-Features"] = "Evaluations=V1Preview"
        await asyncio.to_thread(self.bundle.approval.validate_execution, datetime.now(UTC))
        url = request.url
        if (url.scheme, url.host, url.port) != (
            self.prefix.scheme,
            self.prefix.host,
            self.prefix.port,
        ) or set(url.params.keys()) - {"api-version", "after", "limit", "order", "order_by"}:
            raise EvaluationFailure("publication_endpoint_rejected")
        mutation: Mutation | None = None
        allowed = False
        if url.path == self.eval_path:
            allowed = request.method == "GET" and self.bundle.recovery
            if request.method == "POST":
                mutation = "evaluation"
        elif self.state.evaluation_id is not None:
            evaluation = self.eval_path + "/" + _identifier(self.state.evaluation_id)
            runs = evaluation + "/runs"
            allowed = request.method == "GET" and url.path in (evaluation, runs)
            if request.method == "POST" and url.path == runs:
                mutation = "run"
            if self.state.run_id is not None:
                run = runs + "/" + _identifier(self.state.run_id)
                allowed |= request.method == "GET" and url.path in (run, run + "/output_items")
        self.remaining()
        if mutation is not None:
            if (
                (self.bundle.recovery and not self.continue_unsubmitted)
                or mutation in self.state.mutations
                or self.state.pending is not None
                or len(self.state.mutations) >= self.bundle.approval.publication_mutation_limit
                or mutation != ("evaluation", "run")[len(self.state.mutations)]
            ):
                raise EvaluationFailure("publication_mutation_replay_rejected")
            await self.save(mutations=(*self.state.mutations, mutation), pending=mutation)
        elif allowed:
            if self.state.reads >= self.bundle.approval.publication_read_limit:
                raise EvaluationFailure("publication_read_limit")
            await self.save(reads=self.state.reads + 1)
        else:
            raise EvaluationFailure("publication_endpoint_rejected")
        return min(self.remaining(), self.bundle.approval.publication_request_timeout_s)

    def inspect(self, request: httpx2.Request, value: dict[str, JsonValue]) -> None:
        if _has_error(value.get("error")):
            raise EvaluationFailure("publication_service_error")
        if request.url.path == self.eval_path + "/" + str(self.state.evaluation_id):
            criteria = value.get("testing_criteria")
            schema = value.get("data_source_config")
            expected_schema = _wire_schema()
            if (
                not isinstance(criteria, list)
                or len(criteria) != 1
                or not isinstance(criteria[0], dict)
                or set(criteria[0]) - {"id", "type", "name", "source", "pass_threshold"}
                or criteria[0].get("type") != "python"
                or criteria[0].get("name") != ORIGIN
                or criteria[0].get("source") != self.code
                or type(criteria[0].get("pass_threshold")) not in (int, float)
                or criteria[0].get("pass_threshold") != 0.5
                or not isinstance(schema, dict)
                or schema.get("type") != "custom"
                or schema.get("item_schema") not in ({}, expected_schema)
                or ("schema" in schema and schema["schema"] != {"item": expected_schema})
                or (
                    schema.get("item_schema") == {}
                    and schema.get("schema") != {"item": expected_schema}
                )
                or schema.get("include_sample_schema") not in (None, False)
            ):
                raise EvaluationFailure("evaluation_definition_drift")
        if request.url.path.endswith("/output_items"):
            data = value.get("data")
            if not isinstance(data, list) or type(value.get("has_more")) is not bool:
                raise EvaluationFailure("incomplete_publication_page")
            if value["has_more"] and (
                not data
                or not isinstance(data[-1], dict)
                or value.get("last_id") != data[-1].get("id")
            ):
                raise EvaluationFailure("incomplete_publication_page")
            for item in data:
                self.validate_item(item)
        counts = value.get("result_counts")
        if isinstance(counts, dict) and counts.get("errored") not in (None, 0):
            raise EvaluationFailure("publication_item_execution_error")
        if (
            self.state.evaluation_id is not None
            and self.state.run_id is not None
            and request.url.path
            == self.eval_path + "/" + self.state.evaluation_id + "/runs/" + self.state.run_id
            and value.get("status") == "completed"
        ):
            passed = sum(row.score >= 0.5 for row in self.bundle.rows)
            expected_counts = {"total": 2, "passed": passed, "failed": 2 - passed, "errored": 0}
            if (
                not isinstance(counts, dict)
                or any(
                    type(counts.get(key)) is not int or counts[key] != count
                    for key, count in expected_counts.items()
                )
                or (
                    "skipped" in counts
                    and (type(counts["skipped"]) is not int or counts["skipped"] != 0)
                )
            ):
                raise EvaluationFailure("publication_result_counts_mismatch")

    def validate_item(self, item: JsonValue) -> None:
        if not isinstance(item, dict):
            raise EvaluationFailure("invalid_publication_item")
        results = item.get("results")
        if (
            item.get("eval_id") != self.state.evaluation_id
            or item.get("run_id") != self.state.run_id
            or item.get("status") != "completed"
            or _has_error(item.get("error"))
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
                _has_error(sample.get("error")) or sample.get("errors")
            ):
                raise EvaluationFailure("publication_item_execution_error")
        row = _read_row(item.get("datasource_item"))
        expected = {value.case_id: value for value in self.bundle.rows}
        score = metric.get("score")
        if (
            row.case_id in self.seen
            or row != expected.get(row.case_id)
            or metric.get("type") != "python"
            or metric.get("status") != "completed"
            or metric.get("name") != ORIGIN
            or type(score) not in (int, float)
            or score != row.score
            or type(metric.get("passed")) is not bool
            or metric["passed"] != (row.score >= 0.5)
            or _has_error(metric.get("error"))
            or metric.get("errors")
            or metric.get("error_message")
        ):
            raise EvaluationFailure("publication_score_or_lineage_mismatch")
        self.seen.add(row.case_id)

    def owned(self, metadata: dict[str, str] | None) -> bool:
        return metadata is not None and all(
            metadata.get(key) == value for key, value in self.metadata().items()
        )

    async def execute(self, project: AIProjectClient) -> dict[str, object]:
        async with project.get_openai_client(
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=ProjectTransport(
                    httpx2.AsyncHTTPTransport(retries=0, trust_env=False),
                    self.admit,
                    self.inspect,
                ),
                trust_env=False,
                follow_redirects=False,
            ),
        ) as client:
            if (
                self.bundle.recovery
                and self.state.evaluation_id is None
                and "evaluation" in self.state.mutations
            ):
                owned = [
                    value
                    async for value in client.evals.list(limit=100)
                    if self.owned(value.metadata)
                ]
                if len(owned) != 1:
                    raise EvaluationFailure("ambiguous_evaluation_publication")
                await self.save(evaluation_id=_identifier(owned[0].id), pending=None)
            if self.state.evaluation_id is None:
                evaluation = await client.evals.create(
                    name=self.name,
                    metadata=self.metadata(),
                    data_source_config={
                        "type": "custom",
                        "item_schema": _wire_schema(),
                    },
                    testing_criteria=[
                        {
                            "type": "python",
                            "name": ORIGIN,
                            "source": self.code,
                            "pass_threshold": 0.5,
                        }
                    ],
                )
                if not self.owned(evaluation.metadata):
                    raise EvaluationFailure("foreign_evaluation_publication")
                await self.save(evaluation_id=_identifier(evaluation.id), pending=None)
            evaluation_id = _identifier(self.state.evaluation_id)
            retained_evaluation = await client.evals.retrieve(evaluation_id)
            if (
                not self.owned(retained_evaluation.metadata)
                or retained_evaluation.name != self.name
                or retained_evaluation.id != evaluation_id
            ):
                raise EvaluationFailure("foreign_evaluation_publication")
            if self.bundle.recovery and self.state.run_id is None and "run" in self.state.mutations:
                owned_runs = [
                    value
                    async for value in client.evals.runs.list(evaluation_id, limit=100)
                    if self.owned(value.metadata)
                ]
                if len(owned_runs) != 1:
                    raise EvaluationFailure("ambiguous_run_publication")
                await self.save(run_id=_identifier(owned_runs[0].id), pending=None)
            if self.state.run_id is None:
                run = await client.evals.runs.create(
                    evaluation_id,
                    name=self.name,
                    metadata=self.metadata(),
                    data_source={
                        "type": "jsonl",
                        "source": {
                            "type": "file_content",
                            "content": [{"item": _wire_row(row)} for row in self.bundle.rows],
                        },
                    },
                )
                if not self.owned(run.metadata):
                    raise EvaluationFailure("foreign_run_publication")
                await self.save(run_id=_identifier(run.id), pending=None)
            run_id = _identifier(self.state.run_id)
            while True:
                retained_run = await client.evals.runs.retrieve(run_id, eval_id=evaluation_id)
                if (
                    not self.owned(retained_run.metadata)
                    or retained_run.eval_id != evaluation_id
                    or retained_run.id != run_id
                    or retained_run.name != self.name
                ):
                    raise EvaluationFailure("foreign_run_publication")
                if retained_run.status == "completed":
                    break
                if retained_run.status not in ("queued", "in_progress"):
                    raise EvaluationFailure("publication_run_failed")
                wait = self.bundle.approval.publication_poll_spacing_s
                if wait >= self.remaining():
                    raise EvaluationFailure("evaluation_deadline")
                await asyncio.sleep(wait)
            async for _ in client.evals.runs.output_items.list(
                run_id, eval_id=evaluation_id, limit=100
            ):
                pass
            if self.seen != {"p01", "p02"}:
                raise EvaluationFailure("publication_case_set_mismatch")
            counts = retained_run.result_counts
            passed = sum(row.score >= 0.5 for row in self.bundle.rows)
            if (
                counts is None
                or counts.errored != 0
                or counts.total != 2
                or counts.passed != passed
                or counts.failed != 2 - passed
                or getattr(counts, "skipped", 0) != 0
            ):
                raise EvaluationFailure("publication_result_counts_mismatch")
            report = urlsplit(retained_run.report_url or "")
            if report.scheme != "https" or report.netloc != "ai.azure.com":
                raise EvaluationFailure("invalid_publication_report_reference")
            receipt: dict[str, object] = {
                "outcome": "api_verified",
                "verified_at": datetime.now(UTC).isoformat(),
                "ui_verified": False,
                "publication_protocol": self.state.publication_protocol,
                "cases": 2,
                "report_url": retained_run.report_url,
                "configuration_sha256": self.state.configuration_sha256,
                "results_sha256": self.state.results_sha256,
                "evaluation_id": evaluation_id,
                "run_id": run_id,
                "reads": self.state.reads,
                "mutations": len(self.state.mutations),
                "budget": self.bundle.result.budget.model_dump(mode="json"),
            }
            await self.bundle.journal.persist("publication.json", receipt)
            await self.save(verification="api_verified")
            return receipt


async def publish(
    path: Path, approved_sha256: str, *, continue_unsubmitted: bool = False
) -> dict[str, object]:
    await asyncio.to_thread(load_bundle, path, approved_sha256)
    lock = await asyncio.to_thread(journal_lock, path)
    try:
        bundle = await asyncio.to_thread(load_bundle, path, approved_sha256)
        remaining = (bundle.result.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise EvaluationFailure("evaluation_deadline")
        async with asyncio.timeout(remaining):
            return await _publish(bundle, continue_unsubmitted=continue_unsubmitted)
    finally:
        await asyncio.to_thread(lock.close)


async def _publish(bundle: Bundle, *, continue_unsubmitted: bool) -> dict[str, object]:
    context = await read_context()
    if context.digest() != bundle.approval.context_sha256:
        raise EvaluationFailure("execution_context_digest_mismatch")
    publisher = await asyncio.to_thread(
        Publisher, bundle, context, continue_unsubmitted=continue_unsubmitted
    )
    await publisher.save(verification="pending")
    transport = CatalogTransport(
        ProjectTransport(
            httpx2.AsyncHTTPTransport(retries=0, trust_env=False),
            publisher.admit,
            publisher.inspect,
        )
    )
    completed = False
    try:
        async with (
            AzureCliCredential(
                tenant_id=context.environment["AGENT_TENANT_ID"], process_timeout=30
            ) as credential,
            AIProjectClient(
                endpoint=publisher.endpoint,
                credential=credential,
                allow_preview=True,
                retry_total=0,
                redirect_max=0,
                transport=transport,
            ) as project,
        ):
            receipt = await publisher.execute(project)
            completed = True
            return receipt
    finally:
        if not completed:
            await publisher.save(verification="failed")
