"""Verify MiniMax provider decoding, external subtitle formats and stream cleanup."""

import json
from unittest.mock import Mock

import pytest
import requests
from flaskr.api.tts import minimax_provider as minimax


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
