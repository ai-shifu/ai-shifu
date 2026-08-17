"""Langfuse SDK v4 semantics of the compatibility facade in flaskr.api.langfuse.

The facade keeps the legacy call surface (trace.span(), span.generation(), ...)
while the SDK only exposes observations. These tests drive a real Langfuse
client whose spans are captured in memory, so the resulting OTel spans are
asserted the way the Langfuse backend reads them: parent/child hierarchy,
overall input/output on the root observation, and trace attributes replicated
onto every observation.
"""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExportResult,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from langfuse import Langfuse
from langfuse._client.resource_manager import LangfuseResourceManager
from langfuse._client.span_exporter import LangfuseTransformingSpanExporter

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
)


@pytest.fixture
def captured_spans(monkeypatch):
    """A Langfuse client whose observations are captured instead of shipped."""
    monkeypatch.setattr(
        LangfuseTransformingSpanExporter,
        "export",
        lambda self, spans: SpanExportResult.SUCCESS,
        raising=False,
    )
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    client = Langfuse(
        public_key="pk-lf-test-v4-semantics",
        secret_key="sk-lf-test-v4-semantics",
        host="http://langfuse.invalid",
        tracer_provider=provider,
        tracing_enabled=True,
    )
    try:
        yield client, exporter
    finally:
        # Shut the client down while the exporter is still stubbed, otherwise
        # the batch processor flushes to the network at interpreter exit.
        client.shutdown()
        provider.shutdown()
        LangfuseResourceManager._instances.clear()


def _spans_by_name(exporter: InMemorySpanExporter) -> dict:
    return {span.name: span for span in exporter.get_finished_spans()}


def test_facade_builds_a_single_observation_hierarchy(captured_spans):
    client, exporter = captured_spans

    trace, root_span = create_trace_with_root_span(
        client=client,
        trace_payload={
            "id": "request-id-1",
            "name": "lesson",
            "user_id": "user-1",
            "input": "hello",
            "metadata": {"outline": "outline-1"},
        },
        root_span_payload={"input": "hello"},
    )
    ask_span = root_span.span(name="ask")
    generation = ask_span.generation(name="llm", model="gpt-test")
    generation.end(output="answer")
    ask_span.end(output="answer")
    finalize_langfuse_trace(
        trace=trace,
        root_span=root_span,
        trace_payload={"output": "answer"},
        root_span_payload={"output": "answer"},
    )

    spans = _spans_by_name(exporter)
    assert set(spans) == {"lesson", "ask", "llm"}
    trace_ids = {span.context.trace_id for span in spans.values()}
    assert len(trace_ids) == 1
    assert spans["ask"].parent.span_id == spans["lesson"].context.span_id
    assert spans["llm"].parent.span_id == spans["ask"].context.span_id
    assert spans["llm"].attributes["langfuse.observation.type"] == "generation"
    assert spans["llm"].attributes["langfuse.observation.model.name"] == "gpt-test"


def test_overall_input_output_lands_on_the_root_observation(captured_spans):
    client, exporter = captured_spans

    trace, root_span = create_trace_with_root_span(
        client=client,
        trace_payload={"id": "request-id-2", "name": "lesson", "input": "hello"},
        root_span_payload={"input": "hello"},
    )
    finalize_langfuse_trace(
        trace=trace,
        root_span=root_span,
        trace_payload={"output": "answer"},
        root_span_payload={"output": "answer"},
    )

    root = _spans_by_name(exporter)["lesson"]
    # v4 dropped the mutable trace record: the overall input/output of a trace
    # is read from its root observation.
    assert root.attributes["langfuse.observation.input"] == "hello"
    assert root.attributes["langfuse.observation.output"] == "answer"
    assert root.attributes["langfuse.internal.as_root"] is True


def test_trace_attributes_are_propagated_to_child_observations(captured_spans):
    client, exporter = captured_spans

    trace, root_span = create_trace_with_root_span(
        client=client,
        trace_payload={
            "id": "request-id-3",
            "name": "lesson",
            "user_id": "user-1",
            "metadata": {"outline": "outline-1"},
        },
        root_span_payload={},
    )
    ask_span = root_span.span(name="ask")
    ask_span.end(output="answer")
    # A session id bound late must still reach the observations of the trace.
    trace.update(session_id="session-1")
    root_span.end()

    spans = _spans_by_name(exporter)
    for span in spans.values():
        assert span.attributes["user.id"] == "user-1"
        assert span.attributes["langfuse.trace.name"] == "lesson"
        assert span.attributes["langfuse.trace.metadata.outline"] == "outline-1"
    assert spans["lesson"].attributes["session.id"] == "session-1"
