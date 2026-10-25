"""Authored brace text stays literal through SDK calls and stored-session resumption."""

from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import ScriptBundle, render_first_prompt


@pytest.mark.parametrize("memory", [{}, {"goal": None}, {"goal": ""}])
def test_brace_text_does_not_read_memory(memory: dict) -> None:
    """A skipped earlier lesson cannot turn a template into a learner fact."""
    bundle = ScriptBundle(
        script="Show `{{goal}}` in a timeline; mark missing evidence unconfirmed.",
        constraints="Connect the explanation to {{goal}}.",
    )
    prompt = render_first_prompt(bundle, memory)
    assert prompt.count("{{goal}}") == 2
    assert "unavailable_learner_value" not in prompt
    assert bundle.script.startswith("Show `{{goal}}`")
    assert memory.get("goal") in (None, "")


def test_known_false_zero_and_complete_values_remain_exact() -> None:
    """Unavailability does not erase false, zero, or budget-omitted stored text."""
    prompt = render_first_prompt(
        ScriptBundle(script="{{goal}} / {{count}} / {{enabled}}"),
        {"goal": "Keep the whole learner answer.", "count": 0, "enabled": False},
        memory_limit=2,
    )
    assert "{{goal}} / {{count}} / {{enabled}}" in prompt
    assert "Keep the whole learner answer." not in prompt
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
async def test_literal_braces_reach_initial_and_resumed_sdk_requests(
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
        assert "Show {{goal}}, then ask ?[Next]." in payload
        assert "ordinary authored text" in info.instructions
        assert "unavailable_learner_value" not in payload
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
    assert "Personal fact: {{水平}}." in prompt
    assert "unavailable_learner_value" not in prompt


def test_verbatim_content_never_interpolates_memory() -> None:
    """Known memory never changes authored verbatim source."""
    prompt = render_first_prompt(
        ScriptBundle(script="===Hello {{name}}.===\n!===\n{{name}}\n!==="),
        {"name": "Ada"},
    )
    assert "===Hello {{name}}.===" in prompt
    assert "!===\n{{name}}\n!===" in prompt


@pytest.mark.parametrize(
    "prefix",
    [
        "{{ unfinished\n",
        "%{{ unfinished\n\n",
        "{{ complete }} ",
        "{{ unfinished\n\n```md\n?[example]\n```\n",
        "{{ unfinished\n<!--\n?[example]\n-->\n",
        "{{ unfinished\n<script>\n?[example]\n</script>\n",
        "{{ unfinished\n` then ",
    ],
)
def test_standalone_braces_never_hide_the_next_question_in_any_stream_partition(
    prefix: str,
) -> None:
    """Ordinary braces cannot own later controls or native code/comment boundaries."""
    from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
    from markdownflow.engine import collected_questions
    from markdownflow.engine.tools import _script_questions

    question = "?[%{{ What is your goal? }} A|B]"
    source = prefix + question
    assert collected_questions(source) == frozenset({"What is your goal?"})
    assert [control.question for control in _script_questions(source)] == [
        "What is your goal?"
    ]
    partitions = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for chunks in partitions:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in chunks) + syntax.flush()
        assert shown == prefix
        assert syntax.spans == [question]


def test_literal_option_brace_groups_keep_the_browser_parser_contract() -> None:
    """Question text and literal option groups preserve their existing delimiter boundaries."""
    from markdownflow.engine.tools import _script_questions, script_options

    source = "?[%{{ Pick [a|b]? }} A {{x|y}} | B]"
    question = _script_questions(source)[0]
    assert question.question == "Pick [a|b]?"
    assert [choice.strip() for choice in question.choices] == ["A {{x|y}}", "B"]
    assert script_options(source)["A {{x|y}}"] == "A {{x|y}}"
