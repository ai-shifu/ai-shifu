"""Exercise the model-facing question, its presentation, and saved answer identity."""

import json
from collections.abc import AsyncIterator
from typing import Literal

import pytest
from markdownflow.engine import (
    ContentDelta,
    Engine,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
    ToolResult,
)
from pydantic_ai.messages import ModelMessage, RetryPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


@pytest.mark.anyio
@pytest.mark.parametrize("listen_mode", [False, True])
@pytest.mark.parametrize("render", ["sandbox", "none"])
@pytest.mark.parametrize("binding", ["question", "legacy-key", "none"])
async def test_question_is_shown_before_controls_and_keys_the_answer(
    listen_mode: bool, render: Literal["sandbox", "none"], binding: str
) -> None:
    """Keep the model's question prose ahead of the controls and use its key for storage."""
    question = "Which examples match?"
    teaching = "Compare the examples."
    prefix = {
        "question": f"{{{{ {question} }}}} ",
        "legacy-key": "{{matching_examples}} ",
        "none": "",
    }[binding]
    options = [{"display": "A", "value": "a"}, {"display": "B", "value": "b"}]
    calls = 0

    async def model(
        _messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 2 and binding == "legacy-key":
            yield {
                0: DeltaToolCall(
                    name="recall",
                    tool_call_id="recall-old-binding",
                    json_args=json.dumps({"key": "matching_examples"}),
                )
            }
            return
        if calls > 1:
            yield "Those examples match."
            return
        schema = next(
            tool.parameters_json_schema
            for tool in info.function_tools
            if tool.name == "interact"
        )
        assert "question" in schema["properties"]
        assert "question" in schema["required"]
        assert not {"prompt", "variable"}.intersection(schema["properties"])
        assert "ask the complete question in visible Markdown prose" in (
            info.instructions or ""
        )
        yield f"{teaching}\n\n{question}"
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="examples",
                json_args=json.dumps(
                    {
                        "type": "multi",
                        "question": question,
                        "options": options,
                    }
                ),
            )
        }

    engine = Engine(
        FunctionModel(stream_function=model),
        render=render,
        memory_admission=True,
        memory_recall=True,
    )
    session = await engine.new_session(
        f"{teaching}\n?[{prefix}A//a || B//b]", listen_mode=listen_mode
    )
    events = [event async for event in engine.run_turn(session)]
    assert not any(event.type == "error" for event in events)
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    before = events[: events.index(interaction)]
    if not listen_mode:
        text = "".join(e.text for e in before if isinstance(e, ContentDelta))
    else:
        text = "".join(e.text for e in before if e.type == "narration.delta")
    assert text.index(teaching) < text.index(question)
    assert text.count(question) == 1
    assert interaction.spec.question == question
    assert interaction.spec.type == "multi"
    assert [option.model_dump() for option in interaction.spec.options] == options
    session = Session.loads(session.dumps())
    assert session.pending[0].spec.question == question
    events = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="examples", values=["a", "b"])
        )
    ]
    assert not any(event.type == "error" for event in events)
    assert [(e.key, e.value) for e in events if isinstance(e, MemoryUpdated)] == [
        (question, "a, b")
    ]
    assert session.memory == {question: "a, b"}
    if binding == "legacy-key":
        assert [
            json.loads(e.content)
            for e in events
            if isinstance(e, ToolResult) and e.name == "recall"
        ] == [{"status": "found", "value": "a, b"}]
        restored = Session.loads(session.dumps())
        assert restored.memory == {question: "a, b"}
        assert restored.all_memory()["matching_examples"] == "a, b"


@pytest.mark.anyio
@pytest.mark.parametrize("listen_mode", [False, True])
async def test_tool_question_does_not_generate_missing_prose(listen_mode: bool) -> None:
    """The tool's memory key cannot add text or narration that the model did not write."""
    teaching = "Review the examples."
    question = "Which example applies here?"

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield teaching
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="example",
                json_args=json.dumps({"type": "text", "question": question}),
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Discuss the examples.", listen_mode=listen_mode)
    events = [event async for event in engine.run_turn(session)]
    assert not any(event.type == "error" for event in events)
    (interaction,) = [
        event for event in events if isinstance(event, InteractionRequest)
    ]
    assert interaction.spec.question == question
    text_event = "narration.delta" if listen_mode else "content.delta"
    assert (
        "".join(event.text for event in events if event.type == text_event) == teaching
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "missing_question",
    [{}, {"question": "  "}, {"prompt": "Legacy question?", "variable": "key"}],
    ids=["omitted", "blank", "legacy-only"],
)
@pytest.mark.parametrize("single_choice", [False, True])
async def test_answer_control_without_a_real_question_is_retried(
    missing_question: dict[str, str], single_choice: bool
) -> None:
    """A single answer option is not enough to make a question a navigation control."""
    question = "What color is the sky?"
    script = question + ("\n?[Blue]" if single_choice else "\n?[...Your answer]")
    control = (
        {"type": "single", "options": [{"display": "Blue"}]}
        if single_choice
        else {"type": "text", "placeholder": "Your answer"}
    )
    attempts = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            fields = missing_question
        else:
            assert attempts == 2
            assert any(
                isinstance(part, RetryPromptPart) and part.tool_name == "interact"
                for part in messages[-1].parts
            )
            fields = {"question": question}
            yield question
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"attempt-{attempts}",
                json_args=json.dumps({**control, **fields}),
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(script)
    events = [e async for e in engine.run_turn(session)]
    assert not any(event.type == "error" for event in events)
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert interaction.id == "attempt-2"
    assert interaction.spec.question == question
