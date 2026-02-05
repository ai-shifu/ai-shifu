"""
Volcengine HTTP TTS Provider.

This module provides TTS synthesis using Volcengine's HTTP v1/tts API
(ByteDance TTS). See docs/bytedance-tts-api.md for request/response format.
"""

from __future__ import annotations

import base64
import logging
import uuid
from typing import Optional, List

import requests

from flaskr.common.config import get_config
from flaskr.api.tts.base import (
    BaseTTSProvider,
    TTSResult,
    VoiceSettings,
    AudioSettings,
    ProviderConfig,
    ParamRange,
)


logger = logging.getLogger(__name__)

VOLCENGINE_HTTP_TTS_URL = "https://openspeech.bytedance.com/api/v1/tts"

VOLCENGINE_HTTP_ENCODING_MAP = {
    "mp3": "mp3",
    "pcm": "pcm",
    "wav": "wav",
    "ogg_opus": "ogg_opus",
}

VOLCENGINE_HTTP_SAMPLE_RATES = {8000, 16000, 24000}
VOLCENGINE_HTTP_DEFAULT_CLUSTER = "volcano_tts"

VOLCENGINE_HTTP_MODELS = [
    {"value": VOLCENGINE_HTTP_DEFAULT_CLUSTER, "label": "volcano_tts"},
]

VOLCENGINE_HTTP_VOICES = [
    {"value": "BV700_V2_streaming", "label": "Can Can 2.0"},
    {"value": "BV705_streaming", "label": "Yang Yang"},
    {"value": "BV701_V2_streaming", "label": "Qing Cang 2.0"},
    {"value": "BV001_V2_streaming", "label": "General Female 2.0"},
    {"value": "BV700_streaming", "label": "Can Can"},
    {"value": "BV701_streaming", "label": "Qing Cang"},
    {"value": "BV001_streaming", "label": "General Female"},
    {"value": "BV002_streaming", "label": "General Male"},
    {"value": "BV406_streaming", "label": "Zi Zi"},
    {"value": "BV123_streaming", "label": "Sunny Youth"},
    {"value": "BV120_streaming", "label": "Anti-involution Youth"},
    {"value": "BV119_streaming", "label": "General Son-in-law"},
    {"value": "BV115_streaming", "label": "Ancient Style Young Master"},
    {"value": "BV107_streaming", "label": "Domineering Uncle"},
    {"value": "BV100_streaming", "label": "Simple Youth"},
    {"value": "BV104_streaming", "label": "Gentle Lady"},
    {"value": "BV004_streaming", "label": "Cheerful Youth"},
    {"value": "BV113_streaming", "label": "Sweet Young Master"},
    {"value": "BV102_streaming", "label": "Elegant Youth"},
    {"value": "BV405_streaming", "label": "Sweet Xiao Yuan"},
    {"value": "BV009_streaming", "label": "Intellectual Female"},
    {"value": "BV008_streaming", "label": "Kind Male"},
    {"value": "BV064_streaming", "label": "Little Loli"},
    {"value": "BV437_streaming", "label": "Commentary Xiao Shuai"},
    {"value": "BV511_streaming", "label": "Lazy Female - Ava"},
    {"value": "BV040_streaming", "label": "Kind Female - Anna"},
    {"value": "BV138_streaming", "label": "Emotional Female - Lawrence"},
    {"value": "BV704_streaming", "label": "Dialect Can Can"},
    {"value": "BV702_streaming", "label": "Stefan"},
    {"value": "BV421_streaming", "label": "Talented Girl"},
]

VOLCENGINE_HTTP_EMOTIONS = [
    {"value": "pleased", "label": "Pleased"},
    {"value": "sorry", "label": "Sorry"},
    {"value": "annoyed", "label": "Annoyed"},
    {"value": "happy", "label": "Happy"},
    {"value": "sad", "label": "Sad"},
    {"value": "angry", "label": "Angry"},
    {"value": "scare", "label": "Scare"},
    {"value": "hate", "label": "Hate"},
    {"value": "surprise", "label": "Surprise"},
    {"value": "tear", "label": "Tear"},
    {"value": "novel_dialog", "label": "Novel Dialog"},
    {"value": "customer_service", "label": "Customer Service"},
    {"value": "professional", "label": "Professional"},
    {"value": "serious", "label": "Serious"},
    {"value": "narrator", "label": "Narrator"},
    {"value": "narrator_immersive", "label": "Narrator Immersive"},
    {"value": "comfort", "label": "Comfort"},
    {"value": "lovey-dovey", "label": "Lovey-dovey"},
    {"value": "energetic", "label": "Energetic"},
    {"value": "conniving", "label": "Conniving"},
    {"value": "tsundere", "label": "Tsundere"},
    {"value": "charming", "label": "Charming"},
    {"value": "storytelling", "label": "Storytelling"},
    {"value": "radio", "label": "Radio"},
    {"value": "yoga", "label": "Yoga"},
    {"value": "advertising", "label": "Advertising"},
    {"value": "assistant", "label": "Assistant"},
    {"value": "chat", "label": "Chat"},
]


class VolcengineHttpTTSProvider(BaseTTSProvider):
    """TTS provider using Volcengine HTTP v1/tts API."""

    @property
    def provider_name(self) -> str:
        return "volcengine_http"

    def _get_credentials(self) -> tuple[str, str, str]:
        app_id = (get_config("VOLCENGINE_TTS_APP_KEY") or "").strip()
        token = (get_config("VOLCENGINE_TTS_ACCESS_KEY") or "").strip()
        cluster = (get_config("VOLCENGINE_TTS_RESOURCE_ID") or "").strip()
        return app_id, token, cluster

    def is_configured(self) -> bool:
        app_id, token, cluster = self._get_credentials()
        return bool(app_id and token and cluster)

    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings.

        Notes:
        - Per-Shifu voice settings are stored in the database.
        - This method only provides a provider-level fallback.
        """
        return VoiceSettings(
            voice_id="BV700_streaming",
            speed=1.0,
            pitch=10,
            emotion="",
            volume=1.0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        return AudioSettings(
            format="mp3",
            sample_rate=get_config("VOLCENGINE_TTS_SAMPLE_RATE") or 24000,
            bitrate=get_config("VOLCENGINE_TTS_BITRATE") or 128000,
            channel=1,
        )

    def _build_model_options(self) -> List[dict]:
        configured_cluster = (get_config("VOLCENGINE_TTS_RESOURCE_ID") or "").strip()
        models: List[dict] = []
        seen: set[str] = set()

        def add_model(value: str, label: str) -> None:
            if not value or value in seen:
                return
            seen.add(value)
            models.append({"value": value, "label": label})

        if configured_cluster:
            add_model(configured_cluster, f"{configured_cluster} (configured)")

        for model in VOLCENGINE_HTTP_MODELS:
            add_model(
                (model.get("value") or "").strip(),
                (model.get("label") or "").strip(),
            )

        return models

    def get_supported_voices(self) -> List[dict]:
        """Get list of supported voices."""
        return VOLCENGINE_HTTP_VOICES

    def _resolve_encoding(self, audio_settings: AudioSettings) -> str:
        encoding = (audio_settings.format or "mp3").strip().lower()
        return VOLCENGINE_HTTP_ENCODING_MAP.get(encoding, "mp3")

    def _resolve_sample_rate(self, audio_settings: AudioSettings) -> int:
        rate = int(audio_settings.sample_rate or 24000)
        if rate not in VOLCENGINE_HTTP_SAMPLE_RATES:
            return 24000
        return rate

    def _resolve_pitch_ratio(self, pitch: int) -> float:
        """
        Convert integer pitch to Volcengine pitch_ratio (0.1-3.0).

        The UI uses integer pitch values, where 10 maps to 1.0.
        """
        try:
            ratio = float(pitch) / 10.0
        except (TypeError, ValueError):
            ratio = 1.0
        return max(0.1, min(3.0, ratio))

    def synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> TTSResult:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        app_id, token, cluster = self._get_credentials()
        if not app_id or not token or not cluster:
            raise ValueError(
                "Volcengine HTTP TTS credentials are not configured. "
                "Set VOLCENGINE_TTS_APP_KEY, VOLCENGINE_TTS_ACCESS_KEY, "
                "and VOLCENGINE_TTS_RESOURCE_ID"
            )

        if not voice_settings:
            voice_settings = self.get_default_voice_settings()
        if not audio_settings:
            audio_settings = self.get_default_audio_settings()

        encoding = self._resolve_encoding(audio_settings)
        sample_rate = self._resolve_sample_rate(audio_settings)

        req_id = str(uuid.uuid4())
        uid = req_id.replace("-", "")

        payload = {
            "app": {
                "appid": app_id,
                "token": token,
                "cluster": (model or "").strip() or cluster,
            },
            "user": {"uid": uid},
            "audio": {
                "voice_type": voice_settings.voice_id,
                "encoding": encoding,
                "rate": sample_rate,
                "speed_ratio": float(voice_settings.speed or 1.0),
                "volume_ratio": float(voice_settings.volume or 1.0),
                "pitch_ratio": self._resolve_pitch_ratio(voice_settings.pitch),
            },
            "request": {
                "reqid": req_id,
                "text": text,
                "text_type": "plain",
                "operation": "query",
                "silence_duration": 125,
            },
        }

        if voice_settings.emotion:
            payload["audio"]["emotion"] = voice_settings.emotion

        headers = {"Authorization": f"Bearer;{token}"}

        try:
            response = requests.post(
                VOLCENGINE_HTTP_TTS_URL,
                json=payload,
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as exc:
            logger.error("Volcengine HTTP TTS request failed: %s", exc)
            raise ValueError(f"Volcengine HTTP TTS request failed: {exc}") from exc
        except ValueError as exc:
            logger.error("Volcengine HTTP TTS invalid JSON response: %s", exc)
            raise ValueError("Volcengine HTTP TTS response is not valid JSON") from exc

        code = result.get("code")
        message = result.get("message") or ""
        if code != 3000:
            raise ValueError(f"Volcengine HTTP TTS error {code}: {message}")

        audio_base64 = result.get("data") or ""
        if not audio_base64:
            raise ValueError("No audio data in Volcengine HTTP TTS response")

        try:
            audio_data = base64.b64decode(audio_base64)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "Invalid base64 audio data from Volcengine HTTP TTS"
            ) from exc

        duration_ms = 0
        addition = result.get("addition")
        if isinstance(addition, dict):
            duration_raw = addition.get("duration")
            if duration_raw is not None:
                try:
                    duration_ms = int(float(duration_raw))
                except (ValueError, TypeError):
                    duration_ms = 0

        logger.info(
            "Volcengine HTTP TTS synthesis completed: duration=%sms, size=%s bytes",
            duration_ms,
            len(audio_data),
        )

        return TTSResult(
            audio_data=audio_data,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            format=encoding,
            word_count=len(text),
        )

    def get_provider_config(self) -> ProviderConfig:
        """Get provider configuration for frontend."""
        return ProviderConfig(
            name="volcengine_http",
            label="Volcengine (HTTP)",
            speed=ParamRange(min=0.2, max=3.0, step=0.1, default=1.0),
            pitch=ParamRange(min=1, max=30, step=1, default=10),
            supports_emotion=True,
            models=self._build_model_options(),
            voices=VOLCENGINE_HTTP_VOICES,
            emotions=VOLCENGINE_HTTP_EMOTIONS,
        )
