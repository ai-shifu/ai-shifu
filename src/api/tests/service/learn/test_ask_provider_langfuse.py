import types
from unittest.mock import patch

from flask import Flask

from flaskr.service.learn.ask_provider_langfuse import stream_provider_with_langfuse


class _DummyGeneration:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.end_kwargs = {}

    def end(self, **kwargs):
        self.end_kwargs = kwargs


class _DummySpan:
    def __init__(self, trace_id="trace-1", span_id="span-1"):
        self.trace_id = trace_id
        self.id = span_id
        self.generations = []

    def generation(self, **kwargs):
        generation = _DummyGeneration(**kwargs)
        self.generations.append(generation)
        return generation


def test_stream_provider_with_langfuse_links_generation_to_parent_span():
    app = Flask("ask-provider-langfuse")
    span = _DummySpan(trace_id="trace-1", span_id="follow-up-span-1")
    provider_stream = [
        types.SimpleNamespace(content="provider-"),
        types.SimpleNamespace(content="answer"),
    ]

    events = list(
        stream_provider_with_langfuse(
            provider_stream=provider_stream,
            span=span,
            app=app,
            provider_name="coze",
            generation_name="lesson_runtime/generation/ask_provider",
            user_query="hello",
            messages=[{"role": "user", "content": "hello"}],
            provider_config={"config": {"api_key": "secret"}},
        )
    )

    assert events == provider_stream
    assert len(span.generations) == 1
    generation = span.generations[0]
    assert generation.kwargs["trace_id"] == "trace-1"
    assert generation.kwargs["parent_observation_id"] == "follow-up-span-1"
    assert generation.end_kwargs["output"] == "provider-answer"
    assert generation.end_kwargs["metadata"]["status"] == "success"
    assert (
        generation.end_kwargs["metadata"]["provider_config"]["config"]["api_key"]
        == "[REDACTED]"
    )


def test_stream_provider_with_langfuse_uses_request_trace_id_fallback():
    app = Flask("ask-provider-langfuse-fallback")
    span = _DummySpan(trace_id="", span_id="follow-up-span-2")

    with patch(
        "flaskr.api.langfuse.get_request_trace_id",
        return_value="request-trace-1",
    ):
        list(
            stream_provider_with_langfuse(
                provider_stream=[types.SimpleNamespace(content="ok")],
                span=span,
                app=app,
                provider_name="dify",
                generation_name="lesson_runtime/generation/ask_provider_dify",
                user_query="hello",
                messages=[{"role": "user", "content": "hello"}],
                provider_config={},
            )
        )

    assert len(span.generations) == 1
    generation = span.generations[0]
    assert generation.kwargs["trace_id"] == "request-trace-1"
    assert generation.kwargs["parent_observation_id"] == "follow-up-span-2"
