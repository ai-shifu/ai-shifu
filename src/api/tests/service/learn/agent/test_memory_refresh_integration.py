"""Exercise current durable answers across stored lesson sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.rewind import RewindPlan, checkpoint_of
from flaskr.service.learn.memory import (
    MemoryUpdate,
    VariableMemoryUpdate,
    stage_memory,
)
from flaskr.service.profile.api import delete_course_memory
from flaskr.service.profile.models import VariableValue
from pydantic_ai.messages import ModelMessagesTypeAdapter

from tests.service.learn.agent.test_memory_integration import (
    ANSWER,
    _collector,
    _drive,
    learner,
)
from tests.service.learn.agent.test_memory_recall_integration import _reader

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.learn.agent.engine import Engine

__all__ = ["learner"]

SCRIPT = "Ask %{{goal}}. Then use the learner's goal for examples."


def _turn(
    app: Flask,
    engine: Engine,
    user: str,
    course: str,
    lesson: str,
    answer: str | None = None,
    rewind: RewindPlan | None = None,
) -> None:
    """Run a real host request against the same authored named question."""
    list(
        run_agent.run_agent_lesson(
            app,
            engine=engine,
            script=SCRIPT,
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            user_input=answer,
            iter_turn=_drive,
            rewind=rewind,
        )
    )


@pytest.mark.parametrize("updated", ["", "Use the revised project.\n" + "é" * 2002])
def test_reloaded_named_answer_uses_current_committed_course_value(
    app: Flask, learner: tuple[str, str], updated: str
) -> None:
    """An old lesson must not shadow an answer updated after its last save."""
    user, course = learner
    lesson = uuid4().hex
    engine = _collector()
    _turn(app, engine, user, course, lesson)
    _turn(app, engine, user, course, lesson, ANSWER)
    db.session.remove()
    before = session_store.load_agent_session(app, user, lesson)
    assert before.memory["goal"] == ANSWER
    original_history = ModelMessagesTypeAdapter.dump_json(before.messages)
    if updated:
        another = uuid4().hex
        _turn(app, engine, user, course, another)
        _turn(app, engine, user, course, another, updated)
    else:
        _update(app, user, course, updated)
    db.session.remove()
    rows = VariableValue.query.filter_by(user_bid=user).count()
    seen: list[dict] = []
    _turn(app, _reader("goal", seen, []), user, course, lesson)
    assert seen == [{"status": "found", "value": updated}]
    db.session.remove()
    after = session_store.load_agent_session(app, user, lesson)
    assert after.all_memory()["goal"] == updated
    assert after.memory["scratch"] == "lesson-only"
    assert (
        ModelMessagesTypeAdapter.dump_json(after.messages[: len(before.messages)])
        == original_history
    )
    assert VariableValue.query.filter_by(user_bid=user).count() == rows


def _update(app: Flask, user: str, course: str, value: str) -> None:
    """Use the same durable staging API as a successful host turn."""
    with unit_of_work():
        stage_memory(
            app,
            user,
            course,
            MemoryUpdate(variables=[VariableMemoryUpdate(key="goal", value=value)]),
        )


@pytest.mark.parametrize("recreated", [False, True])
def test_deleted_answer_cannot_return_from_a_stored_session(
    app: Flask, learner: tuple[str, str], recreated: bool
) -> None:
    """Deletion refresh runs before answer refresh, including a recreated key."""
    user, course = learner
    lesson = uuid4().hex
    engine = _collector()
    _turn(app, engine, user, course, lesson)
    _turn(app, engine, user, course, lesson, ANSWER)
    row = VariableValue.query.filter_by(user_bid=user, key="goal", deleted=0).one()
    delete_course_memory(user, course, row.id)
    if recreated:
        _update(app, user, course, "Recreated answer")
    db.session.remove()
    seen: list[dict] = []
    _turn(app, _reader("goal", seen, []), user, course, lesson)
    after = session_store.load_agent_session(app, user, lesson)
    if recreated:
        # A deleted named answer must be answered again in this lesson.
        assert seen == [{"status": "unavailable"}]
        assert after.user_memory["goal"] == "Recreated answer"
    else:
        assert seen == [{"status": "unavailable"}]
        assert "goal" not in after.all_memory()
    assert "goal" not in after.memory
    assert after.memory["scratch"] == "lesson-only"


def test_failed_resume_does_not_commit_a_partially_refreshed_session(
    app: Flask, learner: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed save retains the old session and the independently committed new value."""
    user, course = learner
    lesson = uuid4().hex
    engine = _collector()
    _turn(app, engine, user, course, lesson)
    _turn(app, engine, user, course, lesson, ANSWER)
    _update(app, user, course, "Current answer")
    db.session.remove()
    before = session_store.load_agent_session(app, user, lesson).dumps()
    rows = VariableValue.query.filter_by(user_bid=user).count()
    original_apply = session_store._apply

    def fail_after_apply(row: object, session: object) -> None:
        original_apply(row, session)
        message = "injected refreshed session save failure"
        raise RuntimeError(message)

    with monkeypatch.context() as patch:
        patch.setattr(session_store, "_apply", fail_after_apply)
        with pytest.raises(
            RuntimeError, match="injected refreshed session save failure"
        ):
            _turn(app, _reader("goal", [], []), user, course, lesson)
    db.session.remove()
    assert session_store.load_agent_session(app, user, lesson).dumps() == before
    assert VariableValue.query.filter_by(user_bid=user).count() == rows
    seen: list[dict] = []
    _turn(app, _reader("goal", seen, []), user, course, lesson)
    assert seen == [{"status": "found", "value": "Current answer"}]


def test_rewind_to_unanswered_question_accepts_new_input_over_current_course_value(
    app: Flask, learner: tuple[str, str]
) -> None:
    """Restoring the old question must not fabricate an answer from the course snapshot."""
    user, course = learner
    lesson = uuid4().hex
    engine = _collector()
    _turn(app, engine, user, course, lesson)
    checkpoint = checkpoint_of(session_store.load_agent_session(app, user, lesson))
    assert "goal" not in checkpoint["memory"]
    assert checkpoint["pending"]
    _turn(app, engine, user, course, lesson, ANSWER)
    _update(app, user, course, "Updated elsewhere")
    db.session.remove()
    _turn(
        app,
        engine,
        user,
        course,
        lesson,
        "New answer after rewind",
        rewind=RewindPlan(checkpoint=checkpoint, replay_values=None),
    )
    db.session.remove()
    seen: list[dict] = []
    _turn(app, _reader("goal", seen, []), user, course, lesson)
    assert seen == [{"status": "found", "value": "New answer after rewind"}]
