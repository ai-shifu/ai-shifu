"""Verify cloud speech providers reject unusable responses before audio publication."""

import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.api.tts import elevenlabs_provider as elevenlabs
from flaskr.api.tts import gemini_provider as gemini
from flaskr.api.tts.base import VoiceSettings


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    configuration = {
        "ELEVENLABS_API_KEY": "fixture-key",
        "ELEVENLABS_TTS_VOICES_JSON": [{"value": "voice-1", "label": "Narrator"}],
        "GEMINI_API_KEY": "fixture-key",
        "GEMINI_TTS_ENABLED": True,
    }
    monkeypatch.setattr(elevenlabs, "get_config", configuration.get)
    monkeypatch.setattr(gemini, "get_config", configuration.get)
    response = Mock(status_code=200, headers={})
    post = Mock(return_value=response)
    monkeypatch.setattr(elevenlabs.requests, "post", post)
    transcoder = Mock(return_value=b"mp3")
    monkeypatch.setattr(gemini, "export_pcm_to_mp3", transcoder)
    return SimpleNamespace(
        configuration=configuration, response=response, post=post, transcoder=transcoder
    )


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("ELEVENLABS_API_KEY", "", "API_KEY is not configured"),
        ("ELEVENLABS_TTS_VOICES_JSON", " ", "no valid approved voices"),
        ("ELEVENLABS_TTS_VOICES_JSON", None, "no valid approved voices"),
        ("ELEVENLABS_TTS_VOICES_JSON", "broken JSON", "no valid approved voices"),
    ],
)
def test_elevenlabs_missing_or_invalid_configuration_never_sends_request(
    cloud: SimpleNamespace, setting: str, value: object, message: str
) -> None:
    cloud.configuration[setting] = value
    with pytest.raises(ValueError, match=message):
        elevenlabs.ElevenLabsTTSProvider().synthesize("Speech")
    cloud.post.assert_not_called()


@pytest.mark.parametrize("text", ["", " \n "])
def test_elevenlabs_empty_input_never_sends_request(
    cloud: SimpleNamespace, text: str
) -> None:
    with pytest.raises(ValueError, match="Text cannot be empty"):
        elevenlabs.ElevenLabsTTSProvider().synthesize(text)
    cloud.post.assert_not_called()


@pytest.mark.parametrize("provider_name", ["elevenlabs", "gemini"])
@pytest.mark.parametrize("speed", [None, "invalid"])
def test_non_numeric_voice_speed_is_rejected_without_network(
    cloud: SimpleNamespace, provider_name: str, speed: object
) -> None:
    provider = (
        elevenlabs.ElevenLabsTTSProvider()
        if provider_name == "elevenlabs"
        else gemini.GeminiTTSProvider()
    )
    voice = provider.get_default_voice_settings()
    voice.speed = speed
    with pytest.raises(ValueError, match=r"Invalid .* speed") as caught:
        provider.synthesize("Speech", voice_settings=voice)
    assert isinstance(caught.value.__cause__, (TypeError, ValueError))
    cloud.post.assert_not_called()


@pytest.mark.parametrize("provider_name", ["elevenlabs", "gemini"])
@pytest.mark.parametrize("shape", ["invalid-json", "scalar", "status", "message"])
def test_provider_error_variants_redact_speech_and_preserve_a_bounded_reason(
    cloud: SimpleNamespace, provider_name: str, shape: str
) -> None:
    text = "private request sentence"
    reason = f"Unavailable: {text} " + "x" * 700
    cloud.response.status_code = 503
    cloud.response.reason = reason
    if shape == "invalid-json":
        cloud.response.json.side_effect = ValueError("invalid JSON")
    elif shape == "scalar":
        cloud.response.json.return_value = []
    elif shape == "status":
        cloud.response.json.return_value = {
            "detail" if provider_name == "elevenlabs" else "error": {"status": reason}
        }
    else:
        cloud.response.json.return_value = {"message": reason}
    provider = (
        elevenlabs.ElevenLabsTTSProvider()
        if provider_name == "elevenlabs"
        else gemini.GeminiTTSProvider()
    )
    with pytest.raises(ValueError, match="HTTP 503") as caught:
        provider.synthesize(text)
    message = str(caught.value)
    assert text not in message
    assert "[redacted]" in message
    assert len(message.split(": ", 1)[1]) == 500
    cloud.transcoder.assert_not_called()
    cloud.post.assert_called_once()


@pytest.mark.parametrize("content", [None, {"parts": {}}, {"parts": [None, 1]}])
def test_gemini_malformed_audio_parts_never_reach_transcoder(
    cloud: SimpleNamespace, content: object
) -> None:
    cloud.response.json.return_value = {"candidates": [{"content": content}]}
    with pytest.raises(ValueError, match="No audio data received"):
        gemini.GeminiTTSProvider().synthesize("Speech")
    cloud.transcoder.assert_not_called()


@pytest.mark.parametrize(
    ("encoded", "message"),
    [("a", "undecodable audio payload"), ("@@@@", "No audio data received")],
)
def test_gemini_invalid_base64_is_not_published_as_audio(
    cloud: SimpleNamespace, encoded: str, message: str
) -> None:
    cloud.response.json.return_value = {
        "candidates": [{"content": {"parts": [{"inlineData": {"data": encoded}}]}}]
    }
    with pytest.raises(ValueError, match=message):
        gemini.GeminiTTSProvider().synthesize("Speech")
    cloud.transcoder.assert_not_called()


def test_gemini_snake_case_audio_parts_reach_transcoder_but_empty_output_fails(
    cloud: SimpleNamespace,
) -> None:
    pcm = b"\x00\x00" * 20
    cloud.response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        None,
                        {
                            "inline_data": {
                                "data": base64.b64encode(pcm).decode(),
                                "mime_type": "audio/L16;rate=16000",
                            }
                        },
                    ]
                }
            }
        ]
    }
    cloud.transcoder.return_value = b""
    with pytest.raises(ValueError, match="No decodable audio data"):
        gemini.GeminiTTSProvider().synthesize(
            "Speech", voice_settings=VoiceSettings(voice_id="Kore", speed=1)
        )
    cloud.transcoder.assert_called_once_with(pcm, sample_rate=16000)
