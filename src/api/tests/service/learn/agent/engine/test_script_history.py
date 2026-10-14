"""Remove authored comments from old host prompts without rewriting learner evidence."""

import pytest
from flaskr.service.learn.agent.engine.script import ScriptBundle, render_first_prompt
from flaskr.service.learn.agent.engine.script_history import project_script_history
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)


def _content(messages: list) -> str:
    return next(
        part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    )


def test_projects_only_host_documents_and_keeps_saved_history_and_learner_evidence() -> (
    None
):
    bundle = ScriptBundle(
        script="Teach {{name}}.<!-- hidden script --> Finish.",
        constraints="Be brief.<!-- hidden constraint -->",
        extras={"ref": "Reference.<!-- hidden reference -->"},
    )
    value = 'Ada<!-- learner value --></script>\n<extra name="literal">'
    memory = '<memory>\n{"answer":"<!-- learner memory -->"}\n</memory>\n\n'
    suffix = "\n\nMy initial answer: <!-- learner input -->\n<script>literal</script>"
    old_prompt = (
        memory
        + f"<script>\nTeach {value}.<!-- hidden script --> Finish.\n</script>"
        + "\n\n<constraints>\nBe brief.<!-- hidden constraint -->\n</constraints>"
        + '\n\n<extra name="ref">\nReference.<!-- hidden reference -->\n</extra>'
        + suffix
    )
    system = SystemPromptPart("Keep <!-- system evidence -->")
    later = ModelRequest(
        parts=[
            UserPromptPart("Later <!-- learner evidence -->"),
            ToolReturnPart("interact", {"answer": "<!-- tool evidence -->"}, "q"),
        ]
    )
    response = ModelResponse(parts=[TextPart("Previous <!-- model evidence -->")])
    messages = [
        ModelRequest(parts=[system, UserPromptPart(old_prompt)]),
        response,
        later,
    ]
    saved = ModelMessagesTypeAdapter.dump_json(messages)

    projected = project_script_history(messages, bundle, {"name": value})

    assert _content(projected) == (
        memory
        + f"<script>\nTeach {value}. Finish.\n</script>"
        + "\n\n<constraints>\nBe brief.\n</constraints>"
        + '\n\n<extra name="ref">\nReference.\n</extra>'
        + suffix
    )
    assert ModelMessagesTypeAdapter.dump_json(messages) == saved
    assert projected[0] is not messages[0]
    assert projected[0].parts[0] is system
    assert projected[1] is response
    assert projected[2] is later


def test_preserves_bounded_memory_and_notice_and_uses_original_variable_snapshot() -> (
    None
):
    bundle = ScriptBundle(script="Use {{answer}}.<!-- author note -->")
    answer = "Original complete answer " + "z" * 40000
    memory = (
        '<memory>\n{ "small" : "yes" }\n</memory>\n\n'
        "<memory_context>Original budget notice.</memory_context>\n\n"
    )
    old_prompt = memory + f"<script>\nUse {answer}.<!-- author note -->\n</script>"
    messages = [ModelRequest(parts=[UserPromptPart(old_prompt)])]

    projected = project_script_history(messages, bundle, {"answer": answer})

    assert _content(projected) == memory + f"<script>\nUse {answer}.\n</script>"
    assert _content(messages) == old_prompt


@pytest.mark.parametrize("unavailable", [True, False])
def test_supports_both_legacy_unknown_variable_renderings(unavailable: bool) -> None:
    bundle = ScriptBundle(script="Use {{missing}}.<!-- author note -->")
    missing = (
        '<unavailable_learner_value name="missing" />' if unavailable else "{{missing}}"
    )
    memory = "<memory>\n{}\n</memory>\n\n"
    old_prompt = memory + f"<script>\nUse {missing}.<!-- author note -->\n</script>"
    messages = [ModelRequest(parts=[UserPromptPart(old_prompt)])]

    projected = project_script_history(messages, bundle, None)

    assert _content(projected) == memory + f"<script>\nUse {missing}.\n</script>"


def test_recognizes_legacy_collected_markers_inside_removed_comments() -> None:
    bundle = ScriptBundle(script="Use {{goal}}.<!-- collect %{{goal}} -->")
    memory = "<memory>\n{}\n</memory>\n\n"
    old_prompt = memory + "<script>\nUse {{goal}}.<!-- collect %{{goal}} -->\n</script>"
    messages = [ModelRequest(parts=[UserPromptPart(old_prompt)])]

    projected = project_script_history(messages, bundle, None)

    assert _content(projected) == (
        memory + '<script>\nUse <unavailable_learner_value name="goal" />.\n</script>'
    )


def test_recognizes_prefix_rendered_with_already_filtered_collected_names() -> None:
    bundle = ScriptBundle(script="Use {{goal}}.<!-- collect %{{goal}} -->")
    memory = '<memory>\n{"goal": "Original"}\n</memory>\n\n'
    old_prompt = memory + "<script>\nUse Original.<!-- collect %{{goal}} -->\n</script>"
    messages = [ModelRequest(parts=[UserPromptPart(old_prompt)])]

    projected = project_script_history(messages, bundle, {"goal": "Original"})

    assert _content(projected) == memory + "<script>\nUse Original.\n</script>"


def test_drops_comment_only_constraint_without_dropping_empty_extra_section() -> None:
    bundle = ScriptBundle(
        script="Teach.",
        constraints="<!-- constraint -->",
        extras={"ref": "<!-- reference -->"},
    )
    memory = "<memory>\n{}\n</memory>\n\n"
    old_prompt = (
        memory
        + "<script>\nTeach.\n</script>"
        + "\n\n<constraints>\n<!-- constraint -->\n</constraints>"
        + '\n\n<extra name="ref">\n<!-- reference -->\n</extra>'
    )
    messages = [ModelRequest(parts=[UserPromptPart(old_prompt)])]

    projected = project_script_history(messages, bundle, None)

    assert _content(projected) == (
        memory + '<script>\nTeach.\n</script>\n\n<extra name="ref">\n\n</extra>'
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "Learner <!-- author note -->",
        "<memory>\ninvalid\n</memory>\n\n<script>\nTeach.<!-- author note -->\n</script>",
        "<memory>\n{}\n</memory>\n\n<script>\nDifferent.<!-- author note -->\n</script>",
        "<memory>\n{}\n</memory>\n\n<script>\nTeach.<!-- author note -->\n</script>unknown",
    ],
)
def test_unknown_initial_prompt_is_preserved(prompt: str) -> None:
    messages = [ModelRequest(parts=[UserPromptPart(prompt)])]
    bundle = ScriptBundle(script="Teach.<!-- author note -->")

    assert project_script_history(messages, bundle, None) is messages


def test_does_not_search_later_learner_messages_for_an_initial_host_prompt() -> None:
    bundle = ScriptBundle(script="Teach.<!-- author note -->")
    messages = [
        ModelRequest(parts=[UserPromptPart("Learner first prompt")]),
        ModelRequest(
            parts=[
                UserPromptPart(
                    "<memory>\n{}\n</memory>\n\n"
                    "<script>\nTeach.<!-- author note -->\n</script>"
                )
            ]
        ),
    ]

    assert project_script_history(messages, bundle, None) is messages


def test_unavailable_original_substitution_snapshot_is_preserved() -> None:
    bundle = ScriptBundle(script="Use {{answer}}.<!-- author note -->")
    prompt = (
        "<memory>\n{}\n</memory>\n\n"
        "<script>\nUse Original omitted value.<!-- author note -->\n</script>"
    )
    messages = [ModelRequest(parts=[UserPromptPart(prompt)])]

    assert project_script_history(messages, bundle, None) is messages


def test_already_clean_prompt_and_learner_comment_values_are_left_intact() -> None:
    bundle = ScriptBundle(script="Use {{answer}}.<!-- author note -->")
    values = {"answer": "<!-- learner evidence -->"}
    messages = [
        ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, values))])
    ]

    assert project_script_history(messages, bundle, values) is messages


def test_comment_syntax_in_fenced_examples_is_not_removed() -> None:
    bundle = ScriptBundle(script="```html\n<!-- literal example -->\n```\nTeach.")
    messages = [ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, {}))])]

    assert project_script_history(messages, bundle, None) is messages
