from datetime import UTC, datetime, timedelta

import pytest
from test_baseline_budget import Recorder, approval, frozen, ready
from test_budget import Clock

from agent_evaluation import baseline_runner, context
from agent_evaluation.baseline_budget import BaselineBudget
from agent_evaluation.policy import EvaluationFailure


@pytest.mark.parametrize(
    "second,expected",
    [
        (0, 70),
        (69, 1),
        (70, 0),
        (900, 0),
        (1730, 0),
        (1731, 139),
        (1799, 71),
    ],
)
def test_boundary_wait_respects_retained_schedule_without_extending_window(
    monkeypatch: pytest.MonkeyPatch,
    second: int,
    expected: int,
) -> None:
    class Clock:
        @staticmethod
        def now(zone: object) -> datetime:
            return datetime.fromtimestamp(1800 * 100000 + second, UTC)

    monkeypatch.setattr(context, "datetime", Clock)
    assert context.schedule_window_delay() == expected
    if expected:
        with pytest.raises(EvaluationFailure, match="shared_deployment_schedule_window"):
            context.verify_schedule_window()
    else:
        context.verify_schedule_window()


async def test_schedule_wait_preserves_original_deadline_and_admits_no_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    now = datetime.now(UTC)
    value = frozen()
    approved = approval(value, now)
    budget = BaselineBudget(
        approved,
        value,
        persist=Recorder(),
        ready=ready,
        clock=clock,
        sleep=clock.sleep,
        now=lambda: now + timedelta(seconds=clock.now),
    )
    await budget.start()
    deadline = budget.deadline
    delays = iter((70.0, 0.0))
    monkeypatch.setattr(baseline_runner, "schedule_window_delay", lambda: next(delays))
    await baseline_runner.wait_for_schedule(budget)
    assert clock.waits == [70.0] and not budget.judge.attempts
    assert budget.deadline == deadline
    assert budget.receipt().original_expires_at == approved.expires_at
    budget.deadline = clock.now + 10
    monkeypatch.setattr(baseline_runner, "schedule_window_delay", lambda: 70.0)
    with pytest.raises(EvaluationFailure, match="baseline_execution_deadline"):
        await baseline_runner.wait_for_schedule(budget)
    assert clock.waits == [70.0] and not budget.judge.attempts


@pytest.mark.parametrize(
    "failure",
    [None, "shared_deployment_busy", "shared_deployment_schedule_window", "judge_deployment_drift"],
)
async def test_known_busy_workload_waits_without_dispatch_or_deadline_extension(
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    clock = Clock()
    now = datetime.now(UTC)
    value = frozen()
    budget = BaselineBudget(
        approval(value, now),
        value,
        persist=Recorder(),
        ready=ready,
        clock=clock,
        sleep=clock.sleep,
        now=lambda: now + timedelta(seconds=clock.now),
    )
    await budget.start()
    deadline = budget.deadline
    monkeypatch.setattr(baseline_runner, "schedule_window_delay", lambda: 0.0)

    class Readiness:
        def __init__(self) -> None:
            self.calls = 0

        async def ensure_ready(self) -> None:
            self.calls += 1
            if self.calls == 1 and failure is not None:
                raise EvaluationFailure(failure)

    from agent_evaluation.context import Context

    class LocalContext(Context):
        async def ensure_ready(self) -> None:
            await readiness.ensure_ready()

    readiness = Readiness()
    if failure == "judge_deployment_drift":
        with pytest.raises(EvaluationFailure, match="judge_deployment_drift"):
            await baseline_runner.wait_for_model_readiness(budget, LocalContext({}, "authored"))
        assert not clock.waits
    else:
        await baseline_runner.wait_for_model_readiness(budget, LocalContext({}, "authored"))
        assert clock.waits == ([30] if failure == "shared_deployment_busy" else [])
    assert budget.deadline == deadline and not budget.judge.attempts
