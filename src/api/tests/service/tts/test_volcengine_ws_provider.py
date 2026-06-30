import threading
from types import SimpleNamespace

import flaskr.api.tts.volcengine_provider as volcengine_provider


def test_volcengine_ws_get_credentials_prefers_volcengine_tts_keys(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APP_KEY", "test-app")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_KEY", "test-access")
    monkeypatch.setenv("ARK_ACCESS_KEY_ID", "legacy-app")
    monkeypatch.setenv("ARK_SECRET_ACCESS_KEY", "legacy-access")

    provider = volcengine_provider.VolcengineTTSProvider()
    app_key, access_key, resource_id = provider._get_credentials("seed-tts-2.0")

    assert app_key == "test-app"
    assert access_key == "test-access"
    assert resource_id == "seed-tts-2.0"


def test_volcengine_ws_get_credentials_falls_back_to_ark_keys(monkeypatch):
    monkeypatch.delenv("VOLCENGINE_TTS_APP_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_TTS_ACCESS_KEY", raising=False)
    monkeypatch.setenv("ARK_ACCESS_KEY_ID", "legacy-app")
    monkeypatch.setenv("ARK_SECRET_ACCESS_KEY", "legacy-access")

    provider = volcengine_provider.VolcengineTTSProvider()
    app_key, access_key, resource_id = provider._get_credentials("")

    assert app_key == "legacy-app"
    assert access_key == "legacy-access"
    assert resource_id == "seed-tts-1.0"


def test_volcengine_ws_is_configured_uses_volcengine_tts_keys(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APP_KEY", "test-app")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_KEY", "test-access")
    monkeypatch.delenv("ARK_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ARK_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setattr(volcengine_provider, "WEBSOCKET_AVAILABLE", True)

    provider = volcengine_provider.VolcengineTTSProvider()
    assert provider.is_configured() is True


def test_volcengine_ws_waits_for_session_started_before_task_request(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APP_KEY", "test-app")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_KEY", "test-access")
    monkeypatch.setattr(volcengine_provider, "WEBSOCKET_AVAILABLE", True)

    captured = {}

    class FakeProtocol:
        def encode_start_connection(self):
            return b"start_connection"

        def encode_start_session(self, **kwargs):
            captured["start_session_kwargs"] = kwargs
            return b"start_session"

        def encode_task_request(self, session_id, text):
            return b"task_request"

        def encode_finish_session(self, session_id):
            return b"finish_session"

        def encode_finish_connection(self):
            return b"finish_connection"

        def decode_frame(self, message):
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
            raise AssertionError(f"unexpected frame: {message!r}")

    class FakeWebSocketApp:
        def __init__(self, url, header, on_message, on_error, on_close, on_open):
            self.on_message = on_message
            self.on_close = on_close
            self.on_open = on_open
            self.sent = []
            self.session_started_sent = False
            captured["ws"] = self

        def run_forever(self, **kwargs):
            self.on_open(self)

        def send(self, frame, opcode=None):
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

        def _emit_session_started(self):
            self.session_started_sent = True
            self.on_message(self, b"session_started")

        def close(self):
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
        voice_settings=volcengine_provider.VoiceSettings(
            voice_id="zh_female_vv_uranus_bigtts"
        ),
        model="seed-tts-2.0",
    )

    assert result.audio_data == b"audio-bytes"
    assert result.duration_ms == 456
    assert captured["start_session_kwargs"]["enable_timestamp"] is False
    assert captured["start_session_kwargs"]["enable_subtitle"] is True
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
