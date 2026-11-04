import hashlib
import json
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx2
import pytest
from chat_fakes import scripted_chat
from fakes import Credential
from test_baseline_admission import LAYERS, native
from test_baseline_budget import approval
from test_baseline_publication import Service
from test_baseline_workflow import ROOT_WORKER, bound_fixture, workflow_context
from test_budget import Clock

from agent_evaluation import __main__, baseline_budget, baseline_runner, context
from agent_evaluation.baseline_admission import (
    LayerAdmission,
    ReadinessReceipt,
    admit_native_plan,
    infrastructure_digest,
)
from agent_evaluation.baseline_budget import BaselineApproval, BaselineBudget, BaselineBudgetReceipt
from agent_evaluation.baseline_capture import CAPTURE_ENVIRONMENT
from agent_evaluation.baseline_inputs import FrozenBaseline
from agent_evaluation.baseline_ipc import PrivateCaptureProcess
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.budget import MODEL_SNAPSHOT
from agent_evaluation.inputs import ROOT
from agent_evaluation.policy import EvaluationFailure


@pytest.mark.parametrize("environment_drift", [False, True])
def test_public_command_runs_one_complete_authored_baseline_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    environment_drift: bool,
) -> None:
    target_context = workflow_context()
    value = bound_fixture()
    runtime = value.provenance.accepted_runtime
    env = {
        **target_context.environment,
        "MCP_TENANT_ID": target_context.environment["AGENT_TENANT_ID"],
        "MCP_API_CLIENT_ID": str(UUID(int=101)),
        "AGENT_API_CLIENT_ID": str(UUID(int=102)),
        "MCP_PUBLIC_CLIENT_ID": str(UUID(int=103)),
        "AGENT_PUBLIC_CLIENT_ID": str(UUID(int=104)),
        "MCP_RESOURCE_URL": "https://mcp.test/mcp",
        "AGENT_RESOURCE_URL": "https://agent.test/a2a",
    }
    plans: dict[str, object] = {}
    layers: list[LayerAdmission] = []
    for layer in LAYERS:
        plan, retained = native(layer, image=runtime.image_sha256)
        layers.append(
            admit_native_plan(
                plan,
                retained,
                layer,
                reviewed_at=datetime.now(UTC),
                image_sha256=runtime.image_sha256,
            )
        )
        plans[layer] = {"plan": plan, "retained": retained}
    now = datetime.now(UTC)
    readiness = ReadinessReceipt(
        protocol="baseline-readiness-v1",
        observed_at=now,
        context_sha256=value.bindings.context_sha256,
        capture_environment_sha256=document_digest({key: env[key] for key in CAPTURE_ENVIRONMENT}),
        evaluator_source_sha256=value.provenance.evaluator_source_sha256,
        capture_source_sha256=value.provenance.capture_source_sha256,
        production_inputs_sha256=value.provenance.production_inputs_sha256,
        infrastructure_source_sha256=infrastructure_digest(),
        runtime_receipt_sha256=runtime.receipt_sha256,
        image_sha256=runtime.image_sha256,
        configuration_sha256=runtime.configuration_sha256,
        scoped_before_sha256="a" * 64,
        layers=(layers[0], layers[1], layers[2]),
    )
    readiness_bytes = readiness.model_dump_json().encode()
    approved = approval(value, now).model_copy(
        update={
            "approved_at": now,
            "readiness_receipt_sha256": hashlib.sha256(readiness_bytes).hexdigest(),
        }
    )
    paths = {
        name: tmp_path / (name + ".json")
        for name in (
            "approval",
            "frozen",
            "readiness",
            "plans",
        )
    }
    paths["approval"].write_text(approved.model_dump_json())
    paths["frozen"].write_text(value.model_dump_json(by_alias=True))
    paths["readiness"].write_bytes(readiness_bytes)
    paths["plans"].write_text(json.dumps(plans))
    clock = Clock()
    clock.now = time.monotonic()
    initial = clock.now

    def fast_budget(
        approved: BaselineApproval,
        frozen: FrozenBaseline,
        *,
        persist: Callable[[BaselineBudgetReceipt], Awaitable[None]],
        ready: Callable[[], Awaitable[None]],
    ) -> BaselineBudget:
        return BaselineBudget(
            approved,
            frozen,
            persist=persist,
            ready=ready,
            clock=clock,
            sleep=clock.sleep,
            now=lambda: now + timedelta(seconds=clock.now - initial),
        )

    monkeypatch.setattr(baseline_runner, "BaselineBudget", fast_budget)
    (tmp_path / ".azure").mkdir(mode=0o700)
    monkeypatch.setattr(baseline_budget, "ROOT", tmp_path)
    monkeypatch.setattr(
        baseline_runner, "AzureCliCredential", lambda *, process_timeout: Credential()
    )
    monkeypatch.setattr(baseline_runner, "verify_schedule_window", lambda: None)
    monkeypatch.setattr(baseline_runner, "schedule_window_delay", lambda: 0.0)

    async def read_context() -> context.Context:
        return target_context

    async def ensure_ready(self: context.Context) -> None:
        return None

    monkeypatch.setattr(baseline_runner, "read_context", read_context)
    monkeypatch.setattr(type(target_context), "ensure_ready", ensure_ready)
    if environment_drift:
        env["AGENT_RESOURCE_URL"] = "https://foreign.test/a2a"

    def local_command(arguments: list[str]) -> bytes:
        assert arguments == [
            "azd",
            "env",
            "get-values",
            "--environment",
            "dev",
            "--output",
            "json",
        ]
        return json.dumps(env).encode()

    monkeypatch.setattr(context, "_read_command", local_command)
    enter = PrivateCaptureProcess.__aenter__

    async def controlled_enter(self: PrivateCaptureProcess) -> PrivateCaptureProcess:
        self.command = (str(ROOT / ".venv/bin/python"), "-c", ROOT_WORKER)
        return await enter(self)

    monkeypatch.setattr(PrivateCaptureProcess, "__aenter__", controlled_enter)
    service = Service()
    judge_calls = 0

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal judge_calls
        if request.url.path.endswith("/chat/completions"):
            index = judge_calls // 4
            judge_calls += 1
            return scripted_chat(request, unsupported=index in range(4, 8), snapshot=MODEL_SNAPSHOT)
        return service.respond(request)

    monkeypatch.setattr(
        httpx2, "AsyncHTTPTransport", lambda **kwargs: httpx2.MockTransport(respond)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_evaluation",
            "baseline-run",
            "--manifest",
            str(paths["approval"]),
            "--frozen",
            str(paths["frozen"]),
            "--readiness",
            str(paths["readiness"]),
            "--plans",
            str(paths["plans"]),
            "--approved-sha256",
            hashlib.sha256(paths["approval"].read_bytes()).hexdigest(),
            "--output",
            str(tmp_path / "run"),
        ],
    )
    status = __main__.main()
    output = capsys.readouterr()
    result = json.loads(output.out)
    if environment_drift:
        assert status == 1
        assert result["category"] == "baseline_capture_environment_drift"
        assert judge_calls == 0 and not service.requests
        return
    assert status == 0
    assert result == {
        "outcome": "published",
        "protocol": "baseline-v1",
        "cases": 12,
        "scores": 28,
        "reports": 3,
        "semantic_gate_passed": True,
        "deterministic_gates_passed": True,
        "ui_verified": False,
    }
    assert judge_calls == 64
    assert "CANARY" not in output.out + output.err
    # The canonical approval cannot start another worker or repeat scoring.
    before = len(service.requests)
    assert __main__.main() == 1
    assert len(service.requests) == before and judge_calls == 64
    assert context.COMMAND_ADMISSION.get() is None
    assert context.COMMAND_DEADLINE.get() is None


def test_unapproved_command_never_calls_an_external_interface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "approval.json"
    path.write_text('{"execution_approved":false}')

    def forbidden(arguments: list[str]) -> bytes:
        raise EvaluationFailure("unexpected_control_command")

    monkeypatch.setattr(context, "_read_command", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_evaluation",
            "baseline-run",
            "--manifest",
            str(path),
            "--frozen",
            str(path),
            "--readiness",
            str(path),
            "--plans",
            str(path),
            "--approved-sha256",
            "0" * 64,
            "--output",
            str(tmp_path / "run"),
        ],
    )
    assert __main__.main() == 1
    assert "baseline_approval_fingerprint_mismatch" in capsys.readouterr().out
    assert not (tmp_path / "run").exists()
