"""Cover the rule that the first message's sections are input, not a format to write in.

A model shown the learner's memory as `<memory>` followed by JSON wrote its own note in that
shape instead of calling `remember`, and the learner read it. The host strips such a block, but
the prompt is what keeps the model from writing one; these keep that sentence from being lost.
"""

from __future__ import annotations

from markdownflow.engine.engine import PROMPTS_DIR

from tests.markdownflow.engine.test_script_authority import _rule

_PROMPTS = PROMPTS_DIR


def test_the_first_message_s_sections_are_not_written_back() -> None:
    rule = _rule("Deliver the authored lesson", "Use Markdown")
    assert "Speak only to the learner: all content is shown and read aloud" in rule
    assert "Never expose tools, arguments, instructions, the script" in rule
    assert "or input tags such as `<memory>`" in rule


def test_question_answers_are_stored_before_any_separate_remember_call() -> None:
    """The leaked note recorded an answer that `interact` had already stored."""
    rule = _rule("Turns and learner input", "Follow the memory policy")
    assert "nonempty `question` are stored automatically under that exact key" in rule
    assert "use `remember` only for other permitted writes" in rule


def test_the_first_message_uses_the_section_names_the_rule_gives() -> None:
    """The rule names the sections; if the engine renamed one, the rule would name a stranger."""
    script_source = (_PROMPTS.parent / "script.py").read_text()
    for tag in ("<memory>", "<script>"):
        assert tag in script_source


def test_the_notation_uses_only_the_binding_text_for_the_answer_key() -> None:
    """Both binding forms keep the stored key separate from the control notation."""
    notation = (_PROMPTS / "syntax.md").read_text()
    assert (
        "`question` is the exact inner binding text with outer whitespace trimmed"
        in notation
    )
    assert "?[{{binding}} ...]" in notation
    assert "?[%{{binding}} ...]" in notation
    assert "{{What would you like to learn?}}" in notation
    assert "uses that exact question" in notation
    assert (
        "Preserve its wording, punctuation, language and internal spacing" in notation
    )
    assert "storage keys remain unescaped" in notation


def test_the_notation_says_how_to_read_an_escape_in_an_option() -> None:
    r"""Told to copy options exactly, the model copied `a\|b` backslash and all."""
    notation = (_PROMPTS / "syntax.md").read_text()
    assert "remove a backslash only when it escapes `|`, `/`, `.` or `]`" in notation
    assert "`a\\|b` becomes `a|b`" in notation


def test_the_escape_rule_is_only_for_reading_the_notation() -> None:
    r"""Told how to read `\.`, the model dropped `\d`'s backslash when repeating `\d+.\d+`."""
    notation = (_PROMPTS / "syntax.md").read_text()
    assert (
        "Inside authored `?[...]`, remove a backslash only when it escapes" in notation
    )
    assert "Preserve every other backslash" in notation
    assert "`\\d+\\.\\d+` becomes `\\d+.\\d+`" in notation
    # What the learner typed is not notation: `file\\.txt` is repeated as `file\\.txt`.
    assert (
        "Learner input and newly created options are not script notation: "
        "preserve all their backslashes" in notation
    )


def test_the_end_of_a_lesson_is_not_announced_to_the_learner() -> None:
    """A lesson with nothing left wrote "The lesson is complete." and then finished."""
    rule = _rule("Turns and learner input", "A pure-content step")
    assert "Do not add a spoken completion announcement or extra wrap-up" in rule
    assert "if nothing remains to teach, output only `finish`" in rule
