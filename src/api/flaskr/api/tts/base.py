"""
TTS Provider Base Classes and Interfaces.

This module defines the abstract base classes for TTS providers,
allowing multiple TTS backends (Minimax, Volcengine, etc.) to be
used interchangeably.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class TTSProvider(str, Enum):
    """Supported TTS providers."""

    MINIMAX = "minimax"
    VOLCENGINE = "volcengine"
    VOLCENGINE_HTTP = "volcengine_http"
    BAIDU = "baidu"
    ALIYUN = "aliyun"


@dataclass
class ParamRange:
    """Parameter range configuration."""

    min: float
    max: float
    step: float
    default: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "default": self.default,
        }


@dataclass
class ProviderConfig:
    """TTS provider configuration for frontend."""

    name: str
    label: str
    speed: ParamRange
    pitch: ParamRange
    supports_emotion: bool
    models: List[Dict[str, str]] = field(default_factory=list)
    voices: List[Dict[str, str]] = field(default_factory=list)
    emotions: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "speed": self.speed.to_dict(),
            "pitch": self.pitch.to_dict(),
            "supports_emotion": self.supports_emotion,
            "models": self.models,
            "voices": self.voices,
            "emotions": self.emotions,
        }


@dataclass
class TTSResult:
    """Result of TTS synthesis."""

    audio_data: bytes
    duration_ms: int
    sample_rate: int
    format: str
    word_count: int = 0


@dataclass
class VoiceSettings:
    """Voice settings for TTS synthesis."""

    voice_id: str = ""
    speed: float = 1.0
    pitch: int = 0
    emotion: str = ""
    volume: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "voice_id": self.voice_id,
            "speed": self.speed,
            "pitch": self.pitch,
            "emotion": self.emotion,
            "volume": self.volume,
        }


@dataclass
class AudioSettings:
    """Audio settings for TTS synthesis."""

    format: str = "mp3"
    sample_rate: int = 24000
    bitrate: int = 128000
    channel: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "format": self.format,
            "sample_rate": self.sample_rate,
            "bitrate": self.bitrate,
            "channel": self.channel,
        }


class BaseTTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the provider is properly configured."""
        pass

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> TTSResult:
        """
        Synthesize text to speech.

        Args:
            text: Text to synthesize
            voice_settings: Voice settings (optional)
            audio_settings: Audio settings (optional)
            model: TTS model/resource ID (optional, provider-specific)

        Returns:
            TTSResult with audio data and metadata

        Raises:
            ValueError: If synthesis fails
        """
        pass

    @abstractmethod
    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings for this provider."""
        pass

    @abstractmethod
    def get_default_audio_settings(self) -> AudioSettings:
        """Get default audio settings for this provider."""
        pass

    def get_supported_emotions(self) -> List[str]:
        """Get list of supported emotions for this provider."""
        return []

    def get_supported_voices(self) -> List[Dict[str, str]]:
        """Get list of supported voices for this provider."""
        return []

    @abstractmethod
    def get_provider_config(self) -> ProviderConfig:
        """
        Get provider configuration for frontend.

        Returns:
            ProviderConfig with parameter ranges, voices, models, etc.
        """
        pass
