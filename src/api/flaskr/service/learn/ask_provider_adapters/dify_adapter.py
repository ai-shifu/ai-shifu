"""Dify ask provider adapter."""

import json
from typing import Any, Generator

import requests
from flask import Flask

from flaskr.service.shifu.shifu_draft_funcs import ASK_PROVIDER_DIFY

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


class DifyAskProviderAdapter:
    provider = ASK_PROVIDER_DIFY

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

        base_url = str(config.get("base_url") or "").strip()
        api_key = str(config.get("api_key") or "").strip()
        if not base_url or not api_key:
            raise AskProviderConfigError(
                "dify base_url/api_key are required in ask_provider_config.config"
            )

        payload: dict[str, Any] = {
            "query": user_query,
            "user": user_id,
            "response_mode": "streaming",
            "auto_generate_name": False,
            "inputs": config.get("inputs", {})
            if isinstance(config.get("inputs"), dict)
            else {},
            "files": [],
        }
        conversation_id = str(config.get("conversation_id") or "").strip()
        if conversation_id:
            payload["conversation_id"] = conversation_id

        url = base_url.rstrip("/") + "/chat-messages"
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
            raise AskProviderTimeoutError("dify request timeout") from exc
        except requests.RequestException as exc:
            raise AskProviderError(f"dify request failed: {exc}") from exc

        response = raise_for_provider_response(response, self.provider)

        for raw_payload in iter_sse_payloads(response):
            if not raw_payload or raw_payload.replace(" ", "") == "[DONE]":
                continue
            try:
                parsed = json.loads(raw_payload)
            except json.JSONDecodeError:
                app.logger.warning("Skip malformed dify payload: %s", raw_payload)
                continue

            event = str(parsed.get("event") or "").strip().lower()
            if event == "error":
                error_message = extract_text(parsed) or str(parsed)
                raise AskProviderError(f"dify error: {error_message}")

            text = extract_text(parsed)
            if text:
                yield AskProviderChunk(content=text)
