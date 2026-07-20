"""Shared helpers for ask provider adapters."""

import json
from functools import lru_cache
from typing import Any, Iterable

import requests

from flaskr.service.config import get_config
from flaskr.util.prompt_loader import load_prompt_template

from .base import AskProviderError


# Placeholder kept by the publish pipeline (prompts/ask.md via
# _make_ask_prompt). At ask time it is replaced with the rendered knowledge
# section when a retrieval provider returned material, or removed entirely so
# the prompt carries no empty knowledge tags.
KNOWLEDGE_SECTION_PLACEHOLDER = "{knowledge_section}"


@lru_cache(maxsize=1)
def _knowledge_section_template() -> str:
    return load_prompt_template("ask_knowledge")


def render_knowledge_section(knowledge_context: str) -> str:
    """Render the provider-agnostic knowledge section of the ask prompt."""
    return (
        _knowledge_section_template().replace("{knowledge}", knowledge_context).strip()
    )


def apply_knowledge_context(system_prompt: str, knowledge_context: str) -> str:
    """Fill or remove the ask-template knowledge section.

    Prompts published before the template gained the placeholder get the
    rendered section appended instead, so retrieval results are never
    silently dropped.
    """
    knowledge_context = (knowledge_context or "").strip()
    section = render_knowledge_section(knowledge_context) if knowledge_context else ""
    if KNOWLEDGE_SECTION_PLACEHOLDER in system_prompt:
        return system_prompt.replace(KNOWLEDGE_SECTION_PLACEHOLDER, section)
    if not section:
        return system_prompt
    return system_prompt + "\n\n" + section


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
