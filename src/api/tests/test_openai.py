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


def test_invoke_llm_streams_via_litellm(monkeypatch, app):
    captured_kwargs = {}

    def fake_responses(*args, **kwargs):
        captured_kwargs["args"] = args
        captured_kwargs["kwargs"] = kwargs
        assert isinstance(kwargs.get("input"), list)
        chunks = [
            {
                "type": "response.output_text.delta",
                "delta": "Hello ",
                "response_id": "resp-1",
            },
            {
                "type": "response.output_text.delta",
                "delta": "world",
                "response_id": "resp-1",
            },
            {
                "type": "response.completed",
                "response_id": "resp-1",
                "response": {
                    "id": "resp-1",
                    "usage": {"input_tokens": 5, "output_tokens": 4, "total_tokens": 9},
                },
            },
        ]
        return iter(chunks)

    monkeypatch.setattr(llm.litellm, "responses", fake_responses)
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
