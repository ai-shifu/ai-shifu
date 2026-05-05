# ruff: noqa: E402
import sys
import types
from types import SimpleNamespace

import pytest


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = types.ModuleType("litellm")
    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.completion = lambda *args, **kwargs: iter([])
    sys.modules["litellm"] = litellm_stub


def _install_openai_responses_stub() -> None:
    if "openai.types.responses" in sys.modules:
        return

    responses_pkg = types.ModuleType("openai.types.responses")
    responses_pkg.__path__ = []
    response_mod = types.ModuleType("openai.types.responses.response")
    response_create_mod = types.ModuleType(
        "openai.types.responses.response_create_params"
    )
    response_function_mod = types.ModuleType(
        "openai.types.responses.response_function_tool_call"
    )
    response_text_mod = types.ModuleType(
        "openai.types.responses.response_text_config_param"
    )

    for name in [
        "IncompleteDetails",
        "Response",
        "ResponseOutputItem",
        "Tool",
        "ToolChoice",
    ]:
        setattr(response_mod, name, type(name, (), {}))

    for name in [
        "Reasoning",
        "ResponseIncludable",
        "ResponseInputParam",
        "ToolChoice",
        "ToolParam",
        "Text",
    ]:
        setattr(response_create_mod, name, type(name, (), {}))

    response_function_tool_call = type("ResponseFunctionToolCall", (), {})
    response_text_config = type("ResponseTextConfigParam", (), {})
    setattr(
        response_function_mod,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )
    setattr(
        response_text_mod,
        "ResponseTextConfigParam",
        response_text_config,
    )
    setattr(
        responses_pkg,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )

    sys.modules["openai.types.responses"] = responses_pkg
    sys.modules["openai.types.responses.response"] = response_mod
    sys.modules["openai.types.responses.response_create_params"] = response_create_mod
    sys.modules["openai.types.responses.response_function_tool_call"] = (
        response_function_mod
    )
    sys.modules["openai.types.responses.response_text_config_param"] = response_text_mod


_install_litellm_stub()
_install_openai_responses_stub()

from flaskr.api import llm

pytestmark = pytest.mark.no_mock_llm


class DummySpan:
    def __init__(self, trace_id="trace-1", span_id="span-1"):
        self.generation_args = None
        self.end_args = None
        self.trace_id = trace_id
        self.id = span_id

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


class FakeModelsResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_deepseek_model_loader_lists_models(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeModelsResponse(
            {
                "object": "list",
                "data": [
                    {"id": "deepseek-v4-flash", "object": "model"},
                    {"id": "deepseek-v4-pro", "object": "model"},
                ],
            }
        )

    monkeypatch.setattr(llm.requests, "get", fake_get)
    config = llm.ProviderConfig(
        key="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_API_URL",
        default_base_url="https://api.deepseek.com",
    )

    models = llm._load_deepseek_models(
        config,
        {"api_key": "test-key", "api_base": "https://api.deepseek.com"},
        "https://api.deepseek.com",
    )

    assert models == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert captured["url"] == "https://api.deepseek.com/models"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["timeout"] == 20


def test_deepseek_model_loader_falls_back_when_list_models_fails(monkeypatch):
    def fake_get(*args, **kwargs):
        _ = args, kwargs
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(llm.requests, "get", fake_get)
    config = llm.ProviderConfig(
        key="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_API_URL",
        default_base_url="https://api.deepseek.com",
    )

    models = llm._load_deepseek_models(
        config,
        {"api_key": "test-key", "api_base": "https://api.deepseek.com"},
        "https://api.deepseek.com",
    )

    assert models == llm.DEEPSEEK_FALLBACK_MODELS


def test_chat_llm_disables_deepseek_thinking(monkeypatch, app):
    captured_kwargs = {}

    def fake_completion(*args, **kwargs):
        captured_kwargs["kwargs"] = kwargs
        return iter([FakeResponse("chunk-1", content="Hi", finish_reason="stop")])

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    provider_state = llm.ProviderState(
        enabled=True,
        params={"api_key": "test-key", "api_base": "https://api.deepseek.com"},
        models=["deepseek-v4-pro"],
        prefix="",
        wildcard_prefixes=(),
        reload_params=llm._reload_deepseek_params,
    )
    monkeypatch.setattr(llm, "PROVIDER_STATES", {"deepseek": provider_state})
    monkeypatch.setattr(
        llm,
        "MODEL_ALIAS_MAP",
        {"deepseek-v4-pro": ("deepseek", "deepseek-v4-pro")},
    )
    monkeypatch.setattr(
        llm,
        "PROVIDER_CONFIG_HINTS",
        {"deepseek": "DEEPSEEK_API_KEY,DEEPSEEK_API_URL"},
    )

    list(
        llm.chat_llm(
            app=app,
            user_id="user-1",
            span=DummySpan(),
            model="deepseek-v4-pro",
            messages=[{"role": "user", "content": "hello"}],
            temperature="0.7",
            generation_name="deepseek-test",
        )
    )

    assert captured_kwargs["kwargs"]["temperature"] == 0.7
    assert captured_kwargs["kwargs"]["extra_body"] == {"thinking": {"type": "disabled"}}


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
    assert span.generation_args["trace_id"] == "trace-1"
    assert span.generation_args["parent_observation_id"] == "span-1"


def test_chat_llm_falls_back_to_request_trace_id(monkeypatch, app):
    def fake_completion(*args, **kwargs):
        _ = args, kwargs
        return iter([FakeResponse("chunk-1", content="Hi", finish_reason="stop")])

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
    monkeypatch.setattr(
        "flaskr.api.langfuse.get_request_trace_id", lambda: "request-trace-1"
    )

    span = DummySpan(trace_id="", span_id="span-2")
    list(
        llm.chat_llm(
            app=app,
            user_id="user-1",
            span=span,
            model="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
            generation_name="chat-fallback",
        )
    )

    assert span.generation_args["trace_id"] == "request-trace-1"
    assert span.generation_args["parent_observation_id"] == "span-2"
