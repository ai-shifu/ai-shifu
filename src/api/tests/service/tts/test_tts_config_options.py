import json

from flask import Flask

from flaskr.api.tts import base


class _FakeMinimaxProvider:
    def get_provider_config(self):
        return base.ProviderConfig(
            name="MiniMax",
            label="MiniMax",
            speed=base.ParamRange(min=0.5, max=2.0, step=0.1, default=1.0),
            pitch=base.ParamRange(min=-12, max=12, step=1, default=0),
            supports_emotion=True,
            models=[
                {"value": "speech-01-turbo", "label": "Speech Turbo"},
                {"value": "speech-01-hd", "label": "Speech HD"},
            ],
            voices=[{"value": "voice-1", "label": "Voice 1"}],
            emotions=[],
        )


class _FakeBaiduProvider:
    def get_provider_config(self):
        return base.ProviderConfig(
            name="baidu",
            label="Baidu",
            speed=base.ParamRange(min=0, max=15, step=1, default=5),
            pitch=base.ParamRange(min=0, max=15, step=1, default=5),
            supports_emotion=False,
            models=[],
            voices=[{"value": "baidu-voice", "label": "Baidu Voice"}],
            emotions=[],
        )


def test_tts_config_model_options_follow_allowlist_and_localized_names(
    monkeypatch,
):
    import flaskr.api.tts as tts_api
    from flaskr.i18n import clear_language, set_language

    monkeypatch.setattr(
        tts_api,
        "_PROVIDER_REGISTRY",
        {"minimax": _FakeMinimaxProvider, "baidu": _FakeBaiduProvider},
    )
    monkeypatch.setattr(tts_api, "_PROVIDER_PRIORITY", ("minimax", "baidu"))
    monkeypatch.setattr(
        tts_api,
        "_resolve_credit_multiplier_label",
        lambda provider, model: "2x" if provider == "minimax" else None,
    )
    monkeypatch.setenv(
        "TTS_ALLOWED_MODELS",
        "minimax/speech-01-turbo,baidu/default",
    )
    monkeypatch.setenv(
        "TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON",
        json.dumps(
            {
                "minimax/speech-01-turbo": {
                    "zh-CN": "MiniMax 语音 Turbo",
                    "en-US": "MiniMax Speech Turbo",
                },
                "baidu/default": {"en-US": "Baidu Default"},
            }
        ),
    )

    try:
        set_language("zh-CN")
        config = tts_api.get_all_provider_configs()
    finally:
        clear_language()

    assert [item["value"] for item in config["model_options"]] == [
        "minimax/speech-01-turbo",
        "baidu/default",
    ]
    assert config["model_options"][0] == {
        "value": "minimax/speech-01-turbo",
        "label": "MiniMax 语音 Turbo",
        "provider": "minimax",
        "model": "speech-01-turbo",
        "credit_multiplier_label": "2x",
    }
    assert config["model_options"][1] == {
        "value": "baidu/default",
        "label": "Baidu Default",
        "provider": "baidu",
        "model": "",
    }


def test_tts_credit_multiplier_uses_default_llm_output_rate(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.service.billing.consts import (
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        BILLING_METRIC_TTS_OUTPUT_CHARS,
    )
    from flaskr.service.metering.consts import (
        BILL_USAGE_TYPE_LLM,
        BILL_USAGE_TYPE_TTS,
    )

    class FakeRate:
        def __init__(
            self,
            credits_per_unit: str,
            unit_size: int,
            provider: str,
            model: str,
        ):
            self.credits_per_unit = credits_per_unit
            self.unit_size = unit_size
            self.provider = provider
            self.model = model

    captured = []

    def fake_load_usage_rate(*, usage, billing_metric, settlement_at):
        captured.append(
            {
                "usage_type": usage.usage_type,
                "provider": usage.provider,
                "model": usage.model,
                "billing_metric": billing_metric,
            }
        )
        if (
            usage.usage_type == BILL_USAGE_TYPE_LLM
            and usage.provider == "qwen"
            and usage.model == "deepseek-v4-flash"
            and billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS
        ):
            return FakeRate("1", 10000, "qwen", "deepseek-v4-flash")
        if (
            usage.usage_type == BILL_USAGE_TYPE_TTS
            and usage.provider == "tencent"
            and usage.model == ""
            and billing_metric == BILLING_METRIC_TTS_OUTPUT_CHARS
        ):
            return FakeRate("4", 10000, "tencent", "")
        return None

    monkeypatch.setattr(
        tts_api,
        "_resolve_default_llm_rate_identity",
        lambda: ("qwen", ["deepseek-v4-flash"]),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.charges.load_usage_rate",
        fake_load_usage_rate,
    )

    assert tts_api._resolve_credit_multiplier_label("tencent", "") == "4x"
    assert captured == [
        {
            "usage_type": BILL_USAGE_TYPE_LLM,
            "provider": "qwen",
            "model": "deepseek-v4-flash",
            "billing_metric": BILLING_METRIC_LLM_OUTPUT_TOKENS,
        },
        {
            "usage_type": BILL_USAGE_TYPE_TTS,
            "provider": "tencent",
            "model": "",
            "billing_metric": BILLING_METRIC_TTS_OUTPUT_CHARS,
        },
    ]


def test_tts_credit_multiplier_falls_back_to_default_llm_rate(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.service.billing.consts import (
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        BILLING_METRIC_TTS_OUTPUT_CHARS,
    )
    from flaskr.service.metering.consts import (
        BILL_USAGE_TYPE_LLM,
        BILL_USAGE_TYPE_TTS,
    )

    class FakeRate:
        def __init__(
            self,
            credits_per_unit: str,
            unit_size: int,
            provider: str,
            model: str,
        ):
            self.credits_per_unit = credits_per_unit
            self.unit_size = unit_size
            self.provider = provider
            self.model = model

    def fake_load_usage_rate(*, usage, billing_metric, settlement_at):
        if (
            usage.usage_type == BILL_USAGE_TYPE_LLM
            and usage.provider == "qwen"
            and usage.model == "deepseek-v4-flash"
            and billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS
        ):
            return FakeRate("1", 10000, "qwen", "deepseek-v4-flash")
        if (
            usage.usage_type == BILL_USAGE_TYPE_TTS
            and billing_metric == BILLING_METRIC_TTS_OUTPUT_CHARS
        ):
            return FakeRate("100", 10000, "*", "*")
        return None

    monkeypatch.setattr(
        tts_api,
        "_resolve_default_llm_rate_identity",
        lambda: ("qwen", ["deepseek-v4-flash"]),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.charges.load_usage_rate",
        fake_load_usage_rate,
    )

    assert tts_api._resolve_credit_multiplier_label("unknown", "missing") == "1x"


def test_tts_display_name_prefers_request_language(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.i18n import clear_language

    monkeypatch.setenv(
        "TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON",
        json.dumps(
            {
                "tencent/default": {
                    "zh-CN": "基础语音",
                    "en-US": "Basic Voice",
                }
            }
        ),
    )

    app = Flask(__name__)
    try:
        with app.test_request_context(headers={"Accept-Language": "zh-CN,zh;q=0.9"}):
            assert (
                tts_api._resolve_localized_tts_label(
                    tts_api._parse_tts_display_names(),
                    "tencent/default",
                    "Tencent",
                )
                == "基础语音"
            )
    finally:
        clear_language()
