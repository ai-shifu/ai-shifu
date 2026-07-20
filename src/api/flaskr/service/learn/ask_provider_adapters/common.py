"""Shared helpers for ask provider adapters."""

import json
from typing import Any, Iterable

import requests

from flaskr.service.config import get_config

from .base import AskProviderError


# Placeholder kept by the publish pipeline (prompts/ask.md via
# _make_ask_prompt) and filled at ask time with retrieval-provider results.
KNOWLEDGE_PLACEHOLDER = "{knowledge}"

# Appended to system prompts published before the template gained the
# knowledge section, so retrieval results are never silently dropped.
KNOWLEDGE_FALLBACK_SECTION_TEMPLATE = (
    "\n\n# Knowledge base material\n"
    "If the material between the <knowledge></knowledge> tags is relevant to "
    "the user's question, answer based on it first.\n"
    "<knowledge>\n\n{knowledge_context}\n\n</knowledge>"
)


def apply_knowledge_context(system_prompt: str, knowledge_context: str) -> str:
    """Fill the ask-template knowledge section with retrieval results."""
    knowledge_context = (knowledge_context or "").strip()
    if KNOWLEDGE_PLACEHOLDER in system_prompt:
        return system_prompt.replace(KNOWLEDGE_PLACEHOLDER, knowledge_context)
    if not knowledge_context:
        return system_prompt
    return system_prompt + KNOWLEDGE_FALLBACK_SECTION_TEMPLATE.format(
        knowledge_context=knowledge_context
    )


def apply_knowledge_to_messages(
    messages: list[dict[str, Any]], knowledge_context: str
) -> list[dict[str, Any]]:
    """Return messages with the first system prompt carrying the knowledge.

    Without a system message, a new one is prepended only when there is
    knowledge to inject.
    """
    updated = [dict(message) for message in messages]
    for message in updated:
        if message.get("role") == "system":
            message["content"] = apply_knowledge_context(
                str(message.get("content") or ""), knowledge_context
            )
            return updated
    knowledge_context = (knowledge_context or "").strip()
    if knowledge_context:
        updated.insert(
            0,
            {
                "role": "system",
                "content": apply_knowledge_context("", knowledge_context),
            },
        )
    return updated


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
