"""Keep authored text inputs usable under the question-only tool contract."""

import json
from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import (
    ContentDelta,
    Engine,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
)
from pydantic_ai.messages import ModelMessage, RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


@pytest.mark.anyio
@pytest.mark.parametrize("mixed", [False, True], ids=["text-only", "mixed"])
@pytest.mark.parametrize("bound", [False, True], ids=["unbound", "bound"])
async def test_duplicate_hint_cannot_bypass_the_answer_question(
    mixed: bool, bound: bool
) -> None:
    generated_question = "Quel projet souhaitez-vous réaliser ?"
    question = "project_path" if bound else generated_question
    hint = "Describe your project"
    localized_hint = "Décrivez votre projet"
    choices = (
        [
            {"display": "Nouveau", "value": "new"},
            {"display": "Existant", "value": "old"},
        ]
        if mixed
        else []
    )
    attempts = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
            yield "Continue teaching."
            return
        attempts += 1
        if attempts == 1:
            wording = generated_question if bound else ""
        else:
            assert attempts == 2
            retry_detail = question if bound else "complete question"
            assert any(
                isinstance(part, RetryPromptPart)
                and part.tool_name == "interact"
                and retry_detail in str(part.content)
                for part in messages[-1].parts
            )
            wording = question
        if wording:
            yield wording
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"attempt-{attempts}",
                json_args=json.dumps(
                    {
                        "type": "single",
                        "question": wording,
                        "options": [
                            *choices,
                            {"display": localized_hint, "value": hint},
                        ],
                    }
                ),
            )
        }

    engine = Engine(
        FunctionModel(stream_function=model),
        output_language="fr-FR",
        buffer_model_responses=True,
    )
    authored_choices = "New//new | Existing//old | " if mixed else ""
    binding = f"{{{{{question}}}}} " if bound else ""
    session = await engine.new_session(f"?[{binding}{authored_choices}...{hint}]")
    events = [event async for event in engine.run_turn(session)]
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert interaction.id == "attempt-2"
    assert interaction.spec.type == ("single_or_text" if mixed else "text")
    assert interaction.spec.placeholder == localized_hint
    assert [option.model_dump() for option in interaction.spec.options] == choices

    answer = "Mon projet de lecture."
    events = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=answer))
    ]
    assert [(e.key, e.value) for e in events if isinstance(e, MemoryUpdated)] == [
        (question, answer)
    ]
    assert session.all_memory() == {question: answer}


@pytest.mark.anyio
async def test_authored_question_keeps_exact_wording_when_hint_changes() -> None:
    question = "learning_goal"
    hint = "Answer"
    rewritten_question = "What would you like to learn?"
    attempt = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempt
        if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
            yield "Continue teaching."
            return
        attempt += 1
        if attempt == 1:
            wording, placeholder = rewritten_question, "Share a topic"
        else:
            assert attempt == 2
            assert any(
                isinstance(part, RetryPromptPart)
                and part.tool_name == "interact"
                and question in str(part.content)
                for part in messages[-1].parts
            )
            wording, placeholder = question, hint
        yield wording
        yield _input(f"attempt-{attempt}", wording, placeholder)

    engine = Engine(FunctionModel(stream_function=model), buffer_model_responses=True)
    session = await engine.new_session(f"?[{{{{{question}}}}}...{hint}]")
    events = [event async for event in engine.run_turn(session)]
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert interaction.id == "attempt-2"
    assert "".join(e.text for e in events if isinstance(e, ContentDelta)) == question
    await _answer(engine, session, "Algebra", question)
    assert session.all_memory() == {question: "Algebra"}


@pytest.mark.anyio
async def test_generated_follow_up_can_reuse_authored_input_shape() -> None:
    question = "learning_goal"
    generated = "Which example should we start with?"
    hint = "Answer"
    attempt = 0

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempt
        attempt += 1
        if attempt == 4:
            yield "Continue teaching."
            return
        if attempt == 1:
            tool = next(tool for tool in info.function_tools if tool.name == "interact")
            schema = tool.parameters_json_schema
            assert schema["properties"]["generated_control"]["type"] == "boolean"
            assert "generated_control" not in schema["required"]
            # The opt-out cannot reuse an authored memory key, regardless of its hint.
            yield question
            yield _input("invalid", question, "Something else", generated_control=True)
        elif attempt == 2:
            assert any(
                isinstance(part, RetryPromptPart)
                and part.tool_name == "interact"
                and "generated_control" in str(part.content)
                for part in messages[-1].parts
            )
            yield question
            yield _input("authored", question, hint)
        else:
            yield generated
            yield _input("generated", generated, hint, generated_control=True)

    engine = Engine(FunctionModel(stream_function=model), buffer_model_responses=True)
    session = await engine.new_session(f"?[{{{{{question}}}}}...{hint}]")
    initial = [event async for event in engine.run_turn(session)]
    (authored,) = [e for e in initial if isinstance(e, InteractionRequest)]
    assert authored.id == "authored"
    events = await _answer(engine, session, "Algebra", question)
    (follow_up,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert follow_up.id == "generated"
    assert follow_up.spec.question == generated
    assert follow_up.spec.placeholder == hint
    assert follow_up.spec.generated_control
    session = Session.loads(session.dumps())
    assert session.pending[0].spec.generated_control
    await _answer(engine, session, "A number line", generated)
    assert session.all_memory() == {question: "Algebra", generated: "A number line"}


@pytest.mark.anyio
async def test_generated_choice_keeps_its_literal_authored_lookalike() -> None:
    question = "Which string includes the backslash?"
    option = r"A\|B"

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield question
        yield _input(
            "generated",
            question,
            "",
            type="single",
            options=[{"display": option}],
            generated_control=True,
        )

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(r"?[{{Choose a symbol}} A\|B]")
    events = [event async for event in engine.run_turn(session)]
    (follow_up,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert follow_up.spec.options[0].stored == option
    assert follow_up.spec.options[0].display == option


def _input(
    call_id: str, question: str, hint: str, **fields: object
) -> dict[int, DeltaToolCall]:
    return {
        0: DeltaToolCall(
            name="interact",
            tool_call_id=call_id,
            json_args=json.dumps(
                {"type": "text", "question": question, "placeholder": hint, **fields}
            ),
        )
    }


async def _answer(
    engine: Engine, session: Session, answer: str, key: str
) -> list[object]:
    events = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=answer))
    ]
    assert [(e.key, e.value) for e in events if isinstance(e, MemoryUpdated)] == [
        (key, answer)
    ]
    return events
