from typing import Generator
from .ernie import get_ernie_response, get_erine_models, chat_ernie
from .glm import get_zhipu_models, invoke_glm
import openai
from flask import Flask
from langfuse.client import StatefulSpanClient
from langfuse.model import ModelUsage

from openai.types.chat import ChatCompletionStreamOptionsParam
from openai.types.shared_params import ResponseFormatJSONObject
from flask import current_app
from .dify import DifyChunkChatCompletionResponse, dify_chat_message
from flaskr.common.config import get_config
from flaskr.service.common.models import raise_error_with_args
from ..ark.sign import request
from datetime import datetime

openai_enabled = False

OPENAI_MODELS = []
if get_config("OPENAI_API_KEY"):
    openai_enabled = True
    openai_client = openai.Client(
        api_key=get_config("OPENAI_API_KEY"),
        base_url=get_config("OPENAI_BASE_URL"),
    )
    try:
        OPENAI_MODELS = [
            i.id for i in openai_client.models.list().data if i.id.startswith("gpt")
        ]
    except Exception as e:
        current_app.logger.warning(f"get openai models error: {e}")
        OPENAI_MODELS = []
else:
    current_app.logger.warning("OPENAI_API_KEY not configured")
    openai_client = None

deepseek_enabled = False
if get_config("DEEPSEEK_API_KEY"):
    deepseek_enabled = True
    deepseek_client = openai.Client(
        api_key=get_config("DEEPSEEK_API_KEY"),
        base_url=get_config("DEEPSEEK_API_URL"),
    )
else:
    current_app.logger.warning("DEEPSEEK_API_KEY not configured")
    deepseek_client = None


# qwen
qwen_enabled = False
QWEN_MODELS = []
QWEN_PREFIX = "qwen/"
if get_config("QWEN_API_KEY"):
    qwen_enabled = True
    qwen_client = openai.Client(
        api_key=get_config("QWEN_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    # get_config("QWEN_API_URL")
    # )
    QWEN_MODELS = [QWEN_PREFIX + i.id for i in qwen_client.models.list().data]
    QWEN_MODELS = QWEN_MODELS + [
        QWEN_PREFIX + "deepseek-r1",
        QWEN_PREFIX + "deepseek-v3",
    ]
    current_app.logger.info(f"qwen models: {QWEN_MODELS}")
else:
    current_app.logger.warning("QWEN_API_KEY not configured")
    qwen_client = None

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
if get_config("ERNIE_API_KEY"):
    ernie_v2_enabled = True
    ernie_v2_client = openai.Client(
        api_key=get_config("ERNIE_API_KEY"), base_url="https://qianfan.baidubce.com/v2"
    )
    ERNIE_V2_MODELS = [ERNIE_V2_PREFIX + i for i in ERNIE_V2_MODELS]
    current_app.logger.info(f"ernie v2 models: {ERNIE_V2_MODELS}")
else:
    current_app.logger.warning("ERNIE_API_TOKEN not configured")

# ernie
ernie_enabled = False
ERNIE_MODELS = []

if get_config("ERNIE_API_ID") and get_config("ERNIE_API_SECRET"):
    ernie_enabled = True
    ERNIE_MODELS = get_erine_models(current_app)
else:
    current_app.logger.warning("ERNIE_API_ID and ERNIE_API_SECRET not configured")

current_app.logger.info(f"ernie models: {ERNIE_MODELS}")

# ark
ark_enabled = False
ARK_MODELS = []
ARK_PREFIX = "ark/"
ARK_MODELS_MAP = {}
if get_config("ARK_ACCESS_KEY_ID") and get_config("ARK_SECRET_ACCESS_KEY"):
    ark_list_endpoints = request(
        "POST",
        datetime.now(),
        {},
        {},
        get_config("ARK_ACCESS_KEY_ID"),
        get_config("ARK_SECRET_ACCESS_KEY"),
        "ListEndpoints",
        None,
    )
    current_app.logger.info(ark_list_endpoints)
    ark_enabled = True
    current_app.logger.info("ARK CONFIGURED")
    ark_endpoints = ark_list_endpoints.get("Result", {}).get("Items", [])
    if ark_endpoints and len(ark_endpoints) > 0:
        for endpoint in ark_endpoints:
            endpoint_id = endpoint.get("Id")
            model_name = (
                endpoint.get("ModelReference", {})
                .get("FoundationModel", {})
                .get("Name", "")
            )
            current_app.logger.info(f"ark endpoint: {endpoint_id}, model: {model_name}")
            ARK_MODELS.append(ARK_PREFIX + model_name)
            ARK_MODELS_MAP[ARK_PREFIX + model_name] = endpoint_id
    ark_client = openai.Client(
        api_key=get_config("ARK_API_KEY"),
        base_url="https://ark.cn-beijing.volces.com/api/v3",
    )
    current_app.logger.info(f"ark models: {ARK_MODELS}")
else:
    current_app.logger.warning("ARK_API_KEY not configured")


# special model glm
glm_enabled = False
if get_config("GLM_API_KEY"):
    glm_enabled = True
else:
    current_app.logger.warning("GLM_API_KEY not configured")
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
    current_app.logger.warning("No LLM Configured")


# silicon
silicon_enabled = False
SILICON_MODELS = []
SILICON_PREFIX = "silicon/"
if get_config("SILICON_API_KEY"):
    silicon_enabled = True
    current_app.logger.info("SILICON CONFIGURED")
    silicon_client = openai.Client(
        api_key=get_config("SILICON_API_KEY"), base_url="https://api.siliconflow.cn/v1"
    )

    SILICON_MODELS = [SILICON_PREFIX + i.id for i in silicon_client.models.list().data]
    current_app.logger.info(f"SILICON_MODELS: {SILICON_MODELS}")
else:
    current_app.logger.warning("SILICON_API_KEY not configured")
    silicon_client = None

ERNIE_MODELS = get_erine_models(Flask(__name__))
GLM_MODELS = get_zhipu_models(Flask(__name__))
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


def get_openai_client_and_model(model: str):
    client = None
    if (
        model in OPENAI_MODELS
        or model.startswith("gpt")
        or model in QWEN_MODELS
        or model in DEEP_SEEK_MODELS
        or model in SILICON_MODELS
        or model in ERNIE_V2_MODELS
        or model in ARK_MODELS
    ):
        if model in OPENAI_MODELS or model.startswith("gpt"):
            client = openai_client
            if not client:
                raise_error_with_args(
                    "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
                    model=model,
                    config_var="OPENAI_API_KEY,OPENAI_BASE_URL",
                )
        elif model in QWEN_MODELS:
            client = qwen_client
            model = model.replace(QWEN_PREFIX, "")
            if not client:
                raise_error_with_args(
                    "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
                    model=model,
                    config_var="QWEN_API_KEY,QWEN_API_URL",
                )
        elif model in DEEP_SEEK_MODELS:
            client = deepseek_client
            if not client:
                raise_error_with_args(
                    "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
                    model=model,
                    config_var="DEEPSEEK_API_KEY,DEEPSEEK_API_URL",
                )
        elif model in SILICON_MODELS:
            client = silicon_client
            model = model.replace(SILICON_PREFIX, "")
            if not client:
                raise_error_with_args(
                    "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
                    model=model,
                    config_var="SILICON_API_KEY,SILICON_API_URL",
                )
        elif model in ERNIE_V2_MODELS:
            client = ernie_v2_client
            model = model.replace(ERNIE_V2_PREFIX, "")
            if not client:
                raise_error_with_args(
                    "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
                    model=model,
                    config_var="ERNIE_API_KEY",
                )
        elif model in ARK_MODELS:
            client = ark_client
            model = ARK_MODELS_MAP[model]
            if not client:
                raise_error_with_args(
                    "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
                    model=model,
                    config_var="ARK_ACCESS_KEY_ID,ARK_SECRET_ACCESS_KEY",
                )
    return client, model


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
    kwargs.update({"stream": True})
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
    client, invoke_model = get_openai_client_and_model(model)
    start_completion_time = None
    if client:
        messages = []
        if system:
            messages.append({"content": system, "role": "system"})
        messages.append({"content": message, "role": "user"})
        if json:
            kwargs["response_format"] = ResponseFormatJSONObject(type="json_object")
        kwargs["temperature"] = float(kwargs.get("temperature", 0.8))
        kwargs["stream_options"] = ChatCompletionStreamOptionsParam(include_usage=True)
        response = client.chat.completions.create(
            model=invoke_model, messages=messages, **kwargs
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
                "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
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
    elif model.lower() in GLM_MODELS:
        if not glm_enabled:
            raise_error_with_args(
                "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
                model=model,
                config_var="GLM_API_KEY",
            )
        if kwargs.get("temperature", None) is not None:
            kwargs["temperature"] = str(kwargs["temperature"])
        messages = []
        if system:
            messages.append({"content": system, "role": "system"})
        messages.append({"content": message, "role": "user"})
        response = invoke_glm(app, model.lower(), messages, **kwargs)
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
                True if res.choices[0].finish_reason else False,
                False,
                res.choices[0].delta.content,
                res.choices[0].finish_reason,
                None,
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
            "LLM.MODEL_NOT_SUPPORTED",
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
    span.end(output=response_text)


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
    kwargs.update({"stream": True})
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
    client, invoke_model = get_openai_client_and_model(model)
    if client:
        response = client.chat.completions.create(
            model=invoke_model, messages=messages, **kwargs
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
                "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
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
    elif model.lower() in GLM_MODELS:
        if not glm_enabled:
            raise_error_with_args(
                "LLM.SPECIFIED_LLM_NOT_CONFIGURED",
                model=model,
                config_var="GLM_API_KEY",
            )
        if kwargs.get("temperature", None) is not None:
            kwargs["temperature"] = str(kwargs["temperature"])
        response = invoke_glm(app, model.lower(), messages, **kwargs)
        for res in response:
            if start_completion_time is None:
                start_completion_time = datetime.now()
            response_text += res.choices[0].delta.content
            if res.usage:
                usage = ModelUsage(
                    unit="TOKENS",
                    input=res.usage.prompt_tokens,
                    output=res.usage.completion_tokens,
                    total=res.usage.total_tokens,
                )
            yield LLMStreamResponse(
                res.id,
                True if res.choices[0].finish_reason else False,
                False,
                res.choices[0].delta.content,
                res.choices[0].finish_reason,
                None,
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
            "LLM.MODEL_NOT_SUPPORTED",
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
