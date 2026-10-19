"""LLM invocation wrappers built on LiteLLM."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from dataclasses import replace
from typing import TYPE_CHECKING

import requests

# litellm fetches its model cost map from GitHub at import time by default,
# which stalls every worker boot (and times out entirely on hosts without
# outbound internet). Default to the bundled local map; deployments can still
# override by exporting LITELLM_LOCAL_MODEL_COST_MAP=False before startup.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm
from flask import Flask, current_app

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from datetime import datetime

    from litellm.types.utils import ModelResponseStream

from flaskr.api.langfuse import (
    LangfuseObservationHandle,
    build_langfuse_observation_link,
    get_request_id,
    normalize_langfuse_output_value,  # noqa: F401  # re-exported public API
    resolve_langfuse_trace_id,
)
from flaskr.api.llm.model_selection import resolve_selection
from flaskr.api.llm.payloads import (
    LLMStreamaUsage,  # noqa: F401  # re-exported public API
    LLMStreamResponse,
    _attach_usage_output_text,
    _build_langfuse_llm_output,
    _extract_input_cache,
    _extract_reasoning_delta,
    _extract_tool_call_deltas,
    _extract_usage_value,
    _reported_input_cache,
)
from flaskr.api.llm.providers import (
    DEEPSEEK_FALLBACK_MODELS,
    ERNIE_V2_PREFIX,
    GEMINI_PREFIX,
    GLM_PREFIX,
    QWEN_PREFIX,
    SILICON_PREFIX,
    ProviderConfig,
    ProviderState,
    _build_models_url,
)
from flaskr.api.llm.request_params import (
    _LITELLM_1102_COMPATIBILITY_PATCHES,
    _drop_path_overlaps_primary,
    _find_thinking_control,
    _keep_primary_thinking_control,
    _litellm_minimum_thinking_params,
    _merge_litellm_param_patch,
    _should_inject_default_temperature,
    _thinking_conflict_drop_params,
)
from flaskr.api.llm.stream_retry import (
    _STREAM_PRECONTENT_RETRY_ATTEMPTS,
    _check_stream_cancelled,
    _is_litellm_repeated_stream_chunk_error,
    _is_rate_limit_error,
    _retryable_stream_error_types,
    _wait_before_retry,
)
from flaskr.common.config import (
    parse_llm_model_max_output_tokens,
)
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_OUTPUT_TOKENS,  # noqa: F401  # re-exported public API
    CREDIT_USAGE_RATE_STATUS_ACTIVE,  # noqa: F401  # re-exported public API
)
from flaskr.service.billing.models import (
    CreditUsageRate,  # noqa: F401  # re-exported public API
)
from flaskr.service.billing.rate_references import (
    format_credit_multiplier,  # noqa: F401  # re-exported public API
)
from flaskr.service.common.credit_rate_references import (
    load_llm_credit_1x_unit_cost,  # noqa: F401  # re-exported public API
)
from flaskr.service.common.models import (
    ERROR_CODE,  # noqa: F401  # re-exported public API
    AppError,  # noqa: F401  # re-exported public API
    raise_error_with_args,
)
from flaskr.service.config import get_config
from flaskr.service.metering import UsageContext, record_llm_usage
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,  # noqa: F401  # re-exported public API
    BILL_USAGE_TYPE_LLM,  # noqa: F401  # re-exported public API
    normalize_usage_scene,
)
from flaskr.util.datetime import (
    NAIVE_DATETIME_MIN,  # noqa: F401  # re-exported public API
    now_utc,
)

from .live_catalog import (
    GEMINI_LIVE_MODEL_ALLOWLIST,  # noqa: F401  # re-exported public API
    get_gemini_live_voice_options,  # noqa: F401  # re-exported public API
    is_gemini_live_enabled,  # noqa: F401  # re-exported public API
    is_live_follow_up_model,  # noqa: F401  # re-exported public API
)

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


MODEL_ALIAS_MAP: dict[str, tuple[str, str]] = {}
PROVIDER_STATES: dict[str, ProviderState] = {}
MODEL_MAX_OUTPUT_TOKENS: dict[str, int] = {}
MODEL_SUPPORTED_GENERATION_METHODS: dict[str, frozenset[str]] = {}
_GEMINI_CAPABILITY_DISCOVERED_MODELS: set[str] = set()
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


def _load_and_register_model_max_output_tokens() -> dict[str, int]:
    raw_limits = get_config("LLM_MODEL_MAX_OUTPUT_TOKENS", "")
    try:
        limits = parse_llm_model_max_output_tokens(raw_limits)
    except ValueError as exc:
        _log_warning(f"Ignoring invalid LLM_MODEL_MAX_OUTPUT_TOKENS: {exc}")
        limits = {}

    model_metadata = {
        model: {"max_output_tokens": max_output_tokens}
        for model, max_output_tokens in limits.items()
    }
    # LiteLLM 1.102.0 lacks exact GPT-6 Sol/Luna catalogue entries. Register
    # their no-reasoning capability together with any configured output limit
    # so catalogue reloads preserve both and temperature remains supported.
    for model in ("gpt-6-sol", "gpt-6-luna"):
        model_metadata[model] = {
            **model_metadata.get(model, {}),
            "litellm_provider": "openai",
            "supports_none_reasoning_effort": True,
        }

    register_model = getattr(litellm, "register_model", None)
    if not callable(register_model):
        _log_warning(
            "LiteLLM register_model is unavailable; using configured model "
            "output limits without extending LiteLLM metadata"
        )
        return limits
    try:
        register_model(model_metadata)
    except Exception as exc:
        _log_warning(f"Registering LiteLLM model metadata failed: {exc}")
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


def _get_llm_max_output_tokens(requested_model: str, invoke_model: str) -> int | None:
    """Return a known output ceiling; missing metadata does not imply unavailability."""
    # Routed ids distinguish providers that expose the same upstream model id.
    configured = MODEL_MAX_OUTPUT_TOKENS.get(requested_model)
    if configured is not None:
        return configured
    try:
        limit = litellm.get_max_tokens(invoke_model)
    except Exception as exc:
        _log_warning(f"get max tokens for {invoke_model} failed: {exc}")
        return None
    # Partial catalogue entries can contain null, zero or malformed limits.
    if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
        return limit
    return None


def _stream_litellm_completion(
    app: Flask,
    requested_model: str,
    model: str,
    messages: list,
    params: dict,
    kwargs: dict,
) -> object:
    _apply_llm_max_output_tokens(requested_model, model, kwargs)
    try:
        app.logger.info(
            "stream_litellm_completion: model=%s | message_count=%s",
            model,
            len(messages),
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
        if _is_rate_limit_error(exc):
            raise
        raise_error_with_args(
            "server.llm.requestFailed",
            model=model,
            message=str(exc),
        )


_STREAM_RATE_LIMIT_RETRY_DELAYS = (15.0, 45.0)


def _rate_limit_retry_delay(exc: Exception, attempt: int) -> float:
    """Honor a bounded provider delay, or wait across the current TPM window."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = headers.get("retry-after") if headers is not None else None
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            pass
        else:
            if 0 < delay <= 60:
                return delay
    return _STREAM_RATE_LIMIT_RETRY_DELAYS[attempt - 1] + secrets.randbelow(6)


def _iter_stream_with_precontent_retry(
    app: Flask,
    requested_model: str,
    invoke_model: str,
    messages: list,
    params: dict,
    kwargs: dict,
    *,
    tool_calls_are_output: bool = False,
    retry_cancelled: Callable[[], bool] | None = None,
) -> Generator[ModelResponseStream, None, None]:
    """Yield stream chunks, retrying transient failures before any output arrives.

    The built-in openai/litellm retries only cover request setup; an
    established stream that dies mid-read (transient network corruption,
    provider LB reset) surfaces as an exception from the chunk iterator and
    kills the whole run. Re-issuing is only safe while no content has been
    seen: nothing user-visible can be duplicated. Hidden reasoning chunks are
    buffered until the attempt produces content or completes, so reasoning
    from an abandoned attempt does not leak into Langfuse. Once content
    flowed, the error is re-raised unchanged. Provider 429 responses may require
    waiting for a TPM window, so they use a separate bounded delay schedule.

    `tool_calls_are_output` extends "content" to tool-call fragments. A caller reading those
    (`chat_llm(..., emit_tool_calls=True)`) has already been handed them, so replaying the request
    would deliver the same arguments twice and could run one tool call as two.
    """
    connection_attempts = 0
    rate_limit_attempts = 0
    while True:
        saw_content = False
        pending_reasoning_chunks = []
        response = None
        _check_stream_cancelled(retry_cancelled)
        try:
            response = _stream_litellm_completion(
                app,
                requested_model,
                invoke_model,
                messages,
                params,
                kwargs,
            )
            for res in response:
                has_choices = bool(len(res.choices))
                has_content = bool(has_choices and res.choices[0].delta.content)
                if tool_calls_are_output and has_choices and not has_content:
                    has_content = bool(_extract_tool_call_deltas(res.choices[0].delta))
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
            if _is_rate_limit_error(exc):
                rate_limit_attempts += 1
                if not saw_content and rate_limit_attempts <= len(
                    _STREAM_RATE_LIMIT_RETRY_DELAYS
                ):
                    delay = _rate_limit_retry_delay(exc, rate_limit_attempts)
                    app.logger.warning(
                        "LLM provider rate limited %s before output; retrying in %.1fs (%s/%s)",
                        invoke_model,
                        delay,
                        rate_limit_attempts,
                        len(_STREAM_RATE_LIMIT_RETRY_DELAYS),
                    )
                    _wait_before_retry(delay, retry_cancelled)
                    continue
                app.logger.exception(
                    "LLM provider rate limit stopped stream: model=%s attempts=%s output_started=%s",
                    invoke_model,
                    rate_limit_attempts,
                    saw_content,
                )
                raise_error_with_args(
                    "server.llm.requestFailed",
                    model=invoke_model,
                    message=str(exc),
                )
            connection_attempts += 1
            retryable = _retryable_stream_error_types()
            if (
                saw_content
                or connection_attempts > _STREAM_PRECONTENT_RETRY_ATTEMPTS
                or not retryable
                or not isinstance(exc, retryable)
            ):
                raise
            _log_warning(
                f"LLM stream for {invoke_model} failed before first content "
                f"(attempt {connection_attempts}/{_STREAM_PRECONTENT_RETRY_ATTEMPTS + 1}); "
                f"reissuing request: {exc}"
            )
        else:
            return
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()


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
    for discovered_model in _GEMINI_CAPABILITY_DISCOVERED_MODELS:
        MODEL_SUPPORTED_GENERATION_METHODS.pop(discovered_model, None)
    _GEMINI_CAPABILITY_DISCOVERED_MODELS.clear()

    # If a custom proxy is provided, try the generic OpenAI-compatible fetcher first.
    if base_url and "generativelanguage.googleapis.com" not in base_url:
        try:
            models.extend(_fetch_provider_models(api_key, base_url))
        except Exception:
            # Provider exceptions may contain a request URL with the API key.
            _log_warning("load gemini models via custom base failed")
        else:
            # A transparent Gemini proxy can return a successful native
            # ListModels envelope, which has no OpenAI `data[].id` entries.
            # Continue through native discovery to retain Bidi capabilities.
            if models:
                return models

    # Default to Google Gemini ListModels endpoint (v1beta).
    google_base = (
        (base_url or "https://generativelanguage.googleapis.com").strip().rstrip("/")
    )
    versioned_base = (
        google_base if google_base.endswith("/v1beta") else f"{google_base}/v1beta"
    )
    url = f"{versioned_base}/models"
    try:
        page_token = ""
        seen_page_tokens: set[str] = set()
        for _page_index in range(10):
            query_params = {"key": api_key, "pageSize": 1000}
            if page_token:
                query_params["pageToken"] = page_token
            response = requests.get(url, params=query_params, timeout=20)
            response.raise_for_status()
            data = response.json()
            for item in data.get("models", []):
                name = item.get("name", "") or ""
                if name.startswith("models/"):
                    name = name.split("/", 1)[1]
                methods = frozenset(
                    str(method).strip()
                    for method in (item.get("supportedGenerationMethods", []) or [])
                    if str(method).strip()
                )
                if methods and not methods.intersection(
                    {"generateContent", "bidiGenerateContent"}
                ):
                    continue
                if name:
                    MODEL_SUPPORTED_GENERATION_METHODS[name] = methods
                    _GEMINI_CAPABILITY_DISCOVERED_MODELS.add(name)
                    if name not in models:
                        models.append(name)
            next_page_token = data.get("nextPageToken")
            if not isinstance(next_page_token, str) or not next_page_token:
                break
            if next_page_token in seen_page_tokens:
                _log_warning("load gemini models stopped on repeated page token")
                break
            seen_page_tokens.add(next_page_token)
            page_token = next_page_token
        else:
            _log_warning("load gemini models stopped at the page limit")
    except Exception:
        # Never attach the exception: requests errors can include query params.
        _log_warning("load gemini models failed")
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


def _litellm_provider_name(provider_key: str, provider_params: dict[str, str]) -> str:
    configured_provider = provider_params.get("custom_llm_provider")
    if configured_provider:
        return configured_provider
    for config in LITELLM_PROVIDER_CONFIGS:
        if config.key == provider_key and config.custom_llm_provider:
            return config.custom_llm_provider
    return provider_key


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
        _LITELLM_1102_COMPATIBILITY_PATCHES.get((provider_key, None), {}),
        _LITELLM_1102_COMPATIBILITY_PATCHES.get(
            (provider_key, model_id.casefold()), {}
        ),
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
    if provider_key == "openai" and model_id.casefold() == "gpt-6-astra":
        # Astra's minimum reasoning level is low, which rejects temperature.
        prepared.pop("temperature", None)
    elif "temperature" in prepared:
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


def _start_llm_generation(
    app: Flask,
    span: LangfuseObservationHandle,
    *,
    model: str,
    generation_input: list,
    generation_name: str,
    usage_metadata: dict[str, object],
    request_id: str | None,
    trace_id: str | None,
) -> object:
    """Open the Langfuse generation for one LLM call and log its trace link."""
    generation_link = build_langfuse_observation_link(span, trace_id)
    generation = span.generation(
        model=model,
        input=generation_input,
        name=generation_name,
        metadata={
            key: value
            for key, value in usage_metadata.items()
            if key.startswith("model_") or key == "resolved_model"
        },
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
    return generation


def _resolve_llm_usage_context(
    usage_context: UsageContext | None,
    *,
    user_id: str,
    request_id: str | None,
    trace_id: str | None,
    usage_scene: str | int | None,
    billable: int | None,
) -> UsageContext:
    """Build or refresh the metering context for one LLM call."""
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
    return usage_context


def _record_llm_call_usage(
    app: Flask,
    usage_context: UsageContext,
    usage_metadata: dict[str, object],
    *,
    usage: dict[str, object] | None,
    provider_name: str,
    model: str,
    stream_flag: bool,
    input_cache_tokens: int,
    latency_ms: int,
    status: int,
    error_message: str,
) -> None:
    """Persist LLM usage, marking whether token counts came from LiteLLM."""
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
            status=status,
            error_message=error_message,
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
            status=status,
            error_message=error_message,
            extra=usage_metadata,
        )


def _finalize_invoke_llm(
    app: Flask,
    span: LangfuseObservationHandle,
    generation: object,
    *,
    generation_input: list,
    generation_name: str,
    usage_context: UsageContext | None,
    usage_metadata: dict[str, object],
    kwargs: dict[str, object],
    user_id: str,
    request_id: str | None,
    trace_id: str | None,
    usage_scene: str | int | None,
    billable: int | None,
    model: str,
    provider_name: str,
    stream_flag: bool,
    response_text: str,
    reasoning_text: str,
    usage: dict[str, object] | None,
    input_cache_tokens: int,
    start_time: float,
    start_completion_time: datetime | None,
) -> None:
    """Record usage and close the Langfuse generation after a completed stream."""
    app.logger.info("invoke_llm response_chars=%s", len(response_text))
    if usage is None:
        app.logger.info("invoke_llm usage: None")
    else:
        app.logger.info("invoke_llm usage: %s", usage.__str__())
    latency_ms = int((time.monotonic() - start_time) * 1000)
    usage_context = _resolve_llm_usage_context(
        usage_context,
        user_id=user_id,
        request_id=request_id,
        trace_id=trace_id,
        usage_scene=usage_scene,
        billable=billable,
    )
    usage_metadata.setdefault("generation_name", generation_name)
    if "temperature" in kwargs:
        usage_metadata.setdefault("temperature", kwargs.get("temperature"))
    usage_metadata = _attach_usage_output_text(usage_metadata, response_text)
    _record_llm_call_usage(
        app,
        usage_context,
        usage_metadata,
        usage=usage,
        provider_name=provider_name,
        model=model,
        stream_flag=stream_flag,
        input_cache_tokens=input_cache_tokens,
        latency_ms=latency_ms,
        status=0,
        error_message="",
    )
    generation.end(
        input=generation_input,
        output=_build_langfuse_llm_output(response_text, reasoning_text),
        usage=usage,
        metadata={
            **kwargs,
            **{
                key: value
                for key, value in usage_metadata.items()
                if key.startswith("model_") or key == "resolved_model"
            },
        },
        completion_start_time=start_completion_time,
    )
    span.update(output=response_text)


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
    model, usage_metadata = resolve_selection(model, usage_metadata)
    generation_input = []
    if system:
        generation_input.append({"role": "system", "content": system})
    generation_input.append({"role": "user", "content": message})
    generation = _start_llm_generation(
        app,
        span,
        model=model,
        generation_input=generation_input,
        generation_name=generation_name,
        usage_metadata=usage_metadata,
        request_id=request_id,
        trace_id=trace_id,
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

    _finalize_invoke_llm(
        app,
        span,
        generation,
        generation_input=generation_input,
        generation_name=generation_name,
        usage_context=usage_context,
        usage_metadata=usage_metadata,
        kwargs=kwargs,
        user_id=user_id,
        request_id=request_id,
        trace_id=trace_id,
        usage_scene=usage_scene,
        billable=billable,
        model=model,
        provider_name=provider_name,
        stream_flag=stream_flag,
        response_text=response_text,
        reasoning_text=reasoning_text,
        usage=usage,
        input_cache_tokens=input_cache_tokens,
        start_time=start_time,
        start_completion_time=start_completion_time,
    )


def _chat_llm_chunk_responses(
    res: ModelResponseStream,
    *,
    content: str | None,
    tool_deltas: list[dict],
    finish_reason: str | None,
    res_usage: object,
    emit_tool_calls: bool,
) -> Generator[LLMStreamResponse, None, None]:
    """Yield the caller-visible responses for one chat stream chunk."""
    # Without emit_tool_calls this is exactly the old condition: text chunks only.
    if content or tool_deltas or (emit_tool_calls and finish_reason):
        yield LLMStreamResponse(
            res.id,
            bool(finish_reason),
            is_truncated=False,
            result=content or "",
            finish_reason=finish_reason,
            usage=None,
            tool_call_deltas=tool_deltas,
        )
    if res_usage and emit_tool_calls:
        # Token counts only arrive on the final frame, which carries no text and
        # would otherwise be dropped. It trails the chunk that reported the finish
        # reason, so it must not claim to be the end as well: a caller that stops
        # at the first `is_end` would then never see the usage it is waiting for.
        yield LLMStreamResponse(
            res.id,
            is_end=False,
            is_truncated=False,
            result="",
            finish_reason=finish_reason,
            usage={
                "prompt_tokens": res_usage.prompt_tokens,
                "completion_tokens": res_usage.completion_tokens,
                "total_tokens": res_usage.total_tokens,
                "input_cache": _reported_input_cache(res_usage),
            },
        )


def _finalize_chat_llm(
    app: Flask,
    generation: object,
    *,
    generation_input: list,
    generation_name: str,
    usage_context: UsageContext | None,
    usage_metadata: dict[str, object],
    kwargs: dict[str, object],
    user_id: str,
    request_id: str | None,
    trace_id: str | None,
    usage_scene: str | int | None,
    billable: int | None,
    model: str,
    provider_name: str,
    stream_flag: bool,
    response_text: str,
    reasoning_text: str,
    tool_call_text: str,
    usage: dict[str, object] | None,
    input_cache_tokens: int,
    start_time: float,
    start_completion_time: datetime | None,
    status: int,
    error_message: str,
) -> None:
    """Record chat usage and close the Langfuse generation, even after failures."""
    app.logger.info("chat_llm response_chars=%s", len(response_text))
    if usage is None:
        app.logger.info("chat_llm usage: None")
    else:
        app.logger.info("chat_llm usage: %s", usage.__str__())
    latency_ms = int((time.monotonic() - start_time) * 1000)
    usage_context = _resolve_llm_usage_context(
        usage_context,
        user_id=user_id,
        request_id=request_id,
        trace_id=trace_id,
        usage_scene=usage_scene,
        billable=billable,
    )
    usage_metadata.setdefault("generation_name", generation_name)
    if "temperature" in kwargs:
        usage_metadata.setdefault("temperature", kwargs.get("temperature"))
    usage_metadata = _attach_usage_output_text(
        usage_metadata, response_text + tool_call_text
    )
    try:
        _record_llm_call_usage(
            app,
            usage_context,
            usage_metadata,
            usage=usage,
            provider_name=provider_name,
            model=model,
            stream_flag=stream_flag,
            input_cache_tokens=input_cache_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
        )
    finally:
        generation.end(
            input=generation_input,
            output=_build_langfuse_llm_output(
                response_text + tool_call_text, reasoning_text
            ),
            usage=usage,
            metadata={
                **kwargs,
                **({"status": status, "error_type": error_message} if status else {}),
                **{
                    key: value
                    for key, value in usage_metadata.items()
                    if key.startswith("model_") or key == "resolved_model"
                },
            },
            completion_start_time=start_completion_time,
        )


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
        "chat_llm: model=%s | message_count=%s | json=%s",
        model,
        len(messages),
        json,
    )
    stream_flag = bool(kwargs.get("stream", True))
    kwargs.pop("stream", None)
    # Off by default: the 1.0 runtime only reads text, and a tool-call-only chunk carries none.
    emit_tool_calls = bool(kwargs.pop("emit_tool_calls", False))
    retry_cancelled = kwargs.pop("retry_cancelled", None)
    usage_scene = (
        usage_scene if usage_scene is not None else kwargs.pop("usage_scene", None)
    )
    billable = billable if billable is not None else kwargs.pop("billable", None)
    request_id = request_id or kwargs.pop("request_id", None) or get_request_id()
    trace_id = resolve_langfuse_trace_id(span, trace_id or kwargs.pop("trace_id", None))
    usage_metadata = usage_metadata or kwargs.pop("usage_metadata", None) or {}
    model, usage_metadata = resolve_selection(model, usage_metadata)
    generation_input = messages
    generation = _start_llm_generation(
        app,
        span,
        model=model,
        generation_input=generation_input,
        generation_name=generation_name,
        usage_metadata=usage_metadata,
        request_id=request_id,
        trace_id=trace_id,
    )
    response_text = ""
    reasoning_text = ""
    tool_call_text = ""
    usage = None
    input_cache_tokens = 0
    provider_name = ""
    start_time = time.monotonic()
    start_completion_time = None
    status = 0
    error_message = ""
    response = None
    try:
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
                tool_calls_are_output=emit_tool_calls,
                retry_cancelled=retry_cancelled,
            )
            try:
                for res in response:
                    if start_completion_time is None:
                        start_completion_time = now_utc()
                    choice = res.choices[0] if len(res.choices) else None
                    if choice is not None:
                        reasoning_text += _extract_reasoning_delta(choice.delta)
                    content = choice.delta.content if choice is not None else None
                    tool_deltas = (
                        _extract_tool_call_deltas(choice.delta)
                        if (emit_tool_calls and choice is not None)
                        else []
                    )
                    finish_reason = choice.finish_reason if choice is not None else None
                    if content:
                        response_text += content
                    if tool_deltas:
                        tool_call_text += "".join(
                            (d.get("name") or "") + (d.get("arguments") or "")
                            for d in tool_deltas
                        )
                    res_usage = getattr(res, "usage", None)
                    if res_usage:
                        input_cache_tokens = _extract_input_cache(res_usage)
                        usage = {
                            "input": res_usage.prompt_tokens,
                            "output": res_usage.completion_tokens,
                            "total": res_usage.total_tokens,
                        }
                    yield from _chat_llm_chunk_responses(
                        res,
                        content=content,
                        tool_deltas=tool_deltas,
                        finish_reason=finish_reason,
                        res_usage=res_usage,
                        emit_tool_calls=emit_tool_calls,
                    )
                _check_stream_cancelled(retry_cancelled)
            except Exception as exc:
                # A tool-calling turn can be entirely tool calls, so text alone is the wrong test for
                # "something already reached the caller".
                partial = response_text or (tool_call_text if emit_tool_calls else "")
                if not (_is_litellm_repeated_stream_chunk_error(exc) and partial):
                    raise
                app.logger.warning(
                    "LiteLLM repeated streaming chunk detected; ending stream with partial response | model=%s | response_chars=%s | tool_call_chars=%s | error=%s",
                    invoke_model,
                    len(response_text),
                    len(tool_call_text),
                    exc,
                )
        else:
            raise_error_with_args(
                "server.llm.modelNotSupported",
                model=model,
            )

    except BaseException as exc:
        # Generator closure and cancellation must finalize paid requests too.
        status = 1
        error_message = type(exc).__name__
        raise
    finally:
        close = getattr(response, "close", None)
        if close is not None:
            close()
        _finalize_chat_llm(
            app,
            generation,
            generation_input=generation_input,
            generation_name=generation_name,
            usage_context=usage_context,
            usage_metadata=usage_metadata,
            kwargs=kwargs,
            user_id=user_id,
            request_id=request_id,
            trace_id=trace_id,
            usage_scene=usage_scene,
            billable=billable,
            model=model,
            provider_name=provider_name,
            stream_flag=stream_flag,
            response_text=response_text,
            reasoning_text=reasoning_text,
            tool_call_text=tool_call_text,
            usage=usage,
            input_cache_tokens=input_cache_tokens,
            start_time=start_time,
            start_completion_time=start_completion_time,
            status=status,
            error_message=error_message,
        )


def count_llm_chat_input_tokens(
    model: str,
    messages: list[dict[str, object]],
    *,
    tools: list[dict[str, object]] | None = None,
) -> int:
    """Count one gateway chat request with the configured model tokenizer."""
    _params, invoke_model, _provider_key = get_litellm_params_and_model(model)
    count = litellm.token_counter(
        model=invoke_model,
        messages=messages,
        tools=tools or None,
    )
    normalized = int(count or 0)
    if normalized <= 0:
        raise_error_with_args("server.llm.modelNotSupported", model=model)
    return normalized


def resolve_llm_max_output_tokens(model: str, requested: object = None) -> int | None:
    """Validate a gateway budget before shared provider parameter preparation."""
    params, invoke_model, _provider_key = get_litellm_params_and_model(model)
    if not params:
        raise_error_with_args("server.llm.modelNotSupported", model=model)
    resolved = _resolve_llm_max_output_tokens(model, invoke_model, requested)
    if requested is not None and resolved is not None and requested > resolved:
        raise_error_with_args(
            "server.llm.requestFailed",
            model=model,
            message=f"max_tokens exceeds model limit {resolved}",
        )
    return resolved


def _resolve_llm_max_output_tokens(
    model: str, invoke_model: str, requested: object
) -> int | None:
    """Fit a valid task budget to the optional model output ceiling."""
    if requested is None:
        return _get_llm_max_output_tokens(model, invoke_model)
    if not isinstance(requested, int) or isinstance(requested, bool) or requested <= 0:
        raise_error_with_args(
            "server.llm.requestFailed", model=model, message="max_tokens"
        )
    configured = _get_llm_max_output_tokens(model, invoke_model)
    return min(requested, configured) if configured is not None else requested


def _apply_llm_max_output_tokens(
    model: str, invoke_model: str, kwargs: dict[str, object]
) -> None:
    resolved = _resolve_llm_max_output_tokens(
        model, invoke_model, kwargs.get("max_tokens")
    )
    if resolved is None:
        kwargs.pop("max_tokens", None)
    else:
        kwargs["max_tokens"] = resolved


# Gateway and catalog code lives in sibling modules and looks package-level
# names up through this module at call time. Import them after every name above
# is bound so `flaskr.api.llm.<name>` stays the single patchable surface.
from flaskr.api.llm.catalog import (  # noqa: E402, F401  # re-exported after package globals exist
    _attach_credit_multipliers,
    _build_model_options,
    _load_llm_output_rate_rows,
    _resolve_billing_rate_identity,
    get_course_model_options,
    get_current_models,
    get_follow_up_models,
    get_legacy_course_model_options,
    is_live_follow_up_model_available,
)
from flaskr.api.llm.gateway import (  # noqa: E402, F401  # re-exported after package globals exist
    _record_gateway_llm_usage,
    complete_openai_chat_completion,
    stream_openai_chat_completion,
)
