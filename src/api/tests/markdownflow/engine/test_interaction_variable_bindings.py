"""Standard bindings share the existing named-answer and legacy wire contracts."""

import json
from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import (
    Engine,
    ErrorEvent,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
    ScriptBundle,
    Session,
    ToolResult,
    collected_names,
    render_first_prompt,
    substitute_variables,
)
from markdownflow.engine.script import substitution_names
from markdownflow.engine.tools import script_options, script_pauses, script_text_inputs
from markdownflow.interaction_rendering import QuestionLabels, QuestionRenderer
from markdownflow.syntax import InteractionParser
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

_LITERAL_EXAMPLES = [
    "",
    "Show `?[` then ",
    "<!-- ?[ -->\n\n",
    "```md\n?[\n```\n\n",
]


@pytest.mark.parametrize("prefix", ["", "%"])
@pytest.mark.parametrize("separator", [" | ", " || "])
def test_leading_binding_is_not_an_option_or_input_hint(
    prefix: str, separator: str
) -> None:
    source = (
        "?[ " + prefix + "{{goal}} A//a" + separator + "B//b" + separator + "...Other]"
    )
    assert script_options(source) == {"A": "A", "a": "a", "B": "B", "b": "b"}
    (question,) = script_text_inputs(source)
    assert question.variable == "goal"
    assert question.placeholder == "Other"
    assert question.multi is (separator == " || ")
    assert script_pauses("?[" + prefix + "{{goal}} Ready]") == 0
    assert script_options("?[" + prefix + "{{goal}} ...Your goal?]") == {}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("?[{{goal}} A | B]", {"goal"}),
        ("?[%{{goal}} A | B]", {"goal"}),
        ("Remember %{{goal}}.", {"goal"}),
        ("Read {{goal}}.", set()),
        ("?[Prefix {{goal}} A | B]", set()),
        ("```md\n?[{{goal}} A | B]\n```", set()),
        ("`?[{{goal}} A | B]`", set()),
        ("<!-- ?[{{goal}} A | B] -->", set()),
        (r"\?[{{goal}} A | B]", set()),
    ],
)
def test_only_leading_bindings_add_standard_collection_permission(
    source: str, expected: set[str]
) -> None:
    assert collected_names(source) == expected


def test_removing_a_fenced_example_cannot_create_a_binding() -> None:
    source = "?[\n```md\nnot a control\n```\n{{goal}} A | B]"
    assert collected_names(source) == set()
    assert substitution_names(ScriptBundle(source)) == {"goal"}
    assert "OLD_ANSWER" in render_first_prompt(
        ScriptBundle(source), {"goal": "OLD_ANSWER"}
    )


@pytest.mark.parametrize("prefix", ["", "%"])
@pytest.mark.parametrize("example", _LITERAL_EXAMPLES)
def test_old_memory_cannot_replace_a_binding_or_its_later_read(
    prefix: str, example: str
) -> None:
    binding = prefix + "{{goal}}"
    source = example + "?[" + binding + " A | B]\nGoal: {{goal}}; name: {{nickname}}."
    memory = {"goal": "OLD_ANSWER", "nickname": "Lin"}
    assert collected_names(source) == {"goal"}
    assert substitute_variables(source, memory).startswith(example + "?[" + binding)
    assert substitute_variables(
        source, memory, collected=collected_names(source)
    ).endswith("Goal: {{goal}}; name: Lin.")
    assert substitution_names(ScriptBundle(source)) == {"nickname"}
    prompt = render_first_prompt(ScriptBundle(source), memory)
    assert "OLD_ANSWER" not in prompt
    assert '"nickname": "Lin"' in prompt
    assert source in prompt


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["", "%"])
@pytest.mark.parametrize("replaying", [False, True])
@pytest.mark.parametrize("example", _LITERAL_EXAMPLES)
async def test_fresh_named_answer_survives_storage_and_legacy_wire_round_trip(
    prefix: str, replaying: bool, example: str
) -> None:
    calls = 0
    prompts: list[str] = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            prompts.extend(
                part.content
                for message in messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, UserPromptPart) and isinstance(part.content, str)
            )
        if calls in (1, 3):
            name, arguments = "recall", {"key": "goal"}
        elif calls == 2:
            name, arguments = (
                "interact",
                {
                    "type": "single",
                    "prompt": "Your goal?",
                    "variable": "goal",
                    "options": [{"display": "A"}, {"display": "B"}],
                },
            )
        else:
            yield "Continue with the learner's answer."
            return
        yield {
            0: DeltaToolCall(
                name=name,
                tool_call_id="call-" + str(calls),
                json_args=json.dumps(arguments),
            )
        }

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        memory_recall=True,
        render="none",
    )
    source = example + "?[" + prefix + "{{goal}} A | B]"
    session = await engine.new_session(source, memory={"goal": "OLD_ANSWER"})
    first = [event async for event in engine.run_turn(session)]
    assert "OLD_ANSWER" not in "\n".join(prompts)
    assert first[-1].reason == "interaction"
    assert [
        json.loads(event.content)
        for event in first
        if isinstance(event, ToolResult) and event.name == "recall"
    ] == [{"status": "unavailable"}]
    (question,) = [event for event in first if isinstance(event, InteractionRequest)]
    assert question.spec.variable == "goal"
    renderer = QuestionRenderer(QuestionLabels("Continue", "Your answer"))
    wire = renderer.render_interaction(question.spec)
    assert "%{{ goal }}" in wire
    assert InteractionParser().parse(wire)["variable"] == "goal"

    session = Session.loads(session.dumps())
    assert session.script.script == source
    assert session.memory == {"goal": "OLD_ANSWER"}
    assert not session.answered_memory_keys()
    second = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=["B"]), replaying_input=replaying
        )
    ]
    assert not any(isinstance(event, ErrorEvent) for event in second)
    assert [
        (event.key, event.value) for event in second if isinstance(event, MemoryUpdated)
    ] == [("goal", "B")]
    assert [
        json.loads(event.content)
        for event in second
        if isinstance(event, ToolResult) and event.name == "recall"
    ] == [{"status": "found", "value": "B"}]
    restored = Session.loads(session.dumps())
    assert restored.memory == {"goal": "B"}
    assert restored.answered_memory_keys() == {"goal"}
