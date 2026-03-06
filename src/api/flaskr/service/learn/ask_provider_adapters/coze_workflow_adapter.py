"""Coze workflow ask provider adapter (stream_run)."""

import json
from typing import Any, Generator, Iterable

import requests
from flask import Flask

from flaskr.service.shifu.shifu_draft_funcs import ASK_PROVIDER_COZE_WORKFLOW

from .base import (
    AskProviderChunk,
    AskProviderConfigError,
    AskProviderError,
    AskProviderRuntime,
    AskProviderTimeoutError,
)
from .common import extract_text, provider_timeout_seconds, raise_for_provider_response


def _iter_sse_events(response: requests.Response) -> Iterable[tuple[str, str]]:
    """Parse server-sent events into (event, data) tuples.

    Coze workflow streaming response uses SSE fields like:
      id: 0
      event: Message
      data: {"content": "..."}

    Each event is separated by a blank line.
    """

    current_event = ""
    current_data = ""

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = str(raw_line).strip("\r\n")
        stripped = line.strip()

        if not stripped:
            if current_event or current_data:
                yield current_event, current_data
            current_event = ""
            current_data = ""
            continue

        if stripped.startswith("event:"):
            current_event = stripped[6:].strip()
            continue

        if stripped.startswith("data:"):
            payload = stripped[5:].strip()
            if current_data:
                current_data += "\n"
            current_data += payload
            continue

        # ignore: id: / retry: / unknown fields

    if current_event or current_data:
        yield current_event, current_data


class CozeWorkflowAskProviderAdapter:
    provider = ASK_PROVIDER_COZE_WORKFLOW

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
        _ = messages

        config = provider_config.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        base_url = str(config.get("base_url") or "").strip() or "https://api.coze.cn"
        api_key = str(config.get("api_key") or "").strip()
        workflow_id = str(config.get("workflow_id") or "").strip()
        if not api_key or not workflow_id:
            raise AskProviderConfigError(
                "coze_workflow api_key/workflow_id are required in ask_provider_config.config"
            )

        api_path = str(config.get("api_path") or "/v1/workflow/stream_run").strip()
        if api_path.startswith("http"):
            url = api_path
        else:
            url = base_url.rstrip("/") + "/" + api_path.lstrip("/")

        query_parameter = str(config.get("query_parameter") or "input").strip()
        raw_parameters = config.get("parameters")
        parameters: dict[str, Any] = {}
        if isinstance(raw_parameters, dict):
            parameters.update(raw_parameters)

        if query_parameter:
            parameters[query_parameter] = user_query

        payload: dict[str, Any] = {
            "workflow_id": workflow_id,
            "parameters": parameters,
        }

        bot_id = str(config.get("bot_id") or "").strip()
        app_id = str(config.get("app_id") or "").strip()
        if bot_id:
            payload["bot_id"] = bot_id
        if app_id:
            payload["app_id"] = app_id

        workflow_version = str(config.get("workflow_version") or "").strip()
        if workflow_version:
            payload["workflow_version"] = workflow_version

        connector_id = str(config.get("connector_id") or "").strip()
        if connector_id:
            payload["connector_id"] = connector_id

        ext = config.get("ext")
        if isinstance(ext, dict) and ext:
            payload["ext"] = {str(k): str(v) for k, v in ext.items() if v is not None}

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
            raise AskProviderTimeoutError("coze_workflow request timeout") from exc
        except requests.RequestException as exc:
            raise AskProviderError(f"coze_workflow request failed: {exc}") from exc

        response = raise_for_provider_response(response, self.provider)

        for event, data_raw in _iter_sse_events(response):
            normalized_event = str(event or "").strip().lower()
            data_raw = (data_raw or "").strip()

            if normalized_event in {"ping", ""} and not data_raw:
                continue

            if normalized_event == "done":
                break

            parsed: Any = None
            if data_raw:
                try:
                    parsed = json.loads(data_raw)
                except json.JSONDecodeError:
                    parsed = data_raw

            if normalized_event == "error":
                error_message = extract_text(parsed) or str(parsed)
                raise AskProviderError(f"coze_workflow error: {error_message}")

            if normalized_event == "interrupt":
                interrupt_message = extract_text(parsed) or str(parsed)
                raise AskProviderError(
                    f"coze_workflow interrupted: {interrupt_message}"
                )

            if normalized_event != "message":
                # Unknown/unsupported event
                continue

            text = extract_text(parsed)
            if text:
                yield AskProviderChunk(content=text)
