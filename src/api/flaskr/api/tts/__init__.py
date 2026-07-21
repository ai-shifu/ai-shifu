"""
TTS API Client.

This module provides integration with multiple Text-to-Speech providers:
- Minimax (t2a_v2 API)
- Volcengine (bidirectional WebSocket API)
- Baidu (Short Text Online Synthesis API)
- Aliyun (NLS RESTful TTS API)
- Tencent (TRTC conversational SSE API)

The provider can be selected per-Shifu configuration.
"""

import logging
import json
from decimal import Decimal, InvalidOperation
from typing import Optional

from flask import has_request_context, request

from flaskr.common.config import get_config
from flaskr.util.datetime import now_utc
from flaskr.common.log import AppLoggerProxy
from flaskr.i18n import get_current_language
from flaskr.service.billing.consts import BILLING_METRIC_TTS_OUTPUT_CHARS
from flaskr.service.billing.rate_references import load_llm_credit_1x_unit_cost
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_TTS

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
from flaskr.api.tts.tencent_provider import TencentTTSProvider


logger = AppLoggerProxy(logging.getLogger(__name__))
TTS_DEFAULT_MODEL_TOKEN = "default"

# Provider registry (ordered by default selection priority)
_PROVIDER_REGISTRY = {
    "minimax": MinimaxTTSProvider,
    "volcengine": VolcengineTTSProvider,
    "volcengine_http": VolcengineHttpTTSProvider,
    "baidu": BaiduTTSProvider,
    "aliyun": AliyunTTSProvider,
    "tencent": TencentTTSProvider,
}
_PROVIDER_PRIORITY = (
    "minimax",
    "volcengine",
    "volcengine_http",
    "baidu",
    "aliyun",
    "tencent",
)
_AUTO_DETECT_PROVIDER_PRIORITY = (
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
            or get_config("VOLCENGINE_TTS_RESOURCE_ID")
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


def _iter_provider_classes(*, include_explicit_only: bool = True):
    provider_priority = (
        _PROVIDER_PRIORITY if include_explicit_only else _AUTO_DETECT_PROVIDER_PRIORITY
    )
    for name in provider_priority:
        provider_cls = _PROVIDER_REGISTRY.get(name)
        if provider_cls:
            yield name, provider_cls


def get_tts_provider(provider_name: str = "") -> BaseTTSProvider:
    """
    Get a TTS provider instance.

    Args:
        provider_name: Provider name ("minimax", "volcengine", "volcengine_http", "baidu", "aliyun", "tencent").
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
        for _name, provider_cls in _iter_provider_classes(include_explicit_only=False):
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
    configured = get_config("TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON")
    if isinstance(configured, dict):
        payload = configured
    else:
        raw = str(configured or "").strip()
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Ignoring invalid TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON: %s", exc
            )
            return {}
    if not isinstance(payload, dict):
        return {}

    # Normalize keys the same way as TTS_ALLOWED_MODELS so localized labels are
    # found regardless of the provider/model casing used in the config value.
    normalized: dict = {}
    for raw_key, value in payload.items():
        key = str(raw_key or "").strip()
        if "/" not in key:
            continue
        provider, model = key.split("/", 1)
        normalized_key = _normalize_tts_model_key(provider, model)
        if normalized_key:
            normalized[normalized_key] = value
    return normalized


def _iter_tts_display_language_candidates():
    if has_request_context():
        for value in (
            request.args.get("language"),
            request.headers.get("X-Language"),
            request.headers.get("X-Locale"),
        ):
            normalized = str(value or "").strip()
            if normalized:
                yield normalized

        accept_language = request.headers.get("Accept-Language", "")
        for part in accept_language.split(","):
            normalized = part.split(";", 1)[0].strip()
            if normalized:
                yield normalized

    language = str(get_current_language() or "").strip()
    if language:
        yield language
    yield "en-US"


def _resolve_locale_entry(entry: dict, language: str) -> str:
    normalized_language = str(language or "").replace("_", "-").lower()
    if not normalized_language:
        return ""

    normalized_primary = normalized_language.split("-", 1)[0]
    for key, value in entry.items():
        normalized_key = str(key or "").replace("_", "-").lower()
        if normalized_key == normalized_language:
            return str(value or "").strip()

    for key, value in entry.items():
        normalized_key = str(key or "").replace("_", "-").lower()
        if normalized_key.split("-", 1)[0] == normalized_primary:
            return str(value or "").strip()

    return ""


def _resolve_localized_tts_label(
    display_names: dict,
    key: str,
    fallback: str,
) -> str:
    entry = display_names.get(key)
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    if isinstance(entry, dict):
        for locale in _iter_tts_display_language_candidates():
            value = _resolve_locale_entry(entry, locale)
            if value:
                return value
    return fallback


def _resolve_credit_multiplier_label(provider_name: str, model: str) -> str | None:
    try:
        # One shared fixed 1x anchor for LLM and TTS. TTS is priced per
        # character, so translate its per-character cost into the same
        # per-LLM-token dimension using chars-synthesized-per-token.
        baseline_cost = load_llm_credit_1x_unit_cost()
        if baseline_cost is None or baseline_cost <= 0:
            return None
        chars_per_token = _load_tts_chars_per_llm_token()
        if chars_per_token is None or chars_per_token <= 0:
            return None
        tts_char_cost = _load_usage_rate_unit_cost(
            usage_type=BILL_USAGE_TYPE_TTS,
            provider=provider_name,
            model_candidates=[model],
            billing_metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
            ignore_global_wildcard=True,
        )
        if tts_char_cost is None or tts_char_cost <= 0:
            return None
        multiplier = (tts_char_cost * chars_per_token) / baseline_cost
        return _format_credit_multiplier_label(multiplier)
    except Exception as exc:
        logger.debug("Skipping TTS credit multiplier label: %s", exc)
        return None


def _load_tts_chars_per_llm_token() -> Decimal | None:
    # TTS is billed per character but the fixed 1x anchor is an LLM output token,
    # so we need "how many TTS characters one LLM token turns into" to compare
    # them on one scale. This is omega x 1.6 (TTS-token share of a task x
    # token->char ratio); see TTS_CHARS_PER_LLM_TOKEN.
    try:
        raw = get_config("TTS_CHARS_PER_LLM_TOKEN", "")
        if raw is None or str(raw).strip() == "":
            return None
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _load_usage_rate_unit_cost(
    *,
    usage_type: int,
    provider: str,
    model_candidates: list[str],
    billing_metric: int,
    ignore_global_wildcard: bool = False,
) -> Decimal | None:
    from flaskr.service.billing.charges import load_usage_rate
    from flaskr.service.metering.models import BillUsageRecord

    normalized_models = [str(model or "").strip() for model in model_candidates]
    if not normalized_models:
        normalized_models = [""]
    # Match the UTC settlement window used by billing rate selection.
    settlement_at = now_utc()
    for model in normalized_models:
        rate = load_usage_rate(
            usage=BillUsageRecord(
                usage_type=int(usage_type),
                provider=str(provider or "").strip(),
                model=model,
                usage_scene=BILL_USAGE_SCENE_PROD,
            ),
            billing_metric=billing_metric,
            settlement_at=settlement_at,
        )
        if rate is None:
            continue
        if (
            ignore_global_wildcard
            and str(rate.provider or "").strip() == "*"
            and str(rate.model or "").strip() == "*"
        ):
            continue
        try:
            unit_size = max(int(rate.unit_size or 1), 1)
            return Decimal(str(rate.credits_per_unit or 0)) / Decimal(str(unit_size))
        except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
            continue
    return None


def _format_credit_multiplier_label(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"))
    text = format(rounded.normalize(), "f").rstrip("0").rstrip(".")
    return f"{text or '0'}x"


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
