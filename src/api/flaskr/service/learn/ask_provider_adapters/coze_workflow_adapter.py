"""Coze workflow ask provider adapter."""

import json
from typing import Any, Generator

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


DEFAULT_COZE_WORKFLOW_BASE_URL = "https://api.coze.cn"
WORKFLOW_PATH = "/v1/workflow/run"
WORKFLOW_CATEGORY_ORDER = (
    "concepts",
    "facts",
    "methods",
    "models",
    "quotes",
    "values",
)
WORKFLOW_CATEGORY_LABELS = {
    "concepts": "Concepts",
    "facts": "Facts",
    "methods": "Methods",
    "models": "Models",
    "quotes": "Quotes",
    "values": "Values",
}


def _parse_output_fields(raw_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in raw_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value and key not in fields:
            fields[key] = value
    return fields


def _format_workflow_item(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()

    if not isinstance(item, dict):
        return extract_text(item).strip()

    raw_output = item.get("output")
    output_fields: dict[str, str] = {}
    if isinstance(raw_output, str) and raw_output.strip():
        output_fields = _parse_output_fields(raw_output)

    title = output_fields.get("title") or str(item.get("title") or "").strip()
    summary = (
        output_fields.get("summary")
        or output_fields.get("slice_content")
        or str(item.get("summary") or "").strip()
    )

    if not summary:
        fallback = extract_text(item).strip()
        if fallback and fallback != str(raw_output or "").strip():
            summary = fallback
        elif not title:
            summary = fallback

    if title and summary and summary != title:
        return f"{title}\n{summary}"
    return title or summary or json.dumps(item, ensure_ascii=False)


def _format_workflow_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if isinstance(payload, list):
        lines: list[str] = []
        for index, item in enumerate(payload, start=1):
            formatted = _format_workflow_item(item)
            if not formatted:
                continue
            item_lines = [
                line.strip() for line in formatted.splitlines() if line.strip()
            ]
            if not item_lines:
                continue
            lines.append(f"{index}. {item_lines[0]}")
            lines.extend(item_lines[1:])
        return "\n".join(lines).strip()

    if not isinstance(payload, dict):
        return extract_text(payload).strip()

    ordered_keys = [
        key for key in WORKFLOW_CATEGORY_ORDER if isinstance(payload.get(key), list)
    ]
    ordered_keys.extend(
        key
        for key, value in payload.items()
        if key not in ordered_keys and isinstance(value, list)
    )

    sections: list[str] = []
    for key in ordered_keys:
        items = payload.get(key)
        if not isinstance(items, list):
            continue

        lines = [f"## {WORKFLOW_CATEGORY_LABELS.get(key, key)}"]
        item_count = 0
        for index, item in enumerate(items, start=1):
            formatted = _format_workflow_item(item)
            if not formatted:
                continue
            item_lines = [
                line.strip() for line in formatted.splitlines() if line.strip()
            ]
            if not item_lines:
                continue
            lines.append(f"{index}. {item_lines[0]}")
            lines.extend(item_lines[1:])
            item_count += 1

        if item_count > 0:
            sections.append("\n".join(lines))

    if sections:
        return "\n\n".join(sections).strip()

    direct_text = extract_text(payload).strip()
    if direct_text:
        return direct_text
    return json.dumps(payload, ensure_ascii=False)


def _extract_workflow_text(response_payload: dict[str, Any]) -> str:
    data = response_payload.get("data")
    parsed_data: Any = data

    if isinstance(data, str):
        trimmed = data.strip()
        if not trimmed:
            return ""
        try:
            parsed_data = json.loads(trimmed)
        except json.JSONDecodeError:
            return trimmed

    text = _format_workflow_payload(parsed_data)
    return text.strip()


def _build_workflow_error_message(response_payload: dict[str, Any]) -> str:
    code = response_payload.get("code")
    message = (
        str(
            response_payload.get("msg") or response_payload.get("message") or ""
        ).strip()
        or "unknown error"
    )
    detail = response_payload.get("detail")
    logid = ""
    if isinstance(detail, dict):
        logid = str(detail.get("logid") or "").strip()
    if logid:
        return f"coze_workflow error [{code}]: {message} (logid: {logid})"
    return f"coze_workflow error [{code}]: {message}"


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
        _ = (app, user_id, messages, runtime)
        config = provider_config.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        base_url = str(config.get("base_url") or DEFAULT_COZE_WORKFLOW_BASE_URL).strip()
        api_key = str(config.get("api_key") or "").strip()
        workflow_id = str(config.get("workflow_id") or "").strip()
        if not api_key or not workflow_id:
            raise AskProviderConfigError(
                "coze_workflow api_key/workflow_id are required in ask_provider_config.config"
            )

        query_key = str(config.get("query_key") or "query").strip() or "query"
        parameters = config.get("parameters")
        payload_parameters = dict(parameters) if isinstance(parameters, dict) else {}
        payload_parameters[query_key] = user_query

        payload: dict[str, Any] = {
            "workflow_id": workflow_id,
            "parameters": payload_parameters,
        }

        extra_body = config.get("extra_body")
        if isinstance(extra_body, dict):
            payload.update(extra_body)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        url = base_url.rstrip("/") + WORKFLOW_PATH

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(5, provider_timeout_seconds()),
            )
        except requests.Timeout as exc:
            raise AskProviderTimeoutError("coze_workflow request timeout") from exc
        except requests.RequestException as exc:
            raise AskProviderError(f"coze_workflow request failed: {exc}") from exc

        response = raise_for_provider_response(response, self.provider)

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise AskProviderError("coze_workflow response is not valid json") from exc

        if not isinstance(response_payload, dict):
            raise AskProviderError("coze_workflow response has invalid payload")

        response_code = response_payload.get("code")
        if response_code not in (0, "0"):
            raise AskProviderError(_build_workflow_error_message(response_payload))

        text = _extract_workflow_text(response_payload)
        if not text:
            raise AskProviderError("coze_workflow response has no retrievable text")

        yield AskProviderChunk(content=text)
