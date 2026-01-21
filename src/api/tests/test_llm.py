from types import SimpleNamespace

import pytest

from flaskr.api import llm

pytestmark = pytest.mark.no_mock_llm


class DummySpan:
    def __init__(self):
        self.generation_args = None
        self.end_args = None

    def generation(self, **kwargs):
        self.generation_args = kwargs
        return self

    def end(self, **kwargs):
        self.end_args = kwargs

    def update(self, **kwargs):
        self.update_args = kwargs


class FakeResponse:
    def __init__(self, chunk_id, content=None, finish_reason=None, usage=None):
        self.id = chunk_id
        delta = SimpleNamespace(content=content)
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]
        self.usage = usage


def test_chat_llm_streams(monkeypatch, app):
    captured_kwargs = {}

    def fake_completion(*args, **kwargs):
        captured_kwargs["kwargs"] = kwargs
        chunks = [
            FakeResponse("chunk-1", content="Hi "),
            FakeResponse("chunk-2", content="there", finish_reason="stop"),
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

    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"},
    ]
    span = DummySpan()
    responses = list(
        llm.chat_llm(
            app=app,
            user_id="user-1",
            span=span,
            model="gpt-test",
            messages=messages,
            temperature="0.7",
            generation_name="chat-test",
        )
    )

    assert [resp.result for resp in responses] == ["Hi ", "there"]
    assert captured_kwargs["kwargs"]["temperature"] == 0.7
    assert captured_kwargs["kwargs"]["stream"] is True
    assert span.generation_args["name"] == "chat-test"
