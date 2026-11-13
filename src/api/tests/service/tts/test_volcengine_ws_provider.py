"""Verify volcengine WebSocket provider behavior."""

import threading
from types import SimpleNamespace
from uuid import UUID

import flaskr.api.tts as tts_api
import pytest
from flaskr.api.tts import volcengine_provider


@pytest.mark.parametrize(
    ("settings", "provider_name"),
    [
        ({"VOLCENGINE_TTS_API_KEY": "test-api-key"}, "volcengine"),
        ({"ARK_ACCESS_KEY_ID": "app", "ARK_SECRET_ACCESS_KEY": "token"}, "MiniMax"),
    ],
)
def test_volcengine_provider_auto_detection(
    monkeypatch: pytest.MonkeyPatch, settings: dict[str, str], provider_name: str
) -> None:
    monkeypatch.setattr(tts_api, "get_config", settings.get)
    monkeypatch.setattr(volcengine_provider, "get_config", settings.get)
    monkeypatch.setattr(tts_api, "_provider_instances", {})

    assert tts_api.get_tts_provider().provider_name == provider_name


def test_volcengine_ws_is_configured_with_only_api_key(
    monkeypatch: object,
) -> None:
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "test-api-key")
    monkeypatch.delenv("ARK_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ARK_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setattr(volcengine_provider, "WEBSOCKET_AVAILABLE", True)

    assert tts_api.is_tts_configured("volcengine") is True


@pytest.mark.parametrize(
    ("voice_id", "model", "resource_id", "use_subtitle"),
    [
        ("zh_female_vv_uranus_bigtts", "seed-tts-2.0", "seed-tts-2.0", True),
        ("zh_female_shuangkuaisisi_moon_bigtts", "seed-tts-1.0", "seed-tts-1.0", False),
        ("S_xxxxxxxxxx", "seed-tts-2.0", "seed-icl-2.0", True),
    ],
)
def test_volcengine_ws_uses_api_key_and_waits_for_session_started(
    monkeypatch: object,
    voice_id: str,
    model: str,
    resource_id: str,
    use_subtitle: bool,
) -> None:
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", " test-api-key ")
    monkeypatch.setattr(volcengine_provider, "WEBSOCKET_AVAILABLE", True)

    captured = {}

    class FakeProtocol:
        def encode_start_connection(self) -> object:
            return b"start_connection"

        def encode_start_session(self, **kwargs: object) -> object:
            captured["start_session_kwargs"] = kwargs
            return b"start_session"

        def encode_task_request(self, session_id: object, text: object) -> object:
            _ = (session_id, text)
            return b"task_request"

        def encode_finish_session(self, session_id: object) -> object:
            _ = session_id
            return b"finish_session"

        def encode_finish_connection(self) -> object:
            return b"finish_connection"

        def decode_frame(self, message: object) -> object:
            if message == b"connection_started":
                return SimpleNamespace(
                    event=volcengine_provider.Event.CONNECTION_STARTED,
                    message_type=None,
                    connection_id="conn",
                    session_id=None,
                    payload=None,
                    error_code=None,
                )
            if message == b"session_started":
                return SimpleNamespace(
                    event=volcengine_provider.Event.SESSION_STARTED,
                    message_type=None,
                    connection_id=None,
                    session_id="session",
                    payload=None,
                    error_code=None,
                )
            if message == b"tts_response":
                return SimpleNamespace(
                    event=volcengine_provider.Event.TTS_RESPONSE,
                    message_type=None,
                    connection_id=None,
                    session_id="session",
                    payload=b"audio-bytes",
                    error_code=None,
                )
            if message == b"sentence_end":
                return SimpleNamespace(
                    event=volcengine_provider.Event.TTS_SENTENCE_END,
                    message_type=None,
                    connection_id=None,
                    session_id="session",
                    payload={"res_params": {"duration_ms": 456}},
                    error_code=None,
                )
            if message == b"subtitle":
                return SimpleNamespace(
                    event=volcengine_provider.Event.TTS_SUBTITLE,
                    message_type=None,
                    connection_id=None,
                    session_id="session",
                    payload={
                        "text": "hello",
                        "words": [
                            {"word": "he", "start_time": "0", "end_time": "0.2"},
                            {"word": "llo", "start_time": "0.2", "end_time": "0.456"},
                        ],
                    },
                    error_code=None,
                )
            if message == b"session_finished":
                return SimpleNamespace(
                    event=volcengine_provider.Event.SESSION_FINISHED,
                    message_type=None,
                    connection_id=None,
                    session_id="session",
                    payload={},
                    error_code=None,
                )
            error_message = f"unexpected frame: {message!r}"
            raise AssertionError(error_message)

    class FakeWebSocketApp:
        def __init__(
            self,
            url: object,
            header: object,
            on_message: object,
            on_error: object,
            on_close: object,
            on_open: object,
        ) -> None:
            _ = on_error
            captured["url"] = url
            captured["headers"] = header
            self.on_message = on_message
            self.on_close = on_close
            self.on_open = on_open
            self.sent = []
            self.session_started_sent = False
            captured["ws"] = self

        def run_forever(self, **kwargs: object) -> None:
            _ = kwargs
            self.on_open(self)

        def send(self, frame: object, opcode: object = None) -> None:
            _ = opcode
            self.sent.append(frame)
            if frame == b"start_connection":
                self.on_message(self, b"connection_started")
                return
            if frame == b"start_session":
                timer = threading.Timer(0.15, self._emit_session_started)
                timer.daemon = True
                timer.start()
                return
            if frame == b"task_request":
                assert self.session_started_sent is True
                return
            if frame == b"finish_session":
                self.on_message(self, b"tts_response")
                self.on_message(self, b"sentence_end")
                self.on_message(self, b"subtitle")
                self.on_message(self, b"session_finished")

        def _emit_session_started(self) -> None:
            self.session_started_sent = True
            self.on_message(self, b"session_started")

        def close(self) -> None:
            self.on_close(self, None, None)

    fake_websocket = SimpleNamespace(
        ABNF=SimpleNamespace(OPCODE_BINARY=2),
        WebSocketApp=FakeWebSocketApp,
    )

    monkeypatch.setattr(volcengine_provider, "VolcengineProtocol", FakeProtocol)
    monkeypatch.setattr(volcengine_provider, "websocket", fake_websocket)

    provider = volcengine_provider.VolcengineTTSProvider()
    result = provider.synthesize(
        "hello",
        voice_settings=volcengine_provider.VoiceSettings(voice_id=voice_id),
        model=model,
    )

    assert captured["url"] == volcengine_provider.VOLCENGINE_TTS_WS_URL
    headers = captured["headers"]
    assert UUID(headers["X-Api-Connect-Id"]).version == 4
    assert headers == {
        "X-Api-Key": "test-api-key",
        "X-Api-Resource-Id": resource_id,
        "X-Api-Connect-Id": headers["X-Api-Connect-Id"],
    }
    assert result.audio_data == b"audio-bytes"
    assert result.duration_ms == 456
    assert captured["start_session_kwargs"]["enable_timestamp"] is not use_subtitle
    assert captured["start_session_kwargs"]["enable_subtitle"] is use_subtitle
    assert result.subtitle_cues == [
        {
            "text": "hello",
            "start_ms": 0,
            "end_ms": 456,
            "segment_index": 0,
        }
    ]
    assert captured["ws"].sent == [
        b"start_connection",
        b"start_session",
        b"task_request",
        b"finish_session",
        b"finish_connection",
    ]
