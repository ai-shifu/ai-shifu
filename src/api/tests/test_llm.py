# ruff: noqa: E402
"""Verify visible LLM models include stable credit-rate metadata."""

import importlib.metadata
import json
import os
import subprocess
import sys
import textwrap
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

    def register_model(model_map: object):
        litellm_stub.model_cost.update(model_map)

    def get_model_info(*args: object, **kwargs: object):
        _ = args, kwargs
        message = "unknown model"
        raise ValueError(message)

    litellm_stub.register_model = register_model
    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.get_model_info = get_model_info
    litellm_stub.completion = lambda *_args, **_kwargs: iter([])
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
    response_function_mod.ResponseFunctionToolCall = response_function_tool_call
    response_text_mod.ResponseTextConfigParam = response_text_config
    responses_pkg.ResponseFunctionToolCall = response_function_tool_call

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
from flaskr.service.common import credit_rate_references
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
)

pytestmark = pytest.mark.no_mock_llm


class DummySpan:
    """Simulate span behavior for tests."""

    def __init__(
        self, trace_id: object = "trace-1", span_id: object = "span-1"
    ) -> None:
        """Capture span calls alongside fixed trace and span identifiers."""
        self.generation_args = None
        self.end_args = None
        self.trace_id = trace_id
        self.id = span_id

    def generation(self, **kwargs: object):
        self.generation_args = kwargs
        return self

    def end(self, **kwargs: object):
        self.end_args = kwargs

    def update(self, **kwargs: object):
        self.update_args = kwargs


class FakeResponse:
    """Simulate response behavior for tests."""

    def __init__(
        self,
        chunk_id: object,
        content: object = None,
        finish_reason: object = None,
        usage: object = None,
        reasoning_content: object = None,
    ) -> None:
        """Capture streamed content, finish state, reasoning, and usage."""
        self.id = chunk_id
        delta = SimpleNamespace(
            content=content,
            reasoning_content=reasoning_content,
        )
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]
        self.usage = usage


class FakeModelsResponse:
    """Simulate models response behavior for tests."""

    def __init__(self, payload: object) -> None:
        """Capture the payload returned by the fake models endpoint."""
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


def _configure_model_list(monkeypatch: object):
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
        "LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS": "0.066667",
        "LLM_ALLOWED_MODELS": ",".join(available_models),
        "LLM_ALLOWED_MODEL_DISPLAY_NAMES": (
            "DeepSeek-V4-Flash,Doubao-Seed-2.0-lite,No Rate"
        ),
    }
    monkeypatch.setattr(
        llm, "get_config", lambda key, default=None: config.get(key, default)
    )
    monkeypatch.setattr(
        credit_rate_references,
        "get_config",
        lambda key, default=None: config.get(key, default),
    )


def test_get_current_models_adds_output_token_credit_multiplier(
    monkeypatch: object, app: object
):
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
                    credits_per_unit="0.0001800009",
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


def test_get_current_models_uses_fixed_credit_1x_anchor(
    monkeypatch: object, app: object
):
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
                _create_credit_rate(
                    rate_bid="doubao-output",
                    provider="ark",
                    model="ark/doubao-seed-2-0-lite-260428",
                    credits_per_unit="0.0001800009",
                    effective_from=datetime(2026, 1, 1, 0, 0, 0),
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
    assert (
        by_model["ark/doubao-seed-2-0-lite-260428"]["credit_multiplier_label"] == "2.7x"
    )


def test_get_current_models_hides_multiplier_when_credit_1x_anchor_missing(
    monkeypatch: object, app: object
):
    _configure_model_list(monkeypatch)
    missing_anchor_config = {
        "DEFAULT_LLM_MODEL": "qwen/deepseek-v4-flash",
        "LLM_ALLOWED_MODELS": (
            "qwen/deepseek-v4-flash,ark/doubao-seed-2-0-lite-260428"
        ),
    }
    monkeypatch.setattr(
        llm,
        "get_config",
        lambda key, default=None: missing_anchor_config.get(key, default),
    )
    monkeypatch.setattr(
        credit_rate_references,
        "get_config",
        lambda key, default=None: missing_anchor_config.get(key, default),
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        db.session.add(
            _create_credit_rate(
                rate_bid="default-output",
                provider="qwen",
                model="qwen/deepseek-v4-flash",
                credits_per_unit="0.000066667",
            )
        )
        db.session.commit()

        models = llm.get_current_models(app)

        db.session.query(CreditUsageRate).delete()
        db.session.commit()

    assert all(item["credit_multiplier"] is None for item in models)
    assert all(item.get("credit_multiplier_label") is None for item in models)


def test_get_current_models_keeps_list_when_credit_rate_lookup_fails(
    monkeypatch: object, app: object
):
    _configure_model_list(monkeypatch)

    def raise_lookup(_app: object):
        message = "db unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(llm, "_load_llm_output_rate_rows", raise_lookup)

    models = llm.get_current_models(app)

    assert [item["model"] for item in models] == [
        "qwen/deepseek-v4-flash",
        "ark/doubao-seed-2-0-lite-260428",
        "qwen/no-rate-model",
    ]
    assert all(item["credit_multiplier"] is None for item in models)


def test_deepseek_model_loader_lists_models(monkeypatch: object):
    captured = {}

    def fake_get(url: object, headers: object = None, timeout: object = None):
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


def test_deepseek_model_loader_falls_back_when_list_models_fails(monkeypatch: object):
    def fake_get(*args: object, **kwargs: object):
        _ = args, kwargs
        message = "network unavailable"
        raise RuntimeError(message)

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


def test_qwen_prefixed_model_routes_without_fetched_alias(
    monkeypatch: object, app: object
):
    captured = {}

    def fake_completion(model: object, *args: object, **kwargs: object):
        _ = args
        captured["model"] = model
        captured["kwargs"] = kwargs
        return iter([FakeResponse("chunk-1", content="ok", finish_reason="stop")])

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)

    def reload_qwen_params(model_id: object, temperature: object):
        captured["reload_model"] = model_id
        return llm._reload_qwen_params(model_id, temperature)

    provider_state = llm.ProviderState(
        enabled=True,
        params={"api_key": "test-key", "api_base": "https://example.com"},
        models=[],
        prefix=llm.QWEN_PREFIX,
        wildcard_prefixes=(llm.QWEN_PREFIX,),
        reload_params=reload_qwen_params,
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
    assert captured["reload_model"] == "deepseek-v4-flash"
    assert captured["kwargs"]["temperature"] == 0.7
    assert captured["kwargs"]["extra_body"] == {"enable_thinking": False}
    assert captured["kwargs"]["max_tokens"] == 393216


def test_load_and_register_model_max_output_tokens(monkeypatch: object):
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
        captured.update,
        raising=False,
    )

    limits = llm._load_and_register_model_max_output_tokens()

    assert limits == configured
    assert captured == {
        "qwen/deepseek-v4-flash": {"max_output_tokens": 393216},
        "ark/doubao-seed-2-0-lite-260428": {"max_output_tokens": 131072},
    }


def test_load_model_max_output_tokens_ignores_invalid_config(monkeypatch: object):
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


def test_stream_litellm_completion_falls_back_to_litellm_limit(
    monkeypatch: object, app: object
):
    captured = {}
    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {})
    monkeypatch.setattr(llm.litellm, "get_max_tokens", lambda _model: 8192)
    monkeypatch.setattr(
        llm.litellm,
        "completion",
        lambda *_args, **kwargs: captured.update(kwargs) or iter([]),
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
    monkeypatch: object,
    app: object,
    requested_max_tokens: object,
    expected_max_tokens: object,
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
        lambda *_args, **kwargs: captured.update(kwargs) or iter([]),
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


def test_stream_litellm_completion_omits_unknown_limit(
    monkeypatch: object, app: object
):
    captured = {}

    def raise_unknown(_model: object):
        message = "unknown model"
        raise ValueError(message)

    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {})
    monkeypatch.setattr(llm.litellm, "get_max_tokens", raise_unknown)
    monkeypatch.setattr(
        llm.litellm,
        "completion",
        lambda *_args, **kwargs: captured.update(kwargs) or iter([]),
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
    assert qwen_config.custom_llm_provider == "dashscope"


@pytest.mark.parametrize(
    ("provider_key", "expected_litellm_provider"),
    [
        ("deepseek", "deepseek"),
        ("qwen", "dashscope"),
        ("ark", "volcengine"),
        ("glm", "zai"),
        ("silicon", "openai"),
        ("ernie_v2", "openai"),
    ],
)
def test_provider_configs_use_expected_litellm_adapters(
    provider_key: object,
    expected_litellm_provider: object,
):
    provider_config = next(
        config for config in llm.LITELLM_PROVIDER_CONFIGS if config.key == provider_key
    )

    assert provider_config.custom_llm_provider == expected_litellm_provider


@pytest.mark.parametrize(
    ("model_info", "expected_effort", "expected_temperature"),
    [
        ({"supports_none_reasoning_effort": True}, "none", 0.4),
        (
            {
                "supports_none_reasoning_effort": False,
                "supports_minimal_reasoning_effort": True,
            },
            "minimal",
            1,
        ),
        (
            {
                "supports_none_reasoning_effort": False,
                "supports_minimal_reasoning_effort": False,
                "supports_low_reasoning_effort": True,
            },
            "low",
            1,
        ),
        (
            {
                "supports_none_reasoning_effort": False,
                "supports_minimal_reasoning_effort": False,
                "supports_low_reasoning_effort": False,
            },
            "medium",
            1,
        ),
    ],
)
def test_openai_params_use_litellm_reasoning_capabilities(
    monkeypatch: object,
    model_info: object,
    expected_effort: object,
    expected_temperature: object,
):
    captured = {}

    def fake_get_model_info(*, model: object, custom_llm_provider: object):
        captured["model"] = model
        captured["custom_llm_provider"] = custom_llm_provider
        return model_info

    monkeypatch.setattr(llm.litellm, "get_model_info", fake_get_model_info)

    params = llm._reload_openai_params("gpt-5.6-luna", 0.4)

    assert params == {
        "reasoning_effort": expected_effort,
        "temperature": expected_temperature,
    }
    assert captured == {
        "model": "gpt-5.6-luna",
        "custom_llm_provider": "openai",
    }


def test_openai_params_fall_back_to_existing_policy_for_unknown_model(
    monkeypatch: object,
):
    def raise_unknown(*args: object, **kwargs: object):
        _ = args, kwargs
        message = "unknown model"
        raise ValueError(message)

    monkeypatch.setattr(llm.litellm, "get_model_info", raise_unknown)

    assert llm._reload_openai_params("gpt-5-custom", 0.4) == {
        "reasoning_effort": "minimal",
        "temperature": 1,
    }


def test_openai_params_fall_back_when_capability_metadata_is_partial(
    monkeypatch: object,
):
    monkeypatch.setattr(
        llm.litellm,
        "get_model_info",
        lambda *_args, **_kwargs: {"supports_none_reasoning_effort": False},
    )

    assert llm._reload_openai_params("gpt-5.2-custom", 0.4) == {
        "reasoning_effort": "none",
        "temperature": 0.4,
    }


@pytest.mark.parametrize(
    "model_id",
    ["glm-4.5", "glm-4.6-air", "glm-4.7-flash", "glm-5.2"],
)
def test_glm_params_disable_thinking_for_supported_models(model_id: object):
    params = llm._reload_glm_params(model_id, 0.4)

    assert params == {
        "temperature": 0.4,
        "allowed_openai_params": ["response_format", "thinking"],
        "extra_body": {"thinking": {"type": "disabled"}},
    }


def test_glm_params_leave_legacy_models_unchanged():
    params = llm._reload_glm_params("glm-4-plus", 0.4)

    assert params == {
        "temperature": 0.4,
        "allowed_openai_params": ["response_format"],
    }


def test_provider_specific_thinking_params_remain_compatible():
    assert llm._reload_qwen_params("qwen-max", 0.4)["extra_body"] == {
        "enable_thinking": False
    }
    assert llm._reload_silicon_params("deepseek-ai/DeepSeek-V3", 0.4)["extra_body"] == {
        "enable_thinking": False
    }
    assert llm._reload_ark_params("doubao-seed", 0.4)["thinking"] == {
        "type": "disabled"
    }
    assert llm._reload_ark_params("doubao-seed", 0.4)["allowed_openai_params"] == [
        "response_format"
    ]


def test_provider_thinking_policy_removes_caller_conflicts():
    kwargs = {
        "reasoning_effort": "high",
        "thinking": {"type": "enabled"},
        "enable_thinking": True,
        "extra_body": {
            "thinking": {"type": "enabled"},
            "enable_thinking": True,
            "custom_field": "keep",
        },
    }

    llm._apply_provider_params(
        kwargs,
        {"reasoning_effort": "none", "temperature": 0.4},
    )

    assert kwargs == {
        "reasoning_effort": "none",
        "temperature": 0.4,
        "extra_body": {"custom_field": "keep"},
    }


@pytest.mark.parametrize(
    ("generation_config_key", "thinking_config_key", "top_k_key"),
    [
        ("generationConfig", "thinkingConfig", "topK"),
        ("generation_config", "thinking_config", "top_k"),
    ],
)
def test_gemini_thinking_policy_removes_nested_caller_override(
    generation_config_key: object,
    thinking_config_key: object,
    top_k_key: object,
):
    kwargs = {
        "extra_body": {
            generation_config_key: {
                thinking_config_key: {"thinkingLevel": "high"},
                top_k_key: 8,
            },
            "custom_field": "keep",
        },
    }

    llm._apply_provider_params(
        kwargs,
        llm._reload_gemini_params("gemini-3.6-flash", 0.4),
    )

    assert kwargs == {
        "temperature": 0.4,
        "reasoning_effort": "none",
        "allowed_openai_params": ["reasoning_effort"],
        "extra_body": {
            "generationConfig": {top_k_key: 8},
            "custom_field": "keep",
        },
    }


@pytest.mark.parametrize("generation_config_key", llm._GEMINI_GENERATION_CONFIG_KEYS)
def test_gemini_thinking_policy_removes_invalid_native_config(
    generation_config_key: object,
):
    kwargs = {
        "extra_body": {
            generation_config_key: None,
            "custom_field": "keep",
        },
    }

    llm._apply_provider_params(
        kwargs,
        llm._reload_gemini_params("gemini-3.6-flash", 0.4),
    )

    assert kwargs["extra_body"] == {"custom_field": "keep"}


def test_gemini_thinking_policy_normalizes_generation_config_aliases():
    kwargs = {
        "extra_body": {
            "generation_config": {
                "thinking_config": {"thinking_level": "high"},
                "top_k": 4,
            },
            "generationConfig": {
                "thinkingConfig": {"thinkingLevel": "high"},
                "topK": 8,
            },
        },
    }

    llm._apply_provider_params(
        kwargs,
        llm._reload_gemini_params("gemini-3.6-flash", 0.4),
    )

    assert kwargs["extra_body"] == {
        "generationConfig": {
            "top_k": 4,
            "topK": 8,
        },
    }


def test_provider_thinking_policy_preserves_caller_extra_body_fields():
    kwargs = {
        "extra_body": {
            "enable_thinking": True,
            "custom_field": "keep",
        },
    }

    llm._apply_provider_params(
        kwargs,
        llm._reload_qwen_params("qwen-max", 0.4),
    )

    assert kwargs == {
        "temperature": 0.4,
        "extra_body": {
            "enable_thinking": False,
            "custom_field": "keep",
        },
    }


LITELLM_CONTRACT_VERSION = "1.95.0"


def _installed_litellm_version() -> str | None:
    try:
        return importlib.metadata.version("litellm")
    except importlib.metadata.PackageNotFoundError:
        return None


@pytest.mark.skipif(
    _installed_litellm_version() != LITELLM_CONTRACT_VERSION,
    reason=(
        "contract test targets litellm=="
        f"{LITELLM_CONTRACT_VERSION}, found "
        f"{_installed_litellm_version() or 'no litellm distribution'}; "
        "install requirements.txt to run it"
    ),
)
def test_litellm_195_native_adapter_contracts():
    script = textwrap.dedent(
        """
        import importlib.metadata
        import json

        import httpx
        import litellm
        from openai import OpenAI
        from litellm.llms.custom_httpx.http_handler import HTTPHandler

        messages = [{"role": "user", "content": "hello"}]
        sse_events = [
            {
                "id": "chatcmpl-contract",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "contract-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "Hello"},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "chatcmpl-contract",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "contract-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": " world"},
                        "finish_reason": "stop",
                    }
                ],
            },
            {
                "id": "chatcmpl-contract",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "contract-model",
                "choices": [],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            },
        ]
        sse_payload = (
            "".join(f"data: {json.dumps(event)}\\n\\n" for event in sse_events)
            + "data: [DONE]\\n\\n"
        ).encode()

        def adapter_contract(provider, model, api_base, provider_kwargs):
            captured = []

            def respond(request):
                captured.append(
                    {
                        "url": str(request.url),
                        "body": json.loads(request.content.decode()),
                    }
                )
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=sse_payload,
                    request=request,
                )

            http_client = httpx.Client(
                transport=httpx.MockTransport(respond),
                trust_env=False,
            )
            # DeepSeek uses LiteLLM's native HTTP handler. The other adapters
            # currently route their transformed request through the OpenAI SDK.
            client = (
                HTTPHandler(client=http_client)
                if provider == "deepseek"
                else OpenAI(
                    api_key="test-key",
                    base_url=api_base,
                    http_client=http_client,
                )
            )
            chunks = list(
                litellm.completion(
                    model=model,
                    custom_llm_provider=provider,
                    api_base=api_base,
                    api_key="test-key",
                    client=client,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                    temperature=0.4,
                    **provider_kwargs,
                )
            )
            content = "".join(
                chunk.choices[0].delta.content or ""
                for chunk in chunks
                if chunk.choices
            )
            usage_chunks = [
                chunk.usage
                for chunk in chunks
                if getattr(chunk, "usage", None) is not None
            ]
            assert len(captured) == 1
            assert len(usage_chunks) == 1
            return {
                **captured[0],
                "content": content,
                "usage": {
                    "prompt_tokens": usage_chunks[0].prompt_tokens,
                    "completion_tokens": usage_chunks[0].completion_tokens,
                    "total_tokens": usage_chunks[0].total_tokens,
                },
            }

        contracts = {
            "version": importlib.metadata.version("litellm"),
            "deepseek": adapter_contract(
                "deepseek",
                "deepseek-v4-pro",
                "https://api.deepseek.com",
                {"reasoning_effort": "none"},
            ),
            "dashscope": adapter_contract(
                "dashscope",
                "deepseek-v3",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
                {"extra_body": {"enable_thinking": False}},
            ),
            "volcengine": adapter_contract(
                "volcengine",
                "doubao-seed-2-0-lite-260428",
                "https://ark.cn-beijing.volces.com/api/v3",
                {
                    "thinking": {"type": "disabled"},
                    "allowed_openai_params": ["response_format"],
                    "response_format": {"type": "json_object"},
                },
            ),
            "zai": adapter_contract(
                "zai",
                "glm-5.2",
                "https://open.bigmodel.cn/api/paas/v4",
                {
                    "extra_body": {"thinking": {"type": "disabled"}},
                    "allowed_openai_params": ["thinking", "response_format"],
                    "response_format": {"type": "json_object"},
                },
            ),
            "gemini_3": litellm.get_optional_params(
                model="gemini-3.6-flash",
                custom_llm_provider="gemini",
                reasoning_effort="none",
                allowed_openai_params=["reasoning_effort"],
            ),
            "gemini_25_pro": litellm.get_optional_params(
                model="gemini-2.5-pro",
                custom_llm_provider="gemini",
                reasoning_effort="minimal",
                allowed_openai_params=["reasoning_effort"],
            ),
            "gemini_25_flash": litellm.get_optional_params(
                model="gemini-2.5-flash",
                custom_llm_provider="gemini",
                reasoning_effort="none",
                allowed_openai_params=["reasoning_effort"],
            ),
            "max_tokens": {
                model: litellm.get_max_tokens(model)
                for model in (
                    "gpt-5.6-luna",
                    "gemini-3.6-flash",
                    "deepseek-v4-pro",
                    "deepseek-v4-flash",
                )
            },
        }
        print(json.dumps(contracts, sort_keys=True))
        """
    )
    env = os.environ.copy()
    env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        env=env,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    contracts = json.loads(completed.stdout.strip().splitlines()[-1])
    assert contracts["version"] == "1.95.0"

    expected_urls = {
        "deepseek": "https://api.deepseek.com/chat/completions",
        "dashscope": (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        ),
        "volcengine": ("https://ark.cn-beijing.volces.com/api/v3/chat/completions"),
        "zai": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    }
    for provider, expected_url in expected_urls.items():
        body = contracts[provider]["body"]
        assert contracts[provider]["url"] == expected_url
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert contracts[provider]["content"] == "Hello world"
        assert contracts[provider]["usage"] == {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
        }

    assert contracts["deepseek"]["body"]["thinking"] == {"type": "disabled"}
    assert contracts["dashscope"]["body"]["enable_thinking"] is False
    assert contracts["volcengine"]["body"]["thinking"] == {"type": "disabled"}
    assert contracts["volcengine"]["body"]["response_format"] == {"type": "json_object"}
    assert contracts["zai"]["body"]["thinking"] == {"type": "disabled"}
    assert contracts["zai"]["body"]["response_format"] == {"type": "json_object"}

    assert contracts["gemini_3"]["thinkingConfig"] == {
        "thinkingLevel": "minimal",
        "includeThoughts": False,
    }
    assert contracts["gemini_25_pro"]["thinkingConfig"] == {
        "thinkingBudget": 128,
        "includeThoughts": True,
    }
    assert contracts["gemini_25_flash"]["thinkingConfig"] == {
        "thinkingBudget": 0,
        "includeThoughts": False,
    }
    assert contracts["max_tokens"] == {
        "gpt-5.6-luna": 128000,
        "gemini-3.6-flash": 65536,
        "deepseek-v4-pro": 8192,
        "deepseek-v4-flash": 8192,
    }


def test_chat_llm_disables_deepseek_thinking(monkeypatch: object, app: object):
    captured_kwargs = {}

    def fake_completion(*args: object, **kwargs: object):
        _ = args
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
            reasoning_effort="high",
            thinking={"type": "enabled"},
            extra_body={
                "thinking": {"type": "enabled"},
                "custom_field": "keep",
            },
            generation_name="deepseek-test",
        )
    )

    assert captured_kwargs["kwargs"]["temperature"] == 0.7
    assert captured_kwargs["kwargs"]["reasoning_effort"] == "none"
    assert "thinking" not in captured_kwargs["kwargs"]
    assert captured_kwargs["kwargs"]["extra_body"] == {"custom_field": "keep"}


def test_gemini_3_params_use_none_with_explicit_allowlist():
    params = llm._reload_gemini_params("gemini-3.1-flash-lite", 0.3)

    assert params == {
        "temperature": 0.3,
        "allowed_openai_params": ["reasoning_effort"],
        "reasoning_effort": "none",
    }


def test_gemini_25_pro_params_use_lowest_supported_reasoning():
    params = llm._reload_gemini_params("gemini-2.5-pro", 0.3)

    assert params["allowed_openai_params"] == ["reasoning_effort"]
    assert params["reasoning_effort"] == "minimal"


def test_invoke_llm_uses_actual_model_for_provider_params(
    monkeypatch: object, app: object
):
    captured = {}

    def reload_params(model_id: object, temperature: object):
        captured["reload_model"] = model_id
        return {"temperature": temperature}

    def fake_completion(model: object, *args: object, **kwargs: object):
        _ = args
        captured["completion_model"] = model
        captured["completion_kwargs"] = kwargs
        return iter([FakeResponse("chunk-1", content="ok", finish_reason="stop")])

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm, "record_llm_usage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        llm,
        "PROVIDER_STATES",
        {
            "test": llm.ProviderState(
                enabled=True,
                params={"api_key": "test-key"},
                models=["display-model"],
                reload_params=reload_params,
            )
        },
    )
    monkeypatch.setattr(
        llm,
        "MODEL_ALIAS_MAP",
        {"display-model": ("test", "actual-model")},
    )
    monkeypatch.setattr(llm, "PROVIDER_CONFIG_HINTS", {"test": "TEST_API_KEY"})

    responses = list(
        llm.invoke_llm(
            app=app,
            user_id="user-1",
            span=DummySpan(),
            model="display-model",
            message="hello",
            temperature="0.4",
            generation_name="invoke-model-test",
        )
    )

    assert [response.result for response in responses] == ["ok"]
    assert captured["reload_model"] == "actual-model"
    assert captured["completion_model"] == "actual-model"
    assert captured["completion_kwargs"]["temperature"] == 0.4


def test_chat_llm_ends_partial_response_on_repeated_stream_chunk(
    monkeypatch: object, app: object
):
    class RepeatedChunkError(Exception):
        __module__ = "litellm.exceptions"

    def fake_completion(*args: object, **kwargs: object):
        _ = (args, kwargs)
        yield FakeResponse("chunk-1", content="你好")
        message = "The model is repeating the same chunk = ！ ！ ."
        raise RepeatedChunkError(message)

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm, "record_llm_usage", lambda *_args, **_kwargs: None)
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


def test_chat_llm_streams(monkeypatch: object, app: object):
    captured_kwargs = {}
    captured_usage = {}

    def fake_completion(*args: object, **kwargs: object):
        _ = args
        captured_kwargs["kwargs"] = kwargs
        chunks = [
            FakeResponse("chunk-1", content="Hi "),
            FakeResponse("chunk-2", content="there", finish_reason="stop"),
            SimpleNamespace(
                id="usage",
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=3,
                    completion_tokens=2,
                    total_tokens=5,
                ),
            ),
        ]
        return iter(chunks)

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    monkeypatch.setattr(
        llm,
        "record_llm_usage",
        lambda *_args, **kwargs: captured_usage.update(kwargs),
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
    assert captured_kwargs["kwargs"]["stream_options"] == {"include_usage": True}
    assert span.generation_args["name"] == "chat-test"
    assert span.generation_args["trace_id"] == "trace-1"
    assert span.generation_args["parent_observation_id"] == "span-1"
    assert captured_usage["input"] == 3
    assert captured_usage["output"] == 2
    assert captured_usage["total"] == 5
    assert span.end_args["output"] == "Hi there"
    assert captured_usage["extra"]["output_text"] == "Hi there"


@pytest.mark.parametrize("llm_method", ["invoke_llm", "chat_llm"])
def test_llm_sends_reasoning_output_to_langfuse_without_streaming_it(
    monkeypatch: object, app: object, llm_method: object
):
    def fake_completion(*args: object, **kwargs: object):
        _ = args, kwargs
        return iter(
            [
                FakeResponse("chunk-1", reasoning_content="Think "),
                FakeResponse(
                    "chunk-2",
                    content="The answer",
                    reasoning_content="carefully.",
                    finish_reason="stop",
                ),
            ]
        )

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm, "record_llm_usage", lambda *_args, **_kwargs: None)
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
    common_kwargs = {
        "app": app,
        "user_id": "user-1",
        "span": span,
        "model": "gpt-test",
        "generation_name": "reasoning-test",
    }
    if llm_method == "invoke_llm":
        responses = list(llm.invoke_llm(message="hello", **common_kwargs))
    else:
        responses = list(
            llm.chat_llm(
                messages=[{"role": "user", "content": "hello"}],
                **common_kwargs,
            )
        )

    assert [response.result for response in responses] == ["The answer"]
    assert span.end_args["output"] == {
        "content": "The answer",
        "reasoning_content": "Think carefully.",
    }


def test_langfuse_reasoning_output_keeps_empty_content_key():
    assert llm._build_langfuse_llm_output("", "Think carefully.") == {
        "content": "",
        "reasoning_content": "Think carefully.",
    }


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (
            SimpleNamespace(
                reasoning_content=None,
                thinking_blocks=[
                    {"type": "thinking", "thinking": "first block"},
                    {"type": "thinking", "thinking": "second block"},
                ],
            ),
            "first block\nsecond block",
        ),
        (
            SimpleNamespace(
                reasoning_content=None,
                thinking_blocks=None,
                provider_specific_fields={"reasoning": "provider"},
            ),
            "provider",
        ),
        (
            SimpleNamespace(
                reasoning_content=None,
                thinking_blocks=[
                    {
                        "type": "thinking",
                        "thinking": "accumulated snapshot",
                        "signature": "signed",
                    }
                ],
            ),
            "",
        ),
    ],
)
def test_extract_reasoning_delta_supports_litellm_fallback_fields(
    delta: object, expected: object
):
    assert llm._extract_reasoning_delta(delta) == expected


def test_chat_llm_falls_back_to_request_trace_id(monkeypatch: object, app: object):
    def fake_completion(*args: object, **kwargs: object):
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


class _FakeAPIConnectionError(Exception):
    """Stands in for litellm.exceptions.APIConnectionError."""


class _FakeMidStreamFallbackError(Exception):
    """Stands in for litellm.exceptions.MidStreamFallbackError."""


def _stream_chunk(content: object):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(delta=SimpleNamespace(content=content), finish_reason=None)
        ],
        usage=None,
    )


def _reasoning_stream_chunk(reasoning_content: object):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=None, reasoning_content=reasoning_content
                ),
                finish_reason=None,
            )
        ],
        usage=None,
    )


def _patch_retryable_stream_errors(monkeypatch: object):
    # Distinct classes per exception name: a resolver that silently drops one
    # of the names fails that class's parametrized retry test instead of
    # being masked by a shared class.
    monkeypatch.setattr(
        llm.litellm,
        "exceptions",
        SimpleNamespace(
            APIConnectionError=_FakeAPIConnectionError,
            MidStreamFallbackError=_FakeMidStreamFallbackError,
        ),
        raising=False,
    )


def _patch_scripted_streams(monkeypatch: object, scripts: object):
    """Each call to _stream_litellm_completion consumes the next script; a script is a list of chunks and/or exceptions raised in order."""
    calls = {"count": 0}

    def _factory(
        _app: object,
        _requested: object,
        _invoke: object,
        _messages: object,
        _params: object,
        _kwargs: object,
    ):
        script = scripts[min(calls["count"], len(scripts) - 1)]
        calls["count"] += 1

        def _gen():
            for item in script:
                if isinstance(item, BaseException):
                    raise item
                yield item

        return _gen()

    monkeypatch.setattr(llm, "_stream_litellm_completion", _factory)
    return calls


def _collect_retry_stream(app: object):
    return list(
        llm._iter_stream_with_precontent_retry(
            app, "qwen/test-model", "test-model", [], {}, {}
        )
    )


@pytest.mark.parametrize(
    "error_type", [_FakeAPIConnectionError, _FakeMidStreamFallbackError]
)
def test_stream_retries_connection_error_before_first_content(
    monkeypatch: object, app: object, error_type: object
):
    _patch_retryable_stream_errors(monkeypatch)
    calls = _patch_scripted_streams(
        monkeypatch,
        [
            [error_type("bad record mac")],
            [_stream_chunk("hello"), _stream_chunk(" world")],
        ],
    )

    chunks = _collect_retry_stream(app)

    assert [c.choices[0].delta.content for c in chunks] == ["hello", " world"]
    assert calls["count"] == 2


def test_stream_retry_discards_reasoning_from_failed_attempt(
    monkeypatch: object, app: object
):
    _patch_retryable_stream_errors(monkeypatch)
    calls = _patch_scripted_streams(
        monkeypatch,
        [
            [
                _reasoning_stream_chunk("stale reasoning"),
                _FakeAPIConnectionError("bad record mac"),
            ],
            [
                _reasoning_stream_chunk("fresh reasoning"),
                _stream_chunk("answer"),
            ],
        ],
    )

    chunks = _collect_retry_stream(app)

    assert [
        llm._extract_reasoning_delta(chunk.choices[0].delta)
        for chunk in chunks
        if llm._extract_reasoning_delta(chunk.choices[0].delta)
    ] == ["fresh reasoning"]
    assert [chunk.choices[0].delta.content for chunk in chunks] == [None, "answer"]
    assert calls["count"] == 2


def test_stream_error_after_content_is_not_retried(monkeypatch: object, app: object):
    _patch_retryable_stream_errors(monkeypatch)
    calls = _patch_scripted_streams(
        monkeypatch,
        [[_stream_chunk("partial"), _FakeMidStreamFallbackError("mid-stream death")]],
    )

    with pytest.raises(_FakeMidStreamFallbackError):
        _collect_retry_stream(app)

    assert calls["count"] == 1


def test_stream_retry_attempts_are_bounded(monkeypatch: object, app: object):
    _patch_retryable_stream_errors(monkeypatch)
    calls = _patch_scripted_streams(
        monkeypatch,
        [
            [_FakeAPIConnectionError("first failure")],
            [_FakeMidStreamFallbackError("second failure")],
        ],
    )

    with pytest.raises(_FakeMidStreamFallbackError):
        _collect_retry_stream(app)

    assert calls["count"] == 2


def test_stream_non_retryable_error_raises_immediately(
    monkeypatch: object, app: object
):
    _patch_retryable_stream_errors(monkeypatch)
    calls = _patch_scripted_streams(monkeypatch, [[ValueError("business error")]])

    with pytest.raises(ValueError, match="business error"):
        _collect_retry_stream(app)

    assert calls["count"] == 1


def test_stream_retry_noop_when_exception_types_unavailable(
    monkeypatch: object, app: object
):
    """The litellm test stub has no exceptions submodule; the wrapper must degrade to raising instead of crashing on type resolution."""
    monkeypatch.delattr(llm.litellm, "exceptions", raising=False)
    calls = _patch_scripted_streams(
        monkeypatch, [[_FakeAPIConnectionError("connection died")]]
    )

    with pytest.raises(_FakeAPIConnectionError):
        _collect_retry_stream(app)

    assert calls["count"] == 1
