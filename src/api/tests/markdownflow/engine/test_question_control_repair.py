"""Keep authored text inputs usable under the question-only tool contract."""

import json
from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import (
    Engine,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
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
