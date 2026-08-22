"""Dify ask provider adapter."""

import json
from collections.abc import Generator
from typing import Any

import requests
from flask import Flask

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
from .consts import ASK_PROVIDER_DIFY


def _build_dify_query(user_query: str, messages: list[dict[str, Any]]) -> str:
    if not isinstance(messages, list) or not messages:
        return user_query

    role_map = {
        "system": "system",
        "user": "user",
        "assistant": "assistant",
    }
    transcript_lines: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = role_map.get(str(message.get("role") or "").strip().lower())
        content = str(message.get("content") or "").strip()
        if not role or not content:
            continue
        transcript_lines.append(f"[{role}]\n{content}")

    if not transcript_lines:
        return user_query

    return "\n\n".join(transcript_lines)


class DifyAskProviderAdapter:
    """Adapt Dify responses to the common ask stream."""

    provider = ASK_PROVIDER_DIFY

    def stream_answer(
        self: object,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, Any]],
        provider_config: dict[str, Any],
        runtime: AskProviderRuntime | None = None,
    ) -> Generator[AskProviderChunk, None, None]:
        """Stream answer chunks from the configured provider."""
        _ = runtime
        config = provider_config.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        base_url = str(config.get("base_url") or "").strip()
        api_key = str(config.get("api_key") or "").strip()
        if not base_url or not api_key:
            exception_message = (
                "dify base_url/api_key are required in ask_provider_config.config"
            )
            raise AskProviderConfigError(exception_message)

        contextual_query = _build_dify_query(user_query, messages)
        payload: dict[str, Any] = {
            "query": contextual_query,
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
            exception_message = "dify request timeout"
            raise AskProviderTimeoutError(exception_message) from exc
        except requests.RequestException as exc:
            message = f"dify request failed: {exc}"
            raise AskProviderError(message) from exc

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
                message = f"dify error: {error_message}"
                raise AskProviderError(message)

            text = extract_text(parsed)
            if text:
                yield AskProviderChunk(content=text)
