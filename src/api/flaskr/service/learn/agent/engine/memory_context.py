"""Project the engine-owned initial memory block when resuming old sessions."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from .script import render_memory_section

if TYPE_CHECKING:
    from .script import ScriptBundle


def project_memory_history(
    messages: list[ModelMessage],
    bundle: ScriptBundle,
    *,
    limit: int,
    priority: frozenset[str] = frozenset(),
) -> list[ModelMessage]:
    """Copy only the initial engine prompt for a model request; preserve saved history.

    Decode JSON to locate the closing tag: a learner value may itself contain `</memory>`.
    Later learner messages and tool results are conversation evidence, not memory blocks.
    """
    for index, request in enumerate(messages):
        if not isinstance(request, ModelRequest):
            continue
        for part_index, part in enumerate(request.parts):
            if not isinstance(part, UserPromptPart):
                continue
            content = part.content
            if not isinstance(content, str) or not content.startswith("<memory>\n"):
                return messages
            start = len("<memory>\n")
            try:
                memory, end = json.JSONDecoder().raw_decode(content, start)
            except ValueError:
                return messages
            suffix = content[end:]
            # New bounded prompts may already carry the static omission notice.
            closing = "\n</memory>"
            if not isinstance(memory, dict) or not suffix.startswith(closing):
                return messages
            rest = suffix[len(closing) :]
            notice = ""
            if rest.startswith("\n\n<memory_context>"):
                notice_end = rest.find("</memory_context>")
                if notice_end < 0:
                    return messages
                notice_end += len("</memory_context>")
                notice, rest = rest[:notice_end], rest[notice_end:]
            if not rest.startswith("\n\n<script>\n"):
                return messages
            projected = render_memory_section(
                bundle, memory, limit=limit, priority=priority
            )
            # Preserve a prior omission notice: the stored bounded snapshot cannot reconstruct
            # which values were absent from its original projection.
            if notice and "<memory_context>" not in projected:
                projected += notice
            parts = list(request.parts)
            parts[part_index] = replace(part, content=projected + rest)
            result = list(messages)
            result[index] = replace(request, parts=parts)
            return result
        # Only the first user prompt, even if the first request contains just system parts.
    return messages
