"""Refresh deleted course memory without rewriting saved prompt text."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

from markdownflow.engine.memory_context import parse_initial_memory_prompt
from markdownflow.engine.script import collected_names
from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from flaskr.api.markdownflow import Session


def refresh_deleted_memory(
    session: Session,
    deleted: frozenset[str],
    *,
    current: dict | None = None,
) -> None:
    """Refresh removed/recreated memory while preserving every saved script and brief."""
    if not deleted:
        return
    fresh = {key: value for key, value in (current or {}).items() if key in deleted}
    for key in deleted:
        session.memory.pop(key, None)
        session.answer_hashes.pop(key, None)
        session.user_memory.pop(key, None)
    session.user_memory.update(fresh)
    for index, message in enumerate(session.messages):
        if not isinstance(message, ModelRequest):
            continue
        for part_index, part in enumerate(message.parts):
            if not isinstance(part, UserPromptPart):
                continue
            if not isinstance(part.content, str):
                return
            parsed = parse_initial_memory_prompt(part.content)
            if parsed is None:
                return
            collected = collected_names(session.script.script)
            memory = {k: v for k, v in parsed.memory.items() if k not in deleted}
            memory.update(
                {key: value for key, value in fresh.items() if key not in collected}
            )
            content = (
                "<memory>\n"
                + json.dumps(memory, ensure_ascii=False, indent=2)
                + "\n</memory>"
                + parsed.notice
                + "\n\n"
                + part.content[parsed.script_start :]
            )
            parts = list(message.parts)
            parts[part_index] = replace(part, content=content)
            session.messages[index] = replace(message, parts=parts)
            return
