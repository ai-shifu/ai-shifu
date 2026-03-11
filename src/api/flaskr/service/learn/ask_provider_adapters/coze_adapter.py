"""Coze ask provider adapter."""

import json
from typing import Any, Generator

import requests
from flask import Flask

from flaskr.service.shifu.shifu_draft_funcs import ASK_PROVIDER_COZE

from .base import (
    AskProviderChunk,
    AskProviderConfigError,
    AskProviderError,
    AskProviderRuntime,
    AskProviderTimeoutError,
)
from .common import (
    extract_text,
    iter_sse_payloads,
    provider_timeout_seconds,
    raise_for_provider_response,
)

DEFAULT_COZE_BASE_URL = "https://api.coze.cn"


class CozeAskProviderAdapter:
    provider = ASK_PROVIDER_COZE

    def stream_answer(
        self,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, Any]],
        provider_config: dict[str, Any],
        runtime: AskProviderRuntime | None = None,
    ) -> Generator[AskProviderChunk, None, None]:
        _ = runtime
        config = provider_config.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        base_url = str(config.get("base_url") or DEFAULT_COZE_BASE_URL).strip()
        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            raise AskProviderConfigError(
                "coze api_key is required in ask_provider_config.config"
            )

        bot_id = str(config.get("bot_id") or "").strip()
        api_path = str(config.get("api_path") or "/v3/chat").strip() or "/v3/chat"
        if api_path.startswith("http"):
            url = api_path
        else:
            url = base_url.rstrip("/") + "/" + api_path.lstrip("/")

        if api_path == "/v3/chat" and not bot_id:
            raise AskProviderConfigError("coze bot_id is required")

        payload: dict[str, Any] = {
            "stream": True,
            "user_id": user_id,
            "additional_messages": [
                {
                    "role": "user",
                    "content": user_query,
                    "content_type": "text",
                }
            ],
        }
        if bot_id:
            payload["bot_id"] = bot_id

        conversation_id = str(config.get("conversation_id") or "").strip()
        if conversation_id:
            payload["conversation_id"] = conversation_id

        extra_body = config.get("extra_body")
        if isinstance(extra_body, dict):
            payload.update(extra_body)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=(5, provider_timeout_seconds()),
            )
        except requests.Timeout as exc:
            raise AskProviderTimeoutError("coze request timeout") from exc
        except requests.RequestException as exc:
            raise AskProviderError(f"coze request failed: {exc}") from exc

        response = raise_for_provider_response(response, self.provider)

        for raw_payload in iter_sse_payloads(response):
            if not raw_payload or raw_payload.replace(" ", "") == "[DONE]":
                continue

            try:
                parsed = json.loads(raw_payload)
            except json.JSONDecodeError:
                app.logger.warning("Skip malformed coze payload: %s", raw_payload)
                continue

            event = str(parsed.get("event") or parsed.get("type") or "").lower()
            if "error" in event:
                error_message = extract_text(parsed) or str(parsed)
                raise AskProviderError(f"coze error: {error_message}")
            if event in {"done", "message_end", "chat.completed"}:
                continue

            text = extract_text(parsed)
            if text:
                yield AskProviderChunk(content=text)
