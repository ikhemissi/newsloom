from collections.abc import Callable
from typing import Protocol

import httpx2
from azure.ai.projects.aio import AIProjectClient

from agent_evaluation.baseline_budget import BaselineBudget, BaselineRun
from agent_evaluation.baseline_checks import check_answer
from agent_evaluation.baseline_inputs import CASE_IDS, SEMANTIC_CASES, CaseId, CaseReceipt
from agent_evaluation.baseline_publication import BaselinePublisher
from agent_evaluation.baseline_scoring import BaselineCompletion, BaselineScorer, TransientAnswer
from agent_evaluation.context import Context


class Capture(Protocol):
    async def open(self) -> None: ...
    async def capture(self, case_id: CaseId) -> tuple[CaseReceipt, TransientAnswer | None]: ...
    async def close(self, *, graceful: bool) -> None: ...


async def execute_workflow(
    budget: BaselineBudget,
    run: BaselineRun,
    completion: BaselineCompletion,
    capture_factory: Callable[[], Capture],
    project: AIProjectClient,
    context: Context,
    *,
    publication_transport: httpx2.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    scorer = BaselineScorer(budget, run, completion)
    completed = False
    try:
        await scorer.calibrate()
        capture = capture_factory()
        answers: list[tuple[CaseReceipt, TransientAnswer | None]] = []
        captured_all = False
        try:
            await capture.open()
            for case_id in CASE_IDS:
                # The same bounded readiness guard protects agent and judge dispatch.
                if budget.judge.ready is not None:
                    await budget.judge.ready()
                answers.append(await capture.capture(case_id))
            captured_all = True
        finally:
            await capture.close(graceful=captured_all)
        for receipt, answer in answers:
            if receipt.case_id in SEMANTIC_CASES:
                if answer is None:
                    from agent_evaluation.policy import EvaluationFailure

                    raise EvaluationFailure("baseline_scoring_answer_missing")
                await scorer.score(answer)
            checked = check_answer(
                budget.frozen,
                receipt,
                None if answer is None else answer.answer,
                () if answer is None else answer.evidence,
            )
            await scorer.record_contracts(receipt.case_id, checked.metric_scores())
        result = await scorer.finish()
        answers.clear()
        publisher = BaselinePublisher(budget, run, result, context)
        await publisher.execute(project, inner=publication_transport)
        completed = True
        return {
            "outcome": "published",
            "protocol": "baseline-v1",
            "cases": len(result.cases),
            "scores": len(result.scores),
            "reports": len(publisher.state.reports),
            "semantic_gate_passed": scorer.semantic_gate_passed(),
            "deterministic_gates_passed": all(
                row.score == 1.0 for row in result.scores if row.metric_id != "faithfulness"
            ),
            "ui_verified": False,
        }
    finally:
        if not completed:
            await budget.halt()
        else:
            await budget.checkpoint()
