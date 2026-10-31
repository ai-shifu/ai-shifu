"""Dify ask provider adapter."""

import json
from collections.abc import Generator
from typing import Any

from flask import Flask
from flaskr.common.safe_outbound import (
    OutboundDeadlineExceededError,
    OutboundRedirectError,
    OutboundResponseTooLargeError,
    OutboundUrlPolicy,
    SafeOutboundClient,
    SafeOutboundResponse,
    UnsafeOutboundUrlError,
)
from urllib3.exceptions import HTTPError
from urllib3.exceptions import TimeoutError as UrllibTimeoutError

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
)
from .consts import ASK_PROVIDER_DIFY


def _build_dify_query(user_query: str, messages: list[dict[str, object]]) -> str:
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


def _trusted_dify_origins(app: Flask) -> frozenset[str]:
    configured = app.config.get("DIFY_TRUSTED_ORIGINS", [])
    if isinstance(configured, str):
        values = configured.split(",")
    elif isinstance(configured, (list, tuple, set, frozenset)):
        values = configured
    else:
        values = []
    return frozenset(str(origin).strip() for origin in values if str(origin).strip())


class DifyAskProviderAdapter:
    """Adapt Dify responses to the common ask stream."""

    provider = ASK_PROVIDER_DIFY

    def stream_answer(
        self,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, object]],
        provider_config: dict[str, object],
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
            client = SafeOutboundClient(
                policy=OutboundUrlPolicy(
                    trusted_origins=_trusted_dify_origins(app),
                    max_redirects=3,
                    max_response_bytes=10 * 1024 * 1024,
                    connect_timeout_seconds=5,
                    read_timeout_seconds=provider_timeout_seconds(),
                )
            )
        except ValueError as exc:
            message = "DIFY_TRUSTED_ORIGINS contains an invalid origin"
            raise AskProviderConfigError(message) from exc
        try:
            response = client.request(
                "POST",
                url,
                headers=headers,
                body=json.dumps(payload).encode("utf-8"),
            )
        except (OutboundDeadlineExceededError, UrllibTimeoutError) as exc:
            exception_message = "dify request timeout"
            raise AskProviderTimeoutError(exception_message) from exc
        except (
            HTTPError,
            OutboundRedirectError,
            OutboundResponseTooLargeError,
            UnsafeOutboundUrlError,
        ) as exc:
            message = "dify request was rejected or failed"
            raise AskProviderError(message) from exc

        try:
            with response:
                _raise_for_dify_response(response)

                for raw_payload in iter_sse_payloads(response):
                    if not raw_payload or raw_payload.replace(" ", "") == "[DONE]":
                        continue
                    try:
                        parsed = json.loads(raw_payload)
                    except json.JSONDecodeError:
                        app.logger.warning("Skip malformed dify payload")
                        continue

                    event = str(parsed.get("event") or "").strip().lower()
                    if event == "error":
                        error_message = extract_text(parsed) or "provider error"
                        message = f"dify error: {error_message}"
                        raise AskProviderError(message)

                    text = extract_text(parsed)
                    if text:
                        yield AskProviderChunk(content=text)
        except (OutboundDeadlineExceededError, UrllibTimeoutError) as exc:
            exception_message = "dify request timeout"
            raise AskProviderTimeoutError(exception_message) from exc
        except (HTTPError, OutboundResponseTooLargeError) as exc:
            message = "dify response was rejected or failed"
            raise AskProviderError(message) from exc


def _raise_for_dify_response(response: SafeOutboundResponse) -> None:
    if 200 <= response.status < 300:
        return
    message = f"dify request failed with status {response.status}"
    raise AskProviderError(message)
