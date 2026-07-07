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


class _FakeRate:
    def __init__(self, credits_per_unit, unit_size, provider, model):
        self.credits_per_unit = credits_per_unit
        self.unit_size = unit_size
        self.provider = provider
        self.model = model


def _chars_per_token_config(value: str):
    def _get_config(key, default=None):
        if key == "TTS_CHARS_PER_LLM_TOKEN":
            return value
        return default

    return _get_config


def test_tts_credit_multiplier_uses_shared_llm_anchor(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.service.billing.consts import (
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        BILLING_METRIC_TTS_OUTPUT_CHARS,
    )
    from flaskr.service.metering.consts import (
        BILL_USAGE_TYPE_LLM,
        BILL_USAGE_TYPE_TTS,
    )

    captured = []

    def fake_load_usage_rate(*, usage, billing_metric, settlement_at):
        captured.append((usage.usage_type, usage.provider, usage.model, billing_metric))
        if (
            usage.usage_type == BILL_USAGE_TYPE_LLM
            and usage.provider == "qwen"
            and usage.model == "deepseek-v4-flash"
            and billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS
        ):
            return _FakeRate("1", 10000, "qwen", "deepseek-v4-flash")  # 0.0001/token
        if (
            usage.usage_type == BILL_USAGE_TYPE_TTS
            and usage.provider == "tencent"
            and usage.model == ""
            and billing_metric == BILLING_METRIC_TTS_OUTPUT_CHARS
        ):
            return _FakeRate("8", 10000, "tencent", "")  # 0.0008/char
        return None

    monkeypatch.setattr(
        tts_api,
        "_resolve_default_llm_rate_identity",
        lambda: ("qwen", ["deepseek-v4-flash"]),
    )
    monkeypatch.setattr(tts_api, "get_config", _chars_per_token_config("0.5"))
    monkeypatch.setattr(
        "flaskr.service.billing.charges.load_usage_rate",
        fake_load_usage_rate,
    )

    # TTS 0.0008/char x 0.5 chars/token = 0.0004 credits per LLM token; the shared
    # 1x anchor is the LLM rate 0.0001/token -> 0.0004 / 0.0001 = 4x. Both the LLM
    # baseline and the TTS rate are looked up (one shared anchor, not a standalone
    # TTS baseline).
    assert tts_api._resolve_credit_multiplier_label("tencent", "") == "4x"
    assert (
        BILL_USAGE_TYPE_LLM,
        "qwen",
        "deepseek-v4-flash",
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
    ) in captured
    assert (
        BILL_USAGE_TYPE_TTS,
        "tencent",
        "",
        BILLING_METRIC_TTS_OUTPUT_CHARS,
    ) in captured


def test_tts_credit_multiplier_scales_with_chars_per_token(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.service.billing.consts import (
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        BILLING_METRIC_TTS_OUTPUT_CHARS,
    )
    from flaskr.service.metering.consts import (
        BILL_USAGE_TYPE_LLM,
        BILL_USAGE_TYPE_TTS,
    )

    def fake_load_usage_rate(*, usage, billing_metric, settlement_at):
        if (
            usage.usage_type == BILL_USAGE_TYPE_LLM
            and billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS
        ):
            return _FakeRate("1", 10000, "qwen", "deepseek-v4-flash")  # 0.0001/token
        if (
            usage.usage_type == BILL_USAGE_TYPE_TTS
            and billing_metric == BILLING_METRIC_TTS_OUTPUT_CHARS
        ):
            return _FakeRate("8", 10000, "minimax", "speech-2.8-turbo")  # 0.0008/char
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

    # Doubling chars-per-token doubles the TTS consumption per LLM token, so the
    # multiplier doubles (4x -> 8x). This is the token<->char conversion knob.
    monkeypatch.setattr(tts_api, "get_config", _chars_per_token_config("0.5"))
    assert (
        tts_api._resolve_credit_multiplier_label("minimax", "speech-2.8-turbo") == "4x"
    )
    monkeypatch.setattr(tts_api, "get_config", _chars_per_token_config("1.0"))
    assert (
        tts_api._resolve_credit_multiplier_label("minimax", "speech-2.8-turbo") == "8x"
    )


def test_tts_credit_multiplier_none_when_tts_rate_missing(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.service.billing.consts import BILLING_METRIC_LLM_OUTPUT_TOKENS
    from flaskr.service.metering.consts import BILL_USAGE_TYPE_LLM

    def fake_load_usage_rate(*, usage, billing_metric, settlement_at):
        if (
            usage.usage_type == BILL_USAGE_TYPE_LLM
            and billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS
        ):
            return _FakeRate("1", 10000, "qwen", "deepseek-v4-flash")
        return None  # no curated TTS rate

    monkeypatch.setattr(
        tts_api,
        "_resolve_default_llm_rate_identity",
        lambda: ("qwen", ["deepseek-v4-flash"]),
    )
    monkeypatch.setattr(tts_api, "get_config", _chars_per_token_config("0.216"))
    monkeypatch.setattr(
        "flaskr.service.billing.charges.load_usage_rate",
        fake_load_usage_rate,
    )

    # No TTS rate -> no meaningful multiplier -> no label (not a fabricated 1x).
    assert tts_api._resolve_credit_multiplier_label("unknown", "missing") is None


def test_tts_credit_multiplier_none_when_conversion_unset(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.service.billing.consts import BILLING_METRIC_LLM_OUTPUT_TOKENS
    from flaskr.service.metering.consts import BILL_USAGE_TYPE_LLM

    def fake_load_usage_rate(*, usage, billing_metric, settlement_at):
        if (
            usage.usage_type == BILL_USAGE_TYPE_LLM
            and billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS
        ):
            return _FakeRate("1", 10000, "qwen", "deepseek-v4-flash")
        return _FakeRate("8", 10000, "tencent", "")

    monkeypatch.setattr(
        tts_api,
        "_resolve_default_llm_rate_identity",
        lambda: ("qwen", ["deepseek-v4-flash"]),
    )
    monkeypatch.setattr(tts_api, "get_config", _chars_per_token_config(""))
    monkeypatch.setattr(
        "flaskr.service.billing.charges.load_usage_rate",
        fake_load_usage_rate,
    )

    # A blank conversion factor disables the label instead of guessing.
    assert tts_api._resolve_credit_multiplier_label("tencent", "") is None


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


def test_tts_display_name_normalizes_config_keys(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.i18n import clear_language

    # Config uses non-normalized provider casing; lookups later use the
    # normalized "tencent/default" key, so parsing must normalize provider case
    # to keep the label.
    monkeypatch.setenv(
        "TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON",
        json.dumps(
            {
                "TenCent/default": {
                    "zh-CN": "基础语音",
                    "en-US": "Basic Voice",
                }
            }
        ),
    )

    app = Flask(__name__)
    try:
        with app.test_request_context(headers={"Accept-Language": "en-US"}):
            display_names = tts_api._parse_tts_display_names()
            assert "tencent/default" in display_names
            assert (
                tts_api._resolve_localized_tts_label(
                    display_names,
                    "tencent/default",
                    "Tencent",
                )
                == "Basic Voice"
            )
    finally:
        clear_language()


def test_parse_tts_display_names_accepts_preparsed_dict(monkeypatch):
    import flaskr.api.tts as tts_api

    # A programmatic/unit-test config may hand back an already-parsed dict; the
    # parser must accept it instead of str()-ing and failing json.loads.
    monkeypatch.setattr(
        tts_api,
        "get_config",
        lambda key, default=None: (
            {"MiniMax/speech-01-turbo": {"en-US": "Flagship Voice"}}
            if key == "TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON"
            else default
        ),
    )

    display_names = tts_api._parse_tts_display_names()
    assert display_names == {"minimax/speech-01-turbo": {"en-US": "Flagship Voice"}}


def test_usage_rate_unit_cost_uses_utc_settlement(monkeypatch):
    import flaskr.api.tts as tts_api
    from datetime import datetime
    from flaskr.service.billing.consts import BILLING_METRIC_TTS_OUTPUT_CHARS
    from flaskr.service.metering.consts import BILL_USAGE_TYPE_TTS

    utc_sentinel = datetime(2026, 1, 1, 0, 0, 0)

    monkeypatch.setattr(tts_api, "now_utc", lambda: utc_sentinel)

    captured = {}

    def fake_load_usage_rate(*, usage, billing_metric, settlement_at):
        captured["settlement_at"] = settlement_at
        return None

    monkeypatch.setattr(
        "flaskr.service.billing.charges.load_usage_rate",
        fake_load_usage_rate,
    )

    tts_api._load_usage_rate_unit_cost(
        usage_type=BILL_USAGE_TYPE_TTS,
        provider="tencent",
        model_candidates=[""],
        billing_metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
    )

    assert captured["settlement_at"] == utc_sentinel
