"""Remove retired cross-course snapshots before the next model request."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.learn.agent.engine.memory_context import parse_initial_memory_prompt
from flaskr.service.learn.agent.engine.script import substitution_names
from flaskr.service.profile.api import is_course_reference
from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from flaskr.service.learn.agent.engine.session import Session


def discard_course_references(
    session: Session, *, teaching_brief: str | None = None
) -> None:
    """Clear old aliases/substitutions; keep original classroom answers and later history."""
    names = (
        set(session.all_memory())
        | set(session.initial_variables or {})
        | substitution_names(session.script)
    )
    for message in session.messages:
        if not isinstance(message, ModelRequest):
            continue
        prompt = next((p for p in message.parts if isinstance(p, UserPromptPart)), None)
        if prompt is not None:
            parsed = (
                parse_initial_memory_prompt(prompt.content)
                if isinstance(prompt.content, str)
                else None
            )
            if parsed is not None:
                names.update(parsed.memory)
            break
    keys = frozenset(key for key in names if is_course_reference(key))
    refresh_deleted_memory(session, keys, constraints=teaching_brief)
    if session.initial_variables is not None:
        session.initial_variables = {
            key: value
            for key, value in session.initial_variables.items()
            if not is_course_reference(key)
        }
