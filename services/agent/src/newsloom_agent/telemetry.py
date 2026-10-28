"""Managed-identity export of allowlisted outcomes, durations and observed usage."""

import math
from collections.abc import Sequence
from typing import Protocol

from azure.identity import ManagedIdentityCredential
from azure.monitor.opentelemetry.exporter import (
    AzureMonitorMetricExporter,
    AzureMonitorTraceExporter,
)
from newsloom_core.telemetry import private_span
from opentelemetry import trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from newsloom_agent.generation import GenerationStats
from newsloom_agent.models import AgentFailure
from newsloom_agent.research_generation import ResearchStats

OUTCOMES = {"success", "failure", "cancelled", "unauthorized", "forbidden", "overloaded", "other"}
SURFACES = {"a2a", "metadata", "health", "other"}
CATEGORIES = {
    "",
    "request_timeout",
    "authorization_expired",
    "user_preservation_failed",
    "assertion_lifetime",
    "assertion_unavailable",
    "exchange_denied",
    "exchange_unavailable",
    "exchange_response_invalid",
    "downstream_keys_unavailable",
    "downstream_token_invalid",
    "downstream_permission_invalid",
    "mcp_denied",
    "mcp_unavailable",
    "mcp_response_limit",
    "mcp_aggregate_response_limit",
    "mcp_response_invalid",
    "model_denied",
    "model_throttled",
    "model_unavailable",
    "model_token_lifetime",
    "model_identity_unavailable",
    "model_refused",
    "model_incomplete",
    "model_stream_incomplete",
    "model_input_limit",
    "model_output_limit",
    "model_update_limit",
    "model_response_limit",
    "model_redirect_refused",
    "model_transport_boundary",
    "invalid_model_stream",
    "invalid_model_usage",
    "model_token_limit",
    "unsupported_model_content",
    "agent_execution_failed",
    "research_tool_invalid",
    "research_result_invalid",
    "research_tool_limit",
    "research_repeated_tool",
    "research_selection_boundary",
    "research_unknown_item",
    "research_filter_relaxation",
    "research_filter_violation",
    "research_inconsistent_evidence",
    "research_evidence_limit",
    "research_citation_url_invalid",
    "research_model_url_refused",
    "research_answer_invalid",
    "research_coverage_invalid",
    "research_citation_unknown",
    "research_answer_limit",
    "research_no_retrieval",
    "research_missing_detail",
    "research_model_call_limit",
    "research_planning_limit",
    "research_token_reservation",
    "research_model_input_limit",
    "research_model_response_limit",
    "research_schema_invalid",
    "research_model_input_invalid",
    "research_model_structure_invalid",
    "other",
}


class AgentObserver(Protocol):
    def execution(
        self, outcome: str, category: str, elapsed: float, stats: GenerationStats
    ) -> None: ...

    def http(self, surface: str, outcome: str, elapsed: float) -> None: ...


class PrivateSpanExporter(SpanExporter):
    def __init__(self, exporter: SpanExporter) -> None:
        self.exporter = exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        safe = []
        for span in spans:
            original = span.attributes or {}
            attributes: dict[str, str | int | float | bool] = {}
            for key, allowed in (
                ("operation", {"recent-news", "research"}),
                ("outcome", OUTCOMES),
                ("category", CATEGORIES),
            ):
                value = original.get(key)
                if isinstance(value, str) and value in allowed:
                    attributes[key] = value
            elapsed = original.get("elapsed_seconds")
            if isinstance(elapsed, float) and math.isfinite(elapsed) and 0 <= elapsed <= 300:
                attributes["elapsed_seconds"] = elapsed
            research = original.get("operation") == "research"
            for key, maximum in (
                ("generation_calls", 4 if research else 1),
                ("input_tokens", 262144 if research else 65536),
                ("output_tokens", 4096 if research else 512),
            ):
                value = original.get(key)
                if type(value) is int and 0 <= value <= maximum:
                    attributes[key] = value
            if research:
                for key, maximum in (("tool_calls", 8), ("usage_observed_calls", 4)):
                    value = original.get(key)
                    if type(value) is int and 0 <= value <= maximum:
                        attributes[key] = value
                complete = original.get("usage_complete")
                if type(complete) is bool:
                    attributes["usage_complete"] = complete
            safe.append(
                private_span(
                    span,
                    name="newsloom.agent.request",
                    service="newsloom-agent",
                    attributes=attributes,
                )
            )
        return self.exporter.export(safe)

    def shutdown(self) -> None:
        self.exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.exporter.force_flush(timeout_millis)


class Telemetry:
    def __init__(self, routing: str, client_id: str) -> None:
        self.credential = ManagedIdentityCredential(client_id=client_id)
        resource = Resource({"service.name": "newsloom-agent"})
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
        meter = self.metrics.get_meter("newsloom.agent")
        self.calls = meter.create_counter("newsloom.agent.calls")
        self.duration = meter.create_histogram("newsloom.agent.duration", unit="s")
        self.model_calls = meter.create_counter("newsloom.agent.generation_calls")
        self.input_tokens = meter.create_counter("newsloom.agent.input_tokens")
        self.output_tokens = meter.create_counter("newsloom.agent.output_tokens")
        self.usage_reads = meter.create_counter("newsloom.agent.usage_observed")
        self.http_calls = meter.create_counter("newsloom.agent.http_calls")
        self.http_duration = meter.create_histogram("newsloom.agent.http_duration", unit="s")

    def execution(
        self, outcome: str, category: str, elapsed: float, stats: GenerationStats
    ) -> None:
        if outcome not in OUTCOMES or not math.isfinite(elapsed) or elapsed < 0:
            raise AgentFailure("invalid_telemetry_category")
        category = category if category in CATEGORIES else "other"
        research = isinstance(stats, ResearchStats)
        attributes = {
            "operation": "research" if research else "recent-news",
            "outcome": outcome,
            "category": category,
        }
        self.calls.add(1, attributes)
        self.duration.record(elapsed, attributes)
        self.model_calls.add(stats.calls, attributes)
        observed_calls = (
            stats.usage_calls if isinstance(stats, ResearchStats) else int(stats.usage_observed)
        )
        self.usage_reads.add(observed_calls, attributes)
        span_attributes: dict[str, str | int | float | bool] = {
            **attributes,
            "elapsed_seconds": elapsed,
            "generation_calls": stats.calls,
        }
        if isinstance(stats, ResearchStats):
            span_attributes.update(
                tool_calls=stats.tool_calls,
                usage_observed_calls=stats.usage_calls,
                usage_complete=stats.usage_observed,
            )
        if observed_calls:
            self.input_tokens.add(stats.input_tokens, attributes)
            self.output_tokens.add(stats.output_tokens, attributes)
            span_attributes.update(
                input_tokens=stats.input_tokens, output_tokens=stats.output_tokens
            )
        with self.traces.get_tracer("newsloom.agent").start_as_current_span(
            "newsloom.agent.execution",
            attributes=span_attributes,
            record_exception=False,
            set_status_on_exception=False,
        ):
            pass

    def http(self, surface: str, outcome: str, elapsed: float) -> None:
        if (
            surface not in SURFACES
            or outcome not in OUTCOMES
            or not math.isfinite(elapsed)
            or elapsed < 0
        ):
            raise AgentFailure("invalid_telemetry_category")
        attributes = {"surface": surface, "outcome": outcome}
        self.http_calls.add(1, attributes)
        self.http_duration.record(elapsed, attributes)

    def close(self) -> None:
        try:
            metrics_flushed = self.metrics.force_flush()
            traces_flushed = self.traces.force_flush()
            if not metrics_flushed or not traces_flushed:
                raise AgentFailure("telemetry_flush_failed")
        finally:
            try:
                self.metrics.shutdown()
            finally:
                try:
                    self.traces.shutdown()
                finally:
                    self.credential.close()
