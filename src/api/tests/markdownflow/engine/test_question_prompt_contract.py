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
)
from pydantic_ai.messages import ModelMessage, RetryPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


@pytest.mark.anyio
async def test_interact_accepts_a_question_supplied_only_in_its_arguments() -> None:
    """An omitted question in prose does not trigger a runtime retry."""
    opening = "欢迎来到 AI 师傅因材施教体验课！"
    question = "您想让后续课节怎样选题？"
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls > 1:
            yield "That is how we will choose a topic."
            return
        yield opening
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="topic",
                json_args=json.dumps(
                    {
                        "type": "single_or_text",
                        "question": question,
                        "options": [{"display": "Let the teacher choose"}],
                        "placeholder": "Name a topic",
                    }
                ),
            )
        }

    engine = Engine(FunctionModel(stream_function=model), pauses_from_notation=True)
    session = await engine.new_session(
        opening + "\n?[{{ " + question + " }} Let the teacher choose | ...Name a topic]"
    )
    events = [event async for event in engine.run_turn(session)]

    assert calls == 1
    assert not any(event.type == "error" for event in events)
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert interaction.spec.question == question
    assert [e.text for e in events if isinstance(e, ContentDelta)] == [opening]
    events = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="topic", text="Recursion")
        )
    ]
    assert not any(event.type == "error" for event in events)
    assert session.all_memory() == {question: "Recursion"}


@pytest.mark.anyio
@pytest.mark.parametrize("listen_mode", [False, True])
@pytest.mark.parametrize("render", ["sandbox", "none"])
@pytest.mark.parametrize("binding", ["question", "short-label", "none", "mixed"])
async def test_question_is_shown_before_controls_and_keys_the_answer(
    listen_mode: bool, render: Literal["sandbox", "none"], binding: str
) -> None:
    """Keep the model's question prose ahead of the controls and use its key for storage."""
    learner_question = "Which examples match?"
    question = "matching_examples" if binding == "short-label" else learner_question
    teaching = "Compare the examples."
    prefix = f"{{{{ {question} }}}} " if binding in ("question", "short-label") else ""
    options = [{"display": "A", "value": "a"}, {"display": "B", "value": "b"}]
    calls = 0

    async def model(
        _messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls > 1:
            yield "Those examples match."
            return
        schema = next(
            tool.parameters_json_schema
            for tool in info.function_tools
            if tool.name == "interact"
        )
        assert "question" in schema["properties"]
        assert "question" not in schema.get("required", [])
        assert not {"prompt", "variable", "display_question"}.intersection(
            schema["properties"]
        )
        assert "MUST ask the question in visible Markdown prose" in (
            info.instructions or ""
        )
        yield f"{teaching}\n\n{learner_question}"
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
    script = f"{teaching}\n{learner_question}\n?[{prefix}A//a || B//b]"
    if binding == "mixed":
        script += "\n?[{{extra_examples}} A//a || B//b]"
    session = await engine.new_session(script, listen_mode=listen_mode)
    events = [event async for event in engine.run_turn(session)]
    assert not any(event.type == "error" for event in events)
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    before = events[: events.index(interaction)]
    if not listen_mode:
        text = "".join(e.text for e in before if isinstance(e, ContentDelta))
    else:
        text = "".join(e.text for e in before if e.type == "narration.delta")
    assert text.index(teaching) < text.index(learner_question)
    assert text.count(learner_question) == 1
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
    restored = Session.loads(session.dumps())
    assert restored.all_memory() == {question: "a, b"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "wrong_question", ["What would you like to learn?", "Learning goal"]
)
@pytest.mark.parametrize("competing_control", [False, True])
@pytest.mark.parametrize("placeholder", ["Share your goal", None])
async def test_bound_control_retries_rewritten_question_with_localized_or_omitted_hint(
    wrong_question: str, competing_control: bool, placeholder: str | None
) -> None:
    """A localized question uses the original binding as the only answer key."""
    question = "learning_goal"
    translation = "What would you like to learn?"
    attempts = 0

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        attempts += 1
        if attempts == 3:
            yield "Continue teaching."
            return
        if attempts == 2:
            assert any(
                isinstance(part, RetryPromptPart)
                and part.tool_name == "interact"
                and question in str(part.content)
                for part in messages[-1].parts
            )
        assert "Keep the exact authored text in interact.question" in (
            info.instructions or ""
        )
        wording = wrong_question if attempts == 1 else question
        yield translation
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"attempt-{attempts}",
                json_args=json.dumps(
                    {
                        "type": "text",
                        "question": wording,
                        "display_question": translation,
                        "placeholder": placeholder,
                    }
                ),
            )
        }

    engine = Engine(
        FunctionModel(stream_function=model),
        output_language="en-US",
        buffer_model_responses=True,
        memory_admission=True,
    )
    lesson = "?[{{ learning_goal }}...请分享学习目标]"
    if competing_control:
        lesson += "\n?[{{ learning_pace }}...请分享学习目标]"
    session = await engine.new_session(lesson)
    events = [event async for event in engine.run_turn(session)]
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert interaction.id == "attempt-2"
    assert "".join(e.text for e in events if isinstance(e, ContentDelta)) == translation
    session = Session.loads(session.dumps())
    assert session.pending[0].spec.question == question
    assert session.pending[0].spec.presented_question == translation
    events = [
        e
        async for e in engine.run_turn(session, InteractionResponseTurn(text="Graphs"))
    ]
    assert [(e.key, e.value) for e in events if isinstance(e, MemoryUpdated)] == [
        (question, "Graphs")
    ]
    assert session.all_memory() == {question: "Graphs"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("trusted", "authored", "accepted"),
    [(True, True, True), (True, False, False), (False, True, False)],
)
async def test_reserved_question_requires_a_trusted_exact_authored_control(
    trusted: bool,
    authored: bool,
    accepted: bool,
) -> None:
    """An allowlist cannot authorize an unbound use of a host-owned key."""
    question = "sys_user_nickname"
    attempts = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            if not accepted:
                assert any(
                    isinstance(part, RetryPromptPart)
                    and "reserved" in str(part.content)
                    for part in messages[-1].parts
                )
            yield "Continue teaching."
            return
        yield question
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="nickname",
                json_args=json.dumps(
                    {"type": "text", "question": question, "placeholder": "Nickname"}
                ),
            )
        }

    engine = Engine(
        FunctionModel(stream_function=model),
        allowed_authored_question_keys=frozenset({question})
        if trusted
        else frozenset(),
        memory_admission=True,
    )
    binding = f"{{{{ {question} }}}}" if authored else ""
    session = await engine.new_session(f"?[{binding}...Nickname]")
    events = [event async for event in engine.run_turn(session)]
    assert not any(event.type == "error" for event in events)
    assert bool(session.pending) is accepted
    if accepted:
        _ = [
            e
            async for e in engine.run_turn(
                session, InteractionResponseTurn(text="Learner")
            )
        ]
    assert session.memory == ({question: "Learner"} if accepted else {})


@pytest.mark.anyio
async def test_visible_html_question_is_delivered_before_its_control() -> None:
    question = "What would you like to learn & practice?"
    prose = "<p>What would you like to <strong>learn &amp; practice</strong>?</p>"
    attempts = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        attempts += 1
        yield prose
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"html-question-{attempts}",
                json_args=json.dumps(
                    {"type": "text", "question": question, "placeholder": "Answer"}
                ),
            )
        }

    engine = Engine(
        FunctionModel(stream_function=model), render="none", buffer_model_responses=True
    )
    session = await engine.new_session("?[...Answer]")
    events = [event async for event in engine.run_turn(session)]

    (interaction,) = [
        event for event in events if isinstance(event, InteractionRequest)
    ]
    assert interaction.id == "html-question-1"
    assert interaction.spec.question == question
    assert (
        "".join(
            event.text
            for event in events[: events.index(interaction)]
            if isinstance(event, ContentDelta)
        )
        == prose
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
    """A leading binding or a text input requires a complete question."""
    question = "What color is the sky?"
    script = f"?[{{{{{question}}}}} Blue]" if single_choice else "?[...Your answer]"
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
