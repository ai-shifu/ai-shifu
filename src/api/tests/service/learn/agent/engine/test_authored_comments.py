"""Author notes never become model instructions or runtime declarations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    InteractionResponseTurn,
    ScriptBundle,
    collected_names,
    detect_v1_syntax,
    render_first_prompt,
)
from flaskr.service.learn.agent.engine.script import substitution_names
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("intro", ["Topic", "- Topic", "1. Topic\n"])
@pytest.mark.parametrize("indent", ["    ", "\t"])
def test_indented_author_notes_are_not_prompts_or_collected_variables(
    intro: str, indent: str
) -> None:
    source = (
        f"{intro}\n{indent}<!-- private %{{{{goal}}}} {{{{secret}}}} -->\n"
        f"{indent}Explain the topic"
    )
    bundle = ScriptBundle(script=source)
    prompt = render_first_prompt(bundle, {})
    assert "private" not in prompt
    assert "goal" not in prompt
    assert "secret" not in prompt
    assert "Explain the topic" in prompt
    assert collected_names(source) == frozenset()
    assert substitution_names(bundle) == frozenset()
    assert not detect_v1_syntax(source)
    assert bundle.script == source


def test_comments_are_removed_before_substitution_without_changing_source() -> None:
    bundle = ScriptBundle(
        script="Hello {{name}}<!-- private script %{{name}} {{secret}} -->.",
        constraints="Be brief.<!-- private constraint {{secret}} -->",
        extras={"reference": "Visible reference.<!-- private reference -->"},
    )
    original = bundle.to_dict()
    literal = "<!-- learner literal -->"
    prompt = render_first_prompt(bundle, {"name": literal})
    assert "private" not in prompt
    assert "secret" not in prompt
    assert f"Hello {literal}." in prompt
    assert (
        literal
        in json.loads(prompt.split("<memory>\n")[1].split("\n</memory>")[0])["name"]
    )
    assert "Visible reference." in prompt
    assert bundle.to_dict() == original
    assert collected_names(bundle.script) == frozenset()
    assert substitution_names(bundle) == frozenset({"name"})
    assert not detect_v1_syntax("Teach plain prose.<!-- ?[%{{hidden}} A | B] -->")


async def test_first_request_ignores_commented_notation_in_every_document() -> None:
    seen = []

    async def spy(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        seen.extend(messages)
        yield "Visible lesson."

    bundle = ScriptBundle(
        script="Visible lesson.<!-- private script ?[%{{hidden}} A | B] -->",
        constraints="Be brief.<!-- private constraint {{secret}} -->",
        extras={"reference": "Visible reference.<!-- private reference --- -->"},
    )
    engine = Engine(FunctionModel(stream_function=spy))
    session = await engine.new_session(bundle)
    _ = [event async for event in engine.run_turn(session)]
    requests = [message for message in seen if isinstance(message, ModelRequest)]
    assert "Script notation" not in (requests[0].instructions or "")
    prompt = next(
        part.content for part in requests[0].parts if isinstance(part, UserPromptPart)
    )
    assert "private" not in prompt
    assert "Visible lesson." in prompt
    assert session.script == bundle


async def test_resumed_answer_reference_excludes_commented_requirements() -> None:
    script = "# Exercise\nUse the visible rule.<!-- private criterion -->\n?[...Explain the rule]\n"
    seen: list[str] = []

    async def spy(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        if any(
            isinstance(part, ToolReturnPart)
            for message in messages
            for part in message.parts
        ):
            seen.append(messages[-1].instructions or "")
            yield "Useful feedback."
        else:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args=json.dumps(
                        {
                            "type": "text",
                            "prompt": "Explain",
                            "placeholder": "Explain the rule",
                        }
                    ),
                    tool_call_id="exercise",
                )
            }

    engine = Engine(FunctionModel(stream_function=spy))
    session = await engine.new_session(script)
    _ = [event async for event in engine.run_turn(session)]
    _ = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(text="My answer")
        )
    ]
    assert seen
    assert "authored_section" in seen[0]
    assert "Use the visible rule." in seen[0]
    assert "private criterion" not in seen[0]
    assert session.script.script == script
