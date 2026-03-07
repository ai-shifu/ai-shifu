"""Shared helpers for ask provider adapters."""

import json
from typing import Any, Iterable

import requests

from flaskr.service.config import get_config

from .base import AskProviderError


def provider_timeout_seconds() -> int:
    raw = get_config("ASK_PROVIDER_TIMEOUT_SECONDS")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 20
    return max(value, 1)


def iter_sse_payloads(response: requests.Response) -> Iterable[str]:
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        normalized = line.strip()
        if normalized.startswith("data:"):
            yield normalized[5:].strip()
        else:
            yield normalized


def extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        for item in payload:
            text = extract_text(item)
            if text:
                return text
        return ""
    if not isinstance(payload, dict):
        return ""

    for key in ("answer", "content", "text", "output"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    nested_data = payload.get("data")
    if isinstance(nested_data, str):
        try:
            nested_data = json.loads(nested_data)
        except Exception:
            pass
    nested_text = extract_text(nested_data)
    if nested_text:
        return nested_text

    nested_message = payload.get("message")
    nested_text = extract_text(nested_message)
    if nested_text:
        return nested_text

    return ""


def raise_for_provider_response(
    response: requests.Response, provider: str
) -> requests.Response:
    try:
        response.raise_for_status()
        return response
    except requests.HTTPError as exc:
        detail = ""
        try:
            detail = response.text
        except Exception:
            detail = ""
        message = f"{provider} request failed: {exc}"
        if detail:
            message += f" | {detail[:300]}"
        raise AskProviderError(message) from exc
