"""Verify MiniMax provider decoding, external subtitle formats and stream cleanup."""

import json
from unittest.mock import Mock

import pytest
import requests
from flaskr.api.tts import minimax_provider as minimax
from flaskr.api.tts.base import VoiceSettings


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> minimax.MinimaxTTSProvider:
    monkeypatch.setattr(
        minimax,
        "get_config",
        lambda key: "test-key" if key == "MINIMAX_API_KEY" else None,
    )
    monkeypatch.setattr(minimax, "acquire_tts_rpm_slot", Mock())
    return minimax.MinimaxTTSProvider()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([{"text": "one"}, None], [{"text": "one"}]),
        ({"subtitles": [{"text": "two"}, "noise"]}, [{"text": "two"}]),
        ({"data": [{"text": "three"}]}, [{"text": "three"}]),
        ({"data": {"subtitles": [{"text": "four"}, None]}}, [{"text": "four"}]),
        ({"other": []}, []),
        ("noise", []),
    ],
)
def test_downloaded_subtitle_shapes_preserve_only_object_entries(
    monkeypatch: pytest.MonkeyPatch, payload: object, expected: list
) -> None:
    response = Mock()
    response.json.return_value = payload
    get = Mock(return_value=response)
    monkeypatch.setattr(minimax.requests, "get", get)
    assert (
        minimax._fetch_minimax_subtitle_file("https://audio.invalid/subtitles")
        == expected
    )
    get.assert_called_once_with("https://audio.invalid/subtitles", timeout=20)
    response.raise_for_status.assert_called_once()


@pytest.mark.parametrize("stage", ["empty", "request", "status", "decode"])
def test_missing_or_failed_subtitle_download_does_not_break_audio(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    response = Mock()
    get = Mock(return_value=response)
    if stage == "request":
        get.side_effect = requests.ConnectionError("offline")
    elif stage == "status":
        response.raise_for_status.side_effect = requests.HTTPError("unavailable")
    elif stage == "decode":
        response.json.side_effect = ValueError("invalid JSON")
    monkeypatch.setattr(minimax.requests, "get", get)
    assert (
        minimax._fetch_minimax_subtitle_file(
            "" if stage == "empty" else "https://audio.invalid/subtitles"
        )
        == []
    )
    if stage == "empty":
        get.assert_not_called()


@pytest.mark.parametrize("container", ["data", "extra_info", "root"])
@pytest.mark.parametrize(
    "key", ["subtitles", "subtitle", "subtitle_file", "subtitle_url", "subtitles_url"]
)
def test_stream_accepts_nested_and_downloaded_subtitle_locations(
    monkeypatch: pytest.MonkeyPatch, container: str, key: str
) -> None:
    cue = {"text": "spoken", "start_ms": 0, "end_ms": 100}
    fetch = Mock(return_value=[cue])
    monkeypatch.setattr(minimax, "_fetch_minimax_subtitle_file", fetch)
    value = (
        {"data": {"subtitle": cue}}
        if key in {"subtitle", "subtitles"}
        else "https://audio.invalid/subtitles"
    )
    content = {key: value}
    message = content if container == "root" else {container: content}
    assert minimax._extract_minimax_subtitles(message) == [cue]
    assert fetch.call_count == int(isinstance(value, str))


@pytest.mark.parametrize("text", ["", " \n "])
def test_empty_input_is_rejected_before_opening_transport(
    provider: minimax.MinimaxTTSProvider, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    post = Mock()
    monkeypatch.setattr(minimax.requests, "post", post)
    with pytest.raises(ValueError, match="Text cannot be empty"):
        provider.synthesize(text)
    with pytest.raises(ValueError, match="Text cannot be empty"):
        list(provider.stream_synthesize(text))
    post.assert_not_called()


def test_missing_api_key_rejects_both_transport_modes(
    provider: minimax.MinimaxTTSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(minimax, "get_config", lambda _: None)
    post = Mock()
    monkeypatch.setattr(minimax.requests, "post", post)
    with pytest.raises(ValueError, match="not configured"):
        provider.synthesize("hello")
    with pytest.raises(ValueError, match="not configured"):
        list(provider.stream_synthesize("hello"))
    post.assert_not_called()


@pytest.mark.parametrize(
    ("code", "message"), [(2054, "voice is not available"), (1000, "API error: 1000")]
)
def test_nonstream_provider_error_is_actionable(
    provider: minimax.MinimaxTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    message: str,
) -> None:
    response = Mock()
    response.json.return_value = {
        "base_resp": {"status_code": code, "status_msg": "rejected"}
    }
    monkeypatch.setattr(minimax.requests, "post", Mock(return_value=response))
    with pytest.raises(ValueError, match=message):
        provider.synthesize("hello")


def test_nonstream_missing_audio_is_rejected(
    provider: minimax.MinimaxTTSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = Mock()
    response.json.return_value = {"data": {}}
    monkeypatch.setattr(minimax.requests, "post", Mock(return_value=response))
    with pytest.raises(ValueError, match="No audio data"):
        provider.synthesize("hello")


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("invalid json", "Invalid MiniMax HTTP streaming JSON"),
        (
            json.dumps({"data": {"audio": "invalid hex"}}),
            "Invalid MiniMax HTTP streaming audio hex",
        ),
        (
            json.dumps(
                {
                    "base_resp": {"status_code": 1000, "status_msg": "rejected"},
                    "trace_id": "trace",
                }
            ),
            "1000 - rejected, trace_id=trace",
        ),
    ],
)
def test_stream_errors_propagate_and_close_response(
    provider: minimax.MinimaxTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    line: str,
    message: str,
) -> None:
    response = Mock()
    response.iter_lines.return_value = iter(["data: " + line])
    monkeypatch.setattr(minimax.requests, "post", Mock(return_value=response))
    with pytest.raises(ValueError, match=message):
        list(provider.stream_synthesize("hello"))
    response.close.assert_called_once()


def test_stream_http_error_closes_response(
    provider: minimax.MinimaxTTSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("provider unavailable")
    monkeypatch.setattr(minimax.requests, "post", Mock(return_value=response))
    with pytest.raises(requests.HTTPError, match="provider unavailable"):
        list(provider.stream_synthesize("hello"))
    response.close.assert_called_once()


@pytest.mark.parametrize("cancel", [True, False])
def test_stream_completion_or_consumer_cancellation_closes_response(
    provider: minimax.MinimaxTTSProvider, monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    response = Mock()
    response.iter_lines.return_value = iter(
        ["", "data: " + json.dumps({"data": {"audio": b"audio".hex()}}), "data: [DONE]"]
    )
    monkeypatch.setattr(minimax.requests, "post", Mock(return_value=response))
    stream = provider.stream_synthesize("hello")
    assert next(stream).audio_data == b"audio"
    if cancel:
        stream.close()
    else:
        assert list(stream) == []
    response.close.assert_called_once()


@pytest.mark.parametrize(
    ("model", "emotion", "included"),
    [
        ("speech-01-turbo", "happy", True),
        ("speech-2.8-turbo", "happy", False),
        ("speech-01-turbo", "neutral", False),
        ("speech-01-turbo", "unknown", False),
    ],
)
def test_emotion_is_sent_only_for_supported_model_family(
    model: str, emotion: str, included: bool
) -> None:
    settings = minimax._build_minimax_voice_setting(
        VoiceSettings(voice_id="voice", pitch=None, emotion=emotion), model=model
    )
    assert ("emotion" in settings) is included
    assert "pitch" not in settings
    if included:
        assert settings["emotion"] == emotion


@pytest.mark.parametrize("raw", ["bad", object()])
def test_invalid_numeric_configuration_uses_documented_defaults(
    monkeypatch: pytest.MonkeyPatch, raw: object
) -> None:
    monkeypatch.setattr(minimax, "get_config", lambda _: raw)
    assert minimax._coerce_float_config("WAIT", 10.0) == 10.0
    assert minimax._coerce_int_config("RPM", 2) == 2


@pytest.mark.parametrize("raw", [{"speech-2.8-turbo": "bad"}, "[]", "invalid json"])
def test_invalid_rpm_overrides_do_not_replace_tier_defaults(
    monkeypatch: pytest.MonkeyPatch, raw: object
) -> None:
    monkeypatch.setattr(minimax, "get_config", lambda _: raw)
    assert minimax._resolve_minimax_rpm_limit("speech-2.8-turbo") == 200


@pytest.mark.parametrize("failure_point", ["http_status", "iteration"])
def test_close_failure_preserves_original_transport_error(
    provider: minimax.MinimaxTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    original_error = requests.ConnectionError("stream disconnected")
    response = Mock()
    response.close.side_effect = OSError("connection cleanup failed")
    if failure_point == "http_status":
        original_error = requests.HTTPError("provider unavailable")
        response.raise_for_status.side_effect = original_error
    else:
        response.iter_lines.side_effect = original_error
    monkeypatch.setattr(minimax.requests, "post", Mock(return_value=response))

    with pytest.raises(type(original_error)) as exc:
        list(provider.stream_synthesize("hello"))

    assert exc.value is original_error
    response.close.assert_called_once()
    assert "Failed to close MiniMax TTS streaming response" in caplog.text


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("invalid json", "Invalid MiniMax HTTP streaming JSON"),
        (
            json.dumps({"data": {"audio": "invalid hex"}}),
            "Invalid MiniMax HTTP streaming audio hex",
        ),
        (
            json.dumps({"base_resp": {"status_code": 1000, "status_msg": "rejected"}}),
            "1000 - rejected",
        ),
    ],
)
def test_close_failure_preserves_stream_decoding_or_provider_error(
    provider: minimax.MinimaxTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
    message: str,
) -> None:
    response = Mock()
    response.iter_lines.return_value = iter(["data: " + payload])
    response.close.side_effect = OSError("connection cleanup failed")
    monkeypatch.setattr(minimax.requests, "post", Mock(return_value=response))

    with pytest.raises(ValueError, match=message):
        list(provider.stream_synthesize("hello"))

    response.close.assert_called_once()


@pytest.mark.parametrize("cancel", [False, True])
def test_close_failure_does_not_fail_completed_or_cancelled_stream(
    provider: minimax.MinimaxTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = Mock()
    response.iter_lines.return_value = iter(
        ["data: " + json.dumps({"data": {"audio": b"audio".hex()}}), "data: [DONE]"]
    )
    response.close.side_effect = OSError("connection cleanup failed")
    monkeypatch.setattr(minimax.requests, "post", Mock(return_value=response))
    stream = provider.stream_synthesize("hello")

    assert next(stream).audio_data == b"audio"
    response.close.assert_not_called()
    if cancel:
        stream.close()
    else:
        assert list(stream) == []

    response.close.assert_called_once()
    assert list(stream) == []
    assert "Failed to close MiniMax TTS streaming response" in caplog.text
