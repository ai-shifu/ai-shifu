"""
Volcengine TTS WebSocket Binary Protocol Handler.

This module implements the binary protocol used by Volcengine's
bidirectional TTS WebSocket API.

Protocol Reference:
- WebSocket URL: wss://openspeech.bytedance.com/api/v3/tts/bidirection
- Uses custom binary frame format with 4-byte header
"""

import struct
import json
import gzip
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union
from enum import IntEnum

from flaskr.common.log import AppLoggerProxy

logger = AppLoggerProxy(logging.getLogger(__name__))


class MessageType(IntEnum):
    """WebSocket message types."""

    FULL_CLIENT_REQUEST = 0b0001
    FULL_SERVER_RESPONSE = 0b1001
    AUDIO_ONLY_RESPONSE = 0b1011
    ERROR_INFORMATION = 0b1111


class MessageFlag(IntEnum):
    """Message type specific flags."""

    NO_EVENT = 0b0000
    WITH_EVENT = 0b0100


class SerializationMethod(IntEnum):
    """Payload serialization methods."""

    RAW = 0b0000
    JSON = 0b0001


class CompressionMethod(IntEnum):
    """Payload compression methods."""

    NONE = 0b0000
    GZIP = 0b0001


class Event(IntEnum):
    """Protocol events."""

    # Connection events (upstream)
    START_CONNECTION = 1
    FINISH_CONNECTION = 2

    # Connection events (downstream)
    CONNECTION_STARTED = 50
    CONNECTION_FAILED = 51
    CONNECTION_FINISHED = 52

    # Session events (upstream)
    START_SESSION = 100
    CANCEL_SESSION = 101
    FINISH_SESSION = 102

    # Session events (downstream)
    SESSION_STARTED = 150
    SESSION_CANCELED = 151
    SESSION_FINISHED = 152
    SESSION_FAILED = 153

    # Data events
    TASK_REQUEST = 200

    # TTS response events
    TTS_SENTENCE_START = 350
    TTS_SENTENCE_END = 351
    TTS_RESPONSE = 352


class ErrorCode(IntEnum):
    """Protocol error codes."""

    OK = 20000000
    CLIENT_ERROR = 45000000
    SERVER_ERROR = 55000000
    SESSION_ERROR = 55000001
    INVALID_REQUEST = 45000001


@dataclass
class ProtocolFrame:
    """Represents a parsed protocol frame."""

    message_type: MessageType
    message_flags: int
    serialization: SerializationMethod
    compression: CompressionMethod
    event: Optional[Event]
    session_id: Optional[str]
    connection_id: Optional[str]
    payload: Union[bytes, Dict[str, Any], None]
    error_code: Optional[int] = None


class VolcengineProtocol:
    """Encoder/decoder for Volcengine TTS binary protocol."""

    PROTOCOL_VERSION = 0b0001
    HEADER_SIZE = 0b0001  # 4 bytes (multiplied by 4)

    def __init__(self):
        self.connection_id: Optional[str] = None
        self.session_id: Optional[str] = None

    def encode_start_connection(self) -> bytes:
        """Encode StartConnection frame."""
        return self._encode_frame(
            message_type=MessageType.FULL_CLIENT_REQUEST,
            message_flags=MessageFlag.WITH_EVENT,
            serialization=SerializationMethod.JSON,
            compression=CompressionMethod.NONE,
            event=Event.START_CONNECTION,
            payload={},
        )

    def encode_finish_connection(self) -> bytes:
        """Encode FinishConnection frame."""
        return self._encode_frame(
            message_type=MessageType.FULL_CLIENT_REQUEST,
            message_flags=MessageFlag.WITH_EVENT,
            serialization=SerializationMethod.JSON,
            compression=CompressionMethod.NONE,
            event=Event.FINISH_CONNECTION,
            payload={},
        )

    def encode_start_session(
        self,
        session_id: str,
        speaker: str,
        audio_format: str = "mp3",
        sample_rate: int = 24000,
        speed: float = 1.0,
        pitch: int = 0,
        volume: float = 1.0,
        emotion: str = "",
        model: str = "",
    ) -> bytes:
        """
        Encode StartSession frame.

        Args:
            session_id: Unique session identifier
            speaker: Voice/speaker ID
            audio_format: Audio format (mp3, ogg_opus, pcm)
            sample_rate: Audio sample rate
            speed: Speech rate (-50 to 100, 0 is normal)
            pitch: Not used by Volcengine in this way
            volume: Volume rate (-50 to 100, 0 is normal)
            emotion: Emotion setting
            model: Model version (e.g., seed-tts-1.1)

        Returns:
            Encoded binary frame
        """
        self.session_id = session_id

        # Build audio params
        audio_params = {
            "format": audio_format,
            "sample_rate": sample_rate,
        }

        # Convert speed from 0.5-2.0 range to -50 to 100 range
        # 1.0 -> 0, 2.0 -> 100, 0.5 -> -50
        speech_rate = int((speed - 1.0) * 100)
        audio_params["speech_rate"] = speech_rate

        # Convert volume from 0.1-10.0 range to -50 to 100 range
        # 1.0 -> 0, 2.0 -> 100, 0.5 -> -50
        loudness_rate = int((volume - 1.0) * 100)
        audio_params["loudness_rate"] = loudness_rate

        # Add emotion if specified
        if emotion:
            audio_params["emotion"] = emotion

        # Build request params
        req_params = {
            "speaker": speaker,
            "audio_params": audio_params,
        }

        # Add model if specified
        if model:
            req_params["model"] = model

        # Build additions for extra settings
        additions = {}
        if additions:
            req_params["additions"] = json.dumps(additions)

        payload = {
            "user": {"uid": "ai-shifu"},
            "event": Event.START_SESSION,
            "namespace": "BidirectionalTTS",
            "req_params": req_params,
        }

        return self._encode_session_frame(
            message_type=MessageType.FULL_CLIENT_REQUEST,
            message_flags=MessageFlag.WITH_EVENT,
            serialization=SerializationMethod.JSON,
            compression=CompressionMethod.NONE,
            event=Event.START_SESSION,
            session_id=session_id,
            payload=payload,
        )

    def encode_task_request(self, session_id: str, text: str) -> bytes:
        """
        Encode TaskRequest frame with text to synthesize.

        Args:
            session_id: Session identifier
            text: Text to synthesize

        Returns:
            Encoded binary frame
        """
        payload = {
            "user": {"uid": "ai-shifu"},
            "event": Event.TASK_REQUEST,
            "namespace": "BidirectionalTTS",
            "req_params": {
                "text": text,
            },
        }

        return self._encode_session_frame(
            message_type=MessageType.FULL_CLIENT_REQUEST,
            message_flags=MessageFlag.WITH_EVENT,
            serialization=SerializationMethod.JSON,
            compression=CompressionMethod.NONE,
            event=Event.TASK_REQUEST,
            session_id=session_id,
            payload=payload,
        )

    def encode_finish_session(self, session_id: str) -> bytes:
        """Encode FinishSession frame."""
        return self._encode_session_frame(
            message_type=MessageType.FULL_CLIENT_REQUEST,
            message_flags=MessageFlag.WITH_EVENT,
            serialization=SerializationMethod.JSON,
            compression=CompressionMethod.NONE,
            event=Event.FINISH_SESSION,
            session_id=session_id,
            payload={},
        )

    def encode_cancel_session(self, session_id: str) -> bytes:
        """Encode CancelSession frame."""
        return self._encode_session_frame(
            message_type=MessageType.FULL_CLIENT_REQUEST,
            message_flags=MessageFlag.WITH_EVENT,
            serialization=SerializationMethod.JSON,
            compression=CompressionMethod.NONE,
            event=Event.CANCEL_SESSION,
            session_id=session_id,
            payload={},
        )

    def decode_frame(self, data: bytes) -> ProtocolFrame:
        """
        Decode a binary frame from server.

        Args:
            data: Raw binary data

        Returns:
            Parsed ProtocolFrame
        """
        if len(data) < 4:
            raise ValueError(f"Frame too short: {len(data)} bytes")

        # Parse header (4 bytes)
        byte0 = data[0]
        byte1 = data[1]
        byte2 = data[2]
        # byte3 is reserved

        _protocol_version = (byte0 >> 4) & 0x0F  # noqa: F841
        header_size = (byte0 & 0x0F) * 4

        message_type = MessageType((byte1 >> 4) & 0x0F)
        message_flags = byte1 & 0x0F

        serialization = SerializationMethod((byte2 >> 4) & 0x0F)
        compression = CompressionMethod(byte2 & 0x0F)

        offset = header_size
        event: Optional[Event] = None
        session_id: Optional[str] = None
        connection_id: Optional[str] = None
        error_code: Optional[int] = None

        # Check if frame has event number
        has_event = (message_flags & MessageFlag.WITH_EVENT) != 0

        if message_type == MessageType.ERROR_INFORMATION:
            # Error frame has error code at bytes 4-7
            if len(data) >= 8:
                error_code = struct.unpack(">I", data[4:8])[0]
                offset = 8
        elif has_event:
            # Parse event number (4 bytes, big endian)
            if len(data) >= offset + 4:
                event_value = struct.unpack(">i", data[offset : offset + 4])[0]
                try:
                    event = Event(event_value)
                except ValueError:
                    logger.warning(f"Unknown event code: {event_value}")
                    event = None
                offset += 4

            # Parse connection_id or session_id based on event type
            if event and event in [
                Event.CONNECTION_STARTED,
                Event.CONNECTION_FAILED,
                Event.CONNECTION_FINISHED,
            ]:
                # Connection events have connection_id
                if len(data) >= offset + 4:
                    conn_id_len = struct.unpack(">I", data[offset : offset + 4])[0]
                    offset += 4
                    if len(data) >= offset + conn_id_len:
                        connection_id = data[offset : offset + conn_id_len].decode(
                            "utf-8"
                        )
                        offset += conn_id_len
                        self.connection_id = connection_id
            elif event and event in [
                Event.SESSION_STARTED,
                Event.SESSION_CANCELED,
                Event.SESSION_FINISHED,
                Event.SESSION_FAILED,
                Event.TTS_SENTENCE_START,
                Event.TTS_SENTENCE_END,
                Event.TTS_RESPONSE,
            ]:
                # Session events have session_id
                if len(data) >= offset + 4:
                    sess_id_len = struct.unpack(">I", data[offset : offset + 4])[0]
                    offset += 4
                    if len(data) >= offset + sess_id_len:
                        session_id = data[offset : offset + sess_id_len].decode("utf-8")
                        offset += sess_id_len

        # Parse payload
        payload: Union[bytes, Dict[str, Any], None] = None

        if len(data) > offset:
            if message_type == MessageType.AUDIO_ONLY_RESPONSE:
                # Audio data - parse payload size first
                if len(data) >= offset + 4:
                    payload_size = struct.unpack(">I", data[offset : offset + 4])[0]
                    offset += 4
                    if len(data) >= offset + payload_size:
                        payload = data[offset : offset + payload_size]
            else:
                # JSON or other payload - parse payload size first
                if len(data) >= offset + 4:
                    payload_size = struct.unpack(">I", data[offset : offset + 4])[0]
                    offset += 4
                    if len(data) >= offset + payload_size:
                        payload_data = data[offset : offset + payload_size]

                        # Decompress if needed
                        if compression == CompressionMethod.GZIP:
                            payload_data = gzip.decompress(payload_data)

                        # Deserialize
                        if serialization == SerializationMethod.JSON:
                            try:
                                payload = json.loads(payload_data.decode("utf-8"))
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse JSON payload: {e}")
                                payload = payload_data
                        else:
                            payload = payload_data

        return ProtocolFrame(
            message_type=message_type,
            message_flags=message_flags,
            serialization=serialization,
            compression=compression,
            event=event,
            session_id=session_id,
            connection_id=connection_id,
            payload=payload,
            error_code=error_code,
        )

    def _encode_frame(
        self,
        message_type: MessageType,
        message_flags: int,
        serialization: SerializationMethod,
        compression: CompressionMethod,
        event: Optional[Event] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Encode a frame without session/connection ID."""
        frame = bytearray()

        # Byte 0: protocol version (4 bits) | header size (4 bits)
        byte0 = (self.PROTOCOL_VERSION << 4) | self.HEADER_SIZE
        frame.append(byte0)

        # Byte 1: message type (4 bits) | message flags (4 bits)
        byte1 = (message_type << 4) | message_flags
        frame.append(byte1)

        # Byte 2: serialization (4 bits) | compression (4 bits)
        byte2 = (serialization << 4) | compression
        frame.append(byte2)

        # Byte 3: reserved
        frame.append(0x00)

        # Event number (4 bytes, big endian) if WITH_EVENT flag is set
        if message_flags & MessageFlag.WITH_EVENT and event is not None:
            frame.extend(struct.pack(">i", event))

        # Payload
        if payload is not None:
            if serialization == SerializationMethod.JSON:
                payload_bytes = json.dumps(payload).encode("utf-8")
            else:
                payload_bytes = (
                    payload
                    if isinstance(payload, bytes)
                    else str(payload).encode("utf-8")
                )

            if compression == CompressionMethod.GZIP:
                payload_bytes = gzip.compress(payload_bytes)

            # Payload size (4 bytes, big endian)
            frame.extend(struct.pack(">I", len(payload_bytes)))
            frame.extend(payload_bytes)

        return bytes(frame)

    def _encode_session_frame(
        self,
        message_type: MessageType,
        message_flags: int,
        serialization: SerializationMethod,
        compression: CompressionMethod,
        event: Event,
        session_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Encode a frame with session ID."""
        frame = bytearray()

        # Byte 0: protocol version (4 bits) | header size (4 bits)
        byte0 = (self.PROTOCOL_VERSION << 4) | self.HEADER_SIZE
        frame.append(byte0)

        # Byte 1: message type (4 bits) | message flags (4 bits)
        byte1 = (message_type << 4) | message_flags
        frame.append(byte1)

        # Byte 2: serialization (4 bits) | compression (4 bits)
        byte2 = (serialization << 4) | compression
        frame.append(byte2)

        # Byte 3: reserved
        frame.append(0x00)

        # Event number (4 bytes, big endian)
        frame.extend(struct.pack(">i", event))

        # Session ID length (4 bytes, big endian) + session ID
        session_id_bytes = session_id.encode("utf-8")
        frame.extend(struct.pack(">I", len(session_id_bytes)))
        frame.extend(session_id_bytes)

        # Payload
        if payload is not None:
            if serialization == SerializationMethod.JSON:
                payload_bytes = json.dumps(payload).encode("utf-8")
            else:
                payload_bytes = (
                    payload
                    if isinstance(payload, bytes)
                    else str(payload).encode("utf-8")
                )

            if compression == CompressionMethod.GZIP:
                payload_bytes = gzip.compress(payload_bytes)

            # Payload size (4 bytes, big endian)
            frame.extend(struct.pack(">I", len(payload_bytes)))
            frame.extend(payload_bytes)

        return bytes(frame)
