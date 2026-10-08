"""Refresh deleted course memory without erasing classroom conversation evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

from flaskr.service.learn.agent.engine.memory_context import parse_initial_memory_prompt
from flaskr.service.learn.agent.engine.script import (
    collected_names,
    substitute_variables,
    substitution_names,
)
from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from flaskr.service.learn.agent.engine.session import Session


def _section(tag: str, text: str, values: dict, collected: set[str]) -> str:
    return (
        f"<{tag}>\n{substitute_variables(text, values, collected=collected)}\n</{tag}>"
    )


def refresh_deleted_memory(
    session: Session,
    deleted: frozenset[str],
    *,
    current: dict | None = None,
    constraints: str | None = None,
) -> None:
    """Refresh removed/recreated keys and an optional current initial teaching brief."""
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
            updated = {k: v for k, v in original.items() if k not in deleted}
            updated.update(fresh)
            collected = collected_names(session.script.script)

            suffix = part.content[parsed.script_start :]
            old = _section("script", session.script.script, original, collected)
            if suffix.startswith(old):
                suffix = (
                    _section("script", session.script.script, updated, collected)
                    + suffix[len(old) :]
                )
                if session.script.constraints or constraints is not None:
                    old_brief = (
                        "\n\n"
                        + _section(
                            "constraints",
                            session.script.constraints,
                            original,
                            collected,
                        )
                        if session.script.constraints
                        else ""
                    )
                    start = len(
                        _section("script", session.script.script, updated, collected)
                    )
                    if suffix.startswith(old_brief, start):
                        brief = (
                            session.script.constraints
                            if constraints is None
                            else constraints
                        )
                        new_brief = (
                            "\n\n" + _section("constraints", brief, updated, collected)
                            if brief
                            else ""
                        )
                        suffix = (
                            suffix[:start]
                            + new_brief
                            + suffix[start + len(old_brief) :]
                        )
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
                session.initial_variables.update(
                    {
                        key: value
                        for key, value in fresh.items()
                        if key
                        in substitution_names(
                            replace(session.script, constraints=constraints)
                            if constraints is not None
                            else session.script
                        )
                    }
                )
            return
