"""Verify recall projection at the gateway, durable store, and rewind boundaries."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import gateway_model as gw
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine, ErrorEvent, MessageTurn, TurnDone
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.engine.session import Session
from flaskr.service.learn.agent.input_budget import INPUT_BUDGET_BYTES
from flaskr.service.learn.agent.rewind import checkpoint_of, restore
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.profile.api import delete_course_memory
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.repository import create_user_entity
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_gateway_model import FakeChunk, FakeSpan
from tests.service.learn.agent.test_memory_integration import _drive

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from flask import Flask


def _large_session() -> Session:
    session = Session(script=ScriptBundle(script="Teach the next step."))
    session.messages = [ModelRequest(parts=[UserPromptPart("Original exact script.")])]
    for index in range(50):
        session.messages.extend(
            [
                ModelResponse(
                    parts=[ToolCallPart("recall", {"key": "goal"}, f"r{index}")]
                ),
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            "recall",
                            json.dumps({"status": "found", "value": "x" * 6000}),
                            f"r{index}",
                        )
                    ]
                ),
                ModelResponse(parts=[TextPart(f"Delivered example {index}.")]),
            ]
        )
    session.messages.extend(
        [
            ModelRequest(
                parts=[UserPromptPart("Keep my complete learner message " + "é" * 1000)]
            ),
            ModelResponse(parts=[TextPart("The latest step was delivered.")]),
        ]
    )
    session.memory = {"goal": "Current allowed goal."}
    return session


@pytest.mark.anyio
async def test_real_gateway_recovers_from_old_recall_growth_and_still_enforces_total_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def chat(**kwargs: object) -> Iterator[FakeChunk]:
        calls.append(kwargs)
        yield FakeChunk(result="The next new useful step.", finish_reason="stop")

    monkeypatch.setattr(gw, "chat_llm", chat)

    async def run(
        enabled: bool, limit: int = INPUT_BUDGET_BYTES
    ) -> tuple[Session, list]:
        engine = Engine(
            gw.GatewayModel(
                None,
                "test",
                user_id="learner",
                span=FakeSpan(),
                input_budget_bytes=limit,
            ),
            memory_recall=True,
            recall_history_compaction=enabled,
        )
        session = _large_session()
        original = session.to_dict()["messages"]
        events = [
            e
            async for e in engine.run_turn(
                session, MessageTurn(text="Teach the next step.")
            )
        ]
        assert session.to_dict()["messages"][: len(original)] == original
        assert session.memory == {"goal": "Current allowed goal."}
        assert not session.finished
        assert all(
            "history_compacted" not in str(p.content)
            for m in session.messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        )
        return session, events

    _, refused = await run(enabled=False)
    assert isinstance(refused[-1], ErrorEvent)
    assert refused[-1].code == "input_budget_exceeded"
    assert not calls
    _, success = await run(enabled=True)
    assert isinstance(success[-1], TurnDone)
    assert len(calls) == 1
    sent = calls[0]
    assert (
        sum(
            m["role"] == "tool" and '"history_compacted"' in m["content"]
            for m in sent["messages"]
        )
        == 50
    )
    assert all(
        any(m["content"] == f"Delivered example {i}." for m in sent["messages"])
        for i in range(50)
    )
    projected_size = len(
        json.dumps(
            {"messages": sent["messages"], "tools": sent["tools"]},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    assert projected_size < 65536
    calls.clear()
    _, exact = await run(enabled=True, limit=projected_size)
    assert isinstance(exact[-1], TurnDone)
    assert len(calls) == 1
    calls.clear()
    _, oversized = await run(enabled=True, limit=projected_size - 1)
    assert oversized[-1].code == "input_budget_exceeded"
    assert not calls


@pytest.mark.parametrize("change", ["update", "delete"])
def test_durable_host_projects_only_requests_and_recall_uses_current_authorization(
    app: Flask, change: str
) -> None:
    with app.app_context():
        user, course, lesson = (uuid4().hex for _ in range(3))
        original_value = "Original value " + "é" * 2000
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            db.session.add(
                Variable(shifu_bid=course, key="goal", variable_bid=uuid4().hex)
            )
            row = VariableValue(
                user_bid=user,
                shifu_bid=course,
                key="goal",
                value=original_value,
                variable_value_bid=uuid4().hex,
            )
            db.session.add(row)
        row_id = row.id
        session = Session(script=ScriptBundle(script="Teach."))
        session.messages = [
            ModelRequest(parts=[UserPromptPart("Original teaching script.")]),
            ModelResponse(parts=[ToolCallPart("recall", {"key": "goal"}, "old")]),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        "recall",
                        json.dumps({"status": "found", "value": original_value}),
                        "old",
                    )
                ]
            ),
            ModelResponse(parts=[TextPart("Original delivered teaching.")]),
        ]
        rewind = checkpoint_of(session)
        session.messages.extend(
            [
                ModelRequest(
                    parts=[UserPromptPart("Another accepted learner request.")]
                ),
                ModelResponse(parts=[TextPart("More useful teaching.")]),
            ]
        )
        original_history = session.to_dict()["messages"]
        session_store.save_agent_session(
            app, session, user_bid=user, shifu_bid=course, outline_item_bid=lesson
        )
        if change == "delete":
            delete_course_memory(user, course, row_id)
        else:
            with unit_of_work():
                VariableValue.query.filter_by(
                    id=row_id
                ).one().value = "Updated authorized fact."
        db.session.remove()
        seen = []

        async def model(
            messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            returns = [
                p
                for m in messages
                if isinstance(m, ModelRequest)
                for p in m.parts
                if isinstance(p, ToolReturnPart)
            ]
            if returns[-1].tool_call_id == "old":
                assert json.loads(returns[0].content)["status"] == "history_compacted"
                yield {
                    0: DeltaToolCall(
                        name="recall", tool_call_id="fresh", json_args='{"key":"goal"}'
                    )
                }
            else:
                seen.append(json.loads(returns[-1].content))
                yield "Apply the current fact if available."

        events = list(
            run_agent.run_agent_lesson(
                app,
                engine=Engine(
                    FunctionModel(stream_function=model),
                    memory_recall=True,
                    recall_history_compaction=True,
                ),
                script="Teach.",
                user_bid=user,
                shifu_bid=course,
                outline_bid=lesson,
                iter_turn=_drive,
            )
        )
        assert seen == [
            {"status": "unavailable"}
            if change == "delete"
            else {"status": "found", "value": "Updated authorized fact."}
        ]
        visible = "".join(
            str(e.content or "") for e in events if e.type == GeneratedType.CONTENT
        )
        assert "history_compacted" not in visible
        assert "status" not in visible
        stored = session_store.load_agent_session(app, user, lesson)
        assert stored.to_dict()["messages"][: len(original_history)] == original_history
        assert all(
            "history_compacted" not in str(p.content)
            for m in stored.messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        )
        assert VariableValue.query.filter_by(
            user_bid=user, shifu_bid=course, deleted=0
        ).count() == (0 if change == "delete" else 1)
        restored = Session.loads(stored.dumps())
        restore(restored, rewind)
        assert len(restored.messages) == rewind["messages"]
        assert restored.to_dict()["messages"] == original_history[: rewind["messages"]]
        assert "More useful teaching." not in restored.dumps()
        assert (
            json.loads(restored.messages[2].parts[0].content)["value"] == original_value
        )
