"""Bound complete mapped model inputs without changing learning evidence."""

import json
from typing import Any

from markdownflow import InputBudgetExceededError

INPUT_BUDGET_BYTES = 262_144


def input_budget_bytes_for(max_input_tokens: int | None) -> int:
    """Size the byte budget from a model's input token ceiling.

    A token of real text never encodes fewer than one UTF-8 byte (Chinese runs
    about three bytes per token, English about four), and the JSON envelope this
    budget counts adds more bytes than the chat template adds tokens. So a byte
    budget equal to the token ceiling cannot admit a request the model would
    reject for length. Unknown models keep the fixed default.
    """
    if max_input_tokens is None:
        return INPUT_BUDGET_BYTES
    return max_input_tokens


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
