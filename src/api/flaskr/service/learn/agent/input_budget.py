"""Bound complete mapped model inputs without changing learning evidence."""

import json
from typing import Any

from .engine.events import InputBudgetExceededError

INPUT_BUDGET_BYTES = 262_144


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
