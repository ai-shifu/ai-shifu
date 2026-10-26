"""Cover the boundary between previewing a lesson and taking it.

An author previewing a lesson they are writing is the same person, with the same lesson
identifier, as a learner taking the published one. Without a scope in the key they share a row:
each resumes the other's conversation, and the author's drafts land in a real learner's history.
"""

from __future__ import annotations

from flaskr.service.learn.agent.models import active_key_for

USER = "user-bid"
OUTLINE = "outline-bid"


def test_previewing_and_taking_a_lesson_are_different_sessions() -> None:
    assert active_key_for(USER, OUTLINE, preview_mode=True) != active_key_for(
        USER, OUTLINE, preview_mode=False
    )


def test_taking_a_lesson_is_the_default_scope() -> None:
    """Every caller that does not know about previewing is a learner taking the course."""
    assert active_key_for(USER, OUTLINE) == active_key_for(
        USER, OUTLINE, preview_mode=False
    )


def test_a_key_still_separates_learners_and_lessons() -> None:
    keys = {
        active_key_for(USER, OUTLINE),
        active_key_for("someone-else", OUTLINE),
        active_key_for(USER, "another-lesson"),
        active_key_for(USER, OUTLINE, preview_mode=True),
    }
    assert len(keys) == 4
