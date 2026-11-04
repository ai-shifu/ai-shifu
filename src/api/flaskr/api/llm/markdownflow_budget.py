"""Bound complete mapped model inputs without changing learning evidence."""

import json
from typing import Any

from markdownflow import InputBudgetExceededError

INPUT_BUDGET_BYTES = 262_144


def input_budget_bytes_for(max_input_tokens: int | None) -> int:
    """Size the byte budget from a model's input token ceiling.

    The budget is one byte per input token, never below the fixed 256 KiB
    default, so a model with a known small ceiling refuses nothing it accepted
    before. Lesson text runs about three bytes per token in Chinese and four in
    English, so a budget at the ceiling admits roughly a quarter to a third of it
    in tokens. This is headroom, not a guarantee: the budget counts only the
    `messages`/`tools` JSON, not the provider's chat-template framing or output,
    and the provider remains the final judge of length. Configure the input
    ceiling (not a combined window) where a provider publishes one. Unknown
    models keep the default.
    """
    if max_input_tokens is None:
        return INPUT_BUDGET_BYTES
    return max(INPUT_BUDGET_BYTES, max_input_tokens)


def check_input_budget(
    messages: list[dict[str, Any]], tools: object, *, limit: int
) -> None:
    """Count a canonical UTF-8 envelope, including JSON escaping and tool schemas.

    This application budget is not a provider token count. Nothing is truncated;
    callers retain the complete inputs when an oversized request is refused.
    """
    size = len(
        json.dumps(
            {"messages": messages, "tools": tools},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if size > limit:
        message = f"model input exceeds the application budget ({size} > {limit} bytes)"
        raise InputBudgetExceededError(message)
