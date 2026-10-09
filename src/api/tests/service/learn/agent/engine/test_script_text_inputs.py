"""Keep authored free-text hints out of generated choices and saved pending questions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
)
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.legacy_protocol import render_interaction
from markdown_flow import InteractionParser
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.anyio

_CHOICES = [
    "Start a new project",
    "Improve an existing assistant",
    "Use course materials",
]
_HINT = "Describe my project directly"
_SCRIPT = "?[%{{project_path}} " + " | ".join([*_CHOICES, "..." + _HINT]) + "]"


@pytest.mark.parametrize("placeholder", [None, ""])
@pytest.mark.parametrize("variable", [None, "answer"])
async def test_text_only_hint_is_restored_among_multiple_authored_questions(
    placeholder: str | None,
    variable: str | None,
) -> None:
    """A copied authored prompt restores the input and accepts the reloaded answer."""
    prefix = "%{{" + variable + "}} " if variable else ""
    hints = ["Prepare and execute", "List advantages", "Nine lines of code"]
    script = "\n".join("?[" + prefix + "..." + hint + "]" for hint in hints)
    arguments = _arguments(
        type="text",
        prompt=hints[0],
        options=[],
        variable=variable,
        placeholder=placeholder,
    )
    engine = _engine(arguments)
    session = await engine.new_session(script)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert spec.placeholder == hints[0]
    assert render_interaction(spec) == "?[" + prefix + "..." + hints[0] + "]"
    assert InteractionParser().parse(render_interaction(spec))["question"] == hints[0]
    session = Session.loads(session.dumps())
    events = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(text="My answer")
        )
    ]
    assert not session.pending
    assert session.memory == ({variable: "My answer"} if variable else {})


async def test_saved_text_only_question_recovers_input_on_empty_answer() -> None:
    """Old cached questions re-emit their authored input without changing history."""
    engine = _engine(
        _arguments(
            type="text", prompt=_HINT, options=[], variable=None, placeholder=None
        )
    )
    session = await engine.new_session("Ask a dynamic question.")
    _ = [e async for e in engine.run_turn(session)]
    session.script = ScriptBundle(script="?[..." + _HINT + "]")
    session = Session.loads(session.dumps())
    history = session.messages.copy()
    events = [e async for e in engine.run_turn(session, InteractionResponseTurn())]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert spec.placeholder == _HINT
    assert session.messages == history
    assert render_interaction(spec) == "?[..." + _HINT + "]"


@pytest.mark.parametrize(
    ("script", "prompt", "variable", "placeholder", "expected"),
    [
        (
            "?[...Write your answer]",
            "What part is unclear?",
            None,
            None,
            None,
        ),
        ("?[...One]\n?[...Two]", "A generated question", None, None, None),
        ("?[...One]\n?[...]", "A generated question", None, None, None),
        ("?[...One]\n?[...One]", "One", None, None, "One"),
        (
            "?[...Write your answer]",
            "Write your answer",
            None,
            None,
            "Write your answer",
        ),
        ("?[...One]", "One", "different", None, None),
        ("?[...One]", "One", None, "Custom hint", "Custom hint"),
        ("```\n?[...One]\n```", "One", None, None, None),
        ("?[Yes | ...One]", "One", None, None, None),
        (
            r"?[...Describe a\|b\.\.\.]",
            r"Describe a\|b\.\.\.",
            None,
            None,
            "Describe a|b...",
        ),
    ],
)
async def test_missing_text_hint_uses_only_unambiguous_authored_text_questions(
    script: str,
    prompt: str,
    variable: str | None,
    placeholder: str | None,
    expected: str | None,
) -> None:
    """Only an exact authored hint match can repair a missing text placeholder."""
    engine = _engine(
        _arguments(
            type="text",
            prompt=prompt,
            options=[],
            variable=variable,
            placeholder=placeholder,
        )
    )
    session = await engine.new_session(script)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert spec.placeholder == expected


def _engine(arguments: dict) -> Engine:
    """Build an offline engine that asks once, then consumes the accepted answer."""

    async def model(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Emit the configured interaction or continue after its tool result."""
        if any(isinstance(p, ToolReturnPart) for p in messages[-1].parts):
            yield "Continue with the learner's actual project."
        else:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="question",
                    json_args=json.dumps(arguments),
                )
            }

    return Engine(FunctionModel(stream_function=model))


def _arguments(**changes: object) -> dict:
    return {
        "type": "single_or_text",
        "prompt": "How would you like to start?",
        "options": [{"display": option} for option in [*_CHOICES, _HINT]],
        "variable": "project_path",
        "placeholder": _HINT,
        **changes,
    }


@pytest.mark.parametrize("marker", ["", "..."])
@pytest.mark.parametrize("placeholder", [None, _HINT])
@pytest.mark.parametrize("kind", ["single", "single_or_text"])
async def test_generated_hint_button_becomes_only_the_authored_input(
    marker: str,
    placeholder: str | None,
    kind: str,
) -> None:
    arguments = _arguments(
        type=kind,
        placeholder=placeholder,
        options=[{"display": option} for option in [*_CHOICES, marker + _HINT]],
    )
    engine = _engine(arguments)
    session = await engine.new_session(_SCRIPT)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in spec.options] == _CHOICES
    assert spec.type == "single_or_text"
    assert spec.placeholder == _HINT
    parsed = InteractionParser().parse(render_interaction(spec))
    assert [o["display"] for o in parsed["buttons"]] == _CHOICES
    assert parsed["question"] == _HINT
    session = Session.loads(session.dumps())
    answer = "I want to build a reading assistant."
    events = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=answer))
    ]
    assert any(isinstance(e, MemoryUpdated) and e.value == answer for e in events)
    assert session.memory["project_path"] == answer


@pytest.mark.parametrize(
    "reason",
    [
        "different_variable",
        "different_options",
        "reordered",
        "different_placeholder",
        "fence",
        "already_correct",
        "real_button",
        "different_value",
        "ambiguous",
    ],
)
async def test_only_an_unambiguous_authored_hint_duplication_is_repaired(
    reason: str,
) -> None:
    script = _SCRIPT
    arguments = _arguments()
    if reason == "different_variable":
        arguments["variable"] = "another_question"
    elif reason == "different_options":
        arguments["options"][0]["display"] = "A model-authored follow-up"
    elif reason == "reordered":
        arguments["options"][:2] = list(reversed(arguments["options"][:2]))
    elif reason == "different_placeholder":
        arguments["placeholder"] = "A different question"
    elif reason == "fence":
        script = "````\n```\n" + script + "\n````\nTeach normally."
    elif reason == "already_correct":
        arguments["options"].pop()
    elif reason == "real_button":
        script = script.replace(" | ...", " | " + _HINT + " | ...")
    elif reason == "different_value":
        arguments["options"][-1]["value"] = "real_answer"
    elif reason == "ambiguous":
        arguments["placeholder"] = None
        script += "\n" + _SCRIPT.replace("..." + _HINT, "...Another hint").replace(
            " | ...Another hint", " | " + _HINT + " | ...Another hint"
        )
    engine = _engine(arguments)
    session = await engine.new_session(script)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in spec.options] == [
        o["display"] for o in arguments["options"]
    ]
    assert spec.placeholder == arguments["placeholder"]


async def test_saved_pending_hint_is_repaired_on_reload_without_changing_history() -> (
    None
):
    engine = _engine(_arguments())
    session = await engine.new_session("Teach a dynamic question.")
    _ = [e async for e in engine.run_turn(session)]
    session.script = ScriptBundle(script=_SCRIPT)
    session = Session.loads(session.dumps())
    history = session.messages.copy()
    events = [e async for e in engine.run_turn(session, InteractionResponseTurn())]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in spec.options] == _CHOICES
    assert session.messages == history


@pytest.mark.parametrize(
    "script",
    [
        "?[%{{project_path}} Start a new project | Improve an existing assistant | Use course materials | ...Describe my project directly](https://example.org)",
        "<!-- " + _SCRIPT + " -->",
        "```example\n" + _SCRIPT,
        "   ~~~~example\n" + _SCRIPT + "\n   ~~~~~",
        "````example\n```\n" + _SCRIPT + "\n`````",
        "    " + _SCRIPT,
        "\t" + _SCRIPT,
        " \t" + _SCRIPT,
    ],
)
async def test_examples_and_links_cannot_authorize_a_repair(script: str) -> None:
    engine = _engine(_arguments())
    session = await engine.new_session(script)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in spec.options] == [*_CHOICES, _HINT]


@pytest.mark.parametrize("variable", [None, "project_path"])
async def test_multiple_choice_stored_values_and_escaped_input_hint_survive(
    variable: str | None,
) -> None:
    prefix = "%{{" + variable + "}} " if variable else ""
    script = "?[" + prefix + r"First//one || Second//two || ...Describe a\|b\.\.\.]"
    hint = "Describe a|b..."
    arguments = _arguments(
        type="multi_or_text",
        variable=variable,
        placeholder=hint,
        options=[
            {"display": "First", "value": "one"},
            {"display": "Second", "value": "two"},
            {"display": hint},
        ],
    )
    engine = _engine(arguments)
    session = await engine.new_session(script)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert [(o.display, o.stored) for o in spec.options] == [
        ("First", "one"),
        ("Second", "two"),
    ]
    assert spec.type == "multi_or_text"
    assert spec.variable == variable
    assert spec.placeholder == hint
    parsed = InteractionParser().parse(render_interaction(spec))
    assert parsed["is_multi_select"] is True
    assert parsed["question"] == hint


@pytest.mark.parametrize(
    ("display_form", "value_form", "placeholder_form", "marker"),
    [
        ("raw", "raw", "raw", ""),
        ("raw", "raw", "decoded", ""),
        ("decoded", "decoded", "raw", ""),
        ("raw", "decoded", "raw", ""),
        ("decoded", "raw", "raw", ""),
        ("raw", "raw", "raw", "..."),
    ],
)
async def test_verbatim_authored_hint_escapes_are_repaired(
    display_form: str,
    value_form: str,
    placeholder_form: str,
    marker: str,
) -> None:
    """Match only the authored raw or decoded hint, retaining actual free text."""
    forms = {"raw": r"Describe a\|b\/c\.\.\.\]", "decoded": "Describe a|b/c...]"}
    script = _SCRIPT.replace(_HINT, forms["raw"])
    arguments = _arguments(
        placeholder=forms[placeholder_form],
        options=[
            *[{"display": option} for option in _CHOICES],
            {
                "display": marker + forms[display_form],
                "value": marker + forms[value_form],
            },
        ],
    )
    engine = _engine(arguments)
    session = await engine.new_session(script)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in spec.options] == _CHOICES
    assert spec.placeholder == forms["decoded"]
    parsed = InteractionParser().parse(render_interaction(spec))
    assert [o["display"] for o in parsed["buttons"]] == _CHOICES
    assert parsed["question"] == forms["decoded"]
    session = Session.loads(session.dumps())
    answer = r"My project uses a\|b literally."
    _ = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=answer))
    ]
    assert session.memory["project_path"] == answer


@pytest.mark.parametrize("real_choice", [True, False])
async def test_raw_hint_does_not_remove_a_real_choice_or_different_stored_value(
    real_choice: bool,
) -> None:
    """Escape compatibility must preserve deliberate answers and their stored values."""
    raw = r"Describe a\|b"
    script = _SCRIPT.replace(_HINT, raw)
    if real_choice:
        script = script.replace(" | ...", " | " + raw + " | ...")
    arguments = _arguments(
        placeholder=raw,
        options=[
            *[{"display": option} for option in _CHOICES],
            {"display": raw, "value": raw if real_choice else "real_answer"},
        ],
    )
    engine = _engine(arguments)
    session = await engine.new_session(script)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert len(spec.options) == 4
    assert spec.options[-1].stored == ("Describe a|b" if real_choice else "real_answer")


async def test_raw_pending_hint_is_repaired_without_changing_history() -> None:
    """Repair persisted raw hints through the same helper before resumption."""
    raw = r"Describe a\|b"
    engine = _engine(
        _arguments(
            placeholder=raw,
            options=[{"display": option} for option in [*_CHOICES, raw]],
        )
    )
    session = await engine.new_session("Teach a dynamic question.")
    _ = [e async for e in engine.run_turn(session)]
    session.script = ScriptBundle(script=_SCRIPT.replace(_HINT, raw))
    session = Session.loads(session.dumps())
    history = session.messages.copy()
    events = [e async for e in engine.run_turn(session, InteractionResponseTurn())]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in spec.options] == _CHOICES
    assert spec.placeholder == "Describe a|b"
    assert session.messages == history


async def test_real_question_after_indented_example_still_repairs() -> None:
    """Skipping code must not suppress the following ordinary lesson control."""
    engine = _engine(_arguments())
    session = await engine.new_session("    " + _SCRIPT + "\n\n" + _SCRIPT)
    events = [e async for e in engine.run_turn(session)]
    spec = next(e.spec for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in spec.options] == _CHOICES
    assert spec.placeholder == _HINT
