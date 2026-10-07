"""Refresh canonical nickname inputs without rewriting learner conversation history."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

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
            return


def _refresh_prompt(
    content: str, session: Session, nickname: str, *, answered: bool, pending: bool
) -> str:
    """Replace known host sections only, failing closed on an unfamiliar prompt shape."""
    prefix = "<memory>\n"
    if not content.startswith(prefix):
        return content
    try:
        original, end = json.JSONDecoder().raw_decode(content, len(prefix))
    except ValueError:
        return content
    boundary = "\n</memory>\n\n"
    if not isinstance(original, dict) or not content.startswith(boundary, end):
        return content
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

    start = end + len(boundary)
    old_script = section("script", session.script.script, original)
    if not content.startswith(old_script, start):
        return content
    suffix = content[start + len(old_script) :]
    # The host re-reads the brief each turn. An older, different brief cannot be reconstructed
    # safely from today's bundle, so leave that unmatched history untouched.
    if session.script.constraints:
        old_brief = "\n\n" + section(
            "constraints", session.script.constraints, original
        )
        if suffix.startswith(old_brief):
            suffix = (
                "\n\n"
                + section("constraints", session.script.constraints, updated)
                + suffix[len(old_brief) :]
            )
    memory = json.dumps(updated, ensure_ascii=False, indent=2) if updated else "{}"
    return (
        prefix
        + memory
        + boundary
        + section("script", session.script.script, updated)
        + suffix
    )
