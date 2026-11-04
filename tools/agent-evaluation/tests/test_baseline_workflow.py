import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx2
import pytest
from azure.ai.projects.aio import AIProjectClient
from chat_fakes import scripted_chat
from fakes import PROJECT_ENDPOINT, Credential
from openai import AsyncOpenAI
from pydantic import JsonValue
from test_baseline_budget import approval, ready
from test_baseline_inputs import frozen_data
from test_baseline_publication import Service
from test_budget import Clock
from test_publication import selected_context

from agent_evaluation.baseline_budget import BaselineBudget, BaselineRun
from agent_evaluation.baseline_capture import CaptureSession
from agent_evaluation.baseline_inputs import FrozenBaseline, parse_document
from agent_evaluation.baseline_ipc import PrivateCaptureProcess
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.baseline_publication import BaselinePublisher
from agent_evaluation.baseline_scoring import BaselineCompletion
from agent_evaluation.baseline_workflow import execute_workflow
from agent_evaluation.budget import MODEL_SNAPSHOT
from agent_evaluation.context import Context
from agent_evaluation.inputs import ROOT
from agent_evaluation.judge import JudgeTransport
from agent_evaluation.policy import EvaluationFailure

# Only authored transports are replaced; the real worker, capture adapter, pipes,
# supervisor, DeepEval/OpenAI pipeline and native publisher execute unchanged.
ROOT_WORKER = """
import time
from contextlib import asynccontextmanager
from uuid import UUID
import httpx
import scripts.agent_quality_capture as c
import scripts.agent_quality_worker as w
from newsloom_agent.auth import Caller, AgentVerifier
from newsloom_agent.client import ResearchInvocation
from newsloom_agent.research_models import (
    NewsDetail, RankedMetadata, SearchResults, ResearchReceipt,
)
def snapshot(i):
    return {
        "id": str(UUID(int=i)), "title": "Authored title " + str(i),
        "summary": "Authored bounded evidence " + str(i),
        "source": "source-one" if i < 3 else "source-two",
        "category": "governance", "tags": ["ai"],
        "published_at": "2030-01-01T00:00:00Z",
        "url": "https://example.com/authored/" + str(i),
        "author": "", "date_origin": "published", "publisher_categories": [],
    }
caller = None
async def sign(settings, public, limits):
    global caller
    limits.admit_sign_in(); limits.admit_auth()
    caller = Caller(settings.agent.tenant, UUID(int=100),
        settings.agent.public_client_id, "subject", int(time.time())+3600, "TOKEN_CANARY")
    return "TOKEN_CANARY", caller
async def authenticate(self, token, deadline):
    return caller
class Reader:
    def __init__(self, caller, limits):
        self.caller, self.limits, self.denial = caller, limits, denied
    async def item(self, item_id):
        self.limits.admit_tool()
        return NewsDetail.model_validate(snapshot(item_id.int)) if item_id.int in (1,2,3) else None
    async def call(self, name, args):
        assert name == "search_news" and args["query"] is None
        self.limits.admit_tool()
        ids = {"source-one": [1,2], "source-two": [3], "source-none": []}[args["source"]]
        return SearchResults(items=tuple(RankedMetadata.model_validate({
            k:v for k,v in snapshot(i).items()
            if k not in ("author", "date_origin", "publisher_categories")
        }) for i in ids))
@asynccontextmanager
async def evidence(settings, user, limits, *, readiness):
    assert not readiness
    limits.admit_sign_in(); limits.admit_auth()
    yield Reader(user, limits)
async def denied(*args, **kwargs):
    return 401
async def invoke(settings, token, public, request, *, request_hook, response_hook):
    await request_hook(httpx.Request("POST", settings.resource_url,
        json={"method": "SendStreamingMessage"}))
    ids = list(request.item_ids or ())
    if not ids:
        pools = {"source-one":[1,2],"source-two":[3],"source-none":[]}
        ids = [UUID(int=i) for i in pools[request.filters.source]]
    present = [i for i in ids if i.int in (1,2,3)]
    missing = [i for i in ids if i not in present]
    question = request.question
    limited = (bool(missing) or "full-article or external" in question
        or "database update" in question)
    outcome = "no_match" if not present else "limited" if limited else "supported"
    parts = ["Authored bounded evidence. ["+str(n)+"]" for n,_ in enumerate(present, 1)]
    if "two supported observations" in question:
        parts.append("Another authored observation. [1]")
    if outcome != "supported":
        parts.append("Limitation: Only the authored stored evidence is available.")
    if request.item_ids:
        coverage = "partial" if missing else "complete"
        parts.append("Selection retrieval coverage: " + coverage + ".")
        if missing:
            parts.append("Missing selected items: " + ", ".join(map(str,missing)) + ".")
    footer = ("Evidence is limited to stored summaries and metadata; "
        "full articles and web search were not accessed.")
    text = "\\n\\n".join(parts) + "\\n\\n" + footer
    if present:
        refs = ["["+str(n)+"] "+snapshot(i.int)["url"] for n,i in enumerate(present,1)]
        text += "\\n\\n" + "\\n\\n".join(refs)
    receipt = ResearchReceipt(
        outcome=outcome, items=len(present), user_preserved=True, validated=True,
        tool_calls=max(1,len(ids)), generation_calls=1 if present else 0,
        usage_observed_calls=1 if present else 0,
        input_tokens=10 if present else 0, output_tokens=5 if present else 0)
    await request_hook(httpx.Request("POST", settings.resource_url, json={"method":"GetTask"}))
    return ResearchInvocation(text, {}, receipt)
w.sign_in_agent=sign; w.evidence_session=evidence; w.capture_denial=denied
c.invoke_research=invoke; AgentVerifier.authenticate=authenticate
raise SystemExit(w.main())
"""


def snapshot(index: int) -> dict[str, JsonValue]:
    return {
        "id": str(UUID(int=index)),
        "title": "Authored title " + str(index),
        "summary": "Authored bounded evidence " + str(index),
        "source": "source-one" if index < 3 else "source-two",
        "category": "governance",
        "tags": ["ai"],
        "published_at": "2030-01-01T00:00:00Z",
        "url": "https://example.com/authored/" + str(index),
        "author": "",
        "date_origin": "published",
        "publisher_categories": [],
    }


def workflow_context() -> Context:
    context = selected_context()
    context.environment["AGENT_TENANT_ID"] = str(UUID(int=90))
    data = frozen_data()
    provenance = data["provenance"]
    assert isinstance(provenance, dict) and isinstance(provenance["accepted_runtime"], dict)
    runtime = provenance["accepted_runtime"]
    context.environment["AGENT_IMAGE"] = "registry.test/agent@sha256:" + str(
        runtime["image_sha256"]
    )
    context.environment["AGENT_IMAGE_REVISION"] = str(runtime["source_sha256"])
    return context


def bound_fixture() -> FrozenBaseline:
    data = frozen_data()
    bindings = data["bindings"]
    oracles = data["oracles"]
    provenance = data["provenance"]
    assert isinstance(bindings, dict) and isinstance(oracles, dict) and isinstance(provenance, dict)
    items, filters = bindings["items"], bindings["filters"]
    assert isinstance(items, list) and isinstance(filters, list)
    for row in items:
        if row["present"]:
            row["fingerprint"] = document_digest(snapshot(UUID(row["item_id"]).int))
    by_alias = {row["alias"]: row for row in items}
    for index, row in enumerate(filters):
        row["source"] = ("source-one", "source-two", "source-none")[index]
        row["pool_sha256"] = document_digest(
            [
                {
                    key: value
                    for key, value in snapshot(UUID(by_alias[alias]["item_id"]).int).items()
                    if key not in ("author", "date_origin", "publisher_categories")
                }
                for alias in row["pool_aliases"]
            ]
        )
    context = workflow_context()
    bindings["context_sha256"] = context.digest()
    bindings["actor_sha256"] = document_digest(
        {
            "oid": str(UUID(int=100)),
            "tenant": context.environment["AGENT_TENANT_ID"],
        }
    )
    binding_hash = document_digest(bindings)
    oracles["bindings_sha256"] = binding_hash
    provenance["bindings_sha256"] = binding_hash
    provenance["oracle_sha256"] = document_digest(oracles)
    return parse_document(FrozenBaseline, json.dumps(data).encode())


@pytest.mark.parametrize("failure", [None, "low_quality", "calibration", "publication"])
async def test_real_private_worker_composes_full_frozen_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    frozen = bound_fixture()
    context = workflow_context()
    start = datetime.now(UTC)
    approved = approval(frozen, start)
    encoded = approved.model_dump_json().encode()
    run = BaselineRun(
        tmp_path / "run",
        encoded,
        hashlib.sha256(encoded).hexdigest(),
        frozen,
        registry=tmp_path / "registry",
    )
    clock = Clock()
    clock.now = time.monotonic()
    initial = clock.now
    budget = BaselineBudget(
        approved,
        frozen,
        persist=run.checkpoint,
        ready=ready,
        clock=clock,
        sleep=clock.sleep,
        now=lambda: start + timedelta(seconds=clock.now - initial),
    )
    await budget.start()
    calls: list[httpx2.Request] = []
    workers: list[PrivateCaptureProcess] = []
    enter = PrivateCaptureProcess.__aenter__

    async def controlled_enter(self: PrivateCaptureProcess) -> PrivateCaptureProcess:
        assert len(calls) == 32
        workers.append(self)
        self.command = (str(ROOT / ".venv/bin/python"), "-c", ROOT_WORKER)
        return await enter(self)

    monkeypatch.setattr(PrivateCaptureProcess, "__aenter__", controlled_enter)

    def respond(request: httpx2.Request) -> httpx2.Response:
        control = len(calls) // 4
        calls.append(request)
        return scripted_chat(
            request,
            unsupported=(
                control in range(4, 8)
                or failure == "calibration"
                or (failure == "low_quality" and control >= 8)
            ),
            snapshot=MODEL_SNAPSHOT,
        )

    service = Service()
    if failure == "publication":
        service.change = "precision"
    env = {
        **context.environment,
        "MCP_TENANT_ID": context.environment["AGENT_TENANT_ID"],
        "MCP_API_CLIENT_ID": str(UUID(int=101)),
        "AGENT_API_CLIENT_ID": str(UUID(int=102)),
        "MCP_PUBLIC_CLIENT_ID": str(UUID(int=103)),
        "AGENT_PUBLIC_CLIENT_ID": str(UUID(int=104)),
        "MCP_RESOURCE_URL": "https://mcp.test/mcp",
        "AGENT_RESOURCE_URL": "https://agent.test/a2a",
    }
    async with (
        AsyncOpenAI(
            base_url="https://evaluation-test.openai.azure.com/openai/v1",
            api_key="synthetic",
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=JudgeTransport(
                    "https://evaluation-test.openai.azure.com",
                    "test-deployment",
                    budget.judge,
                    httpx2.MockTransport(respond),
                )
            ),
        ) as client,
        Credential() as credential,
        AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=credential,
            allow_preview=True,
            retry_total=0,
            redirect_max=0,
        ) as project,
    ):
        completion = BaselineCompletion(client, "test-deployment", budget.judge)
        operation = execute_workflow(
            budget,
            run,
            completion,
            lambda: CaptureSession(budget, run, env),
            project,
            context,
            publication_transport=httpx2.MockTransport(service.respond),
        )
        if failure in ("calibration", "publication"):
            with pytest.raises(EvaluationFailure):
                await operation
            assert budget.halted
        else:
            result = await operation
            assert result["cases"] == 12 and result["scores"] == 28 and result["reports"] == 3
            assert result["semantic_gate_passed"] == (failure is None)
            assert result["ui_verified"] is False
            assert result["deterministic_gates_passed"]
            assert budget.counts["publication_creates"] == 6
            assert len(calls) == 64
            assert len(run.load_results().scores) == 28
    if failure == "calibration":
        assert not workers and not budget.agents and not service.requests
    else:
        assert len(budget.agents) == 12 and workers[0].closed
        assert workers[0].process is not None and workers[0].process.returncode is not None
        assert budget.counts["task_reads"] == 10
    if failure == "publication":
        saved_result = run.load_results()
        recovery = BaselinePublisher(budget, run, saved_result, context)
        assert recovery.recovery
        creates = budget.counts["publication_creates"]
        service.change = None
        from test_baseline_publication import execute

        with pytest.raises(EvaluationFailure, match="publication_mutation_replay_rejected"):
            await execute(recovery, service)
        assert recovery.state.reports[0].verification == "api_verified"
        assert budget.counts["publication_creates"] == creates
    for path in (tmp_path / "run").iterdir():
        if path.is_file():
            saved = path.read_bytes()
            assert b"Authored bounded evidence" not in saved
            assert b"TOKEN_CANARY" not in saved
    with pytest.raises(EvaluationFailure, match="baseline_scoring_already_claimed"):
        from agent_evaluation.baseline_scoring import BaselineScorer

        BaselineScorer(budget, run, completion)
