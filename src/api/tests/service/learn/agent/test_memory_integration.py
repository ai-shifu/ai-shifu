"""Verify learner memory through real agent turns, profile rows and new lesson prompts."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.memory import (
    MemoryUpdate,
    VariableMemoryUpdate,
    load_memory,
    stage_memory,
)
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.repository import create_user_entity
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from flask import Flask

ANSWER = "Practice with a small project.\n" + "é" * 2001


@pytest.fixture
def learner(app: Flask) -> Iterator[tuple[str, str]]:
    """Create course-defined memory keys without replacing profile or session storage."""
    with app.app_context():
        user, course = uuid4().hex, uuid4().hex
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            db.session.add_all(
                Variable(variable_bid=uuid4().hex, shifu_bid=course, key=key)
                for key in ("goal", "pace")
            )
        yield user, course


def _drive(make_events: Callable, **_kwargs: object) -> Iterator:
    """Replace only the thread bridge; execute the real engine and tools to completion."""

    async def collect() -> list:
        return [event async for event in make_events()]

    return iter(asyncio.run(collect()))


def _collector() -> Engine:
    """Ask a named question, then record one durable and one session-only note."""

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        last = messages[-1]
        returns = (
            [part for part in last.parts if isinstance(part, ToolReturnPart)]
            if isinstance(last, ModelRequest)
            else []
        )
        if not returns:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="goal-question",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "Your goal?", "variable": "goal"}
                    ),
                )
            }
        elif returns[0].tool_name == "interact":
            yield {
                index: DeltaToolCall(
                    name="remember",
                    tool_call_id=f"note-{index}",
                    json_args=json.dumps({"key": key, "value": value, "scope": scope}),
                )
                for index, (key, value, scope) in enumerate(
                    [("pace", "slow", "user"), ("scratch", "lesson-only", "session")]
                )
            }
        else:
            yield "We will use your goal for the next example."

    return Engine(FunctionModel(stream_function=model))


def _observer(seen: list[str]) -> Engine:
    """Capture the actual first user message the next model invocation receives."""

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        seen.append(
            next(
                part.content
                for message in messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, UserPromptPart) and isinstance(part.content, str)
            )
        )
        yield "Here is the next example."

    return Engine(FunctionModel(stream_function=model))


def _run(
    app: Flask,
    engine: Engine,
    user: str,
    course: str,
    lesson: str,
    answer: str | None = None,
) -> list:
    events = list(
        run_agent.run_agent_lesson(
            app,
            engine=engine,
            script="Use {{goal}} and the learner's {{pace}} pace.",
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            user_input=answer,
            iter_turn=_drive,
        )
    )
    assert events[-1].type == GeneratedType.BREAK
    return events


def _teach_first(app: Flask, user: str, course: str) -> str:
    """Persist the question and its answer in two independent host requests."""
    lesson = uuid4().hex
    engine = _collector()
    _run(app, engine, user, course, lesson)
    _run(app, engine, user, course, lesson, ANSWER)
    db.session.remove()
    return lesson


def _memory(prompt: str) -> dict:
    """Read the injected memory section separately from the substituted script."""
    return json.loads(prompt.split("<memory>\n", 1)[1].split("\n</memory>", 1)[0])


def test_answer_and_durable_note_reach_the_next_lesson_but_working_notes_do_not(
    app: Flask, learner: tuple[str, str]
) -> None:
    """A new request loads committed course memory, including the exact long answer."""
    user, course = learner
    first = _teach_first(app, user, course)
    stored = session_store.load_agent_session(app, user, first)
    assert stored.memory["goal"] == ANSWER
    assert stored.memory["scratch"] == "lesson-only"
    assert VariableValue.query.filter_by(user_bid=user, key="scratch").count() == 0
    seen = []
    _run(app, _observer(seen), user, course, uuid4().hex)
    memory = _memory(seen[0])
    assert memory["goal"] == ANSWER
    assert memory["pace"] == "slow"
    assert "scratch" not in memory
    script = seen[0].split("<script>\n", 1)[1]
    assert ANSWER in script
    assert "slow" in script
    assert "{{goal}}" not in script
    assert "{{pace}}" not in script


@pytest.mark.parametrize("other", ["learner", "course"])
def test_course_memory_does_not_leak_to_another_learner_or_course(
    app: Flask, learner: tuple[str, str], other: str
) -> None:
    """Identical variable names do not confer access to another scope's answers."""
    user, course = learner
    _teach_first(app, user, course)
    with unit_of_work():
        if other == "learner":
            user = uuid4().hex
            create_user_entity(user_bid=user, identify=user, nickname="Other learner")
        else:
            course = uuid4().hex
            db.session.add_all(
                Variable(variable_bid=uuid4().hex, shifu_bid=course, key=key)
                for key in ("goal", "pace")
            )
    seen = []
    _run(app, _observer(seen), user, course, uuid4().hex)
    assert "goal" not in _memory(seen[0])
    assert "pace" not in _memory(seen[0])
    assert ANSWER not in seen[0]
    assert "lesson-only" not in seen[0]


def test_failed_session_save_rolls_back_answer_and_note_together(
    app: Flask, learner: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure after staging rows cannot make the next lesson see an unsaved answer."""
    user, course = learner
    lesson = uuid4().hex
    engine = _collector()
    _run(app, engine, user, course, lesson)
    before = session_store.load_agent_session(app, user, lesson).dumps()
    original_apply = session_store._apply

    def fail_after_apply(row: object, session: object) -> None:
        original_apply(row, session)
        # Memory has already been staged inside this very transaction.
        assert (
            VariableValue.query.filter_by(user_bid=user, key="goal").one().value
            == ANSWER
        )
        message = "injected session save failure"
        raise RuntimeError(message)

    with monkeypatch.context() as patch:
        patch.setattr(session_store, "_apply", fail_after_apply)
        with pytest.raises(RuntimeError, match="injected session save failure"):
            _run(app, engine, user, course, lesson, ANSWER)
    db.session.remove()
    assert session_store.load_agent_session(app, user, lesson).dumps() == before
    assert VariableValue.query.filter_by(user_bid=user).count() == 0
    seen = []
    _run(app, _observer(seen), user, course, uuid4().hex)
    assert "goal" not in _memory(seen[0])
    assert "pace" not in _memory(seen[0])


@pytest.mark.parametrize("ordering", ["before", "after"])
def test_finishing_bounds_durable_model_notes(
    app: Flask, learner: tuple[str, str], ordering: str
) -> None:
    """Keep legitimate final notes while preventing post-finish profile overwrites."""
    user, course = learner
    lesson = uuid4().hex
    with unit_of_work():
        stage_memory(
            app,
            user,
            course,
            MemoryUpdate(variables=[VariableMemoryUpdate(key="pace", value="slow")]),
        )
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Attempt the same overwrite on either side of the finish call."""
        nonlocal calls
        calls += 1
        if calls in (1, 2):
            remember = (calls == 1) == (ordering == "before")
            yield {
                0: DeltaToolCall(
                    name="remember" if remember else "finish",
                    tool_call_id=f"call-{calls}",
                    json_args=json.dumps(
                        {"key": "pace", "value": "fast", "scope": "user"}
                        if remember
                        else {"summary": "done"}
                    ),
                )
            }
        else:
            yield ""

    events = list(
        run_agent.run_agent_lesson(
            app,
            engine=Engine(FunctionModel(stream_function=model)),
            script="Teach the final example.",
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            iter_turn=_drive,
        )
    )
    assert events[-1].type == GeneratedType.DONE
    db.session.remove()
    expected = "fast" if ordering == "before" else "slow"
    assert load_memory(app, user, course).as_variables()["pace"] == expected
    saved = session_store.load_agent_session(app, user, lesson)
    assert saved.finished is True
    assert saved.user_memory["pace"] == expected
    rows = VariableValue.query.filter_by(user_bid=user, key="pace").all()
    assert len(rows) == (2 if ordering == "before" else 1)
