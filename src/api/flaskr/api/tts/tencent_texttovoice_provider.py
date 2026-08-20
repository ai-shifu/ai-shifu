"""Tencent Cloud TextToVoice TTS Provider.

Calls the standard Tencent Cloud TTS API (tts.tencentcloudapi.com,
Action=TextToVoice) with TC3-HMAC-SHA256 signing. This is a different
service from the TRTC conversational SSE API wrapped by
``tencent_provider.py`` (trtc.ai.tencentcloudapi.com).

Model tiers exposed by this provider (display names come from
TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON; note the mapping is easy to mix up):

    internal model  | voice types      | sample rate | UI display name (zh-CN)
    --------------- | ---------------- | ----------- | -----------------------
    premium         | 101xxx (精品音色) | 16000       | 基础语音
    large-model     | 501xxx/601xxx    | 24000       | 标准语音
                      (大模型音色)

Credentials: TENCENT_TTS_SECRET_ID / TENCENT_TTS_SECRET_KEY (shared with the
TRTC provider; no AppId is required for TextToVoice).
"""

import base64
import datetime as dt
import hashlib
import hmac
import json
import logging
import time
import uuid

import requests

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

logger = AppLoggerProxy(logging.getLogger(__name__))

TENCENT_TEXTTOVOICE_HOST = "tts.tencentcloudapi.com"
TENCENT_TEXTTOVOICE_ENDPOINT = f"https://{TENCENT_TEXTTOVOICE_HOST}"
TENCENT_TEXTTOVOICE_SERVICE = "tts"
TENCENT_TEXTTOVOICE_ACTION = "TextToVoice"
TENCENT_TEXTTOVOICE_VERSION = "2019-08-23"
TENCENT_TEXTTOVOICE_REGION = "ap-guangzhou"
TENCENT_TEXTTOVOICE_ALGORITHM = "TC3-HMAC-SHA256"

TENCENT_TEXTTOVOICE_PREMIUM_MODEL = "premium"
TENCENT_TEXTTOVOICE_LARGE_MODEL = "large-model"
TENCENT_TEXTTOVOICE_DEFAULT_MODEL = TENCENT_TEXTTOVOICE_PREMIUM_MODEL
TENCENT_TEXTTOVOICE_DEFAULT_VOICE_ID = "101001"

TENCENT_TEXTTOVOICE_MODELS = [
    {"value": TENCENT_TEXTTOVOICE_PREMIUM_MODEL, "label": "精品音色 (16k)"},
    {"value": TENCENT_TEXTTOVOICE_LARGE_MODEL, "label": "大模型音色 (24k)"},
]

_PREMIUM_SAMPLE_RATE = 16000
_LARGE_MODEL_SAMPLE_RATE = 24000

# TextToVoice single-request limit is 150 Chinese chars / 500 English letters.
# Weighted budget: CJK/full-width chars cost 1, others cost 0.3 (150/500);
# cap at 140 to keep a safety margin below the documented limit.
_SEGMENT_WEIGHT_LIMIT = 140.0
_NON_CJK_CHAR_WEIGHT = 0.3
_TERMINAL_PUNCTUATION = "。！？!?；;\n"


def _texttovoice_voice(
    value: str, label: str, model: str, language: str = "zh"
) -> dict[str, str]:
    tier_label = {
        TENCENT_TEXTTOVOICE_PREMIUM_MODEL: "精品",
        TENCENT_TEXTTOVOICE_LARGE_MODEL: "大模型",
    }.get(model, model)
    language_label = {
        "zh": "中文",
        "en": "英文",
        "yue": "粤语",
    }.get(language, language)
    return {
        "value": value,
        "label": f"{label} ({language_label}, {tier_label})",
        "language": language,
        "resource_id": model,
    }


def _premium(value: str, label: str, language: str = "zh") -> dict[str, str]:
    return _texttovoice_voice(value, label, TENCENT_TEXTTOVOICE_PREMIUM_MODEL, language)


def _large_model(value: str, label: str, language: str = "zh") -> dict[str, str]:
    return _texttovoice_voice(value, label, TENCENT_TEXTTOVOICE_LARGE_MODEL, language)


TENCENT_TEXTTOVOICE_VOICES = [
    # Premium voices (VoiceType 101xxx, 16k)
    _premium("101001", "智瑜·情感女声"),
    _premium("101004", "智云·通用男声"),
    _premium("101011", "智燕·新闻女声"),
    _premium("101013", "智辉·新闻男声"),
    _premium("101015", "智萌·男童声"),
    _premium("101016", "智甜·女童声"),
    _premium("101019", "智彤·粤语女声", "yue"),
    _premium("101021", "智瑞·新闻男声"),
    _premium("101026", "智希·甜美女声"),
    _premium("101027", "智梅·通用女声"),
    _premium("101030", "智柯·通用男声"),
    _premium("101050", "WeJack·英文男声", "en"),
    _premium("101054", "智友·通用男声"),
    _premium("101055", "智付·通用女声"),
    # Large-model voices (VoiceType 501xxx/601xxx, 24k)
    _large_model("501000", "智斌·阅读男声"),
    _large_model("501001", "智兰·资讯女声"),
    _large_model("501002", "智菊·阅读女声"),
    _large_model("501003", "智宇·阅读男声"),
    _large_model("501004", "月华·聊天女声"),
    _large_model("501005", "飞镜·聊天男声"),
    _large_model("501006", "千嶂·聊天男声"),
    _large_model("501007", "浅草·聊天男声"),
    _large_model("501008", "WeJames·英文男声", "en"),
    _large_model("501009", "WeWinny·英文女声", "en"),
    _large_model("601008", "爱小豪·聊天男声"),
    _large_model("601009", "爱小芊·聊天女声"),
    _large_model("601010", "爱小娇·聊天女声"),
    _large_model("601011", "爱小川·聊天男声"),
    _large_model("601012", "爱小璟·特色女声"),
    _large_model("601013", "爱小伊·阅读女声"),
    _large_model("601014", "爱小简·聊天男声"),
]

_VOICE_MODEL_BY_ID = {
    voice["value"]: voice["resource_id"] for voice in TENCENT_TEXTTOVOICE_VOICES
}


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tc3_sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def build_texttovoice_tc3_headers(
    *,
    payload_json: str,
    secret_id: str,
    secret_key: str,
    timestamp: int | None = None,
) -> dict[str, str]:
    request_timestamp = int(timestamp if timestamp is not None else time.time())
    request_date = dt.datetime.fromtimestamp(
        request_timestamp,
        tz=dt.UTC,
    ).strftime("%Y-%m-%d")
    canonical_headers = (
        "content-type:application/json\n"
        f"host:{TENCENT_TEXTTOVOICE_HOST}\n"
        f"x-tc-action:{TENCENT_TEXTTOVOICE_ACTION.lower()}\n"
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
    credential_scope = f"{request_date}/{TENCENT_TEXTTOVOICE_SERVICE}/tc3_request"
    string_to_sign = "\n".join(
        [
            TENCENT_TEXTTOVOICE_ALGORITHM,
            str(request_timestamp),
            credential_scope,
            _sha256_hex(canonical_request),
        ]
    )
    secret_date = _tc3_sign(
        ("TC3" + str(secret_key or "")).encode("utf-8"), request_date
    )
    secret_service = _tc3_sign(secret_date, TENCENT_TEXTTOVOICE_SERVICE)
    secret_signing = _tc3_sign(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"{TENCENT_TEXTTOVOICE_ALGORITHM} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": "application/json",
        "Host": TENCENT_TEXTTOVOICE_HOST,
        "X-TC-Action": TENCENT_TEXTTOVOICE_ACTION,
        "X-TC-Version": TENCENT_TEXTTOVOICE_VERSION,
        "X-TC-Region": TENCENT_TEXTTOVOICE_REGION,
        "X-TC-Timestamp": str(request_timestamp),
    }


def _resolve_sample_rate(voice_id: str, model: str | None) -> int:
    voice_model = _VOICE_MODEL_BY_ID.get(str(voice_id or "").strip())
    effective_model = voice_model or (model or "").strip()
    if effective_model == TENCENT_TEXTTOVOICE_LARGE_MODEL:
        return _LARGE_MODEL_SAMPLE_RATE
    return _PREMIUM_SAMPLE_RATE


def _char_weight(char: str) -> float:
    return 1.0 if ord(char) >= 0x2E80 else _NON_CJK_CHAR_WEIGHT


def _text_weight(text: str) -> float:
    return sum(_char_weight(char) for char in text)


def _hard_split(text: str) -> list[str]:
    pieces: list[str] = []
    current = ""
    current_weight = 0.0
    for char in text:
        weight = _char_weight(char)
        if current and current_weight + weight > _SEGMENT_WEIGHT_LIMIT:
            pieces.append(current)
            current = ""
            current_weight = 0.0
        current += char
        current_weight += weight
    if current:
        pieces.append(current)
    return pieces


def _split_text(text: str) -> list[str]:
    """Split text into segments within the TextToVoice request limit."""
    normalized = str(text or "").strip()
    if not normalized:
        return []

    sentences: list[str] = []
    current = ""
    for char in normalized:
        current += char
        if char in _TERMINAL_PUNCTUATION:
            sentences.append(current)
            current = ""
    if current:
        sentences.append(current)

    segments: list[str] = []
    buffer = ""
    buffer_weight = 0.0
    for sentence in sentences:
        sentence_weight = _text_weight(sentence)
        if sentence_weight > _SEGMENT_WEIGHT_LIMIT:
            if buffer.strip():
                segments.append(buffer)
            buffer = ""
            buffer_weight = 0.0
            segments.extend(_hard_split(sentence))
            continue
        if buffer and buffer_weight + sentence_weight > _SEGMENT_WEIGHT_LIMIT:
            segments.append(buffer)
            buffer = ""
            buffer_weight = 0.0
        buffer += sentence
        buffer_weight += sentence_weight
    if buffer.strip():
        segments.append(buffer)

    return [segment for segment in segments if segment.strip()]


class TencentTextToVoiceProvider(BaseTTSProvider):
    """TTS provider using the Tencent Cloud TextToVoice API."""

    @property
    def provider_name(self) -> str:
        return "tencent_texttovoice"

    def _get_credentials(self) -> tuple:
        secret_id = (get_config("TENCENT_TTS_SECRET_ID") or "").strip()
        secret_key = (get_config("TENCENT_TTS_SECRET_KEY") or "").strip()
        return secret_id, secret_key

    def is_configured(self) -> bool:
        secret_id, secret_key = self._get_credentials()
        return bool(secret_id and secret_key)

    def get_default_voice_settings(self) -> VoiceSettings:
        return VoiceSettings(
            voice_id=TENCENT_TEXTTOVOICE_DEFAULT_VOICE_ID,
            speed=0,  # Tencent native range -2..6, 0 is normal speed
            pitch=0,
            emotion="",
            volume=0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        return AudioSettings(
            format="mp3",
            sample_rate=_PREMIUM_SAMPLE_RATE,
            bitrate=128000,
            channel=1,
        )

    def get_supported_voices(self) -> list[dict[str, str]]:
        return [dict(voice) for voice in TENCENT_TEXTTOVOICE_VOICES]

    def _synthesize_segment(
        self,
        text: str,
        voice_type: int,
        speed: float,
        sample_rate: int,
    ) -> bytes:
        payload = {
            "Text": text,
            "SessionId": str(uuid.uuid4()),
            "VoiceType": voice_type,
            "Codec": "mp3",
            "SampleRate": sample_rate,
            "ModelType": 1,
            "Speed": speed,
        }
        payload_json = json.dumps(payload, ensure_ascii=False)
        secret_id, secret_key = self._get_credentials()
        headers = build_texttovoice_tc3_headers(
            payload_json=payload_json,
            secret_id=secret_id,
            secret_key=secret_key,
        )
        try:
            response = requests.post(
                TENCENT_TEXTTOVOICE_ENDPOINT,
                data=payload_json.encode("utf-8"),
                headers=headers,
                timeout=60,
            )
            body = response.json()
        except requests.RequestException as exc:
            logger.exception("Tencent TextToVoice request failed")
            message = f"Tencent TextToVoice request failed: {exc}"
            raise ValueError(message) from exc
        except ValueError as exc:
            message = f"Tencent TextToVoice returned invalid JSON: {exc}"
            raise ValueError(message) from exc

        result = body.get("Response") or {}
        error = result.get("Error")
        if error:
            request_id = result.get("RequestId", "")
            message = (
                f"Tencent TextToVoice error {error.get('Code', 'unknown')}: "
                f"{error.get('Message', '')} (request_id={request_id})"
            )
            raise ValueError(message)
        audio_base64 = result.get("Audio") or ""
        if not audio_base64:
            error_message = "No audio data received from Tencent TextToVoice"
            raise ValueError(error_message)
        return base64.b64decode(audio_base64)

    def synthesize(
        self,
        text: str,
        voice_settings: VoiceSettings | None = None,
        audio_settings: AudioSettings | None = None,
        model: str | None = None,
    ) -> TTSResult:
        if not text or not text.strip():
            error_message = "Text cannot be empty"
            raise ValueError(error_message)
        if not self.is_configured():
            error_message = (
                "Tencent TextToVoice is not configured. "
                "Set TENCENT_TTS_SECRET_ID and TENCENT_TTS_SECRET_KEY"
            )
            raise ValueError(error_message)

        if not voice_settings:
            voice_settings = self.get_default_voice_settings()
        voice_id = (voice_settings.voice_id or "").strip() or (
            TENCENT_TEXTTOVOICE_DEFAULT_VOICE_ID
        )
        try:
            voice_type = int(voice_id)
        except (TypeError, ValueError) as exc:
            message = f"Invalid Tencent TextToVoice voice id: {voice_id}"
            raise ValueError(message) from exc

        sample_rate = _resolve_sample_rate(voice_id, model)
        speed = float(voice_settings.speed or 0)

        segments = _split_text(text)
        if not segments:
            error_message = "Text cannot be empty"
            raise ValueError(error_message)

        logger.debug(
            "Calling Tencent TextToVoice: voice_type=%s, sample_rate=%s, "
            "segments=%s, text_len=%s",
            voice_type,
            sample_rate,
            len(segments),
            len(text),
        )

        audio_segments = [
            self._synthesize_segment(segment, voice_type, speed, sample_rate)
            for segment in segments
        ]
        audio_data = concat_audio_best_effort(audio_segments, output_format="mp3")
        if not audio_data:
            error_message = "No audio data received from Tencent TextToVoice"
            raise ValueError(error_message)
        duration_ms = try_get_audio_duration_ms(audio_data, audio_format="mp3") or 0

        return TTSResult(
            audio_data=audio_data,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            format="mp3",
            word_count=len(text),
            usage_characters=resolve_tts_billable_chars(text, 0),
            subtitle_cues=[],
        )

    def get_provider_config(self) -> ProviderConfig:
        return ProviderConfig(
            name=self.provider_name,
            label="腾讯云语音合成",
            speed=ParamRange(min=-2, max=6, step=0.1, default=0),
            pitch=ParamRange(min=0, max=0, step=1, default=0),
            supports_emotion=False,
            models=[dict(model) for model in TENCENT_TEXTTOVOICE_MODELS],
            voices=self.get_supported_voices(),
            emotions=[],
        )
