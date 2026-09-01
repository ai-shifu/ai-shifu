"""Focused contracts for the raw Gemini Live upstream provider."""

from __future__ import annotations

import base64
import json
from collections import deque

import pytest
import websocket
from flaskr.service.learn.gemini_live_provider import (
    GEMINI_LIVE_IO_TIMEOUT_SECONDS,
    GEMINI_LIVE_MAX_INPUT_FRAME_BYTES,
    GeminiLiveHistoryTurn,
    GeminiLiveProtocolError,
    GeminiLiveProvider,
    parse_gemini_live_server_event,
)


class _FakeSocket:
    def __init__(self, received: list[object]) -> None:
        self.received = deque(received)
        self.sent: list[str] = []
        self.closed = False
        self.shutdown_called = False
        self.timeouts: list[float | None] = []

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self) -> str:
        item = self.received.popleft()
        if isinstance(item, BaseException):
            raise item
        return str(item)

    def close(self) -> None:
        self.closed = True

    def settimeout(self, timeout: float | None) -> None:
        self.timeouts.append(timeout)

    def shutdown(self) -> None:
        self.shutdown_called = True


class _SocketFactory:
    def __init__(self, sockets: list[_FakeSocket]) -> None:
        self.sockets = deque(sockets)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, url: str, **kwargs: object) -> _FakeSocket:
        self.calls.append((url, kwargs))
        return self.sockets.popleft()


def test_provider_waits_for_setup_and_seeds_official_audio_contract() -> None:
    socket = _FakeSocket(['{"setupComplete":{}}'])
    factory = _SocketFactory([socket])
    provider = GeminiLiveProvider(
        api_key="secret+/=",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        system_instruction="Teach from the current lesson.",
        history=[
            GeminiLiveHistoryTurn(role="user", text="Earlier question"),
            {"role": "assistant", "content": "Earlier answer"},
        ],
        connection_factory=factory,
    )

    setup_event = provider.connect()

    assert setup_event.setup_complete is True
    assert "secret+/=" not in repr(provider)
    assert "key=secret%2B%2F%3D" in factory.calls[0][0]
    assert factory.calls[0][1] == {
        "timeout": 15.0,
        "enable_multithread": True,
    }
    assert socket.timeouts[-1] == GEMINI_LIVE_IO_TIMEOUT_SECONDS
    assert len(socket.timeouts) == 4
    assert all(
        timeout is not None and 0 < timeout <= 15 for timeout in socket.timeouts[:-1]
    )

    setup = json.loads(socket.sent[0])["setup"]
    assert setup["model"] == "models/gemini-3.1-flash-live-preview"
    assert setup["generationConfig"] == {
        "responseModalities": ["AUDIO"],
        "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
        "thinkingConfig": {"thinkingLevel": "MINIMAL"},
    }
    assert setup["inputAudioTranscription"] == {}
    assert setup["outputAudioTranscription"] == {}
    assert setup["realtimeInputConfig"] == {
        "automaticActivityDetection": {
            "disabled": False,
            "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
            "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
            "prefixPaddingMs": 100,
            "silenceDurationMs": 700,
        },
        "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
        "turnCoverage": "TURN_INCLUDES_ONLY_ACTIVITY",
    }
    assert setup["sessionResumption"] == {}
    assert setup["historyConfig"] == {"initialHistoryInClientContent": True}
    assert setup["contextWindowCompression"] == {
        "triggerTokens": "25000",
        "slidingWindow": {"targetTokens": "8000"},
    }
    assert json.loads(socket.sent[1]) == {
        "clientContent": {
            "turns": [
                {"role": "user", "parts": [{"text": "Earlier question"}]},
                {"role": "model", "parts": [{"text": "Earlier answer"}]},
            ],
            "turnComplete": True,
        }
    }


def test_provider_sends_pcm_frames_and_stream_end() -> None:
    socket = _FakeSocket(['{"setupComplete":{}}'])
    provider = GeminiLiveProvider(
        api_key="key",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        system_instruction="prompt",
        connection_factory=_SocketFactory([socket]),
    )
    provider.connect()

    setup = json.loads(socket.sent[0])["setup"]
    assert "historyConfig" not in setup
    provider.send_audio(b"\x01\x02")
    provider.send_audio_stream_end()

    assert json.loads(socket.sent[1]) == {
        "realtimeInput": {
            "audio": {
                "mimeType": "audio/pcm;rate=16000",
                "data": "AQI=",
            }
        }
    }
    assert json.loads(socket.sent[2]) == {"realtimeInput": {"audioStreamEnd": True}}
    with pytest.raises(GeminiLiveProtocolError, match="too large"):
        provider.send_audio(b"x" * (GEMINI_LIVE_MAX_INPUT_FRAME_BYTES + 1))
    with pytest.raises(GeminiLiveProtocolError, match="complete samples"):
        provider.send_audio(b"x")


def test_provider_uses_receive_timeout_as_cancellation_checkpoint() -> None:
    socket = _FakeSocket(
        [
            '{"setupComplete":{}}',
            websocket.WebSocketTimeoutException("quiet session"),
            '{"serverContent":{"inputTranscription":{"text":"hello"}}}',
        ]
    )
    provider = GeminiLiveProvider(
        api_key="key",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        system_instruction="prompt",
        connection_factory=_SocketFactory([socket]),
    )
    provider.connect()

    event = provider.receive()

    assert event.input_transcripts == ("hello",)


def test_provider_abort_immediately_shuts_down_inflight_socket() -> None:
    socket = _FakeSocket(['{"setupComplete":{}}'])
    provider = GeminiLiveProvider(
        api_key="key",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        system_instruction="prompt",
        connection_factory=_SocketFactory([socket]),
    )
    provider.connect()

    provider.abort()

    assert socket.shutdown_called is True
    assert provider.connected is False


def test_provider_does_not_start_initial_history_phase_without_valid_turns() -> None:
    socket = _FakeSocket(['{"setupComplete":{}}'])
    provider = GeminiLiveProvider(
        api_key="key",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        system_instruction="prompt",
        history=[
            {"role": "system", "content": "not a conversation turn"},
            {"role": "user", "content": "  "},
        ],
        connection_factory=_SocketFactory([socket]),
    )

    provider.connect()

    assert "historyConfig" not in json.loads(socket.sent[0])["setup"]
    assert len(socket.sent) == 1


def test_parser_reads_all_audio_parts_transcripts_and_lifecycle_fields() -> None:
    first_audio = base64.b64encode(b"first").decode("ascii")
    second_audio = base64.b64encode(b"second").decode("ascii")
    event = parse_gemini_live_server_event(
        json.dumps(
            {
                "serverContent": {
                    "modelTurn": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "audio/pcm;rate=24000",
                                    "data": first_audio,
                                }
                            },
                            {"text": "model side text"},
                            {
                                "inlineData": {
                                    "mimeType": "audio/pcm;rate=24000",
                                    "data": second_audio,
                                }
                            },
                        ]
                    },
                    "interimInputTranscription": {"text": "ques"},
                    "inputTranscription": {"text": "question"},
                    "outputTranscription": {"text": "answer"},
                    "interrupted": True,
                    "turnComplete": True,
                    "generationComplete": True,
                },
                "usageMetadata": {
                    "totalTokenCount": 9,
                    "responseTokensDetails": [{"modality": "AUDIO", "tokenCount": 4}],
                },
                "sessionResumptionUpdate": {
                    "newHandle": "resume-handle",
                    "resumable": True,
                },
                "goAway": {"timeLeft": "5s"},
                "error": {"code": 429, "message": "must not escape"},
            }
        )
    )

    assert event.audio_chunks == (b"first", b"second")
    assert event.model_texts == ("model side text",)
    assert event.interim_input_transcripts == ("ques",)
    assert event.input_transcripts == ("question",)
    assert event.output_transcripts == ("answer",)
    assert event.interrupted is True
    assert event.turn_complete is True
    assert event.generation_complete is True
    assert event.usage_metadata == {
        "totalTokenCount": 9,
        "responseTokensDetails": [{"modality": "AUDIO", "tokenCount": 4}],
    }
    assert event.resumption_handle == "resume-handle"
    assert event.resumable is True
    assert event.go_away is True
    assert event.go_away_time_left == "5s"
    assert event.upstream_error is True
    assert event.upstream_error_code == "429"


def test_provider_reconnects_with_latest_resumption_handle_without_history() -> None:
    first = _FakeSocket(
        [
            '{"setupComplete":{}}',
            '{"sessionResumptionUpdate":{"newHandle":"handle-1","resumable":true},'
            '"goAway":{"timeLeft":"3s"}}',
        ]
    )
    second = _FakeSocket(['{"setupComplete":{}}'])
    provider = GeminiLiveProvider(
        api_key="key",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        system_instruction="prompt",
        history=[{"role": "user", "content": "history"}],
        connection_factory=_SocketFactory([first, second]),
    )
    provider.connect()
    go_away = provider.receive()

    assert provider.can_resume_after(go_away) is True
    provider.reconnect_with_resumption()

    assert first.closed is True
    resumed_setup = json.loads(second.sent[0])["setup"]
    assert resumed_setup["sessionResumption"] == {"handle": "handle-1"}
    assert "historyConfig" not in resumed_setup
    assert len(second.sent) == 1


def test_provider_rejects_stale_handle_when_current_state_is_not_resumable() -> None:
    socket = _FakeSocket(
        [
            '{"setupComplete":{}}',
            '{"sessionResumptionUpdate":{"newHandle":"handle-1","resumable":true}}',
            '{"sessionResumptionUpdate":{"resumable":false},'
            '"goAway":{"timeLeft":"3s"}}',
        ]
    )
    provider = GeminiLiveProvider(
        api_key="key",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        system_instruction="prompt",
        connection_factory=_SocketFactory([socket]),
    )
    provider.connect()

    provider.receive()
    go_away = provider.receive()

    assert provider.resumption_handle is None
    assert provider.can_resume_after(go_away) is False


def test_parser_rejects_malformed_audio_without_leaking_payload() -> None:
    with pytest.raises(GeminiLiveProtocolError, match="invalid audio data"):
        parse_gemini_live_server_event(
            json.dumps(
                {
                    "serverContent": {
                        "modelTurn": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/pcm;rate=24000",
                                        "data": "not base64!",
                                    }
                                }
                            ]
                        }
                    }
                }
            )
        )
