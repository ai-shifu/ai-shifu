from typing import Generator
import requests
from flask import Flask
import jwt
import time
import json

from flaskr.common.config import get_config

URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


URLS = {
    "glm-4-0520": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "glm-4": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "glm-4-air": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "glm-4-airx": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "glm-4-flash": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "glm-4v": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "glm-3-turbo": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
}


class ChatResponse:
    def __init__(self, id, created, model, choices, usage=None, object=None):
        self.id: str = id
        self.created: int = created
        self.model: str = model
        self.choices: list[Choice] = [Choice(**choice) for choice in choices]
        self.usage: Usage = Usage(**usage) if usage else None
        self.object: str = object if object else None


class FunctionCall:
    def __init__(self, name=None, arguments=None):
        self.name: str = name
        self.arguments: str = arguments


class ToolCall:
    def __init__(self, id, type, index=None, function=None):
        self.id: str = id
        self.type: str = type
        self.index: int = index if index else None
        self.function: FunctionCall = FunctionCall(**function) if function else None


class Choice:
    def __init__(self, index, delta, finish_reason=None):
        self.index: int = index
        self.delta: Delta = Delta(**delta)
        self.finish_reason: str = finish_reason if finish_reason else None


class Delta:
    def __init__(self, role, content=None, tool_calls=None):
        self.role = role
        self.content = content
        self.tool_calls: list[ToolCall] = (
            [ToolCall(**tool_call) for tool_call in tool_calls] if tool_calls else None
        )


class Usage:
    def __init__(self, prompt_tokens, completion_tokens, total_tokens):
        self.prompt_tokens: int = prompt_tokens
        self.completion_tokens: int = completion_tokens
        self.total_tokens: int = total_tokens

    def __str__(self):
        return f"prompt_tokens:{self.prompt_tokens},completion_tokens:{self.completion_tokens},total_tokens:{self.total_tokens}"


def get_token(app: Flask) -> str:
    try:
        id, secret = get_config("BIGMODEL_API_KEY").split(".")
    except Exception as e:
        raise Exception("invalid apikey", e)

    payload = {
        "api_key": id,
        "exp": int(round(time.time() * 1000)) + 10 * 1000,
        "timestamp": int(round(time.time() * 1000)),
    }
    return jwt.encode(
        payload,
        secret,
        algorithm="HS256",
        headers={"alg": "HS256", "sign_type": "SIGN"},
    )


def get_chat_response(app: Flask, msg: str) -> Generator[ChatResponse, None, None]:
    data = {
        "messages": [{"content": msg, "role": "user"}],
    }
    for res in invoke_glm(app, **data):
        yield res


def invoke_glm(
    app: Flask, model, messages, **args
) -> Generator[ChatResponse, None, None]:

    data = {"model": model, "messages": messages, "stream": True}

    data = {**data, **args}

    headers = {"Authorization": "Bearer " + get_config("GLM_API_KEY")}
    response = requests.post(URLS[model], json=data, headers=headers, stream=True)
    app.logger.info("request data: {}".format(json.dumps(data)))
    for res in response.iter_lines():
        res = res.decode("utf-8")
        app.logger.info("zhipu response data: {}".format(res))
        if res.startswith("data:"):
            # 提取 'data:' 后面的内容
            json_data = res[5:].strip()
            # 尝试解析 JSON 数据
            if json_data.replace(" ", "") == "[DONE]":
                break
            parsed_data = json.loads(json_data)
            yield ChatResponse(**parsed_data)
    if response.status_code != 200:
        try:
            app.logger.error(
                "zhipu response status code: {}".format(response.status_code)
            )
            app.logger.error("zhipu response data: {}".format(response.text))
        except Exception as e:
            app.logger.error("zhipu response error: {}".format(e))
            pass
        # raise Exception('zhipu response status code: {}'.format(response.status_code))

    app.logger.error("ernie response data: {}".format(response))


def get_zhipu_models(app: Flask) -> list[str]:
    return list(URLS.keys())
