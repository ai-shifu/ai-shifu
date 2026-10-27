"""Publish only successful response text when the host enables buffering."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
from markdownflow.engine import (
    ContentDelta,
    Engine,
    ErrorEvent,
    InteractionRequest,
    TurnDone,
)
from pydantic_ai.messages import ModelResponse, TextPart, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from markdownflow.engine import Event
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

pytestmark = pytest.mark.anyio
StreamChunks = AsyncIterator[str | dict[int, DeltaToolCall]]


def _text(events: list[Event]) -> str:
    return "".join(event.text for event in events if isinstance(event, ContentDelta))


def _history_text(messages: list[ModelMessage]) -> str:
    return "".join(
        part.content
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, TextPart)
    )


def _returned(messages: list[ModelMessage], name: str) -> bool:
    return any(
        isinstance(part, ToolReturnPart) and part.tool_name == name
        for message in messages
        for part in message.parts
    )


def _call(name: str, **arguments: object) -> dict[int, DeltaToolCall]:
    return {
        0: DeltaToolCall(name=name, tool_call_id=name, json_args=json.dumps(arguments))
    }


@pytest.mark.parametrize("buffered", [False, True])
async def test_response_buffering_discards_rejected_text_without_changing_default_streaming(
    buffered: bool,
) -> None:
    attempts = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield "Rejected draft.\n"
            yield _call("interact", type="text", prompt="Forbidden question")
        else:
            yield "Corrected content.\n"

    engine = Engine(
        FunctionModel(stream_function=script),
        interaction_check=lambda _spec: "Questions are not allowed in this step",
        buffer_model_responses=buffered,
    )
    session = await engine.new_session("Only present the introduction.")
    events = [event async for event in engine.run_turn(session)]

    assert attempts == 2
    assert _text(events) == (
        "Corrected content.\n" if buffered else "Rejected draft.\nCorrected content.\n"
    )
    assert not any(isinstance(event, ErrorEvent) for event in events)
    if buffered:
        assert "Rejected draft" not in _history_text(session.messages)


async def test_successful_tool_responses_keep_text_before_and_after_the_tool() -> None:
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _returned(messages, "remember"):
            yield "Continue after the tool.\n"
        else:
            yield "Start before the tool.\n<div>Visual</div>\n"
            yield _call("remember", key="pace", value="short", scope="session")

    engine = Engine(FunctionModel(stream_function=script), buffer_model_responses=True)
    session = await engine.new_session("Present the introduction and record the pace.")
    events = [event async for event in engine.run_turn(session)]

    assert _text(events) == (
        "Start before the tool.\n<div>Visual</div>\nContinue after the tool.\n"
    )
    assert session.memory == {"pace": "short"}
    assert _history_text(session.messages) == _text(events)


async def test_successful_text_before_finish_still_suppresses_a_later_farewell() -> (
    None
):
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _returned(messages, "finish"):
            yield "A farewell that must remain hidden."
        else:
            yield "The accepted closing line.\n"
            yield _call("finish", summary="Completed")

    engine = Engine(FunctionModel(stream_function=script), buffer_model_responses=True)
    session = await engine.new_session("Deliver the closing line and finish.")
    events = [event async for event in engine.run_turn(session)]

    assert _text(events) == "The accepted closing line.\n"
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"


async def test_a_rejected_preface_does_not_suppress_a_closing_line_after_finish() -> (
    None
):
    attempts = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield "Rejected preface.\n"
            yield _call("interact", type="text", prompt="Forbidden question")
        elif attempts == 2:
            yield _call("finish", summary="Completed")
            yield "The actual accepted closing line."
        else:
            pytest.fail("Accepted completion must not request closing prose")

    engine = Engine(
        FunctionModel(stream_function=script),
        interaction_check=lambda _spec: "Questions are not allowed in this step",
        buffer_model_responses=True,
    )
    session = await engine.new_session("Deliver the closing line and finish.")
    events = [event async for event in engine.run_turn(session)]

    assert attempts == 2
    assert _text(events) == "The actual accepted closing line."
    assert "Rejected preface" not in _history_text(session.messages)
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"


async def test_plain_text_output_retry_discards_the_unexecuted_interaction_response() -> (
    None
):
    attempts = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield 'Rejected preface.\n<interact type="text" />\n'
        else:
            yield "Accepted question preface.\n"
            yield _call(
                "interact",
                type="text",
                prompt="Your answer?",
                placeholder="Your answer",
            )

    engine = Engine(FunctionModel(stream_function=script), buffer_model_responses=True)
    session = await engine.new_session("Ask the learner a question.")
    events = [event async for event in engine.run_turn(session)]

    assert attempts == 2
    assert _text(events) == "Accepted question preface.\n"
    assert (
        len([event for event in events if isinstance(event, InteractionRequest)]) == 1
    )
    assert "Rejected preface" not in _history_text(session.messages)


async def test_malformed_tool_retry_discards_its_text_before_accepting_a_correction() -> (
    None
):
    attempts = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield "Rejected malformed question.\n"
            yield _call("interact", type="single", prompt="Missing options")
        else:
            yield "Accepted corrected response.\n"

    engine = Engine(FunctionModel(stream_function=script), buffer_model_responses=True)
    session = await engine.new_session("Present the introduction.")
    events = [event async for event in engine.run_turn(session)]

    assert attempts == 2
    assert _text(events) == "Accepted corrected response.\n"
    assert "Rejected malformed question" not in _history_text(session.messages)
