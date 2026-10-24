"""Allowlisted diagnostics and explicit, authenticated OpenTelemetry export."""

from azure.identity import ManagedIdentityCredential
from azure.monitor.opentelemetry.exporter import (
    AzureMonitorMetricExporter,
    AzureMonitorTraceExporter,
)
from newsloom_core.diagnostics import (
    SafeHandler as SafeHandler,
)
from newsloom_core.diagnostics import (
    configure_logging as configure_logging,
)
from newsloom_core.diagnostics import (
    event as event,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from newsloom_ingestion.models import IngestionFailure


class Telemetry:
    def __init__(self, routing: str, client_id: str) -> None:
        self.credential = ManagedIdentityCredential(client_id=client_id)
        resource = Resource({"service.name": "newsloom-ingestion"})
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
                connection_string=routing,
                credential=self.credential,
                disable_offline_storage=True,
            )
        )
        self.metrics = MeterProvider(resource=resource, metric_readers=[reader])
        meter = self.metrics.get_meter("newsloom.ingestion")
        self.counter = meter.create_counter("newsloom.ingestion.outcomes")
        self.latency = meter.create_histogram("newsloom.ingestion.duration", unit="s")
        self.depth = meter.create_gauge("newsloom.ingestion.queue_depth")

    def record(self, correlation: str, counts: dict[str, int], elapsed: float) -> None:
        attributes = {"correlation_id": correlation}
        for outcome, count in counts.items():
            self.counter.add(count, {**attributes, "outcome": outcome})
        self.latency.record(elapsed, attributes)
        self.depth.set(counts["pending"], attributes)
        tracer = self.traces.get_tracer("newsloom.ingestion")
        with tracer.start_as_current_span("newsloom.ingestion.run", attributes=attributes) as span:
            for name, count in counts.items():
                span.set_attribute(name, count)

    def close(self) -> None:
        try:
            if not self.metrics.force_flush() or not self.traces.force_flush():
                raise IngestionFailure("telemetry_flush_failed")
        finally:
            self.metrics.shutdown()
            self.traces.shutdown()
            self.credential.close()
