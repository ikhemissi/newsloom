"""Allowlisted service telemetry; SDK exceptions and user-controlled attributes never export."""

from collections.abc import Sequence

from azure.identity import ManagedIdentityCredential
from azure.monitor.opentelemetry.exporter import (
    AzureMonitorMetricExporter,
    AzureMonitorTraceExporter,
)
from newsloom_core.model_transport import ModelClient
from opentelemetry import trace
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import SpanContext, Status, TraceState

from newsloom_mcp.models import McpFailure

TOOLS = {"get_recent_news", "get_news_item", "list_sources", "search_news"}
METHODS = {"initialize", "tools/list", "tools/call", "ping", "notifications/initialized"}
OUTCOMES = {"success", "failure", "cancelled", "unauthorized", "forbidden", "overloaded", "other"}


def private_context(context: SpanContext | None) -> SpanContext | None:
    if context is None:
        return None
    return SpanContext(
        trace_id=context.trace_id,
        span_id=context.span_id,
        is_remote=context.is_remote,
        trace_flags=context.trace_flags,
        trace_state=TraceState(),
    )


class PrivateSpanExporter(SpanExporter):
    def __init__(self, exporter: SpanExporter) -> None:
        self.exporter = exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        safe = []
        for span in spans:
            original = span.attributes or {}
            attributes: dict[str, str | int | float | bool] = {}
            for field, allowed in [
                ("gen_ai.tool.name", TOOLS),
                ("mcp.method.name", METHODS),
                ("tool", TOOLS),
                ("outcome", OUTCOMES),
            ]:
                value = original.get(field)
                if isinstance(value, str) and value in allowed:
                    attributes[field] = value
            elapsed = original.get("elapsed_seconds")
            if isinstance(elapsed, float) and 0 <= elapsed < 1000:
                attributes["elapsed_seconds"] = elapsed
            safe.append(
                ReadableSpan(
                    name="newsloom.mcp.request",
                    context=private_context(span.context),
                    parent=private_context(span.parent),
                    resource=Resource({"service.name": "newsloom-mcp"}),
                    attributes=attributes,
                    events=(),
                    links=(),
                    kind=span.kind,
                    status=Status(span.status.status_code),
                    start_time=span.start_time,
                    end_time=span.end_time,
                )
            )
        return self.exporter.export(safe)

    def shutdown(self) -> None:
        self.exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.exporter.force_flush(timeout_millis)


class Telemetry:
    def __init__(self, routing: str, client_id: str, model: ModelClient) -> None:
        self.credential = ManagedIdentityCredential(client_id=client_id)
        resource = Resource({"service.name": "newsloom-mcp"})
        self.traces = TracerProvider(resource=resource)
        self.traces.add_span_processor(
            BatchSpanProcessor(
                PrivateSpanExporter(
                    AzureMonitorTraceExporter(
                        connection_string=routing,
                        credential=self.credential,
                        disable_offline_storage=True,
                    )
                )
            )
        )
        trace.set_tracer_provider(self.traces)
        self.metrics = MeterProvider(
            resource=resource,
            metric_readers=[
                PeriodicExportingMetricReader(
                    AzureMonitorMetricExporter(
                        connection_string=routing,
                        credential=self.credential,
                        disable_offline_storage=True,
                    )
                )
            ],
        )
        meter = self.metrics.get_meter("newsloom.mcp")
        self.calls = meter.create_counter("newsloom.mcp.calls")
        self.latency = meter.create_histogram("newsloom.mcp.duration", unit="s")
        self.http_calls = meter.create_counter("newsloom.mcp.http_calls")
        self.http_latency = meter.create_histogram("newsloom.mcp.http_duration", unit="s")

        def tokens(options: CallbackOptions) -> Sequence[Observation]:
            return [Observation(model.observations.input_tokens)]

        def requests(options: CallbackOptions) -> Sequence[Observation]:
            return [Observation(model.observations.embedding_calls)]

        def model_latency(options: CallbackOptions) -> Sequence[Observation]:
            calls = model.observations.embedding_calls
            return [Observation(model.observations.embedding_seconds / calls if calls else 0)]

        meter.create_observable_counter("newsloom.mcp.embedding_input_tokens", callbacks=[tokens])
        meter.create_observable_counter("newsloom.mcp.embedding_calls", callbacks=[requests])
        meter.create_observable_gauge(
            "newsloom.mcp.mean_embedding_latency", callbacks=[model_latency], unit="s"
        )

    def record(self, tool: str, outcome: str, elapsed: float) -> None:
        if tool not in TOOLS or outcome not in OUTCOMES:
            raise McpFailure("invalid_telemetry_category")
        attributes = {"tool": tool, "outcome": outcome}
        self.calls.add(1, attributes)
        self.latency.record(elapsed, attributes)
        with self.traces.get_tracer("newsloom.mcp").start_as_current_span(
            "newsloom.mcp.tool", attributes={**attributes, "elapsed_seconds": elapsed}
        ):
            pass

    def record_http(self, surface: str, outcome: str, elapsed: float) -> None:
        if surface not in ("mcp", "metadata", "health", "other") or outcome not in OUTCOMES:
            raise McpFailure("invalid_telemetry_category")
        attributes = {"surface": surface, "outcome": outcome}
        self.http_calls.add(1, attributes)
        self.http_latency.record(elapsed, attributes)

    def close(self) -> None:
        try:
            if not self.metrics.force_flush() or not self.traces.force_flush():
                raise McpFailure("telemetry_flush_failed")
        finally:
            self.metrics.shutdown()
            self.traces.shutdown()
            self.credential.close()
