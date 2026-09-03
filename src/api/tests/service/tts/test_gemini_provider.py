"""Verify Gemini TTS provider configuration, requests, and validation."""

from __future__ import annotations

import base64
import json
from typing import ClassVar

import pytest
import requests
from flaskr.api.tts import gemini_provider as module
from flaskr.api.tts.base import VoiceSettings
from flaskr.service.common.models import AppError
from flaskr.service.tts.validation import validate_tts_settings_strict

_ONE_SECOND_PCM = b"\x00\x00" * 24000  # 16-bit mono at 24 kHz
_FAKE_MP3 = b"ID3fake-mp3"


def _patch_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: object = True,
    api_key: str = "test-gemini-key",
    voices: object = "",
    api_url: str = "",
) -> None:
    values = {
        "GEMINI_TTS_ENABLED": enabled,
        "GEMINI_API_KEY": api_key,
        "GEMINI_TTS_VOICES_JSON": voices,
        "GEMINI_TTS_API_URL": api_url,
    }
    monkeypatch.setattr(module, "get_config", lambda key, *_args: values.get(key, ""))


def _patch_transcoder(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def _fake_export(pcm: bytes, *, sample_rate: int, **kwargs: object) -> bytes:
        calls.append({"pcm": pcm, "sample_rate": sample_rate, **kwargs})
        return _FAKE_MP3 if pcm else b""

    monkeypatch.setattr(module, "export_pcm_to_mp3", _fake_export)
    return calls


def _audio_response(
    pcm: bytes = _ONE_SECOND_PCM,
    *,
    mime_type: str = "audio/L16;codec=pcm;rate=24000",
    finish_reason: str = "STOP",
    extra_parts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    parts: list[dict[str, object]] = list(extra_parts or [])
    parts.append(
        {
            "inlineData": {
                "mimeType": mime_type,
                "data": base64.b64encode(pcm).decode("ascii"),
            }
        }
    )
    return {
        "candidates": [
            {
                "content": {"parts": parts, "role": "model"},
                "finishReason": finish_reason,
            }
        ],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 25},
    }


class _JsonResponse:
    reason = "OK"
    headers: ClassVar[dict[str, str]] = {"x-request-id": "req-1"}

    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload).encode("utf-8")

    def json(self) -> object:
        return self._payload


def test_builtin_voice_catalog_has_thirty_unique_prebuilt_voices() -> None:
    values = [item["value"] for item in module.GEMINI_TTS_VOICES]

    assert len(values) == 30
    assert len(set(values)) == 30
    assert "Kore" in values
    assert all(
        item["label"].startswith(item["value"]) for item in module.GEMINI_TTS_VOICES
    )


def test_load_voices_defaults_to_builtin_when_allowlist_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, voices="")
    assert module._load_gemini_voices() == module.GEMINI_TTS_VOICES

    _patch_config(monkeypatch, voices="   ")
    assert module._load_gemini_voices() == module.GEMINI_TTS_VOICES


def test_load_voices_filters_allowlist_to_builtin_and_applies_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(
        monkeypatch,
        voices=json.dumps(
            [
                {"value": " Puck ", "label": "Narrator"},
                {"value": "Kore", "label": "Teacher"},
            ]
        ),
    )

    assert module._load_gemini_voices() == [
        {"value": "Puck", "label": "Narrator"},
        {"value": "Kore", "label": "Teacher"},
    ]


def test_load_voices_drops_unknown_names_and_falls_back_when_none_remain(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch_config(
        monkeypatch,
        voices=json.dumps(
            [{"value": "NotAVoice", "label": "Nope"}, {"value": "Kore", "label": "K"}]
        ),
    )
    with caplog.at_level("WARNING"):
        assert module._load_gemini_voices() == [{"value": "Kore", "label": "K"}]
    assert "NotAVoice" in caplog.text

    _patch_config(monkeypatch, voices=json.dumps([{"value": "Nope", "label": "N"}]))
    assert module._load_gemini_voices() == module.GEMINI_TTS_VOICES


@pytest.mark.parametrize(
    "value",
    [
        "not-json",
        json.dumps({"value": "Kore"}),
        json.dumps(["Kore"]),
        json.dumps([{"value": "", "label": "Voice"}]),
        json.dumps([{"value": "Kore", "label": "A"}, {"value": "Kore", "label": "B"}]),
    ],
)
def test_load_voices_ignores_invalid_json(
    monkeypatch: pytest.MonkeyPatch, value: str, caplog: pytest.LogCaptureFixture
) -> None:
    _patch_config(monkeypatch, voices=value)
    with caplog.at_level("WARNING"):
        assert module._load_gemini_voices() == module.GEMINI_TTS_VOICES
    assert "GEMINI_TTS_VOICES_JSON" in caplog.text


def test_provider_requires_enabled_flag_and_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = module.GeminiTTSProvider()

    _patch_config(monkeypatch, enabled=False, api_key="key")
    assert provider.is_configured() is False

    _patch_config(monkeypatch, enabled=True, api_key="")
    assert provider.is_configured() is False

    _patch_config(monkeypatch, enabled=True, api_key="key")
    assert provider.is_configured() is True


def test_provider_config_exposes_models_locked_ranges_and_voices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    provider = module.GeminiTTSProvider()

    config = provider.get_provider_config()

    assert provider.provider_name == "gemini"
    assert config.name == "gemini"
    assert config.label == "Gemini"
    assert [item["value"] for item in config.models or []] == [
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts",
    ]
    assert config.voices == module.GEMINI_TTS_VOICES
    assert config.speed.to_dict() == {
        "min": 1.0,
        "max": 1.0,
        "step": 0.1,
        "default": 1.0,
    }
    assert config.pitch.min == config.pitch.max == config.pitch.default == 0
    assert config.supports_emotion is False
    assert config.supports_custom_voice_id is False
    assert config.supports_voice_cloning is False
    assert provider.get_default_voice_settings().voice_id == "Zephyr"
    assert provider.get_default_audio_settings().format == "mp3"


def test_provider_is_registered_for_explicit_selection_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.api.tts as tts_api

    _patch_config(monkeypatch)
    tts_api._provider_instances.clear()

    assert tts_api.TTSProvider.GEMINI == "gemini"
    assert tts_api.get_tts_provider("gemini").provider_name == "gemini"
    assert "gemini" in tts_api._PROVIDER_PRIORITY
    assert "gemini" not in tts_api._AUTO_DETECT_PROVIDER_PRIORITY
    assert "gemini" in tts_api._CONFIG_REQUIRES_CONFIGURED_PROVIDER
    assert "gemini" in tts_api._CONFIG_REQUIRES_ALLOWED_MODEL


def test_synthesize_sends_generate_content_request_and_returns_mp3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, api_url="https://example.test/v1beta/")
    transcodes = _patch_transcoder(monkeypatch)
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return _JsonResponse(_audio_response())

    monkeypatch.setattr(module.requests, "post", fake_post)

    result = module.GeminiTTSProvider().synthesize(
        "Hello there.",
        voice_settings=VoiceSettings(voice_id="Puck", speed=1.0, pitch=0),
        model="gemini-2.5-pro-preview-tts",
    )

    assert captured["url"] == (
        "https://example.test/v1beta/models/gemini-2.5-pro-preview-tts:generateContent"
    )
    assert captured["headers"] == {
        "x-goog-api-key": "test-gemini-key",
        "Content-Type": "application/json",
    }
    assert captured["json"] == {
        "contents": [{"parts": [{"text": "Hello there."}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}
            },
        },
    }
    assert captured["timeout"] == (10, 90)
    assert captured["allow_redirects"] is False
    assert transcodes == [{"pcm": _ONE_SECOND_PCM, "sample_rate": 24000}]
    assert result.audio_data == _FAKE_MP3
    assert result.format == "mp3"
    assert result.sample_rate == 24000
    assert result.duration_ms == 1000
    assert result.word_count == len("Hello there.")
    assert result.usage_characters == len("Hello there.")
    assert result.subtitle_cues == []


def test_synthesize_defaults_model_and_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch, voices=json.dumps([{"value": "Kore", "label": "K"}]))
    _patch_transcoder(monkeypatch)
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return _JsonResponse(_audio_response())

    monkeypatch.setattr(module.requests, "post", fake_post)

    module.GeminiTTSProvider().synthesize("Hello")

    assert str(captured["url"]).endswith(
        f"/models/{module.GEMINI_TTS_DEFAULT_MODEL}:generateContent"
    )
    speech_config = captured["json"]["generationConfig"]["speechConfig"]  # type: ignore[index]
    assert speech_config["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"


def test_synthesize_honours_sample_rate_from_mime_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    transcodes = _patch_transcoder(monkeypatch)
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: _JsonResponse(
            _audio_response(
                mime_type="audio/L16;codec=pcm;rate=16000",
                extra_parts=[{"text": "ignored transcript"}],
            )
        ),
    )

    result = module.GeminiTTSProvider().synthesize("Hello")

    assert transcodes[0]["sample_rate"] == 16000
    assert result.sample_rate == 16000
    assert result.duration_ms == 1500


def test_synthesize_rejects_non_pcm_mime_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    _patch_transcoder(monkeypatch)
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: _JsonResponse(
            _audio_response(mime_type="audio/mpeg")
        ),
    )

    with pytest.raises(ValueError, match="Unsupported Gemini TTS audio mime type"):
        module.GeminiTTSProvider().synthesize("Hello")


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, "Gemini TTS HTTP 400"),
        (401, "Gemini TTS HTTP 401"),
        (404, "Gemini TTS HTTP 404"),
        (429, "rate limit"),
        (500, "Gemini TTS HTTP 500"),
        (503, "rate limit"),
    ],
)
def test_synthesize_reports_safe_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected: str,
) -> None:
    _patch_config(monkeypatch)
    payload = {
        "error": {
            "code": status_code,
            "message": "request denied for Hello",
            "status": "FAILED",
        }
    }
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: _JsonResponse(payload, status_code=status_code),
    )

    with pytest.raises(ValueError, match=expected) as exc_info:
        module.GeminiTTSProvider().synthesize("Hello")

    assert "test-gemini-key" not in str(exc_info.value)
    assert "Hello" not in str(exc_info.value)
    assert "[redacted]" in str(exc_info.value)


def test_synthesize_rejects_redirect_without_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    captured: dict[str, object] = {}

    def fake_post(*_args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return _JsonResponse({"error": {"message": "moved"}}, status_code=302)

    monkeypatch.setattr(module.requests, "post", fake_post)

    with pytest.raises(ValueError, match="Gemini TTS HTTP 302"):
        module.GeminiTTSProvider().synthesize("Hello")
    assert captured["allow_redirects"] is False


def test_synthesize_converts_network_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)

    def timeout(*_args: object, **_kwargs: object) -> object:
        message = "connection timed out"
        raise requests.Timeout(message)

    monkeypatch.setattr(module.requests, "post", timeout)
    with pytest.raises(ValueError, match="request failed"):
        module.GeminiTTSProvider().synthesize("Hello")


@pytest.mark.parametrize(
    "payload",
    [
        {"candidates": []},
        {"candidates": [{"content": {"parts": [{"text": "no audio"}]}}]},
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"inlineData": {"mimeType": "audio/L16", "data": ""}}]
                    }
                }
            ]
        },
        _audio_response(pcm=b""),
    ],
)
def test_synthesize_raises_empty_audio_marker(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    _patch_config(monkeypatch)
    _patch_transcoder(monkeypatch)
    monkeypatch.setattr(
        module.requests, "post", lambda *_args, **_kwargs: _JsonResponse(payload)
    )

    with pytest.raises(ValueError, match="No audio data received"):
        module.GeminiTTSProvider().synthesize("Hello")


def test_synthesize_reports_prompt_block_and_safety_finish_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    _patch_transcoder(monkeypatch)

    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: _JsonResponse(
            {"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}, "candidates": []}
        ),
    )
    with pytest.raises(ValueError, match="blocked: PROHIBITED_CONTENT") as exc_info:
        module.GeminiTTSProvider().synthesize("Hello")
    assert "No audio data received" not in str(exc_info.value)

    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: _JsonResponse(
            {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}
        ),
    )
    with pytest.raises(ValueError, match="content blocked: SAFETY") as exc_info:
        module.GeminiTTSProvider().synthesize("Hello")
    assert "No audio data received" not in str(exc_info.value)


def test_synthesize_rejects_non_json_and_non_object_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)

    class BadJsonResponse(_JsonResponse):
        def json(self) -> object:
            message = "not json"
            raise ValueError(message)

    monkeypatch.setattr(
        module.requests, "post", lambda *_args, **_kwargs: BadJsonResponse({})
    )
    with pytest.raises(ValueError, match="non-JSON"):
        module.GeminiTTSProvider().synthesize("Hello")

    monkeypatch.setattr(
        module.requests, "post", lambda *_args, **_kwargs: _JsonResponse(["nope"])
    )
    with pytest.raises(TypeError, match="unexpected response payload"):
        module.GeminiTTSProvider().synthesize("Hello")


@pytest.mark.parametrize(
    ("text", "voice_id", "model", "speed", "pitch", "message"),
    [
        (
            "Hello",
            "Unknown",
            "gemini-2.5-flash-preview-tts",
            1.0,
            0,
            "voice is not approved",
        ),
        ("Hello", "Kore", "unknown-model", 1.0, 0, "Unsupported Gemini TTS model"),
        (
            "Hello",
            "Kore",
            "gemini-2.5-flash-preview-tts",
            1.2,
            0,
            "speed is fixed at 1.0",
        ),
        (
            "Hello",
            "Kore",
            "gemini-2.5-flash-preview-tts",
            1.0,
            1,
            "pitch is fixed at 0",
        ),
        (
            "Hello",
            "Kore",
            "gemini-2.5-flash-preview-tts",
            float("nan"),
            0,
            "Invalid Gemini TTS speed",
        ),
        (
            "x" * 4001,
            "Kore",
            "gemini-2.5-flash-preview-tts",
            1.0,
            0,
            "exceeds Gemini TTS limit",
        ),
        ("   ", "Kore", "gemini-2.5-flash-preview-tts", 1.0, 0, "Text cannot be empty"),
    ],
)
def test_synthesize_rejects_invalid_direct_settings(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    voice_id: str,
    model: str,
    speed: float,
    pitch: int,
    message: str,
) -> None:
    _patch_config(monkeypatch)
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: pytest.fail("provider must reject before requesting"),
    )
    with pytest.raises(ValueError, match=message):
        module.GeminiTTSProvider().synthesize(
            text,
            voice_settings=VoiceSettings(voice_id=voice_id, speed=speed, pitch=pitch),
            model=model,
        )


def test_synthesize_requires_switch_and_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_args, **_kwargs: pytest.fail("provider must reject before requesting"),
    )

    _patch_config(monkeypatch, enabled=False)
    with pytest.raises(ValueError, match="GEMINI_TTS_ENABLED"):
        module.GeminiTTSProvider().synthesize("Hello")

    _patch_config(monkeypatch, api_key="")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        module.GeminiTTSProvider().synthesize("Hello")


def test_strict_validation_accepts_locked_settings_and_rejects_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.api.tts as tts_api

    _patch_config(monkeypatch)
    tts_api._provider_instances.clear()

    settings = validate_tts_settings_strict(
        provider="gemini",
        model="gemini-3.1-flash-tts-preview",
        voice_id="Kore",
        speed=1.0,
        pitch=0,
        emotion="",
    )
    assert settings.provider == "gemini"
    assert settings.model == "gemini-3.1-flash-tts-preview"
    assert settings.voice_id == "Kore"

    valid = {
        "model": "gemini-3.1-flash-tts-preview",
        "voice_id": "Kore",
        "speed": 1.0,
        "pitch": 0,
        "emotion": "",
    }
    invalid_settings = [
        {**valid, "model": ""},
        {**valid, "model": "unknown"},
        {**valid, "voice_id": "Unknown"},
        {**valid, "speed": 0.9},
        {**valid, "speed": float("inf")},
        {**valid, "pitch": 1},
        {**valid, "emotion": "happy"},
    ]
    for values in invalid_settings:
        with pytest.raises(AppError):
            validate_tts_settings_strict(provider="gemini", **values)


def test_config_endpoint_hides_disabled_provider_and_exposes_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.api.tts as tts_api

    monkeypatch.setattr(
        tts_api,
        "_PROVIDER_REGISTRY",
        {"gemini": module.GeminiTTSProvider},
    )
    monkeypatch.setattr(tts_api, "_PROVIDER_PRIORITY", ("gemini",))
    monkeypatch.setattr(
        tts_api, "_resolve_credit_multiplier_label", lambda *_args: None
    )

    _patch_config(monkeypatch, enabled=False)
    assert tts_api.get_all_provider_configs() == {"providers": [], "model_options": []}

    _patch_config(monkeypatch)
    monkeypatch.setattr(
        tts_api,
        "get_config",
        lambda key, default=None: (
            "volcengine/seed-tts-2.0" if key == "TTS_ALLOWED_MODELS" else default
        ),
    )
    assert tts_api.get_all_provider_configs() == {"providers": [], "model_options": []}

    subset_config = {
        "TTS_ALLOWED_MODELS": "gemini/gemini-2.5-flash-preview-tts",
        "TTS_DEFAULT_MODEL": "gemini/gemini-2.5-flash-preview-tts",
        "TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON": "",
    }
    monkeypatch.setattr(
        tts_api, "get_config", lambda key, default=None: subset_config.get(key, default)
    )
    subset = tts_api.get_all_provider_configs()

    assert [model["value"] for model in subset["providers"][0]["models"]] == [
        "gemini-2.5-flash-preview-tts"
    ]
    assert len(subset["providers"][0]["voices"]) == 30
    assert [item["value"] for item in subset["model_options"]] == [
        "gemini/gemini-2.5-flash-preview-tts"
    ]
    assert subset["model_options"][0]["is_default"] is True
