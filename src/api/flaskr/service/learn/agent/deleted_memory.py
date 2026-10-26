"""Refresh deleted course memory without erasing classroom conversation evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

from flaskr.service.learn.agent.legacy_prompt import (
    historical_collected_names,
    matched_section_length,
)
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
    constraints: str | None = None,
) -> None:
    """Refresh removed keys in the host's initial prompt and preserve later history.

    Recognized legacy prompts are rebuilt from their authored source, so old
    expanded placeholders cannot retain removed values. Authored text stays literal.
    """
    if not deleted:
        return
    saved = session.all_memory()
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
            original = {**saved, **(session.initial_variables or {}), **parsed.memory}
            collected = collected_names(session.script.script)
            historical_collected = historical_collected_names(session.script.script)
            length = matched_section_length(
                part.content,
                parsed.script_start,
                "script",
                session.script.script,
                original,
                historical_collected,
            )
            suffix = part.content[parsed.script_start + (length or 0) :]
            if length is not None and (
                session.script.constraints or constraints is not None
            ):
                old_brief_length = (
                    matched_section_length(
                        suffix,
                        2,
                        "constraints",
                        session.script.constraints,
                        original,
                        historical_collected,
                    )
                    if session.script.constraints and suffix.startswith("\n\n")
                    else 0
                    if not session.script.constraints
                    else None
                )
                if old_brief_length is not None:
                    brief = (
                        session.script.constraints
                        if constraints is None
                        else constraints
                    )
                    new_brief = (
                        f"\n\n<constraints>\n{brief}\n</constraints>" if brief else ""
                    )
                    suffix = (
                        new_brief
                        + suffix[(2 + old_brief_length) if old_brief_length else 0 :]
                    )
            memory = {
                key: value for key, value in parsed.memory.items() if key not in deleted
            }
            memory.update(
                {key: value for key, value in fresh.items() if key not in collected}
            )
            content = (
                "<memory>\n"
                + json.dumps(memory, ensure_ascii=False, indent=2)
                + "\n</memory>"
                + parsed.notice
                + "\n\n"
                + (
                    f"<script>\n{session.script.script}\n</script>"
                    if length is not None
                    else ""
                )
                + suffix
            )
            parts = list(message.parts)
            parts[part_index] = replace(part, content=content)
            session.messages[index] = replace(message, parts=parts)
            if session.initial_variables is not None:
                session.initial_variables = {
                    key: value
                    for key, value in session.initial_variables.items()
                    if key not in deleted
                }
            return
