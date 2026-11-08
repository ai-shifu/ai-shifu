"""Verify bounded model context through the actual SQLite learning host."""

import json
from collections.abc import AsyncIterator
from uuid import uuid4

from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.memory import (
    MemoryUpdate,
    VariableMemoryUpdate,
    load_memory,
    stage_memory,
)
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.repository import create_user_entity
from markdownflow.engine import Engine
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive, _memory, _observer


def test_oversized_defined_answer_stays_stored_without_expanding_script(
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
            assert "Teach using {{goal}} at {{pace}} pace." in prompt
            assert answer not in prompt
            assert "An absent key is unknown here" in prompt
        assert VariableValue.query.filter_by(user_bid=user).count() == 2


def test_exact_question_reference_reads_the_answer_from_an_earlier_lesson(
    app: Flask,
) -> None:
    user, course, first_lesson = (uuid4().hex for _ in range(3))
    question = "What would you like to learn?"
    answer = "Geometry"

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        if any(
            isinstance(part, ToolReturnPart)
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
        ):
            yield "We will use this in the next lesson."
            return
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="goal",
                json_args=json.dumps(
                    {
                        "type": "text",
                        "question": question,
                        "placeholder": "Share your goal",
                    }
                ),
            )
        }

    with app.app_context():
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
        for submitted in (None, answer):
            list(
                run_agent.run_agent_lesson(
                    app,
                    engine=Engine(FunctionModel(stream_function=model)),
                    script=f"?[{{{{ {question} }}}}...Share your goal]",
                    user_bid=user,
                    shifu_bid=course,
                    outline_bid=first_lesson,
                    user_input=submitted,
                    iter_turn=_drive,
                )
            )
        db.session.remove()
        assert [
            (row.key, row.value)
            for row in VariableValue.query.filter_by(
                user_bid=user, shifu_bid=course
            ).all()
        ] == [(question, answer)]
        with unit_of_work():
            db.session.add_all(
                VariableValue(
                    variable_value_bid=uuid4().hex,
                    user_bid=user,
                    shifu_bid=course,
                    key=f"Other question {index}?",
                    value="Another answer",
                )
                for index in range(101)
            )
        assert (
            question
            not in load_memory(
                app, user, course, include_course_variables=True
            ).variables
        )

        seen: list[str] = []
        list(
            run_agent.run_agent_lesson(
                app,
                engine=_observer(seen),
                script=f"Build on {{{{ {question} }}}} with a practice problem.",
                user_bid=user,
                shifu_bid=course,
                outline_bid=uuid4().hex,
                iter_turn=_drive,
            )
        )
        assert _memory(seen[0])[question] == answer
