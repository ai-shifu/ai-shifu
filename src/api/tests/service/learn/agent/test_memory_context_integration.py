"""Verify bounded model context through the actual SQLite learning host."""

import json
from collections.abc import AsyncIterator
from uuid import uuid4

from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine
from flaskr.service.learn.memory import (
    MemoryUpdate,
    VariableMemoryUpdate,
    load_memory,
    stage_memory,
)
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.repository import create_user_entity
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive, _memory


def test_oversized_defined_answer_stays_stored_and_substituted_across_lessons(
    app: Flask,
) -> None:
    """A projection omission must never turn into a profile deletion or truncated answer."""
    with app.app_context():
        user, course = uuid4().hex, uuid4().hex
        answer = "My full original answer.\n" + "z" * 40000
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            db.session.add_all(
                [
                    Variable(variable_bid=uuid4().hex, shifu_bid=course, key=key)
                    for key in ("goal", "pace")
                ]
            )
            stage_memory(
                app,
                user,
                course,
                MemoryUpdate(
                    variables=[
                        VariableMemoryUpdate("goal", answer),
                        VariableMemoryUpdate("pace", "slow"),
                    ]
                ),
            )
        seen = []

        async def model(
            messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str]:
            prompt = next(
                p.content
                for m in messages
                if isinstance(m, ModelRequest)
                for p in m.parts
                if isinstance(p, UserPromptPart)
            )
            seen.append(prompt)
            yield "A useful example."

        engine = Engine(
            FunctionModel(stream_function=model), memory_context_limit=32768
        )
        lessons = [uuid4().hex, uuid4().hex]
        for lesson in lessons:
            list(
                run_agent.run_agent_lesson(
                    app,
                    engine=engine,
                    script="Teach using {{goal}} at {{pace}} pace.",
                    user_bid=user,
                    shifu_bid=course,
                    outline_bid=lesson,
                    iter_turn=_drive,
                )
            )
            db.session.remove()
            stored = session_store.load_agent_session(app, user, lesson)
            assert stored.user_memory["goal"] == answer
            assert load_memory(app, user, course).variables["goal"] == answer
            assert (
                VariableValue.query.filter_by(
                    user_bid=user, shifu_bid=course, key="goal"
                )
                .one()
                .value
                == answer
            )
        assert len(seen) == 2
        for prompt in seen:
            values = _memory(prompt)
            assert len(json.dumps(values, ensure_ascii=False, indent=2)) <= 32768
            assert "goal" not in values
            assert values["pace"] == "slow"
            assert f"Teach using {answer} at slow pace." in prompt
            assert "An absent key is unknown here" in prompt
        assert VariableValue.query.filter_by(user_bid=user).count() == 2
