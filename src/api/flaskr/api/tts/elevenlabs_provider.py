"""ElevenLabs text-to-speech provider."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
import uuid
from contextlib import contextmanager
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
from flaskr.common.config import get_config
from flaskr.common.log import AppLoggerProxy
from flaskr.service.tts.audio_utils import try_get_audio_duration_ms

logger = AppLoggerProxy(logging.getLogger(__name__))

ELEVENLABS_TTS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"
ELEVENLABS_DEFAULT_MODEL = "eleven_multilingual_v2"
ELEVENLABS_REQUEST_TIMEOUT = (10, 90)
ELEVENLABS_CONCURRENCY_LEASE_SECONDS = 120
ELEVENLABS_MODELS = [
    {
        "value": "eleven_v3_conversational",
        "label": "Eleven v3 Conversational",
    },
    {"value": "eleven_v3", "label": "Eleven v3"},
    {"value": "eleven_flash_v2_5", "label": "Eleven Flash v2.5"},
    {"value": "eleven_multilingual_v2", "label": "Eleven Multilingual v2"},
]
_ELEVENLABS_MODEL_IDS = {item["value"] for item in ELEVENLABS_MODELS}
_ERROR_DETAIL_LIMIT = 500
_LOCAL_CONCURRENCY_LOCK = threading.RLock()
_LOCAL_CONCURRENCY_SEMAPHORES: dict[str, threading.BoundedSemaphore] = {}

_LUA_ACQUIRE_CONCURRENCY_SLOT = """
local key = KEYS[1]
local holder = ARGV[1]
local max_count = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local lease_ms = tonumber(ARGV[4])
redis.call('zremrangebyscore', key, '-inf', now_ms)
if redis.call('zcard', key) < max_count then
    redis.call('zadd', key, now_ms + lease_ms, holder)
    redis.call('pexpire', key, lease_ms)
    return 1
end
return 0
"""

_LUA_RELEASE_CONCURRENCY_SLOT = """
redis.call('zrem', KEYS[1], ARGV[1])
return 1
"""


def parse_elevenlabs_voices(value: object) -> list[dict[str, str]]:
    """Parse and normalize the deployment-owned ElevenLabs voice whitelist."""
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            message = "ELEVENLABS_TTS_VOICES_JSON must be valid JSON"
            raise ValueError(message) from exc
    else:
        payload = value

    if payload in (None, ""):
        return []
    if not isinstance(payload, list):
        message = "ELEVENLABS_TTS_VOICES_JSON must be a JSON array"
        raise TypeError(message)

    voices: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            message = f"ElevenLabs voice at index {index} must be an object"
            raise TypeError(message)
        voice_id = str(item.get("value") or "").strip()
        label = str(item.get("label") or "").strip()
        if not voice_id or not label:
            message = (
                f"ElevenLabs voice at index {index} requires non-empty value and label"
            )
            raise ValueError(message)
        if voice_id in seen_ids:
            message = f"Duplicate ElevenLabs voice id: {voice_id}"
            raise ValueError(message)
        seen_ids.add(voice_id)
        voices.append({"value": voice_id, "label": label})
    return voices


def _load_elevenlabs_voices() -> list[dict[str, str]]:
    try:
        return parse_elevenlabs_voices(get_config("ELEVENLABS_TTS_VOICES_JSON"))
    except (TypeError, ValueError) as exc:
        logger.warning("Ignoring invalid ELEVENLABS_TTS_VOICES_JSON: %s", exc)
        return []


def _extract_safe_error_detail(response: Response, request_text: str) -> str:
    detail: Any = ""
    try:
        payload = response.json()
    except (TypeError, ValueError):
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or payload.get("error")
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("status") or ""
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


def _coerce_int_config(name: str, default: int) -> int:
    try:
        return int(get_config(name) or default)
    except (TypeError, ValueError):
        return default


def _coerce_float_config(name: str, default: float) -> float:
    try:
        return float(get_config(name) or default)
    except (TypeError, ValueError):
        return default


def _elevenlabs_concurrency_scope_key(api_key: str) -> str:
    key_hash = hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:24]
    return f"elevenlabs:{key_hash}"


def _get_redis_client() -> object:
    from flaskr.dao import get_redis_client

    redis_client = get_redis_client()
    if redis_client is None:
        message = "Redis is not configured"
        raise RuntimeError(message)
    return redis_client


def _acquire_redis_concurrency_slot(
    *,
    key: str,
    holder: str,
    max_count: int,
    deadline: float,
) -> bool:
    redis_client = _get_redis_client()
    lease_ms = int(ELEVENLABS_CONCURRENCY_LEASE_SECONDS * 1000)
    while True:
        now = time.time()
        acquired = redis_client.eval(
            _LUA_ACQUIRE_CONCURRENCY_SLOT,
            1,
            key,
            holder,
            str(max_count),
            str(int(now * 1000)),
            str(lease_ms),
        )
        if bool(acquired):
            return True
        if now >= deadline:
            return False
        time.sleep(min(0.2, max(deadline - now, 0.0)))


def _release_redis_concurrency_slot(*, key: str, holder: str) -> None:
    redis_client = _get_redis_client()
    redis_client.eval(_LUA_RELEASE_CONCURRENCY_SLOT, 1, key, holder)


def _get_local_concurrency_semaphore(
    key: str, max_count: int
) -> threading.BoundedSemaphore:
    with _LOCAL_CONCURRENCY_LOCK:
        semaphore = _LOCAL_CONCURRENCY_SEMAPHORES.get(key)
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(max_count)
            _LOCAL_CONCURRENCY_SEMAPHORES[key] = semaphore
        return semaphore


@contextmanager
def _elevenlabs_concurrency_slot(api_key: str) -> object:
    max_count = max(_coerce_int_config("ELEVENLABS_TTS_MAX_CONCURRENT_REQUESTS", 4), 0)
    if max_count <= 0:
        yield
        return

    max_wait_seconds = max(
        _coerce_float_config("ELEVENLABS_TTS_CONCURRENCY_MAX_WAIT_SECONDS", 45.0),
        0.0,
    )
    key = f"tts:concurrency:{_elevenlabs_concurrency_scope_key(api_key)}"
    holder = uuid.uuid4().hex
    deadline = time.time() + max_wait_seconds
    acquired_with_redis = False
    local_semaphore: threading.BoundedSemaphore | None = None

    try:
        acquired_with_redis = _acquire_redis_concurrency_slot(
            key=key,
            holder=holder,
            max_count=max_count,
            deadline=deadline,
        )
    except Exception as exc:
        logger.warning(
            "ElevenLabs concurrency Redis gate unavailable; using process-local gate: %s",
            exc,
        )
        local_semaphore = _get_local_concurrency_semaphore(key, max_count)
        acquired = local_semaphore.acquire(timeout=max_wait_seconds)
        if not acquired:
            message = "ElevenLabs TTS concurrency queue timed out"
            raise ValueError(message) from exc
    if not acquired_with_redis and local_semaphore is None:
        message = "ElevenLabs TTS concurrency queue timed out"
        raise ValueError(message)

    try:
        yield
    finally:
        if acquired_with_redis:
            try:
                _release_redis_concurrency_slot(key=key, holder=holder)
            except Exception:
                logger.warning("Failed to release ElevenLabs concurrency slot")
        if local_semaphore is not None:
            local_semaphore.release()


class ElevenLabsTTSProvider(BaseTTSProvider):
    """TTS provider using the ElevenLabs create-speech REST API."""

    @property
    def provider_name(self) -> str:
        """Return the provider's stable configuration name."""
        return "elevenlabs"

    def is_configured(self) -> bool:
        """Return whether both credentials and approved voices are configured."""
        api_key = str(get_config("ELEVENLABS_API_KEY") or "").strip()
        return bool(api_key and _load_elevenlabs_voices())

    def get_default_voice_settings(self) -> VoiceSettings:
        """Return a provider-level fallback using the first approved voice."""
        voices = _load_elevenlabs_voices()
        return VoiceSettings(
            voice_id=voices[0]["value"] if voices else "",
            speed=1.0,
            pitch=0,
            emotion="",
            volume=1.0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        """Return the fixed MP3 settings used by the shared audio pipeline."""
        return AudioSettings(
            format="mp3",
            sample_rate=44100,
            bitrate=128000,
            channel=1,
        )

    def get_supported_voices(self) -> list[dict[str, str]]:
        """Return only voices approved by deployment configuration."""
        return _load_elevenlabs_voices()

    def synthesize(
        self,
        text: str,
        voice_settings: VoiceSettings | None = None,
        audio_settings: AudioSettings | None = None,
        model: str | None = None,
    ) -> TTSResult:
        """Synthesize speech as an MP3 byte string."""
        del audio_settings  # ElevenLabs output is intentionally fixed for v1.

        if not text or not text.strip():
            message = "Text cannot be empty"
            raise ValueError(message)

        api_key = str(get_config("ELEVENLABS_API_KEY") or "").strip()
        if not api_key:
            message = "ELEVENLABS_API_KEY is not configured"
            raise ValueError(message)

        voices = self.get_supported_voices()
        if not voices:
            message = "ELEVENLABS_TTS_VOICES_JSON has no valid approved voices"
            raise ValueError(message)

        settings = voice_settings or self.get_default_voice_settings()
        voice_id = str(settings.voice_id or "").strip()
        approved_voice_ids = {voice["value"] for voice in voices}
        if voice_id not in approved_voice_ids:
            message = f"ElevenLabs voice is not approved: {voice_id or '<empty>'}"
            raise ValueError(message)

        model_id = str(model or "").strip() or ELEVENLABS_DEFAULT_MODEL
        if model_id not in _ELEVENLABS_MODEL_IDS:
            message = f"Unsupported ElevenLabs model: {model_id}"
            raise ValueError(message)

        try:
            speed = float(settings.speed)
        except (TypeError, ValueError) as exc:
            message = f"Invalid ElevenLabs speed: {settings.speed!r}"
            raise ValueError(message) from exc
        if not math.isfinite(speed):
            message = f"Invalid ElevenLabs speed: {settings.speed!r}"
            raise ValueError(message)
        if speed < 0.7 or speed > 1.2:
            message = f"ElevenLabs speed out of range: {speed} (expected 0.7-1.2)"
            raise ValueError(message)

        url = f"{ELEVENLABS_TTS_API_URL}/{quote(voice_id, safe='')}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {"speed": speed},
        }

        try:
            with _elevenlabs_concurrency_slot(api_key):
                response = requests.post(
                    url,
                    params={"output_format": ELEVENLABS_OUTPUT_FORMAT},
                    headers=headers,
                    json=payload,
                    timeout=ELEVENLABS_REQUEST_TIMEOUT,
                    allow_redirects=False,
                )
        except requests.RequestException as exc:
            logger.warning(
                "ElevenLabs TTS request failed: model=%s voice=%s text_len=%s error_type=%s",
                model_id,
                voice_id,
                len(text),
                type(exc).__name__,
            )
            message = f"ElevenLabs TTS request failed: {exc}"
            raise ValueError(message) from exc

        if response.status_code != 200:
            request_id = _extract_request_id(response)
            detail = _extract_safe_error_detail(response, text)
            logger.error(
                "ElevenLabs TTS HTTP error: status=%s request_id=%s model=%s voice=%s text_len=%s detail=%s",
                response.status_code,
                request_id or "-",
                model_id,
                voice_id,
                len(text),
                detail or "-",
            )
            if response.status_code == 429:
                message = "ElevenLabs TTS HTTP 429 rate limit"
            else:
                message = f"ElevenLabs TTS HTTP {response.status_code}"
            if detail:
                message = f"{message}: {detail}"
            raise ValueError(message)

        audio_data = bytes(response.content or b"")
        if not audio_data:
            message = "No audio data received from ElevenLabs TTS"
            raise ValueError(message)

        duration_ms = try_get_audio_duration_ms(audio_data, audio_format="mp3") or 0
        logger.info(
            "ElevenLabs TTS synthesis completed: model=%s voice=%s duration_ms=%s size=%s text_len=%s",
            model_id,
            voice_id,
            duration_ms,
            len(audio_data),
            len(text),
        )
        return TTSResult(
            audio_data=audio_data,
            duration_ms=duration_ms,
            sample_rate=44100,
            format="mp3",
            word_count=len(text),
            usage_characters=len(text),
        )

    def get_provider_config(self) -> ProviderConfig:
        """Return ElevenLabs settings consumed by the generic editor UI."""
        return ProviderConfig(
            name="elevenlabs",
            label="ElevenLabs",
            speed=ParamRange(min=0.7, max=1.2, step=0.1, default=1.0),
            pitch=ParamRange(min=0, max=0, step=1, default=0),
            supports_emotion=False,
            models=ELEVENLABS_MODELS,
            voices=self.get_supported_voices(),
            emotions=[],
            supports_custom_voice_id=False,
            supports_voice_cloning=False,
        )
