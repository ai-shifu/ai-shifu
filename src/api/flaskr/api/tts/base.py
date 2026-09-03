"""TTS Provider Base Classes and Interfaces.

This module defines the abstract base classes for TTS providers,
allowing multiple TTS backends (Minimax, Volcengine, etc.) to be
used interchangeably.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar


class TTSProvider(StrEnum):
    """Supported TTS providers."""

    MINIMAX = "minimax"
    VOLCENGINE = "volcengine"
    VOLCENGINE_HTTP = "volcengine_http"
    BAIDU = "baidu"
    ALIYUN = "aliyun"
    TENCENT = "tencent"
    TENCENT_TEXTTOVOICE = "tencent_texttovoice"
    ELEVENLABS = "elevenlabs"
    GEMINI = "gemini"


REQUEST_SCOPED_STREAM_MINIMAX_HTTP = "minimax_http"
REQUEST_SCOPED_STREAM_VOLCENGINE_TIMESTAMP = "volcengine_timestamp"


@dataclass(frozen=True)
class ProviderCapabilities:
    """Behavior a provider declares so shared code never keys on its name.

    Every flag defaults to the most conservative value; a provider opts into
    each behavior explicitly. The orchestration layers (validation, streaming,
    segmentation, config exposure) read these instead of maintaining
    provider-name sets.
    """

    requires_model: bool = False
    """Strict validation demands an explicit model/resource id."""
    requires_listed_voice: bool = False
    """Strict validation only accepts voices the provider lists."""
    retry_on_empty_audio: bool = False
    """An empty-audio response is transient and worth one quick retry."""
    skip_non_speakable_text: bool = False
    """Segments without letters or digits are skipped before synthesis."""
    segment_max_bytes: int | None = None
    """Extra per-request byte cap applied after character segmentation."""
    segment_encoding: str = "utf-8"
    """Encoding used to measure ``segment_max_bytes``."""
    expose_only_when_configured: bool = False
    """Hide the provider from the config payload unless it is configured."""
    restrict_models_to_allowlist: bool = False
    """Narrow exposed models to TTS_ALLOWED_MODELS and hide when none match."""
    auto_detectable: bool = False
    """Eligible for credential-based auto-detection when no provider is set."""
    request_scoped_stream: str = ""
    """Named request-scoped synthesis path used instead of sentence segments."""


@dataclass
class ParamRange:
    """Parameter range configuration."""

    min: float
    max: float
    step: float
    default: float

    def to_dict(self) -> dict[str, Any]:
        """Return a new mapping with min, max, step, and default values."""
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
    models: list[dict[str, str]] | None = None
    voices: list[dict[str, str]] = field(default_factory=list)
    emotions: list[dict[str, str]] = field(default_factory=list)
    supports_custom_voice_id: bool = False
    supports_voice_cloning: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return frontend config with serialized ranges and shared list values."""
        data = {
            "name": self.name,
            "label": self.label,
            "speed": self.speed.to_dict(),
            "pitch": self.pitch.to_dict(),
            "supports_emotion": self.supports_emotion,
            "supports_custom_voice_id": self.supports_custom_voice_id,
            "supports_voice_cloning": self.supports_voice_cloning,
            "voices": self.voices,
            "emotions": self.emotions,
        }
        if self.models is not None:
            data["models"] = self.models
        return data


@dataclass
class TTSResult:
    """Result of TTS synthesis."""

    audio_data: bytes
    duration_ms: int
    sample_rate: int
    format: str
    word_count: int = 0
    usage_characters: int = 0
    subtitle_cues: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class VoiceSettings:
    """Voice settings for TTS synthesis."""

    voice_id: str = ""
    speed: float = 1.0
    pitch: int = 0
    emotion: str = ""
    volume: float = 1.0

    def to_dict(self) -> dict[str, Any]:
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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "format": self.format,
            "sample_rate": self.sample_rate,
            "bitrate": self.bitrate,
            "channel": self.channel,
        }


class BaseTTSProvider(ABC):
    """Abstract base class for TTS providers."""

    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities()

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the provider is properly configured."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_settings: VoiceSettings | None = None,
        audio_settings: AudioSettings | None = None,
        model: str | None = None,
    ) -> TTSResult:
        """Synthesize text to speech.

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

    @abstractmethod
    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings for this provider."""

    @abstractmethod
    def get_default_audio_settings(self) -> AudioSettings:
        """Get default audio settings for this provider."""

    def get_supported_emotions(self) -> list[str]:
        """Get list of supported emotions for this provider."""
        return []

    def get_supported_voices(self) -> list[dict[str, str]]:
        """Get list of supported voices for this provider."""
        return []

    @abstractmethod
    def get_provider_config(self) -> ProviderConfig:
        """Get provider configuration for frontend.

        Returns:
            ProviderConfig with parameter ranges, voices, models, etc.

        """
