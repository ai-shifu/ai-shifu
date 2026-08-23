"""Verify tencent TextToVoice provider behavior."""

import base64
import hashlib
import hmac
import json

import pytest


def _expected_tc3_authorization(*, payload_json: str, timestamp: int) -> str:
    host = "tts.tencentcloudapi.com"
    service = "tts"
    secret_id = "secret-id"
    secret_key = "secret-key"
    date = "2023-07-06"
    algorithm = "TC3-HMAC-SHA256"
    canonical_headers = (
        f"content-type:application/json\nhost:{host}\nx-tc-action:texttovoice\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    canonical_request = (
        f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
    )
    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        [
            algorithm,
            str(timestamp),
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    def sign(key: object, msg: object):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = sign(secret_date, service)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


def _patch_credentials(monkeypatch: object):
    from flaskr.api.tts import tencent_texttovoice_provider as module

    config = {
        "TENCENT_TTS_SECRET_ID": "secret-id",
        "TENCENT_TTS_SECRET_KEY": "secret-key",
    }
    monkeypatch.setattr(
        module,
        "get_config",
        lambda key, default=None: config.get(key, default),
    )


class _FakeResponse:
    def __init__(self, body: object) -> None:
        self._body = body

    def json(self):
        return self._body


def test_tc3_headers_sign_exact_request_payload() -> None:
    from flaskr.api.tts.tencent_texttovoice_provider import (
        build_texttovoice_tc3_headers,
    )

    payload_json = json.dumps(
        {
            "Text": "你好呀",
            "SessionId": "session-1",
            "VoiceType": 101001,
            "Codec": "mp3",
            "SampleRate": 16000,
            "ModelType": 1,
            "Speed": 0.0,
        },
        ensure_ascii=False,
    )
    headers = build_texttovoice_tc3_headers(
        payload_json=payload_json,
        secret_id="secret-id",
        secret_key="secret-key",
        timestamp=1688610905,
    )

    assert headers["Host"] == "tts.tencentcloudapi.com"
    assert headers["Content-Type"] == "application/json"
    assert headers["X-TC-Action"] == "TextToVoice"
    assert headers["X-TC-Version"] == "2019-08-23"
    assert headers["X-TC-Region"] == "ap-guangzhou"
    assert headers["X-TC-Timestamp"] == "1688610905"
    assert headers["Authorization"] == _expected_tc3_authorization(
        payload_json=payload_json,
        timestamp=1688610905,
    )


def test_provider_config_exposes_two_model_tiers_with_tagged_voices() -> None:
    from flaskr.api.tts.tencent_texttovoice_provider import (
        TencentTextToVoiceProvider,
    )

    cfg = TencentTextToVoiceProvider().get_provider_config()

    assert [model["value"] for model in cfg.models] == ["premium", "large-model"]
    assert cfg.supports_emotion is False
    resource_ids = {(voice.get("resource_id") or "") for voice in cfg.voices}
    assert resource_ids == {"premium", "large-model"}
    premium_voices = [
        voice for voice in cfg.voices if voice["resource_id"] == "premium"
    ]
    large_voices = [
        voice for voice in cfg.voices if voice["resource_id"] == "large-model"
    ]
    assert premium_voices  # non-empty
    assert all(v["value"].startswith("101") for v in premium_voices)
    assert all(v["value"][:3] in {"501", "601"} for v in large_voices)


def test_resolve_sample_rate_by_voice_tier_and_model_fallback() -> None:
    from flaskr.api.tts.tencent_texttovoice_provider import _resolve_sample_rate

    assert _resolve_sample_rate("101001", "") == 16000
    assert _resolve_sample_rate("501001", "") == 24000
    assert _resolve_sample_rate("601008", "") == 24000
    # Unknown voice falls back to the model tier, then to premium.
    assert _resolve_sample_rate("999999", "large-model") == 24000
    assert _resolve_sample_rate("999999", "") == 16000


def test_split_text_weighted_limits() -> None:
    from flaskr.api.tts.tencent_texttovoice_provider import (
        _SEGMENT_WEIGHT_LIMIT,
        _split_text,
        _text_weight,
    )

    # Pure Chinese beyond the limit splits on sentence boundaries.
    chinese = "这是一句用于测试的话。" * 30
    segments = _split_text(chinese)
    assert len(segments) > 1
    assert "".join(segments) == chinese
    assert all(_text_weight(seg) <= _SEGMENT_WEIGHT_LIMIT for seg in segments)

    # 460 English letters weigh 138 (< 140): stays in one segment.
    english = ("hello world" * 46)[:460]
    assert len(_split_text(english)) == 1

    # A single overlong sentence without punctuation is hard-split.
    overlong = "长" * 300
    hard_segments = _split_text(overlong)
    assert len(hard_segments) > 1
    assert "".join(hard_segments) == overlong
    assert all(_text_weight(seg) <= _SEGMENT_WEIGHT_LIMIT for seg in hard_segments)

    assert _split_text("   ") == []


def test_synthesize_builds_payload_and_concatenates_segments(
    monkeypatch: object,
) -> None:
    from flaskr.api.tts import tencent_texttovoice_provider as module

    _patch_credentials(monkeypatch)
    captured_payloads = []

    def _fake_post(
        url: object, data: object = None, headers: object = None, timeout: object = None
    ):
        _ = (url, headers, timeout)
        captured_payloads.append(json.loads(data.decode("utf-8")))
        return _FakeResponse(
            {
                "Response": {
                    "Audio": base64.b64encode(b"seg-audio").decode("ascii"),
                    "RequestId": "req-1",
                }
            }
        )

    monkeypatch.setattr(module.requests, "post", _fake_post)

    def concat_audio(segments: list[bytes], output_format: str = "mp3") -> bytes:
        del output_format
        return b"".join(segments)

    monkeypatch.setattr(
        module,
        "concat_audio_best_effort",
        concat_audio,
    )
    monkeypatch.setattr(
        module,
        "try_get_audio_duration_ms",
        lambda _audio, **_kwargs: 1234,
    )

    provider = module.TencentTextToVoiceProvider()
    text = "第一句话。" * 40  # forces multiple segments
    result = provider.synthesize(
        text,
        voice_settings=module.VoiceSettings(voice_id="501001", speed=1.5),
        model="large-model",
    )

    assert len(captured_payloads) > 1
    for payload in captured_payloads:
        assert payload["VoiceType"] == 501001
        assert payload["Codec"] == "mp3"
        assert payload["ModelType"] == 1
        assert payload["SampleRate"] == 24000
        assert payload["Speed"] == 1.5
        assert payload["SessionId"]
    assert result.audio_data == b"seg-audio" * len(captured_payloads)
    assert result.duration_ms == 1234
    assert result.sample_rate == 24000
    assert result.usage_characters == len(text)


def test_synthesize_raises_on_api_error_with_code(monkeypatch: object) -> None:
    from flaskr.api.tts import tencent_texttovoice_provider as module

    _patch_credentials(monkeypatch)
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            {
                "Response": {
                    "Error": {
                        "Code": "InvalidParameterValue",
                        "Message": "bad voice",
                    },
                    "RequestId": "req-err",
                }
            }
        ),
    )

    provider = module.TencentTextToVoiceProvider()
    with pytest.raises(ValueError, match="InvalidParameterValue") as exc_info:
        provider.synthesize(
            "你好",
            voice_settings=module.VoiceSettings(voice_id="101001"),
        )
    assert "InvalidParameterValue" in str(exc_info.value)
    assert "req-err" in str(exc_info.value)


def test_synthesize_raises_on_empty_audio(monkeypatch: object) -> None:
    from flaskr.api.tts import tencent_texttovoice_provider as module

    _patch_credentials(monkeypatch)
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            {"Response": {"Audio": "", "RequestId": "req-empty"}}
        ),
    )

    provider = module.TencentTextToVoiceProvider()
    with pytest.raises(
        ValueError, match="No audio data received from Tencent TextToVoice"
    ) as exc_info:
        provider.synthesize(
            "你好",
            voice_settings=module.VoiceSettings(voice_id="101001"),
        )
    assert "No audio data received from Tencent TextToVoice" in str(exc_info.value)


def test_synthesize_rejects_non_numeric_voice_id(monkeypatch: object) -> None:
    from flaskr.api.tts import tencent_texttovoice_provider as module

    _patch_credentials(monkeypatch)
    provider = module.TencentTextToVoiceProvider()
    with pytest.raises(
        ValueError, match="Invalid Tencent TextToVoice voice id"
    ) as exc_info:
        provider.synthesize(
            "你好",
            voice_settings=module.VoiceSettings(voice_id="v-female-R2s4N9qJ"),
        )
    assert "Invalid Tencent TextToVoice voice id" in str(exc_info.value)


def test_validation_requires_model_and_tier_consistency() -> None:
    from flaskr.service.common.models import AppError
    from flaskr.service.tts.validation import validate_tts_settings_strict

    # Valid: premium voice with premium tier.
    settings = validate_tts_settings_strict(
        provider="tencent_texttovoice",
        model="premium",
        voice_id="101001",
        speed=0,
        pitch=0,
        emotion="",
    )
    assert settings.model == "premium"

    # Valid: large-model voice with large-model tier.
    settings = validate_tts_settings_strict(
        provider="tencent_texttovoice",
        model="large-model",
        voice_id="501001",
        speed=0,
        pitch=0,
        emotion="",
    )
    assert settings.model == "large-model"

    # Missing model is rejected (provider requires model).
    with pytest.raises(AppError):
        validate_tts_settings_strict(
            provider="tencent_texttovoice",
            model="",
            voice_id="101001",
            speed=0,
            pitch=0,
            emotion="",
        )

    # Cross-tier combination is rejected (premium voice + large-model tier).
    with pytest.raises(AppError):
        validate_tts_settings_strict(
            provider="tencent_texttovoice",
            model="large-model",
            voice_id="101001",
            speed=0,
            pitch=0,
            emotion="",
        )

    # Emotion is not supported.
    with pytest.raises(AppError):
        validate_tts_settings_strict(
            provider="tencent_texttovoice",
            model="premium",
            voice_id="101001",
            speed=0,
            pitch=0,
            emotion="happy",
        )
