"""Refresh read-only cross-course values before a resumed teaching request."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.learn.agent.engine.script import substitution_names
from flaskr.service.profile.api import is_course_reference

if TYPE_CHECKING:
    from flaskr.service.learn.agent.engine.session import Session


def refresh_course_references(
    session: Session, current: dict, *, teaching_brief: str | None = None
) -> None:
    """Replace prior initial substitutions after source edits, deletion or lost authorization."""
    keys = frozenset(
        key
        for key in (
            set(session.all_memory())
            | set(session.initial_variables or {})
            | substitution_names(session.script)
            | set(current)
        )
        if is_course_reference(key)
    )
    refresh_deleted_memory(session, keys, current=current, constraints=teaching_brief)
