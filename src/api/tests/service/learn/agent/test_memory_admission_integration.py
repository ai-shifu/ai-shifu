"""Prove admitted requests persist atomically and reach only the learner's next course lesson."""

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine
from flaskr.service.learn.memory import load_memory
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.repository import create_user_entity
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive, _memory, _observer

REQUEST = "Please remember that I prefer short explanations."


def _engine(allowed: bool) -> Engine:
    """Run a real interaction followed by a grounded note with no author profile definition."""
    phase = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal phase
        phase += 1
        if phase == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="q",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "What helps you learn?"}
                    ),
                )
            }
        elif phase == 2:
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id="note",
                    json_args=json.dumps(
                        {
                            "key": "requested_pace",
                            "value": "short explanations",
                            "request": REQUEST,
                        }
                    ),
                )
            }
        else:
            yield "Here is a short example."

    return Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        memory_request_check=AsyncMock(return_value=allowed),
    )


def _run(
    app: Flask,
    engine: Engine,
    user: str,
    course: str,
    lesson: str,
    answer: str | None = None,
) -> list:
    return list(
        run_agent.run_agent_lesson(
            app,
            engine=engine,
            script="Teach using {{requested_pace}}.",
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            user_input=answer,
            iter_turn=_drive,
        )
    )


@pytest.mark.parametrize("allowed", [True, False])
def test_request_without_a_definition_reaches_next_lesson_only_when_admitted(
    app: Flask, allowed: bool
) -> None:
    """Real SQLite storage and host rehydration preserve the course and learner boundary."""
    with app.app_context():
        user, course, lesson = uuid4().hex, uuid4().hex, uuid4().hex
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
        engine = _engine(allowed)
        _run(app, engine, user, course, lesson)
        _run(app, engine, user, course, lesson, REQUEST)
        db.session.remove()
        assert VariableValue.query.filter_by(
            user_bid=user, shifu_bid=course, key="requested_pace"
        ).count() == int(allowed)
        saved = session_store.load_agent_session(app, user, lesson)
        assert saved.user_memory.get("requested_pace") == (
            "short explanations" if allowed else None
        )
        assert "requested_pace" not in load_memory(app, user, course).variables
        seen = []
        _run(app, _observer(seen), user, course, uuid4().hex)
        assert _memory(seen[0]).get("requested_pace") == (
            "short explanations" if allowed else None
        )
        if allowed:
            assert "Teach using short explanations." in seen[0]
        with unit_of_work():
            other = uuid4().hex
            create_user_entity(user_bid=other, identify=other, nickname="Other learner")
        for owner, context in ((user, uuid4().hex), (other, course)):
            seen = []
            _run(app, _observer(seen), owner, context, uuid4().hex)
            assert "requested_pace" not in _memory(seen[0])


def test_failed_session_save_rolls_back_an_admitted_request(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        user, course, lesson = uuid4().hex, uuid4().hex, uuid4().hex
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
        engine = _engine(allowed=True)
        _run(app, engine, user, course, lesson)
        before = session_store.load_agent_session(app, user, lesson).dumps()
        original = session_store._apply

        def fail(row: object, session: object) -> None:
            original(row, session)
            assert (
                VariableValue.query.filter_by(
                    user_bid=user, key="requested_pace"
                ).count()
                == 1
            )
            message = "injected session save failure"
            raise RuntimeError(message)

        with monkeypatch.context() as patch:
            patch.setattr(session_store, "_apply", fail)
            with pytest.raises(RuntimeError, match="injected session save failure"):
                _run(app, engine, user, course, lesson, REQUEST)
        db.session.remove()
        assert session_store.load_agent_session(app, user, lesson).dumps() == before
        assert VariableValue.query.filter_by(user_bid=user).count() == 0
        assert (
            "requested_pace"
            not in load_memory(
                app, user, course, include_course_variables=True
            ).variables
        )
