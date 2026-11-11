"""Replay a lesson opening whose prose was duplicated after an interact retry."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from markdownflow.engine import ContentDelta, Engine, InteractionRequest, ToolCall
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from markdownflow.engine import Event
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.mark.anyio
@pytest.mark.parametrize("retry", ["replay", "rewrite"])
async def test_lesson_opening_streams_while_interact_validates(retry: str) -> None:
    """Replay the trace with a missing tool argument to trigger a retry."""
    opening = "欢迎来到 AI 师傅因材施教体验课！\n\n"
    choices = "1. 让 AI 师傅根据您的背景选题。\n2. 您也可以自己指定一个主题。"
    question = "您想让后续课节怎样选题？"
    addition = "\n\n" + question
    rewrite = "欢迎来到 AI 师傅因材施教体验课，先看看两种选题方式。"
    options = [{"display": "让 AI 师傅选题"}, {"display": "我来指定主题"}]
    attempts = 0
    events: list[Event] = []

    def content() -> str:
        return "".join(e.text for e in events if isinstance(e, ContentDelta))

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield opening
            assert content() == opening  # No tool args have been produced yet.
            yield choices
            assert content() == opening + choices
        else:
            assert attempts == 2
            assert any(
                isinstance(part, RetryPromptPart)
                and part.tool_name == "interact"
                and "complete question" in str(part.content)
                for part in messages[-1].parts
            )
            if retry == "replay":
                # Change chunk boundaries so matching cannot rely on equal deltas.
                repeated = opening + choices
                yield repeated[:5]
                yield repeated[5:] + addition[:3]
                assert content() == repeated + addition[:3]
                yield addition[3:]
            else:
                yield rewrite[:5]
                yield rewrite[5:]
                assert content() == opening + choices + "\n" + rewrite
                yield addition
        args = {
            "type": "single_or_text",
            "options": options,
            "placeholder": "输入主题",
        }
        if attempts == 2:
            args["question"] = question
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"topic-{attempts}",
                json_args=json.dumps(args),
            )
        }

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        memory_context_limit=32_768,
        memory_recall=True,
        exercise_statistics=True,
        feedback_contract=True,
        pauses_from_notation=True,
    )
    session = await engine.new_session(
        opening + choices + "\n?[让 AI 师傅选题 | 我来指定主题 | ...输入主题]"
    )
    async for event in engine.run_turn(session):
        assert event.type != "error", event
        events.append(event)

    assert attempts == 2
    expected_suffix = addition if retry == "replay" else "\n" + rewrite + addition
    assert content() == opening + choices + expected_suffix
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert interaction.id == f"topic-{attempts}"
    assert interaction.spec.question == question
    assert interaction.spec.type == "single_or_text"
    assert [option.display for option in interaction.spec.options] == [
        option["display"] for option in options
    ]
    first_call = next(
        i for i, event in enumerate(events) if isinstance(event, ToolCall)
    )
    assert (
        "".join(e.text for e in events[:first_call] if isinstance(e, ContentDelta))
        == opening + choices
    )


@pytest.mark.anyio
async def test_retry_continues_an_unfinished_word() -> None:
    """An exact replay resumes the previous text without inserting a line break."""
    prefix = "Wel"
    suffix = "come to the lesson."
    question = "What should we study?"
    attempts = 0
    events: list[Event] = []

    def content() -> str:
        return "".join(
            event.text for event in events if isinstance(event, ContentDelta)
        )

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield prefix
            assert content() == prefix
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="invalid",
                    json_args='{"type":"text","placeholder":"Answer"}',
                )
            }
            return

        assert attempts == 2
        assert any(
            isinstance(part, RetryPromptPart) and part.tool_call_id == "invalid"
            for part in messages[-1].parts
        )
        yield prefix[:2]
        yield prefix[2:]
        yield suffix
        assert content() == prefix + suffix
        yield "\n\n" + question
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="valid",
                json_args=json.dumps(
                    {"type": "text", "question": question, "placeholder": "Answer"}
                ),
            )
        }

    engine = Engine(FunctionModel(stream_function=model), pauses_from_notation=True)
    session = await engine.new_session("Introduce the lesson.\n?[...Answer]")
    async for event in engine.run_turn(session):
        assert event.type != "error", event
        events.append(event)

    assert content() == prefix + suffix + "\n\n" + question
    (interaction,) = [
        event for event in events if isinstance(event, InteractionRequest)
    ]
    assert interaction.id == "valid"


@pytest.mark.anyio
async def test_repeat_after_a_successful_tool_is_kept() -> None:
    """An ordinary tool hop can intentionally repeat prose."""
    prose = "Compare the same two approaches."
    attempts = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        attempts += 1
        yield prose
        if attempts == 1:
            yield {
                0: DeltaToolCall(
                    name="recall", tool_call_id="read", json_args='{"key":"topic"}'
                )
            }

    engine = Engine(FunctionModel(stream_function=model), memory_recall=True)
    session = await engine.new_session("Show the comparison twice.")
    events = [event async for event in engine.run_turn(session)]
    assert not any(event.type == "error" for event in events)
    assert attempts == 2
    assert [e.text for e in events if isinstance(e, ContentDelta)] == [
        prose,
        "\n" + prose,
    ]
