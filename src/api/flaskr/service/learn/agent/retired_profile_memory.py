"""Refresh former global profile snapshots without discarding course answers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.profile.api import RETIRED_PROFILE_KEYS
from markdownflow.engine.script import collected_names

if TYPE_CHECKING:
    from flaskr.api.markdownflow import Session


PROFILE_MEMORY_VERSION_KEY = "ai_shifu_profile_memory_version"
_PROFILE_MEMORY_VERSION = 1


def mark_profile_memory_current(session: Session) -> None:
    """Track the application-owned profile scope without changing engine schemas."""
    setattr(session, PROFILE_MEMORY_VERSION_KEY, _PROFILE_MEMORY_VERSION)


def profile_memory_metadata(session: Session) -> dict[str, int]:
    """Serialize the one-time retirement marker beside the engine document."""
    if getattr(session, PROFILE_MEMORY_VERSION_KEY, None) == _PROFILE_MEMORY_VERSION:
        return {PROFILE_MEMORY_VERSION_KEY: _PROFILE_MEMORY_VERSION}
    return {}


def restore_profile_memory_metadata(session: Session, data: dict) -> None:
    """Restore host metadata ignored by the application-independent engine."""
    if data.get(PROFILE_MEMORY_VERSION_KEY) == _PROFILE_MEMORY_VERSION:
        mark_profile_memory_current(session)


def refresh_retired_profile_memory(session: Session, current: dict[str, Any]) -> None:
    """Replace retired global inputs with current course values on session resume.

    Session-owned notes and accepted named answers remain course values. Only
    host-owned memory and substitution snapshots change; saved scripts, learner
    messages and tool results retain their original text.
    """
    if profile_memory_metadata(session):
        # New and already refreshed lesson sessions may contain legitimate
        # course notes in user_memory.
        return
    values = {
        key: session.memory[key] for key in session.memory.keys() & RETIRED_PROFILE_KEYS
    }
    hashes = {
        key: value
        for key, value in session.answer_hashes.items()
        if key in RETIRED_PROFILE_KEYS
    }
    answered = session.answered_memory_keys() & RETIRED_PROFILE_KEYS
    # Match the host's existing named-answer refresh: persisted course edits
    # outrank an older accepted answer, while session-only notes keep precedence.
    authored_answers = answered & collected_names(session.script.script)
    values.update({key: current[key] for key in authored_answers if key in current})
    effective = {**current, **values}
    refresh_deleted_memory(session, RETIRED_PROFILE_KEYS, current=effective)
    session.memory.update(values)
    session.answer_hashes.update(hashes)
    for key in answered:
        session.record_answer(key, values[key])
    if session.initial_variables is not None:
        session.initial_variables = {
            key: effective[key] if key in RETIRED_PROFILE_KEYS else value
            for key, value in session.initial_variables.items()
            if key not in RETIRED_PROFILE_KEYS or key in effective
        }
    mark_profile_memory_current(session)
