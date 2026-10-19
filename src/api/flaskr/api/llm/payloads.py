"""Extract usage, reasoning, and tool-call data from LiteLLM stream payloads."""

from __future__ import annotations

from typing import Any

import litellm

from flaskr.api.langfuse import (
    normalize_langfuse_output_value,
)

_USAGE_OUTPUT_TEXT_MAX_LENGTH = 12000


def _extract_usage_value(usage: object, key: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(key) or 0)
    return int(getattr(usage, key, 0) or 0)


def _reported_input_cache(usage: object) -> object:
    """Return explicit raw cache metadata; missing fields remain unknown."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        if "input_cache" in usage:
            return usage.get("input_cache")
        details = usage.get("input_tokens_details") or usage.get(
            "prompt_tokens_details"
        )
        return details.get("cached_tokens") if isinstance(details, dict) else None
    value = getattr(usage, "input_cache", None)
    if value is not None:
        return value
    details = getattr(usage, "input_tokens_details", None) or getattr(
        usage, "prompt_tokens_details", None
    )
    if isinstance(details, dict):
        return details.get("cached_tokens")
    return getattr(details, "cached_tokens", None)


def _extract_input_cache(usage: object) -> int:
    """Keep the shared billing conversion while preserving raw reporting separately."""
    return int(_reported_input_cache(usage) or 0)


def _attach_usage_output_text(
    metadata: dict[str, object],
    response_text: str,
) -> dict[str, object]:
    """Store a bounded response excerpt for operator usage detail summaries."""
    normalized_response_text = str(response_text or "").strip()
    if not normalized_response_text or "output_text" in metadata:
        return metadata
    next_metadata = dict(metadata)
    next_metadata["output_text"] = normalized_response_text[
        :_USAGE_OUTPUT_TEXT_MAX_LENGTH
    ]
    return next_metadata


def _extract_reasoning_delta(delta: object) -> str:
    """Return provider reasoning from a normalized LiteLLM stream delta."""

    def _get(value: object, key: str) -> object:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    def _normalize(value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value
        return normalize_langfuse_output_value(value)

    candidates: list[Any] = [
        _get(delta, "reasoning_content"),
        _get(delta, "reasoning"),
    ]
    thinking_blocks = _get(delta, "thinking_blocks")
    if isinstance(thinking_blocks, list):
        block_reasoning = []
        for block in thinking_blocks:
            # Anthropic emits the full accumulated thinking again alongside
            # the signature. Incremental reasoning was already delivered in
            # earlier chunks, so recording the signed snapshot duplicates it.
            if _normalize(_get(block, "signature")):
                continue
            normalized = _normalize(_get(block, "thinking"))
            if normalized:
                block_reasoning.append(normalized)
        if block_reasoning:
            candidates.append("\n".join(block_reasoning))
    provider_fields = _get(delta, "provider_specific_fields")
    if provider_fields:
        candidates.extend(
            [
                _get(provider_fields, "reasoning_content"),
                _get(provider_fields, "reasoning"),
            ]
        )

    for candidate in candidates:
        normalized = _normalize(candidate)
        if normalized:
            return normalized
    return ""


def _build_langfuse_llm_output(
    response_text: str,
    reasoning_text: str,
) -> str | dict[str, str]:
    if not reasoning_text:
        return response_text
    return {
        "content": response_text,
        "reasoning_content": reasoning_text,
    }


class LLMStreamaUsage:
    """Track token usage reported by a streaming LLM response."""

    def __init__(
        self,
        prompt_tokens: object,
        completion_tokens: object,
        total_tokens: object,
        input_cache: object = None,
    ) -> None:
        """Record stream token counts with optional explicit provider cache metadata."""
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.input_cache = input_cache


class LLMStreamResponse:
    """Wrap an LLM stream together with response metadata."""

    def __init__(
        self,
        response_id: object,
        is_end: object,
        is_truncated: object,
        result: object,
        finish_reason: object,
        usage: object,
        tool_call_deltas: list[dict] | None = None,
    ) -> None:
        """Build an LLM stream-chunk response."""
        self.id = response_id

        self.is_end = is_end
        self.is_truncated = is_truncated
        self.result = result
        self.finish_reason = finish_reason
        self.usage = LLMStreamaUsage(**usage) if usage else None
        # Tool-call fragments for this chunk, each {"index", "id", "name", "arguments"}.
        # Always empty unless the caller passes emit_tool_calls=True.
        self.tool_call_deltas = list(tool_call_deltas or [])


def _get_attr(obj: object, name: str) -> object:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _extract_tool_call_deltas(delta: object) -> list[dict]:
    """Normalize a streaming delta's tool_calls into plain dicts.

    Providers hand these back either as objects or as dicts, and a single call's arguments arrive
    split across chunks, so the index is what stitches them back together.
    """
    calls = _get_attr(delta, "tool_calls")
    if not calls:
        return []
    out: list[dict] = []
    for position, call in enumerate(calls):
        function = _get_attr(call, "function") or {}
        index = _get_attr(call, "index")
        out.append(
            {
                "index": position if index is None else index,
                "id": _get_attr(call, "id"),
                "name": _get_attr(function, "name"),
                "arguments": _get_attr(function, "arguments"),
            }
        )
    return out


def _gateway_output_token_count(invoke_model: str, output: str) -> int:
    if not output:
        return 0
    try:
        return max(int(litellm.token_counter(model=invoke_model, text=output) or 0), 0)
    except Exception:
        return 0


def _gateway_output_text(payload: dict[str, object]) -> str:
    """Extract generated text and tool arguments without counting protocol JSON."""
    parts: list[str] = []
    for choice in payload.get("choices") or []:
        message = dict(choice.get("message") or choice.get("delta") or {})
        for output_field in ("content", "reasoning_content", "reasoning"):
            content = message.get(output_field)
            if isinstance(content, list):
                message[output_field] = "".join(
                    part["text"]
                    for part in content
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        parts.append(_extract_reasoning_delta(message))
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            for output_field in ("name", "arguments"):
                value = function.get(output_field)
                if isinstance(value, str):
                    parts.append(value)
    return "".join(parts)


def _gateway_usage_values(
    usage: object,
    *,
    invoke_model: str,
    fallback_input_tokens: int,
    output_capture: str,
) -> tuple[dict[str, int], int, str]:
    if usage is not None:
        values = {
            "input": _extract_usage_value(usage, "prompt_tokens"),
            "output": _extract_usage_value(usage, "completion_tokens"),
            "total": _extract_usage_value(usage, "total_tokens"),
        }
        return values, _extract_input_cache(usage), "litellm"

    output_tokens = _gateway_output_token_count(invoke_model, output_capture)
    return (
        {
            "input": max(int(fallback_input_tokens or 0), 0),
            "output": output_tokens,
            "total": max(int(fallback_input_tokens or 0), 0) + output_tokens,
        },
        0,
        "estimated",
    )
