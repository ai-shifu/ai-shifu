"""Finish accepted teaching without paying for another model response."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import (
    ContentDelta,
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
    SegmentEnd,
    Session,
    ToolResult,
    TurnDone,
)
from pydantic_ai import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.toolsets import FunctionToolset

pytestmark = pytest.mark.anyio

StreamChunks = AsyncIterator[str | dict[int, DeltaToolCall]]


def _call(name: str, call_id: str, **arguments: object) -> DeltaToolCall:
    return DeltaToolCall(
        name=name,
        tool_call_id=call_id,
        json_args=json.dumps(arguments),
    )


def _text(events: list[object]) -> str:
    return "".join(event.text for event in events if isinstance(event, ContentDelta))


def _assert_paired_finish(session: Session, call_id: str) -> None:
    parts = [part for message in session.messages for part in message.parts]
    calls = [
        part
        for part in parts
        if isinstance(part, ToolCallPart) and part.tool_call_id == call_id
    ]
    returns = [
        part
        for part in parts
        if isinstance(part, ToolReturnPart) and part.tool_call_id == call_id
    ]
    assert len(calls) == len(returns) == 1
    assert calls[0].tool_name == returns[0].tool_name == "finish"
    call_message = next(
        message for message in session.messages if calls[0] in message.parts
    )
    return_message = next(
        message for message in session.messages if returns[0] in message.parts
    )
    assert return_message.run_id == call_message.run_id
    assert return_message.conversation_id == call_message.conversation_id


@pytest.mark.parametrize("buffered", [False, True])
@pytest.mark.parametrize("listen", [False, True])
async def test_accepted_finish_stops_before_another_request_and_survives_reload(
    buffered: bool,
    listen: bool,
) -> None:
    calls = 0
    closing = "The final lesson point.\n"

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal calls
        calls += 1
        assert calls == 1, "An accepted finish must not request another response"
        yield closing
        yield {0: _call("finish", "finished", summary="Lesson completed")}

    engine = Engine(
        FunctionModel(stream_function=model),
        buffer_model_responses=buffered,
    )
    session = await engine.new_session("Present the final point.", listen_mode=listen)
    events = [event async for event in engine.run_turn(session)]

    assert calls == 1
    assert _text(events) == closing
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert not any(
        isinstance(event, ToolResult) and event.name == "finish" for event in events
    )
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"
    assert events[-1].summary == "Lesson completed"
    assert events[-1].usage == session.usage
    assert session.usage["requests"] == 1
    assert session.finished
    assert not session.interrupted
    _assert_paired_finish(session, "finished")
    if listen:
        segments = [event for event in events if isinstance(event, SegmentEnd)]
        assert "".join(event.narration for event in segments) == closing
        assert events.index(segments[-1]) < len(events) - 1

    restored = Session.loads(session.dumps())
    previous_usage = dict(restored.usage)
    previous_messages = list(restored.messages)
    again = [event async for event in engine.run_turn(restored, ContinueTurn())]
    assert calls == 1
    assert len(again) == 1
    assert isinstance(again[0], TurnDone)
    assert again[0].reason == "finished"
    assert restored.usage == previous_usage
    assert restored.messages == previous_messages
    _assert_paired_finish(restored, "finished")


@pytest.mark.parametrize("remember_first", [True, False])
async def test_finishing_a_tool_batch_keeps_only_notes_written_before_finish(
    remember_first: bool,
) -> None:
    calls = 0

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal calls
        calls += 1
        assert calls == 1, "Sibling tools must finish without another model request"
        note = _call("remember", "note", key="pace", value="slow", scope="session")
        finish = _call("finish", "finished", summary="Lesson completed")
        ordered = [note, finish] if remember_first else [finish, note]
        yield dict(enumerate(ordered))

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(
        "Remember the pace before completing the lesson."
    )
    events = [event async for event in engine.run_turn(session)]

    assert calls == 1
    assert session.memory == ({"pace": "slow"} if remember_first else {})
    updates = [event for event in events if isinstance(event, MemoryUpdated)]
    assert [(event.key, event.value) for event in updates] == (
        [("pace", "slow")] if remember_first else []
    )
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"
    assert session.finished
    assert session.usage["requests"] == 1
    _assert_paired_finish(session, "finished")


@pytest.mark.parametrize("question_first", [True, False])
async def test_finish_respects_a_sibling_question_and_its_restored_answer(
    question_first: bool,
) -> None:
    calls = 0

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal calls
        calls += 1
        assert calls == 1, "The accepted finish already establishes the lesson's end"
        question = _call(
            "interact",
            "last-question",
            type="text",
            prompt="What will you apply?",
            placeholder="Your answer",
            variable="application",
        )
        finish = _call("finish", "finished", summary="Final question delivered")
        ordered = [question, finish] if question_first else [finish, question]
        yield dict(enumerate(ordered))

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask the final question, then finish.")
    first = [event async for event in engine.run_turn(session)]
    assert calls == 1
    questions = [event for event in first if isinstance(event, InteractionRequest)]
    assert [event.id for event in questions] == (
        ["last-question"] if question_first else []
    )
    assert isinstance(first[-1], TurnDone)
    assert first[-1].reason == ("interaction" if question_first else "finished")
    assert session.finished is (not question_first)
    _assert_paired_finish(session, "finished")

    restored = Session.loads(session.dumps())
    if question_first:
        assert [pending.tool_call_id for pending in restored.pending] == [
            "last-question"
        ]
        answer = [
            event
            async for event in engine.run_turn(
                restored,
                InteractionResponseTurn(text="Use smaller steps."),
            )
        ]
        assert calls == 1
        assert not any(
            isinstance(event, (InteractionRequest, ErrorEvent)) for event in answer
        )
        assert isinstance(answer[-1], TurnDone)
        assert answer[-1].reason == "finished"
        assert answer[-1].summary == "Final question delivered"
        assert restored.memory["application"] == "Use smaller steps."
        assert not restored.pending
        assert not restored.answers
        assert restored.finished
        assert restored.usage["requests"] == 1
        _assert_paired_finish(restored, "finished")
    else:
        assert not restored.pending
        assert not restored.memory


async def test_a_rejected_finish_allows_question_recovery_before_valid_completion() -> (
    None
):
    calls = 0
    markup = '<interact type="text" prompt="What will you apply?" />'

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield markup
            yield {0: _call("finish", "rejected-finish", summary="Premature")}
        elif calls == 2:
            assert any(
                isinstance(part, RetryPromptPart)
                for message in messages
                for part in message.parts
            )
            yield {
                0: _call(
                    "interact",
                    "recovered-question",
                    type="text",
                    prompt="What will you apply?",
                    placeholder="Your answer",
                    variable="application",
                )
            }
        else:
            assert calls == 3, "Only the rejected finish should require a correction"
            yield "The accepted closing line.\n"
            yield {0: _call("finish", "accepted-finish", summary="Answer received")}

    engine = Engine(FunctionModel(stream_function=model), buffer_model_responses=True)
    session = await engine.new_session("Ask a question, then explain and finish.")
    first = [event async for event in engine.run_turn(session)]

    assert calls == 2
    assert not session.finished
    assert markup not in _text(first)
    assert [event.id for event in first if isinstance(event, InteractionRequest)] == [
        "recovered-question"
    ]
    restored = Session.loads(session.dumps())
    final = [
        event
        async for event in engine.run_turn(
            restored,
            InteractionResponseTurn(text="Use smaller steps."),
        )
    ]
    assert calls == 3
    assert _text(final) == "The accepted closing line.\n"
    assert not any(isinstance(event, ErrorEvent) for event in final)
    assert isinstance(final[-1], TurnDone)
    assert final[-1].reason == "finished"
    assert final[-1].summary == "Answer received"
    assert restored.finished
    assert restored.memory["application"] == "Use smaller steps."
    assert restored.usage["requests"] == 3
    _assert_paired_finish(restored, "accepted-finish")


async def test_finish_waits_for_a_sibling_tools_required_correction() -> None:
    """A valid finish must not swallow another tool's pending validation retry."""
    calls = 0
    accepted: list[bool] = []

    async def checked(valid: bool) -> str:
        if not valid:
            message = "Correct the required value before ending"
            raise ModelRetry(message)
        accepted.append(valid)
        return "Validated"

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                0: _call("checked", "invalid-value", valid=False),
                1: _call("finish", "finished", summary="Lesson completed"),
            }
        else:
            assert calls == 2, "The corrected tool batch needs no further response"
            assert any(
                isinstance(part, RetryPromptPart) and part.tool_name == "checked"
                for message in messages
                for part in message.parts
            )
            yield {0: _call("checked", "corrected-value", valid=True)}

    engine = Engine(
        FunctionModel(stream_function=model),
        toolsets=[FunctionToolset(tools=[checked])],
    )
    session = await engine.new_session("Validate the required value, then finish.")
    events = [event async for event in engine.run_turn(session)]

    assert calls == 2
    assert accepted == [True]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"
    assert session.finished
    assert session.usage["requests"] == 2
    _assert_paired_finish(session, "finished")
