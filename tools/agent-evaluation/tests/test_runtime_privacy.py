import logging
from collections.abc import Callable

import pytest
from deepeval.config.settings import get_settings
from opentelemetry import _logs, metrics, trace
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider

from agent_evaluation.policy import EvaluationFailure, configure_privacy, verify_privacy


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("CONFIDENT_API_KEY", "synthetic-cached-key-canary"),
        ("ENABLE_DEEPEVAL_CACHE", True),
        ("DEEPEVAL_FILE_SYSTEM", "NORMAL"),
        ("CONFIDENT_TRACE_SAMPLE_RATE", 1.0),
        ("CONFIDENT_TRACE_FLUSH", True),
        ("CONFIDENT_TRACE_INTERNAL", True),
        ("CONFIDENT_TRACE_VERBOSE", True),
        ("DEEPEVAL_LOG_STACK_TRACES", True),
        ("DEEPEVAL_TELEMETRY_OPT_OUT", False),
        ("DEEPEVAL_TELEMETRY_ENABLED", True),
    ],
)
def test_cached_runtime_privacy_drift_is_rejected(
    field: str,
    value: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(get_settings().__dict__, field, value)
    with pytest.raises(EvaluationFailure, match="evaluation_runtime_privacy_changed"):
        verify_privacy()


@pytest.mark.parametrize("kind", ["traces", "metrics", "logs"])
def test_sdk_instrumentation_is_rejected_even_when_environment_is_disabled(
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutdown: Callable[[], None]
    if kind == "traces":
        provider = TracerProvider(shutdown_on_exit=False)
        monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
        shutdown = provider.shutdown
    elif kind == "metrics":
        meter = MeterProvider(shutdown_on_exit=False)
        monkeypatch.setattr(metrics, "get_meter_provider", lambda: meter)
        shutdown = meter.shutdown
    else:
        logger = LoggerProvider(shutdown_on_exit=False)
        monkeypatch.setattr(_logs, "get_logger_provider", lambda: logger)
        shutdown = logger.shutdown
    try:
        with pytest.raises(EvaluationFailure, match="evaluation_instrumentation_present"):
            configure_privacy()
    finally:
        shutdown()


def test_forced_logging_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging.root.manager, "disable", 0)
    with pytest.raises(EvaluationFailure, match="evaluation_logging_configuration_changed"):
        verify_privacy()
