"""Project the engine-owned initial memory block when resuming old sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from .script import render_memory_section

if TYPE_CHECKING:
    from .script import ScriptBundle


@dataclass(frozen=True)
class InitialMemoryPrompt:
    """Decoded boundaries of the known engine-owned initial prompt."""

    memory: dict
    script_start: int
    notice: str


def parse_initial_memory_prompt(content: str) -> InitialMemoryPrompt | None:
    """Locate tagged host sections without treating literal tags in JSON values as structure."""
    prefix = "<memory>\n"
    if not content.startswith(prefix):
        return None
    try:
        memory, end = json.JSONDecoder().raw_decode(content, len(prefix))
    except ValueError:
        return None
    closing = "\n</memory>"
    if not isinstance(memory, dict) or not content.startswith(closing, end):
        return None
    start = end + len(closing)
    notice = ""
    if content.startswith("\n\n<memory_context>", start):
        notice_end = content.find("</memory_context>", start)
        if notice_end < 0:
            return None
        notice_end += len("</memory_context>")
        notice, start = content[start:notice_end], notice_end
    if not content.startswith("\n\n<script>\n", start):
        return None
    return InitialMemoryPrompt(memory=memory, script_start=start + 2, notice=notice)


def project_memory_history(
    messages: list[ModelMessage],
    bundle: ScriptBundle,
    *,
    limit: int,
    priority: frozenset[str] = frozenset(),
) -> list[ModelMessage]:
    """Copy only the initial engine prompt for a model request; preserve saved history.

    Later learner messages and tool results are conversation evidence, not memory blocks.
    """
    for index, request in enumerate(messages):
        if not isinstance(request, ModelRequest):
            continue
        for part_index, part in enumerate(request.parts):
            if not isinstance(part, UserPromptPart):
                continue
            if not isinstance(part.content, str):
                return messages
            parsed = parse_initial_memory_prompt(part.content)
            if parsed is None:
                return messages
            projected, omitted = render_memory_section(
                bundle, parsed.memory, limit=limit, priority=priority
            )
            # Use projection metadata, not tags that may occur inside learner JSON values.
            if parsed.notice and not omitted:
                projected += parsed.notice
            parts = list(request.parts)
            parts[part_index] = replace(
                part, content=projected + "\n\n" + part.content[parsed.script_start :]
            )
            result = list(messages)
            result[index] = replace(request, parts=parts)
            return result
    return messages
