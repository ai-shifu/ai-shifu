"""
TTS API Client.

This module provides integration with multiple Text-to-Speech providers:
- Minimax (t2a_v2 API)
- Volcengine (bidirectional WebSocket API)
- Baidu (Short Text Online Synthesis API)
- Aliyun (NLS RESTful TTS API)

The provider can be selected per-Shifu configuration.
"""

import logging
import os
import json
from typing import Optional

from flaskr.common.config import get_config
from flaskr.common.log import AppLoggerProxy
from flaskr.i18n import get_current_language
from flaskr.service.metering.consts import BILL_USAGE_TYPE_TTS

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
from flaskr.api.tts.volcengine_http_provider import VolcengineHttpTTSProvider
from flaskr.api.tts.baidu_provider import BaiduTTSProvider
from flaskr.api.tts.aliyun_provider import AliyunTTSProvider
from flaskr.api.tts.aliyun_nls_token import is_aliyun_nls_token_configured


logger = AppLoggerProxy(logging.getLogger(__name__))
TTS_DEFAULT_MODEL_TOKEN = "default"

# Provider registry (ordered by default selection priority)
_PROVIDER_REGISTRY = {
    "minimax": MinimaxTTSProvider,
    "volcengine": VolcengineTTSProvider,
    "volcengine_http": VolcengineHttpTTSProvider,
    "baidu": BaiduTTSProvider,
    "aliyun": AliyunTTSProvider,
}
_PROVIDER_PRIORITY = (
    "minimax",
    "volcengine",
    "volcengine_http",
    "baidu",
    "aliyun",
)

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
    if (
        get_config("VOLCENGINE_TTS_APP_KEY")
        and get_config("VOLCENGINE_TTS_ACCESS_KEY")
        and (
            get_config("VOLCENGINE_TTS_CLUSTER_ID")
            or os.environ.get("VOLCENGINE_TTS_RESOURCE_ID")
        )
    ):
        return "volcengine_http"
    if get_config("BAIDU_TTS_API_KEY") and get_config("BAIDU_TTS_SECRET_KEY"):
        return "baidu"
    if get_config("ALIYUN_TTS_APPKEY") and is_aliyun_nls_token_configured():
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
        provider_name: Provider name ("minimax", "volcengine", "volcengine_http", "baidu", "aliyun").
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


def _normalize_tts_model_key(provider_name: str, model: str = "") -> str:
    provider = (provider_name or "").strip().lower()
    model_key = (model or "").strip() or TTS_DEFAULT_MODEL_TOKEN
    return f"{provider}/{model_key}" if provider else ""


def _parse_allowed_tts_model_keys() -> list[str]:
    keys: list[str] = []
    seen = set()
    configured = get_config("TTS_ALLOWED_MODELS") or []
    if isinstance(configured, str):
        configured = configured.split(",")
    for raw in configured:
        value = str(raw or "").strip()
        if not value:
            continue
        if "/" not in value:
            logger.warning("Ignoring invalid TTS_ALLOWED_MODELS entry: %s", value)
            continue
        provider, model = value.split("/", 1)
        key = _normalize_tts_model_key(provider, model)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _parse_tts_display_names() -> dict:
    raw = str(get_config("TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON") or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        logger.warning("Ignoring invalid TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON: %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_localized_tts_label(
    display_names: dict,
    key: str,
    fallback: str,
) -> str:
    entry = display_names.get(key)
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    if isinstance(entry, dict):
        language = get_current_language()
        for locale in (language, "en-US"):
            value = str(entry.get(locale) or "").strip()
            if value:
                return value
    return fallback


def _resolve_credit_multiplier_label(provider_name: str, model: str) -> str | None:
    try:
        from flaskr.service.billing.charges import resolve_credit_multiplier_label

        return resolve_credit_multiplier_label(
            usage_type=BILL_USAGE_TYPE_TTS,
            provider=provider_name,
            model=model,
        )
    except Exception as exc:
        logger.debug("Skipping TTS credit multiplier label: %s", exc)
        return None


def _build_tts_model_options(provider_payloads: list[tuple[str, dict]]) -> list[dict]:
    display_names = _parse_tts_display_names()
    options: list[dict] = []

    for provider_name, payload in provider_payloads:
        provider_label = str(payload.get("label") or provider_name).strip()
        models = payload.get("models") or []
        if not models:
            key = _normalize_tts_model_key(provider_name)
            option = {
                "value": key,
                "label": _resolve_localized_tts_label(
                    display_names, key, provider_label or provider_name
                ),
                "provider": provider_name,
                "model": "",
            }
            credit_label = _resolve_credit_multiplier_label(provider_name, "")
            if credit_label:
                option["credit_multiplier_label"] = credit_label
            options.append(option)
            continue

        for item in models:
            if not isinstance(item, dict):
                continue
            model = str(item.get("value") or "").strip()
            if not model:
                continue
            key = _normalize_tts_model_key(provider_name, model)
            model_label = str(item.get("label") or model).strip()
            fallback_label = (
                f"{provider_label} / {model_label}" if provider_label else model_label
            )
            option = {
                "value": key,
                "label": _resolve_localized_tts_label(
                    display_names, key, fallback_label
                ),
                "provider": provider_name,
                "model": model,
            }
            credit_label = _resolve_credit_multiplier_label(provider_name, model)
            if credit_label:
                option["credit_multiplier_label"] = credit_label
            options.append(option)

    allowed_keys = _parse_allowed_tts_model_keys()
    if not allowed_keys:
        return options

    option_map = {option["value"]: option for option in options}
    filtered = [option_map[key] for key in allowed_keys if key in option_map]
    missing = [key for key in allowed_keys if key not in option_map]
    if missing:
        logger.warning("Ignoring unavailable TTS_ALLOWED_MODELS entries: %s", missing)
    return filtered


def get_all_provider_configs() -> dict:
    """
    Get configuration for all TTS providers.

    Returns:
        Dictionary with provider configurations for frontend
    """
    providers = []
    provider_payloads: list[tuple[str, dict]] = []

    # Get config from each provider
    for name, provider_cls in _iter_provider_classes():
        try:
            provider = provider_cls()
            payload = provider.get_provider_config().to_dict()
            providers.append(payload)
            provider_payloads.append((name, payload))
        except Exception as e:
            logger.warning("Failed to get %s config: %s", name, e)

    return {
        "providers": providers,
        "model_options": _build_tts_model_options(provider_payloads),
    }
