"""Check long teaching at the real gateway, durable host and rewind boundaries."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.service.learn.agent import gateway_model as gw
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    MessageTurn,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.engine.teaching_history import project_teaching_history
from flaskr.service.learn.agent.input_budget import INPUT_BUDGET_BYTES
from flaskr.service.learn.agent.rewind import checkpoint_of, restore
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.profile.models import VariableValue
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_gateway_model import FakeChunk, FakeSpan
from tests.service.learn.agent.test_memory_integration import _drive

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from flask import Flask


def _long_session() -> Session:
    session = Session(script=ScriptBundle(script="Teach the next step."))
    session.messages = [ModelRequest(parts=[UserPromptPart("Exact original script.")])]
    for index in range(50):
        session.messages.extend(
            [
                ModelResponse(
                    parts=[
                        TextPart(
                            f"Delivered step {index}. "
                            + "x" * 6000
                            + f" Exact closing {index}."
                        )
                    ]
                ),
                ModelRequest(parts=[UserPromptPart(f"Accepted answer {index}.")]),
            ]
        )
    session.messages.append(ModelResponse(parts=[TextPart("The most recent step.")]))
    return session


@pytest.mark.anyio
async def test_actual_gateway_compacts_teaching_preserves_answers_and_checks_every_read_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    mode = "text"

    def chat(**kwargs: object) -> Iterator[FakeChunk]:
        calls.append(kwargs)
        if mode == "read" and len(calls) == 1:
            marker = json.loads(
                next(
                    m["content"]
                    for m in kwargs["messages"]
                    if m["role"] == "assistant" and '"teaching_excerpt"' in m["content"]
                )
            )
            yield FakeChunk(
                tool_call_deltas=[
                    {
                        "index": 0,
                        "id": "read",
                        "name": "read_teaching",
                        "arguments": json.dumps({"reference": marker["reference"]}),
                    }
                ],
                finish_reason="tool_calls",
            )
        else:
            yield FakeChunk(
                result="Continue with the next useful step.", finish_reason="stop"
            )

    monkeypatch.setattr(gw, "chat_llm", chat)

    async def run(enabled: bool, limit: int = INPUT_BUDGET_BYTES) -> list:
        session = _long_session()
        original = session.to_dict()["messages"]
        engine = Engine(
            gw.GatewayModel(
                None,
                "test",
                user_id="learner",
                span=FakeSpan(),
                input_budget_bytes=limit,
            ),
            memory_context_limit=32768,
            teaching_history_compaction=enabled,
        )
        events = [
            e
            async for e in engine.run_turn(
                session, MessageTurn(text="Continue the next step.")
            )
        ]
        assert session.to_dict()["messages"][: len(original)] == original
        assert session.memory == {}
        return events

    events = await run(enabled=False)
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].code == "input_budget_exceeded"
    assert not calls
    events = await run(enabled=True)
    assert isinstance(events[-1], TurnDone)
    assert len(calls) == 1
    sent = calls[0]
    assert (
        sum(
            m["role"] == "assistant" and '"teaching_excerpt"' in m["content"]
            for m in sent["messages"]
        )
        == 49
    )
    for index in range(50):
        assert any(
            m["content"] == f"Accepted answer {index}." for m in sent["messages"]
        )

    def size(call: dict) -> int:
        return len(
            json.dumps(
                {"messages": call["messages"], "tools": call["tools"]},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )

    projected_size = size(sent)
    assert projected_size < 100_000
    calls.clear()
    assert isinstance((await run(enabled=True, limit=projected_size))[-1], TurnDone)
    calls.clear()
    assert (await run(enabled=True, limit=projected_size - 1))[
        -1
    ].code == "input_budget_exceeded"
    assert not calls
    mode = "read"
    assert isinstance((await run(enabled=True))[-1], TurnDone)
    assert len(calls) == 2
    assert (
        json.loads(calls[-1]["messages"][-1]["content"])["text"]
        == _long_session().messages[1].parts[0].content
    )
    loop_size = size(calls[-1])
    assert loop_size > projected_size
    calls.clear()
    assert (await run(enabled=True, limit=loop_size - 1))[
        -1
    ].code == "input_budget_exceeded"
    assert len(calls) == 1


def test_real_host_retains_original_teaching_and_rewind_invalidates_future_reference(
    app: Flask,
) -> None:
    with app.app_context():
        user, course, lesson = (uuid4().hex for _ in range(3))
        session = Session(script=ScriptBundle(script="Teach."))
        session.messages = [
            ModelRequest(parts=[UserPromptPart("Exact original script.")]),
            ModelResponse(parts=[TextPart("First exact teaching " * 500)]),
        ]
        rewind = checkpoint_of(session)
        session.messages.extend(
            [
                ModelRequest(parts=[UserPromptPart("Accepted old answer.")]),
                ModelResponse(
                    parts=[TextPart("Future exact teaching CODE-823 " * 500)]
                ),
                ModelRequest(parts=[UserPromptPart("Accepted later answer.")]),
                ModelResponse(parts=[TextPart("Recent previous teaching.")]),
                ModelRequest(parts=[UserPromptPart("Accepted last answer.")]),
                ModelResponse(parts=[TextPart("Recent last teaching.")]),
            ]
        )
        original = session.to_dict()["messages"]
        references = project_teaching_history(session.messages)[1]
        reference = next(key for key, text in references.items() if "CODE-823" in text)
        session_store.save_agent_session(
            app, session, user_bid=user, shifu_bid=course, outline_item_bid=lesson
        )
        observed = []

        async def model(
            messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            if (
                isinstance(messages[-1], ModelRequest)
                and messages[-1].parts[-1].part_kind == "tool-return"
            ):
                observed.append(json.loads(messages[-1].parts[-1].content))
                yield "A new useful next step."
            else:
                yield {
                    0: DeltaToolCall(
                        name="read_teaching",
                        tool_call_id="read",
                        json_args=json.dumps({"reference": reference}),
                    )
                }

        engine = Engine(
            FunctionModel(stream_function=model),
            memory_context_limit=32768,
            teaching_history_compaction=True,
        )

        def run() -> list:
            return list(
                run_agent.run_agent_lesson(
                    app,
                    engine=engine,
                    script="Teach.",
                    user_bid=user,
                    shifu_bid=course,
                    outline_bid=lesson,
                    iter_turn=_drive,
                )
            )

        events = run()
        assert observed[-1]["status"] == "found"
        assert "CODE-823" in observed[-1]["text"]
        stored = session_store.load_agent_session(app, user, lesson)
        assert stored.to_dict()["messages"][: len(original)] == original
        visible = "".join(
            str(e.content or "") for e in events if e.type == GeneratedType.CONTENT
        )
        assert "teaching_excerpt" not in visible
        assert "CODE-823" not in visible
        assert stored.memory == {}
        assert "CODE-823" not in json.dumps(stored.user_memory)
        assert VariableValue.query.filter_by(user_bid=user).count() == 0
        restore(stored, rewind)
        assert stored.to_dict()["messages"] == original[: rewind["messages"]]
        assert "CODE-823" not in stored.dumps()
        session_store.save_agent_session(
            app, stored, user_bid=user, shifu_bid=course, outline_item_bid=lesson
        )
        run()
        assert observed[-1] == {"status": "unavailable"}
