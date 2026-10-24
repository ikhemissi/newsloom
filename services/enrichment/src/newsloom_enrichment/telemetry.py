"""Explicit Entra-authenticated enrichment counters and timing summaries."""

from azure.identity import ManagedIdentityCredential
from azure.monitor.opentelemetry.exporter import (
    AzureMonitorMetricExporter,
    AzureMonitorTraceExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from newsloom_enrichment.models import EnrichmentFailure
from newsloom_enrichment.providers import Observations


class Telemetry:
    def __init__(self, routing: str, client_id: str) -> None:
        self.credential = ManagedIdentityCredential(client_id=client_id)
        resource = Resource({"service.name": "newsloom-enrichment"})
        self.traces = TracerProvider(resource=resource)
        self.traces.add_span_processor(
            BatchSpanProcessor(
                AzureMonitorTraceExporter(
                    connection_string=routing,
                    credential=self.credential,
                    disable_offline_storage=True,
                )
            )
        )
        reader = PeriodicExportingMetricReader(
            AzureMonitorMetricExporter(
                connection_string=routing, credential=self.credential, disable_offline_storage=True
            )
        )
        self.metrics = MeterProvider(resource=resource, metric_readers=[reader])
        meter = self.metrics.get_meter("newsloom.enrichment")
        self.counter = meter.create_counter("newsloom.enrichment.outcomes")
        self.duration = meter.create_histogram("newsloom.enrichment.duration", unit="s")
        self.depth = meter.create_gauge("newsloom.enrichment.queue_depth")
        self.model_latency = meter.create_histogram(
            "newsloom.enrichment.mean_model_latency", unit="s"
        )

    def record(
        self, correlation: str, counts: dict[str, int], elapsed: float, observations: Observations
    ) -> None:
        attributes = {"correlation_id": correlation}
        for outcome, value in {
            **counts,
            "generation_calls": observations.generation_calls,
            "embedding_calls": observations.embedding_calls,
            "input_tokens": observations.input_tokens,
            "output_tokens": observations.output_tokens,
        }.items():
            self.counter.add(value, {**attributes, "outcome": outcome})
        self.duration.record(elapsed, attributes)
        self.depth.set(counts["pending"], attributes)
        for stage, calls, seconds in [
            ("generation", observations.generation_calls, observations.generation_seconds),
            ("embedding", observations.embedding_calls, observations.embedding_seconds),
        ]:
            if calls:
                self.model_latency.record(seconds / calls, {**attributes, "stage": stage})
        with self.traces.get_tracer("newsloom.enrichment").start_as_current_span(
            "newsloom.enrichment.run", attributes=attributes
        ) as span:
            for key, value in counts.items():
                span.set_attribute(key, value)

    def close(self) -> None:
        try:
            if not self.metrics.force_flush() or not self.traces.force_flush():
                raise EnrichmentFailure("telemetry_flush_failed")
        finally:
            self.metrics.shutdown()
            self.traces.shutdown()
            self.credential.close()
