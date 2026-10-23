import json

import pytest
from azure.identity import ManagedIdentityCredential
from newsloom_ingestion import telemetry
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def test_real_sdk_metrics_and_correlated_spans_use_authenticated_export_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = InMemoryMetricReader()
    spans = InMemorySpanExporter()

    def trace_exporter(**kwargs: object) -> InMemorySpanExporter:
        assert kwargs["disable_offline_storage"] is True
        assert isinstance(kwargs["credential"], ManagedIdentityCredential)
        return spans

    def metric_exporter(**kwargs: object) -> None:
        assert kwargs["disable_offline_storage"] is True
        assert isinstance(kwargs["credential"], ManagedIdentityCredential)

    monkeypatch.setattr(telemetry, "AzureMonitorTraceExporter", trace_exporter)
    monkeypatch.setattr(telemetry, "AzureMonitorMetricExporter", metric_exporter)
    monkeypatch.setattr(telemetry, "PeriodicExportingMetricReader", lambda exporter: reader)
    client = telemetry.Telemetry("synthetic-routing", "synthetic-client")
    try:
        client.record("fixture-correlation", {"pending": 4, "accepted_run": 2}, 1.5)
        assert client.traces.force_flush()
        data = reader.get_metrics_data()
        assert data is not None
        payload = json.loads(data.to_json())
        metrics = {
            metric["name"]: metric["data"]["data_points"]
            for metric in payload["resource_metrics"][0]["scope_metrics"][0]["metrics"]
        }
        assert metrics["newsloom.ingestion.duration"][0]["sum"] == 1.5
        assert metrics["newsloom.ingestion.queue_depth"][0]["value"] == 4
        assert {
            point["attributes"]["outcome"]: point["value"]
            for point in metrics["newsloom.ingestion.outcomes"]
        } == {"pending": 4, "accepted_run": 2}
        finished = spans.get_finished_spans()
        assert len(finished) == 1
        assert finished[0].attributes is not None
        assert finished[0].attributes["correlation_id"] == "fixture-correlation"
        assert finished[0].attributes["pending"] == 4
    finally:
        client.close()
