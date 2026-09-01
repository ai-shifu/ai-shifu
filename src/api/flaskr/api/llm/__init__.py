"""LLM invocation wrappers built on LiteLLM."""

import asyncio
import logging
import os
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

import requests

# litellm fetches its model cost map from GitHub at import time by default,
# which stalls every worker boot (and times out entirely on hosts without
# outbound internet). Default to the bundled local map; deployments can still
# override by exporting LITELLM_LOCAL_MODEL_COST_MAP=False before startup.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm
from flask import Flask, current_app
from litellm.types.utils import ModelResponseStream

from flaskr.api.langfuse import (
    LangfuseObservationHandle,
    build_langfuse_observation_link,
    get_request_id,
    normalize_langfuse_output_value,
    resolve_langfuse_trace_id,
)
from flaskr.common.config import (
    get_explicit_env_override,
    parse_llm_model_max_output_tokens,
)
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.billing.rate_references import (
    format_credit_multiplier,
    load_llm_credit_1x_unit_cost,
)
from flaskr.service.common.models import raise_error_with_args
from flaskr.service.config import get_config
from flaskr.service.metering import UsageContext, record_llm_usage
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    normalize_usage_scene,
)
from flaskr.util.datetime import NAIVE_DATETIME_MIN, now_utc

logger = logging.getLogger(__name__)

# Global asyncio.run patch to avoid RuntimeError when called from a running
# event loop (seen in LiteLLM logging threads under gunicorn/gevent). For the
# specific case where a loop is already running, we fall back to scheduling
# the coroutine on the existing loop instead of raising.
_original_asyncio_run = asyncio.run
# Strong references so fire-and-forget tasks are not garbage-collected mid-run.
_background_asyncio_tasks: set[asyncio.Task] = set()


def _safe_asyncio_run(coro: object, *args: object, **kwargs: object) -> object | None:
    try:
        return _original_asyncio_run(coro, *args, **kwargs)
    except RuntimeError as exc:
        message = str(exc)
        if "cannot be called from a running event loop" not in message:
            # Preserve original behaviour for unrelated errors.
            raise
        loop = asyncio.get_running_loop()
        try:
            task = loop.create_task(coro)
            _background_asyncio_tasks.add(task)
            task.add_done_callback(_background_asyncio_tasks.discard)
        except Exception:
            # If even scheduling fails, swallow the error so logging/caching
            # failures do not break the main application.
            return None


asyncio.run = _safe_asyncio_run


@dataclass
class ProviderConfig:
    """Describe configuration for one LLM provider."""

    key: str
    api_key_env: str
    base_url_env: str | None = None
    default_base_url: str | None = None
    prefix: str = ""
    fetch_models: bool = True
    filter_fn: Callable[[str], bool] | None = None
    static_models: list[str] = field(default_factory=list)
    extra_models: list[str] = field(default_factory=list)
    wildcard_prefixes: tuple[str, ...] = ()
    config_hint: str = ""
    custom_llm_provider: str | None = None
    model_loader: (
        Callable[
            ["ProviderConfig", dict[str, str], str | None], list[str | tuple[str, str]]
        ]
        | None
    ) = None


@dataclass
class ProviderState:
    """Track availability and retry state for one LLM provider."""

    enabled: bool
    params: dict[str, str] | None
    models: list[str]
    prefix: str = ""
    wildcard_prefixes: tuple[str, ...] = ()


MODEL_ALIAS_MAP: dict[str, tuple[str, str]] = {}
PROVIDER_STATES: dict[str, ProviderState] = {}
MODEL_MAX_OUTPUT_TOKENS: dict[str, int] = {}
_USAGE_OUTPUT_TEXT_MAX_LENGTH = 12000
_INCOMPLETE_FINISH_REASONS = frozenset({"content_filter", "length"})


def _log(level: str, message: str) -> None:
    try:
        getattr(current_app.logger, level)(message)
    except Exception:
        getattr(logger, level)(message)


def _log_info(message: str) -> None:
    _log("info", message)


def _log_warning(message: str) -> None:
    _log("warning", message)


def _extract_usage_value(usage: object, key: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(key) or 0)
    return int(getattr(usage, key, 0) or 0)


def _extract_input_cache(usage: object) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        if "input_cache" in usage:
            return int(usage.get("input_cache") or 0)
        details = usage.get("input_tokens_details") or usage.get(
            "prompt_tokens_details"
        )
        if isinstance(details, dict):
            return int(details.get("cached_tokens") or 0)
        return 0
    value = getattr(usage, "input_cache", None)
    if value is not None:
        return int(value or 0)
    details = getattr(usage, "input_tokens_details", None) or getattr(
        usage, "prompt_tokens_details", None
    )
    if isinstance(details, dict):
        return int(details.get("cached_tokens") or 0)
    if details is not None:
        return int(getattr(details, "cached_tokens", 0) or 0)
    return 0


def _attach_usage_output_text(
    metadata: dict[str, object],
    response_text: str,
) -> dict[str, object]:
    """Store a bounded response excerpt for operator usage detail summaries."""
    normalized_response_text = str(response_text or "").strip()
    if not normalized_response_text or "output_text" in metadata:
        return metadata
    next_metadata = dict(metadata)
    next_metadata["output_text"] = normalized_response_text[
        :_USAGE_OUTPUT_TEXT_MAX_LENGTH
    ]
    return next_metadata


def _extract_reasoning_delta(delta: object) -> str:
    """Return provider reasoning from a normalized LiteLLM stream delta."""

    def _get(value: object, key: str) -> object:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    def _normalize(value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value
        return normalize_langfuse_output_value(value)

    candidates: list[Any] = [
        _get(delta, "reasoning_content"),
        _get(delta, "reasoning"),
    ]
    thinking_blocks = _get(delta, "thinking_blocks")
    if isinstance(thinking_blocks, list):
        block_reasoning = []
        for block in thinking_blocks:
            # Anthropic emits the full accumulated thinking again alongside
            # the signature. Incremental reasoning was already delivered in
            # earlier chunks, so recording the signed snapshot duplicates it.
            if _normalize(_get(block, "signature")):
                continue
            normalized = _normalize(_get(block, "thinking"))
            if normalized:
                block_reasoning.append(normalized)
        if block_reasoning:
            candidates.append("\n".join(block_reasoning))
    provider_fields = _get(delta, "provider_specific_fields")
    if provider_fields:
        candidates.extend(
            [
                _get(provider_fields, "reasoning_content"),
                _get(provider_fields, "reasoning"),
            ]
        )

    for candidate in candidates:
        normalized = _normalize(candidate)
        if normalized:
            return normalized
    return ""


def _build_langfuse_llm_output(
    response_text: str,
    reasoning_text: str,
) -> str | dict[str, str]:
    if not reasoning_text:
        return response_text
    return {
        "content": response_text,
        "reasoning_content": reasoning_text,
    }


def _normalize_model_config(value: object) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        normalized = []
        for item in value:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    return []


def _env_has_value(key: str) -> bool:
    value = get_explicit_env_override(key)
    if value is None:
        return False
    return bool(value.strip())


def _resolve_allowed_model_config() -> tuple[list[str], list[str]]:
    allowed_source = "default"
    if _env_has_value("LLM_ALLOWED_MODELS"):
        allowed = _normalize_model_config(
            get_explicit_env_override("LLM_ALLOWED_MODELS") or ""
        )
        allowed_source = "env"
    else:
        legacy_allowed = _normalize_model_config(get_config("llm-allowed-models", None))
        if legacy_allowed:
            allowed = legacy_allowed
            allowed_source = "legacy"
        else:
            allowed = _normalize_model_config(get_config("LLM_ALLOWED_MODELS", None))

    if _env_has_value("LLM_ALLOWED_MODEL_DISPLAY_NAMES"):
        display_names = _normalize_model_config(
            get_explicit_env_override("LLM_ALLOWED_MODEL_DISPLAY_NAMES") or ""
        )
    elif allowed_source == "legacy":
        display_names = _normalize_model_config(
            get_config("llm-allowed-model-display-names", None)
        )
    else:
        display_names = _normalize_model_config(
            get_config("LLM_ALLOWED_MODEL_DISPLAY_NAMES", None)
        )

    return allowed, display_names


def _load_and_register_model_max_output_tokens() -> dict[str, int]:
    raw_limits = get_config("LLM_MODEL_MAX_OUTPUT_TOKENS", "")
    try:
        limits = parse_llm_model_max_output_tokens(raw_limits)
    except ValueError as exc:
        _log_warning(f"Ignoring invalid LLM_MODEL_MAX_OUTPUT_TOKENS: {exc}")
        return {}
    if not limits:
        return {}

    register_model = getattr(litellm, "register_model", None)
    if not callable(register_model):
        _log_warning(
            "LiteLLM register_model is unavailable; using configured model "
            "output limits without extending LiteLLM metadata"
        )
        return limits
    try:
        register_model(
            {
                model: {"max_output_tokens": max_output_tokens}
                for model, max_output_tokens in limits.items()
            }
        )
    except Exception as exc:
        _log_warning(
            f"Registering LLM_MODEL_MAX_OUTPUT_TOKENS with LiteLLM failed: {exc}"
        )
    return limits


def _register_provider_models(
    config: ProviderConfig, raw_models: list[str | tuple[str, str]]
) -> list[str]:
    seen = set()
    display_models: list[str] = []
    for model_id in raw_models:
        actual_model = None
        if isinstance(model_id, tuple):
            model_name, actual_model = model_id
        else:
            model_name = model_id
        if not model_name:
            continue
        display = f"{config.prefix}{model_name}" if config.prefix else model_name
        if display in seen:
            continue
        seen.add(display)
        MODEL_ALIAS_MAP[display] = (config.key, actual_model or model_name)
        if actual_model and actual_model not in MODEL_ALIAS_MAP:
            MODEL_ALIAS_MAP[actual_model] = (config.key, actual_model)
        display_models.append(display)
    return display_models


def _init_litellm_provider(config: ProviderConfig) -> ProviderState:
    api_key = get_config(config.api_key_env)
    if not api_key:
        _log_warning(f"{config.api_key_env} not configured")
        return ProviderState(
            enabled=False,
            params=None,
            models=[],
            prefix=config.prefix,
            wildcard_prefixes=config.wildcard_prefixes,
        )
    base_url = None
    if config.base_url_env:
        base_url = get_config(config.base_url_env)
    if not base_url:
        base_url = config.default_base_url
    if (
        config.key == "gemini"
        and base_url
        and "generativelanguage.googleapis.com" in base_url
    ):
        base_url = None
        _log_info("Skipping GEMINI_API_URL override to use LiteLLM default endpoint")
    params: dict[str, str] = {"api_key": api_key}
    if base_url:
        params["api_base"] = base_url
    if config.custom_llm_provider:
        params["custom_llm_provider"] = config.custom_llm_provider
    if config.model_loader:
        raw_models = config.model_loader(config, params, base_url)
    else:
        raw_models: list[str | tuple[str, str]] = list(config.static_models)
        if config.fetch_models:
            try:
                fetched_models = _fetch_provider_models(api_key, base_url)
                if config.filter_fn:
                    fetched_models = [m for m in fetched_models if config.filter_fn(m)]
                raw_models.extend(fetched_models)
            except Exception as exc:
                _log_warning(f"load {config.key} models error: {exc}")
        raw_models.extend(config.extra_models)
    display_models = _register_provider_models(config, raw_models)
    if display_models:
        _log_info(f"{config.key} models: {display_models}")
    return ProviderState(
        enabled=True,
        params=params,
        models=display_models,
        prefix=config.prefix,
        wildcard_prefixes=config.wildcard_prefixes,
    )


def _build_models_url(base_url: str | None) -> str:
    base = base_url or "https://api.openai.com/v1"
    return f"{base.rstrip('/')}/models"


def _fetch_provider_models(api_key: str, base_url: str | None) -> list[str]:
    if not api_key:
        return []
    url = _build_models_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()
    return [item.get("id", "") for item in data.get("data", []) if item.get("id")]


def _is_litellm_repeated_stream_chunk_error(exc: Exception) -> bool:
    message = str(exc)
    return (
        "repeating the same chunk" in message
        and exc.__class__.__module__.startswith("litellm")
    )


def _stream_litellm_completion(
    app: Flask,
    requested_model: str,
    model: str,
    messages: list,
    params: dict,
    kwargs: dict,
) -> object:
    try:
        # Routed ids are the application-level identity. LiteLLM completion uses
        # the stripped provider model id, which can collide across routes (for
        # example, a Qwen-hosted DeepSeek model and the direct DeepSeek provider).
        max_tokens = MODEL_MAX_OUTPUT_TOKENS.get(requested_model)
        if max_tokens is None:
            try:
                max_tokens = litellm.get_max_tokens(model)
            except Exception as exc:
                _log_warning(f"get max tokens for {model} failed: {exc}")
        if max_tokens is not None:
            requested_max_tokens = kwargs.get("max_tokens")
            if (
                isinstance(requested_max_tokens, int)
                and not isinstance(requested_max_tokens, bool)
                and requested_max_tokens > 0
            ):
                kwargs["max_tokens"] = min(requested_max_tokens, max_tokens)
            else:
                kwargs["max_tokens"] = max_tokens
        app.logger.info(
            "stream_litellm_completion: %s %s %s %s", model, messages, params, kwargs
        )
        return litellm.completion(
            model=model,
            messages=messages,
            stream=True,
            **params,
            **kwargs,
        )
    except Exception as exc:
        _log_warning(f"LiteLLM completion failed for {model}: {exc}")
        raise_error_with_args(
            "server.llm.requestFailed",
            model=model,
            message=str(exc),
        )


# How many times to re-issue a streaming request whose connection died before
# the first content token arrived.
_STREAM_PRECONTENT_RETRY_ATTEMPTS = 1


def _retryable_stream_error_types() -> tuple:
    """Connection-level litellm stream errors that are safe to retry.

    Resolved lazily via getattr because tests stub the litellm module without
    an ``exceptions`` submodule. APIConnectionError covers connections that
    die before the response starts; MidStreamFallbackError is litellm's
    wrapper for an established stream dying mid-read (observed in production
    as TLS record corruption on the provider path: DECRYPTION_FAILED_OR_
    BAD_RECORD_MAC).
    """
    exceptions_mod = getattr(litellm, "exceptions", None)
    resolved = []
    for name in ("APIConnectionError", "MidStreamFallbackError"):
        exc_type = getattr(exceptions_mod, name, None)
        if isinstance(exc_type, type):
            resolved.append(exc_type)
    return tuple(resolved)


def _iter_stream_with_precontent_retry(
    app: Flask,
    requested_model: str,
    invoke_model: str,
    messages: list,
    params: dict,
    kwargs: dict,
) -> Generator[ModelResponseStream, None, None]:
    """Yield litellm stream chunks, re-issuing the request when the stream dies on a connection-level error before any content token arrived.

    The built-in openai/litellm retries only cover request setup; an
    established stream that dies mid-read (transient network corruption,
    provider LB reset) surfaces as an exception from the chunk iterator and
    kills the whole run. Re-issuing is only safe while no content has been
    seen: nothing user-visible can be duplicated. Hidden reasoning chunks are
    buffered until the attempt produces content or completes, so reasoning
    from an abandoned attempt does not leak into Langfuse. Once content
    flowed, the error is re-raised unchanged.
    """
    attempts = 0
    while True:
        response = _stream_litellm_completion(
            app,
            requested_model,
            invoke_model,
            messages,
            params,
            kwargs,
        )
        saw_content = False
        pending_reasoning_chunks = []
        try:
            for res in response:
                has_choices = bool(len(res.choices))
                has_content = bool(has_choices and res.choices[0].delta.content)
                has_reasoning = bool(
                    has_choices and _extract_reasoning_delta(res.choices[0].delta)
                )
                if has_content:
                    saw_content = True
                    yield from pending_reasoning_chunks
                    pending_reasoning_chunks.clear()
                    yield res
                elif not saw_content and has_reasoning:
                    pending_reasoning_chunks.append(res)
                else:
                    yield res
            yield from pending_reasoning_chunks
        except Exception as exc:
            attempts += 1
            retryable = _retryable_stream_error_types()
            if (
                saw_content
                or attempts > _STREAM_PRECONTENT_RETRY_ATTEMPTS
                or not retryable
                or not isinstance(exc, retryable)
            ):
                raise
            _log_warning(
                f"LLM stream for {invoke_model} failed before first content "
                f"(attempt {attempts}/{_STREAM_PRECONTENT_RETRY_ATTEMPTS + 1}); "
                f"reissuing request: {exc}"
            )
        else:
            return


def _resolve_provider_for_model(model: str) -> tuple[str | None, str]:
    alias = MODEL_ALIAS_MAP.get(model)
    if alias:
        return alias
    for provider_key, state in PROVIDER_STATES.items():
        for prefix in state.wildcard_prefixes:
            if model.startswith(prefix):
                normalized = model
                if state.prefix and model.startswith(state.prefix):
                    normalized = model.replace(state.prefix, "", 1)
                return provider_key, normalized
    return None, model


def _load_gemini_models(
    config: ProviderConfig, params: dict[str, str], base_url: str | None
) -> list[str | tuple[str, str]]:
    _ = config
    models: list[str | tuple[str, str]] = []
    api_key = params.get("api_key")
    if not api_key:
        return models

    # If a custom proxy is provided, try the generic OpenAI-compatible fetcher first.
    if base_url and "generativelanguage.googleapis.com" not in base_url:
        try:
            models.extend(_fetch_provider_models(api_key, base_url))
        except Exception as exc:
            _log_warning(f"load gemini models via custom base error: {exc}")
        else:
            return models

    # Default to Google Gemini ListModels endpoint (v1beta).
    google_base = base_url or "https://generativelanguage.googleapis.com"
    url = f"{google_base.rstrip('/')}/v1beta/models?key={api_key}"
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
        for item in data.get("models", []):
            name = item.get("name", "") or ""
            if name.startswith("models/"):
                name = name.split("/", 1)[1]
            methods = item.get("supportedGenerationMethods", []) or []
            if methods and "generateContent" not in methods:
                continue
            if name:
                models.append(name)
    except Exception as exc:
        _log_warning(f"load gemini models error: {exc}")
    return models


def _load_deepseek_models(
    config: ProviderConfig, params: dict[str, str], base_url: str | None
) -> list[str | tuple[str, str]]:
    api_key = params.get("api_key", "")
    try:
        return _fetch_provider_models(api_key, base_url)
    except Exception as exc:
        _log_warning(f"load {config.key} models error: {exc}")
        return list(DEEPSEEK_FALLBACK_MODELS)


QWEN_PREFIX = "qwen/"
ERNIE_V2_PREFIX = "ernie/"
GLM_PREFIX = "glm/"
SILICON_PREFIX = "silicon/"
GEMINI_PREFIX = ""
DEEPSEEK_FALLBACK_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
]


_REASONING_EFFORT_CAPABILITIES = (
    ("none", "supports_none_reasoning_effort"),
    ("minimal", "supports_minimal_reasoning_effort"),
    ("low", "supports_low_reasoning_effort"),
)
_THINKING_CONTROL_KEYS = ("reasoning_effort", "thinking", "enable_thinking")
_LIST_PATCH_KEYS = frozenset({"allowed_openai_params", "additional_drop_params"})
_THINKING_CONFLICT_PATHS = (
    "reasoning_effort",
    "reasoning",
    "thinking",
    "enable_thinking",
    "thinkingConfig",
    "thinking_config",
    "extra_body.reasoning_effort",
    "extra_body.reasoning",
    "extra_body.thinking",
    "extra_body.enable_thinking",
    "extra_body.thinkingConfig",
    "extra_body.thinking_config",
    "generationConfig.thinkingConfig",
    "generationConfig.thinking_config",
    "generation_config.thinkingConfig",
    "generation_config.thinking_config",
    "extra_body.generationConfig.thinkingConfig",
    "extra_body.generationConfig.thinking_config",
    "extra_body.generation_config.thinkingConfig",
    "extra_body.generation_config.thinking_config",
)

# These entries cover confirmed gaps in LiteLLM 1.98.0. The normal path is
# capability-driven; upgrading LiteLLM should make individual rows removable
# when their contract tests start passing without the row.
_ZAI_DISABLED_THINKING_PATCH: dict[str, object] = {
    # LiteLLM 1.98 sends top-level thinking to the OpenAI SDK for ZAI, where it
    # is rejected. extra_body reaches the provider wire format.
    "extra_body": {"thinking": {"type": "disabled"}},
}
_LITELLM_198_COMPATIBILITY_PATCHES: dict[tuple[str, str | None], dict[str, object]] = {
    ("qwen", None): {"extra_body": {"enable_thinking": False}},
    ("silicon", None): {"extra_body": {"enable_thinking": False}},
    ("ark", None): {"allowed_openai_params": ["response_format"]},
    ("glm", None): {"allowed_openai_params": ["response_format"]},
    ("glm", "glm-4.5"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5v"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5-air"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5-x"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5-airx"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5-flash"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.6"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.7"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.7-flash"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-5"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-5.1"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-5-code"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-5.2"): _ZAI_DISABLED_THINKING_PATCH,
    ("qwen", "zhipu/glm-5.3"): {
        "reasoning_effort": "low",
        "allowed_openai_params": ["reasoning_effort"],
        "additional_drop_params": ["enable_thinking"],
    },
    ("qwen", "zhipu/glm-5.3-flash"): {
        "reasoning_effort": "low",
        "allowed_openai_params": ["reasoning_effort"],
        "additional_drop_params": ["enable_thinking"],
    },
    ("gemini", "gemini-3.7-flash"): {"reasoning_effort": "low"},
    ("gemini", "gemini-2.5-pro"): {"reasoning_effort": "minimal"},
    ("openai", "gpt-5-pro"): {"reasoning_effort": "high"},
    ("openai", "gpt-5-pro-2025-10-06"): {"reasoning_effort": "high"},
    ("openai", "gpt-5.2-pro"): {"reasoning_effort": "medium"},
    ("openai", "gpt-5.2-pro-2025-12-11"): {"reasoning_effort": "medium"},
    ("openai", "gpt-5.4-pro"): {"reasoning_effort": "medium"},
    ("openai", "gpt-5.4-pro-2026-03-05"): {"reasoning_effort": "medium"},
    ("openai", "gpt-5.5-pro"): {"reasoning_effort": "medium"},
    ("openai", "gpt-5.5-pro-2026-04-23"): {"reasoning_effort": "medium"},
}


def _ordered_param_union(*values: object) -> list[object]:
    merged: list[object] = []
    for value in values:
        if not isinstance(value, (list, tuple)):
            continue
        for item in value:
            if item not in merged:
                merged.append(item)
    return merged


def _merge_litellm_param_patch(
    base: dict[str, object], patch: dict[str, object]
) -> dict[str, object]:
    """Shallow-merge one request patch without inventing a policy language."""
    merged = dict(base)
    for key, value in patch.items():
        if key in _LIST_PATCH_KEYS:
            merged[key] = _ordered_param_union(merged.get(key), value)
        elif key == "extra_body" and isinstance(value, dict):
            current = merged.get(key)
            merged[key] = {
                **(current if isinstance(current, dict) else {}),
                **value,
            }
        elif isinstance(value, dict):
            merged[key] = dict(value)
        elif isinstance(value, list):
            merged[key] = list(value)
        else:
            merged[key] = value
    return merged


def _litellm_provider_name(provider_key: str, provider_params: dict[str, str]) -> str:
    configured_provider = provider_params.get("custom_llm_provider")
    if configured_provider:
        return configured_provider
    for config in LITELLM_PROVIDER_CONFIGS:
        if config.key == provider_key and config.custom_llm_provider:
            return config.custom_llm_provider
    return provider_key


def _litellm_minimum_thinking_params(
    model_id: str, custom_llm_provider: str
) -> dict[str, object]:
    """Use LiteLLM's declared adapter capabilities for the product minimum."""
    try:
        supported_params = litellm.get_supported_openai_params(
            model=model_id,
            custom_llm_provider=custom_llm_provider,
        )
    except Exception as exc:
        logger.debug(
            "LiteLLM supported params unavailable for %s/%s: %s",
            custom_llm_provider,
            model_id,
            exc,
        )
        supported_params = None

    if supported_params and "reasoning_effort" in supported_params:
        try:
            model_info = litellm.get_model_info(
                model=model_id,
                custom_llm_provider=custom_llm_provider,
            )
        except Exception as exc:
            logger.debug(
                "LiteLLM model info unavailable for %s/%s: %s",
                custom_llm_provider,
                model_id,
                exc,
            )
            model_info = {}

        for effort, capability in _REASONING_EFFORT_CAPABILITIES:
            if model_info.get(capability) is True:
                return {"reasoning_effort": effort}
        if all(
            model_info.get(capability) is False
            for _effort, capability in _REASONING_EFFORT_CAPABILITIES
        ):
            return {"reasoning_effort": "medium"}
        # The adapter supports the standard parameter but the model metadata is
        # incomplete. LiteLLM maps none to each provider's native minimum.
        return {"reasoning_effort": "none"}

    if supported_params and "thinking" in supported_params:
        return {"thinking": {"type": "disabled"}}
    return {}


def _find_thinking_control(
    params: dict[str, object],
) -> tuple[str, str] | None:
    for key in _THINKING_CONTROL_KEYS:
        if key in params:
            return "root", key
    extra_body = params.get("extra_body")
    if isinstance(extra_body, dict):
        for key in _THINKING_CONTROL_KEYS:
            if key in extra_body:
                return "extra_body", key
    return None


def _keep_primary_thinking_control(
    params: dict[str, object], primary: tuple[str, str] | None
) -> dict[str, object]:
    if primary is None:
        return params
    kept = dict(params)
    for key in _THINKING_CONTROL_KEYS:
        if primary != ("root", key):
            kept.pop(key, None)
    extra_body = kept.get("extra_body")
    if isinstance(extra_body, dict):
        kept_extra_body = dict(extra_body)
        for key in _THINKING_CONTROL_KEYS:
            if primary != ("extra_body", key):
                kept_extra_body.pop(key, None)
        if kept_extra_body:
            kept["extra_body"] = kept_extra_body
        else:
            kept.pop("extra_body", None)
    return kept


def _thinking_conflict_drop_params(primary: tuple[str, str]) -> list[object]:
    if primary[0] == "root":
        protected_paths = {primary[1]}
        if primary[1] == "thinking":
            # OpenAI-compatible adapters can map standard thinking into
            # extra_body, so dropping that path would remove the policy value.
            protected_paths.add("extra_body.thinking")
    else:
        # A flat drop also removes an extra_body field with the same name.
        protected_paths = {primary[1], f"extra_body.{primary[1]}"}
    return [path for path in _THINKING_CONFLICT_PATHS if path not in protected_paths]


def _drop_path_overlaps_primary(path: object, primary: tuple[str, str]) -> bool:
    if not isinstance(path, str):
        return False
    target_path = primary[1] if primary[0] == "root" else f"extra_body.{primary[1]}"
    protected_paths = {target_path}
    if primary == ("root", "thinking"):
        protected_paths.add("extra_body.thinking")
    if primary[0] == "extra_body":
        # LiteLLM also treats the flat field name as an extra_body filter.
        protected_paths.add(primary[1])
    return any(
        path == protected
        or path.startswith(f"{protected}.")
        or protected.startswith(f"{path}.")
        for protected in protected_paths
    )


def _should_inject_default_temperature(
    provider_key: str,
    model_id: str,
    primary: tuple[str, str] | None,
    policy_params: dict[str, object],
) -> bool:
    normalized_model = model_id.casefold()
    if provider_key == "gemini" and normalized_model.startswith("gemini-3"):
        return False
    return not (
        provider_key == "openai"
        and primary == ("root", "reasoning_effort")
        and policy_params.get("reasoning_effort") != "none"
    )


def _prepare_litellm_request_kwargs(
    provider_key: str,
    model_id: str,
    provider_params: dict[str, str],
    kwargs: dict[str, object],
) -> dict[str, object]:
    """Resolve minimum thinking controls once for both invocation paths."""
    provider_key = provider_key.casefold()
    custom_llm_provider = _litellm_provider_name(provider_key, provider_params)
    stages = [
        _litellm_minimum_thinking_params(model_id, custom_llm_provider),
        _LITELLM_198_COMPATIBILITY_PATCHES.get((provider_key, None), {}),
        _LITELLM_198_COMPATIBILITY_PATCHES.get((provider_key, model_id.casefold()), {}),
    ]
    primary = None
    policy_params: dict[str, object] = {}
    for stage in stages:
        policy_params = _merge_litellm_param_patch(policy_params, stage)
        stage_control = _find_thinking_control(stage)
        if stage_control is not None:
            primary = stage_control
    policy_params = _keep_primary_thinking_control(policy_params, primary)

    prepared = dict(kwargs)
    if "temperature" in prepared:
        prepared["temperature"] = float(prepared["temperature"])
    elif _should_inject_default_temperature(
        provider_key, model_id, primary, policy_params
    ):
        prepared["temperature"] = 0.3

    if primary is not None:
        if primary == ("root", "thinking"):
            caller_extra_body = prepared.get("extra_body")
            if isinstance(caller_extra_body, dict):
                sanitized_extra_body = dict(caller_extra_body)
                sanitized_extra_body.pop("thinking", None)
                if sanitized_extra_body:
                    prepared["extra_body"] = sanitized_extra_body
                else:
                    prepared.pop("extra_body", None)
        if primary[0] == "extra_body":
            # None prevents the caller's top-level vendor field from
            # overwriting the patch when LiteLLM builds extra_body.
            prepared[primary[1]] = None
        caller_drop_params = prepared.get("additional_drop_params")
        if isinstance(caller_drop_params, (list, tuple)):
            prepared["additional_drop_params"] = [
                path
                for path in caller_drop_params
                if not _drop_path_overlaps_primary(path, primary)
            ]
        policy_params = _merge_litellm_param_patch(
            policy_params,
            {
                "additional_drop_params": _thinking_conflict_drop_params(primary),
            },
        )

    return _merge_litellm_param_patch(prepared, policy_params)


LITELLM_PROVIDER_CONFIGS: list[ProviderConfig] = [
    ProviderConfig(
        key="openai",
        api_key_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        default_base_url="https://api.openai.com/v1",
        filter_fn=lambda model_id: model_id.startswith("gpt"),
        wildcard_prefixes=("gpt",),
        config_hint="OPENAI_API_KEY,OPENAI_BASE_URL",
        custom_llm_provider="openai",
    ),
    ProviderConfig(
        key="qwen",
        api_key_env="QWEN_API_KEY",
        base_url_env="QWEN_API_URL",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        prefix=QWEN_PREFIX,
        extra_models=["deepseek-r1", "deepseek-v3"],
        wildcard_prefixes=(QWEN_PREFIX,),
        config_hint="QWEN_API_KEY,QWEN_API_URL",
        custom_llm_provider="dashscope",
    ),
    ProviderConfig(
        key="ernie_v2",
        api_key_env="ERNIE_API_KEY",
        default_base_url="https://qianfan.baidubce.com/v2",
        prefix=ERNIE_V2_PREFIX,
        config_hint="ERNIE_API_KEY",
        custom_llm_provider="openai",
    ),
    ProviderConfig(
        key="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_API_URL",
        default_base_url="https://api.deepseek.com",
        config_hint="DEEPSEEK_API_KEY,DEEPSEEK_API_URL",
        custom_llm_provider="deepseek",
        model_loader=_load_deepseek_models,
    ),
    ProviderConfig(
        key="gemini",
        api_key_env="GEMINI_API_KEY",
        base_url_env="GEMINI_API_URL",
        default_base_url=None,
        prefix=GEMINI_PREFIX,
        fetch_models=False,
        wildcard_prefixes=("gemini-",),
        config_hint="GEMINI_API_KEY,GEMINI_API_URL",
        custom_llm_provider="gemini",
        model_loader=_load_gemini_models,
    ),
    ProviderConfig(
        key="glm",
        api_key_env="BIGMODEL_API_KEY",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        prefix=GLM_PREFIX,
        config_hint="BIGMODEL_API_KEY",
        custom_llm_provider="zai",
    ),
    ProviderConfig(
        key="silicon",
        api_key_env="SILICON_API_KEY",
        default_base_url="https://api.siliconflow.cn/v1",
        prefix=SILICON_PREFIX,
        config_hint="SILICON_API_KEY,SILICON_API_URL",
        custom_llm_provider="openai",
    ),
    ProviderConfig(
        key="ark",
        api_key_env="ARK_API_KEY",
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        prefix="ark/",
        config_hint="ARK_API_KEY",
        custom_llm_provider="volcengine",
    ),
]

PROVIDER_CONFIG_HINTS: dict[str, str] = {}
for config in LITELLM_PROVIDER_CONFIGS:
    PROVIDER_STATES[config.key] = _init_litellm_provider(config)
    PROVIDER_CONFIG_HINTS[config.key] = config.config_hint or config.api_key_env

MODEL_MAX_OUTPUT_TOKENS.update(_load_and_register_model_max_output_tokens())


any_litellm_enabled = any(state.enabled for state in PROVIDER_STATES.values())
if not any_litellm_enabled:
    _log_warning("No LLM Configured")


class LLMStreamaUsage:
    """Track token usage reported by a streaming LLM response."""

    def __init__(
        self,
        prompt_tokens: object,
        completion_tokens: object,
        total_tokens: object,
    ) -> None:
        """Record token counts for an LLM stream."""
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class LLMStreamResponse:
    """Wrap an LLM stream together with response metadata."""

    def __init__(
        self,
        response_id: object,
        is_end: object,
        is_truncated: object,
        result: object,
        finish_reason: object,
        usage: object,
    ) -> None:
        """Build an LLM stream-chunk response."""
        self.id = response_id

        self.is_end = is_end
        self.is_truncated = is_truncated
        self.result = result
        self.finish_reason = finish_reason
        self.usage = LLMStreamaUsage(**usage) if usage else None


def get_litellm_params_and_model(
    model: str,
) -> tuple[
    dict[str, str] | None,
    str,
    str | None,
]:
    """Return LiteLLM params, actual model, and application provider key."""
    requested_model = model
    provider_key, invoke_model = _resolve_provider_for_model(model)
    if provider_key:
        state = PROVIDER_STATES.get(provider_key)
        params = state.params if state else None
        if not params:
            raise_error_with_args(
                "server.llm.specifiedLlmNotConfigured",
                model=requested_model,
                config_var=PROVIDER_CONFIG_HINTS.get(
                    provider_key, provider_key.upper()
                ),
            )
        return params, invoke_model, provider_key
    return None, model, None


def invoke_llm(
    app: Flask,
    user_id: str,
    span: LangfuseObservationHandle,
    model: str,
    message: str,
    system: str | None = None,
    json: bool = False,
    generation_name: str = "invoke_llm",
    usage_context: UsageContext | None = None,
    usage_scene: str | int | None = None,
    billable: int | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
    usage_metadata: dict[str, object] | None = None,
    **kwargs: object,
) -> Generator[LLMStreamResponse, None, None]:
    """Invoke LLM."""
    stream_flag = bool(kwargs.get("stream", True))
    kwargs.pop("stream", None)
    usage_scene = (
        usage_scene if usage_scene is not None else kwargs.pop("usage_scene", None)
    )
    billable = billable if billable is not None else kwargs.pop("billable", None)
    request_id = request_id or kwargs.pop("request_id", None) or get_request_id()
    trace_id = resolve_langfuse_trace_id(span, trace_id or kwargs.pop("trace_id", None))
    usage_metadata = usage_metadata or kwargs.pop("usage_metadata", None) or {}
    model = model.strip()
    generation_input = []
    if system:
        generation_input.append({"role": "system", "content": system})
    generation_input.append({"role": "user", "content": message})
    generation_link = build_langfuse_observation_link(span, trace_id)
    generation = span.generation(
        model=model,
        input=generation_input,
        name=generation_name,
        **generation_link,
    )
    app.logger.info(
        "langfuse llm generation linked | request_id=%s | trace_id=%s | parent_observation_id=%s | generation_name=%s | model=%s",
        request_id or "",
        generation_link.get("trace_id", ""),
        generation_link.get("parent_observation_id", ""),
        generation_name,
        model,
    )
    response_text = ""
    reasoning_text = ""
    usage = None
    input_cache_tokens = 0
    provider_name = ""
    start_time = time.monotonic()
    params, invoke_model, provider_key = get_litellm_params_and_model(model)
    start_completion_time = None
    if params:
        provider_name = provider_key or ""
        messages = []
        if system:
            messages.append({"content": system, "role": "system"})
        messages.append({"content": message, "role": "user"})
        if json:
            kwargs["response_format"] = {"type": "json_object"}
        kwargs["stream_options"] = {"include_usage": True}
        kwargs = _prepare_litellm_request_kwargs(
            provider_name,
            invoke_model,
            params,
            kwargs,
        )
        response = _iter_stream_with_precontent_retry(
            app,
            model,
            invoke_model,
            messages,
            params,
            kwargs,
        )

        for res in response:
            if start_completion_time is None:
                start_completion_time = now_utc()
            if len(res.choices):
                choice = res.choices[0]
                reasoning_text += _extract_reasoning_delta(choice.delta)
                content = choice.delta.content or ""
                if content:
                    response_text += content
                is_truncated = choice.finish_reason in _INCOMPLETE_FINISH_REASONS
                if content or choice.finish_reason is not None:
                    yield LLMStreamResponse(
                        res.id,
                        bool(choice.finish_reason),
                        is_truncated=is_truncated,
                        result=content,
                        finish_reason=choice.finish_reason,
                        usage=None,
                    )
            res_usage = getattr(res, "usage", None)
            if res_usage:
                input_cache_tokens = _extract_input_cache(res_usage)
                usage = {
                    "input": res_usage.prompt_tokens,
                    "output": res_usage.completion_tokens,
                    "total": res_usage.total_tokens,
                }
    else:
        raise_error_with_args(
            "server.llm.modelNotSupported",
            model=model,
        )

    app.logger.info("invoke_llm response: %s ", response_text)
    if usage is None:
        app.logger.info("invoke_llm usage: None")
    else:
        app.logger.info("invoke_llm usage: %s", usage.__str__())
    latency_ms = int((time.monotonic() - start_time) * 1000)
    resolved_usage_scene = normalize_usage_scene(usage_scene)
    if usage_context is None:
        usage_context = UsageContext(
            user_bid=user_id or "",
            request_id=request_id or "",
            trace_id=trace_id or "",
            usage_scene=resolved_usage_scene,
            billable=billable,
        )
    else:
        usage_context = replace(
            usage_context,
            request_id=request_id or usage_context.request_id,
            trace_id=trace_id or usage_context.trace_id,
            usage_scene=resolved_usage_scene,
            billable=billable if billable is not None else usage_context.billable,
        )
    usage_metadata.setdefault("generation_name", generation_name)
    if "temperature" in kwargs:
        usage_metadata.setdefault("temperature", kwargs.get("temperature"))
    usage_metadata = _attach_usage_output_text(usage_metadata, response_text)
    if usage is None:
        usage_metadata.setdefault("usage_source", "missing")
        record_llm_usage(
            app,
            usage_context,
            provider=provider_name or "",
            model=model,
            is_stream=stream_flag,
            input=0,
            input_cache=input_cache_tokens,
            output=0,
            total=0,
            latency_ms=latency_ms,
            status=0,
            error_message="",
            extra=usage_metadata,
        )
    else:
        usage_metadata.setdefault("usage_source", "litellm")
        record_llm_usage(
            app,
            usage_context,
            provider=provider_name or "",
            model=model,
            is_stream=stream_flag,
            input=_extract_usage_value(usage, "input"),
            input_cache=input_cache_tokens,
            output=_extract_usage_value(usage, "output"),
            total=_extract_usage_value(usage, "total"),
            latency_ms=latency_ms,
            status=0,
            error_message="",
            extra=usage_metadata,
        )
    generation.end(
        input=generation_input,
        output=_build_langfuse_llm_output(response_text, reasoning_text),
        usage=usage,
        metadata=kwargs,
        completion_start_time=start_completion_time,
    )
    span.update(output=response_text)


def chat_llm(
    app: Flask,
    user_id: str,
    span: LangfuseObservationHandle,
    model: str,
    messages: list,
    json: bool = False,
    generation_name: str = "user_follow_ask",
    usage_context: UsageContext | None = None,
    usage_scene: str | int | None = None,
    billable: int | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
    usage_metadata: dict[str, object] | None = None,
    **kwargs: object,
) -> Generator[LLMStreamResponse, None, None]:
    """Send a chat request through the configured LLM provider."""
    app.logger.info(
        "chat_llm [%s] %s ,json:%s ,kwargs:%s", model, messages, json, kwargs
    )
    stream_flag = bool(kwargs.get("stream", True))
    kwargs.pop("stream", None)
    usage_scene = (
        usage_scene if usage_scene is not None else kwargs.pop("usage_scene", None)
    )
    billable = billable if billable is not None else kwargs.pop("billable", None)
    request_id = request_id or kwargs.pop("request_id", None) or get_request_id()
    trace_id = resolve_langfuse_trace_id(span, trace_id or kwargs.pop("trace_id", None))
    usage_metadata = usage_metadata or kwargs.pop("usage_metadata", None) or {}
    model = model.strip()
    generation_input = messages
    generation_link = build_langfuse_observation_link(span, trace_id)
    generation = span.generation(
        model=model,
        input=generation_input,
        name=generation_name,
        **generation_link,
    )
    app.logger.info(
        "langfuse llm generation linked | request_id=%s | trace_id=%s | parent_observation_id=%s | generation_name=%s | model=%s",
        request_id or "",
        generation_link.get("trace_id", ""),
        generation_link.get("parent_observation_id", ""),
        generation_name,
        model,
    )
    response_text = ""
    reasoning_text = ""
    usage = None
    input_cache_tokens = 0
    provider_name = ""
    start_time = time.monotonic()
    start_completion_time = None
    params, invoke_model, provider_key = get_litellm_params_and_model(model)
    if params:
        provider_name = provider_key or ""
        kwargs["stream_options"] = {"include_usage": True}
        kwargs = _prepare_litellm_request_kwargs(
            provider_name,
            invoke_model,
            params,
            kwargs,
        )
        response = _iter_stream_with_precontent_retry(
            app,
            model,
            invoke_model,
            messages,
            params,
            kwargs,
        )
        try:
            for res in response:
                if start_completion_time is None:
                    start_completion_time = now_utc()
                if len(res.choices):
                    reasoning_text += _extract_reasoning_delta(res.choices[0].delta)
                if len(res.choices) and res.choices[0].delta.content:
                    response_text += res.choices[0].delta.content
                    yield LLMStreamResponse(
                        res.id,
                        bool(res.choices[0].finish_reason),
                        is_truncated=False,
                        result=res.choices[0].delta.content,
                        finish_reason=res.choices[0].finish_reason,
                        usage=None,
                    )
                res_usage = getattr(res, "usage", None)
                if res_usage:
                    input_cache_tokens = _extract_input_cache(res_usage)
                    usage = {
                        "input": res_usage.prompt_tokens,
                        "output": res_usage.completion_tokens,
                        "total": res_usage.total_tokens,
                    }
        except Exception as exc:
            if not (_is_litellm_repeated_stream_chunk_error(exc) and response_text):
                raise
            app.logger.warning(
                "LiteLLM repeated streaming chunk detected; ending stream with partial response | model=%s | response_chars=%s | error=%s",
                invoke_model,
                len(response_text),
                exc,
            )
    else:
        raise_error_with_args(
            "server.llm.modelNotSupported",
            model=model,
        )

    app.logger.info("chat_llm response: %s ", response_text)
    if usage is None:
        app.logger.info("chat_llm usage: None")
    else:
        app.logger.info("chat_llm usage: %s", usage.__str__())
    latency_ms = int((time.monotonic() - start_time) * 1000)
    resolved_usage_scene = normalize_usage_scene(usage_scene)
    if usage_context is None:
        usage_context = UsageContext(
            user_bid=user_id or "",
            request_id=request_id or "",
            trace_id=trace_id or "",
            usage_scene=resolved_usage_scene,
            billable=billable,
        )
    else:
        usage_context = replace(
            usage_context,
            request_id=request_id or usage_context.request_id,
            trace_id=trace_id or usage_context.trace_id,
            usage_scene=resolved_usage_scene,
            billable=billable if billable is not None else usage_context.billable,
        )
    usage_metadata.setdefault("generation_name", generation_name)
    if "temperature" in kwargs:
        usage_metadata.setdefault("temperature", kwargs.get("temperature"))
    usage_metadata = _attach_usage_output_text(usage_metadata, response_text)
    if usage is None:
        usage_metadata.setdefault("usage_source", "missing")
        record_llm_usage(
            app,
            usage_context,
            provider=provider_name or "",
            model=model,
            is_stream=stream_flag,
            input=0,
            input_cache=input_cache_tokens,
            output=0,
            total=0,
            latency_ms=latency_ms,
            status=0,
            error_message="",
            extra=usage_metadata,
        )
    else:
        usage_metadata.setdefault("usage_source", "litellm")
        record_llm_usage(
            app,
            usage_context,
            provider=provider_name or "",
            model=model,
            is_stream=stream_flag,
            input=_extract_usage_value(usage, "input"),
            input_cache=input_cache_tokens,
            output=_extract_usage_value(usage, "output"),
            total=_extract_usage_value(usage, "total"),
            latency_ms=latency_ms,
            status=0,
            error_message="",
            extra=usage_metadata,
        )
    generation.end(
        input=generation_input,
        output=_build_langfuse_llm_output(response_text, reasoning_text),
        usage=usage,
        metadata=kwargs,
        completion_start_time=start_completion_time,
    )


def _build_model_options(
    app: Flask, available_models: list[str]
) -> list[dict[str, object]]:
    allowed, display_names = _resolve_allowed_model_config()

    if not allowed:
        return _attach_credit_multipliers(
            app,
            [{"model": model, "display_name": model} for model in available_models],
        )

    available_set = set(available_models)
    filtered_models: list[str] = []
    for model in allowed:
        if model in available_set and model not in filtered_models:
            filtered_models.append(model)

    if not filtered_models:
        _log_warning(
            "LLM_RECOMMENDED_MODELS configured but no matching models are available"
        )
        return []

    display_names_enabled = allowed and len(display_names) == len(allowed)
    if display_names and not display_names_enabled:
        _log_warning(
            "LLM_ALLOWED_MODEL_DISPLAY_NAMES ignored: length must match "
            "LLM_ALLOWED_MODELS"
        )
    display_map: dict[str, str] = (
        dict(zip(allowed, display_names, strict=False)) if display_names_enabled else {}
    )

    options = [
        {
            "model": model,
            "display_name": display_map.get(model, model),
        }
        for model in filtered_models
    ]
    return _attach_credit_multipliers(app, options)


def _resolve_billing_rate_identity(model: str) -> tuple[str, list[str]]:
    provider, actual_model = _resolve_provider_for_model(model)
    candidates: list[str] = []
    for candidate in (actual_model, model):
        normalized = str(candidate or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return provider or "", candidates


def _rate_per_token(rate: CreditUsageRate | None) -> Decimal | None:
    if rate is None:
        return None
    try:
        unit_size = max(int(rate.unit_size or 1), 1)
        return Decimal(str(rate.credits_per_unit or 0)) / Decimal(str(unit_size))
    except (InvalidOperation, ValueError, TypeError, ZeroDivisionError):
        return None


def _select_credit_usage_rate(
    rows: list[CreditUsageRate],
    *,
    provider: str,
    model_candidates: list[str],
    now: datetime,
) -> CreditUsageRate | None:
    normalized_provider = str(provider or "").strip()
    normalized_models = [
        str(model or "").strip() for model in model_candidates if model
    ]
    if not normalized_models:
        return None
    candidate_set = set(normalized_models)
    model_priority = {
        model: len(normalized_models) - index
        for index, model in enumerate(normalized_models)
    }
    candidates = [
        row
        for row in rows
        if row.effective_from <= now
        and (row.effective_to is None or row.effective_to > now)
        and row.provider in {normalized_provider, "*"}
        and row.model in candidate_set.union({"*"})
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            row.provider == normalized_provider,
            row.model in candidate_set,
            model_priority.get(row.model, 0),
            row.effective_from or NAIVE_DATETIME_MIN,
            int(row.id or 0),
        ),
        reverse=True,
    )
    return candidates[0]


def _load_llm_output_rate_rows(app: Flask) -> list[CreditUsageRate]:
    with app.app_context():
        return (
            CreditUsageRate.query.filter(
                CreditUsageRate.deleted == 0,
                CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
                CreditUsageRate.usage_type == BILL_USAGE_TYPE_LLM,
                CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
                CreditUsageRate.billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS,
            )
            .order_by(CreditUsageRate.effective_from.desc(), CreditUsageRate.id.desc())
            .all()
        )


def _attach_credit_multipliers(
    app: Flask, options: list[dict[str, object]]
) -> list[dict[str, object]]:
    default_model = str(get_config("DEFAULT_LLM_MODEL", "") or "").strip()
    if not options:
        return [{**option, "credit_multiplier": None} for option in options]

    try:
        rows = _load_llm_output_rate_rows(app)
        now = now_utc()
        default_rate = load_llm_credit_1x_unit_cost()
        if default_rate is None or default_rate <= 0:
            return [{**option, "credit_multiplier": None} for option in options]

        enriched: list[dict[str, Any]] = []
        for option in options:
            model = str(option.get("model") or "").strip()
            provider, model_candidates = _resolve_billing_rate_identity(model)
            model_rate = _rate_per_token(
                _select_credit_usage_rate(
                    rows,
                    provider=provider,
                    model_candidates=model_candidates,
                    now=now,
                )
            )
            multiplier = None
            multiplier_label = None
            if model_rate is not None and model_rate > 0:
                multiplier_value = model_rate / default_rate
                multiplier = int(
                    multiplier_value.to_integral_value(rounding=ROUND_CEILING)
                )
                multiplier_label = format_credit_multiplier(multiplier_value)
            enriched.append(
                {
                    **option,
                    "credit_multiplier": multiplier,
                    "credit_multiplier_label": multiplier_label,
                    "is_default": model == default_model,
                }
            )
    except Exception as exc:
        _log_warning(f"load LLM credit multipliers error: {exc}")
        return [{**option, "credit_multiplier": None} for option in options]
    else:
        return enriched


def get_current_models(app: Flask) -> list[dict[str, object]]:
    """Return current models."""
    litellm_models: list[str] = []
    for state in PROVIDER_STATES.values():
        litellm_models.extend(state.models)
    available_models = list(dict.fromkeys(litellm_models))
    return _build_model_options(app, available_models)


def get_allowed_models() -> list[str]:
    """Return allowed models."""
    allowed, _ = _resolve_allowed_model_config()
    return allowed
