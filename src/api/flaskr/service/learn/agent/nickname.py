"""Refresh canonical nickname inputs without rewriting learner conversation history."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from flaskr.service.profile.api import SYS_USER_NICKNAME
from markdownflow.engine.memory_context import parse_initial_memory_prompt
from markdownflow.engine.script import collected_names
from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from flaskr.api.markdownflow import Session


def refresh_nickname(session: Session, current: dict[str, Any]) -> None:
    """Make canonical profile edits reach old sessions on their next successful turn.

    Only the host-authored initial memory envelope is refreshed. Authored script and
    brief content, answers, tool results and other memory keys stay intact.
    A pending nickname question still receives its fresh answer through the engine normally.
    """
    if SYS_USER_NICKNAME not in current:
        return
    answered = SYS_USER_NICKNAME in session.memory
    session.memory.pop(SYS_USER_NICKNAME, None)
    pending = any(p.spec.variable == SYS_USER_NICKNAME for p in session.pending)
    for index, message in enumerate(session.messages):
        if not isinstance(message, ModelRequest):
            continue
        for part_index, part in enumerate(message.parts):
            if not isinstance(part, UserPromptPart):
                continue
            if isinstance(part.content, str):
                content = _refresh_prompt(
                    part.content,
                    session,
                    current[SYS_USER_NICKNAME],
                    answered=answered,
                    pending=pending,
                )
                if content != part.content:
                    parts = list(message.parts)
                    parts[part_index] = replace(part, content=content)
                    session.messages[index] = replace(message, parts=parts)
            return


def _refresh_prompt(
    content: str, session: Session, nickname: str, *, answered: bool, pending: bool
) -> str:
    """Refresh known memory JSON without changing the saved authored sections."""
    parsed = parse_initial_memory_prompt(content)
    if parsed is None:
        return content
    prefix = "<memory>\n"
    original = parsed.memory
    boundary = "\n</memory>" + parsed.notice + "\n\n"
    collected = collected_names(session.script.script)
    updated = dict(original)
    if SYS_USER_NICKNAME not in collected or (
        not pending and (answered or SYS_USER_NICKNAME in original)
    ):
        updated[SYS_USER_NICKNAME] = nickname
    else:
        updated.pop(SYS_USER_NICKNAME, None)

    memory = json.dumps(updated, ensure_ascii=False, indent=2) if updated else "{}"
    return prefix + memory + boundary + content[parsed.script_start :]
