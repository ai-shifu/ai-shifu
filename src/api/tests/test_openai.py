from types import SimpleNamespace

import pytest

from flaskr.api import llm

pytestmark = pytest.mark.no_mock_llm


class DummySpan:
    def __init__(self):
        self.generation_args = None
        self.end_args = None
        self.updated = None

    def generation(self, **kwargs):
        self.generation_args = kwargs
        return self

    def end(self, **kwargs):
        self.end_args = kwargs

    def update(self, **kwargs):
        self.updated = kwargs


class FakeResponse:
    def __init__(self, chunk_id, content=None, finish_reason=None, usage=None):
        self.id = chunk_id
        delta = SimpleNamespace(content=content)
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]
        self.usage = usage


class FakeUsage:
    def __init__(self, prompt_tokens, completion_tokens, total_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


def test_invoke_llm_streams_via_litellm(monkeypatch, app):
    captured_kwargs = {}

    def fake_completion(*args, **kwargs):
        captured_kwargs["args"] = args
        captured_kwargs["kwargs"] = kwargs
        usage = FakeUsage(prompt_tokens=5, completion_tokens=4, total_tokens=9)
        chunks = [
            FakeResponse("chunk-1", content="Hello "),
            FakeResponse("chunk-2", content="world", finish_reason="stop", usage=usage),
        ]
        return iter(chunks)

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    provider_state = llm.ProviderState(
        enabled=True,
        params={"api_key": "test-key", "api_base": "https://example.com"},
        models=["gpt-test"],
        prefix="",
        wildcard_prefixes=("gpt",),
    )
    monkeypatch.setattr(llm, "PROVIDER_STATES", {"openai": provider_state})
    monkeypatch.setattr(llm, "MODEL_ALIAS_MAP", {"gpt-test": ("openai", "gpt-test")})
    monkeypatch.setattr(llm, "PROVIDER_CONFIG_HINTS", {"openai": "OPENAI_API_KEY"})

    span = DummySpan()
    responses = list(
        llm.invoke_llm(
            app,
            user_id="user-1",
            span=span,
            model="gpt-test",
            message="Hello world",
            generation_name="unit-test",
        )
    )

    assert [resp.result for resp in responses] == ["Hello ", "world"]
    assert captured_kwargs["kwargs"]["api_key"] == "test-key"
    assert captured_kwargs["kwargs"]["api_base"] == "https://example.com"
    assert captured_kwargs["kwargs"]["stream"] is True
    assert span.generation_args["name"] == "unit-test"
    assert span.end_args is not None
