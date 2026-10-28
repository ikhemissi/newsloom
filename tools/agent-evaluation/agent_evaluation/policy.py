import logging
import os
import sys
from pathlib import Path


class EvaluationFailure(RuntimeError):
    """A content-free failure category suitable for an operator receipt."""


PRIVACY_ENVIRONMENT = {
    "DEEPEVAL_TELEMETRY_OPT_OUT": "1",
    "DEEPEVAL_TELEMETRY_ENABLED": "0",
    "DEEPEVAL_DISABLE_DOTENV": "1",
    "DEEPEVAL_DISABLE_LEGACY_KEYFILE": "1",
    "DEEPEVAL_FILE_SYSTEM": "READ_ONLY",
    "DEEPEVAL_UPDATE_WARNING_OPT_IN": "0",
    "DEEPEVAL_LOG_STACK_TRACES": "0",
    "DEEPEVAL_VERBOSE_MODE": "0",
    "DEEPEVAL_GRPC_LOGGING": "0",
    "DEEPEVAL_EVAL_MODE": "llm",
    "IGNORE_DEEPEVAL_ERRORS": "0",
    "SKIP_DEEPEVAL_MISSING_PARAMS": "0",
    "ENABLE_DEEPEVAL_CACHE": "0",
    "CONFIDENT_TRACE_FLUSH": "0",
    "CONFIDENT_TRACE_VERBOSE": "0",
    "CONFIDENT_TRACE_INTERNAL": "0",
    "CONFIDENT_TRACE_SAMPLE_RATE": "0",
    "CONFIDENT_OPEN_BROWSER": "0",
    "OTEL_SDK_DISABLED": "true",
    "OTEL_TRACES_EXPORTER": "none",
    "OTEL_METRICS_EXPORTER": "none",
    "OTEL_LOGS_EXPORTER": "none",
}

_CREDENTIAL_ENVIRONMENT = (
    "CONFIDENT_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID",
    "OPENAI_ADMIN_KEY",
    "OPENAI_WEBHOOK_SECRET",
    "AZURE_OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "JEV_API_KEY",
    "SENTRY_DSN",
)
_configured = False


def configure_privacy() -> None:
    global _configured
    verify_environment()
    if "deepeval" in sys.modules and not _configured:
        raise EvaluationFailure("evaluator_initialized_before_privacy")
    if _configured:
        verify_privacy()
        return
    os.environ.update(PRIVACY_ENVIRONMENT)
    logging.disable(logging.CRITICAL)
    for name in _CREDENTIAL_ENVIRONMENT:
        os.environ.pop(name, None)
    sys.dont_write_bytecode = True
    _configured = True
    verify_privacy()


def verify_privacy() -> None:
    verify_environment()
    if not _configured or any(
        os.environ.get(name) != value for name, value in PRIVACY_ENVIRONMENT.items()
    ):
        raise EvaluationFailure("evaluation_privacy_configuration_changed")
    if any(os.environ.get(name) for name in _CREDENTIAL_ENVIRONMENT):
        raise EvaluationFailure("evaluation_key_credential_present")
    if logging.root.manager.disable < logging.CRITICAL:
        raise EvaluationFailure("evaluation_logging_configuration_changed")
    from opentelemetry import _logs, metrics, trace

    if type(trace.get_tracer_provider()) not in (
        trace.ProxyTracerProvider,
        trace.NoOpTracerProvider,
    ):
        raise EvaluationFailure("evaluation_instrumentation_present")
    meter = metrics.get_meter_provider()
    logger = _logs.get_logger_provider()
    if (
        type(meter) is not metrics.NoOpMeterProvider
        and (type(meter).__module__, type(meter).__name__)
        != ("opentelemetry.metrics._internal", "_ProxyMeterProvider")
    ) or (
        type(logger) is not _logs.NoOpLoggerProvider
        and (type(logger).__module__, type(logger).__name__)
        != ("opentelemetry._logs._internal", "ProxyLoggerProvider")
    ):
        raise EvaluationFailure("evaluation_instrumentation_present")
    if "deepeval" in sys.modules:
        from deepeval.config.settings import get_settings
        from deepeval.telemetry import NoopBackend, get_backend

        settings = get_settings()
        if (
            settings.CONFIDENT_API_KEY is not None
            or settings.ENABLE_DEEPEVAL_CACHE
            or settings.DEEPEVAL_FILE_SYSTEM != "READ_ONLY"
            or settings.CONFIDENT_TRACE_SAMPLE_RATE != 0
            or settings.CONFIDENT_TRACE_FLUSH
            or settings.CONFIDENT_TRACE_INTERNAL
            or settings.CONFIDENT_TRACE_VERBOSE
            or settings.DEEPEVAL_LOG_STACK_TRACES
            or not settings.DEEPEVAL_TELEMETRY_OPT_OUT
            or settings.DEEPEVAL_TELEMETRY_ENABLED
            or type(get_backend()) is not NoopBackend
        ):
            raise EvaluationFailure("evaluation_runtime_privacy_changed")


def verify_environment() -> None:
    project = Path(__file__).resolve().parents[1]
    if Path(sys.prefix).resolve() != (project / ".venv").resolve():
        raise EvaluationFailure("isolated_evaluation_environment_required")
    if os.environ.get("PYTHONPATH") or os.environ.get("PYTHONHOME"):
        raise EvaluationFailure("evaluation_import_path_override_forbidden")
