"""Verify summary isolation, bounded gateway requests and exact continuation."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent import gateway_model as gw
from flaskr.service.learn.agent.engine import Engine, MessageTurn, Session, TurnDone
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.engine.teaching_history import project_teaching_history
from flaskr.service.learn.agent.teaching_summary import make_teaching_summarizer
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models import ModelRequestParameters

from tests.service.learn.agent.engine.test_teaching_summary import history
from tests.service.learn.agent.test_gateway_model import FakeChunk, FakeSpan

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.mark.anyio
async def test_real_gateway_summary_isolated_billed_named_and_exact_read_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Session(
        script=ScriptBundle(script="Current script must not reach summarizer"),
        messages=history(),
        memory={"private": "Current memory must not reach summarizer"},
    )
    original = ModelMessagesTypeAdapter.dump_json(session.messages)
    calls = []
    _, sources = project_teaching_history(session.messages)
    reference, source = next(iter(sources.items()))

    def fake(**kwargs: object) -> Iterator[FakeChunk]:
        calls.append(kwargs)
        if kwargs["generation_name"] == "agent_teaching_summary":
            assert kwargs["user_id"] == "learner"
            assert kwargs["timeout"] == 8
            assert kwargs["num_retries"] == 0
            assert kwargs["max_tokens"] == 256
            assert kwargs.get("tools", []) == []
            assert len(kwargs["messages"]) == 2
            assert json.loads(kwargs["messages"][1]["content"]) == {
                "historical_teaching": source
            }
            assert "Current memory" not in json.dumps(kwargs["messages"])
            yield FakeChunk(
                "Explained the earlier concept; its original distinction is important."
            )
        else:
            marker = json.loads(kwargs["messages"][2]["content"])
            assert marker["status"] == "teaching_summary"
            assert marker["reference"] == reference
            if len(calls) == 2:
                yield FakeChunk(
                    tool_call_deltas=[
                        {
                            "index": 0,
                            "id": "read",
                            "name": "read_teaching",
                            "arguments": json.dumps({"reference": reference}),
                        }
                    ]
                )
            else:
                page = json.loads(kwargs["messages"][-1]["content"])
                assert page["text"] == source[: len(page["text"])]
                yield FakeChunk("Now continue with a new concept.")

    monkeypatch.setattr(gw, "chat_llm", fake)
    summary_model = gw.GatewayModel(
        None,
        "selected-course-model",
        user_id="learner",
        span=FakeSpan(),
        generation_name="agent_teaching_summary",
        input_budget_bytes=40_960,
        retry_deadline_seconds=8,
        timeout=8,
        num_retries=0,
    )
    engine = Engine(
        gw.GatewayModel(
            None, "selected-course-model", user_id="learner", span=FakeSpan()
        ),
        teaching_history_compaction=True,
        teaching_summarizer=make_teaching_summarizer(summary_model),
    )
    events = [
        event
        async for event in engine.run_turn(session, MessageTurn(text="Next concept"))
    ]
    assert any(isinstance(event, TurnDone) for event in events)
    assert len(calls) == 3
    assert all(call["model"] == "selected-course-model" for call in calls)
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:6]) == original
    assert session.memory == {"private": "Current memory must not reach summarizer"}
    assert len(session.teaching_summaries) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("output", ["", " ", "x" * 1025, "error", "tool"])
async def test_host_rejects_invalid_outputs_without_retries(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    calls = []

    def fake(**kwargs: object) -> Iterator[FakeChunk]:
        calls.append(kwargs)
        if output == "error":
            message = "provider failed"
            raise RuntimeError(message)
        if output == "tool":
            yield FakeChunk(
                tool_call_deltas=[
                    {"index": 0, "id": "write", "name": "remember", "arguments": "{}"}
                ]
            )
        else:
            yield FakeChunk(output)

    monkeypatch.setattr(gw, "chat_llm", fake)
    provider = make_teaching_summarizer(
        gw.GatewayModel(None, "course", user_id="learner", span=FakeSpan())
    )
    assert await provider.summarize("Exact complete historical evidence") is None
    assert len(calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["retry", "chunk", "eof", "disconnect"])
async def test_deadline_closes_gateway_and_preserves_disconnect_cancellation(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    clock = [0.0]
    closed = []
    monkeypatch.setattr(gw.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(gw, "turn_stop_requested", lambda: phase == "disconnect")

    def fake(**kwargs: object) -> Iterator[FakeChunk]:
        try:
            if phase != "eof":
                clock[0] = 9
            if phase == "retry":
                kwargs["retry_cancelled"]()
            yield FakeChunk("late summary")
            clock[0] = 9
        finally:
            closed.append(True)

    monkeypatch.setattr(gw, "chat_llm", fake)
    model = gw.GatewayModel(
        None, "course", user_id="learner", span=FakeSpan(), retry_deadline_seconds=8
    )
    error = asyncio.CancelledError if phase == "disconnect" else TimeoutError
    with pytest.raises(error):
        await model.request([], None, ModelRequestParameters())
    assert closed == [True]


def test_policy_changes_with_selected_model() -> None:
    first = make_teaching_summarizer(
        gw.GatewayModel(None, "first", user_id="learner", span=FakeSpan())
    )
    second = make_teaching_summarizer(
        gw.GatewayModel(None, "second", user_id="learner", span=FakeSpan())
    )
    assert first.policy != second.policy
