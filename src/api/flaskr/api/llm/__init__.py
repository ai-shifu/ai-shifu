from dataclasses import dataclass, field
from typing import Callable, Dict, Generator, List, Optional, Tuple, Union
from datetime import datetime
import logging
import requests
import litellm
from flask import Flask, current_app
from langfuse.client import StatefulSpanClient
from langfuse.model import ModelUsage

from .dify import DifyChunkChatCompletionResponse, dify_chat_message
from flaskr.common.config import get_config
from flaskr.service.common.models import raise_error_with_args
from ..ark.sign import request

logger = logging.getLogger(__name__)


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


@dataclass
class ProviderState:
    enabled: bool
    params: Optional[Dict[str, str]]
    models: List[str]
    prefix: str = ""
    wildcard_prefixes: Tuple[str, ...] = ()


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
        return ProviderState(False, None, [], config.prefix, config.wildcard_prefixes)
    base_url = None
    if config.base_url_env:
        base_url = get_config(config.base_url_env)
    if not base_url:
        base_url = config.default_base_url
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


def _stream_litellm_completion(model: str, messages: list, params: dict, kwargs: dict):
    try:
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


def _load_ark_models(
    config: ProviderConfig, params: Dict[str, str], base_url: Optional[str]
) -> List[Union[str, Tuple[str, str]]]:
    access_key = get_config("ARK_ACCESS_KEY_ID")
    secret_key = get_config("ARK_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        _log_warning("ARK credentials not fully configured")
        return []
    try:
        ark_list_endpoints = request(
            "POST",
            datetime.now(),
            {},
            {},
            access_key,
            secret_key,
            "ListEndpoints",
            None,
        )
        _log_info(str(ark_list_endpoints))
        ark_endpoints = ark_list_endpoints.get("Result", {}).get("Items", [])
        models: List[Tuple[str, str]] = []
        if ark_endpoints:
            for endpoint in ark_endpoints:
                endpoint_id = endpoint.get("Id")
                model_name = (
                    endpoint.get("ModelReference", {})
                    .get("FoundationModel", {})
                    .get("Name", "")
                )
                _log_info(f"ark endpoint: {endpoint_id}, model: {model_name}")
                if endpoint_id and model_name:
                    models.append((model_name, endpoint_id))
        return models
    except Exception as exc:
        _log_warning(f"load ark models error: {exc}")
        return []


QWEN_PREFIX = "qwen/"
ERNIE_V2_PREFIX = "ernie/"
GLM_PREFIX = "glm/"
SILICON_PREFIX = "silicon/"
GEMINI_PREFIX = "gemini/"
DEEPSEEK_EXTRA_MODELS = ["deepseek-chat"]
GEMINI_STATIC_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
]

LITELLM_PROVIDER_CONFIGS: List[ProviderConfig] = [
    ProviderConfig(
        key="openai",
        api_key_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        default_base_url="https://api.openai.com/v1",
        filter_fn=lambda model_id: model_id.startswith("gpt"),
        wildcard_prefixes=("gpt",),
        config_hint="OPENAI_API_KEY,OPENAI_BASE_URL",
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
        default_base_url="https://generativelanguage.googleapis.com",
        prefix=GEMINI_PREFIX,
        static_models=GEMINI_STATIC_MODELS,
        fetch_models=False,
        wildcard_prefixes=("gemini-",),
        config_hint="GEMINI_API_KEY,GEMINI_API_URL",
        custom_llm_provider="gemini",
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
    ),
    ProviderConfig(
        key="ark",
        api_key_env="ARK_API_KEY",
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        prefix="ark/",
        config_hint="ARK_ACCESS_KEY_ID,ARK_SECRET_ACCESS_KEY",
        custom_llm_provider="openai",
        fetch_models=False,
        model_loader=_load_ark_models,
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
    current_app.logger.warning("DIFY_API_KEY and DIFY_URL not configured")


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
        if not params:
            raise_error_with_args(
                "server.llm.specifiedLlmNotConfigured",
                model=requested_model,
                config_var=PROVIDER_CONFIG_HINTS.get(
                    provider_key, provider_key.upper()
                ),
            )
        return params, invoke_model
    return None, model


def invoke_llm(
    app: Flask,
    user_id: str,
    span: StatefulSpanClient,
    model: str,
    message: str,
    system: str = None,
    json: bool = False,
    generation_name: str = "invoke_llm",
    **kwargs,
) -> Generator[LLMStreamResponse, None, None]:
    app.logger.info(
        f"invoke_llm [{model}] {message} ,system:{system} ,json:{json} ,kwargs:{kwargs}"
    )
    kwargs.pop("stream", None)
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
    params, invoke_model = get_litellm_params_and_model(model)
    start_completion_time = None
    if params:
        messages = []
        if system:
            messages.append({"content": system, "role": "system"})
        messages.append({"content": message, "role": "user"})
        if json:
            kwargs["response_format"] = {"type": "json_object"}
        kwargs["temperature"] = float(kwargs.get("temperature", 0.8))
        kwargs["stream_options"] = {"include_usage": True}
        response = _stream_litellm_completion(
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
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res_usage.prompt_tokens,
                    output=res_usage.completion_tokens,
                    total=res_usage.total_tokens,
                )
    elif model in DIFY_MODELS:
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
    app.logger.info(f"invoke_llm usage: {usage.__str__()}")
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
    **kwargs,
) -> Generator[LLMStreamResponse, None, None]:
    app.logger.info(f"chat_llm [{model}] {messages} ,json:{json} ,kwargs:{kwargs}")
    kwargs.pop("stream", None)
    model = model.strip()
    generation_input = messages
    generation = span.generation(
        model=model, input=generation_input, name=generation_name
    )
    response_text = ""
    usage = None
    start_completion_time = None
    if kwargs.get("temperature", None) is not None:
        kwargs["temperature"] = float(kwargs.get("temperature", 0.8))
    params, invoke_model = get_litellm_params_and_model(model)
    if params:
        response = _stream_litellm_completion(
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
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res_usage.prompt_tokens,
                    output=res_usage.completion_tokens,
                    total=res_usage.total_tokens,
                )
    elif model in DIFY_MODELS:
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
    app.logger.info(f"invoke_llm usage: {usage.__str__()}")
    generation.end(
        input=generation_input,
        output=response_text,
        usage=usage,
        metadata=kwargs,
        completion_start_time=start_completion_time,
    )


def get_current_models(app: Flask) -> list[str]:
    litellm_models: list[str] = []
    for state in PROVIDER_STATES.values():
        litellm_models.extend(state.models)
    combined = litellm_models + DIFY_MODELS
    return list(dict.fromkeys(combined))
