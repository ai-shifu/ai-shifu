import json
from types import SimpleNamespace

import pytest

from flaskr.api.tts import AudioSettings, VoiceSettings
import flaskr.api.tts.minimax_provider as minimax_provider
from flaskr.api.tts.minimax_provider import MinimaxWebSocketTTSSession


class _FakeWebSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.closed = False
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self):
        if not self.responses:
            raise RuntimeError("no response queued")
        return json.dumps(self.responses.pop(0))

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def close(self):
        self.closed = True


def _session(monkeypatch, responses, gate_calls):
    fake_ws = _FakeWebSocket(responses)
    monkeypatch.setattr(
        minimax_provider,
        "websocket",
        SimpleNamespace(create_connection=lambda *args, **kwargs: fake_ws),
    )
    monkeypatch.setattr(
        minimax_provider,
        "acquire_tts_rpm_slot",
        lambda **kwargs: gate_calls.append(kwargs),
    )
    session = MinimaxWebSocketTTSSession(
        api_key="api-key",
        model="speech-2.8-turbo",
        voice_settings=VoiceSettings(
            voice_id="voice-a",
            speed=1.2,
            pitch=1,
            emotion="happy",
            volume=0.9,
        ),
        audio_settings=AudioSettings(
            format="mp3",
            sample_rate=32000,
            bitrate=128000,
            channel=1,
        ),
        rpm_limit=120,
        queue_max_wait_seconds=10,
    )
    return session, fake_ws


def test_minimax_websocket_session_gates_task_start_and_continue(monkeypatch):
    gate_calls = []
    session, fake_ws = _session(
        monkeypatch,
        responses=[
            {
                "event": "connected_success",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            {
                "event": "task_started",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            {
                "event": "task_continued",
                "data": {"audio": "61"},
                "is_final": False,
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            {
                "event": "task_continued",
                "data": {"audio": "62"},
                "is_final": True,
                "extra_info": {
                    "audio_length": 240,
                    "audio_sample_rate": 32000,
                    "audio_format": "mp3",
                    "usage_characters": 2,
                },
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            {
                "event": "task_continued",
                "data": {"audio": "63"},
                "is_final": True,
                "extra_info": {
                    "audio_length": 120,
                    "audio_sample_rate": 32000,
                    "audio_format": "mp3",
                    "usage_characters": 1,
                },
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            {
                "event": "task_finished",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        ],
        gate_calls=gate_calls,
    )

    session.open()
    result = session.synthesize_segment("hi")
    next_result = session.synthesize_segment("!")
    session.close()

    assert [payload["event"] for payload in fake_ws.sent] == [
        "task_start",
        "task_continue",
        "task_continue",
        "task_finish",
    ]
    assert fake_ws.sent[0]["voice_setting"]["emotion"] == "happy"
    assert fake_ws.sent[1]["text"] == "hi"
    assert fake_ws.sent[2]["text"] == "!"
    assert len(gate_calls) == 3
    assert all(call["provider"] == "minimax" for call in gate_calls)
    assert result.audio_data == b"ab"
    assert result.duration_ms == 240
    assert result.sample_rate == 32000
    assert result.word_count == 2
    assert next_result.audio_data == b"c"
    assert fake_ws.closed is True


def test_minimax_websocket_session_allows_null_data_before_final_audio(monkeypatch):
    gate_calls = []
    session, _fake_ws = _session(
        monkeypatch,
        responses=[
            {"event": "connected_success", "base_resp": {"status_code": 0}},
            {"event": "task_started", "base_resp": {"status_code": 0}},
            {
                "event": "task_continued",
                "data": None,
                "is_final": False,
                "base_resp": {"status_code": 0},
            },
            {
                "event": "task_continued",
                "data": {"audio": "6869"},
                "is_final": True,
                "extra_info": {"audio_length": 100},
                "base_resp": {"status_code": 0},
            },
        ],
        gate_calls=gate_calls,
    )

    result = session.synthesize_segment("hi")

    assert len(gate_calls) == 2
    assert result.audio_data == b"hi"
    assert result.duration_ms == 100


def test_minimax_websocket_session_raises_on_task_failed(monkeypatch):
    gate_calls = []
    session, _fake_ws = _session(
        monkeypatch,
        responses=[
            {"event": "connected_success", "base_resp": {"status_code": 0}},
            {"event": "task_started", "base_resp": {"status_code": 0}},
            {
                "event": "task_failed",
                "base_resp": {"status_code": 1004, "status_msg": "auth failed"},
            },
        ],
        gate_calls=gate_calls,
    )

    with pytest.raises(ValueError, match="task failed"):
        session.synthesize_segment("hi")
