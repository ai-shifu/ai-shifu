"""Google Gemini text-to-speech provider.

Synthesis goes through the Gemini Developer API ``generateContent`` endpoint
with ``responseModalities=["AUDIO"]``. Gemini only returns raw 16-bit PCM, so
the provider transcodes every response to MP3 before handing it to the shared
streaming, storage, and playback paths, which all assume MP3.
"""

from __future__ import annotations

import base64
import binascii
import logging
import math
import re
from typing import Any
from urllib.parse import quote

import requests
from requests import Response

from flaskr.api.tts.base import (
    AudioSettings,
    BaseTTSProvider,
    ParamRange,
    ProviderConfig,
    TTSResult,
    VoiceSettings,
)
from flaskr.api.tts.voice_config import parse_voice_list_json
from flaskr.common.config import get_config
from flaskr.common.log import AppLoggerProxy
from flaskr.service.tts.audio_utils import export_pcm_to_mp3, pcm_duration_ms

logger = AppLoggerProxy(logging.getLogger(__name__))

GEMINI_TTS_DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_TTS_REQUEST_TIMEOUT = (10, 90)
# The TTS models accept 8k input tokens; CJK text runs at roughly one token
# per character, so this cap stays far inside the limit while still catching
# misuse. Callers normally send sentence-sized segments (TTS_MAX_SEGMENT_CHARS).
GEMINI_TTS_MAX_INPUT_CHARS = 4000
GEMINI_TTS_DEFAULT_SAMPLE_RATE = 24000
GEMINI_TTS_DEFAULT_VOICE = "Kore"
GEMINI_TTS_DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_TTS_MODELS = [
    {"value": "gemini-3.1-flash-tts-preview", "label": "Gemini 3.1 Flash TTS"},
    {"value": "gemini-2.5-flash-preview-tts", "label": "Gemini 2.5 Flash TTS"},
    {"value": "gemini-2.5-pro-preview-tts", "label": "Gemini 2.5 Pro TTS"},
]
_GEMINI_TTS_MODEL_IDS = {item["value"] for item in GEMINI_TTS_MODELS}
# Prebuilt voices published by Google, with the official character adjectives.
GEMINI_TTS_VOICES = [
    {"value": "Zephyr", "label": "Zephyr (Bright)"},
    {"value": "Puck", "label": "Puck (Upbeat)"},
    {"value": "Charon", "label": "Charon (Informative)"},
    {"value": "Kore", "label": "Kore (Firm)"},
    {"value": "Fenrir", "label": "Fenrir (Excitable)"},
    {"value": "Leda", "label": "Leda (Youthful)"},
    {"value": "Orus", "label": "Orus (Firm)"},
    {"value": "Aoede", "label": "Aoede (Breezy)"},
    {"value": "Callirrhoe", "label": "Callirrhoe (Easy-going)"},
    {"value": "Autonoe", "label": "Autonoe (Bright)"},
    {"value": "Enceladus", "label": "Enceladus (Breathy)"},
    {"value": "Iapetus", "label": "Iapetus (Clear)"},
    {"value": "Umbriel", "label": "Umbriel (Easy-going)"},
    {"value": "Algieba", "label": "Algieba (Smooth)"},
    {"value": "Despina", "label": "Despina (Smooth)"},
    {"value": "Erinome", "label": "Erinome (Clear)"},
    {"value": "Algenib", "label": "Algenib (Gravelly)"},
    {"value": "Rasalgethi", "label": "Rasalgethi (Informative)"},
    {"value": "Laomedeia", "label": "Laomedeia (Upbeat)"},
    {"value": "Achernar", "label": "Achernar (Soft)"},
    {"value": "Alnilam", "label": "Alnilam (Firm)"},
    {"value": "Schedar", "label": "Schedar (Even)"},
    {"value": "Gacrux", "label": "Gacrux (Mature)"},
    {"value": "Pulcherrima", "label": "Pulcherrima (Forward)"},
    {"value": "Achird", "label": "Achird (Friendly)"},
    {"value": "Zubenelgenubi", "label": "Zubenelgenubi (Casual)"},
    {"value": "Vindemiatrix", "label": "Vindemiatrix (Gentle)"},
    {"value": "Sadachbia", "label": "Sadachbia (Lively)"},
    {"value": "Sadaltager", "label": "Sadaltager (Knowledgeable)"},
    {"value": "Sulafat", "label": "Sulafat (Warm)"},
]
_GEMINI_TTS_VOICE_IDS = {item["value"] for item in GEMINI_TTS_VOICES}
_BLOCKING_FINISH_REASONS = frozenset(
    {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
)
_EMPTY_AUDIO_MESSAGE = "No audio data received from Gemini TTS"
_ERROR_DETAIL_LIMIT = 500
_PCM_RATE_PATTERN = re.compile(r"rate=(\d+)")
_HTTP_OK = 200
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVICE_UNAVAILABLE = 503


def _load_gemini_voices() -> list[dict[str, str]]:
    """Return the selectable voices, narrowed by the optional deployment allowlist."""
    raw = get_config("GEMINI_TTS_VOICES_JSON")
    if raw in (None, "") or (isinstance(raw, str) and not raw.strip()):
        return [dict(item) for item in GEMINI_TTS_VOICES]

    try:
        configured = parse_voice_list_json(raw, env_name="GEMINI_TTS_VOICES_JSON")
    except (TypeError, ValueError) as exc:
        logger.warning(
            "Ignoring invalid GEMINI_TTS_VOICES_JSON, using built-in voices: %s",
            exc,
        )
        return [dict(item) for item in GEMINI_TTS_VOICES]

    voices: list[dict[str, str]] = []
    for item in configured:
        if item["value"] not in _GEMINI_TTS_VOICE_IDS:
            logger.warning(
                "Ignoring unknown Gemini TTS voice in GEMINI_TTS_VOICES_JSON: %s",
                item["value"],
            )
            continue
        voices.append(item)
    if not voices:
        logger.warning(
            "GEMINI_TTS_VOICES_JSON has no built-in voices, using built-in voices"
        )
        return [dict(item) for item in GEMINI_TTS_VOICES]
    return voices


def _resolve_api_base_url() -> str:
    configured = str(get_config("GEMINI_TTS_API_URL") or "").strip()
    return (configured or GEMINI_TTS_DEFAULT_API_URL).rstrip("/")


def _parse_audio_mime_type(mime_type: str) -> tuple[bool, int]:
    """Return ``(is_pcm, sample_rate)`` for a Gemini inline audio mime type.

    Gemini reports raw audio as ``audio/L16;codec=pcm;rate=24000``. The rate is
    read from the mime parameters so a future default change does not desync
    the transcoder.
    """
    normalized = str(mime_type or "").strip().lower()
    is_pcm = normalized.startswith("audio/l16") or "pcm" in normalized
    match = _PCM_RATE_PATTERN.search(normalized)
    sample_rate = GEMINI_TTS_DEFAULT_SAMPLE_RATE
    if match:
        try:
            sample_rate = int(match.group(1)) or GEMINI_TTS_DEFAULT_SAMPLE_RATE
        except ValueError:
            sample_rate = GEMINI_TTS_DEFAULT_SAMPLE_RATE
    return is_pcm, sample_rate


def _extract_safe_error_detail(response: Response, request_text: str) -> str:
    detail: Any = ""
    try:
        payload = response.json()
    except (TypeError, ValueError):
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            detail = error.get("message") or error.get("status") or ""
        else:
            detail = payload.get("message") or error or ""
    if not detail:
        detail = getattr(response, "reason", "") or ""
    safe_detail = str(detail).strip()
    if request_text:
        safe_detail = safe_detail.replace(request_text, "[redacted]")
    return safe_detail[:_ERROR_DETAIL_LIMIT]


def _extract_request_id(response: Response) -> str:
    for key, value in (response.headers or {}).items():
        if key.lower() in {"request-id", "x-request-id"}:
            return str(value or "").strip()
    return ""


def _find_inline_audio(candidate: dict[str, Any]) -> tuple[str, str]:
    """Return ``(base64_audio, mime_type)`` from the first inline audio part."""
    content = candidate.get("content")
    if not isinstance(content, dict):
        return "", ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return "", ""
    for part in parts:
        if not isinstance(part, dict):
            continue
        inline = part.get("inlineData")
        if not isinstance(inline, dict):
            inline = part.get("inline_data")
        if not isinstance(inline, dict):
            continue
        data = str(inline.get("data") or "").strip()
        mime_type = str(inline.get("mimeType") or inline.get("mime_type") or "")
        if data:
            return data, mime_type
    return "", ""


def _coerce_finite_float(value: object, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        message = f"Invalid Gemini TTS {field_name}: {value!r}"
        raise ValueError(message) from exc
    if not math.isfinite(number):
        message = f"Invalid Gemini TTS {field_name}: {value!r}"
        raise ValueError(message)
    return number


class GeminiTTSProvider(BaseTTSProvider):
    """TTS provider using the Gemini Developer API generateContent endpoint."""

    @property
    def provider_name(self) -> str:
        """Return the provider's stable configuration name."""
        return "gemini"

    def is_configured(self) -> bool:
        """Return whether the provider is switched on and has an API key."""
        if not get_config("GEMINI_TTS_ENABLED"):
            return False
        return bool(str(get_config("GEMINI_API_KEY") or "").strip())

    def get_default_voice_settings(self) -> VoiceSettings:
        """Return a provider-level fallback using the first selectable voice."""
        voices = _load_gemini_voices()
        return VoiceSettings(
            voice_id=voices[0]["value"] if voices else GEMINI_TTS_DEFAULT_VOICE,
            speed=1.0,
            pitch=0,
            emotion="",
            volume=1.0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        """Return the MP3 settings produced after transcoding Gemini PCM."""
        return AudioSettings(
            format="mp3",
            sample_rate=GEMINI_TTS_DEFAULT_SAMPLE_RATE,
            bitrate=128000,
            channel=1,
        )

    def get_supported_voices(self) -> list[dict[str, str]]:
        """Return the built-in voices, narrowed by deployment configuration."""
        return _load_gemini_voices()

    def _build_prompt_text(self, text: str, emotion: str) -> str:
        # Gemini steers delivery through natural-language instructions in the
        # text itself. Emotion is not exposed in v1, so the text is sent as-is;
        # this hook is where a style prefix would be added later.
        del emotion
        return text

    def synthesize(
        self,
        text: str,
        voice_settings: VoiceSettings | None = None,
        audio_settings: AudioSettings | None = None,
        model: str | None = None,
    ) -> TTSResult:
        """Synthesize speech through generateContent and return MP3 bytes."""
        del audio_settings  # Output is fixed to MP3 for the shared audio pipeline.

        if not text or not text.strip():
            message = "Text cannot be empty"
            raise ValueError(message)
        if len(text) > GEMINI_TTS_MAX_INPUT_CHARS:
            message = (
                f"Text exceeds Gemini TTS limit: {len(text)} > "
                f"{GEMINI_TTS_MAX_INPUT_CHARS} characters"
            )
            raise ValueError(message)
        if not get_config("GEMINI_TTS_ENABLED"):
            message = "GEMINI_TTS_ENABLED is not set"
            raise ValueError(message)
        api_key = str(get_config("GEMINI_API_KEY") or "").strip()
        if not api_key:
            message = "GEMINI_API_KEY is not configured"
            raise ValueError(message)

        settings = voice_settings or self.get_default_voice_settings()
        voice_id = str(settings.voice_id or "").strip() or GEMINI_TTS_DEFAULT_VOICE
        approved_voice_ids = {voice["value"] for voice in self.get_supported_voices()}
        if voice_id not in approved_voice_ids:
            message = f"Gemini TTS voice is not approved: {voice_id}"
            raise ValueError(message)

        model_id = str(model or "").strip() or GEMINI_TTS_DEFAULT_MODEL
        if model_id not in _GEMINI_TTS_MODEL_IDS:
            message = f"Unsupported Gemini TTS model: {model_id}"
            raise ValueError(message)

        speed = _coerce_finite_float(settings.speed, "speed")
        if not math.isclose(speed, 1.0, abs_tol=1e-9):
            message = f"Gemini TTS speed is fixed at 1.0: {speed}"
            raise ValueError(message)
        pitch = int(_coerce_finite_float(settings.pitch or 0, "pitch"))
        if pitch != 0:
            message = f"Gemini TTS pitch is fixed at 0: {pitch}"
            raise ValueError(message)

        url = f"{_resolve_api_base_url()}/models/{quote(model_id, safe='')}:generateContent"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "contents": [
                {"parts": [{"text": self._build_prompt_text(text, settings.emotion)}]}
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_id}}
                },
            },
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=GEMINI_TTS_REQUEST_TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Gemini TTS request failed: model=%s voice=%s text_len=%s error_type=%s",
                model_id,
                voice_id,
                len(text),
                type(exc).__name__,
            )
            message = f"Gemini TTS request failed: {exc}"
            raise ValueError(message) from exc

        if response.status_code != _HTTP_OK:
            request_id = _extract_request_id(response)
            detail = _extract_safe_error_detail(response, text)
            logger.error(
                "Gemini TTS HTTP error: status=%s request_id=%s model=%s voice=%s text_len=%s detail=%s",
                response.status_code,
                request_id or "-",
                model_id,
                voice_id,
                len(text),
                detail or "-",
            )
            if response.status_code == _HTTP_TOO_MANY_REQUESTS:
                message = "Gemini TTS HTTP 429 rate limit"
            elif response.status_code == _HTTP_SERVICE_UNAVAILABLE:
                # Preview models answer overload with 503 UNAVAILABLE. The
                # shared streaming retry keys off the "rate limit" marker, so
                # overload is reported the same way as quota exhaustion.
                message = "Gemini TTS HTTP 503 overloaded (rate limit)"
            else:
                message = f"Gemini TTS HTTP {response.status_code}"
            if detail:
                message = f"{message}: {detail}"
            raise ValueError(message)

        try:
            body = response.json()
        except (TypeError, ValueError) as exc:
            message = "Gemini TTS returned a non-JSON response"
            raise ValueError(message) from exc
        if not isinstance(body, dict):
            message = "Gemini TTS returned an unexpected response payload"
            raise TypeError(message)

        prompt_feedback = body.get("promptFeedback")
        block_reason = ""
        if isinstance(prompt_feedback, dict):
            block_reason = str(prompt_feedback.get("blockReason") or "").strip()
        if block_reason:
            message = f"Gemini TTS request blocked: {block_reason}"
            raise ValueError(message)

        candidates = body.get("candidates") or []
        candidate: dict[str, Any] = {}
        if (
            isinstance(candidates, list)
            and candidates
            and isinstance(candidates[0], dict)
        ):
            candidate = candidates[0]
        finish_reason = str(candidate.get("finishReason") or "").strip().upper()
        if finish_reason in _BLOCKING_FINISH_REASONS:
            message = f"Gemini TTS content blocked: {finish_reason}"
            raise ValueError(message)

        encoded_audio, mime_type = _find_inline_audio(candidate)
        if not encoded_audio:
            raise ValueError(_EMPTY_AUDIO_MESSAGE)
        try:
            pcm_audio = base64.b64decode(encoded_audio, validate=False)
        except (binascii.Error, ValueError) as exc:
            message = "Gemini TTS returned undecodable audio payload"
            raise ValueError(message) from exc
        if not pcm_audio:
            raise ValueError(_EMPTY_AUDIO_MESSAGE)

        is_pcm, sample_rate = _parse_audio_mime_type(mime_type)
        if not is_pcm:
            message = (
                f"Unsupported Gemini TTS audio mime type: {mime_type or '<empty>'}"
            )
            raise ValueError(message)

        mp3_audio = export_pcm_to_mp3(pcm_audio, sample_rate=sample_rate)
        if not mp3_audio:
            message = "No decodable audio data received from Gemini TTS"
            raise ValueError(message)
        duration_ms = pcm_duration_ms(pcm_audio, sample_rate=sample_rate)

        usage = body.get("usageMetadata")
        audio_tokens = (
            usage.get("candidatesTokenCount") if isinstance(usage, dict) else None
        )
        logger.info(
            "Gemini TTS synthesis completed: model=%s voice=%s duration_ms=%s pcm_bytes=%s mp3_bytes=%s text_len=%s audio_tokens=%s finish_reason=%s",
            model_id,
            voice_id,
            duration_ms,
            len(pcm_audio),
            len(mp3_audio),
            len(text),
            audio_tokens if audio_tokens is not None else "-",
            finish_reason or "-",
        )
        return TTSResult(
            audio_data=mp3_audio,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            format="mp3",
            word_count=len(text),
            usage_characters=len(text),
        )

    def get_provider_config(self) -> ProviderConfig:
        """Return Gemini settings consumed by the generic editor UI."""
        return ProviderConfig(
            name="gemini",
            label="Gemini",
            speed=ParamRange(min=1.0, max=1.0, step=0.1, default=1.0),
            pitch=ParamRange(min=0, max=0, step=1, default=0),
            supports_emotion=False,
            models=GEMINI_TTS_MODELS,
            voices=self.get_supported_voices(),
            emotions=[],
            supports_custom_voice_id=False,
            supports_voice_cloning=False,
        )
