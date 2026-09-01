"""Raw Gemini Live WebSocket client for voice follow-up sessions.

The provider deliberately owns only the upstream Gemini protocol. Browser
authentication, capacity admission, transcript persistence, and billing stay
in their respective service modules.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections import deque
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlencode

import websocket

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

GEMINI_LIVE_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService."
    "BidiGenerateContent"
)
GEMINI_LIVE_INPUT_MIME_TYPE = "audio/pcm;rate=16000"
GEMINI_LIVE_OUTPUT_SAMPLE_RATE = 24000
GEMINI_LIVE_MAX_INPUT_FRAME_BYTES = 8192
GEMINI_LIVE_IO_TIMEOUT_SECONDS = 5.0


class GeminiLiveProviderError(Exception):
    """Base class for bounded Gemini Live provider failures."""


class GeminiLiveConnectionError(GeminiLiveProviderError):
    """The upstream WebSocket could not be opened or used."""


class GeminiLiveProtocolError(GeminiLiveProviderError):
    """Gemini returned an invalid or unsupported protocol message."""


class _WebSocketConnection(Protocol):
    """Small websocket-client surface used by the provider."""

    def send(self, payload: str) -> object:
        """Send one text frame."""
        ...

    def recv(self) -> str | bytes:
        """Receive one upstream frame."""
        ...

    def settimeout(self, timeout: float | None) -> object:
        """Configure the connection receive timeout."""
        ...

    def close(self) -> object:
        """Close the connection."""
        ...


@dataclass(frozen=True)
class GeminiLiveServerEvent:
    """Normalized fields from one Gemini Live server message."""

    setup_complete: bool = False
    audio_chunks: tuple[bytes, ...] = ()
    model_texts: tuple[str, ...] = ()
    interim_input_transcripts: tuple[str, ...] = ()
    input_transcripts: tuple[str, ...] = ()
    output_transcripts: tuple[str, ...] = ()
    interrupted: bool = False
    turn_complete: bool = False
    generation_complete: bool = False
    usage_metadata: dict[str, object] | None = None
    resumption_handle: str | None = None
    resumable: bool | None = None
    go_away: bool = False
    go_away_time_left: str | None = None
    upstream_error: bool = False
    upstream_error_code: str | None = None


@dataclass(frozen=True)
class GeminiLiveHistoryTurn:
    """One user or model turn used to seed a new Live session."""

    role: str
    text: str


@dataclass
class GeminiLiveProvider:
    """Manage one raw Gemini Live bidirectional WebSocket connection."""

    api_key: str = field(repr=False)
    model: str
    voice_name: str
    system_instruction: str = field(repr=False)
    history: Sequence[GeminiLiveHistoryTurn | Mapping[str, object]] = field(
        default=(),
        repr=False,
    )
    connect_timeout_seconds: float = 15.0
    io_timeout_seconds: float = GEMINI_LIVE_IO_TIMEOUT_SECONDS
    connection_factory: Callable[..., object] | None = field(
        default=None,
        repr=False,
    )
    _connection: _WebSocketConnection | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _pending_events: deque[GeminiLiveServerEvent] = field(
        default_factory=deque,
        init=False,
        repr=False,
    )
    _resumption_handle: str | None = field(default=None, init=False, repr=False)
    _resumption_available: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        """Reject incomplete setup without exposing credential values."""
        if not self.api_key.strip():
            message = "Gemini Live API key is not configured"
            raise GeminiLiveConnectionError(message)
        if not self.model.strip():
            message = "Gemini Live model is not configured"
            raise GeminiLiveProtocolError(message)
        if not self.voice_name.strip():
            message = "Gemini Live voice is not configured"
            raise GeminiLiveProtocolError(message)
        if self.connect_timeout_seconds <= 0 or self.io_timeout_seconds <= 0:
            message = "Gemini Live timeouts must be positive"
            raise GeminiLiveProtocolError(message)

    @property
    def resumption_handle(self) -> str | None:
        """Return the latest resumable handle received from Gemini."""
        return self._resumption_handle

    @property
    def connected(self) -> bool:
        """Return whether an upstream connection is currently installed."""
        return self._connection is not None

    def connect(self, *, resumption_handle: str | None = None) -> GeminiLiveServerEvent:
        """Open Gemini, complete setup, and seed history for a new session.

        Setup completion is consumed synchronously so callers cannot send
        realtime audio before Gemini accepts the session configuration.
        """
        if self._connection is not None:
            message = "Gemini Live connection is already open"
            raise GeminiLiveConnectionError(message)
        if resumption_handle is None:
            self._resumption_handle = None
            self._resumption_available = False

        connection_factory = self.connection_factory or websocket.create_connection
        endpoint = f"{GEMINI_LIVE_ENDPOINT}?{urlencode({'key': self.api_key})}"
        try:
            candidate = connection_factory(
                endpoint,
                timeout=self.connect_timeout_seconds,
                enable_multithread=True,
            )
        except Exception:
            message = "Gemini Live upstream connection failed"
            raise GeminiLiveConnectionError(message) from None
        if not _is_websocket_connection(candidate):
            self._close_candidate(candidate)
            message = "Gemini Live upstream returned an invalid connection"
            raise GeminiLiveConnectionError(message)
        self._connection = candidate
        setup_deadline = monotonic() + self.connect_timeout_seconds

        history_message = (
            self._build_history_message() if resumption_handle is None else None
        )
        try:
            self._set_connection_timeout(self._remaining_setup_timeout(setup_deadline))
            self._send_json(
                self._build_setup_message(
                    resumption_handle=resumption_handle,
                    include_initial_history=history_message is not None,
                )
            )
            setup_event = self._wait_for_setup_complete(deadline=setup_deadline)
            if history_message is not None:
                self._set_connection_timeout(
                    self._remaining_setup_timeout(setup_deadline)
                )
                self._send_json(history_message)
            self._configure_io_timeout()
        except GeminiLiveProviderError:
            self.close()
            raise
        return setup_event

    def reconnect_with_resumption(self) -> GeminiLiveServerEvent:
        """Reconnect the same session using Gemini's latest recovery handle."""
        handle = self._resumption_handle
        if not handle:
            message = "Gemini Live session is not resumable"
            raise GeminiLiveConnectionError(message)
        self.close()
        return self.connect(resumption_handle=handle)

    def can_resume_after(self, event: GeminiLiveServerEvent) -> bool:
        """Return whether a GoAway can be recovered on this provider."""
        return (
            event.go_away
            and self._resumption_available
            and bool(self._resumption_handle)
        )

    def send_audio_frame(self, frame: bytes) -> None:
        """Send one mono PCM16 little-endian 16 kHz input frame."""
        if not frame:
            return
        if len(frame) > GEMINI_LIVE_MAX_INPUT_FRAME_BYTES:
            message = "Gemini Live input audio frame is too large"
            raise GeminiLiveProtocolError(message)
        if len(frame) % 2 != 0:
            message = "Gemini Live PCM16 frame must contain complete samples"
            raise GeminiLiveProtocolError(message)
        encoded = base64.b64encode(frame).decode("ascii")
        self._send_json(
            {
                "realtimeInput": {
                    "audio": {
                        "mimeType": GEMINI_LIVE_INPUT_MIME_TYPE,
                        "data": encoded,
                    }
                }
            }
        )

    def send_audio(self, frame: bytes) -> None:
        """Route-friendly alias for sending one browser PCM frame."""
        self.send_audio_frame(frame)

    def send_audio_stream_end(self) -> None:
        """Tell Gemini that the current browser audio stream ended."""
        self._send_json({"realtimeInput": {"audioStreamEnd": True}})

    def receive_event(self) -> GeminiLiveServerEvent:
        """Receive and normalize one Gemini server event."""
        if self._pending_events:
            return self._pending_events.popleft()
        connection = self._require_connection()
        while True:
            try:
                payload = connection.recv()
                break
            except websocket.WebSocketTimeoutException:
                # A finite socket timeout also bounds writes. Quiet sessions are
                # expected, so receive timeouts are only cancellation checkpoints.
                continue
            except Exception:
                message = "Gemini Live upstream receive failed"
                raise GeminiLiveConnectionError(message) from None
        event = parse_gemini_live_server_event(payload)
        self._remember_resumption_handle(event)
        return event

    def receive(self) -> GeminiLiveServerEvent:
        """Route-friendly alias for receiving one normalized event."""
        return self.receive_event()

    def close(self) -> None:
        """Close the upstream socket and discard connection-local events."""
        connection = self._connection
        self._connection = None
        self._pending_events.clear()
        if connection is None:
            return
        try:
            connection.close()
        except Exception:
            return

    def abort(self) -> None:
        """Immediately cancel in-flight I/O during proxy shutdown."""
        connection = self._connection
        self._connection = None
        self._pending_events.clear()
        if connection is None:
            return
        shutdown = getattr(connection, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                return
            return
        self._close_candidate(connection)

    def _build_setup_message(
        self,
        *,
        resumption_handle: str | None,
        include_initial_history: bool,
    ) -> dict[str, object]:
        setup: dict[str, object] = {
            "model": _qualified_model(self.model),
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": self.voice_name}
                    }
                },
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            },
            "systemInstruction": {
                "parts": [{"text": self.system_instruction}],
            },
            "realtimeInputConfig": {
                "automaticActivityDetection": {
                    "disabled": False,
                    "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                    "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                    "prefixPaddingMs": 100,
                    "silenceDurationMs": 700,
                },
                "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
                "turnCoverage": "TURN_INCLUDES_ONLY_ACTIVITY",
            },
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "contextWindowCompression": {
                "triggerTokens": "25000",
                "slidingWindow": {"targetTokens": "8000"},
            },
        }
        if resumption_handle:
            setup["sessionResumption"] = {"handle": resumption_handle}
        else:
            setup["sessionResumption"] = {}
            if include_initial_history:
                setup["historyConfig"] = {"initialHistoryInClientContent": True}
        return {"setup": setup}

    def _build_history_message(self) -> dict[str, object] | None:
        turns: list[dict[str, object]] = []
        for item in self.history:
            if isinstance(item, GeminiLiveHistoryTurn):
                raw_role = item.role
                text = item.text
            else:
                raw_role = str(item.get("role") or "")
                text = str(item.get("text") or item.get("content") or "")
            normalized_text = text.strip()
            role = _normalize_history_role(raw_role)
            if role is None or not normalized_text:
                continue
            turns.append(
                {
                    "role": role,
                    "parts": [{"text": normalized_text}],
                }
            )
        if not turns:
            return None
        return {
            "clientContent": {
                "turns": turns,
                "turnComplete": True,
            }
        }

    def _wait_for_setup_complete(self, *, deadline: float) -> GeminiLiveServerEvent:
        while True:
            connection = self._require_connection()
            self._set_connection_timeout(self._remaining_setup_timeout(deadline))
            try:
                payload = connection.recv()
            except Exception:
                message = "Gemini Live setup failed"
                raise GeminiLiveConnectionError(message) from None
            event = parse_gemini_live_server_event(payload)
            self._remember_resumption_handle(event)
            if event.setup_complete:
                return event
            self._pending_events.append(event)

    def _remember_resumption_handle(self, event: GeminiLiveServerEvent) -> None:
        if event.resumable is False:
            # A previously issued handle is only a snapshot. Gemini explicitly
            # marks it unsafe while the current state cannot be resumed.
            self._resumption_handle = None
            self._resumption_available = False
            return
        if event.resumption_handle:
            self._resumption_handle = event.resumption_handle
            self._resumption_available = True
        elif event.resumable is True:
            self._resumption_available = self._resumption_handle is not None

    def _send_json(self, payload: Mapping[str, object]) -> None:
        connection = self._require_connection()
        serialized = json.dumps(payload, separators=(",", ":"))
        try:
            connection.send(serialized)
        except Exception:
            message = "Gemini Live upstream send failed"
            raise GeminiLiveConnectionError(message) from None

    def _configure_io_timeout(self) -> None:
        self._set_connection_timeout(self.io_timeout_seconds)

    def _set_connection_timeout(self, timeout: float) -> None:
        connection = self._require_connection()
        settimeout = getattr(connection, "settimeout", None)
        if not callable(settimeout):
            return
        try:
            settimeout(timeout)
        except Exception:
            message = "Gemini Live upstream timeout setup failed"
            raise GeminiLiveConnectionError(message) from None

    @staticmethod
    def _remaining_setup_timeout(deadline: float) -> float:
        remaining = deadline - monotonic()
        if remaining <= 0:
            message = "Gemini Live setup timed out"
            raise GeminiLiveConnectionError(message)
        return remaining

    def _require_connection(self) -> _WebSocketConnection:
        if self._connection is None:
            message = "Gemini Live connection is not open"
            raise GeminiLiveConnectionError(message)
        return self._connection

    @staticmethod
    def _close_candidate(candidate: object) -> None:
        close = getattr(candidate, "close", None)
        if not callable(close):
            return
        try:
            close()
        except Exception:
            return


def parse_gemini_live_server_event(
    payload: str | bytes,
) -> GeminiLiveServerEvent:
    """Parse every relevant part of one raw Gemini Live server frame."""
    try:
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        parsed = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        message = "Gemini Live returned an invalid JSON message"
        raise GeminiLiveProtocolError(message) from None
    if not isinstance(parsed, dict):
        message = "Gemini Live returned an invalid message object"
        raise GeminiLiveProtocolError(message)

    server_content = _mapping_value(parsed, "serverContent", "server_content")
    model_turn = _mapping_value(server_content, "modelTurn", "model_turn")
    raw_parts = model_turn.get("parts") if model_turn is not None else None
    parts = raw_parts if isinstance(raw_parts, list) else []
    audio_chunks: list[bytes] = []
    model_texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_text = part.get("text")
        if isinstance(part_text, str) and part_text:
            model_texts.append(part_text)
        inline_data = _mapping_value(part, "inlineData", "inline_data")
        if inline_data is None:
            continue
        mime_type = str(
            inline_data.get("mimeType") or inline_data.get("mime_type") or ""
        ).lower()
        encoded = inline_data.get("data")
        if not mime_type.startswith("audio/pcm") or not isinstance(encoded, str):
            continue
        try:
            audio_chunks.append(base64.b64decode(encoded, validate=True))
        except (binascii.Error, ValueError):
            message = "Gemini Live returned invalid audio data"
            raise GeminiLiveProtocolError(message) from None

    interim_input_transcripts = _transcript_fragments(
        _value(
            server_content,
            "interimInputTranscription",
            "interim_input_transcription",
        )
    )
    input_transcripts = _transcript_fragments(
        _value(server_content, "inputTranscription", "input_transcription")
    )
    output_transcripts = _transcript_fragments(
        _value(server_content, "outputTranscription", "output_transcription")
    )
    usage = _mapping_value(parsed, "usageMetadata", "usage_metadata")
    resumption = _mapping_value(
        parsed,
        "sessionResumptionUpdate",
        "session_resumption_update",
    )
    go_away = _mapping_value(parsed, "goAway", "go_away")
    upstream_error = _mapping_value(parsed, "error")

    resumption_handle = None
    resumable = None
    if resumption is not None:
        raw_handle = resumption.get("newHandle") or resumption.get("new_handle")
        if isinstance(raw_handle, str) and raw_handle:
            resumption_handle = raw_handle
        raw_resumable = resumption.get("resumable")
        if isinstance(raw_resumable, bool):
            resumable = raw_resumable

    go_away_time_left = None
    if go_away is not None:
        raw_time_left = go_away.get("timeLeft") or go_away.get("time_left")
        if isinstance(raw_time_left, str) and raw_time_left:
            go_away_time_left = raw_time_left

    upstream_error_code = None
    if upstream_error is not None:
        raw_error_code = upstream_error.get("code")
        if isinstance(raw_error_code, (int, str)):
            upstream_error_code = str(raw_error_code)[:32]

    return GeminiLiveServerEvent(
        setup_complete=_has_key(parsed, "setupComplete", "setup_complete"),
        audio_chunks=tuple(audio_chunks),
        model_texts=tuple(model_texts),
        interim_input_transcripts=tuple(interim_input_transcripts),
        input_transcripts=tuple(input_transcripts),
        output_transcripts=tuple(output_transcripts),
        interrupted=_boolean_value(server_content, "interrupted"),
        turn_complete=_boolean_value(
            server_content,
            "turnComplete",
            "turn_complete",
        ),
        generation_complete=_boolean_value(
            server_content,
            "generationComplete",
            "generation_complete",
        ),
        usage_metadata=dict(usage) if usage is not None else None,
        resumption_handle=resumption_handle,
        resumable=resumable,
        go_away=go_away is not None,
        go_away_time_left=go_away_time_left,
        upstream_error=upstream_error is not None,
        upstream_error_code=upstream_error_code,
    )


def _is_websocket_connection(candidate: object) -> bool:
    return all(
        callable(getattr(candidate, attribute, None))
        for attribute in ("send", "recv", "close")
    )


def _qualified_model(model: str) -> str:
    normalized = model.strip()
    return normalized if normalized.startswith("models/") else f"models/{normalized}"


def _normalize_history_role(role: str) -> str | None:
    normalized = role.strip().lower()
    if normalized in {"assistant", "model"}:
        return "model"
    if normalized == "user":
        return "user"
    return None


def _mapping_value(
    source: Mapping[str, object] | None,
    *keys: str,
) -> dict[str, object] | None:
    value = _value(source, *keys)
    return value if isinstance(value, dict) else None


def _value(source: Mapping[str, object] | None, *keys: str) -> object:
    if source is None:
        return None
    for key in keys:
        if key in source:
            return source[key]
    return None


def _has_key(source: Mapping[str, object], *keys: str) -> bool:
    return any(key in source for key in keys)


def _boolean_value(source: Mapping[str, object] | None, *keys: str) -> bool:
    return _value(source, *keys) is True


def _transcript_fragments(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        fragments: list[str] = []
        for item in value:
            fragments.extend(_transcript_fragments(item))
        return fragments
    if not isinstance(value, dict):
        return []
    raw_text = value.get("text")
    return [raw_text] if isinstance(raw_text, str) and raw_text else []
