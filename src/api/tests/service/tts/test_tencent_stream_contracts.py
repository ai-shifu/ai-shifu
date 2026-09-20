"""Exercise Tencent transport cleanup, malformed streams and synthesis accounting."""

import base64
import json
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
import requests
from flaskr.api.tts import tencent_provider as tencent


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
