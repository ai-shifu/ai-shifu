"""Exercise Tencent transport cleanup, malformed streams and synthesis accounting."""

import base64
import json
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
import requests
from flaskr.api.tts import tencent_provider as tencent
from flaskr.api.tts.base import AudioSettings, VoiceSettings


class StreamingResponse:
    """Provide a finite provider stream and observable connection cleanup."""

    def __init__(
        self,
        lines: list,
        error: Exception | None = None,
        *,
        stream_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        """Store response lines and optional status, stream, or cleanup failures."""
        self.lines = lines
        self.error = error
        self.closed = False
        self.close_count = 0
        self.stream_error = stream_error
        self.close_error = close_error

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def iter_lines(self, *, decode_unicode: bool) -> Iterator:
        assert decode_unicode
        yield from self.lines
        if self.stream_error:
            raise self.stream_error

    def close(self) -> None:
        self.closed = True
        self.close_count += 1
        if self.close_error:
            raise self.close_error


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> tencent.TencentTTSProvider:
    settings = {
        "TENCENT_TTS_APP_ID": "1234",
        "TENCENT_TTS_SECRET_ID": "test-id",
        "TENCENT_TTS_SECRET_KEY": "test-key",
    }
    monkeypatch.setattr(
        tencent, "get_config", lambda key, default=None: settings.get(key, default)
    )
    return tencent.TencentTTSProvider()


def _event(**fields: object) -> str:
    return "data: " + json.dumps(fields)


@pytest.mark.parametrize(
    "missing", ["TENCENT_TTS_APP_ID", "TENCENT_TTS_SECRET_ID", "TENCENT_TTS_SECRET_KEY"]
)
def test_unconfigured_provider_rejects_stream_and_synthesis_without_transport(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    settings = {
        "TENCENT_TTS_APP_ID": "1234",
        "TENCENT_TTS_SECRET_ID": "test-id",
        "TENCENT_TTS_SECRET_KEY": "test-key",
    }
    settings[missing] = ""
    monkeypatch.setattr(
        tencent, "get_config", lambda key, default=None: settings.get(key, default)
    )
    post = Mock()
    monkeypatch.setattr(tencent.requests, "post", post)
    provider = tencent.TencentTTSProvider()
    assert not provider.is_configured()
    with pytest.raises(ValueError, match="not configured"):
        list(provider.stream_synthesize("hello"))
    with pytest.raises(ValueError, match="not configured"):
        provider.synthesize("hello")
    post.assert_not_called()


@pytest.mark.parametrize("text", ["", " \n\t "])
def test_empty_text_never_opens_provider_connection(
    provider: tencent.TencentTTSProvider, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    post = Mock()
    monkeypatch.setattr(tencent.requests, "post", post)
    with pytest.raises(ValueError, match="Text cannot be empty"):
        list(provider.stream_synthesize(text))
    with pytest.raises(ValueError, match="Text cannot be empty"):
        provider.synthesize(text)
    post.assert_not_called()


def test_stream_ignores_sse_metadata_and_stops_at_final_audio(
    provider: tencent.TencentTTSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = base64.b64encode(b"pcm").decode()
    response = StreamingResponse(
        [
            "",
            ": keepalive",
            "id: 1",
            "retry: 5",
            "event: audio",
            _event(Type="heartbeat"),
            _event(Audio=audio, Final="yes", Seq="bad"),
            "not valid JSON after final",
        ]
    )
    post = Mock(return_value=response)
    monkeypatch.setattr(tencent.requests, "post", post)
    chunks = list(
        provider.stream_synthesize(
            "hello", VoiceSettings(voice_id=""), AudioSettings(format="wav")
        )
    )
    assert len(chunks) == 1
    assert chunks[0].audio_data == b"pcm"
    assert chunks[0].seq == 0
    assert chunks[0].is_final
    assert response.closed
    payload = json.loads(post.call_args.kwargs["data"])
    assert payload["Voice"]["VoiceId"] == tencent.TENCENT_DEFAULT_VOICE_ID
    assert payload["AudioFormat"]["Format"] == "pcm"


def test_stream_accepts_byte_lines_and_done_marker_after_audio(
    provider: tencent.TencentTTSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = StreamingResponse(
        [
            _event(Audio=base64.b64encode(b"pcm").decode()).encode(),
            b"data: [DONE]",
            b"ignored",
        ]
    )
    monkeypatch.setattr(tencent.requests, "post", Mock(return_value=response))
    assert [chunk.audio_data for chunk in provider.stream_synthesize("hello")] == [
        b"pcm"
    ]
    assert response.closed


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([], "No audio data"),
        (["data: [DONE]"], "No audio data"),
        ([_event(Final=True)], "No audio data"),
        (["data: invalid json"], "Invalid Tencent TTS SSE JSON"),
        ([_event(Audio="not/base64?")], "Invalid Tencent TTS SSE audio base64"),
        (
            [_event(Type="error", Code="Denied", Message="not available")],
            "Tencent TTS error Denied",
        ),
    ],
)
def test_invalid_or_empty_stream_is_rejected_and_closed(
    provider: tencent.TencentTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    lines: list,
    message: str,
) -> None:
    response = StreamingResponse(lines)
    monkeypatch.setattr(tencent.requests, "post", Mock(return_value=response))
    with pytest.raises(ValueError, match=message):
        list(provider.stream_synthesize("hello"))
    assert response.closed


@pytest.mark.parametrize("close_fails", [False, True])
def test_http_error_closes_response_before_propagating(
    provider: tencent.TencentTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    close_fails: bool,
) -> None:
    error = requests.HTTPError("provider unavailable")
    response = StreamingResponse(
        [],
        error=error,
        close_error=OSError("connection cleanup failed") if close_fails else None,
    )
    monkeypatch.setattr(tencent.requests, "post", Mock(return_value=response))
    with pytest.raises(requests.HTTPError, match="provider unavailable"):
        list(provider.stream_synthesize("hello"))
    assert response.closed
    assert response.close_count == 1


def test_consumer_cancellation_closes_open_response(
    provider: tencent.TencentTTSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = StreamingResponse(
        [
            _event(Audio=base64.b64encode(b"first").decode()),
            _event(Audio=base64.b64encode(b"second").decode()),
        ]
    )
    monkeypatch.setattr(tencent.requests, "post", Mock(return_value=response))
    stream = provider.stream_synthesize("hello")
    assert next(stream).audio_data == b"first"
    stream.close()
    assert response.closed


@pytest.mark.parametrize(
    ("pcm", "encoded", "message"),
    [(b"", b"mp3", "No audio data"), (b"pcm", b"", "No decodable audio data")],
)
def test_synthesis_rejects_missing_or_undecodable_audio(
    provider: tencent.TencentTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    pcm: bytes,
    encoded: bytes,
    message: str,
) -> None:
    monkeypatch.setattr(
        provider,
        "stream_synthesize",
        lambda **_: iter([tencent.TencentSSEStreamChunk(pcm)]),
    )
    monkeypatch.setattr(
        tencent, "_export_tencent_pcm_to_mp3", lambda *_args, **_kwargs: encoded
    )
    with pytest.raises(ValueError, match=message):
        provider.synthesize("hello")


def test_synthesis_offsets_subtitles_across_sessions_and_bills_original_text(
    provider: tencent.TencentTTSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    texts = []

    def stream(**kwargs: object) -> Iterator[tencent.TencentSSEStreamChunk]:
        texts.append(kwargs["text"])
        yield tencent.TencentSSEStreamChunk(
            b"\0" * 3200,
            subtitles=[{"Text": kwargs["text"], "BeginTime": 0, "EndTime": 100}],
        )

    monkeypatch.setattr(tencent, "TENCENT_MAX_SESSION_CHARS", 3)
    monkeypatch.setattr(provider, "stream_synthesize", stream)
    monkeypatch.setattr(tencent, "export_pcm_to_mp3", lambda *_args, **_kwargs: b"mp3")
    monkeypatch.setattr(
        tencent, "concat_audio_best_effort", lambda *_args, **_kwargs: b""
    )
    result = provider.synthesize(
        "abcde", VoiceSettings(voice_id=""), AudioSettings(sample_rate=0)
    )
    assert texts == ["abc.", "de."]
    assert result.audio_data == b"mp3mp3"
    assert result.duration_ms == 200
    assert result.sample_rate == 16000
    assert result.word_count == result.usage_characters == 5
    assert [
        (cue["text"], cue["start_ms"], cue["end_ms"]) for cue in result.subtitle_cues
    ] == [("abc.", 0, 100), ("de.", 100, 200)]


@pytest.mark.parametrize(
    ("decoded_ms", "subtitle_ms", "expected"),
    [(240, 400, 240), (0, 400, 400), (0, 0, 0)],
)
def test_synthesis_duration_falls_back_to_decoded_audio_then_subtitles(
    provider: tencent.TencentTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    decoded_ms: int,
    subtitle_ms: int,
    expected: int,
) -> None:
    subtitles = (
        [{"Text": "hello.", "BeginTime": 0, "EndTime": subtitle_ms}]
        if subtitle_ms
        else []
    )
    monkeypatch.setattr(
        provider,
        "stream_synthesize",
        lambda **_: iter([tencent.TencentSSEStreamChunk(b"pcm", subtitles=subtitles)]),
    )
    monkeypatch.setattr(
        tencent, "_tencent_pcm_duration_ms", lambda *_args, **_kwargs: 0
    )
    monkeypatch.setattr(
        tencent, "_export_tencent_pcm_to_mp3", lambda *_args, **_kwargs: b"mp3"
    )
    monkeypatch.setattr(
        tencent, "try_get_audio_duration_ms", lambda *_args, **_kwargs: decoded_ms
    )
    monkeypatch.setattr(
        tencent, "concat_audio_best_effort", lambda *_args, **_kwargs: b""
    )
    assert provider.synthesize("hello").duration_ms == expected


@pytest.mark.parametrize(
    ("code", "final", "is_final"),
    [
        (None, None, False),
        (0, 0, False),
        ("0", 1, True),
        ("", "true", True),
        (0.0, "no", False),
    ],
)
def test_stream_message_coerces_success_codes_and_final_markers(
    code: object, final: object, is_final: bool
) -> None:
    chunk = tencent.parse_tencent_sse_message(
        {"response": {"code": code, "is_final": final}}, request_text="hello"
    )
    assert chunk is not None
    assert chunk.is_final is is_final
    assert chunk.audio_data == b""


def test_error_metadata_survives_outer_envelope_and_fallback_message() -> None:
    with pytest.raises(tencent.TencentTTSError) as error:
        tencent.parse_tencent_sse_message(
            {"Response": {"Code": 5}, "request_id": "request", "message_id": "message"},
            request_text="hello",
        )
    assert error.value.code == 5
    assert error.value.request_id == "request"
    assert error.value.message_id == "message"
    assert "provider error" in str(error.value)


def test_configuration_catalog_returns_defensive_voice_copy(
    provider: tencent.TencentTTSProvider,
) -> None:
    voices = provider.get_supported_voices()
    voices[0]["label"] = "changed"
    assert provider.get_supported_voices()[0]["label"] != "changed"
    assert "" not in provider.get_supported_emotions()
    assert provider._split_text(" \n ") == []


def _audio_line() -> str:
    return "data: " + json.dumps(
        {"Response": {"Audio": base64.b64encode(b"audio").decode("ascii"), "Final": 0}}
    )


@pytest.mark.parametrize("close_fails", [False, True])
def test_successful_stream_closes_response_without_discarding_audio(
    provider: tencent.TencentTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    close_fails: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = StreamingResponse(
        [_audio_line(), "data: [DONE]"],
        close_error=OSError("connection cleanup failed") if close_fails else None,
    )
    monkeypatch.setattr(tencent.requests, "post", Mock(return_value=response))

    chunks = list(provider.stream_synthesize("hello"))

    assert [chunk.audio_data for chunk in chunks] == [b"audio"]
    assert response.closed
    assert response.close_count == 1
    if close_fails:
        assert "Failed to close Tencent TTS streaming response" in caplog.text


@pytest.mark.parametrize("close_fails", [False, True])
def test_consumer_cancellation_closes_response_without_raising_cleanup_error(
    provider: tencent.TencentTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    close_fails: bool,
) -> None:
    response = StreamingResponse(
        [_audio_line(), "data: [DONE]"],
        close_error=OSError("connection cleanup failed") if close_fails else None,
    )
    monkeypatch.setattr(tencent.requests, "post", Mock(return_value=response))
    stream = provider.stream_synthesize("hello")

    assert next(stream).audio_data == b"audio"
    assert response.close_count == 0
    stream.close()

    assert response.closed
    assert response.close_count == 1
    assert list(stream) == []


@pytest.mark.parametrize("close_fails", [False, True])
def test_iteration_failure_closes_response_and_preserves_original_error(
    provider: tencent.TencentTTSProvider,
    monkeypatch: pytest.MonkeyPatch,
    close_fails: bool,
) -> None:
    original_error = requests.ConnectionError("stream disconnected")
    response = StreamingResponse(
        [_audio_line()],
        stream_error=original_error,
        close_error=OSError("connection cleanup failed") if close_fails else None,
    )
    monkeypatch.setattr(tencent.requests, "post", Mock(return_value=response))
    stream = provider.stream_synthesize("hello")

    assert next(stream).audio_data == b"audio"
    with pytest.raises(requests.ConnectionError) as exc:
        next(stream)

    assert exc.value is original_error
    assert response.closed
    assert response.close_count == 1
    assert list(stream) == []
