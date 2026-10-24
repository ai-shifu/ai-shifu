"""Preserve actual database answers and sessions when total input is refused."""

import json
from collections.abc import Iterator
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import gateway_model as gw
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine
from flaskr.service.learn.agent.input_budget import INPUT_BUDGET_BYTES
from flaskr.service.learn.memory import load_memory
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.repository import create_user_entity

from tests.service.learn.agent.test_gateway_model import FakeChunk, FakeSpan
from tests.service.learn.agent.test_memory_integration import _drive


def test_failed_total_budget_keeps_named_answer_and_retry_evidence_in_database(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = []

    def chat(**kwargs: object) -> Iterator[FakeChunk]:
        seen.append(kwargs["messages"])
        if len(seen) == 1:
            yield FakeChunk(
                tool_call_deltas=[
                    {
                        "index": 0,
                        "id": "q",
                        "name": "interact",
                        "arguments": json.dumps(
                            {"type": "text", "prompt": "Your goal?", "variable": "goal"}
                        ),
                    }
                ],
                finish_reason="tool_calls",
            )
        else:
            yield FakeChunk(result="Apply your goal.", finish_reason="stop")

    monkeypatch.setattr(gw, "chat_llm", chat)
    with app.app_context():
        user, course, lesson = uuid4().hex, uuid4().hex, uuid4().hex
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            db.session.add(
                Variable(variable_bid=uuid4().hex, shifu_bid=course, key="goal")
            )

        def run(answer: str | None, limit: int) -> run_agent.TurnOutcome:
            model = gw.GatewayModel(
                app,
                "test-model",
                user_id=user,
                span=FakeSpan(),
                input_budget_bytes=limit,
            )
            engine = Engine(model, memory_context_limit=32768, memory_admission=True)
            stream = run_agent.run_agent_lesson(
                app,
                engine=engine,
                script="Ask %{{goal}} and explain.",
                user_bid=user,
                shifu_bid=course,
                outline_bid=lesson,
                user_input=answer,
                iter_turn=_drive,
            )
            while True:
                try:
                    next(stream)
                except StopIteration as stop:
                    return stop.value

        assert run(None, INPUT_BUDGET_BYTES).reason == "interaction"
        initial = session_store.load_agent_session(app, user, lesson).to_dict()[
            "messages"
        ]
        answer = "complete original answer " + "z" * INPUT_BUDGET_BYTES
        failed = run(answer, INPUT_BUDGET_BYTES)
        assert failed.reason is None
        assert failed.error_code == "input_budget_exceeded"
        assert len(seen) == 1
        db.session.remove()
        stored = session_store.load_agent_session(app, user, lesson)
        assert stored.memory["goal"] == answer
        assert stored.answers
        assert not stored.finished
        assert stored.to_dict()["messages"] == initial
        assert load_memory(app, user, course).variables["goal"] == answer
        assert (
            VariableValue.query.filter_by(user_bid=user, key="goal").one().value
            == answer
        )
        assert run(None, INPUT_BUDGET_BYTES * 4).reason == "end"
        db.session.remove()
        retried = session_store.load_agent_session(app, user, lesson)
        assert not retried.answers
        assert retried.memory["goal"] == answer
        assert answer in seen[-1][-1]["content"]
        assert retried.to_dict()["messages"][: len(initial)] == initial
