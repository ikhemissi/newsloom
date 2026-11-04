import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx2
import pytest
from chat_fakes import scripted_chat
from openai import APIError, AsyncOpenAI
from pydantic import JsonValue
from test_baseline_budget import approval, case_receipt, ready
from test_baseline_inputs import frozen_data
from test_budget import Clock

from agent_evaluation.baseline_budget import BaselineBudget, BaselineRun
from agent_evaluation.baseline_checks import check_answer
from agent_evaluation.baseline_inputs import FrozenBaseline, parse_document
from agent_evaluation.baseline_provenance import document_digest
from agent_evaluation.baseline_scoring import (
    BaselineCompletion,
    BaselineScorer,
    EvidenceSnapshot,
    TransientAnswer,
)
from agent_evaluation.budget import MODEL_SNAPSHOT
from agent_evaluation.judge import JudgeTransport
from agent_evaluation.policy import EvaluationFailure

ENDPOINT = "https://evaluation-test.openai.azure.com"
SNAPSHOT: dict[str, JsonValue] = {
    "id": str(UUID(int=1)),
    "title": "Authored Cedar title",
    "summary": "Authored Cedar summary.",
    "source": "synthetic",
    "category": "governance",
    "tags": ["ai"],
    "published_at": "2030-01-01T00:00:00Z",
    "url": "https://example.com/controlled",
    "author": "",
    "date_origin": "published",
    "publisher_categories": [],
}


def frozen_with_snapshot() -> FrozenBaseline:
    data = frozen_data()
    bindings = data["bindings"]
    oracles = data["oracles"]
    provenance = data["provenance"]
    assert isinstance(bindings, dict) and isinstance(bindings["items"], list)
    assert isinstance(oracles, dict) and isinstance(provenance, dict)
    bindings["items"][0]["fingerprint"] = document_digest(SNAPSHOT)
    binding_hash = document_digest(bindings)
    oracles["bindings_sha256"] = binding_hash
    provenance["bindings_sha256"] = binding_hash
    provenance["oracle_sha256"] = document_digest(oracles)
    return parse_document(FrozenBaseline, json.dumps(data).encode())


@pytest.mark.parametrize(
    "failure", [None, "reason", "calibration", "usage", "schema", "provider", "cancel"]
)
async def test_real_metric_calibration_gate_and_metadata_only_progress(
    tmp_path: Path, failure: str | None
) -> None:
    frozen = frozen_with_snapshot()
    clock = Clock()
    start = datetime.now(UTC)
    approved = approval(frozen, start)
    raw = approved.model_dump_json().encode()
    run = BaselineRun(
        tmp_path / "run",
        raw,
        hashlib.sha256(raw).hexdigest(),
        frozen,
        registry=tmp_path / "registry",
    )
    budget = BaselineBudget(
        approved,
        frozen,
        persist=run.checkpoint,
        ready=ready,
        clock=clock,
        sleep=clock.sleep,
        now=lambda: start + timedelta(seconds=clock.now),
    )
    await budget.start()
    calls: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        index = len(calls) // 4
        calls.append(request)
        if failure == "cancel":
            raise asyncio.CancelledError("PRIVATE_PROVIDER_ERROR_CANARY")
        if failure == "provider":
            return httpx2.Response(
                500, json={"error": {"message": "PRIVATE_PROVIDER_ERROR_CANARY"}}
            )
        unsupported = index >= 4
        if failure == "calibration" and index == 0:
            unsupported = True
        response = scripted_chat(request, unsupported=unsupported, snapshot=MODEL_SNAPSHOT)
        body = response.json()
        if failure == "usage":
            body.pop("usage")
        if failure == "schema":
            body["choices"][0]["message"]["content"] = '{"foreign":true}'
        if failure == "reason":
            content = json.loads(body["choices"][0]["message"]["content"])
            if "reason" in content:
                content["reason"] = "JUDGE_REASON_PRIVATE_CANARY"
            body["choices"][0]["message"]["content"] = json.dumps(content)
        return httpx2.Response(200, json=body)

    async with AsyncOpenAI(
        base_url=ENDPOINT + "/openai/v1",
        api_key="synthetic",
        max_retries=0,
        http_client=httpx2.AsyncClient(
            transport=JudgeTransport(
                ENDPOINT, "test-deployment", budget.judge, httpx2.MockTransport(respond)
            ),
            follow_redirects=False,
        ),
    ) as client:
        scorer = BaselineScorer(
            budget, run, BaselineCompletion(client, "test-deployment", budget.judge)
        )
        if failure in (None, "reason"):
            result = await scorer.calibrate()
            assert result.state == "calibrated" and len(result.controls) == 8
            assert all(value.passed for value in result.controls)
            assert len(calls) == 32
            assert budget.judge.receipt().usage_complete
            with pytest.raises(EvaluationFailure, match="baseline_calibration_already_attempted"):
                await scorer.calibrate()
            await budget.admit_agent("b01")
            answer = "LIVE_ANSWER_PRIVATE_CANARY"
            receipt = case_receipt(frozen).model_copy(
                update={
                    "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                }
            )
            await budget.observe_agent(receipt)
            captured = TransientAnswer(
                case_id="b01",
                answer=answer,
                evidence=(EvidenceSnapshot(alias="n1", item=SNAPSHOT),),
                receipt=receipt,
            )
            measured = await scorer.score(captured)
            assert measured.score == 0.0
            assert not budget.halted and not scorer.semantic_gate_passed()
            assert len(calls) == 36
            checks = check_answer(frozen, receipt, answer, captured.evidence)
            await scorer.record_contracts("b01", checks.metric_scores())
            assert len(scorer.progress.scores) == 3
            with pytest.raises(EvaluationFailure, match="baseline_contract_score_mismatch"):
                await scorer.record_contracts("b01", checks.metric_scores())
            with pytest.raises(EvaluationFailure, match="baseline_scoring_incomplete"):
                await scorer.finish()
            with pytest.raises(EvaluationFailure, match="baseline_case_scoring_not_admitted"):
                await scorer.score(captured)
        else:
            with pytest.raises((EvaluationFailure, ValueError, APIError, asyncio.CancelledError)):
                await scorer.calibrate()
            assert budget.halted and scorer.progress.state == "failed"
            assert len(calls) == (4 if failure == "calibration" else 1)
            assert not budget.agents
            with pytest.raises(EvaluationFailure, match="baseline_admission_halted"):
                await budget.admit_agent("b01")
            with pytest.raises(EvaluationFailure, match="baseline_calibration_already_attempted"):
                await scorer.calibrate()
        with pytest.raises(EvaluationFailure, match="baseline_scoring_already_claimed"):
            BaselineScorer(budget, run, BaselineCompletion(client, "test-deployment", budget.judge))
    progress = json.loads((tmp_path / "run/partial-results.json").read_text())
    encoded = json.dumps(progress)
    assert "LIVE_ANSWER_PRIVATE_CANARY" not in encoded
    assert "Authored Cedar" not in encoded
    assert "JUDGE_REASON_PRIVATE_CANARY" not in encoded
    assert "PRIVATE_PROVIDER_ERROR_CANARY" not in encoded
    for field in ("answer", "evidence", "reason", "question", "prompt"):
        assert f'"{field}":' not in encoded
    assert len(clock.waits) <= max(0, len(calls) - 1)
