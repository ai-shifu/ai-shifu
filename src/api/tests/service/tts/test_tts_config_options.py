import json

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


def test_tts_credit_multiplier_uses_output_chars_metric(monkeypatch):
    import flaskr.api.tts as tts_api
    from flaskr.service.billing.consts import BILLING_METRIC_TTS_OUTPUT_CHARS
    from flaskr.service.metering.consts import BILL_USAGE_TYPE_TTS

    captured = {}

    def fake_resolve_credit_multiplier_label(**kwargs):
        captured.update(kwargs)
        return "4x"

    monkeypatch.setattr(
        "flaskr.service.billing.charges.resolve_credit_multiplier_label",
        fake_resolve_credit_multiplier_label,
    )

    assert tts_api._resolve_credit_multiplier_label("tencent", "") == "4x"
    assert captured == {
        "usage_type": BILL_USAGE_TYPE_TTS,
        "provider": "tencent",
        "model": "",
        "billing_metrics": (BILLING_METRIC_TTS_OUTPUT_CHARS,),
    }
