import base64

import requests

from flaskr.api.tts.base import AudioSettings, VoiceSettings
from flaskr.api.tts.volcengine_http_provider import (
    VOLCENGINE_HTTP_TTS_URL,
    VolcengineHttpTTSProvider,
)
from flaskr.service.tts.pipeline import split_text_for_tts
from flaskr.service.tts.validation import validate_tts_settings_strict


def test_volcengine_http_synthesize_success(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APP_KEY", "test-app")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_KEY", "test-token")
    monkeypatch.setenv("VOLCENGINE_TTS_RESOURCE_ID", "volcano_tts")

    audio_bytes = b"audio-bytes"
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "reqid": "reqid",
                "code": 3000,
                "message": "Success",
                "sequence": -1,
                "data": audio_base64,
                "addition": {"duration": "1234"},
            }

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    provider = VolcengineHttpTTSProvider()
    voice_settings = VoiceSettings(
        voice_id="BV700_streaming",
        speed=1.2,
        pitch=10,
        emotion="happy",
        volume=1.0,
    )
    audio_settings = AudioSettings(format="mp3", sample_rate=24000, bitrate=128000)

    result = provider.synthesize(
        "Hello world",
        voice_settings=voice_settings,
        audio_settings=audio_settings,
        model="volcano_tts",
    )

    assert result.audio_data == audio_bytes
    assert result.duration_ms == 1234
    assert captured["url"] == VOLCENGINE_HTTP_TTS_URL
    assert captured["headers"]["Authorization"] == "Bearer;test-token"
    assert captured["json"]["app"]["cluster"] == "volcano_tts"
    assert captured["json"]["audio"]["voice_type"] == "BV700_streaming"
    assert captured["json"]["audio"]["pitch_ratio"] == 1.0
    assert captured["json"]["audio"]["emotion"] == "happy"


def test_volcengine_http_provider_config_includes_configured_cluster(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_RESOURCE_ID", "custom_cluster")
    provider = VolcengineHttpTTSProvider()
    config = provider.get_provider_config()
    model_values = {model["value"] for model in config.models}
    assert "custom_cluster" in model_values


def test_split_text_for_tts_volcengine_http_byte_limit():
    text = "é" * 600
    segments = split_text_for_tts(
        text, provider_name="volcengine_http", max_segment_chars=2000
    )
    assert segments
    assert all(len(segment.encode("utf-8")) <= 1024 for segment in segments)


def test_validate_tts_settings_strict_volcengine_http(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_RESOURCE_ID", "volcano_tts")
    settings = validate_tts_settings_strict(
        provider="volcengine_http",
        model="volcano_tts",
        voice_id="BV700_streaming",
        speed=1.0,
        pitch=10,
        emotion="happy",
    )
    assert settings.provider == "volcengine_http"
