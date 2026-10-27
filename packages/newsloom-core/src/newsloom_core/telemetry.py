"""Rebuild spans without dependency-controlled content or resource attributes."""

from collections.abc import Mapping

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanContext, Status, TraceState
from opentelemetry.util.types import AttributeValue


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


def private_span(
    span: ReadableSpan,
    *,
    name: str,
    service: str,
    attributes: Mapping[str, AttributeValue],
) -> ReadableSpan:
    return ReadableSpan(
        name=name,
        context=private_context(span.context),
        parent=private_context(span.parent),
        resource=Resource({"service.name": service}),
        attributes=attributes,
        events=(),
        links=(),
        kind=span.kind,
        status=Status(span.status.status_code),
        start_time=span.start_time,
        end_time=span.end_time,
    )
