"""
Minimax TTS Provider.

This module provides TTS synthesis using Minimax's Text-to-Speech API (t2a_v2).
"""

import logging
import requests
from typing import Optional, Dict, Any, List

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

# Minimax TTS API endpoint
MINIMAX_TTS_API_URL = "https://api.minimax.chat/v1/t2a_v2"

# Allowed emotion values for Minimax TTS
MINIMAX_ALLOWED_EMOTIONS = [
    "happy",
    "sad",
    "angry",
    "fearful",
    "disgusted",
    "surprised",
    "calm",
    "neutral",
    "fluent",
    "whisper",
]

# Minimax TTS models
MINIMAX_MODELS = [
    {"value": "speech-01-turbo", "label": "Speech-01-Turbo"},
    {"value": "speech-01-hd", "label": "Speech-01-HD"},
    {"value": "speech-02-turbo", "label": "Speech-02-Turbo"},
    {"value": "speech-02-hd", "label": "Speech-02-HD"},
]

# Minimax TTS voices
MINIMAX_VOICES = [
    {"value": "male-qn-qingse", "label": "青涩青年音色"},
    {"value": "male-qn-jingying", "label": "精英青年音色"},
    {"value": "male-qn-badao", "label": "霸道青年音色"},
    {"value": "male-qn-daxuesheng", "label": "青年大学生音色"},
    {"value": "female-shaonv", "label": "少女音色"},
    {"value": "female-yujie", "label": "御姐音色"},
    {"value": "female-chengshu", "label": "成熟女性音色"},
    {"value": "female-tianmei", "label": "甜美女性音色"},
    {"value": "presenter_male", "label": "男性主持人"},
    {"value": "presenter_female", "label": "女性主持人"},
    {"value": "audiobook_male_1", "label": "男性有声书1"},
    {"value": "audiobook_male_2", "label": "男性有声书2"},
    {"value": "audiobook_female_1", "label": "女性有声书1"},
    {"value": "audiobook_female_2", "label": "女性有声书2"},
]

# Minimax emotions for frontend
MINIMAX_EMOTIONS = [
    {"value": "neutral", "label": "中性"},
    {"value": "happy", "label": "开心"},
    {"value": "sad", "label": "悲伤"},
    {"value": "angry", "label": "愤怒"},
    {"value": "fearful", "label": "恐惧"},
    {"value": "disgusted", "label": "厌恶"},
    {"value": "surprised", "label": "惊讶"},
    {"value": "calm", "label": "平静"},
]


class MinimaxTTSProvider(BaseTTSProvider):
    """TTS provider using Minimax API."""

    @property
    def provider_name(self) -> str:
        return "minimax"

    def is_configured(self) -> bool:
        """Check if Minimax TTS is properly configured."""
        api_key = get_config("MINIMAX_API_KEY")
        return bool(api_key)

    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings.

        Notes:
        - Per-Shifu voice settings are stored in the database.
        - This method only provides a provider-level fallback when callers do not
          specify a voice_id/speed/pitch/emotion.
        """
        return VoiceSettings(
            voice_id="male-qn-qingse",
            speed=1.0,
            pitch=0,
            emotion="",
            volume=1.0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        """Get default audio settings from configuration."""
        return AudioSettings(
            format="mp3",
            sample_rate=get_config("MINIMAX_TTS_SAMPLE_RATE") or 24000,
            bitrate=get_config("MINIMAX_TTS_BITRATE") or 128000,
            channel=1,
        )

    def get_supported_emotions(self) -> List[str]:
        """Get list of supported emotions."""
        return MINIMAX_ALLOWED_EMOTIONS

    def synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> TTSResult:
        """
        Synthesize text to speech using Minimax TTS.

        Args:
            text: Text to synthesize
            voice_settings: Voice settings (optional)
            audio_settings: Audio settings (optional)
            model: TTS model name (optional, defaults to config)

        Returns:
            TTSResult with audio data and metadata

        Raises:
            ValueError: If synthesis fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Call API with hex output format
        result = self._call_api(
            text=text,
            voice_settings=voice_settings,
            audio_settings=audio_settings,
            output_format="hex",
            model=model,
        )

        # Extract audio data
        data = result.get("data", {})
        audio_hex = data.get("audio")

        if not audio_hex:
            raise ValueError("No audio data in API response")

        # Decode hex to bytes
        audio_data = bytes.fromhex(audio_hex)

        # Extract metadata
        extra_info = result.get("extra_info", {})
        duration_ms = extra_info.get("audio_length", 0)
        sample_rate = extra_info.get("audio_sample_rate", 24000)
        audio_format = extra_info.get("audio_format", "mp3")
        word_count = extra_info.get("word_count", 0)

        logger.info(
            f"Minimax TTS synthesis completed: duration={duration_ms}ms, "
            f"size={len(audio_data)} bytes, words={word_count}"
        )

        return TTSResult(
            audio_data=audio_data,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            format=audio_format,
            word_count=word_count,
        )

    def _call_api(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        output_format: str = "hex",
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Minimax TTS API.

        Args:
            text: Text to synthesize
            voice_settings: Voice settings (default from config)
            audio_settings: Audio settings (default from config)
            output_format: Output format - "hex" or "url"
            model: TTS model name (optional, defaults to config)

        Returns:
            API response dictionary

        Raises:
            ValueError: If API key is not configured
            requests.RequestException: If API call fails
        """
        api_key = get_config("MINIMAX_API_KEY")
        group_id = get_config("MINIMAX_GROUP_ID")
        valid_models = {m["value"] for m in MINIMAX_MODELS}
        requested_model = (model or "").strip()
        if requested_model and requested_model not in valid_models:
            logger.warning(
                "Ignoring invalid Minimax TTS model: %s (falling back to default)",
                requested_model,
            )
            requested_model = ""

        tts_model = requested_model or "speech-01-turbo"

        if not api_key:
            raise ValueError("MINIMAX_API_KEY is not configured")

        if not voice_settings:
            voice_settings = self.get_default_voice_settings()

        if not audio_settings:
            audio_settings = self.get_default_audio_settings()

        # Build API URL with group ID if provided
        url = MINIMAX_TTS_API_URL
        if group_id:
            url = f"{url}?GroupId={group_id}"

        # Build voice setting dict for Minimax API
        voice_setting_dict = {
            "voice_id": voice_settings.voice_id,
            "speed": voice_settings.speed,
            "vol": voice_settings.volume,
        }
        if voice_settings.pitch is not None:
            voice_setting_dict["pitch"] = int(voice_settings.pitch)
        emotion = (voice_settings.emotion or "").strip()
        emotion_supported_by_model = tts_model.startswith("speech-01")
        if (
            emotion_supported_by_model
            and emotion
            and emotion != "neutral"
            and emotion in MINIMAX_ALLOWED_EMOTIONS
        ):
            voice_setting_dict["emotion"] = emotion

        # Build request payload
        payload = {
            "model": tts_model,
            "text": text,
            "stream": False,
            "voice_setting": voice_setting_dict,
            "audio_setting": audio_settings.to_dict(),
            "output_format": output_format,
            "subtitle_enable": False,
            "aigc_watermark": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        logger.debug(
            f"Calling Minimax TTS API with model={tts_model}, text_length={len(text)}"
        )

        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()

        result = response.json()

        # Check for API errors
        base_resp = result.get("base_resp", {})
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "Unknown error")
            logger.error(f"Minimax TTS API error: {status_code} - {status_msg}")
            raise ValueError(f"Minimax TTS API error: {status_code} - {status_msg}")

        return result

    def get_provider_config(self) -> ProviderConfig:
        """Get Minimax provider configuration for frontend."""
        return ProviderConfig(
            name="minimax",
            label="Minimax",
            speed=ParamRange(min=0.5, max=2.0, step=0.1, default=1.0),
            pitch=ParamRange(min=-12, max=12, step=1, default=0),
            supports_emotion=True,
            models=MINIMAX_MODELS,
            voices=MINIMAX_VOICES,
            emotions=MINIMAX_EMOTIONS,
        )
