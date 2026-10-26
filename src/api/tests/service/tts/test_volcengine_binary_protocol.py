"""Verify provider wire bytes independently of the production encoder/decoder."""

import gzip
import json
import struct

import pytest
from flaskr.api.tts.volcengine_protocol import (
    CompressionMethod,
    Event,
    MessageFlag,
    MessageType,
    SerializationMethod,
    VolcengineProtocol,
)


def _read_client_session(data: bytes) -> tuple[int, str, dict]:
    assert data[:4] == b"\x11\x14\x10\x00"
    event, length = struct.unpack(">iI", data[4:12])
    session = data[12 : 12 + length].decode("utf-8")
    offset = 12 + length
    payload_length = struct.unpack(">I", data[offset : offset + 4])[0]
    payload = data[offset + 4 :]
    assert len(payload) == payload_length
    return event, session, json.loads(payload)


@pytest.mark.parametrize(
    ("method", "event"),
    [("encode_start_connection", 1), ("encode_finish_connection", 2)],
)
def test_connection_requests_have_exact_wire_format(method: str, event: int) -> None:
    data = getattr(VolcengineProtocol(), method)()
    assert data == b"\x11\x14\x10\x00" + struct.pack(">iI", event, 2) + b"{}"


def test_default_session_start_contains_provider_defaults() -> None:
    protocol = VolcengineProtocol()
    event, session, payload = _read_client_session(
        protocol.encode_start_session("session", "voice")
    )
    assert event == 100
    assert session == protocol.session_id == "session"
    assert payload == {
        "user": {"uid": "ai-shifu"},
        "event": 100,
        "namespace": "BidirectionalTTS",
        "req_params": {
            "speaker": "voice",
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
                "speech_rate": 0,
                "loudness_rate": 0,
            },
        },
    }


@pytest.mark.parametrize(
    ("speed", "volume", "speech", "loudness"),
    [(0.5, 0.5, -50, -50), (1.0, 1.0, 0, 0), (2.0, 2.0, 100, 100)],
)
def test_session_options_are_encoded_in_provider_units(
    speed: float, volume: float, speech: int, loudness: int
) -> None:
    protocol = VolcengineProtocol()
    event, session, payload = _read_client_session(
        protocol.encode_start_session(
            "会话",
            "voice",
            audio_format="pcm",
            sample_rate=16000,
            speed=speed,
            volume=volume,
            emotion="happy",
            model="seed-tts-1.1",
            enable_timestamp=True,
            enable_subtitle=True,
        )
    )
    assert event == 100
    assert session == "会话"
    assert payload["req_params"] == {
        "speaker": "voice",
        "model": "seed-tts-1.1",
        "audio_params": {
            "format": "pcm",
            "sample_rate": 16000,
            "speech_rate": speech,
            "loudness_rate": loudness,
            "emotion": "happy",
            "enable_timestamp": True,
            "enable_subtitle": True,
        },
    }


def test_task_request_preserves_unicode_and_finish_has_empty_payload() -> None:
    protocol = VolcengineProtocol()
    event, session, payload = _read_client_session(
        protocol.encode_task_request("会话", "你好，world!")
    )
    assert event == 200
    assert session == "会话"
    assert payload["req_params"] == {"text": "你好，world!"}
    assert payload["event"] == 200
    assert _read_client_session(protocol.encode_finish_session("会话")) == (
        102,
        "会话",
        {},
    )


def _server_message(
    event: int,
    payload: bytes,
    identifier: str | None = None,
    *,
    audio: bool = False,
    compressed: bool = False,
) -> bytes:
    data = b"\x11" + bytes(
        [0xB4 if audio else 0x94, 0 if audio else 0x10 | int(compressed), 0]
    )
    data += struct.pack(">i", event)
    if identifier is not None:
        encoded = identifier.encode("utf-8")
        data += struct.pack(">I", len(encoded)) + encoded
    wire_payload = gzip.compress(payload) if compressed else payload
    return data + struct.pack(">I", len(wire_payload)) + wire_payload


@pytest.mark.parametrize("event", [50, 51, 52])
def test_connection_response_updates_connection_identity(event: int) -> None:
    protocol = VolcengineProtocol()
    frame = protocol.decode_frame(_server_message(event, b'{"ok": true}', "connection"))
    assert frame.event == event
    assert frame.connection_id == protocol.connection_id == "connection"
    assert frame.session_id is None
    assert frame.payload == {"ok": True}
    assert frame.error_code is None


@pytest.mark.parametrize("event", [150, 151, 152, 153, 350, 351, 352, 364])
def test_session_responses_preserve_event_and_unicode_identity(event: int) -> None:
    protocol = VolcengineProtocol()
    frame = protocol.decode_frame(_server_message(event, b'{"duration": 120}', "会话"))
    assert frame.event == event
    assert frame.session_id == "会话"
    assert frame.connection_id is None
    assert frame.payload == {"duration": 120}


def test_audio_response_preserves_binary_samples_and_ignores_trailing_bytes() -> None:
    samples = b"\x00\xff\x80\x01"
    data = _server_message(352, samples, "session", audio=True)
    frame = VolcengineProtocol().decode_frame(data + b"not part of payload")
    assert frame.message_type == MessageType.AUDIO_ONLY_RESPONSE
    assert frame.serialization == SerializationMethod.RAW
    assert frame.payload == samples


def test_compressed_json_and_error_frames_keep_provider_details() -> None:
    protocol = VolcengineProtocol()
    compressed = protocol.decode_frame(
        _server_message(153, b'{"message": "failed"}', "session", compressed=True)
    )
    assert compressed.compression == CompressionMethod.GZIP
    assert compressed.payload == {"message": "failed"}
    payload = b'{"message": "invalid request"}'
    error = protocol.decode_frame(
        b"\x11\xf0\x10\x00" + struct.pack(">II", 45000001, len(payload)) + payload
    )
    assert error.message_type == MessageType.ERROR_INFORMATION
    assert error.error_code == 45000001
    assert error.payload == {"message": "invalid request"}
    assert error.event is None


def test_unknown_event_and_invalid_json_preserve_raw_provider_payload() -> None:
    frame = VolcengineProtocol().decode_frame(
        _server_message(99999, b"provider diagnostic")
    )
    assert frame.event is None
    assert frame.payload == b"provider diagnostic"


@pytest.mark.parametrize("data", [b"", b"\x11", b"\x11\x94", b"\x11\x94\x10"])
def test_incomplete_header_is_rejected(data: bytes) -> None:
    with pytest.raises(ValueError, match="Frame too short"):
        VolcengineProtocol().decode_frame(data)


@pytest.mark.parametrize(
    "data",
    [
        b"\x11\x94\x10\x00",
        b"\x11\xf0\x10\x00",
        b"\x11\x90\x10\x00\x00",
        b"\x11\xb0\x00\x00\x00",
        b"\x11\x90\x10\x00\x00\x00\x00\x08{}",
        b"\x11\xb0\x00\x00\x00\x00\x00\x08ab",
        b"\x11\x94\x10\x00" + struct.pack(">iI", 50, 20) + b"id",
        b"\x11\x94\x10\x00" + struct.pack(">iI", 150, 20) + b"id",
    ],
)
def test_truncated_optional_fields_never_fabricate_payload(data: bytes) -> None:
    frame = VolcengineProtocol().decode_frame(data)
    assert frame.payload is None
    assert frame.connection_id is None
    assert frame.session_id is None


@pytest.mark.parametrize(
    ("serialization", "payload", "expected"),
    [
        (SerializationMethod.JSON, {"value": "data"}, b'{"value": "data"}'),
        (SerializationMethod.RAW, b"\x00\xff", b"\x00\xff"),
        (SerializationMethod.RAW, "text", b"text"),
    ],
)
@pytest.mark.parametrize(
    "compression", [CompressionMethod.NONE, CompressionMethod.GZIP]
)
def test_encoder_payload_lengths_use_compressed_wire_bytes(
    serialization: SerializationMethod,
    payload: object,
    expected: bytes,
    compression: CompressionMethod,
) -> None:
    protocol = VolcengineProtocol()
    frame = protocol._encode_frame(
        MessageType.FULL_CLIENT_REQUEST,
        MessageFlag.NO_EVENT,
        serialization,
        compression,
        payload=payload,
    )
    size = struct.unpack(">I", frame[4:8])[0]
    assert size == len(frame[8:])
    raw = (
        gzip.decompress(frame[8:])
        if compression == CompressionMethod.GZIP
        else frame[8:]
    )
    assert raw == expected
    session = protocol._encode_session_frame(
        MessageType.FULL_CLIENT_REQUEST,
        MessageFlag.WITH_EVENT,
        serialization,
        compression,
        Event.START_SESSION,
        "session",
        payload=payload,
    )
    session_size = struct.unpack(">I", session[19:23])[0]
    assert session_size == len(session[23:])
    session_raw = (
        gzip.decompress(session[23:])
        if compression == CompressionMethod.GZIP
        else session[23:]
    )
    assert session_raw == expected


def test_encoder_can_omit_payload_and_decoder_can_return_raw_message() -> None:
    protocol = VolcengineProtocol()
    empty = protocol._encode_frame(
        MessageType.FULL_CLIENT_REQUEST,
        MessageFlag.NO_EVENT,
        SerializationMethod.RAW,
        CompressionMethod.NONE,
    )
    assert empty == b"\x11\x10\x00\x00"
    empty_session = protocol._encode_session_frame(
        MessageType.FULL_CLIENT_REQUEST,
        MessageFlag.WITH_EVENT,
        SerializationMethod.RAW,
        CompressionMethod.NONE,
        Event.FINISH_SESSION,
        "x",
    )
    assert empty_session == b"\x11\x14\x00\x00" + struct.pack(">iI", 102, 1) + b"x"
    raw = protocol.decode_frame(b"\x11\x90\x00\x00" + struct.pack(">I", 3) + b"raw")
    assert raw.payload == b"raw"
