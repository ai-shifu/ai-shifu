import asyncio
import os
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union
from datetime import datetime
import logging
import requests
import litellm
from flask import Flask, current_app, request
from langfuse.client import StatefulSpanClient
from langfuse.model import ModelUsage

from .dify import DifyChunkChatCompletionResponse, dify_chat_message
from flaskr.service.config import get_config
from flaskr.service.common.models import raise_error_with_args
from flaskr.service.metering import UsageContext, record_llm_usage
from flaskr.service.metering.consts import normalize_usage_scene
from litellm import get_max_tokens

logger = logging.getLogger(__name__)

# Global asyncio.run patch to avoid RuntimeError when called from a running
# event loop (seen in LiteLLM logging threads under gunicorn/gevent). For the
# specific case where a loop is already running, we fall back to scheduling
# the coroutine on the existing loop instead of raising.
_original_asyncio_run = asyncio.run


def _safe_asyncio_run(coro, *args, **kwargs):
    try:
        return _original_asyncio_run(coro, *args, **kwargs)
    except RuntimeError as exc:
        message = str(exc)
        if "cannot be called from a running event loop" not in message:
            # Preserve original behaviour for unrelated errors.
            raise
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop available, re-raise the original error.
            raise
        try:
            loop.create_task(coro)
        except Exception:
            # If even scheduling fails, swallow the error so logging/caching
            # failures do not break the main application.
            return


asyncio.run = _safe_asyncio_run


@dataclass
class ProviderConfig:
    key: str
    api_key_env: str
    base_url_env: str | None = None
    default_base_url: str | None = None
    prefix: str = ""
    fetch_models: bool = True
    filter_fn: Callable[[str], bool] | None = None
    static_models: List[str] = field(default_factory=list)
    extra_models: List[str] = field(default_factory=list)
    wildcard_prefixes: Tuple[str, ...] = ()
    config_hint: str = ""
    custom_llm_provider: str | None = None
    model_loader: Optional[
        Callable[
            ["ProviderConfig", Dict[str, str], Optional[str]],
            List[Union[str, Tuple[str, str]]],
        ]
    ] = None
    reload_params: Optional[Callable[[str, float], Dict[str, Any]]] = None


@dataclass
class ProviderState:
    enabled: bool
    params: Optional[Dict[str, str]]
    models: List[str]
    prefix: str = ""
    wildcard_prefixes: Tuple[str, ...] = ()
    reload_params: Optional[Callable[[str, float], Dict[str, Any]]] = None


MODEL_ALIAS_MAP: Dict[str, Tuple[str, str]] = {}
PROVIDER_STATES: Dict[str, ProviderState] = {}


def _log(level: str, message: str) -> None:
    try:
        getattr(current_app.logger, level)(message)
    except Exception:
        getattr(logger, level)(message)


def _log_info(message: str) -> None:
    _log("info", message)


def _log_warning(message: str) -> None:
    _log("warning", message)


def _extract_usage_value(usage: Any, key: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(key) or 0)
    return int(getattr(usage, key, 0) or 0)


def _extract_input_cache(usage: Any) -> int:
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


def _get_request_id() -> str:
    try:
        return request.headers.get("X-Request-ID", "") or ""
    except RuntimeError:
        return ""


def _normalize_model_config(value: Any) -> list[str]:
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
    value = os.environ.get(key)
    if value is None:
        return False
    return bool(value.strip())


def _resolve_allowed_model_config() -> tuple[list[str], list[str]]:
    allowed_source = "default"
    if _env_has_value("LLM_ALLOWED_MODELS"):
        allowed = _normalize_model_config(os.environ.get("LLM_ALLOWED_MODELS", ""))
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
            os.environ.get("LLM_ALLOWED_MODEL_DISPLAY_NAMES", "")
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


def _register_provider_models(
    config: ProviderConfig, raw_models: List[Union[str, Tuple[str, str]]]
) -> List[str]:
    seen = set()
    display_models: List[str] = []
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
            False,
            None,
            [],
            config.prefix,
            config.wildcard_prefixes,
            config.reload_params,
        )
    base_url = None
    if config.base_url_env:
        base_url = get_config(config.base_url_env)
    if not base_url:
        base_url = config.default_base_url
    if config.key == "gemini" and base_url:
        if "generativelanguage.googleapis.com" in base_url:
            base_url = None
            _log_info(
                "Skipping GEMINI_API_URL override to use LiteLLM default endpoint"
            )
    params: Dict[str, str] = {"api_key": api_key}
    if base_url:
        params["api_base"] = base_url
    if config.custom_llm_provider:
        params["custom_llm_provider"] = config.custom_llm_provider
    if config.model_loader:
        raw_models = config.model_loader(config, params, base_url)
    else:
        raw_models: List[Union[str, Tuple[str, str]]] = list(config.static_models)
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
        True,
        params,
        display_models,
        config.prefix,
        config.wildcard_prefixes,
        config.reload_params,
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


def _stream_litellm_completion(
    app: Flask, model: str, messages: list, params: dict, kwargs: dict
):
    try:
        try:
            max_tokens = get_max_tokens(model)
            kwargs["max_tokens"] = max_tokens
        except Exception as exc:
            _log_warning(f"get max tokens for {model} failed: {exc}")
        app.logger.info(
            f"stream_litellm_completion: {model} {messages} {params} {kwargs}"
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


def _resolve_provider_for_model(model: str) -> Tuple[Optional[str], str]:
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
    config: ProviderConfig, params: Dict[str, str], base_url: Optional[str]
) -> List[Union[str, Tuple[str, str]]]:
    models: List[Union[str, Tuple[str, str]]] = []
    api_key = params.get("api_key")
    if not api_key:
        return models

    # If a custom proxy is provided, try the generic OpenAI-compatible fetcher first.
    if base_url and "generativelanguage.googleapis.com" not in base_url:
        try:
            models.extend(_fetch_provider_models(api_key, base_url))
            return models
        except Exception as exc:
            _log_warning(f"load gemini models via custom base error: {exc}")

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


QWEN_PREFIX = "qwen/"
ERNIE_V2_PREFIX = "ernie/"
GLM_PREFIX = "glm/"
SILICON_PREFIX = "silicon/"
GEMINI_PREFIX = ""
DEEPSEEK_EXTRA_MODELS = ["deepseek-chat"]


def _reload_openai_params(model_id: str, temperature: float) -> Dict[str, Any]:
    if model_id.startswith("gpt-5.2"):
        return {
            "reasoning_effort": "none",
            "temperature": temperature,
        }
    if model_id.startswith("gpt-5.1"):
        return {
            "reasoning_effort": "none",
            "temperature": 1,
        }
    if model_id.startswith("gpt-5-pro"):
        return {
            "reasoning_effort": "none",
        }

    if model_id.startswith("gpt-5"):
        return {
            "reasoning_effort": "minimal",
            "temperature": 1,
        }
    return {
        "temperature": temperature,
    }


def _reload_gemini_params(model_id: str, temperature: float) -> Dict[str, Any]:
    if model_id.startswith("gemini-2.5-pro"):
        return {
            "reasoning_effort": "low",
            "temperature": temperature,
        }
    if model_id.startswith("gemini-3"):
        return {
            "reasoning_effort": "low",
            "temperature": temperature,
        }
    if model_id.startswith("gemini"):
        return {
            "reasoning_effort": "none",
            "temperature": temperature,
        }
    return {
        "temperature": temperature,
    }


def _reload_ark_params(model_id: str, temperature: float) -> Dict[str, Any]:
    # doubao-seed models support thinking parameter, pass via extra_body for LiteLLM
    return {
        "temperature": temperature,
        "extra_body": {"thinking": {"type": "disabled"}},
    }


def _reload_silicon_params(model_id: str, temperature: float) -> Dict[str, Any]:
    return {
        "temperature": temperature,
        "extra_body": {"enable_thinking": False},
    }


LITELLM_PROVIDER_CONFIGS: List[ProviderConfig] = [
    ProviderConfig(
        key="openai",
        api_key_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        default_base_url="https://api.openai.com/v1",
        filter_fn=lambda model_id: model_id.startswith("gpt"),
        wildcard_prefixes=("gpt",),
        config_hint="OPENAI_API_KEY,OPENAI_BASE_URL",
        custom_llm_provider="openai",
        reload_params=_reload_openai_params,
    ),
    ProviderConfig(
        key="qwen",
        api_key_env="QWEN_API_KEY",
        base_url_env="QWEN_API_URL",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        prefix=QWEN_PREFIX,
        extra_models=["deepseek-r1", "deepseek-v3"],
        config_hint="QWEN_API_KEY,QWEN_API_URL",
        custom_llm_provider="openai",
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
        extra_models=DEEPSEEK_EXTRA_MODELS,
        config_hint="DEEPSEEK_API_KEY,DEEPSEEK_API_URL",
        custom_llm_provider="openai",
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
        reload_params=_reload_gemini_params,
    ),
    ProviderConfig(
        key="glm",
        api_key_env="BIGMODEL_API_KEY",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        prefix=GLM_PREFIX,
        config_hint="BIGMODEL_API_KEY",
        custom_llm_provider="openai",
    ),
    ProviderConfig(
        key="silicon",
        api_key_env="SILICON_API_KEY",
        default_base_url="https://api.siliconflow.cn/v1",
        prefix=SILICON_PREFIX,
        config_hint="SILICON_API_KEY,SILICON_API_URL",
        custom_llm_provider="openai",
        reload_params=_reload_silicon_params,
    ),
    ProviderConfig(
        key="ark",
        api_key_env="ARK_API_KEY",
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        prefix="ark/",
        config_hint="ARK_API_KEY",
        custom_llm_provider="openai",
        reload_params=_reload_ark_params,
    ),
]

PROVIDER_CONFIG_HINTS: Dict[str, str] = {}
for config in LITELLM_PROVIDER_CONFIGS:
    PROVIDER_STATES[config.key] = _init_litellm_provider(config)
    PROVIDER_CONFIG_HINTS[config.key] = config.config_hint or config.api_key_env


any_litellm_enabled = any(state.enabled for state in PROVIDER_STATES.values())
if not any_litellm_enabled:
    _log_warning("No LLM Configured")

DIFY_MODELS = []

if get_config("DIFY_API_KEY") and get_config("DIFY_URL"):
    DIFY_MODELS = ["dify"]
else:
    _log_warning("DIFY_API_KEY and DIFY_URL not configured")


class LLMStreamaUsage:
    def __init__(self, prompt_tokens, completion_tokens, total_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class LLMStreamResponse:
    def __init__(self, id, is_end, is_truncated, result, finish_reason, usage):
        self.id = id

        self.is_end = is_end
        self.is_truncated = is_truncated
        self.result = result
        self.finish_reason = finish_reason
        self.usage = LLMStreamaUsage(**usage) if usage else None


def get_litellm_params_and_model(model: str):
    requested_model = model
    provider_key, invoke_model = _resolve_provider_for_model(model)
    if provider_key:
        state = PROVIDER_STATES.get(provider_key)
        params = state.params if state else None
        reload_params = state.reload_params if state else None
        if not params:
            raise_error_with_args(
                "server.llm.specifiedLlmNotConfigured",
                model=requested_model,
                config_var=PROVIDER_CONFIG_HINTS.get(
                    provider_key, provider_key.upper()
                ),
            )
        return params, invoke_model, reload_params
    return None, model, None


def invoke_llm(
    app: Flask,
    user_id: str,
    span: StatefulSpanClient,
    model: str,
    message: str,
    system: str = None,
    json: bool = False,
    generation_name: str = "invoke_llm",
    usage_context: Optional[UsageContext] = None,
    usage_scene: Optional[Union[str, int]] = None,
    billable: Optional[int] = None,
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    usage_metadata: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Generator[LLMStreamResponse, None, None]:
    stream_flag = bool(kwargs.get("stream", True))
    kwargs.pop("stream", None)
    usage_scene = (
        usage_scene if usage_scene is not None else kwargs.pop("usage_scene", None)
    )
    billable = billable if billable is not None else kwargs.pop("billable", None)
    request_id = request_id or kwargs.pop("request_id", None) or _get_request_id()
    trace_id = trace_id or kwargs.pop("trace_id", None) or getattr(span, "trace_id", "")
    usage_metadata = usage_metadata or kwargs.pop("usage_metadata", None) or {}
    model = model.strip()
    generation_input = []
    if system:
        generation_input.append({"role": "system", "content": system})
    generation_input.append({"role": "user", "content": message})
    generation = span.generation(
        model=model, input=generation_input, name=generation_name
    )
    response_text = ""
    usage = None
    input_cache_tokens = 0
    provider_name = ""
    start_time = time.monotonic()
    params, invoke_model, reload_params = get_litellm_params_and_model(model)
    start_completion_time = None
    if params:
        provider_key, _normalized = _resolve_provider_for_model(model)
        provider_name = provider_key or ""
        messages = []
        if system:
            messages.append({"content": system, "role": "system"})
        messages.append({"content": message, "role": "user"})
        if json:
            kwargs["response_format"] = {"type": "json_object"}
        kwargs["stream_options"] = {"include_usage": True}
        if reload_params:
            kwargs.update(reload_params(model, float(kwargs.get("temperature", 0.3))))
        else:
            kwargs.update(
                {
                    "temperature": float(kwargs.get("temperature", 0.3)),
                }
            )
        response = _stream_litellm_completion(
            app,
            invoke_model,
            messages,
            params,
            kwargs,
        )

        for res in response:
            if start_completion_time is None:
                start_completion_time = datetime.now()
            if len(res.choices) and res.choices[0].delta.content:
                response_text += res.choices[0].delta.content
                yield LLMStreamResponse(
                    res.id,
                    True if res.choices[0].finish_reason else False,
                    False,
                    res.choices[0].delta.content,
                    res.choices[0].finish_reason,
                    None,
                )
            res_usage = getattr(res, "usage", None)
            if res_usage:
                input_cache_tokens = _extract_input_cache(res_usage)
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res_usage.prompt_tokens,
                    output=res_usage.completion_tokens,
                    total=res_usage.total_tokens,
                )
    elif model in DIFY_MODELS:
        provider_name = "dify"
        response = dify_chat_message(app, message, user_id)
        for res in response:
            if start_completion_time is None:
                start_completion_time = datetime.now()
            if res.event == "message":
                response_text += res.answer
                yield LLMStreamResponse(
                    res.task_id,
                    True if res.event == "message" else False,
                    False,
                    res.answer,
                    None,
                    None,
                )
    else:
        raise_error_with_args(
            "server.llm.modelNotSupported",
            model=model,
        )

    app.logger.info(f"invoke_llm response: {response_text} ")
    if usage is None:
        app.logger.info("invoke_llm usage: None")
    else:
        app.logger.info(f"invoke_llm usage: {usage.__str__()}")
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
        output=response_text,
        usage=usage,
        metadata=kwargs,
        completion_start_time=start_completion_time,
    )
    span.update(output=response_text)


def chat_llm(
    app: Flask,
    user_id: str,
    span: StatefulSpanClient,
    model: str,
    messages: list,
    json: bool = False,
    generation_name: str = "user_follow_ask",
    usage_context: Optional[UsageContext] = None,
    usage_scene: Optional[Union[str, int]] = None,
    billable: Optional[int] = None,
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    usage_metadata: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Generator[LLMStreamResponse, None, None]:
    app.logger.info(f"chat_llm [{model}] {messages} ,json:{json} ,kwargs:{kwargs}")
    stream_flag = bool(kwargs.get("stream", True))
    kwargs.pop("stream", None)
    usage_scene = (
        usage_scene if usage_scene is not None else kwargs.pop("usage_scene", None)
    )
    billable = billable if billable is not None else kwargs.pop("billable", None)
    request_id = request_id or kwargs.pop("request_id", None) or _get_request_id()
    trace_id = trace_id or kwargs.pop("trace_id", None) or getattr(span, "trace_id", "")
    usage_metadata = usage_metadata or kwargs.pop("usage_metadata", None) or {}
    model = model.strip()
    generation_input = messages
    generation = span.generation(
        model=model, input=generation_input, name=generation_name
    )
    response_text = ""
    usage = None
    input_cache_tokens = 0
    provider_name = ""
    start_time = time.monotonic()
    start_completion_time = None
    params, invoke_model, reload_params = get_litellm_params_and_model(model)
    if params:
        provider_key, _normalized = _resolve_provider_for_model(model)
        provider_name = provider_key or ""
        if reload_params:
            kwargs.update(reload_params(model, float(kwargs.get("temperature", 0.3))))
        else:
            kwargs.update(
                {
                    "temperature": float(kwargs.get("temperature", 0.3)),
                }
            )
        kwargs["stream_options"] = {"include_usage": True}
        response = _stream_litellm_completion(
            app,
            invoke_model,
            messages,
            params,
            kwargs,
        )
        for res in response:
            if start_completion_time is None:
                start_completion_time = datetime.now()
            if len(res.choices) and res.choices[0].delta.content:
                response_text += res.choices[0].delta.content
                yield LLMStreamResponse(
                    res.id,
                    True if res.choices[0].finish_reason else False,
                    False,
                    res.choices[0].delta.content,
                    res.choices[0].finish_reason,
                    None,
                )
            res_usage = getattr(res, "usage", None)
            if res_usage:
                input_cache_tokens = _extract_input_cache(res_usage)
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res_usage.prompt_tokens,
                    output=res_usage.completion_tokens,
                    total=res_usage.total_tokens,
                )
    elif model in DIFY_MODELS:
        provider_name = "dify"
        response: Generator[DifyChunkChatCompletionResponse, None, None] = (
            dify_chat_message(app, messages[-1]["content"], user_id)
        )
        for res in response:
            if start_completion_time is None:
                start_completion_time = datetime.now()
            if res.event == "message":
                response_text += res.answer
                yield LLMStreamResponse(
                    res.task_id,
                    True if res.event == "message" else False,
                    False,
                    res.answer,
                    None,
                    None,
                )
    else:
        raise_error_with_args(
            "server.llm.modelNotSupported",
            model=model,
        )

    app.logger.info(f"invoke_llm response: {response_text} ")
    if usage is None:
        app.logger.info("invoke_llm usage: None")
    else:
        app.logger.info(f"invoke_llm usage: {usage.__str__()}")
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
        output=response_text,
        usage=usage,
        metadata=kwargs,
        completion_start_time=start_completion_time,
    )


def _build_model_options(
    app: Flask, available_models: list[str]
) -> list[dict[str, str]]:
    allowed, display_names = _resolve_allowed_model_config()

    if not allowed:
        return [{"model": model, "display_name": model} for model in available_models]

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
        dict(zip(allowed, display_names)) if display_names_enabled else {}
    )

    return [
        {
            "model": model,
            "display_name": display_map.get(model, model),
        }
        for model in filtered_models
    ]


def get_current_models(app: Flask) -> list[dict[str, str]]:
    litellm_models: list[str] = []
    for state in PROVIDER_STATES.values():
        litellm_models.extend(state.models)
    combined = litellm_models + DIFY_MODELS
    available_models = list(dict.fromkeys(combined))
    return _build_model_options(app, available_models)


def get_allowed_models() -> list[str]:
    allowed, _ = _resolve_allowed_model_config()
    return allowed
