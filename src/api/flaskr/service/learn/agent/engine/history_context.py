"""Compact completed recall results only in the model-facing history projection."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

_COMPACTED_RECALL = json.dumps(
    {
        "status": "history_compacted",
        "notice": "An older recall result was omitted. Call recall again if needed.",
    },
    separators=(",", ":"),
)


def _wire_size(content: str) -> int:
    return len(json.dumps(content, ensure_ascii=False).encode("utf-8"))


def _successful_recall(content: object) -> bool:
    if not isinstance(content, dict):
        return False
    if content.get("status") == "found":
        return set(content) == {"status", "value"}
    if content.get("status") != "keys" or set(content) != {
        "status",
        "keys",
        "next_offset",
        "skipped",
    }:
        return False
    offset, skipped = content["next_offset"], content["skipped"]
    return (
        isinstance(content["keys"], list)
        and all(isinstance(key, str) for key in content["keys"])
        and (offset is None or (type(offset) is int and offset >= 0))
        and type(skipped) is int
        and skipped >= 0
    )


def compact_recall_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Replace large old recall results, retaining the most recent teaching turn.

    Only unique, paired recall calls with recognized successful results qualify.
    All original messages, call arguments, teaching text, learner answers, and
    failed or pending calls remain intact. Callers must keep the stored history
    and append only new run messages, never persist this projection in its place.
    """
    boundary = 0
    calls: Counter[str] = Counter()
    returns: Counter[str] = Counter()
    for index, message in enumerate(messages):
        if isinstance(message, ModelResponse):
            calls.update(
                part.tool_call_id
                for part in message.parts
                if isinstance(part, ToolCallPart)
            )
        elif isinstance(message, ModelRequest):
            returns.update(
                part.tool_call_id
                for part in message.parts
                if isinstance(part, ToolReturnPart)
            )
            if any(
                isinstance(part, UserPromptPart)
                or (isinstance(part, ToolReturnPart) and part.tool_name == "interact")
                for part in message.parts
            ):
                boundary = index

    result = list(messages)
    preceding: set[str] = set()
    for index, message in enumerate(messages[:boundary]):
        if isinstance(message, ModelResponse):
            preceding.update(
                part.tool_call_id
                for part in message.parts
                if isinstance(part, ToolCallPart) and part.tool_name == "recall"
            )
        elif isinstance(message, ModelRequest):
            parts = list(message.parts)
            changed = False
            for part_index, part in enumerate(message.parts):
                if (
                    not isinstance(part, ToolReturnPart)
                    or part.tool_name != "recall"
                    or part.tool_call_id not in preceding
                    or calls[part.tool_call_id] != 1
                    or returns[part.tool_call_id] != 1
                    or not isinstance(part.content, str)
                    or _wire_size(part.content) <= _wire_size(_COMPACTED_RECALL)
                ):
                    continue
                try:
                    content = json.loads(part.content)
                except ValueError:
                    continue
                if not _successful_recall(content):
                    continue
                parts[part_index] = replace(part, content=_COMPACTED_RECALL)
                changed = True
            if changed:
                result[index] = replace(message, parts=parts)
    return result
