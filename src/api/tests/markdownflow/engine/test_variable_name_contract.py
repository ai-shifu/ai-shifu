"""Keep existing question-style keys intact across the lesson parser boundaries."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
    collected_names,
    substitute_variables,
)
from flaskr.service.learn.agent.engine.events import InteractionRequest
from flaskr.service.learn.agent.engine.interaction import InteractionSpec, Option
from flaskr.service.learn.agent.engine.tools import _script_questions
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
from flaskr.service.learn.agent.legacy_protocol import render_interaction
from markdown_flow import InteractionParser, MarkdownFlow
from markdown_flow.parser.variable import replace_variables_in_text
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio

QUESTION_KEYS = (
    "你的性别是？",
    "gender?",
    "What_is_your_gender?",
    "职业:学生/在职",
    "choice|origin//raw...?",
    "gender_(self)",
    "学习目标_😀？",
    "name",
    "中文变量",
    "\ufeffgender?",
    "gender?\ufeff",
    "\ufeff",
)
CHOICES = ("男", "女", "秘密")


def _question(key: str, padding: str = "") -> str:
    """Use the author's original choice syntax without normalizing its key."""
    return f"?[%{{{{{padding}{key}{padding}}}}} {' | '.join(CHOICES)}]"


@pytest.mark.parametrize("key", QUESTION_KEYS)
@pytest.mark.parametrize("padding", ["", " \t"])
def test_existing_question_keys_agree_across_parser_boundaries(
    key: str, padding: str
) -> None:
    """Punctuation in a name cannot become an option delimiter or disappear."""
    authored = _question(key, padding)
    parsed = InteractionParser().parse(authored)
    assert parsed["variable"] == key
    assert [(button["display"], button["value"]) for button in parsed["buttons"]] == [
        (choice, choice) for choice in CHOICES
    ]
    assert MarkdownFlow(authored).extract_variables() == [key]
    assert collected_names(authored) == frozenset({key})

    reference = f"{{{{{key}}}}}"
    assert replace_variables_in_text(reference, {key: "女"}, add_quotes=False) == "女"
    assert substitute_variables(f"{{{{{padding}{key}{padding}}}}}", {key: "女"}) == "女"
    assert substitute_variables(authored, {key: "女"}) == authored

    questions = _script_questions(authored)
    assert len(questions) == 1
    assert questions[0].variable == key
    assert [choice.strip() for choice in questions[0].choices] == list(CHOICES)
    assert not questions[0].text

    syntax = InteractionSyntaxFilter()
    assert (
        "".join(syntax.feed(character) for character in authored) + syntax.flush() == ""
    )
    assert syntax.spans == [authored]

    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        options=[Option(display=choice) for choice in CHOICES],
        variable=key,
    )
    rendered = render_interaction(spec)
    assert rendered == _question(key)
    assert InteractionParser().parse(rendered)["variable"] == key


@pytest.mark.parametrize("key", QUESTION_KEYS)
async def test_named_question_answer_survives_session_and_wire_round_trips(
    key: str,
) -> None:
    """Exercise admission, deferred tools and returned memory with the exact authored key."""
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="question",
                    json_args=json.dumps(
                        {
                            "type": "single",
                            "prompt": "Choose one",
                            "variable": key,
                            "options": [{"display": choice} for choice in CHOICES],
                        }
                    ),
                )
            }
        else:
            yield {
                0: DeltaToolCall(
                    name="finish",
                    tool_call_id="finished",
                    json_args=json.dumps({"summary": "Done"}),
                )
            }

    engine = Engine(FunctionModel(stream_function=model), memory_admission=True)
    session = await engine.new_session(_question(key))
    first = [event async for event in engine.run_turn(session)]
    assert not [event for event in first if isinstance(event, ErrorEvent)]
    request = next(event for event in first if isinstance(event, InteractionRequest))
    assert request.spec.variable == key
    assert render_interaction(request.spec) == _question(key)
    assert first[-1].reason == "interaction"

    session = Session.loads(session.dumps())
    assert session.pending[0].spec.variable == key
    second = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=["女"])
        )
    ]
    assert not [event for event in second if isinstance(event, ErrorEvent)]
    assert [
        (event.key, event.value, event.source)
        for event in second
        if isinstance(event, MemoryUpdated)
    ] == [(key, "女", "interaction")]
    assert second[-1].reason == "finished"
    restored = Session.loads(session.dumps())
    assert restored.memory == {key: "女"}
    assert substitute_variables(f"{{{{{key}}}}}", restored.memory) == "女"


@pytest.mark.parametrize(
    "key",
    [
        "What is your gender?",
        "a\tb",
        "a{b",
        "a}b",
        "a\nb",
        "a\u0085b",
        "a\u001cb",
        "a\u001db",
        "a\u001eb",
        "a\u001fb",
    ],
)
def test_engine_does_not_declare_keys_with_internal_whitespace_or_braces(
    key: str,
) -> None:
    """Keep the existing authoring contract; this change does not broaden its grammar."""
    assert collected_names(_question(key)) == frozenset()
    reference = f"{{{{{key}}}}}"
    assert substitute_variables(reference, {key: "女"}) == reference


@pytest.mark.parametrize("key", ["What is your gender?", "a{b", "a\nb"])
def test_legacy_parser_remains_tolerant_of_historical_names(key: str) -> None:
    """Legacy tolerance is intentionally broader than the engine's authoring contract."""
    authored = _question(key)
    assert InteractionParser().parse(authored)["variable"] == key
    assert MarkdownFlow(authored).extract_variables() == [key]


@pytest.mark.parametrize("padding", ["\u0085", "\u001c", "\u001d", "\u001e", "\u001f"])
def test_assignment_extraction_trims_python_only_whitespace(padding: str) -> None:
    """Python padding includes controls absent from JavaScript's whitespace set."""
    key = "你的性别是？"
    authored = _question(key, padding)
    assert collected_names(authored) == frozenset({key})
    assert InteractionParser().parse(authored)["variable"] == key
    assert MarkdownFlow(authored).extract_variables() == [key]
