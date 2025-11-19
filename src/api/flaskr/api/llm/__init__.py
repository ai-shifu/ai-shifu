from typing import Generator
from datetime import datetime
import logging
import requests
import litellm
from flask import Flask, current_app
from langfuse.client import StatefulSpanClient
from langfuse.model import ModelUsage

from .ernie import get_ernie_response, get_erine_models, chat_ernie
from .dify import DifyChunkChatCompletionResponse, dify_chat_message
from flaskr.common.config import get_config
from flaskr.service.common.models import raise_error_with_args
from ..ark.sign import request

logger = logging.getLogger(__name__)


def _log(level: str, message: str) -> None:
    try:
        getattr(current_app.logger, level)(message)
    except Exception:
        getattr(logger, level)(message)


def _log_info(message: str) -> None:
    _log("info", message)


def _log_warning(message: str) -> None:
    _log("warning", message)


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


openai_enabled = False
openai_params = None

OPENAI_MODELS = []
openai_api_key = get_config("OPENAI_API_KEY")
if openai_api_key:
    openai_enabled = True
    openai_base_url = get_config("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    openai_params = {"api_key": openai_api_key, "api_base": openai_base_url}
    try:
        OPENAI_MODELS = [
            model_id
            for model_id in _fetch_provider_models(openai_api_key, openai_base_url)
            if model_id.startswith("gpt")
        ]
    except Exception as e:
        _log_warning(f"get openai models error: {e}")
        OPENAI_MODELS = []
else:
    _log_warning("OPENAI_API_KEY not configured")

deepseek_enabled = False
deepseek_params = None
deepseek_api_key = get_config("DEEPSEEK_API_KEY")
if deepseek_api_key:
    deepseek_enabled = True
    deepseek_params = {
        "api_key": deepseek_api_key,
        "api_base": get_config("DEEPSEEK_API_URL") or "https://api.deepseek.com",
    }
else:
    _log_warning("DEEPSEEK_API_KEY not configured")


# qwen
qwen_enabled = False
QWEN_MODELS = []
QWEN_PREFIX = "qwen/"
qwen_params = None
qwen_api_key = get_config("QWEN_API_KEY")
if qwen_api_key:
    try:
        qwen_enabled = True
        qwen_base_url = (
            get_config("QWEN_API_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        qwen_params = {"api_key": qwen_api_key, "api_base": qwen_base_url}
        fetched_models = _fetch_provider_models(qwen_api_key, qwen_base_url)
        QWEN_MODELS = [QWEN_PREFIX + model_id for model_id in fetched_models]
        QWEN_MODELS = QWEN_MODELS + [
            QWEN_PREFIX + "deepseek-r1",
            QWEN_PREFIX + "deepseek-v3",
        ]
        _log_info(f"qwen models: {QWEN_MODELS}")
    except Exception as e:
        _log_warning(f"load qwen models error: {e}")
        qwen_enabled = False
        QWEN_MODELS = []
else:
    _log_warning("QWEN_API_KEY not configured")

# ernie v2
ernie_v2_enabled = False
ERNIE_V2_PREFIX = "ernie/"
ERNIE_V2_MODELS = [
    "ernie-4.0-8k-latest",
    "ernie-4.0-8k-preview",
    "ernie-4.0-8k",
    "ernie-4.0-turbo-8k-latest",
    "ernie-4.0-turbo-8k-preview",
    "ernie-4.0-turbo-8k",
    "ernie-4.0-turbo-128k",
    "ernie-3.5-8k-preview",
    "ernie-3.5-8k",
    "ernie-3.5-128k",
    "ernie-speed-8k",
    "ernie-speed-128k",
    "ernie-speed-pro-128k",
    "ernie-lite-8k",
    "ernie-lite-pro-128k",
    "ernie-tiny-8k",
    "ernie-char-8k",
    "ernie-char-fiction-8k",
    "ernie-novel-8k",
    "deepseek-v3",
    "deepseek-r1",
]
ernie_v2_params = None
ernie_v2_api_key = get_config("ERNIE_API_KEY")
if ernie_v2_api_key:
    try:
        ernie_v2_enabled = True
        ernie_v2_params = {
            "api_key": ernie_v2_api_key,
            "api_base": "https://qianfan.baidubce.com/v2",
        }
        ERNIE_V2_MODELS = [ERNIE_V2_PREFIX + i for i in ERNIE_V2_MODELS]
        _log_info(f"ernie v2 models: {ERNIE_V2_MODELS}")
    except Exception as e:
        _log_warning(f"load ernie v2 models error: {e}")
        ernie_v2_enabled = False
else:
    _log_warning("ERNIE_API_TOKEN not configured")

# ernie
ernie_enabled = False
ERNIE_MODELS = []

if get_config("ERNIE_API_ID") and get_config("ERNIE_API_SECRET"):
    try:
        ernie_enabled = True
        ERNIE_MODELS = get_erine_models(current_app)
    except Exception as e:
        current_app.logger.warning(f"load ernie models error: {e}")
        ernie_enabled = False
        ERNIE_MODELS = []
else:
    current_app.logger.warning("ERNIE_API_ID and ERNIE_API_SECRET not configured")

current_app.logger.info(f"ernie models: {ERNIE_MODELS}")

# ark
ark_enabled = False
ARK_MODELS = []
ARK_PREFIX = "ark/"
ARK_MODELS_MAP = {}
ark_params = None
ark_api_key = get_config("ARK_API_KEY")
ark_access_key = get_config("ARK_ACCESS_KEY_ID")
ark_secret_key = get_config("ARK_SECRET_ACCESS_KEY")
if ark_api_key and ark_access_key and ark_secret_key:
    try:
        ark_list_endpoints = request(
            "POST",
            datetime.now(),
            {},
            {},
            ark_access_key,
            ark_secret_key,
            "ListEndpoints",
            None,
        )
        _log_info(str(ark_list_endpoints))
        ark_enabled = True
        _log_info("ARK CONFIGURED")
        ark_endpoints = ark_list_endpoints.get("Result", {}).get("Items", [])
        if ark_endpoints and len(ark_endpoints) > 0:
            for endpoint in ark_endpoints:
                endpoint_id = endpoint.get("Id")
                model_name = (
                    endpoint.get("ModelReference", {})
                    .get("FoundationModel", {})
                    .get("Name", "")
                )
                _log_info(f"ark endpoint: {endpoint_id}, model: {model_name}")
                ARK_MODELS.append(ARK_PREFIX + model_name)
                ARK_MODELS_MAP[ARK_PREFIX + model_name] = endpoint_id
        ark_params = {
            "api_key": ark_api_key,
            "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        }
        _log_info(f"ark models: {ARK_MODELS}")
    except Exception as e:
        _log_warning(f"load ark models error: {e}")
        ark_enabled = False
        ARK_MODELS = []
        ARK_MODELS_MAP = {}
else:
    _log_warning("ARK credentials not fully configured")


# special model glm
GLM_PREFIX = "glm/"
glm_enabled = False
GLM_MODELS = []
glm_params = None
glm_api_key = get_config("BIGMODEL_API_KEY")
if glm_api_key:
    try:
        glm_enabled = True
        glm_base_url = "https://open.bigmodel.cn/api/paas/v4"
        glm_params = {"api_key": glm_api_key, "api_base": glm_base_url}
        fetched_glm_models = _fetch_provider_models(glm_api_key, glm_base_url)
        GLM_MODELS = [GLM_PREFIX + i for i in fetched_glm_models]
        _log_info(f"GLM_MODELS: {GLM_MODELS}")
    except Exception as e:
        _log_warning(f"load glm models error: {e}")
        glm_enabled = False
        GLM_MODELS = []
else:
    _log_warning("BIGMODEL_API_KEY not configured")
if (
    openai_enabled
    or deepseek_enabled
    or qwen_enabled
    or ernie_enabled
    or glm_enabled
    or ark_enabled
):
    pass
else:
    _log_warning("No LLM Configured")


# silicon
silicon_enabled = False
SILICON_MODELS = []
SILICON_PREFIX = "silicon/"
silicon_params = None
silicon_api_key = get_config("SILICON_API_KEY")
if silicon_api_key:
    try:
        silicon_enabled = True
        _log_info("SILICON CONFIGURED")
        silicon_base_url = "https://api.siliconflow.cn/v1"
        silicon_params = {"api_key": silicon_api_key, "api_base": silicon_base_url}
        fetched_silicon_models = _fetch_provider_models(
            silicon_api_key, silicon_base_url
        )
        SILICON_MODELS = [SILICON_PREFIX + i for i in fetched_silicon_models]
        _log_info(f"SILICON_MODELS: {SILICON_MODELS}")
    except Exception as e:
        _log_warning(f"load silicon models error: {e}")
        silicon_enabled = False
        SILICON_MODELS = []
else:
    _log_warning("SILICON_API_KEY not configured")

ERNIE_MODELS = get_erine_models(Flask(__name__))
DEEP_SEEK_MODELS = ["deepseek-chat"]

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
    params = None
    if (
        model in OPENAI_MODELS
        or model.startswith("gpt")
        or model in QWEN_MODELS
        or model in DEEP_SEEK_MODELS
        or model in SILICON_MODELS
        or model in ERNIE_V2_MODELS
        or model in ARK_MODELS
        or model in GLM_MODELS
    ):
        if model in OPENAI_MODELS or model.startswith("gpt"):
            params = openai_params
            if not params:
                raise_error_with_args(
                    "server.llm.specifiedLlmNotConfigured",
                    model=model,
                    config_var="OPENAI_API_KEY,OPENAI_BASE_URL",
                )
        elif model in QWEN_MODELS:
            params = qwen_params
            model = model.replace(QWEN_PREFIX, "")
            if not params:
                raise_error_with_args(
                    "server.llm.specifiedLlmNotConfigured",
                    model=model,
                    config_var="QWEN_API_KEY,QWEN_API_URL",
                )
        elif model in DEEP_SEEK_MODELS:
            params = deepseek_params
            if not params:
                raise_error_with_args(
                    "server.llm.specifiedLlmNotConfigured",
                    model=model,
                    config_var="DEEPSEEK_API_KEY,DEEPSEEK_API_URL",
                )
        elif model in SILICON_MODELS:
            params = silicon_params
            model = model.replace(SILICON_PREFIX, "")
            if not params:
                raise_error_with_args(
                    "server.llm.specifiedLlmNotConfigured",
                    model=model,
                    config_var="SILICON_API_KEY,SILICON_API_URL",
                )
        elif model in ERNIE_V2_MODELS:
            params = ernie_v2_params
            model = model.replace(ERNIE_V2_PREFIX, "")
            if not params:
                raise_error_with_args(
                    "server.llm.specifiedLlmNotConfigured",
                    model=model,
                    config_var="ERNIE_API_KEY",
                )
        elif model in ARK_MODELS:
            params = ark_params
            model = ARK_MODELS_MAP[model]
            if not params:
                raise_error_with_args(
                    "server.llm.specifiedLlmNotConfigured",
                    model=model,
                    config_var="ARK_ACCESS_KEY_ID,ARK_SECRET_ACCESS_KEY",
                )
        elif model in GLM_MODELS:
            params = glm_params
            model = model.replace(GLM_PREFIX, "")
            if not params:
                raise_error_with_args(
                    "server.llm.specifiedLlmNotConfigured",
                    model=model,
                    config_var="BIGMODEL_API_KEY",
                )
    return params, model


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
            if res.usage:
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res.usage.prompt_tokens,
                    output=res.usage.completion_tokens,
                    total=res.usage.total_tokens,
                )
    elif model in ERNIE_MODELS:
        if not ernie_enabled:
            raise_error_with_args(
                "server.llm.specifiedLlmNotConfigured",
                model=model,
                config_var="ERNIE_API_ID,ERNIE_API_SECRET",
            )
        if system:
            kwargs.update({"system": system})
        if json:
            kwargs["response_format"] = "json_object"
        if kwargs.get("temperature", None) is not None:
            kwargs["temperature"] = float(kwargs.get("temperature", 0.8))
        response = get_ernie_response(app, model, message, **kwargs)
        for res in response:
            if start_completion_time is None:
                start_completion_time = datetime.now()
            response_text += res.result
            if res.usage:
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res.usage.prompt_tokens,
                    output=res.usage.completion_tokens,
                    total=res.usage.total_tokens,
                )
            yield LLMStreamResponse(
                res.id,
                res.is_end,
                res.is_truncated,
                res.result,
                res.finish_reason,
                res.usage.__dict__,
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
            if res.usage:
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res.usage.prompt_tokens,
                    output=res.usage.completion_tokens,
                    total=res.usage.total_tokens,
                )
    elif model in ERNIE_MODELS:
        if not ernie_enabled:
            raise_error_with_args(
                "server.llm.specifiedLlmNotConfigured",
                model=model,
                config_var="ERNIE_API_ID,ERNIE_API_SECRET",
            )
        if kwargs.get("temperature", None) is not None:
            kwargs["temperature"] = float(kwargs.get("temperature", 0.8))
        response = chat_ernie(app, model, messages, **kwargs)
        for res in response:
            if start_completion_time is None:
                start_completion_time = datetime.now()
            response_text += res.result
            if res.usage:
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res.usage.prompt_tokens,
                    output=res.usage.completion_tokens,
                    total=res.usage.total_tokens,
                )
            yield LLMStreamResponse(
                res.id,
                res.is_end,
                res.is_truncated,
                res.result,
                res.finish_reason,
                res.usage.__dict__,
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
    return list(
        dict.fromkeys(
            OPENAI_MODELS
            + ERNIE_MODELS
            + GLM_MODELS
            + QWEN_MODELS
            + DEEP_SEEK_MODELS
            + DIFY_MODELS
            + SILICON_MODELS
            + ERNIE_V2_MODELS
            + ARK_MODELS
        )
    )
