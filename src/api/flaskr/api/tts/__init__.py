"""
TTS API Client.

This module provides integration with multiple Text-to-Speech providers:
- Minimax (t2a_v2 API)
- Volcengine (bidirectional WebSocket API)
- Baidu (Short Text Online Synthesis API)
- Aliyun (NLS RESTful TTS API)

The provider can be selected per-Shifu configuration.
"""

import base64
import logging
from typing import Optional, Tuple

from flaskr.common.config import get_config
from flaskr.common.log import AppLoggerProxy

# Re-export base classes for backward compatibility
from flaskr.api.tts.base import (
    TTSProvider as TTSProvider,
    TTSResult as TTSResult,
    VoiceSettings as VoiceSettings,
    AudioSettings as AudioSettings,
    BaseTTSProvider as BaseTTSProvider,
)
from flaskr.api.tts.minimax_provider import MinimaxTTSProvider
from flaskr.api.tts.volcengine_provider import VolcengineTTSProvider
from flaskr.api.tts.baidu_provider import BaiduTTSProvider
from flaskr.api.tts.aliyun_provider import AliyunTTSProvider


logger = AppLoggerProxy(logging.getLogger(__name__))

# Provider registry (ordered by default selection priority)
_PROVIDER_REGISTRY = {
    "minimax": MinimaxTTSProvider,
    "volcengine": VolcengineTTSProvider,
    "baidu": BaiduTTSProvider,
    "aliyun": AliyunTTSProvider,
}
_PROVIDER_PRIORITY = ("minimax", "volcengine", "baidu", "aliyun")

# Provider instances (lazy initialized)
_provider_instances: dict = {}


def _normalize_provider_name(provider_name: str) -> str:
    normalized = (provider_name or "").strip().lower()
    if normalized == "default":
        return ""
    return normalized


def _auto_detect_provider_name() -> str:
    # Check Minimax first (existing behavior)
    if get_config("MINIMAX_API_KEY"):
        return "minimax"
    if get_config("ARK_ACCESS_KEY_ID") and get_config("ARK_SECRET_ACCESS_KEY"):
        return "volcengine"
    if get_config("BAIDU_TTS_API_KEY") and get_config("BAIDU_TTS_SECRET_KEY"):
        return "baidu"
    if get_config("ALIYUN_TTS_APPKEY") and get_config("ALIYUN_TTS_TOKEN"):
        return "aliyun"
    return "minimax"  # Default fallback


def _resolve_provider_name(provider_name: str = "") -> str:
    normalized = _normalize_provider_name(provider_name)
    return normalized or _auto_detect_provider_name()


def _iter_provider_classes():
    for name in _PROVIDER_PRIORITY:
        provider_cls = _PROVIDER_REGISTRY.get(name)
        if provider_cls:
            yield name, provider_cls


def get_tts_provider(provider_name: str = "") -> BaseTTSProvider:
    """
    Get a TTS provider instance.

    Args:
        provider_name: Provider name ("minimax", "volcengine", "baidu", "aliyun").
                      If empty, auto-detects.

    Returns:
        TTS provider instance

    Raises:
        ValueError: If no configured provider is available
    """
    global _provider_instances

    provider_name = _resolve_provider_name(provider_name)

    # Get or create provider instance
    if provider_name not in _provider_instances:
        provider_cls = _PROVIDER_REGISTRY.get(provider_name)
        if not provider_cls:
            raise ValueError(f"Unknown TTS provider: {provider_name}")
        _provider_instances[provider_name] = provider_cls()

    return _provider_instances[provider_name]


def get_default_voice_settings(provider_name: str = "") -> VoiceSettings:
    """Get default voice settings for the specified provider."""
    provider = get_tts_provider(provider_name)
    return provider.get_default_voice_settings()


def get_default_audio_settings(provider_name: str = "") -> AudioSettings:
    """Get default audio settings for the specified provider."""
    provider = get_tts_provider(provider_name)
    return provider.get_default_audio_settings()


def synthesize_text(
    text: str,
    voice_settings: Optional[VoiceSettings] = None,
    audio_settings: Optional[AudioSettings] = None,
    model: Optional[str] = None,
    provider_name: str = "",
) -> TTSResult:
    """
    Synthesize text to speech.

    Args:
        text: Text to synthesize
        voice_settings: Voice settings (optional)
        audio_settings: Audio settings (optional)
        model: TTS model name (optional, provider-specific)
        provider_name: Provider name (optional, uses config if empty)

    Returns:
        TTSResult with audio data and metadata

    Raises:
        ValueError: If synthesis fails
    """
    provider = get_tts_provider(provider_name)
    return provider.synthesize(
        text=text,
        voice_settings=voice_settings,
        audio_settings=audio_settings,
        model=model,
    )


def synthesize_text_to_base64(
    text: str,
    voice_settings: Optional[VoiceSettings] = None,
    audio_settings: Optional[AudioSettings] = None,
    model: Optional[str] = None,
    provider_name: str = "",
) -> Tuple[str, int]:
    """
    Synthesize text to speech and return base64 encoded audio.

    Args:
        text: Text to synthesize
        voice_settings: Voice settings (optional)
        audio_settings: Audio settings (optional)
        model: TTS model name (optional)
        provider_name: Provider name (optional)

    Returns:
        Tuple of (base64_audio_data, duration_ms)
    """
    result = synthesize_text(
        text=text,
        voice_settings=voice_settings,
        audio_settings=audio_settings,
        model=model,
        provider_name=provider_name,
    )

    base64_data = base64.b64encode(result.audio_data).decode("utf-8")
    return base64_data, result.duration_ms


def is_tts_configured(provider_name: str = "") -> bool:
    """
    Check if TTS is properly configured.

    Args:
        provider_name: Provider name (optional, checks all if empty)

    Returns:
        True if at least one provider is configured
    """
    if provider_name:
        try:
            provider = get_tts_provider(provider_name)
            return provider.is_configured()
        except ValueError:
            return False
    else:
        # Check if any provider is configured
        for _name, provider_cls in _iter_provider_classes():
            try:
                if provider_cls().is_configured():
                    return True
            except Exception:
                continue
        return False


def get_all_provider_configs() -> dict:
    """
    Get configuration for all TTS providers.

    Returns:
        Dictionary with provider configurations for frontend
    """
    providers = []

    # Get config from each provider
    for name, provider_cls in _iter_provider_classes():
        try:
            provider = provider_cls()
            providers.append(provider.get_provider_config().to_dict())
        except Exception as e:
            logger.warning("Failed to get %s config: %s", name, e)

    return {
        "providers": providers,
    }


# Backward compatibility: expose Minimax-specific functions
def call_minimax_tts(*args, **kwargs):
    """Deprecated: Use get_tts_provider('minimax').synthesize() instead."""
    from flaskr.api.tts.minimax_provider import MinimaxTTSProvider

    provider = MinimaxTTSProvider()
    return provider._call_api(*args, **kwargs)
