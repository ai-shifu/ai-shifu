"""Literal authored scripts and exact question-key collection."""

import pytest
from markdownflow.engine import (
    ScriptBundle,
    collected_questions,
    detect_v1_syntax,
    render_first_prompt,
)


@pytest.mark.parametrize(
    "source",
    [
        "intro\n---\nnext",
        "?[%{{What is your goal?}} A|B]",
        "===verbatim===",
        "!===\ntext\n!===",
    ],
)
def test_detects_notation(source: str) -> None:
    assert detect_v1_syntax(source)


@pytest.mark.parametrize(
    "source",
    [
        "Hello {{name}}",
        "Remember %{{name}}",
        "{{unclosed",
        "plain prose",
        "?[link](https://example.com)",
        "\\?[escaped]",
        "```\n---\n?[A|B]\n```",
    ],
)
def test_plain_braces_and_examples_do_not_enable_notation(source: str) -> None:
    assert not detect_v1_syntax(source)


@pytest.mark.parametrize(
    "source",
    [
        "Hello {{name}}",
        "%{{question}}",
        "{{missing}}",
        "{{ unclosed",
        "===Hi {{name}}===",
        "!===\n{{name}}\n!===",
        "```js\n{{name}}\n```",
        '<span title="{{name}}">{{name}}</span>',
        "?[%{{ What is your goal? }} A|B]",
    ],
)
def test_authored_documents_remain_literal_regardless_of_memory(source: str) -> None:
    bundle = ScriptBundle(
        script=source, constraints=source, extras={"reference": source}
    )
    prompt = render_first_prompt(bundle, {"name": "Lin", "question": "old answer"})
    assert f"<script>\n{source}\n</script>" in prompt
    assert f"<constraints>\n{source}\n</constraints>" in prompt
    assert f'<extra name="reference">\n{source}\n</extra>' in prompt
    assert "unavailable_learner_value" not in prompt
    assert (
        prompt.index("<memory>")
        < prompt.index("<script>")
        < prompt.index("<constraints>")
    )


def test_bundle_roundtrip() -> None:
    bundle = ScriptBundle(script="s", constraints=None, extras={"ref": "1"})
    assert ScriptBundle.from_dict(bundle.to_dict()) == bundle


def test_only_actual_question_controls_define_memory_keys() -> None:
    source = (
        "{{read}} %{{prose}}\n"
        "?[%{{ What is your goal? }} A | B]\n"
        "?[%{{Which [path] | level//hint...?}} ...Your answer]\n"
        "?[No memory key]\n"
        "```\n?[%{{example}} A|B]\n```\n"
        "    ?[%{{indented example}} A|B]\n"
        "<!-- ?[%{{comment}} A|B] -->\n"
        "?[%{{link}} A|B](https://example.com)\n"
    )
    assert collected_questions(source) == frozenset(
        {"What is your goal?", "Which [path] | level//hint...?"}
    )


def test_prior_answers_do_not_prefill_a_question_being_asked_again() -> None:
    question = "What is your goal?"
    source = f"?[%{{{{{question}}}}} A|B]\nDiscuss the answer from memory."
    prompt = render_first_prompt(
        ScriptBundle(script=source), {question: "stale goal", "Nickname?": "Lin"}
    )
    assert "stale goal" not in prompt
    assert '"Nickname?": "Lin"' in prompt
    assert f"<script>\n{source}\n</script>" in prompt


@pytest.mark.parametrize("raw", ["", "   ", "What\nnow?", "bad\x00key", "bad\u0085key"])
def test_authoring_scan_keeps_invalid_question_markers_for_validation(raw: str) -> None:
    from markdownflow.engine.script import authored_question_markers

    source = "?[%{{" + raw + "}} Yes|No]"
    markers = list(authored_question_markers(source))
    assert len(markers) == 1
    assert markers[0].raw_name == raw
    assert markers[0].name is None
    assert collected_questions(source) == frozenset()


def test_authoring_scan_distinguishes_no_key_and_inactive_marker_examples() -> None:
    from markdownflow.engine.script import authored_question_markers

    source = "?[Yes|No]\n```\n?[%{{ }} Yes|No]\n```\n<!-- ?[%{{bad\x00key}} Yes|No] -->"
    assert list(authored_question_markers(source)) == []
    valid = list(authored_question_markers("?[%{{ \n Why  now? \n }} Yes|No]"))
    assert [marker.name for marker in valid] == ["Why  now?"]
