"""Refresh canonical nickname inputs without rewriting learner conversation history."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from flaskr.service.learn.agent.engine.memory_context import parse_initial_memory_prompt
from flaskr.service.learn.agent.engine.script import (
    collected_names,
    substitute_variables,
)
from flaskr.service.profile.api import SYS_USER_NICKNAME
from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from flaskr.service.learn.agent.engine.session import Session


def refresh_nickname(session: Session, current: dict[str, Any]) -> None:
    """Make canonical profile edits reach old sessions on their next successful turn.

    Only the host-authored initial memory/script/brief is eligible for repair. Historical
    answers, tool results, displayed assistant content and other memory keys stay intact.
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
                    if (
                        session.initial_variables is not None
                        and SYS_USER_NICKNAME in session.initial_variables
                    ):
                        session.initial_variables[SYS_USER_NICKNAME] = current[
                            SYS_USER_NICKNAME
                        ]
            return


def _refresh_prompt(
    content: str, session: Session, nickname: str, *, answered: bool, pending: bool
) -> str:
    """Replace known host sections only, failing closed on an unfamiliar prompt shape."""
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

    def section(tag: str, text: str, memory: dict) -> str:
        return f"<{tag}>\n{substitute_variables(text, memory, collected=collected)}\n</{tag}>"

    start = parsed.script_start
    # A bounded JSON block can omit a value that the initial script substituted in full.
    # The saved snapshot supplies those missing values; included initial values still win.
    script_memory = {
        **session.user_memory,
        **session.memory,
        **(session.initial_variables or {}),
        **original,
    }
    updated_script_memory = {**script_memory, SYS_USER_NICKNAME: nickname}
    old_script = section("script", session.script.script, script_memory)
    if not content.startswith(old_script, start):
        return content
    suffix = content[start + len(old_script) :]
    # The host re-reads the brief each turn. An older, different brief cannot be reconstructed
    # safely from today's bundle, so leave that unmatched history untouched.
    if session.script.constraints:
        old_brief = "\n\n" + section(
            "constraints", session.script.constraints, script_memory
        )
        if suffix.startswith(old_brief):
            suffix = (
                "\n\n"
                + section(
                    "constraints", session.script.constraints, updated_script_memory
                )
                + suffix[len(old_brief) :]
            )
    memory = json.dumps(updated, ensure_ascii=False, indent=2) if updated else "{}"
    return (
        prefix
        + memory
        + boundary
        + section("script", session.script.script, updated_script_memory)
        + suffix
    )
