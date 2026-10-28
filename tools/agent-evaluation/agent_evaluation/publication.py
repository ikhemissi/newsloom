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
from azure.ai.projects.models import CodeBasedEvaluatorDefinition, EvaluatorVersion
from azure.ai.projects.models import TestingCriterionAzureAIEvaluator as AzureAICriterion
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
Mutation = Literal["catalog", "evaluation", "run"]


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


class PublicationState(StrictModel):
    configuration_sha256: Digest
    results_sha256: Digest
    reads: StrictInt = Field(ge=0, le=60)
    mutations: tuple[Mutation, ...]
    pending: Mutation | None
    catalog_version: StrictStr | None
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
            or (state.pending is not None and state.pending not in state.mutations)
            or state.mutations != ("catalog", "evaluation", "run")[: len(state.mutations)]
            or (len(state.mutations) >= 2 and state.catalog_version is None)
            or (len(state.mutations) >= 3 and state.evaluation_id is None)
            or (state.evaluation_id is not None and "evaluation" not in state.mutations)
            or (state.run_id is not None and "run" not in state.mutations)
        ):
            raise EvaluationFailure("foreign_publication_recovery_record")
    else:
        state = PublicationState(
            configuration_sha256=digest,
            results_sha256=results_digest,
            reads=0,
            mutations=(),
            pending=None,
            catalog_version=None,
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
        self.catalog = "newsloom_pilot_" + bundle.result.configuration_sha256[:24]
        self.deployment = context.environment["ENRICHMENT_DEPLOYMENT"]
        self.prefix = httpx2.URL(self.endpoint)
        self.catalog_path = self.prefix.path + "/evaluators/" + self.catalog + "/versions"
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
        return {"configuration_sha256": self.bundle.result.configuration_sha256, "origin": ORIGIN}

    async def admit(self, request: httpx2.Request) -> float:
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
        if url.path == self.catalog_path or url.path.startswith(self.catalog_path + "/"):
            allowed = request.method == "GET"
            if request.method == "POST" and url.path == self.catalog_path:
                mutation = "catalog"
        elif url.path == self.eval_path:
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
        if value.get("error"):
            raise EvaluationFailure("publication_service_error")
        if request.url.path == self.eval_path + "/" + str(self.state.evaluation_id):
            criteria = value.get("testing_criteria")
            schema = value.get("data_source_config")
            if (
                not isinstance(criteria, list)
                or len(criteria) != 1
                or not isinstance(criteria[0], dict)
                or criteria[0].get("type") != "azure_ai_evaluator"
                or criteria[0].get("name") != ORIGIN
                or criteria[0].get("evaluator_name") != self.catalog
                or criteria[0].get("initialization_parameters")
                != {
                    "deployment_name": self.deployment,
                    "pass_threshold": 0.5,
                }
                or criteria[0].get("data_mapping") != {"score": "{{item.score}}"}
                or not isinstance(schema, dict)
                or schema.get("type") != "custom"
                or schema.get("item_schema") != PublicationRow.model_json_schema()
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

    def validate_item(self, item: JsonValue) -> None:
        if not isinstance(item, dict):
            raise EvaluationFailure("invalid_publication_item")
        results = item.get("results")
        if (
            item.get("eval_id") != self.state.evaluation_id
            or item.get("run_id") != self.state.run_id
            or item.get("status") not in ("pass", "fail")
            or item.get("error")
            or item.get("errors")
            or not isinstance(results, list)
            or len(results) != 1
            or not isinstance(results[0], dict)
        ):
            raise EvaluationFailure("publication_item_execution_error")
        row = PublicationRow.model_validate_json(json.dumps(item.get("datasource_item")))
        expected = {value.case_id: value for value in self.bundle.rows}
        metric = results[0]
        score = metric.get("score")
        if (
            row.case_id in self.seen
            or row != expected[row.case_id]
            or metric.get("name") != ORIGIN
            or type(score) not in (int, float)
            or score != row.score
            or type(metric.get("passed")) is not bool
            or metric["passed"] != (row.score >= 0.5)
            or item["status"] != ("pass" if row.score >= 0.5 else "fail")
            or metric.get("error")
            or metric.get("errors")
            or metric.get("error_message")
            or metric.get("status") in ("error", "failed", "cancelled")
        ):
            raise EvaluationFailure("publication_score_or_lineage_mismatch")
        self.seen.add(row.case_id)

    def owned(self, metadata: dict[str, str] | None) -> bool:
        return metadata is not None and all(
            metadata.get(key) == value for key, value in self.metadata().items()
        )

    async def execute(self, project: AIProjectClient, deployment: str) -> dict[str, object]:
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
            if self.bundle.recovery and "catalog" in self.state.mutations:
                versions = [
                    value
                    async for value in project.evaluators.list_versions(self.catalog)
                    if self.owned(value.metadata)
                ]
                if len(versions) != 1:
                    raise EvaluationFailure("ambiguous_catalog_publication")
                evaluator = versions[0]
            else:
                evaluator = await project.evaluators.create_version(
                    self.catalog,
                    EvaluatorVersion(
                        evaluator_type="custom",
                        categories=["quality"],
                        display_name=ORIGIN,
                        supported_evaluation_levels=["turn"],
                        metadata=self.metadata(),
                        definition=CodeBasedEvaluatorDefinition(code_text=self.code),
                    ),
                )
            if (
                not self.owned(evaluator.metadata)
                or not isinstance(evaluator.definition, CodeBasedEvaluatorDefinition)
                or evaluator.definition.code_text != self.code
                or evaluator.version is None
            ):
                raise EvaluationFailure("foreign_catalog_evaluator")
            await self.save(
                catalog_version=_identifier(evaluator.version),
                pending=None if self.state.pending == "catalog" else self.state.pending,
            )
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
                    name=self.catalog,
                    metadata=self.metadata(),
                    data_source_config={
                        "type": "custom",
                        "item_schema": PublicationRow.model_json_schema(),
                    },
                    testing_criteria=[
                        AzureAICriterion(
                            type="azure_ai_evaluator",
                            name=ORIGIN,
                            evaluator_name=self.catalog,
                            initialization_parameters={
                                "deployment_name": deployment,
                                "pass_threshold": 0.5,
                            },
                            data_mapping={"score": "{{item.score}}"},
                        )
                    ],
                )
                if not self.owned(evaluation.metadata):
                    raise EvaluationFailure("foreign_evaluation_publication")
                await self.save(evaluation_id=_identifier(evaluation.id), pending=None)
            evaluation_id = _identifier(self.state.evaluation_id)
            retained_evaluation = await client.evals.retrieve(evaluation_id)
            if (
                not self.owned(retained_evaluation.metadata)
                or retained_evaluation.name != self.catalog
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
                    name=self.catalog,
                    metadata=self.metadata(),
                    data_source={
                        "type": "jsonl",
                        "source": {
                            "type": "file_content",
                            "content": [
                                {"item": row.model_dump(mode="json")} for row in self.bundle.rows
                            ],
                        },
                    },
                )
                if not self.owned(run.metadata):
                    raise EvaluationFailure("foreign_run_publication")
                await self.save(run_id=_identifier(run.id), pending=None)
            run_id = _identifier(self.state.run_id)
            while True:
                retained_run = await client.evals.runs.retrieve(run_id, eval_id=evaluation_id)
                if not self.owned(retained_run.metadata) or retained_run.eval_id != evaluation_id:
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
            report = urlsplit(retained_run.report_url or "")
            if report.scheme != "https" or report.netloc != "ai.azure.com":
                raise EvaluationFailure("invalid_publication_report_reference")
            receipt: dict[str, object] = {
                "outcome": "api_verified",
                "verified_at": datetime.now(UTC).isoformat(),
                "ui_verified": False,
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
    await context.verify_deployment()
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
            AzureCliCredential(tenant_id=context.environment["AGENT_TENANT_ID"]) as credential,
            AIProjectClient(
                endpoint=publisher.endpoint,
                credential=credential,
                allow_preview=True,
                retry_total=0,
                redirect_max=0,
                transport=transport,
            ) as project,
        ):
            receipt = await publisher.execute(project, context.environment["ENRICHMENT_DEPLOYMENT"])
            completed = True
            return receipt
    finally:
        if not completed:
            await publisher.save(verification="failed")
