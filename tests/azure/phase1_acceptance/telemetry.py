from azure.identity import ManagedIdentityCredential
from azure.monitor.opentelemetry.exporter import AzureMonitorMetricExporter
from newsloom_core.phase1_contracts import AcceptanceFailure, Report
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource


def publish(report: Report, routing: str, client_id: str) -> None:
    credential = ManagedIdentityCredential(client_id=client_id)
    provider = MeterProvider(
        resource=Resource({"service.name": "newsloom-phase1-acceptance"}),
        metric_readers=[
            PeriodicExportingMetricReader(
                AzureMonitorMetricExporter(
                    connection_string=routing,
                    credential=credential,
                    disable_offline_storage=True,
                )
            )
        ],
    )
    try:
        meter = provider.get_meter("newsloom.phase1")
        stages = meter.create_counter("newsloom.phase1.stages")
        duration = meter.create_histogram("newsloom.phase1.stage_duration", unit="s")
        for stage in report.stages:
            attributes = {"stage": stage.name, "outcome": report.outcome}
            stages.add(1, attributes)
            duration.record(stage.elapsed_seconds, attributes)
        if not provider.force_flush():
            raise AcceptanceFailure("acceptance_telemetry_flush_failed")
    finally:
        provider.shutdown()
        credential.close()
