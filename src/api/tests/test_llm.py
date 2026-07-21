# ruff: noqa: E402
import sys
import types
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = types.ModuleType("litellm")
    litellm_stub.model_cost = {}

    def register_model(model_map):
        litellm_stub.model_cost.update(model_map)

    litellm_stub.register_model = register_model
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
from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
)

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


def _create_credit_rate(
    *,
    rate_bid: str,
    provider: str,
    model: str,
    credits_per_unit: str,
    billing_metric: int = BILLING_METRIC_LLM_OUTPUT_TOKENS,
    usage_scene: int = BILL_USAGE_SCENE_PROD,
    unit_size: int = 1,
    effective_from: datetime = datetime(2026, 1, 1, 0, 0, 0),
) -> CreditUsageRate:
    return CreditUsageRate(
        rate_bid=rate_bid,
        usage_type=BILL_USAGE_TYPE_LLM,
        provider=provider,
        model=model,
        usage_scene=usage_scene,
        billing_metric=billing_metric,
        unit_size=unit_size,
        credits_per_unit=Decimal(credits_per_unit),
        rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
        effective_from=effective_from,
        effective_to=None,
        status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
    )


def _configure_model_list(monkeypatch):
    available_models = [
        "qwen/deepseek-v4-flash",
        "ark/doubao-seed-2-0-lite-260428",
        "qwen/no-rate-model",
    ]
    monkeypatch.setattr(
        llm,
        "PROVIDER_STATES",
        {
            "qwen": llm.ProviderState(
                enabled=True,
                params={"api_key": "qwen-key"},
                models=["qwen/deepseek-v4-flash", "qwen/no-rate-model"],
                prefix="qwen/",
                wildcard_prefixes=(),
            ),
            "ark": llm.ProviderState(
                enabled=True,
                params={"api_key": "ark-key"},
                models=["ark/doubao-seed-2-0-lite-260428"],
                prefix="ark/",
                wildcard_prefixes=(),
            ),
        },
    )
    monkeypatch.setattr(
        llm,
        "MODEL_ALIAS_MAP",
        {
            "qwen/deepseek-v4-flash": ("qwen", "deepseek-v4-flash"),
            "ark/doubao-seed-2-0-lite-260428": (
                "ark",
                "doubao-seed-2-0-lite-260428",
            ),
            "qwen/no-rate-model": ("qwen", "no-rate-model"),
        },
    )
    config = {
        "DEFAULT_LLM_MODEL": "qwen/deepseek-v4-flash",
        "LLM_ALLOWED_MODELS": ",".join(available_models),
        "LLM_ALLOWED_MODEL_DISPLAY_NAMES": (
            "DeepSeek-V4-Flash,Doubao-Seed-2.0-lite,No Rate"
        ),
    }
    monkeypatch.setattr(
        llm, "get_config", lambda key, default=None: config.get(key, default)
    )


def test_get_current_models_adds_output_token_credit_multiplier(monkeypatch, app):
    _configure_model_list(monkeypatch)
    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        db.session.add_all(
            [
                _create_credit_rate(
                    rate_bid="default-output",
                    provider="qwen",
                    model="qwen/deepseek-v4-flash",
                    credits_per_unit="0.000066667",
                ),
                _create_credit_rate(
                    rate_bid="doubao-provider-wildcard-output",
                    provider="ark",
                    model="*",
                    credits_per_unit="0.00001",
                ),
                _create_credit_rate(
                    rate_bid="doubao-input-ignored",
                    provider="ark",
                    model="ark/doubao-seed-2-0-lite-260428",
                    credits_per_unit="9",
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                ),
                _create_credit_rate(
                    rate_bid="doubao-cache-ignored",
                    provider="ark",
                    model="ark/doubao-seed-2-0-lite-260428",
                    credits_per_unit="8",
                    billing_metric=BILLING_METRIC_LLM_CACHE_TOKENS,
                ),
                _create_credit_rate(
                    rate_bid="doubao-debug-ignored",
                    provider="ark",
                    model="ark/doubao-seed-2-0-lite-260428",
                    credits_per_unit="7",
                    usage_scene=BILL_USAGE_SCENE_DEBUG,
                ),
                _create_credit_rate(
                    rate_bid="doubao-preview-ignored",
                    provider="ark",
                    model="ark/doubao-seed-2-0-lite-260428",
                    credits_per_unit="6",
                    usage_scene=BILL_USAGE_SCENE_PREVIEW,
                ),
                _create_credit_rate(
                    rate_bid="doubao-output",
                    provider="ark",
                    model="ark/doubao-seed-2-0-lite-260428",
                    credits_per_unit="0.00018",
                ),
            ]
        )
        db.session.commit()

        models = llm.get_current_models(app)

        db.session.query(CreditUsageRate).delete()
        db.session.commit()

    by_model = {item["model"]: item for item in models}
    assert by_model["qwen/deepseek-v4-flash"]["credit_multiplier"] == 1
    assert by_model["qwen/deepseek-v4-flash"]["credit_multiplier_label"] == "1x"
    assert by_model["qwen/deepseek-v4-flash"]["is_default"] is True
    assert by_model["ark/doubao-seed-2-0-lite-260428"]["credit_multiplier"] == 3
    assert (
        by_model["ark/doubao-seed-2-0-lite-260428"]["credit_multiplier_label"] == "2.7x"
    )
    assert by_model["qwen/no-rate-model"]["credit_multiplier"] is None
    assert by_model["qwen/no-rate-model"]["credit_multiplier_label"] is None
    assert by_model["ark/doubao-seed-2-0-lite-260428"]["display_name"] == (
        "Doubao-Seed-2.0-lite"
    )


def test_get_current_models_uses_stable_default_multiplier_anchor(monkeypatch, app):
    _configure_model_list(monkeypatch)
    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        db.session.add_all(
            [
                _create_credit_rate(
                    rate_bid="default-original-output",
                    provider="qwen",
                    model="qwen/deepseek-v4-flash",
                    credits_per_unit="0.000066667",
                    effective_from=datetime(2026, 1, 1, 0, 0, 0),
                ),
                _create_credit_rate(
                    rate_bid="default-edited-output",
                    provider="qwen",
                    model="qwen/deepseek-v4-flash",
                    credits_per_unit="0.000466669",
                    effective_from=datetime(2026, 2, 1, 0, 0, 0),
                ),
            ]
        )
        db.session.commit()

        models = llm.get_current_models(app)

        db.session.query(CreditUsageRate).delete()
        db.session.commit()

    by_model = {item["model"]: item for item in models}
    assert by_model["qwen/deepseek-v4-flash"]["credit_multiplier"] == pytest.approx(7)
    assert by_model["qwen/deepseek-v4-flash"]["credit_multiplier_label"] == "7x"
    assert by_model["qwen/deepseek-v4-flash"]["is_default"] is True


def test_get_current_models_keeps_list_when_credit_rate_lookup_fails(monkeypatch, app):
    _configure_model_list(monkeypatch)

    def raise_lookup(_app):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(llm, "_load_llm_output_rate_rows", raise_lookup)

    models = llm.get_current_models(app)

    assert [item["model"] for item in models] == [
        "qwen/deepseek-v4-flash",
        "ark/doubao-seed-2-0-lite-260428",
        "qwen/no-rate-model",
    ]
    assert all(item["credit_multiplier"] is None for item in models)


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


def test_qwen_prefixed_model_routes_without_fetched_alias(monkeypatch, app):
    captured = {}

    def fake_completion(model, *args, **kwargs):
        captured["model"] = model
        captured["kwargs"] = kwargs
        return iter([FakeResponse("chunk-1", content="ok", finish_reason="stop")])

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    provider_state = llm.ProviderState(
        enabled=True,
        params={"api_key": "test-key", "api_base": "https://example.com"},
        models=[],
        prefix=llm.QWEN_PREFIX,
        wildcard_prefixes=(llm.QWEN_PREFIX,),
        reload_params=llm._reload_qwen_params,
    )
    monkeypatch.setattr(llm, "PROVIDER_STATES", {"qwen": provider_state})
    monkeypatch.setattr(llm, "MODEL_ALIAS_MAP", {})
    monkeypatch.setattr(
        llm,
        "MODEL_MAX_OUTPUT_TOKENS",
        {"qwen/deepseek-v4-flash": 393216},
    )
    monkeypatch.setattr(
        llm,
        "PROVIDER_CONFIG_HINTS",
        {"qwen": "QWEN_API_KEY,QWEN_API_URL"},
    )

    responses = list(
        llm.chat_llm(
            app=app,
            user_id="user-1",
            span=DummySpan(),
            model="qwen/deepseek-v4-flash",
            messages=[{"role": "user", "content": "hello"}],
            temperature="0.7",
            generation_name="qwen-test",
        )
    )

    assert [resp.result for resp in responses] == ["ok"]
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["kwargs"]["temperature"] == 0.7
    assert captured["kwargs"]["extra_body"] == {"enable_thinking": False}
    assert captured["kwargs"]["max_tokens"] == 393216


def test_load_and_register_model_max_output_tokens(monkeypatch):
    configured = {
        "qwen/deepseek-v4-flash": 393216,
        "ark/doubao-seed-2-0-lite-260428": 131072,
    }
    captured = {}

    monkeypatch.setattr(
        llm,
        "get_config",
        lambda key, default=None: (
            configured if key == "LLM_MODEL_MAX_OUTPUT_TOKENS" else default
        ),
    )
    monkeypatch.setattr(
        llm.litellm,
        "register_model",
        lambda model_map: captured.update(model_map),
        raising=False,
    )

    limits = llm._load_and_register_model_max_output_tokens()

    assert limits == configured
    assert captured == {
        "qwen/deepseek-v4-flash": {"max_output_tokens": 393216},
        "ark/doubao-seed-2-0-lite-260428": {"max_output_tokens": 131072},
    }


def test_load_model_max_output_tokens_ignores_invalid_config(monkeypatch):
    monkeypatch.setattr(
        llm,
        "get_config",
        lambda key, default=None: (
            '{"qwen/model": 0}' if key == "LLM_MODEL_MAX_OUTPUT_TOKENS" else default
        ),
    )
    monkeypatch.setattr(
        llm.litellm,
        "register_model",
        lambda _model_map: pytest.fail("invalid limits must not be registered"),
        raising=False,
    )

    assert llm._load_and_register_model_max_output_tokens() == {}


def test_stream_litellm_completion_falls_back_to_litellm_limit(monkeypatch, app):
    captured = {}
    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {})
    monkeypatch.setattr(llm.litellm, "get_max_tokens", lambda model: 8192)
    monkeypatch.setattr(
        llm.litellm,
        "completion",
        lambda *args, **kwargs: captured.update(kwargs) or iter([]),
    )

    list(
        llm._stream_litellm_completion(
            app,
            "openai/gpt-test",
            "gpt-test",
            [],
            {},
            {},
        )
    )

    assert captured["max_tokens"] == 8192


@pytest.mark.parametrize(
    ("requested_max_tokens", "expected_max_tokens"),
    [(None, 131072), (4096, 4096), (200000, 131072)],
)
def test_stream_litellm_completion_applies_configured_limit_as_ceiling(
    monkeypatch,
    app,
    requested_max_tokens,
    expected_max_tokens,
):
    captured = {}
    monkeypatch.setattr(
        llm,
        "MODEL_MAX_OUTPUT_TOKENS",
        {"ark/doubao-seed-2-0-lite-260428": 131072},
    )
    monkeypatch.setattr(
        llm.litellm,
        "completion",
        lambda *args, **kwargs: captured.update(kwargs) or iter([]),
    )
    kwargs = {}
    if requested_max_tokens is not None:
        kwargs["max_tokens"] = requested_max_tokens

    list(
        llm._stream_litellm_completion(
            app,
            "ark/doubao-seed-2-0-lite-260428",
            "doubao-seed-2-0-lite-260428",
            [],
            {},
            kwargs,
        )
    )

    assert captured["max_tokens"] == expected_max_tokens


def test_stream_litellm_completion_omits_unknown_limit(monkeypatch, app):
    captured = {}

    def raise_unknown(_model):
        raise ValueError("unknown model")

    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {})
    monkeypatch.setattr(llm.litellm, "get_max_tokens", raise_unknown)
    monkeypatch.setattr(
        llm.litellm,
        "completion",
        lambda *args, **kwargs: captured.update(kwargs) or iter([]),
    )

    list(
        llm._stream_litellm_completion(
            app,
            "qwen/unknown-model",
            "unknown-model",
            [],
            {},
            {},
        )
    )

    assert "max_tokens" not in captured


def test_qwen_provider_config_keeps_prefix_fallback():
    qwen_config = next(
        config for config in llm.LITELLM_PROVIDER_CONFIGS if config.key == "qwen"
    )

    assert qwen_config.wildcard_prefixes == (llm.QWEN_PREFIX,)


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


def test_gemini_params_use_minimal_reasoning_with_explicit_allowlist():
    params = llm._reload_gemini_params("gemini-3.1-flash-lite", 0.3)

    assert params == {
        "temperature": 0.3,
        "allowed_openai_params": ["reasoning_effort"],
        "reasoning_effort": "minimal",
    }


def test_gemini_25_pro_params_use_lowest_supported_reasoning():
    params = llm._reload_gemini_params("gemini-2.5-pro", 0.3)

    assert params["allowed_openai_params"] == ["reasoning_effort"]
    assert params["reasoning_effort"] == "low"


def test_chat_llm_ends_partial_response_on_repeated_stream_chunk(monkeypatch, app):
    class RepeatedChunkError(Exception):
        __module__ = "litellm.exceptions"

    def fake_completion(*args, **kwargs):
        yield FakeResponse("chunk-1", content="你好")
        raise RepeatedChunkError("The model is repeating the same chunk = ！ ！ .")

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm, "record_llm_usage", lambda *args, **kwargs: None)
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

    responses = list(
        llm.chat_llm(
            app=app,
            user_id="user-1",
            span=DummySpan(),
            model="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
            generation_name="chat-test",
        )
    )

    assert [resp.result for resp in responses] == ["你好"]


def test_chat_llm_streams(monkeypatch, app):
    captured_kwargs = {}
    captured_usage = {}

    def fake_completion(*args, **kwargs):
        captured_kwargs["kwargs"] = kwargs
        chunks = [
            FakeResponse("chunk-1", content="Hi "),
            FakeResponse("chunk-2", content="there", finish_reason="stop"),
        ]
        return iter(chunks)

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    monkeypatch.setattr(
        llm,
        "record_llm_usage",
        lambda *args, **kwargs: captured_usage.update(kwargs),
    )
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
    assert captured_usage["extra"]["output_text"] == "Hi there"


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
