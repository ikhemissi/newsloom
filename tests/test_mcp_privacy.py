import asyncio
import json
import logging

import psycopg
import pytest
from newsloom_core.diagnostics import SafeHandler
from newsloom_core.model_transport import ModelFailure, Vector
from newsloom_mcp.models import SearchInput, SearchResults
from newsloom_mcp.telemetry import PrivateSpanExporter
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from test_mcp_auth import signing_key as signing_key
from test_mcp_http import Endpoint, request
from test_mcp_http import endpoint as endpoint


async def test_real_http_sdk_spans_never_export_queries_articles_tokens_or_request_ids(
    endpoint: Endpoint,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(PrivateSpanExporter(output)))
    trace.set_tracer_provider(provider)
    monkeypatch.setattr(logging.getLogger(), "handlers", [SafeHandler()])
    client, reader, embeddings, token, _verifier, _key = endpoint
    client.headers["Authorization"] = "Bearer " + token
    for body in [
        {
            **request(
                "tools/call",
                {"name": "search_news", "arguments": {"query": "NEWSLOOM_QUERY_CANARY"}},
            ),
            "id": "NEWSLOOM_REQUEST_CANARY",
        },
        request(
            "tools/call",
            {"name": "search_news", "arguments": {"limit": True, "query": "NEWSLOOM_QUERY_CANARY"}},
        ),
        request("tools/call", {"name": "get_news_item", "arguments": {"id": str(reader.item.id)}}),
    ]:
        await client.post("/mcp", json=body)

    async def sql_failure(args: SearchInput, vector: tuple[float, ...] | None) -> SearchResults:
        logging.getLogger("psycopg").warning("NEWSLOOM_SQL_LOG_CANARY")
        raise psycopg.OperationalError("NEWSLOOM_SQL_EXCEPTION_CANARY")

    with monkeypatch.context() as patch:
        patch.setattr(reader, "search", sql_failure)
        response = await client.post(
            "/mcp",
            json=request(
                "tools/call", {"name": "search_news", "arguments": {"source": "synthetic"}}
            ),
        )
        assert response.json()["result"]["isError"]
        assert response.json()["result"]["content"][0]["text"] == "database_unavailable"

    async def model_failure(query: str, deadline: float) -> Vector:
        logging.getLogger("httpx").warning("NEWSLOOM_MODEL_LOG_CANARY")
        raise ModelFailure("model_throttled")

    with monkeypatch.context() as patch:
        patch.setattr(embeddings, "embed", model_failure)
        response = await client.post(
            "/mcp",
            json=request(
                "tools/call",
                {"name": "search_news", "arguments": {"query": "NEWSLOOM_QUERY_CANARY"}},
            ),
        )
        assert response.json()["result"]["isError"]
        assert response.json()["result"]["content"][0]["text"] == "model_throttled"

    admitted = asyncio.Event()

    async def blocked_model(query: str, deadline: float) -> Vector:
        admitted.set()
        await asyncio.Future[None]()
        raise AssertionError("cancelled_inference_returned")

    with monkeypatch.context() as patch:
        patch.setattr(embeddings, "embed", blocked_model)
        task = asyncio.create_task(
            client.post(
                "/mcp",
                json=request(
                    "tools/call",
                    {"name": "search_news", "arguments": {"query": "NEWSLOOM_QUERY_CANARY"}},
                ),
            )
        )
        await asyncio.wait_for(admitted.wait(), 5)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert any(outcome == "cancelled" for _, outcome, _ in reader.observations)
    assert any(outcome == "cancelled" for _, outcome, _ in reader.http_observations)
    assert (await client.get("/health/ready")).status_code == 200
    client.headers["Authorization"] = "Bearer NEWSLOOM_CREDENTIAL_CANARY"
    assert (await client.post("/mcp", json=request("tools/list"))).status_code == 401

    parent = trace.SpanContext(
        trace_id=1,
        span_id=2,
        is_remote=True,
        trace_flags=trace.TraceFlags(1),
        trace_state=trace.TraceState([("unsafe", "NEWSLOOM_TRACE_CANARY")]),
    )
    with provider.get_tracer("synthetic").start_as_current_span(
        "NEWSLOOM_SPAN_CANARY",
        context=trace.set_span_in_context(trace.NonRecordingSpan(parent)),
        attributes={"url.full": "NEWSLOOM_URL_CANARY"},
    ) as span:
        span.add_event("NEWSLOOM_EVENT_CANARY")
        span.set_status(trace.Status(trace.StatusCode.ERROR, "NEWSLOOM_ERROR_CANARY"))
        span.record_exception(ValueError("NEWSLOOM_EXCEPTION_CANARY"))
    assert provider.force_flush()
    spans = output.get_finished_spans()
    assert any((span.attributes or {}).get("gen_ai.tool.name") == "search_news" for span in spans)
    for exported in spans:
        value = json.dumps(
            {
                "name": exported.name,
                "attributes": dict(exported.attributes or {}),
                "events": [str(event) for event in exported.events],
                "status": exported.status.description,
                "resource": dict(exported.resource.attributes),
            }
        )
        assert "CANARY" not in value and token not in value
        assert not exported.events and not exported.links
        assert exported.context is None or not exported.context.trace_state
        assert exported.parent is None or not exported.parent.trace_state
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err
    provider.shutdown()
