import json

import pytest
from newsloom_core.phase1_contracts import AcceptanceFailure
from phase1_acceptance import telemetry
from test_phase1_contracts import report


@pytest.mark.parametrize("flush", [True, False])
def test_authenticated_metric_export_has_only_fixed_stage_outcome_and_numeric_values(
    flush: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values: list[object] = []
    closed = []

    class Credential:
        def __init__(self, *, client_id: str) -> None:
            assert client_id == "synthetic-client"

        def close(self) -> None:
            closed.append("credential")

    class Instrument:
        def add(self, value: int, attributes: dict[str, str]) -> None:
            values.append((value, attributes))

        def record(self, value: float, attributes: dict[str, str]) -> None:
            values.append((value, attributes))

    class Meter:
        def create_counter(self, name: str) -> Instrument:
            assert name == "newsloom.phase1.stages"
            return Instrument()

        def create_histogram(self, name: str, *, unit: str) -> Instrument:
            assert name == "newsloom.phase1.stage_duration" and unit == "s"
            return Instrument()

    class Provider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def get_meter(self, name: str) -> Meter:
            assert name == "newsloom.phase1"
            return Meter()

        def force_flush(self) -> bool:
            return flush

        def shutdown(self) -> None:
            closed.append("provider")

    monkeypatch.setattr(telemetry, "ManagedIdentityCredential", Credential)
    monkeypatch.setattr(telemetry, "MeterProvider", Provider)
    monkeypatch.setattr(telemetry, "AzureMonitorMetricExporter", lambda **kwargs: object())
    monkeypatch.setattr(telemetry, "PeriodicExportingMetricReader", lambda *args: object())
    if flush:
        telemetry.publish(report(), "NEWSLOOM_CREDENTIAL_CANARY", "synthetic-client")
    else:
        with pytest.raises(AcceptanceFailure, match="telemetry_flush_failed"):
            telemetry.publish(report(), "NEWSLOOM_CREDENTIAL_CANARY", "synthetic-client")
    assert len(values) == 16 and closed == ["provider", "credential"]
    captured = capsys.readouterr()
    assert "CANARY" not in json.dumps(values) + captured.out + captured.err
