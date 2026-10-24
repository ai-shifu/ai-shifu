"""Verify exact recall against real host storage, deletion and reference refresh."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.profile.api import delete_course_memory
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.repository import create_user_entity
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive
from tests.service.profile.test_course_references import (
    _published_text,
    _value,
    context,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import SimpleNamespace

    from flask import Flask

__all__ = ["context"]


def _reader(key: str, seen: list[dict], prompts: list[str]) -> Engine:
    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        last = messages[-1]
        returns = (
            [p for p in last.parts if isinstance(p, ToolReturnPart)]
            if isinstance(last, ModelRequest)
            else []
        )
        if returns:
            seen.extend(json.loads(p.content) for p in returns)
            yield "A useful example."
        else:
            prompts.append(
                next(
                    p.content
                    for m in messages
                    if isinstance(m, ModelRequest)
                    for p in m.parts
                    if isinstance(p, UserPromptPart)
                )
            )
            yield {
                0: DeltaToolCall(
                    name="recall",
                    tool_call_id=uuid4().hex,
                    json_args=json.dumps({"key": key}),
                )
            }

    return Engine(
        FunctionModel(stream_function=model),
        memory_recall=True,
        memory_context_limit=100,
    )


def test_real_host_recalls_omitted_values_across_lessons_without_crossing_scopes(
    app: Flask,
) -> None:
    with app.app_context():
        user, other, course, another = (uuid4().hex for _ in range(4))
        values = {
            (user, course): "First learner " + "é" * 2000,
            (other, course): "Other learner",
            (user, another): "Another course",
        }
        with unit_of_work():
            for identity in (user, other):
                create_user_entity(
                    user_bid=identity, identify=identity, nickname="Learner"
                )
            for bid in (course, another):
                db.session.add(
                    Variable(shifu_bid=bid, key="goal", variable_bid=uuid4().hex)
                )
            for (identity, bid), value in values.items():
                db.session.add(
                    VariableValue(
                        user_bid=identity,
                        shifu_bid=bid,
                        key="goal",
                        value=value,
                        variable_value_bid=uuid4().hex,
                    )
                )
        before = [
            (v.id, v.value) for v in VariableValue.query.order_by(VariableValue.id)
        ]
        for (identity, bid), value in values.items():
            seen, prompts = [], []
            engine = _reader("goal", seen, prompts)
            for _ in range(2):
                lesson = uuid4().hex
                events = list(
                    run_agent.run_agent_lesson(
                        app,
                        engine=engine,
                        script="Teach a useful example.",
                        user_bid=identity,
                        shifu_bid=bid,
                        outline_bid=lesson,
                        iter_turn=_drive,
                    )
                )
                visible = "".join(
                    str(e.content or "")
                    for e in events
                    if e.type == GeneratedType.CONTENT
                )
                assert "status" not in visible
                assert value not in visible
                db.session.remove()
                assert (
                    session_store.load_agent_session(app, identity, lesson).user_memory[
                        "goal"
                    ]
                    == value
                )
            assert seen == [{"status": "found", "value": value}] * 2
            if identity == user and bid == course:
                assert all(
                    "goal" not in json.JSONDecoder().raw_decode(p, len("<memory>\n"))[0]
                    for p in prompts
                )
        assert [
            (v.id, v.value) for v in VariableValue.query.order_by(VariableValue.id)
        ] == before


def test_resumed_host_recall_cannot_restore_a_deleted_value(app: Flask) -> None:
    with app.app_context():
        user, course, lesson = (uuid4().hex for _ in range(3))
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            db.session.add(
                Variable(shifu_bid=course, key="goal", variable_bid=uuid4().hex)
            )
            row = VariableValue(
                user_bid=user,
                shifu_bid=course,
                key="goal",
                value="old permitted note",
                variable_value_bid=uuid4().hex,
            )
            db.session.add(row)
        row_id = row.id
        seen, prompts = [], []
        args = {
            "app": app,
            "engine": _reader("goal", seen, prompts),
            "script": "Teach.",
            "user_bid": user,
            "shifu_bid": course,
            "outline_bid": lesson,
            "iter_turn": _drive,
        }
        list(run_agent.run_agent_lesson(**args))
        original = session_store.load_agent_session(app, user, lesson).to_dict()[
            "messages"
        ]
        delete_course_memory(user, course, row_id)
        db.session.remove()
        list(run_agent.run_agent_lesson(**args))
        assert seen == [
            {"status": "found", "value": "old permitted note"},
            {"status": "unavailable"},
        ]
        stored = session_store.load_agent_session(app, user, lesson)
        assert "goal" not in stored.all_memory()
        # Previously recalled data remains historical evidence, not current memory.
        old_returns = [
            p
            for m in stored.messages[: len(original)]
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        ]
        assert any(
            json.loads(p.content).get("value") == "old permitted note"
            for p in old_returns
        )
        assert (
            VariableValue.query.filter_by(
                user_bid=user, shifu_bid=course, key="goal", deleted=0
            ).count()
            == 0
        )


@pytest.mark.parametrize("change", ["update", "remove", "delete", "transfer"])
def test_recall_never_loads_retired_cross_course_references(
    context: SimpleNamespace, change: str
) -> None:
    seen, prompts = [], []
    args = {
        "app": context.app,
        "engine": _reader(context.key, seen, prompts),
        "script": context.reference_text,
        "user_bid": context.user,
        "shifu_bid": context.target,
        "outline_bid": context.outline,
        "iter_turn": _drive,
    }
    list(run_agent.run_agent_lesson(**args))
    with unit_of_work():
        if change == "update":
            _value(context, "Updated source")
        elif change == "delete":
            _value(context, "", deleted=1)
        elif change == "remove":
            _published_text(context, "No source reference.")
        else:
            for model in (DraftShifu, PublishedShifu):
                model.query.filter_by(
                    shifu_bid=context.source
                ).one().created_user_bid = uuid4().hex
    db.session.remove()
    list(run_agent.run_agent_lesson(**args))
    assert seen == [{"status": "unavailable"}] * 2
    assert (
        VariableValue.query.filter_by(
            user_bid=context.user, shifu_bid=context.target
        ).count()
        == 0
    )
