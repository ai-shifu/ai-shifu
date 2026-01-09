"""
TTS API Client.

This module provides integration with multiple Text-to-Speech providers:
- Minimax (t2a_v2 API)
- Volcengine (bidirectional WebSocket API)
- Baidu (Short Text Online Synthesis API)

The provider can be selected via TTS_PROVIDER config or per-Shifu configuration.
"""

import base64
import logging
from typing import Optional, Tuple

from flaskr.common.config import get_config

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


logger = logging.getLogger(__name__)

# Provider instances (lazy initialized)
_provider_instances: dict = {}


def get_tts_provider(provider_name: str = "") -> BaseTTSProvider:
    """
    Get a TTS provider instance.

    Args:
        provider_name: Provider name ("minimax", "volcengine", or "baidu").
                      If empty, uses TTS_PROVIDER config or auto-detects.

    Returns:
        TTS provider instance

    Raises:
        ValueError: If no configured provider is available
    """
    global _provider_instances

    # Determine provider name
    if not provider_name:
        provider_name = get_config("TTS_PROVIDER") or ""

    # Normalize provider name
    provider_name = provider_name.lower().strip()
    if provider_name == "default":
        provider_name = ""

    # If still empty, auto-detect based on configuration
    if not provider_name:
        # Check Minimax first (existing behavior)
        if get_config("MINIMAX_API_KEY"):
            provider_name = "minimax"
        elif (
            get_config("VOLCENGINE_TTS_APP_KEY")
            and get_config("VOLCENGINE_TTS_ACCESS_KEY")
        ) or (get_config("ARK_ACCESS_KEY_ID") and get_config("ARK_SECRET_ACCESS_KEY")):
            provider_name = "volcengine"
        elif get_config("BAIDU_TTS_API_KEY") and get_config("BAIDU_TTS_SECRET_KEY"):
            provider_name = "baidu"
        elif get_config("ALIYUN_TTS_APPKEY") and get_config("ALIYUN_TTS_TOKEN"):
            provider_name = "aliyun"
        else:
            provider_name = "minimax"  # Default fallback

    # Get or create provider instance
    if provider_name not in _provider_instances:
        if provider_name == "minimax":
            _provider_instances[provider_name] = MinimaxTTSProvider()
        elif provider_name == "volcengine":
            _provider_instances[provider_name] = VolcengineTTSProvider()
        elif provider_name == "baidu":
            _provider_instances[provider_name] = BaiduTTSProvider()
        elif provider_name == "aliyun":
            _provider_instances[provider_name] = AliyunTTSProvider()
        else:
            raise ValueError(f"Unknown TTS provider: {provider_name}")

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
        try:
            minimax = MinimaxTTSProvider()
            if minimax.is_configured():
                return True
        except Exception:
            pass

        try:
            volcengine = VolcengineTTSProvider()
            if volcengine.is_configured():
                return True
        except Exception:
            pass

        try:
            baidu = BaiduTTSProvider()
            if baidu.is_configured():
                return True
        except Exception:
            pass

        try:
            aliyun = AliyunTTSProvider()
            if aliyun.is_configured():
                return True
        except Exception:
            pass

        return False


def get_all_provider_configs() -> dict:
    """
    Get configuration for all TTS providers.

    Returns:
        Dictionary with provider configurations for frontend
    """
    providers = []

    # Get config from each provider
    try:
        minimax = MinimaxTTSProvider()
        providers.append(minimax.get_provider_config().to_dict())
    except Exception as e:
        logger.warning(f"Failed to get Minimax config: {e}")

    try:
        volcengine = VolcengineTTSProvider()
        providers.append(volcengine.get_provider_config().to_dict())
    except Exception as e:
        logger.warning(f"Failed to get Volcengine config: {e}")

    try:
        baidu = BaiduTTSProvider()
        providers.append(baidu.get_provider_config().to_dict())
    except Exception as e:
        logger.warning(f"Failed to get Baidu config: {e}")

    try:
        aliyun = AliyunTTSProvider()
        providers.append(aliyun.get_provider_config().to_dict())
    except Exception as e:
        logger.warning(f"Failed to get Aliyun config: {e}")

    # Determine default provider
    default_provider = get_config("TTS_PROVIDER") or ""
    if not default_provider:
        # Auto-detect based on configuration
        if get_config("MINIMAX_API_KEY"):
            default_provider = "minimax"
        elif (
            get_config("VOLCENGINE_TTS_APP_KEY")
            and get_config("VOLCENGINE_TTS_ACCESS_KEY")
        ) or (get_config("ARK_ACCESS_KEY_ID") and get_config("ARK_SECRET_ACCESS_KEY")):
            default_provider = "volcengine"
        elif get_config("BAIDU_TTS_API_KEY") and get_config("BAIDU_TTS_SECRET_KEY"):
            default_provider = "baidu"
        elif get_config("ALIYUN_TTS_APPKEY") and get_config("ALIYUN_TTS_TOKEN"):
            default_provider = "aliyun"

    return {
        "providers": providers,
        "default_provider": default_provider,
    }


# Backward compatibility: expose Minimax-specific functions
def call_minimax_tts(*args, **kwargs):
    """Deprecated: Use get_tts_provider('minimax').synthesize() instead."""
    from flaskr.api.tts.minimax_provider import MinimaxTTSProvider

    provider = MinimaxTTSProvider()
    return provider._call_api(*args, **kwargs)
