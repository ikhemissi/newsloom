import logging

import pytest
from azure.identity import ManagedIdentityCredential
from newsloom_core.diagnostics import SafeHandler
from newsloom_enrichment.providers import Observations
from newsloom_enrichment.telemetry import Telemetry
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def test_enrichment_metrics_and_spans_are_numeric_and_content_free(
    capsys: pytest.CaptureFixture[str],
) -> None:
    telemetry = Telemetry.__new__(Telemetry)
    reader = InMemoryMetricReader()
    spans = InMemorySpanExporter()
    telemetry.metrics = MeterProvider(metric_readers=[reader])
    telemetry.traces = TracerProvider()
    telemetry.traces.add_span_processor(SimpleSpanProcessor(spans))
    telemetry.credential = ManagedIdentityCredential()
    meter = telemetry.metrics.get_meter("newsloom.enrichment")
    telemetry.counter = meter.create_counter("newsloom.enrichment.outcomes")
    telemetry.duration = meter.create_histogram("newsloom.enrichment.duration", unit="s")
    telemetry.depth = meter.create_gauge("newsloom.enrichment.queue_depth")
    telemetry.model_latency = meter.create_histogram(
        "newsloom.enrichment.mean_model_latency", unit="s"
    )
    counts = {"pending": 1, "completed": 2, "news": 2, "enriched_run": 2}
    telemetry.record(
        "fixture",
        counts,
        2.0,
        Observations(
            generation_calls=2,
            embedding_calls=2,
            input_tokens=100,
            output_tokens=50,
            generation_seconds=1.0,
            embedding_seconds=0.5,
        ),
    )
    data = reader.get_metrics_data()
    assert data is not None
    names = {
        metric.name
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }
    assert names == {
        "newsloom.enrichment.outcomes",
        "newsloom.enrichment.duration",
        "newsloom.enrichment.queue_depth",
        "newsloom.enrichment.mean_model_latency",
    }
    finished = spans.get_finished_spans()
    assert len(finished) == 1 and finished[0].name == "newsloom.enrichment.run"
    assert dict(finished[0].attributes or {}) == {"correlation_id": "fixture", **counts}
    SafeHandler().emit(
        logging.LogRecord(
            "azure",
            logging.WARNING,
            "",
            1,
            "NEWSLOOM_COMPLETION_CANARY %s",
            ("NEWSLOOM_CREDENTIAL_CANARY",),
            None,
        )
    )
    assert "CANARY" not in capsys.readouterr().out
    telemetry.close()
