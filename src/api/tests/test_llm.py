from types import SimpleNamespace
from flaskr.api import llm


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


def test_invoke_llm_ark_endpoint_uses_model_name_for_max_tokens(monkeypatch, app):
    captured_kwargs = {}
    captured_token_models = []

    def fake_completion(*args, **kwargs):
        captured_kwargs["kwargs"] = kwargs
        chunks = [
            FakeResponse("chunk-1", content="ok", finish_reason="stop"),
        ]
        return iter(chunks)

    def fake_get_max_tokens(token_model):
        captured_token_models.append(token_model)
        return 123

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm, "get_max_tokens", fake_get_max_tokens)

    provider_state = llm.ProviderState(
        enabled=True,
        params={"api_key": "test-key", "api_base": "https://example.com"},
        models=["ark/doubao-pro"],
        prefix="ark/",
        wildcard_prefixes=(),
    )
    monkeypatch.setattr(llm, "PROVIDER_STATES", {"ark": provider_state})
    monkeypatch.setattr(
        llm, "MODEL_ALIAS_MAP", {"ark/doubao-pro": ("ark", "endpoint-123")}
    )
    monkeypatch.setattr(llm, "PROVIDER_CONFIG_HINTS", {"ark": "ARK_API_KEY"})
    monkeypatch.setattr(llm, "ACTUAL_MODEL_NAME_MAP", {"endpoint-123": "doubao-pro"})

    span = DummySpan()
    responses = list(
        llm.invoke_llm(
            app,
            user_id="user-1",
            span=span,
            model="ark/doubao-pro",
            message="hello",
            generation_name="ark-test",
        )
    )

    assert [resp.result for resp in responses] == ["ok"]
    assert captured_kwargs["kwargs"]["max_tokens"] == 123
    assert captured_token_models == ["doubao-pro"]
