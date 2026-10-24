"""Keep unavailable learner facts distinct from displayable template syntax."""

from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import ScriptBundle, render_first_prompt


@pytest.mark.parametrize("memory", [{}, {"goal": None}, {"goal": ""}])
def test_missing_read_is_explicit_data_unavailability(memory: dict) -> None:
    """A skipped earlier lesson cannot turn a template into a learner fact."""
    bundle = ScriptBundle(
        script="Show `{{goal}}` in a timeline; mark missing evidence unconfirmed.",
        constraints="Connect the explanation to {{goal}}.",
    )
    prompt = render_first_prompt(bundle, memory)
    assert "{{goal}}" not in prompt
    assert prompt.count('<unavailable_learner_value name="goal" />') == 2
    assert bundle.script.startswith("Show `{{goal}}`")
    assert memory.get("goal") in (None, "")


def test_known_false_zero_and_complete_values_remain_exact() -> None:
    """Unavailability does not erase false, zero, or budget-omitted stored text."""
    prompt = render_first_prompt(
        ScriptBundle(script="{{goal}} / {{count}} / {{enabled}}"),
        {"goal": "Keep the whole learner answer.", "count": 0, "enabled": False},
        memory_limit=2,
    )
    assert "Keep the whole learner answer. / 0 / False" in prompt
    assert "unavailable_learner_value" not in prompt


def test_collected_answers_and_literal_generated_code_are_not_replaced() -> None:
    """Fresh answers and fenced CSS/JS/template examples retain their own semantics."""
    literal = "```html\n<style>.card { color: blue; }</style>\n{{goal}}\n```"
    script = "?[%{{goal}} ...Goal]\nAfter answering, use {{goal}}.\n" + literal
    prompt = render_first_prompt(ScriptBundle(script=script), {"goal": "old answer"})
    assert "old answer" not in prompt
    assert "After answering, use {{goal}}." in prompt
    assert literal in prompt
    assert "unavailable_learner_value" not in prompt


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("known", [False, True])
async def test_unavailability_reaches_initial_and_resumed_sdk_requests(
    reload: bool, known: bool
) -> None:
    """Inspect SDK inputs, retaining the distinction from actual model acceptance."""
    import json

    from markdownflow.engine import (
        ContentDelta,
        Engine,
        ErrorEvent,
        InteractionResponseTurn,
        Session,
    )
    from pydantic_ai.messages import (
        ModelMessage,
        ModelMessagesTypeAdapter,
        ModelRequest,
        UserPromptPart,
    )
    from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

    calls = 0
    output = "A recorded goal." if known else "Not yet confirmed."

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Return controlled prose/visuals after checking the actual SDK context."""
        nonlocal calls
        calls += 1
        payload = "\n".join(
            part.content
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart) and isinstance(part.content, str)
        )
        assert "{{goal}}" not in payload
        assert "Never display this metadata" in info.instructions
        assert "generated visuals" in info.instructions
        assert ("unavailable_learner_value" in payload) is not known
        yield output + "\n<div><style>.card {color: blue}</style>" + output + "</div>"
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"next-{calls}",
                json_args=json.dumps(
                    {
                        "type": "single",
                        "prompt": "",
                        "options": [{"display": "Next", "value": "Next"}],
                    }
                    if calls == 1
                    else {
                        "type": "text",
                        "prompt": "",
                        "placeholder": "Reflection",
                    }
                ),
            )
        }

    engine = Engine(FunctionModel(stream_function=stream), request_limit=1)
    session = await engine.new_session(
        "Show {{goal}}, then ask ?[Next]. After selection, show {{goal}} again and ask ?[...Reflection].",
        memory={"goal": output} if known else {},
    )
    first = [event async for event in engine.run_turn(session)]
    assert not any(isinstance(event, ErrorEvent) for event in first), first
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    second = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=["Next"])
        )
    ]
    assert not any(isinstance(event, ErrorEvent) for event in second), second
    assert output in "".join(e.text for e in second if isinstance(e, ContentDelta))
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert session.all_memory() == ({"goal": output} if known else {})
    assert calls == 2


@pytest.mark.parametrize(
    "verbatim",
    [
        "===Learn {{水平}} and {{主题}} literally.===",
        "Before ==={{水平}}=== and !==={{主题}}!=== after.",
        "!===Learn {{水平}} and {{主题}} literally.!===",
        "!===\nLearn {{水平}} and {{主题}} literally.\n!===",
    ],
)
def test_unavailable_metadata_does_not_replace_verbatim_syntax_examples(
    verbatim: str,
) -> None:
    """Authored literal placeholder examples must survive an absent learner value."""
    prompt = render_first_prompt(
        ScriptBundle(script=verbatim + "\nPersonal fact: {{水平}}."), {}
    )
    assert verbatim in prompt
    assert 'Personal fact: <unavailable_learner_value name="水平" />.' in prompt


def test_known_personalization_in_verbatim_content_keeps_existing_behavior() -> None:
    """Only unavailable metadata is excluded from authored literal spans."""
    prompt = render_first_prompt(
        ScriptBundle(script="===Hello {{name}}.===\n!===\n{{name}}\n!==="),
        {"name": "Ada"},
    )
    assert "===Hello Ada.===" in prompt
    assert "!===\nAda\n!===" in prompt
