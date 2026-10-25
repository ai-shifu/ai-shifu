"""Refresh canonical nickname inputs without rewriting learner conversation history."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from flaskr.service.learn.agent.legacy_prompt import (
    historical_collected_questions,
    matched_section_length,
)
from flaskr.service.profile.api import SYS_USER_NICKNAME
from markdownflow.engine.memory_context import (
    parse_initial_memory_prompt,
)
from markdownflow.engine.script import collected_questions
from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from flaskr.api.markdownflow import Session


def refresh_nickname(session: Session, current: dict[str, Any]) -> None:
    """Refresh only the initial host memory while keeping authored source literal."""
    if SYS_USER_NICKNAME not in current:
        return
    answered = SYS_USER_NICKNAME in session.memory
    session.memory.pop(SYS_USER_NICKNAME, None)
    pending = any(p.spec.question == SYS_USER_NICKNAME for p in session.pending)
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
            memory = dict(parsed.memory)
            if SYS_USER_NICKNAME not in collected_questions(session.script.script) or (
                not pending and (answered or SYS_USER_NICKNAME in memory)
            ):
                memory[SYS_USER_NICKNAME] = current[SYS_USER_NICKNAME]
            else:
                memory.pop(SYS_USER_NICKNAME, None)
            source_memory = {
                **session.user_memory,
                **session.memory,
                **(session.initial_memory or {}),
                **parsed.memory,
            }
            historical_collected = historical_collected_questions(session.script.script)
            length = matched_section_length(
                part.content,
                parsed.script_start,
                "script",
                session.script.script,
                source_memory,
                historical_collected,
            )
            if length is None:
                return
            # Rewrite only the recognized initial host memory/script. The suffix
            # can contain an earlier brief, extras and the learner's own request.
            suffix = part.content[parsed.script_start + length :]
            if session.script.constraints and suffix.startswith("\n\n"):
                brief_length = matched_section_length(
                    suffix,
                    2,
                    "constraints",
                    session.script.constraints,
                    source_memory,
                    historical_collected,
                )
                if brief_length is not None:
                    suffix = (
                        f"\n\n<constraints>\n{session.script.constraints}\n</constraints>"
                        + suffix[2 + brief_length :]
                    )
            content = (
                "<memory>\n"
                + json.dumps(memory, ensure_ascii=False, indent=2)
                + "\n</memory>"
                + parsed.notice
                + "\n\n<script>\n"
                + session.script.script
                + "\n</script>"
                + suffix
            )
            parts = list(message.parts)
            parts[part_index] = replace(part, content=content)
            session.messages[index] = replace(message, parts=parts)
            if session.initial_memory is not None:
                session.initial_memory.pop(SYS_USER_NICKNAME, None)
            return
