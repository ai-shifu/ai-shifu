from typing import Generator
import requests

# from ..dao import redis_client
from flask import Flask
import json

from flaskr.common.config import get_config


class ErnieUsage:
    def __init__(self, prompt_tokens, completion_tokens, total_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class ErnieStreamResponse:
    def __init__(
        self,
        id,
        object,
        created,
        sentence_id,
        is_end,
        is_truncated,
        result,
        need_clear_history,
        finish_reason=None,
        usage=None,
        content_type=None,
        **args
    ):
        self.id = id
        self.object = object
        self.created = created
        self.sentence_id = sentence_id
        self.is_end = is_end
        self.is_truncated = is_truncated
        self.result = result
        self.need_clear_history = need_clear_history
        self.finish_reason = finish_reason
        if usage:
            valid_keys = ErnieUsage.__init__.__code__.co_varnames
            filtered_data = {k: v for k, v in usage.items() if k in valid_keys}
            self.usage = ErnieUsage(**filtered_data)
        # self.usage = ErnieUsage(**usage) if usage else None
        self.content_type = content_type


ERNIE_API_ID = get_config("ERNIE_API_ID")
ERNIE_API_SECRET = get_config("ERNIE_API_SECRET")


def get_access_token():
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": ERNIE_API_ID,
        "client_secret": ERNIE_API_SECRET,
    }
    response = requests.post(url, params=params)
    return response.json()["access_token"]


def get_token():
    return get_access_token()


URLS = {
    "ERNIE-4.0-8K": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_pro",
    "ERNIE-4.0-8K-Preview": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-4.0-8k-preview",
    "ERNIE-4.0-8K-0329": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-4.0-8k-0329",
    "ERNIE-4.0-8K-0104": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-4.0-8k-0104",
    "ERNIE-3.5-8K": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
    "ERNIE-3.5-8K-0205": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-3.5-8k-0205",
    "ERNIE-3.5-8K-Preview": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-3.5-8k-preview",
    "ERNIE-3.5-128K": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-3.5-128k",
    "ERNIE-Speed-8K": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie_speed",
    "ERNIE-Speed-128K": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-speed-128k",
    "ERNIE-4.0-8K-Preview-0518": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_adv_pro",
}


def get_ernie_response(
    app, model, msg, **args
) -> Generator[ErnieStreamResponse, None, None]:
    url = URLS[model]
    params = {"access_token": get_access_token()}
    data = {"messages": [{"role": "user", "content": msg}], "stream": True}
    for k, v in args.items():
        data[k] = v
    app.logger.info("ernie request data: {}".format(data))
    response = requests.post(
        url,
        params=params,
        json=data,
        headers={"Content-Type": "application/json"},
        stream=True,
    )
    for res in response.iter_lines():
        res = res.decode("utf-8")
        app.logger.info("ernie response data: {}".format(res))
        if res.startswith("data:"):
            json_data = res[5:].strip()
            # 尝试解析 JSON 数据
            if json_data.replace(" ", "") == "[DONE]":
                return
            parsed_data = json.loads(json_data)
            yield ErnieStreamResponse(**parsed_data)


def chat_ernie(
    app: Flask, model, messages, **args
) -> Generator[ErnieStreamResponse, None, None]:
    url = URLS[model]
    params = {"access_token": get_access_token()}

    data = {}
    if messages[0].get("role", "") == "system":
        data["system"] = messages[0].get("content", "")
        messages = messages[1:]

    data["messages"] = messages
    data["stream"] = True
    for k, v in args.items():
        data[k] = v

    app.logger.info("ernie request data: {}".format(data))
    response = requests.post(
        url,
        params=params,
        json=data,
        headers={"Content-Type": "application/json"},
        stream=True,
    )
    for res in response.iter_lines():
        res = res.decode("utf-8")
        app.logger.info("ernie response data: {}".format(res))
        if res.startswith("data:"):
            json_data = res[5:].strip()
            # 尝试解析 JSON 数据
            if json_data.replace(" ", "") == "[DONE]":
                return
            parsed_data = json.loads(json_data)
            yield ErnieStreamResponse(**parsed_data)


def get_erine_models(app: Flask) -> list[str]:
    return list(URLS.keys())
