import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

import httpx
import pytest
from agent_framework.observability import (
    OBSERVABILITY_SETTINGS,
    disable_instrumentation,
    enable_instrumentation,
)
from newsloom_agent import telemetry as instrumentation
from newsloom_agent.app import create_app
from newsloom_agent.generation import GenerationStats
from newsloom_agent.serving import TaskRegistry
from newsloom_agent.telemetry import PrivateSpanExporter, Telemetry
from newsloom_core.diagnostics import SafeHandler
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from test_agent_delegation import DelegationCase
from test_agent_delegation import delegated as delegated
from test_agent_generation import Model
from test_agent_generation import model as model
from test_agent_serving import invocation, loopback, until
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import endpoint as endpoint


@dataclass
class Credential:
    closed: bool = False

    def close(self) -> None:
        self.closed = True


@dataclass
class Captured:
    telemetry: Telemetry
    traces: InMemorySpanExporter
    metrics: InMemoryMetricReader
    credential: Credential
    framework_spans: list[bool]
    executions: list[tuple[str, str, bool]] = field(default_factory=list)


@pytest.fixture
async def captured(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Captured]:
    spans, metrics, credential = InMemorySpanExporter(), InMemoryMetricReader(), Credential()
    framework_spans: list[bool] = []
    constructors: list[dict[str, object]] = []

    class ObservedExporter(PrivateSpanExporter):
        def export(self, batch: Sequence[ReadableSpan]) -> SpanExportResult:
            framework_spans.extend(
                bool(
                    span.instrumentation_scope
                    and span.instrumentation_scope.name.startswith("agent_framework")
                )
                for span in batch
            )
            return super().export(batch)

    def authenticated_exporter(**kwargs: object) -> InMemorySpanExporter:
        constructors.append(kwargs)
        assert kwargs["connection_string"] == "NEWSLOOM_ROUTING_CANARY"
        assert kwargs["credential"] is credential
        assert kwargs["disable_offline_storage"] is True
        return spans

    monkeypatch.setattr(
        instrumentation, "ManagedIdentityCredential", lambda *, client_id: credential
    )
    monkeypatch.setattr(instrumentation, "AzureMonitorTraceExporter", authenticated_exporter)
    monkeypatch.setattr(instrumentation, "AzureMonitorMetricExporter", authenticated_exporter)
    monkeypatch.setattr(instrumentation, "PeriodicExportingMetricReader", lambda exporter: metrics)
    monkeypatch.setattr(instrumentation, "PrivateSpanExporter", ObservedExporter)
    monkeypatch.setattr(
        trace,
        "set_tracer_provider",
        lambda provider: monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider),
    )
    monkeypatch.setattr(logging.getLogger(), "handlers", [SafeHandler()])
    telemetry = Telemetry("NEWSLOOM_ROUTING_CANARY", "private-identity")
    # MCP caches its first real tracer; keep this temporary provider request-local to the test.
    monkeypatch.setattr("mcp.shared._otel._tracer", telemetry.traces.get_tracer("mcp-python-sdk"))
    assert len(constructors) == 2
    value = Captured(telemetry, spans, metrics, credential, framework_spans)
    execution = telemetry.execution

    def observed(outcome: str, category: str, elapsed: float, stats: GenerationStats) -> None:
        value.executions.append((outcome, category, stats.usage_observed))
        execution(outcome, category, elapsed, stats)

    monkeypatch.setattr(telemetry, "execution", observed)
    try:
        yield value
    finally:
        disable_instrumentation()
        await asyncio.to_thread(telemetry.close)
        assert credential.closed


@pytest.mark.parametrize("force_sensitive", [False, True])
async def test_real_http_automatic_sdk_spans_success_errors_and_cancellation_are_private(
    delegated: DelegationCase,
    model: Model,
    captured: Captured,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_sensitive: bool,
) -> None:
    monkeypatch.setenv("ENABLE_SENSITIVE_DATA", "true")
    authorization, registry = await delegated.authorization(), TaskRegistry()
    async with (
        loopback(
            lambda base: create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=f"{base}/a2a",
                registry=registry,
                generator=model.generator(),
                observer=captured.telemetry,
            )
        ) as base,
        httpx.AsyncClient(
            base_url=base,
            trust_env=False,
            timeout=5,
            headers={
                "Authorization": "Bearer " + authorization.caller.assertion,
                "A2A-Version": "1.0",
            },
        ) as http,
    ):
        assert not OBSERVABILITY_SETTINGS.ENABLED
        enable_instrumentation(enable_sensitive_data=True)
        assert not OBSERVABILITY_SETTINGS.ENABLED
        if force_sensitive:
            enable_instrumentation(
                force=True, enable_sensitive_data=True, enable_message_events=True
            )

        async def invoke() -> httpx.Response:
            return await http.post(
                "/a2a",
                json={
                    "jsonrpc": "2.0",
                    "id": "NEWSLOOM_REQUEST_CANARY",
                    "method": "SendMessage",
                    "params": invocation(),
                },
            )

        assert (await invoke()).json()["result"]["task"]["status"][
            "state"
        ] == "TASK_STATE_COMPLETED"
        model.status = 429
        assert (await invoke()).json()["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
        model.status = 200
        delegated.exchange_status = 400
        delegated.exchange_payload = {
            "error": "invalid_grant",
            "error_description": "NEWSLOOM_IDENTITY_ERROR_CANARY",
        }
        assert (await invoke()).json()["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
        delegated.exchange_status, delegated.exchange_payload = 200, None
        delegated.mcp_status = 403
        assert (await invoke()).json()["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
        delegated.mcp_status = None
        model.release.clear()
        model.entered.clear()
        sending = asyncio.create_task(invoke())
        try:
            await asyncio.wait_for(model.entered.wait(), 3)
            await asyncio.wait_for(model.streams[-1].paused.wait(), 3)
            sending.cancel()
            await asyncio.gather(sending, return_exceptions=True)
            await until(
                lambda: all(record.producer is None for record in registry.records.values())
            )
        finally:
            model.release.set()
            sending.cancel()
            await asyncio.gather(sending, return_exceptions=True)
        assert (
            await http.post("/a2a", headers={"Authorization": "invalid"}, json={})
        ).status_code == 401
        expired = await delegated.authorization(downstream={"exp": 1})
        http.headers["Authorization"] = "Bearer " + expired.caller.assertion
        assert (await invoke()).json()["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
        assert all(stream.closed for stream in model.streams)

    parent = trace.SpanContext(
        trace_id=1,
        span_id=2,
        is_remote=True,
        trace_flags=trace.TraceFlags(1),
        trace_state=trace.TraceState([("unsafe", "NEWSLOOM_TRACE_CANARY")]),
    )
    with captured.telemetry.traces.get_tracer("NEWSLOOM_SCOPE_CANARY").start_as_current_span(
        "NEWSLOOM_SPAN_CANARY",
        context=trace.set_span_in_context(trace.NonRecordingSpan(parent)),
        attributes={
            "url.full": "NEWSLOOM_URL_CANARY",
            "prompt": "NEWSLOOM_PROMPT_CANARY",
            "outcome": "NEWSLOOM_OUTCOME_CANARY",
            "output_tokens": 513,
        },
    ) as span:
        span.add_event("NEWSLOOM_EVENT_CANARY")
        span.set_status(trace.Status(trace.StatusCode.ERROR, "NEWSLOOM_ERROR_CANARY"))
        span.record_exception(ValueError("NEWSLOOM_EXCEPTION_CANARY"))
    assert captured.telemetry.traces.force_flush()
    spans = captured.traces.get_finished_spans()
    assert spans
    if force_sensitive:
        assert any(captured.framework_spans)
    for exported in spans:
        assert exported.name == "newsloom.agent.request"
        assert not exported.events and not exported.links
        assert exported.instrumentation_scope is None
        assert exported.context is None or not exported.context.trace_state
        assert exported.parent is None or not exported.parent.trace_state
        assert exported.status.description is None
        values = json.dumps(
            {
                "attributes": dict(exported.attributes or {}),
                "resource": dict(exported.resource.attributes),
            }
        )
        assert "CANARY" not in values
        assert authorization.caller.assertion not in values
    assert any(outcome == "success" and observed for outcome, _, observed in captured.executions)
    assert any(outcome == "cancelled" for outcome, _, _ in captured.executions)
    assert any(category == "model_throttled" for _, category, _ in captured.executions)
    data = captured.metrics.get_metrics_data()
    assert data is not None
    assert "CANARY" not in str(data)
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err
    assert authorization.caller.assertion not in output.out + output.err


async def test_overload_and_disconnect_metrics_have_no_request_content(
    delegated: DelegationCase,
    model: Model,
    captured: Captured,
) -> None:
    model.release.clear()
    authorization, registry = await delegated.authorization(), TaskRegistry()
    async with (
        loopback(
            lambda base: create_app(
                delegated.adapter,
                delegated.agent_verifier,
                public_url=f"{base}/a2a",
                registry=registry,
                generator=model.generator(),
                observer=captured.telemetry,
            )
        ) as base,
        httpx.AsyncClient(
            base_url=base,
            trust_env=False,
            timeout=5,
            headers={
                "Authorization": "Bearer " + authorization.caller.assertion,
                "A2A-Version": "1.0",
            },
        ) as http,
    ):

        async def invoke() -> httpx.Response:
            return await http.post(
                "/a2a",
                json={
                    "jsonrpc": "2.0",
                    "id": "NEWSLOOM_OVERLOAD_CANARY",
                    "method": "SendMessage",
                    "params": invocation(),
                },
            )

        requests = [asyncio.create_task(invoke()) for _ in range(4)]
        try:
            await until(lambda: len(model.streams) == 4)
            for stream in model.streams:
                await asyncio.wait_for(stream.paused.wait(), 3)
            assert (await invoke()).status_code == 429
        finally:
            for request in requests:
                request.cancel()
            await asyncio.gather(*requests, return_exceptions=True)
            await until(
                lambda: all(record.producer is None for record in registry.records.values())
            )
            model.release.set()
        assert all(stream.closed for stream in model.streams)
    data = captured.metrics.get_metrics_data()
    assert data is not None
    outcomes = {
        point.attributes["outcome"]
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == "newsloom.agent.http_calls"
        for point in metric.data.data_points
        if point.attributes is not None
    }
    assert outcomes == {"overloaded", "cancelled"}
    assert "CANARY" not in str(data)
