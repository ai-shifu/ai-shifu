"""
Tencent Cloud TTS provider.

Tencent's conversational SSE API is used server-side only. The browser keeps
the existing generic TTS/SSE contract and never receives Tencent credentials.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import io
import json
import logging
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

try:
    from pydub import AudioSegment as PydubAudioSegment
except ImportError:  # pragma: no cover - exercised only in minimal deployments
    PydubAudioSegment = None

from flaskr.api.tts.base import (
    AudioSettings,
    BaseTTSProvider,
    ParamRange,
    ProviderConfig,
    TTSResult,
    VoiceSettings,
)
from flaskr.common.config import get_config
from flaskr.common.log import AppLoggerProxy
from flaskr.service.tts import resolve_tts_billable_chars
from flaskr.service.tts.audio_utils import (
    concat_audio_best_effort,
    try_get_audio_duration_ms,
)
from flaskr.service.tts.subtitle_utils import normalize_subtitle_cues


logger = AppLoggerProxy(logging.getLogger(__name__))

TENCENT_TTS_HOST = "trtc.ai.tencentcloudapi.com"
TENCENT_TTS_ENDPOINT = f"https://{TENCENT_TTS_HOST}"
TENCENT_TTS_SERVICE = "trtc"
TENCENT_TTS_ACTION = "TextToSpeechSSE"
TENCENT_TTS_VERSION = "2019-07-22"
TENCENT_TTS_REGION = "ap-guangzhou"
TENCENT_TTS_ALGORITHM = "TC3-HMAC-SHA256"
TENCENT_DEFAULT_MODEL = "flow_01_turbo"
TENCENT_DEFAULT_VOICE_ID = "v-female-R2s4N9qJ"


def _premium_voice(value: str, label: str, language: str) -> dict[str, str]:
    language_label = {
        "zh": "中文",
        "en": "英文",
        "ja": "日语",
        "yue": "粤语",
    }.get(language, language)
    return {
        "value": value,
        "label": f"{label} ({language_label}, 精品音色)",
        "language": language,
    }


TENCENT_PREMIUM_VOICES = [
    _premium_voice("v-male-Bk7vD3xP", "威严霸总", "zh"),
    _premium_voice("v-female-R2s4N9qJ", "温柔姐姐", "zh"),
    _premium_voice("v-female-m1KpW7zE", "傲娇学姐", "zh"),
    _premium_voice("v-female-U8aT2yLf", "夹子女生", "zh"),
    _premium_voice("v-male-s5NqE0rZ", "闲聊男声", "zh"),
    _premium_voice("v-male-W1tH9jVc", "自然男声", "zh"),
    _premium_voice("female-kefu-xiaomei", "客服小美", "zh"),
    _premium_voice("female-kefu-xiaoxin", "客服小心", "zh"),
    _premium_voice("female-kefu-xiaoyue", "客服小悦", "zh"),
    _premium_voice("male-kefu-xiaoxu", "客服小徐", "zh"),
    _premium_voice("v-female-S6n2JxR5", "客服右琪", "zh"),
    _premium_voice("v-female-S6p4LxQ8", "客服小羊", "zh"),
    _premium_voice("v-female-H6p3LxP8", "客服小丁", "zh"),
    _premium_voice("v-male-S6m3LxP8", "客服小柒", "zh"),
    _premium_voice("v-female-A7c9QmP2", "温柔女老师", "en"),
    _premium_voice("v-male-X6h4TvP9", "暖心男老师", "en"),
    _premium_voice("v-male-R3p7LdW8", "阳光男老师", "en"),
    _premium_voice("v-male-K8s2QmJ4", "权威男老师", "en"),
    _premium_voice("v-male-U5n9DwC7", "理性男老师", "en"),
    _premium_voice("v-male-J1r4ZvH6", "真诚男老师", "en"),
    _premium_voice("v-female-P6q9LmR2", "温情女老师", "en"),
    _premium_voice("v-female-H7m4QpL8", "理性女老师", "en"),
    _premium_voice("v-female-N4s7VkJ3", "活泼女老师", "en"),
    _premium_voice("v-female-T3c8WdP6", "专业女老师", "en"),
    _premium_voice("v-female-R9k2LmV7", "自信女老师", "en"),
    _premium_voice("v-female-p9Xy7Q1L", "清晰女旁白", "en"),
    _premium_voice("v-female-Z3x9LmQ2", "理性女讲解", "en"),
    _premium_voice("v-male-A4b9KqP2", "严谨男讲师", "en"),
    _premium_voice("v-male-r7K2pQ9L", "权威男解读", "en"),
    _premium_voice("v-male-Q6p8ZxL3", "沉着男评审", "en"),
    _premium_voice("v-female-T3s8BqL9", "静心女教练", "en"),
    _premium_voice("v-male-P6q7LzD8", "温和男顾问", "en"),
    _premium_voice("v-female-M7k2PxL9", "内敛女播音", "en"),
    _premium_voice("v-female-S5n9QxJ4", "淡然女配音", "en"),
    _premium_voice("v-female-T8m4WxP7", "沉稳女配音", "en"),
    _premium_voice("v-male-D6p3KxN8", "深沉男评析", "en"),
    _premium_voice("v-female-A9b3KfL2", "温情女主持", "en"),
    _premium_voice("v-female-A7h2MxQ5", "真挚女创作", "en"),
    _premium_voice("v-male-G4n7RxM3", "温和男创作", "en"),
    _premium_voice("v-male-H3p9LxK7", "暖心男顾问", "en"),
    _premium_voice("v-male-R6n2MxT9", "真诚男主播", "en"),
    _premium_voice("v-female-C8k4NxL6", "自信女演员", "en"),
    _premium_voice("v-male-L7m5QxP4", "阳光男演讲", "en"),
    _premium_voice("v-male-N4k8TxR7", "理性男评论", "en"),
    _premium_voice("v-female-B7k5WxN4", "理智女旁白", "en"),
    _premium_voice("v-female-J3k7NxR2", "标准女播音", "ja"),
    _premium_voice("v-female-W6n8KxL5", "专业女配音", "ja"),
    _premium_voice("v-female-U4k9TxM3", "沉稳女配音", "ja"),
    _premium_voice("v-female-S2k7NxP9", "严肃女播音", "ja"),
    _premium_voice("v-female-Y5n2KxR8", "温和女旁白", "ja"),
    _premium_voice("v-male-J3n8DxK2", "沉稳男旁白", "ja"),
    _premium_voice("v-male-M7x2QrJ5", "沉稳男配音", "ja"),
    _premium_voice("v-male-F9c6LhY1", "庄重男配音", "ja"),
    _premium_voice("v-female-B5q9NvY6", "温和女配音", "ja"),
    _premium_voice("v-female-D2w6HcL4", "专业女旁白", "ja"),
    _premium_voice("v-female-J8m9NxT2", "温柔少女", "ja"),
    _premium_voice("v-female-R7k3MxW5", "温柔女讲师", "ja"),
    _premium_voice("v-female-H6p2LxQ8", "俏皮女主播", "ja"),
    _premium_voice("v-male-T4n8KxM3", "沉稳男主持", "ja"),
    _premium_voice("v-male-M5k7NxP9", "平和男旁白", "ja"),
    _premium_voice("v-female-P3n6LxW4", "专业女讲师", "ja"),
    _premium_voice("v-male-C9m4QxL7", "庄重男播音", "ja"),
    _premium_voice("v-female-E8k2NxV6", "温和女讲师", "ja"),
    _premium_voice("v-male-D5k8MxN2", "专业男讲师", "ja"),
    _premium_voice("v-male-S6n3KxW9", "庄重男解说", "ja"),
    _premium_voice("v-male-L4k9NxT7", "优雅男讲师", "ja"),
    _premium_voice("v-male-H5k7NxM3", "儒雅男播音", "ja"),
    _premium_voice("v-male-B6k3NxQ9", "深沉男讲师", "ja"),
    _premium_voice("v-female-K9m5NxL4", "中性女播音", "ja"),
    _premium_voice("v-female-k3P8sL0Q", "雅致女解说", "yue"),
    _premium_voice("v-male-L4s7PqZ9", "沉稳男解说", "yue"),
    _premium_voice("v-female-S8p3JwK6", "温和女播音", "yue"),
    _premium_voice("v-female-N7c3LpV5", "理性女向导", "yue"),
    _premium_voice("v-male-P8r6MdQ3", "儒雅男讲员", "yue"),
    _premium_voice("v-male-Q2f7RdP6", "稳重男向导", "yue"),
    _premium_voice("v-female-C5t1QxH9", "自信女讲师", "yue"),
    _premium_voice("v-male-D7p4XcL2", "自然男播音", "yue"),
]
TENCENT_DEFAULT_SAMPLE_RATE = 16000
TENCENT_DEFAULT_CODEC = "mp3"
TENCENT_SSE_REQUEST_CODEC = "pcm"
TENCENT_ENABLE_SUBTITLE = True
TENCENT_MAX_SESSION_CHARS = 255

_TERMINAL_PUNCTUATION = set(".!?;。！？；")

TENCENT_EMOTIONS = [
    {
        "value": "",
        "label": "Default",
    },
    {
        "value": "neutral",
        "label": "Neutral",
    },
    {
        "value": "happy",
        "label": "Happy",
    },
    {
        "value": "sad",
        "label": "Sad",
    },
    {
        "value": "angry",
        "label": "Angry",
    },
    {
        "value": "fear",
        "label": "Fear",
    },
    {
        "value": "news",
        "label": "News",
    },
    {
        "value": "story",
        "label": "Story",
    },
    {
        "value": "radio",
        "label": "Radio",
    },
    {
        "value": "poetry",
        "label": "Poetry",
    },
    {
        "value": "call",
        "label": "Customer Service",
    },
    {
        "value": "customer_service",
        "label": "Customer Service",
    },
    {
        "value": "assistant",
        "label": "Assistant",
    },
]


@dataclass(frozen=True)
class TencentTTSCredentials:
    app_id: int
    secret_id: str
    secret_key: str


@dataclass(frozen=True)
class TencentSSEStreamChunk:
    audio_data: bytes
    is_final: bool = False
    subtitles: list[dict[str, Any]] = field(default_factory=list)
    seq: int = 0
    request_id: str = ""
    chunk_id: str = ""


class TencentTTSError(ValueError):
    def __init__(
        self,
        *,
        code: Any,
        message: str = "",
        request_id: str = "",
        message_id: str = "",
    ):
        safe_message = str(message or "provider error").strip()
        detail = f"Tencent TTS error {code}: {safe_message}"
        if request_id:
            detail += f" (request_id={request_id})"
        if message_id:
            detail += f" (message_id={message_id})"
        super().__init__(detail)
        self.code = code
        self.request_id = request_id
        self.message_id = message_id


def _tencent_codec(value: Any = None) -> str:
    codec = str(value or TENCENT_DEFAULT_CODEC).lower()
    if codec != TENCENT_DEFAULT_CODEC:
        logger.warning(
            "Tencent TTS only supports mp3 in this integration; got %s", codec
        )
        return TENCENT_DEFAULT_CODEC
    return TENCENT_DEFAULT_CODEC


def _concat_tencent_audio_segments(
    audio_segments: list[bytes],
    *,
    output_format: str,
) -> bytes:
    final_audio = concat_audio_best_effort(audio_segments, output_format=output_format)
    if final_audio:
        return final_audio

    if len(audio_segments) == 1:
        return audio_segments[0]
    return b"".join(segment for segment in audio_segments if segment)


def _tencent_pcm_duration_ms(audio_data: bytes, *, sample_rate: int) -> int:
    if not audio_data:
        return 0
    bytes_per_second = max(int(sample_rate or TENCENT_DEFAULT_SAMPLE_RATE), 1) * 2
    return int(round(len(audio_data) * 1000 / bytes_per_second))


def _export_tencent_pcm_to_mp3(audio_data: bytes, *, sample_rate: int) -> bytes:
    if not audio_data:
        return b""
    if PydubAudioSegment is None:
        raise ValueError("pydub is required to convert Tencent TTS PCM audio to MP3")

    segment = PydubAudioSegment(
        data=audio_data,
        sample_width=2,
        frame_rate=int(sample_rate or TENCENT_DEFAULT_SAMPLE_RATE),
        channels=1,
    )
    output = io.BytesIO()
    segment.export(output, format=TENCENT_DEFAULT_CODEC, bitrate="128k")
    return output.getvalue()


def _coerce_app_id(app_id: Any) -> int:
    try:
        return int(app_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Tencent TTS AppId: {app_id!r}") from exc


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return min(max(float(value), minimum), maximum)


def _tencent_flow_speed(value: Any) -> float:
    try:
        legacy_speed = float(value or 0)
    except (TypeError, ValueError):
        legacy_speed = 0
    if legacy_speed <= 0:
        mapped = 1.0 + (legacy_speed * 0.2)
    else:
        mapped = 1.0 + (legacy_speed * 0.25)
    return round(_clamp_float(mapped, 0.5, 2.0), 2)


def _tencent_flow_volume(value: Any) -> float:
    try:
        volume = float(value or 0)
    except (TypeError, ValueError):
        volume = 0
    if volume <= 0:
        return 1.0
    return round(_clamp_float(volume, 0.1, 1.0), 2)


def _tencent_voice_language(voice_id: str) -> str:
    normalized_voice_id = str(voice_id or "").strip()
    for voice in TENCENT_PREMIUM_VOICES:
        if voice.get("value") == normalized_voice_id:
            return str(voice.get("language") or "zh")
    return "zh"


def _normalize_tencent_voice_id(voice_id: Any) -> str:
    normalized_voice_id = str(voice_id or "").strip()
    if not normalized_voice_id:
        return TENCENT_DEFAULT_VOICE_ID
    return normalized_voice_id


def _resolve_tencent_model(model: Optional[str], emotion: str = "") -> str:
    _ = emotion
    normalized_model = str(model or "").strip()
    if normalized_model == TENCENT_DEFAULT_MODEL:
        return normalized_model
    return TENCENT_DEFAULT_MODEL


def _normalize_tencent_emotion(emotion: Any) -> str:
    normalized = str(emotion or "").strip()
    emotion_aliases = {
        "fear": "fearful",
        "neutral": "",
        "call": "",
        "customer_service": "",
        "assistant": "",
        "news": "",
        "story": "",
        "radio": "",
        "poetry": "",
    }
    return emotion_aliases.get(normalized, normalized)


def build_tencent_sse_payload(
    *,
    app_id: Any,
    text: str,
    voice_settings: VoiceSettings,
    audio_settings: AudioSettings,
    model: Optional[str] = None,
) -> dict[str, Any]:
    voice_id = _normalize_tencent_voice_id(
        getattr(voice_settings, "voice_id", "") or TENCENT_DEFAULT_VOICE_ID
    )
    normalized_emotion = _normalize_tencent_emotion(
        getattr(voice_settings, "emotion", "") or ""
    )
    voice_payload: dict[str, Any] = {
        "VoiceId": voice_id,
        "Speed": _tencent_flow_speed(getattr(voice_settings, "speed", 0)),
        "Volume": _tencent_flow_volume(getattr(voice_settings, "volume", 0)),
        "Pitch": int(getattr(voice_settings, "pitch", 0) or 0),
    }
    if normalized_emotion:
        voice_payload["Emotion"] = normalized_emotion

    sample_rate = int(
        getattr(audio_settings, "sample_rate", TENCENT_DEFAULT_SAMPLE_RATE)
        or TENCENT_DEFAULT_SAMPLE_RATE
    )
    params: dict[str, Any] = {
        "Text": str(text or "").strip(),
        "SdkAppId": _coerce_app_id(app_id),
        "Voice": voice_payload,
        "AudioFormat": {
            "Format": TENCENT_SSE_REQUEST_CODEC,
            "SampleRate": sample_rate,
            "Bitrate": 128,
        },
        "Model": _resolve_tencent_model(model, normalized_emotion),
        "Language": _tencent_voice_language(voice_id),
        "AlignmentMode": 1 if TENCENT_ENABLE_SUBTITLE else 0,
    }
    return params


def encode_tencent_sse_payload(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tc3_sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def build_tencent_tc3_headers(
    *,
    payload_json: str,
    secret_id: str,
    secret_key: str,
    timestamp: Optional[int] = None,
) -> dict[str, str]:
    request_timestamp = int(timestamp if timestamp is not None else time.time())
    request_date = dt.datetime.fromtimestamp(
        request_timestamp,
        tz=dt.timezone.utc,
    ).strftime("%Y-%m-%d")
    canonical_headers = (
        "content-type:application/json\n"
        f"host:{TENCENT_TTS_HOST}\n"
        f"x-tc-action:{TENCENT_TTS_ACTION.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            "",
            canonical_headers,
            signed_headers,
            _sha256_hex(payload_json),
        ]
    )
    credential_scope = f"{request_date}/{TENCENT_TTS_SERVICE}/tc3_request"
    string_to_sign = "\n".join(
        [
            TENCENT_TTS_ALGORITHM,
            str(request_timestamp),
            credential_scope,
            _sha256_hex(canonical_request),
        ]
    )
    secret_date = _tc3_sign(
        ("TC3" + str(secret_key or "")).encode("utf-8"), request_date
    )
    secret_service = _tc3_sign(secret_date, TENCENT_TTS_SERVICE)
    secret_signing = _tc3_sign(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"{TENCENT_TTS_ALGORITHM} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Host": TENCENT_TTS_HOST,
        "X-TC-Action": TENCENT_TTS_ACTION,
        "X-TC-Version": TENCENT_TTS_VERSION,
        "X-TC-Region": TENCENT_TTS_REGION,
        "X-TC-Timestamp": str(request_timestamp),
    }


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text or "")


def ensure_tencent_terminal_punctuation(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return normalized
    if normalized[-1] in _TERMINAL_PUNCTUATION:
        return normalized
    punctuation = "。" if _contains_cjk(normalized) else "."
    return f"{normalized}{punctuation}"


def _split_tencent_sentence_units(text: str) -> list[str]:
    units: list[str] = []
    cursor = 0
    for index, char in enumerate(text or ""):
        if char in _TERMINAL_PUNCTUATION:
            unit = text[cursor : index + 1].strip()
            if unit:
                units.append(unit)
            cursor = index + 1
    tail = str(text or "")[cursor:].strip()
    if tail:
        units.append(tail)
    normalized = str(text or "").strip()
    return units or ([normalized] if normalized else [])


def _trim_tencent_source_range(text: str, start: int, end: int) -> tuple[int, int]:
    safe_start = max(int(start or 0), 0)
    safe_end = min(max(int(end or 0), safe_start), len(text))
    while safe_start < safe_end and text[safe_start].isspace():
        safe_start += 1
    while safe_end > safe_start and text[safe_end - 1].isspace():
        safe_end -= 1
    return safe_start, safe_end


def _split_tencent_sentence_units_with_ranges(
    text: str,
) -> list[tuple[str, int, int]]:
    source = str(text or "")
    units: list[tuple[str, int, int]] = []
    cursor = 0
    for index, char in enumerate(source):
        if char in _TERMINAL_PUNCTUATION:
            start, end = _trim_tencent_source_range(source, cursor, index + 1)
            if start < end:
                units.append((source[start:end], start, end))
            cursor = index + 1
    start, end = _trim_tencent_source_range(source, cursor, len(source))
    if start < end:
        units.append((source[start:end], start, end))
    if units:
        return units

    normalized = source.strip()
    if not normalized:
        return []
    start = source.find(normalized)
    if start < 0:
        start = 0
    return [(normalized, start, start + len(normalized))]


def _tencent_speech_weight(text: str) -> int:
    weight = 0
    for char in str(text or ""):
        if char.isspace():
            continue
        if unicodedata.category(char).startswith("P"):
            continue
        weight += 1
    return weight


def _normalize_tencent_grouping_cues(
    cues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw_item in list(cues or []):
        if not isinstance(raw_item, dict):
            continue
        text = str(raw_item.get("text", "") or "").strip()
        if not text:
            continue
        start_ms = max(int(raw_item.get("start_ms", 0) or 0), 0)
        end_ms = max(int(raw_item.get("end_ms", start_ms) or start_ms), start_ms)
        item = {
            "text": text,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "segment_index": max(int(raw_item.get("segment_index", 0) or 0), 0),
            "position": max(int(raw_item.get("position", 0) or 0), 0),
        }
        if raw_item.get("begin_index") is not None:
            item["begin_index"] = max(int(raw_item.get("begin_index") or 0), 0)
        if raw_item.get("end_index") is not None:
            item["end_index"] = max(
                int(raw_item.get("end_index") or 0),
                int(item.get("begin_index", 0) or 0),
            )
        normalized.append(item)

    normalized.sort(
        key=lambda cue: (
            int(cue.get("position", 0) or 0),
            int(cue.get("segment_index", 0) or 0),
            int(cue.get("start_ms", 0) or 0),
            int(cue.get("end_ms", 0) or 0),
        )
    )
    return normalized


def _group_tencent_subtitle_cues_by_source_indices(
    cues: list[dict[str, Any]],
    *,
    source_text: str,
) -> list[dict[str, Any]]:
    sentence_ranges = _split_tencent_sentence_units_with_ranges(source_text)
    indexed_cues = [
        cue
        for cue in cues
        if cue.get("begin_index") is not None and cue.get("end_index") is not None
    ]
    if not sentence_ranges or not indexed_cues:
        return []

    first_cue = cues[0]
    segment_index = int(first_cue.get("segment_index", 0) or 0)
    position = int(first_cue.get("position", 0) or 0)
    grouped: list[dict[str, Any]] = []
    for unit, sentence_start, sentence_end in sentence_ranges:
        overlapping = []
        for cue in indexed_cues:
            cue_start = int(cue.get("begin_index", 0) or 0)
            cue_end = int(cue.get("end_index", cue_start) or cue_start)
            if cue_end > sentence_start and cue_start < sentence_end:
                overlapping.append(cue)
        if not overlapping:
            return []
        start_ms = min(int(cue.get("start_ms", 0) or 0) for cue in overlapping)
        end_ms = max(
            int(cue.get("end_ms", start_ms) or start_ms) for cue in overlapping
        )
        grouped.append(
            {
                "text": unit,
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms),
                "segment_index": segment_index,
                "position": position,
            }
        )

    return normalize_subtitle_cues(grouped)


def _group_tencent_subtitle_cues_by_source_text(
    cues: list[dict[str, Any]],
    *,
    source_text: str,
) -> list[dict[str, Any]]:
    normalized_cues = _normalize_tencent_grouping_cues(cues)
    sentence_units = _split_tencent_sentence_units(source_text)
    if not normalized_cues or not sentence_units:
        return []

    indexed_grouped = _group_tencent_subtitle_cues_by_source_indices(
        normalized_cues,
        source_text=source_text,
    )
    if indexed_grouped:
        return indexed_grouped

    first_cue = normalized_cues[0]
    start_ms = min(int(cue.get("start_ms", 0) or 0) for cue in normalized_cues)
    end_ms = max(int(cue.get("end_ms", 0) or 0) for cue in normalized_cues)
    end_ms = max(end_ms, start_ms)
    segment_index = int(first_cue.get("segment_index", 0) or 0)
    position = int(first_cue.get("position", 0) or 0)
    duration_ms = max(end_ms - start_ms, 0)

    cue_weights = [
        max(_tencent_speech_weight(str(cue.get("text", "") or "")), 0)
        for cue in normalized_cues
    ]
    total_cue_weight = sum(cue_weights)
    sentence_weights = [max(_tencent_speech_weight(unit), 1) for unit in sentence_units]
    total_sentence_weight = sum(sentence_weights) or 1

    def _time_at_weight(target_weight: float) -> int:
        if total_cue_weight <= 0:
            ratio = target_weight / total_sentence_weight
            return start_ms + int(round(duration_ms * ratio))

        bounded_target = max(min(float(target_weight), float(total_cue_weight)), 0.0)
        consumed = 0.0
        last_end_ms = start_ms
        for index, (cue, weight) in enumerate(zip(normalized_cues, cue_weights)):
            cue_start_ms = int(cue.get("start_ms", 0) or 0)
            cue_end_ms = int(cue.get("end_ms", cue_start_ms) or cue_start_ms)
            cue_end_ms = max(cue_end_ms, cue_start_ms)
            if weight <= 0:
                if bounded_target <= consumed:
                    return cue_end_ms
                last_end_ms = cue_end_ms
                continue
            if bounded_target <= consumed + weight:
                ratio = (bounded_target - consumed) / weight
                target_ms = cue_start_ms + int(
                    round((cue_end_ms - cue_start_ms) * ratio)
                )
                if bounded_target >= consumed + weight:
                    for next_cue, next_weight in zip(
                        normalized_cues[index + 1 :],
                        cue_weights[index + 1 :],
                    ):
                        if next_weight > 0:
                            break
                        next_end_ms = int(
                            next_cue.get(
                                "end_ms",
                                next_cue.get("start_ms", target_ms),
                            )
                            or target_ms
                        )
                        target_ms = max(target_ms, next_end_ms)
                return target_ms
            consumed += weight
            last_end_ms = cue_end_ms
        return max(last_end_ms, end_ms)

    grouped: list[dict[str, Any]] = []
    sentence_cursor = 0
    timeline_cursor_ms = start_ms
    for index, unit in enumerate(sentence_units):
        next_sentence_cursor = sentence_cursor + sentence_weights[index]
        if total_cue_weight > 0:
            source_start_weight = (
                total_cue_weight * sentence_cursor / total_sentence_weight
            )
            source_end_weight = (
                total_cue_weight * next_sentence_cursor / total_sentence_weight
            )
            cue_start_ms = _time_at_weight(source_start_weight)
            cue_end_ms = _time_at_weight(source_end_weight)
        else:
            cue_start_ms = start_ms + int(
                round(duration_ms * sentence_cursor / total_sentence_weight)
            )
            cue_end_ms = start_ms + int(
                round(duration_ms * next_sentence_cursor / total_sentence_weight)
            )

        cue_start_ms = max(cue_start_ms, timeline_cursor_ms)
        if index == len(sentence_units) - 1:
            cue_end_ms = end_ms
        cue_end_ms = max(cue_end_ms, cue_start_ms)
        grouped.append(
            {
                "text": unit,
                "start_ms": cue_start_ms,
                "end_ms": cue_end_ms,
                "segment_index": segment_index,
                "position": position,
            }
        )
        sentence_cursor = next_sentence_cursor
        timeline_cursor_ms = cue_end_ms

    return normalize_subtitle_cues(grouped)


def _tencent_subtitle_text(raw_item: dict[str, Any]) -> str:
    for key in ("Text", "text", "Word", "word", "Sentence", "sentence"):
        text = str(raw_item.get(key, "") or "").strip()
        if text:
            return text
    return ""


def _tencent_subtitle_time_ms(
    raw_item: dict[str, Any], keys: tuple[str, ...], default_ms: int = 0
) -> int:
    for key in keys:
        if key not in raw_item:
            continue
        value = raw_item.get(key)
        if value is None or value == "":
            continue
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            continue
    return int(default_ms or 0)


def _tencent_subtitle_index(
    raw_item: dict[str, Any], keys: tuple[str, ...]
) -> Optional[int]:
    for key in keys:
        if key not in raw_item:
            continue
        value = raw_item.get(key)
        if value is None or value == "":
            continue
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            continue
    return None


def normalize_tencent_subtitle_cues(
    subtitles: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    offset_ms: int = 0,
    segment_index: int = 0,
    position: int = 0,
    source_text: str = "",
) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    seen_cue_keys: set[tuple[str, int, int, Optional[int], Optional[int]]] = set()
    for raw_item in list(subtitles or []):
        if not isinstance(raw_item, dict):
            continue
        text = _tencent_subtitle_text(raw_item)
        if not text:
            continue
        start_ms = _tencent_subtitle_time_ms(
            raw_item,
            (
                "BeginTime",
                "begin_time",
                "beginTime",
                "StartTime",
                "start_time",
                "start_ms",
                "begin",
            ),
        )
        end_ms = _tencent_subtitle_time_ms(
            raw_item,
            (
                "EndTime",
                "end_time",
                "endTime",
                "FinishTime",
                "finish_time",
                "end_ms",
                "end",
            ),
            default_ms=start_ms,
        )
        begin_index = _tencent_subtitle_index(
            raw_item,
            (
                "BeginIndex",
                "begin_index",
                "beginIndex",
                "TextBegin",
                "text_begin",
            ),
        )
        end_index = _tencent_subtitle_index(
            raw_item,
            (
                "EndIndex",
                "end_index",
                "endIndex",
                "TextEnd",
                "text_end",
            ),
        )
        if (
            begin_index is not None
            and end_index is not None
            and end_index < begin_index
        ):
            end_index = begin_index
        cue_key = (text, start_ms, end_ms, begin_index, end_index)
        if cue_key in seen_cue_keys:
            continue
        seen_cue_keys.add(cue_key)
        safe_offset_ms = max(int(offset_ms or 0), 0)
        cue = {
            "text": text,
            "start_ms": max(start_ms + safe_offset_ms, 0),
            "end_ms": max(end_ms + safe_offset_ms, start_ms + safe_offset_ms),
            "segment_index": max(int(segment_index or 0), 0),
            "position": max(int(position or 0), 0),
        }
        if begin_index is not None:
            cue["begin_index"] = begin_index
        if end_index is not None:
            cue["end_index"] = end_index
        cues.append(cue)
    source_sentence_units = _split_tencent_sentence_units(str(source_text or ""))
    if len(source_sentence_units) > 1:
        source_grouped_cues = _group_tencent_subtitle_cues_by_source_text(
            cues,
            source_text=str(source_text or ""),
        )
        if source_grouped_cues:
            return source_grouped_cues
    return _group_tencent_subtitle_cues_by_sentence(cues)


def _group_tencent_subtitle_cues_by_sentence(
    cues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None

    for cue in normalize_subtitle_cues(cues):
        text = str(cue.get("text", "") or "").strip()
        if not text:
            continue

        start_ms = int(cue.get("start_ms", 0) or 0)
        end_ms = int(cue.get("end_ms", start_ms) or start_ms)
        if current is None:
            current = {
                "text": text,
                "start_ms": start_ms,
                "end_ms": max(end_ms, start_ms),
                "segment_index": int(cue.get("segment_index", 0) or 0),
                "position": int(cue.get("position", 0) or 0),
            }
        else:
            current["text"] = f"{current.get('text', '')}{text}"
            current["end_ms"] = max(
                int(current.get("end_ms", 0) or 0),
                end_ms,
                start_ms,
            )

        if text[-1] in _TERMINAL_PUNCTUATION:
            grouped.append(current)
            current = None

    if current is not None:
        grouped.append(current)
    return normalize_subtitle_cues(grouped)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default or 0)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _get_first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _is_nonzero_tencent_code(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip()
    return bool(normalized) and normalized != "0"


def _unwrap_tencent_sse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("Response") or payload.get("response")
    if isinstance(response, dict):
        return response
    return payload


def _decode_tencent_sse_line(raw_line: Any) -> str:
    if isinstance(raw_line, bytes):
        return raw_line.decode("utf-8", errors="replace").strip()
    return str(raw_line or "").strip()


def _extract_tencent_sse_subtitles(
    payload: dict[str, Any],
    *,
    request_text: str,
) -> list[dict[str, Any]]:
    result = payload.get("Result") or payload.get("result") or {}
    subtitle_items = payload.get("Subtitles") or payload.get("subtitles")
    if subtitle_items is None and isinstance(result, dict):
        subtitle_items = result.get("Subtitles") or result.get("subtitles")
    if isinstance(subtitle_items, list):
        return [dict(item) for item in subtitle_items if isinstance(item, dict)]

    alignments = payload.get("Alignments") or payload.get("alignments") or []
    if not isinstance(alignments, list):
        return []

    subtitles: list[dict[str, Any]] = []
    text = str(request_text or "")
    for raw_item in alignments:
        if not isinstance(raw_item, dict):
            continue
        begin_index = _coerce_int(
            raw_item.get("TextBegin")
            or raw_item.get("text_begin")
            or raw_item.get("BeginIndex")
            or raw_item.get("begin_index"),
            0,
        )
        end_index = _coerce_int(
            raw_item.get("TextEnd")
            or raw_item.get("text_end")
            or raw_item.get("EndIndex")
            or raw_item.get("end_index"),
            begin_index,
        )
        if end_index < begin_index:
            end_index = begin_index
        cue_text = str(raw_item.get("Text") or raw_item.get("text") or "").strip()
        if not cue_text and text and end_index > begin_index:
            cue_text = text[begin_index:end_index].strip()
        if not cue_text:
            continue
        begin_time = _coerce_int(
            raw_item.get("TimeBeginMs")
            or raw_item.get("time_begin_ms")
            or raw_item.get("BeginTime")
            or raw_item.get("begin_time"),
            0,
        )
        end_time = _coerce_int(
            raw_item.get("TimeEndMs")
            or raw_item.get("time_end_ms")
            or raw_item.get("EndTime")
            or raw_item.get("end_time"),
            begin_time,
        )
        subtitles.append(
            {
                "Text": cue_text,
                "BeginTime": begin_time,
                "EndTime": max(end_time, begin_time),
                "BeginIndex": begin_index,
                "EndIndex": end_index,
            }
        )
    return subtitles


def parse_tencent_sse_message(
    payload: dict[str, Any],
    *,
    request_text: str,
) -> Optional[TencentSSEStreamChunk]:
    message = _unwrap_tencent_sse_payload(payload)
    error_payload = _get_first_present(message, "Error", "error")
    message_type = str(
        _get_first_present(message, "Type", "type")
        or _get_first_present(payload, "Type", "type")
        or ""
    ).lower()
    status_code = _get_first_present(message, "code", "Code")
    if (
        message_type == "error"
        or isinstance(error_payload, dict)
        or _is_nonzero_tencent_code(status_code)
    ):
        error = error_payload if isinstance(error_payload, dict) else message
        raise TencentTTSError(
            code=error.get("Code") or error.get("code") or status_code or "Unknown",
            message=str(error.get("Message") or error.get("message") or ""),
            request_id=str(
                _get_first_present(message, "RequestId", "request_id")
                or _get_first_present(payload, "RequestId", "request_id")
                or ""
            ),
            message_id=str(
                _get_first_present(message, "MessageId", "message_id")
                or _get_first_present(payload, "MessageId", "message_id")
                or ""
            ),
        )
    if message_type and message_type not in {"audio", "chunk"}:
        return None

    subtitles = _extract_tencent_sse_subtitles(message, request_text=request_text)
    has_final_field = any(
        key in message
        for key in ("IsEnd", "is_end", "Final", "final", "IsFinal", "is_final")
    )
    audio_value = str(
        _get_first_present(message, "Audio", "audio", "AudioData", "audio_data") or ""
    )
    try:
        audio_data = (
            base64.b64decode(audio_value, validate=True) if audio_value else b""
        )
    except ValueError as exc:
        raise ValueError("Invalid Tencent TTS SSE audio base64") from exc
    if not audio_data and not subtitles and not has_final_field:
        return None

    return TencentSSEStreamChunk(
        audio_data=audio_data,
        is_final=_coerce_bool(
            _get_first_present(
                message,
                "IsEnd",
                "is_end",
                "Final",
                "final",
                "IsFinal",
                "is_final",
            )
        ),
        subtitles=subtitles,
        seq=_coerce_int(_get_first_present(message, "Seq", "seq"), 0),
        request_id=str(_get_first_present(message, "RequestId", "request_id") or ""),
        chunk_id=str(_get_first_present(message, "ChunkId", "chunk_id") or ""),
    )


class TencentTTSProvider(BaseTTSProvider):
    @property
    def provider_name(self) -> str:
        return "tencent"

    def get_credentials(self) -> TencentTTSCredentials:
        app_id = get_config("TENCENT_TTS_APP_ID", "")
        secret_id = str(get_config("TENCENT_TTS_SECRET_ID", "") or "").strip()
        secret_key = str(get_config("TENCENT_TTS_SECRET_KEY", "") or "").strip()
        if not secret_id or not secret_key:
            raise ValueError("Tencent TTS credentials are not configured")
        return TencentTTSCredentials(
            app_id=_coerce_app_id(app_id),
            secret_id=secret_id,
            secret_key=secret_key,
        )

    def is_configured(self) -> bool:
        try:
            self.get_credentials()
        except ValueError:
            return False
        return True

    def get_default_voice_settings(self) -> VoiceSettings:
        return VoiceSettings(
            voice_id=TENCENT_DEFAULT_VOICE_ID,
            speed=0,
            pitch=0,
            emotion="",
            volume=0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        return AudioSettings(
            format=_tencent_codec(),
            sample_rate=TENCENT_DEFAULT_SAMPLE_RATE,
            bitrate=128000,
            channel=1,
        )

    def get_supported_emotions(self) -> list[str]:
        return [item["value"] for item in TENCENT_EMOTIONS if item["value"]]

    def get_supported_voices(self) -> list[dict[str, str]]:
        return [dict(voice) for voice in TENCENT_PREMIUM_VOICES]

    def get_provider_config(self) -> ProviderConfig:
        return ProviderConfig(
            name=self.provider_name,
            label="腾讯云语音合成",
            speed=ParamRange(min=-2, max=6, step=0.1, default=0),
            pitch=ParamRange(min=0, max=0, step=1, default=0),
            supports_emotion=True,
            models=[],
            voices=self.get_supported_voices(),
            emotions=list(TENCENT_EMOTIONS),
        )

    def _split_text(self, text: str) -> list[str]:
        max_chars = max(TENCENT_MAX_SESSION_CHARS, 1)
        normalized = str(text or "").strip()
        if not normalized:
            return []
        return [
            normalized[start : start + max_chars]
            for start in range(0, len(normalized), max_chars)
        ]

    def stream_synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ):
        if not self.is_configured():
            raise ValueError("Tencent TTS is not configured")
        request_text = str(text or "").strip()
        if not request_text:
            raise ValueError("Text cannot be empty")

        credentials = self.get_credentials()
        effective_voice_settings = voice_settings or self.get_default_voice_settings()
        if not effective_voice_settings.voice_id:
            effective_voice_settings.voice_id = TENCENT_DEFAULT_VOICE_ID
        effective_audio_settings = audio_settings or self.get_default_audio_settings()
        effective_audio_settings.format = _tencent_codec(
            effective_audio_settings.format
        )

        payload = build_tencent_sse_payload(
            app_id=credentials.app_id,
            text=request_text,
            voice_settings=effective_voice_settings,
            audio_settings=effective_audio_settings,
            model=model,
        )
        payload_json = encode_tencent_sse_payload(payload)
        headers = build_tencent_tc3_headers(
            payload_json=payload_json,
            secret_id=credentials.secret_id,
            secret_key=credentials.secret_key,
        )

        logger.debug(
            "Calling Tencent conversational SSE TTS with text_length=%s, voice_id=%s",
            len(request_text),
            payload.get("Voice", {}).get("VoiceId"),
        )
        response = requests.post(
            TENCENT_TTS_ENDPOINT,
            data=payload_json.encode("utf-8"),
            headers=headers,
            stream=True,
            timeout=(10, 90),
        )
        response.raise_for_status()

        received_audio = False
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                line = _decode_tencent_sse_line(raw_line)
                if not line:
                    continue
                if line.startswith(":"):
                    continue
                lower_line = line.lower()
                if (
                    lower_line.startswith("event:")
                    or lower_line.startswith("id:")
                    or lower_line.startswith("retry:")
                ):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break

                try:
                    message = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError("Invalid Tencent TTS SSE JSON response") from exc
                chunk = parse_tencent_sse_message(message, request_text=request_text)
                if chunk is None:
                    continue
                if chunk.audio_data:
                    received_audio = True
                if chunk.is_final and not received_audio:
                    raise ValueError("No audio data received from Tencent TTS")
                yield chunk
                if chunk.is_final:
                    break
            if not received_audio:
                raise ValueError("No audio data received from Tencent TTS")
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> TTSResult:
        if not self.is_configured():
            raise ValueError("Tencent TTS is not configured")
        request_text = str(text or "").strip()
        if not request_text:
            raise ValueError("Text cannot be empty")

        effective_voice_settings = voice_settings or self.get_default_voice_settings()
        if not effective_voice_settings.voice_id:
            effective_voice_settings.voice_id = TENCENT_DEFAULT_VOICE_ID
        effective_audio_settings = audio_settings or self.get_default_audio_settings()
        effective_audio_settings.format = _tencent_codec(
            effective_audio_settings.format
        )

        audio_segments: list[bytes] = []
        subtitle_cues: list[dict[str, Any]] = []
        subtitle_offset_ms = 0
        duration_total_ms = 0
        sample_rate = int(
            effective_audio_settings.sample_rate or TENCENT_DEFAULT_SAMPLE_RATE
        )

        for chunk in self._split_text(request_text):
            chunk_text = ensure_tencent_terminal_punctuation(chunk)
            chunk_pcm_segments: list[bytes] = []
            raw_subtitles: list[dict[str, Any]] = []
            for stream_chunk in self.stream_synthesize(
                text=chunk_text,
                voice_settings=effective_voice_settings,
                audio_settings=effective_audio_settings,
                model=model,
            ):
                if stream_chunk.audio_data:
                    chunk_pcm_segments.append(stream_chunk.audio_data)
                raw_subtitles.extend(
                    item
                    for item in list(stream_chunk.subtitles or [])
                    if isinstance(item, dict)
                )

            chunk_pcm_audio = b"".join(
                segment for segment in chunk_pcm_segments if segment
            )
            if not chunk_pcm_audio:
                raise ValueError("No audio data received from Tencent TTS")
            chunk_mp3_audio = _export_tencent_pcm_to_mp3(
                chunk_pcm_audio,
                sample_rate=sample_rate,
            )
            if not chunk_mp3_audio:
                raise ValueError("No decodable audio data received from Tencent TTS")
            audio_segments.append(chunk_mp3_audio)

            duration_ms = _tencent_pcm_duration_ms(
                chunk_pcm_audio,
                sample_rate=sample_rate,
            )
            if duration_ms <= 0:
                duration_ms = (
                    try_get_audio_duration_ms(
                        chunk_mp3_audio,
                        format=TENCENT_DEFAULT_CODEC,
                    )
                    or 0
                )
            if duration_ms <= 0:
                duration_ms = self._subtitle_cues_end_ms(
                    normalize_tencent_subtitle_cues(
                        raw_subtitles,
                        source_text=chunk_text,
                    )
                )
            duration_ms = int(duration_ms or 0)
            duration_total_ms += duration_ms

            subtitle_cues.extend(
                normalize_tencent_subtitle_cues(
                    raw_subtitles,
                    offset_ms=subtitle_offset_ms,
                    source_text=chunk_text,
                )
            )
            subtitle_offset_ms += duration_ms

        output_format = TENCENT_DEFAULT_CODEC
        final_audio = _concat_tencent_audio_segments(
            audio_segments, output_format=output_format
        )
        if not final_audio:
            raise ValueError("No decodable audio data received from Tencent TTS")
        if duration_total_ms <= 0:
            decoded_duration_ms = try_get_audio_duration_ms(
                final_audio,
                format=output_format,
            )
            duration_total_ms = int(decoded_duration_ms or 0)

        return TTSResult(
            audio_data=final_audio,
            duration_ms=int(duration_total_ms or 0),
            sample_rate=int(effective_audio_settings.sample_rate or 16000),
            format=output_format,
            word_count=len(request_text),
            usage_characters=resolve_tts_billable_chars(request_text, 0),
            subtitle_cues=normalize_subtitle_cues(subtitle_cues),
        )

    @staticmethod
    def _subtitle_cues_end_ms(subtitle_cues: list[dict[str, Any]]) -> int:
        normalized = normalize_subtitle_cues(subtitle_cues)
        if not normalized:
            return 0
        return max(int(cue.get("end_ms", 0) or 0) for cue in normalized)
