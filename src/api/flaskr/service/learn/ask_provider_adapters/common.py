"""Shared helpers for ask provider adapters."""

import json
from functools import lru_cache
from typing import Any, Iterable

import requests

from flaskr.service.config import get_config
from flaskr.util.prompt_loader import load_prompt_template

from .base import AskProviderError


# Placeholders kept by the publish pipeline (prompts/ask.md via
# _make_ask_prompt). At ask time knowledge_rule joins the answering-rules
# list and knowledge_section carries the retrieved material; both are
# removed entirely when there is no material, so the prompt carries neither
# empty knowledge tags nor a dangling rule.
KNOWLEDGE_RULE_PLACEHOLDER = "{knowledge_rule}"
KNOWLEDGE_SECTION_PLACEHOLDER = "{knowledge_section}"


@lru_cache(maxsize=1)
def _knowledge_rule_template() -> str:
    return load_prompt_template("ask_knowledge_rule")


@lru_cache(maxsize=1)
def _knowledge_section_template() -> str:
    return load_prompt_template("ask_knowledge")


def render_knowledge_rule() -> str:
    """Render the answering rule for the knowledge material."""
    return _knowledge_rule_template().strip()


def render_knowledge_section(knowledge_context: str, include_rule: bool) -> str:
    """Render the knowledge section of the ask prompt.

    ``include_rule`` keeps the answering rule inside the section for prompts
    that cannot host it in their answering-rules list.
    """
    section = _knowledge_section_template().replace("{knowledge}", knowledge_context)
    if include_rule:
        section = section.replace(KNOWLEDGE_RULE_PLACEHOLDER, render_knowledge_rule())
    else:
        section = section.replace(KNOWLEDGE_RULE_PLACEHOLDER + "\n", "")
    return section.strip()


def _replace_placeholder(text: str, placeholder: str, replacement: str) -> str:
    if replacement:
        return text.replace(placeholder, replacement)
    # Drop the placeholder together with its trailing blank line so the
    # surrounding lines close up without leftover gaps.
    return (
        text.replace(placeholder + "\n\n", "")
        .replace(placeholder + "\n", "")
        .replace(placeholder, "")
    )


def apply_knowledge_context(system_prompt: str, knowledge_context: str) -> str:
    """Fill or remove the ask-template knowledge rule and section.

    Prompts published before the template gained the placeholders get the
    rendered section (rule included) appended instead, so retrieval results
    are never silently dropped.
    """
    knowledge_context = (knowledge_context or "").strip()
    has_rule = KNOWLEDGE_RULE_PLACEHOLDER in system_prompt
    has_section = KNOWLEDGE_SECTION_PLACEHOLDER in system_prompt

    result = system_prompt
    if has_rule:
        rule = render_knowledge_rule() if knowledge_context else ""
        result = _replace_placeholder(result, KNOWLEDGE_RULE_PLACEHOLDER, rule)
    if has_section:
        section = (
            render_knowledge_section(knowledge_context, include_rule=not has_rule)
            if knowledge_context
            else ""
        )
        return _replace_placeholder(result, KNOWLEDGE_SECTION_PLACEHOLDER, section)
    if not knowledge_context:
        return result
    return (
        result + "\n\n" + render_knowledge_section(knowledge_context, include_rule=True)
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
