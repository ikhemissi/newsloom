import json

from newsloom_agent.research_generation import ResearchStats
from opentelemetry.sdk.metrics.export import Sum
from test_agent_privacy import Captured
from test_agent_privacy import captured as captured


async def test_aggregate_observed_usage_survives_an_unobserved_cancelled_turn(
    captured: Captured,
) -> None:
    stats = ResearchStats(tool_calls=8)
    for _ in range(3):
        limit = stats.admit(final=False)
        stats.usage(60, 10, limit)
    stats.admit(final=True)
    captured.telemetry.execution("cancelled", "", 0.1, stats)
    assert captured.telemetry.traces.force_flush()
    span = captured.traces.get_finished_spans()[-1]
    attributes = dict(span.attributes or {})
    assert attributes["operation"] == "research"
    assert attributes["generation_calls"] == 4
    assert attributes["usage_observed_calls"] == 3 and attributes["usage_complete"] is False
    assert attributes["input_tokens"] == 180 and attributes["output_tokens"] == 30
    assert attributes["tool_calls"] == 8
    data = captured.metrics.get_metrics_data()
    assert data is not None
    sums = {
        metric.name: metric.data
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if isinstance(metric.data, Sum)
    }
    for name, total in (
        ("generation_calls", 4),
        ("usage_observed", 3),
        ("input_tokens", 180),
        ("output_tokens", 30),
    ):
        points = sums["newsloom.agent." + name].data_points
        assert sum(point.value for point in points) == total
        assert all(
            point.attributes is not None and point.attributes["operation"] == "research"
            for point in points
        )


async def test_exporter_keeps_separate_recent_and_research_numeric_limits(
    captured: Captured,
) -> None:
    tracer = captured.telemetry.traces.get_tracer("RESEARCH_SCOPE_CANARY")
    for operation in ("recent-news", "research"):
        with tracer.start_as_current_span(
            "RESEARCH_SPAN_CANARY",
            attributes={
                "operation": operation,
                "generation_calls": 4,
                "input_tokens": 262144,
                "output_tokens": 4096,
                "tool_calls": 8,
                "usage_observed_calls": 4,
                "usage_complete": True,
                "question": "RESEARCH_QUESTION_CANARY",
                "preference": "RESEARCH_PREFERENCE_CANARY",
                "plan": "RESEARCH_PLAN_CANARY",
            },
        ):
            pass
    with tracer.start_as_current_span(
        "RESEARCH_BAD_SPAN_CANARY",
        attributes={
            "operation": "research",
            "generation_calls": 5,
            "input_tokens": 262145,
            "output_tokens": 4097,
            "tool_calls": 9,
            "usage_observed_calls": 5,
            "usage_complete": "RESEARCH_USAGE_CANARY",
        },
    ):
        pass
    assert captured.telemetry.traces.force_flush()
    legacy, research, rejected = captured.traces.get_finished_spans()
    assert dict(legacy.attributes or {}) == {"operation": "recent-news"}
    assert (research.attributes or {})["input_tokens"] == 262144
    assert (research.attributes or {})["usage_complete"] is True
    assert dict(rejected.attributes or {}) == {"operation": "research"}
    assert "CANARY" not in json.dumps(
        [dict(span.attributes or {}) for span in (legacy, research, rejected)]
    )
