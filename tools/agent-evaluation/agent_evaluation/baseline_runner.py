import asyncio
import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AccessToken
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import AzureCliCredential
from pydantic import JsonValue, TypeAdapter

from agent_evaluation.baseline_admission import (
    ReadinessReceipt,
    admit_native_plan,
    object_value,
)
from agent_evaluation.baseline_budget import BaselineBudget, BaselineRun
from agent_evaluation.baseline_capture import CaptureSession
from agent_evaluation.baseline_inputs import FrozenBaseline, parse_document
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.baseline_scoring import BaselineCompletion
from agent_evaluation.baseline_workflow import execute_workflow
from agent_evaluation.context import (
    COMMAND_ADMISSION,
    COMMAND_DEADLINE,
    Context,
    command,
    read_context,
    schedule_window_delay,
    text,
    verify_schedule_window,
)
from agent_evaluation.foundry import project_endpoint
from agent_evaluation.inputs import json_document
from agent_evaluation.judge import model_client
from agent_evaluation.policy import EvaluationFailure, configure_privacy
from agent_evaluation.runner import read_file


class MeteredCredential:
    def __init__(self, credential: AsyncTokenCredential, budget: BaselineBudget) -> None:
        self.credential, self.budget = credential, budget

    async def get_token(
        self,
        *scopes: str,
        claims: str | None = None,
        tenant_id: str | None = None,
        enable_cae: bool = False,
        **kwargs: object,
    ) -> AccessToken:
        if scopes not in (
            ("https://cognitiveservices.azure.com/.default",),
            ("https://ai.azure.com/.default",),
        ):
            raise EvaluationFailure("baseline_credential_scope")
        await self.budget.admit("auth_http")
        async with asyncio.timeout(min(30.0, self.budget.deadline - self.budget.clock())):
            token = await self.credential.get_token(
                *scopes, claims=claims, tenant_id=tenant_id, enable_cae=enable_cae, **kwargs
            )
        self.budget.guard()
        return token

    async def close(self) -> None:
        await self.credential.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.close()


async def wait_for_schedule(budget: BaselineBudget) -> None:
    while delay := schedule_window_delay():
        budget.guard()
        if delay >= budget.deadline - budget.clock():
            raise EvaluationFailure("baseline_execution_deadline")
        await budget.judge.sleep(delay)
        budget.guard()


async def wait_for_model_readiness(budget: BaselineBudget, context: Context) -> None:
    while True:
        budget.guard()
        await wait_for_schedule(budget)
        try:
            await context.ensure_ready()
            budget.guard()
            return
        except EvaluationFailure as error:
            if str(error) == "shared_deployment_schedule_window":
                continue
            if str(error) != "shared_deployment_busy":
                raise
        if budget.deadline - budget.clock() <= 30:
            raise EvaluationFailure("baseline_execution_deadline")
        await budget.judge.sleep(30)
        budget.guard()


async def run(
    manifest: Path,
    frozen_path: Path,
    readiness_path: Path,
    plans_path: Path,
    approved_sha256: str,
    output: Path,
    *,
    prior_usage: Path | None = None,
) -> dict[str, object]:
    configure_privacy()
    approval_bytes = await asyncio.to_thread(read_file, manifest, 32 * 1024)
    approved = BaselineRun.parse_approval(approval_bytes, approved_sha256)
    frozen = parse_document(
        FrozenBaseline, await asyncio.to_thread(read_file, frozen_path, 256 * 1024)
    )
    approved.validate_execution(datetime.now(UTC), frozen)
    if frozen.snapshot_version > 1 and approved.prior_usage_sha256 is None:
        raise EvaluationFailure("baseline_prior_usage_required")
    if approved.prior_usage_sha256 is not None:
        if prior_usage is None:
            raise EvaluationFailure("baseline_prior_usage_required")
        previous = await asyncio.to_thread(read_file, prior_usage, 256 * 1024)
        if hashlib.sha256(previous).hexdigest() != approved.prior_usage_sha256:
            raise EvaluationFailure("baseline_prior_usage_fingerprint_mismatch")
        json_document(previous)
        previous_document = object_value(
            TypeAdapter(JsonValue).validate_json(previous, strict=True)
        )
        estimates = object_value(previous_document.get("estimated_usd"))
        if estimates.get("conservative_combined_exposure") != approved.prior_model_exposure_usd:
            raise EvaluationFailure("baseline_prior_usage_exposure_mismatch")
    elif prior_usage is not None:
        raise EvaluationFailure("baseline_unapproved_prior_usage")
    readiness_bytes = await asyncio.to_thread(read_file, readiness_path, 32 * 1024)
    if hashlib.sha256(readiness_bytes).hexdigest() != approved.readiness_receipt_sha256:
        raise EvaluationFailure("baseline_readiness_fingerprint_mismatch")
    receipt = parse_document(ReadinessReceipt, readiness_bytes)
    receipt.verify(frozen, approved.approved_at)
    plan_bytes = await asyncio.to_thread(read_file, plans_path, 16 * 1024 * 1024)
    json_document(plan_bytes)
    bundle = object_value(TypeAdapter(JsonValue).validate_json(plan_bytes, strict=True))
    if set(bundle) != {"application", "agent", "agent-evaluation"}:
        raise EvaluationFailure("baseline_admission_layer_set")
    for layer in receipt.layers:
        data = object_value(bundle[layer.layer])
        if set(data) != {"plan", "retained"}:
            raise EvaluationFailure("baseline_admission_bundle_fields")
        measured = admit_native_plan(
            object_value(data["plan"]),
            object_value(data["retained"]),
            layer.layer,
            reviewed_at=receipt.observed_at,
            image_sha256=receipt.image_sha256,
        )
        if measured != layer:
            raise EvaluationFailure("baseline_admission_plan_fingerprint_mismatch")
    journal = BaselineRun(output, approval_bytes, approved_sha256, frozen)
    context: Context | None = None
    last_readiness = float("-inf")

    async def ready() -> None:
        nonlocal last_readiness
        if context is None:
            raise EvaluationFailure("baseline_context_not_ready")
        # Schedule checks are local; inventory refreshes share the finite read budget.
        await wait_for_schedule(budget)
        verify_schedule_window()
        if time.monotonic() - last_readiness >= 300:
            await wait_for_model_readiness(budget, context)
            last_readiness = time.monotonic()

    budget = BaselineBudget(approved, frozen, persist=journal.checkpoint, ready=ready)
    await budget.start()

    async def admit_command(arguments: list[str]) -> None:
        if arguments[:3] == ["az", "account", "get-access-token"]:
            await budget.admit("auth_http")
        elif arguments[:3] in (
            ["azd", "env", "get-values"],
            ["az", "account", "show"],
        ) or (arguments[:4] == ["az", "rest", "--method", "get"] and "--url" in arguments):
            after_capture = len(budget.agents) == 12 and all(
                row.receipt is not None for row in budget.agents.values()
            )
            await budget.admit("metadata_after" if after_capture else "metadata_before")
        else:
            raise EvaluationFailure("baseline_control_command_rejected")

    observer = COMMAND_ADMISSION.set(admit_command)
    control_deadline = COMMAND_DEADLINE.set(budget.deadline)
    completed = False
    try:
        context = await read_context()
        if (
            context.digest() != frozen.bindings.context_sha256
            or not context.environment["AGENT_IMAGE"].endswith("@sha256:" + receipt.image_sha256)
            or context.environment["AGENT_IMAGE_REVISION"]
            != frozen.bindings.accepted_runtime.source_sha256
        ):
            raise EvaluationFailure("baseline_context_drift")
        raw = await command(
            [
                "azd",
                "env",
                "get-values",
                "--environment",
                "dev",
                "--output",
                "json",
            ]
        )
        from agent_evaluation.baseline_capture import CAPTURE_ENVIRONMENT

        environment = {key: text(raw, key) for key in CAPTURE_ENVIRONMENT}
        if document_digest(environment) != receipt.capture_environment_sha256:
            raise EvaluationFailure("baseline_capture_environment_drift")
        endpoint = project_endpoint(
            context.environment["AGENT_EVALUATION_PROJECT_ENDPOINT"],
            context.environment["MODEL_ENDPOINT"],
            context.environment["AGENT_EVALUATION_PROJECT_ID"],
        )
        async with AzureCliCredential(process_timeout=30) as credential:
            metered = MeteredCredential(credential, budget)
            async with (
                model_client(
                    context.environment["MODEL_ENDPOINT"],
                    context.environment["ENRICHMENT_DEPLOYMENT"],
                    metered,
                    budget.judge,
                ) as client,
                AIProjectClient(
                    endpoint=endpoint,
                    credential=metered,
                    allow_preview=True,
                    retry_total=0,
                    redirect_max=0,
                ) as project,
            ):
                result = await execute_workflow(
                    budget,
                    journal,
                    BaselineCompletion(
                        client,
                        context.environment["ENRICHMENT_DEPLOYMENT"],
                        budget.judge,
                    ),
                    lambda: CaptureSession(budget, journal, environment),
                    project,
                    context,
                )
        completed = True
        return result
    finally:
        COMMAND_ADMISSION.reset(observer)
        COMMAND_DEADLINE.reset(control_deadline)
        if not completed:
            await budget.halt()
