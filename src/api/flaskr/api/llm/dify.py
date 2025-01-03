from flask import Flask
from typing import Generator
import requests
import json


class DifyChunkChatCompletionResponse:
    event: str
    # event : message
    task_id: str
    conversation_id: str
    answer: str
    created_at: str

    def __init__(self, **kwargs):
        self.event = kwargs.get("event", "")
        self.task_id = kwargs.get("task_id", "")
        self.conversation_id = kwargs.get("conversation_id", "")
        self.answer = kwargs.get("answer", "")
        self.created_at = kwargs.get("created_at", "")


def dify_chat_message(
    app: Flask, message: str
) -> Generator[DifyChunkChatCompletionResponse, None, None]:
    url = app.config.get("DIFY_URL")
    api_key = app.config.get("DIFY_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {"query": message, "response_mode": "streaming", "auto_generate_name": False}
    response = requests.post(url, headers=headers, json=data, stream=True)
    for res in response.iter_lines():
        res = res.decode("utf-8")
        app.logger.info("dify response data: {}".format(res))
        if res.startswith("data:"):
            json_data = res[5:].strip()
            if json_data.replace(" ", "") == "[DONE]":
                return
            parsed_data = json.loads(json_data)
            yield DifyChunkChatCompletionResponse(**parsed_data)
