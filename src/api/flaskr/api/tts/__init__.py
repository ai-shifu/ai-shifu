"""
Minimax TTS API Client.

This module provides integration with Minimax's Text-to-Speech API (t2a_v2).
"""

import base64
import logging
import requests
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from flaskr.common.config import get_config


logger = logging.getLogger(__name__)

# Minimax TTS API endpoint
MINIMAX_TTS_API_URL = "https://api.minimax.chat/v1/t2a_v2"

# Allowed emotion values for Minimax TTS
ALLOWED_EMOTIONS = {
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
}


@dataclass
class TTSResult:
    """Result of TTS synthesis."""

    audio_data: bytes
    duration_ms: int
    sample_rate: int
    format: str
    word_count: int


@dataclass
class VoiceSettings:
    """Voice settings for TTS synthesis."""

    voice_id: str = "male-qn-qingse"
    speed: float = 1.0
    pitch: int = 0
    emotion: str = "neutral"
    volume: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API request format."""
        settings = {
            "voice_id": self.voice_id,
            "speed": self.speed,
            "vol": self.volume,
        }
        # Pitch must be an integer for Minimax API
        if self.pitch is not None:
            settings["pitch"] = int(self.pitch)
        # Only include emotion if it's in allowed values
        if self.emotion and self.emotion in ALLOWED_EMOTIONS:
            settings["emotion"] = self.emotion
        return settings


@dataclass
class AudioSettings:
    """Audio settings for TTS synthesis."""

    format: str = "mp3"
    sample_rate: int = 24000
    bitrate: int = 128000
    channel: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API request format."""
        return {
            "format": self.format,
            "sample_rate": self.sample_rate,
            "bitrate": self.bitrate,
            "channel": self.channel,
        }


def get_default_voice_settings() -> VoiceSettings:
    """Get default voice settings from configuration."""
    return VoiceSettings(
        voice_id=get_config("MINIMAX_TTS_VOICE_ID") or "male-qn-qingse",
        speed=get_config("MINIMAX_TTS_SPEED") or 1.0,
        pitch=get_config("MINIMAX_TTS_PITCH") or 0,
        emotion=get_config("MINIMAX_TTS_EMOTION") or "neutral",
        volume=get_config("MINIMAX_TTS_VOLUME") or 1.0,
    )


def get_default_audio_settings() -> AudioSettings:
    """Get default audio settings from configuration."""
    return AudioSettings(
        format="mp3",
        sample_rate=get_config("MINIMAX_TTS_SAMPLE_RATE") or 24000,
        bitrate=get_config("MINIMAX_TTS_BITRATE") or 128000,
        channel=1,
    )


def call_minimax_tts(
    text: str,
    model: Optional[str] = None,
    voice_settings: Optional[VoiceSettings] = None,
    audio_settings: Optional[AudioSettings] = None,
    output_format: str = "hex",
) -> Dict[str, Any]:
    """
    Call Minimax TTS API.

    Args:
        text: Text to synthesize
        model: TTS model name (default from config)
        voice_settings: Voice settings (default from config)
        audio_settings: Audio settings (default from config)
        output_format: Output format - "hex" or "url"

    Returns:
        API response dictionary

    Raises:
        ValueError: If API key is not configured
        requests.RequestException: If API call fails
    """
    api_key = get_config("MINIMAX_API_KEY")
    group_id = get_config("MINIMAX_GROUP_ID")

    if not api_key:
        raise ValueError("MINIMAX_API_KEY is not configured")

    if not model:
        model = get_config("MINIMAX_TTS_MODEL") or "speech-01-turbo"

    if not voice_settings:
        voice_settings = get_default_voice_settings()

    if not audio_settings:
        audio_settings = get_default_audio_settings()

    # Build API URL with group ID if provided
    url = MINIMAX_TTS_API_URL
    if group_id:
        url = f"{url}?GroupId={group_id}"

    # Build request payload
    payload = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": voice_settings.to_dict(),
        "audio_setting": audio_settings.to_dict(),
        "output_format": output_format,
        "subtitle_enable": False,
        "aigc_watermark": False,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    logger.debug(f"Calling Minimax TTS API with model={model}, text_length={len(text)}")

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


def synthesize_text(
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
        model: TTS model name (optional)

    Returns:
        TTSResult with audio data and metadata

    Raises:
        ValueError: If synthesis fails
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")

    # Call API with hex output format
    result = call_minimax_tts(
        text=text,
        model=model,
        voice_settings=voice_settings,
        audio_settings=audio_settings,
        output_format="hex",
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
        f"TTS synthesis completed: duration={duration_ms}ms, "
        f"size={len(audio_data)} bytes, words={word_count}"
    )

    return TTSResult(
        audio_data=audio_data,
        duration_ms=duration_ms,
        sample_rate=sample_rate,
        format=audio_format,
        word_count=word_count,
    )


def synthesize_text_to_base64(
    text: str,
    voice_settings: Optional[VoiceSettings] = None,
    audio_settings: Optional[AudioSettings] = None,
    model: Optional[str] = None,
) -> Tuple[str, int]:
    """
    Synthesize text to speech and return base64 encoded audio.

    Args:
        text: Text to synthesize
        voice_settings: Voice settings (optional)
        audio_settings: Audio settings (optional)
        model: TTS model name (optional)

    Returns:
        Tuple of (base64_audio_data, duration_ms)
    """
    result = synthesize_text(
        text=text,
        voice_settings=voice_settings,
        audio_settings=audio_settings,
        model=model,
    )

    base64_data = base64.b64encode(result.audio_data).decode("utf-8")
    return base64_data, result.duration_ms


def is_tts_enabled() -> bool:
    """Check if TTS is enabled in configuration."""
    return get_config("TTS_ENABLED") is True


def is_tts_configured() -> bool:
    """Check if TTS is properly configured."""
    api_key = get_config("MINIMAX_API_KEY")
    return bool(api_key)
