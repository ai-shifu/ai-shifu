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
    rule = _rule(12)
    assert (
        "tagged sections of the first message, such as `<memory>` and `<script>`"
        in rule
    )
    assert "not a format to write in" in rule
    assert "a tool call, or a tool's arguments" in rule


def test_question_answers_are_stored_before_any_separate_remember_call() -> None:
    """The leaked note recorded an answer that `interact` had already stored."""
    rule = _rule(4)
    assert "with a nonempty `question` is stored under that exact wording" in rule
    assert "Use `remember` only for other writes allowed by the memory policy" in rule


def test_the_first_message_uses_the_section_names_the_rule_gives() -> None:
    """The rule names the sections; if the engine renamed one, the rule would name a stranger."""
    script_source = (_PROMPTS.parent / "script.py").read_text()
    for tag in ("<memory>", "<script>"):
        assert tag in script_source


def test_the_notation_uses_one_question_for_display_and_storage() -> None:
    """The syntax and system instructions agree on what identifies an answer."""
    notation = (_PROMPTS / "syntax.md").read_text()
    assert "use that exact text in `interact.question`" in notation
    assert "?[{{question}} ...]" in notation
    assert "{{What would you like to learn?}}" in notation
    assert 'question="What would you like to learn?"' in notation
    assert "The answer is saved under `What would you like to learn?`" in notation


def test_the_notation_says_how_to_read_an_escape_in_an_option() -> None:
    r"""Told to copy options exactly, the model copied `a\|b` backslash and all."""
    notation = (_PROMPTS / "syntax.md").read_text()
    assert "only stops that character being read as notation" in notation
    assert "is the option `a|b`" in notation


def test_the_escape_rule_is_only_for_reading_the_notation() -> None:
    r"""Told how to read `\.`, the model dropped `\d`'s backslash when repeating `\d+.\d+`."""
    notation = (_PROMPTS / "syntax.md").read_text()
    assert (
        "This is only how to read the notation of the script's own questions"
        in notation
    )
    assert "the second `\\d` keeps its backslash" in notation
    # What the learner typed is not notation: `file\\.txt` is repeated as `file\\.txt`.
    assert (
        "what the learner typed, an option you made up -- is not notation" in notation
    )


def test_the_end_of_a_lesson_is_not_announced_to_the_learner() -> None:
    """A lesson with nothing left wrote "The lesson is complete." and then finished."""
    rule = _rule(9)
    assert "do not also tell the learner it has ended" in rule
    assert "write nothing and call it" in rule
