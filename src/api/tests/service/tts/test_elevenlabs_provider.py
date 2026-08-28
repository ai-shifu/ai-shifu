"""Verify ElevenLabs provider configuration, requests, and validation."""

from __future__ import annotations

import json
from typing import ClassVar

import pytest
import requests
from flaskr.api.tts import elevenlabs_provider as module
from flaskr.api.tts.base import VoiceSettings
from flaskr.service.common.models import AppError
from flaskr.service.tts.validation import validate_tts_settings_strict


def _voice_json(voice_id: str = "voice-1", label: str = "Voice One") -> str:
    return json.dumps([{"value": voice_id, "label": label}])


def _patch_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str = "test-elevenlabs-key",
    voices: object = None,
) -> None:
    values = {
        "ELEVENLABS_API_KEY": api_key,
        "ELEVENLABS_TTS_VOICES_JSON": (_voice_json() if voices is None else voices),
    }
    monkeypatch.setattr(module, "get_config", lambda key, *_args: values.get(key, ""))


def test_parse_elevenlabs_voices_normalizes_whitespace() -> None:
    voices = module.parse_elevenlabs_voices(
        json.dumps([{"value": " voice-1 ", "label": " Voice One "}])
    )
    assert voices == [{"value": "voice-1", "label": "Voice One"}]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("not-json", "valid JSON"),
        (json.dumps({"value": "voice-1"}), "JSON array"),
        (json.dumps(["voice-1"]), "must be an object"),
        (json.dumps([{"value": "", "label": "Voice"}]), "non-empty"),
        (
            json.dumps(
                [
                    {"value": "voice-1", "label": "First"},
                    {"value": "voice-1", "label": "Duplicate"},
                ]
            ),
            "Duplicate ElevenLabs voice id",
        ),
    ],
)
def test_parse_elevenlabs_voices_rejects_invalid_config(
    value: object, message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        module.parse_elevenlabs_voices(value)


def test_provider_requires_key_and_approved_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = module.ElevenLabsTTSProvider()

    _patch_config(monkeypatch, api_key="", voices=_voice_json())
    assert provider.is_configured() is False

    _patch_config(monkeypatch, api_key="key", voices="[]")
    assert provider.is_configured() is False

    _patch_config(monkeypatch, api_key="key", voices=_voice_json())
    assert provider.is_configured() is True


def test_provider_config_exposes_selected_models_and_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    provider = module.ElevenLabsTTSProvider()

    config = provider.get_provider_config()

    assert provider.provider_name == "elevenlabs"
    assert config.name == "elevenlabs"
    assert config.label == "ElevenLabs"
    assert [item["value"] for item in config.models or []] == [
        "eleven_v3_conversational",
        "eleven_v3",
        "eleven_flash_v2_5",
        "eleven_multilingual_v2",
    ]
    assert config.voices == [{"value": "voice-1", "label": "Voice One"}]
    assert config.speed.to_dict() == {
        "min": 0.7,
        "max": 1.2,
        "step": 0.1,
        "default": 1.0,
    }
    assert config.pitch.min == config.pitch.max == config.pitch.default == 0
    assert config.supports_emotion is False
    assert config.supports_custom_voice_id is False
    assert config.supports_voice_cloning is False


def test_provider_is_registered_for_explicit_selection_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.api.tts as tts_api

    _patch_config(monkeypatch)
    tts_api._provider_instances.clear()

    assert tts_api.TTSProvider.ELEVENLABS == "elevenlabs"
    assert tts_api.get_tts_provider("elevenlabs").provider_name == "elevenlabs"
    assert "elevenlabs" in tts_api._PROVIDER_PRIORITY
    assert "elevenlabs" not in tts_api._AUTO_DETECT_PROVIDER_PRIORITY


def test_synthesize_sends_encoded_approved_request_and_returns_mp3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    voice_id = "voice/with space"
    _patch_config(monkeypatch, voices=_voice_json(voice_id, "Narrator"))
    captured: dict[str, object] = {}

    class DummyResponse:
        status_code = 200
        content = b"mp3-bytes"
        reason = "OK"
        headers: ClassVar[dict[str, str]] = {"request-id": "req-1"}

    def fake_post(
        url: object,
        *,
        params: object,
        headers: object,
        json: object,
        timeout: object,
        allow_redirects: object,
    ) -> object:
        captured.update(
            url=url,
            params=params,
            headers=headers,
            json=json,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )
        return DummyResponse()

    monkeypatch.setattr(module.requests, "post", fake_post)
    monkeypatch.setattr(
        module, "try_get_audio_duration_ms", lambda *_args, **_kwargs: 321
    )

    result = module.ElevenLabsTTSProvider().synthesize(
        "Hello world",
        voice_settings=VoiceSettings(voice_id=voice_id, speed=1.1),
        model="eleven_v3",
    )

    assert captured["url"] == f"{module.ELEVENLABS_TTS_API_URL}/voice%2Fwith%20space"
    assert captured["params"] == {"output_format": "mp3_44100_128"}
    assert captured["headers"] == {
        "xi-api-key": "test-elevenlabs-key",
        "Content-Type": "application/json",
    }
    assert captured["json"] == {
        "text": "Hello world",
        "model_id": "eleven_v3",
        "voice_settings": {"speed": 1.1},
    }
    assert captured["timeout"] == (10, 90)
    assert captured["allow_redirects"] is False
    assert result.audio_data == b"mp3-bytes"
    assert result.duration_ms == 321
    assert result.sample_rate == 44100
    assert result.format == "mp3"
    assert result.word_count == len("Hello world")
    assert result.usage_characters == len("Hello world")


def test_synthesize_rejects_redirect_without_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    requests_seen: list[dict[str, object]] = []

    class RedirectResponse:
        status_code = 302
        content = b""
        reason = "Found"
        headers: ClassVar[dict[str, str]] = {
            "Location": "https://untrusted.example/collect"
        }

        def json(self) -> object:
            return {}

    def fake_post(url: object, **kwargs: object) -> object:
        requests_seen.append({"url": url, **kwargs})
        return RedirectResponse()

    monkeypatch.setattr(module.requests, "post", fake_post)

    with pytest.raises(ValueError, match="HTTP 302"):
        module.ElevenLabsTTSProvider().synthesize("Hello")

    assert len(requests_seen) == 1
    assert requests_seen[0]["url"] == f"{module.ELEVENLABS_TTS_API_URL}/voice-1"
    assert requests_seen[0]["allow_redirects"] is False


def test_synthesize_defaults_to_multilingual_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    captured: dict[str, object] = {}

    class DummyResponse:
        status_code = 200
        content = b"mp3"
        reason = "OK"
        headers: ClassVar[dict[str, str]] = {}

    def fake_post(_url: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(module.requests, "post", fake_post)
    monkeypatch.setattr(
        module, "try_get_audio_duration_ms", lambda *_args, **_kwargs: 0
    )

    module.ElevenLabsTTSProvider().synthesize("Hello")

    assert captured["json"]["model_id"] == "eleven_multilingual_v2"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "HTTP 401"),
        (404, "HTTP 404"),
        (429, "HTTP 429 rate limit"),
        (500, "HTTP 500"),
    ],
)
def test_synthesize_reports_safe_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected: str,
) -> None:
    _patch_config(monkeypatch)

    class DummyResponse:
        content = b""
        reason = "Error"
        headers: ClassVar[dict[str, str]] = {"x-request-id": "req-2"}

        def __init__(self) -> None:
            self.status_code = status_code

        def json(self) -> object:
            return {"detail": {"message": "request denied"}}

    monkeypatch.setattr(
        module.requests, "post", lambda *_args, **_kwargs: DummyResponse()
    )

    with pytest.raises(ValueError, match=expected) as exc_info:
        module.ElevenLabsTTSProvider().synthesize("Hello")

    assert "test-elevenlabs-key" not in str(exc_info.value)
    assert "Hello" not in str(exc_info.value)


def test_synthesize_converts_network_and_empty_audio_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_config(monkeypatch)
    provider = module.ElevenLabsTTSProvider()

    def timeout(*_args: object, **_kwargs: object) -> object:
        message = "connection timed out"
        raise requests.Timeout(message)

    monkeypatch.setattr(module.requests, "post", timeout)
    with pytest.raises(ValueError, match="request failed"):
        provider.synthesize("Hello")

    class EmptyResponse:
        status_code = 200
        content = b""
        reason = "OK"
        headers: ClassVar[dict[str, str]] = {}

    monkeypatch.setattr(
        module.requests, "post", lambda *_args, **_kwargs: EmptyResponse()
    )
    with pytest.raises(ValueError, match="No audio data received"):
        provider.synthesize("Hello")


@pytest.mark.parametrize(
    ("voice_id", "model", "speed", "message"),
    [
        ("unknown", "eleven_v3", 1.0, "voice is not approved"),
        ("voice-1", "unknown", 1.0, "Unsupported ElevenLabs model"),
        ("voice-1", "eleven_v3", 1.3, "speed out of range"),
    ],
)
def test_synthesize_rejects_invalid_direct_settings(
    monkeypatch: pytest.MonkeyPatch,
    voice_id: str,
    model: str,
    speed: float,
    message: str,
) -> None:
    _patch_config(monkeypatch)
    with pytest.raises(ValueError, match=message):
        module.ElevenLabsTTSProvider().synthesize(
            "Hello",
            voice_settings=VoiceSettings(voice_id=voice_id, speed=speed),
            model=model,
        )


@pytest.mark.parametrize("speed", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_speed_at_validation_and_provider_boundaries(
    monkeypatch: pytest.MonkeyPatch, speed: float
) -> None:
    _patch_config(monkeypatch)

    with pytest.raises(ValueError, match="Invalid ElevenLabs speed"):
        module.ElevenLabsTTSProvider().synthesize(
            "Hello",
            voice_settings=VoiceSettings(voice_id="voice-1", speed=speed),
            model="eleven_v3",
        )

    with pytest.raises(AppError):
        validate_tts_settings_strict(
            provider="elevenlabs",
            model="eleven_v3",
            voice_id="voice-1",
            speed=speed,
            pitch=0,
            emotion="",
        )


def test_strict_validation_requires_approved_voice_model_and_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.api.tts as tts_api

    _patch_config(monkeypatch)
    tts_api._provider_instances.clear()

    settings = validate_tts_settings_strict(
        provider="elevenlabs",
        model="eleven_v3",
        voice_id="voice-1",
        speed=1.0,
        pitch=0,
        emotion="",
    )
    assert settings.provider == "elevenlabs"

    invalid_settings = [
        {"model": "", "voice_id": "voice-1", "speed": 1.0, "pitch": 0, "emotion": ""},
        {
            "model": "unknown",
            "voice_id": "voice-1",
            "speed": 1.0,
            "pitch": 0,
            "emotion": "",
        },
        {
            "model": "eleven_v3",
            "voice_id": "unknown",
            "speed": 1.0,
            "pitch": 0,
            "emotion": "",
        },
        {
            "model": "eleven_v3",
            "voice_id": "voice-1",
            "speed": 1.3,
            "pitch": 0,
            "emotion": "",
        },
        {
            "model": "eleven_v3",
            "voice_id": "voice-1",
            "speed": 1.0,
            "pitch": 1,
            "emotion": "",
        },
        {
            "model": "eleven_v3",
            "voice_id": "voice-1",
            "speed": 1.0,
            "pitch": 0,
            "emotion": "happy",
        },
    ]
    for values in invalid_settings:
        with pytest.raises(AppError):
            validate_tts_settings_strict(provider="elevenlabs", **values)


def test_config_endpoint_hides_unconfigured_provider_and_exposes_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.api.tts as tts_api

    monkeypatch.setattr(
        tts_api,
        "_PROVIDER_REGISTRY",
        {"elevenlabs": module.ElevenLabsTTSProvider},
    )
    monkeypatch.setattr(tts_api, "_PROVIDER_PRIORITY", ("elevenlabs",))
    monkeypatch.setattr(
        tts_api, "_resolve_credit_multiplier_label", lambda *_args: None
    )

    _patch_config(monkeypatch, api_key="", voices="")
    assert tts_api.get_all_provider_configs() == {"providers": [], "model_options": []}

    _patch_config(monkeypatch)
    monkeypatch.setattr(
        tts_api,
        "get_config",
        lambda key, default=None: (
            "minimax/speech-01-turbo" if key == "TTS_ALLOWED_MODELS" else default
        ),
    )
    assert tts_api.get_all_provider_configs() == {"providers": [], "model_options": []}

    monkeypatch.setattr(
        tts_api,
        "get_config",
        lambda key, default=None: (
            "elevenlabs/not-a-model" if key == "TTS_ALLOWED_MODELS" else default
        ),
    )
    assert tts_api.get_all_provider_configs() == {"providers": [], "model_options": []}

    subset_config = {
        "TTS_ALLOWED_MODELS": "elevenlabs/eleven_v3",
        "TTS_DEFAULT_MODEL": "elevenlabs/eleven_v3",
        "TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON": "",
    }
    monkeypatch.setattr(
        tts_api, "get_config", lambda key, default=None: subset_config.get(key, default)
    )
    subset = tts_api.get_all_provider_configs()

    assert [model["value"] for model in subset["providers"][0]["models"]] == [
        "eleven_v3"
    ]
    assert [item["value"] for item in subset["model_options"]] == [
        "elevenlabs/eleven_v3"
    ]

    allowed = ",".join(
        f"elevenlabs/{model['value']}" for model in module.ELEVENLABS_MODELS
    )
    config_values = {
        "TTS_ALLOWED_MODELS": allowed,
        "TTS_DEFAULT_MODEL": "elevenlabs/eleven_multilingual_v2",
        "TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON": "",
    }
    monkeypatch.setattr(
        tts_api, "get_config", lambda key, default=None: config_values.get(key, default)
    )

    config = tts_api.get_all_provider_configs()

    assert [provider["name"] for provider in config["providers"]] == ["elevenlabs"]
    assert [item["value"] for item in config["model_options"]] == allowed.split(",")
    assert [item["is_default"] for item in config["model_options"]] == [
        False,
        False,
        False,
        True,
    ]
