"""Protect WebSocket failure cleanup and provider timestamp normalization."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.api.tts import volcengine_provider as volc
from flaskr.api.tts.base import AudioSettings


class ImmediateEvent:
    """Make the provider's bounded waits deterministic without wall-clock delays."""

    def __init__(self) -> None:
        """Create an unset event."""
        self.ready = False

    def set(self) -> None:
        self.ready = True

    def wait(self, timeout: float) -> bool:
        assert timeout in {10, 60}
        return self.ready


@pytest.fixture
def websocket_scenario(monkeypatch: pytest.MonkeyPatch) -> object:
    def configure(mode: str) -> SimpleNamespace:
        state = SimpleNamespace(mode=mode, socket=None, thread=None)
        protocol = Mock()
        for phase in (
            "start_connection",
            "start_session",
            "task_request",
            "finish_session",
            "finish_connection",
        ):
            getattr(protocol, "encode_" + phase).return_value = phase.encode()

        def decode(message: bytes) -> SimpleNamespace:
            event_name = message.decode()
            if event_name == "malformed":
                error_message = "malformed frame"
                raise ValueError(error_message)
            event = getattr(volc.Event, event_name, None)
            return SimpleNamespace(
                event=event,
                message_type=volc.MessageType.ERROR_INFORMATION
                if event_name == "ERROR"
                else None,
                connection_id="connection",
                session_id="session",
                error_code=403,
                payload=b"a" * 1600
                if event_name == "TTS_RESPONSE"
                else {"reason": "rejected", "usage": {"characters": 5}},
            )

        protocol.decode_frame.side_effect = decode

        def socket_factory(_url: str, *, header: dict, **callbacks: object) -> Mock:
            socket = Mock()
            state.socket = socket
            state.headers = header

            def send(frame: bytes, *, opcode: int) -> None:
                assert opcode == 2
                if frame == b"start_connection":
                    if mode == "connection_timeout":
                        return
                    if mode == "socket_error":
                        callbacks["on_error"](socket, "socket failed")
                        return
                    if mode == "closed":
                        callbacks["on_close"](socket, 1000, "closed")
                        return
                    callbacks["on_message"](
                        socket,
                        b"CONNECTION_FAILED"
                        if mode == "connection_failed"
                        else b"CONNECTION_STARTED",
                    )
                elif frame == b"start_session":
                    if mode in {"session_timeout", "closed"}:
                        return
                    callbacks["on_message"](
                        socket,
                        b"SESSION_FAILED"
                        if mode == "session_failed"
                        else b"SESSION_STARTED",
                    )
                elif frame == b"finish_session":
                    if mode == "synthesis_timeout":
                        return
                    if mode in {"error_frame", "malformed"}:
                        callbacks["on_message"](
                            socket, b"ERROR" if mode == "error_frame" else b"malformed"
                        )
                        return
                    callbacks["on_message"](socket, "metadata")
                    callbacks["on_message"](socket, b"TTS_SENTENCE_START")
                    if mode != "empty":
                        callbacks["on_message"](socket, b"TTS_RESPONSE")
                    callbacks["on_message"](socket, b"SESSION_FINISHED")

            socket.send.side_effect = send
            socket.run_forever.side_effect = lambda **_: callbacks["on_open"](socket)
            socket.close.side_effect = lambda: callbacks["on_close"](
                socket, 1000, "done"
            )
            return socket

        def thread_factory(*, target: object, kwargs: dict) -> Mock:
            thread = Mock()
            thread.start.side_effect = lambda: target(**kwargs)
            state.thread = thread
            return thread

        monkeypatch.setattr(volc, "VolcengineProtocol", lambda: protocol)
        monkeypatch.setattr(
            volc,
            "get_config",
            lambda key: (
                "key"
                if key in {"VOLCENGINE_TTS_APP_KEY", "VOLCENGINE_TTS_ACCESS_KEY"}
                else None
            ),
        )
        monkeypatch.setattr(volc, "WEBSOCKET_AVAILABLE", True)
        monkeypatch.setattr(
            volc,
            "websocket",
            SimpleNamespace(
                WebSocketApp=socket_factory, ABNF=SimpleNamespace(OPCODE_BINARY=2)
            ),
        )
        monkeypatch.setattr(
            volc,
            "threading",
            SimpleNamespace(Lock=Mock, Event=ImmediateEvent, Thread=thread_factory),
        )
        state.provider = volc.VolcengineTTSProvider()
        return state

    return configure


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("connection_timeout", "Timeout waiting for connection"),
        ("connection_failed", "Connection failed"),
        ("socket_error", "socket failed"),
        ("closed", "Timeout waiting for TTS session to start"),
        ("session_timeout", "Timeout waiting for TTS session to start"),
        ("session_failed", "Session failed"),
        ("synthesis_timeout", "Timeout waiting for TTS synthesis"),
        ("error_frame", "Error 403"),
        ("malformed", "malformed frame"),
        ("empty", "No audio data received"),
    ],
)
def test_failed_websocket_sessions_always_close_and_join(
    websocket_scenario: object, mode: str, message: str
) -> None:
    state = websocket_scenario(mode)
    with pytest.raises(ValueError, match=message):
        state.provider.synthesize("hello")
    state.socket.close.assert_called_once()
    state.thread.join.assert_called_once_with(timeout=5)
    assert state.thread.daemon is True
    sent = [call.args[0] for call in state.socket.send.call_args_list]
    if mode in {"connection_timeout", "connection_failed", "socket_error"}:
        assert sent == [b"start_connection"]
    elif mode in {"session_timeout", "session_failed", "closed"}:
        assert sent == [b"start_connection", b"start_session"]


@pytest.mark.parametrize(("bitrate", "expected_duration"), [(128000, 100), (0, 0)])
def test_audio_without_provider_duration_uses_bitrate_estimate(
    websocket_scenario: object, bitrate: int, expected_duration: int
) -> None:
    state = websocket_scenario("success")
    result = state.provider.synthesize(
        "hello", audio_settings=AudioSettings(bitrate=bitrate)
    )
    assert result.audio_data == b"a" * 1600
    assert result.duration_ms == expected_duration
    assert result.word_count == 5
    assert [call.args[0] for call in state.socket.send.call_args_list] == [
        b"start_connection",
        b"start_session",
        b"task_request",
        b"finish_session",
        b"finish_connection",
    ]
    state.socket.close.assert_called_once()


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("start_ms", "12.8", 13),
        ("startMs", -2, 0),
        ("start_ms", "invalid", 0),
        ("start", "0.12", 120),
        ("start", "invalid", 0),
        ("start", None, 0),
        ("start", "", 0),
    ],
)
def test_timestamp_aliases_normalize_units_and_invalid_values(
    key: str, raw: object, expected: int
) -> None:
    cues = volc._extract_volcengine_subtitle_cues(
        {"sentences": [None, {}, {"text": "hello", key: raw, "end_ms": 5}]},
        segment_index=-2,
    )
    assert cues == [
        {
            "text": "hello",
            "start_ms": expected,
            "end_ms": max(expected, 5),
            "segment_index": 0,
        }
    ]


def test_nested_subtitles_and_word_timing_produce_ordered_segment_indexes() -> None:
    cues = volc._extract_volcengine_subtitle_cues(
        {
            "subtitles": {
                "sentences": [{"text": "first", "start_ms": 0, "end_ms": 100}]
            },
            "words": ["noise", {"word": "second", "start_time": 0.1, "end_time": 0.3}],
        },
        segment_index=2,
    )
    assert cues == [
        {"text": "first", "start_ms": 0, "end_ms": 100, "segment_index": 2},
        {"text": "second", "start_ms": 100, "end_ms": 300, "segment_index": 3},
    ]


@pytest.mark.parametrize(
    "payload", [None, "noise", {}, {"words": [None]}, {"words": [{"word": " "}]}]
)
def test_empty_or_invalid_subtitles_do_not_invent_text(payload: object) -> None:
    assert volc._extract_volcengine_subtitle_cues(payload) == []


def test_missing_websocket_package_rejects_configuration_and_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(volc, "WEBSOCKET_AVAILABLE", False)
    provider = volc.VolcengineTTSProvider()
    assert not provider.is_configured()
    with pytest.raises(ValueError, match="websocket-client package is not installed"):
        provider.synthesize("hello")


@pytest.mark.parametrize("text", ["", " \n "])
def test_empty_text_is_rejected_before_connecting(
    monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    monkeypatch.setattr(volc, "WEBSOCKET_AVAILABLE", True)
    with pytest.raises(ValueError, match="Text cannot be empty"):
        volc.VolcengineTTSProvider().synthesize(text)


def test_missing_credentials_are_rejected_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(volc, "WEBSOCKET_AVAILABLE", True)
    monkeypatch.setattr(volc, "get_config", lambda _: None)
    with pytest.raises(ValueError, match="credentials are not configured"):
        volc.VolcengineTTSProvider().synthesize("hello")
