"""Cover what the syntax prompt tells the model about `---`."""

from __future__ import annotations

from pathlib import Path

_PROMPT = (
    Path(__file__).resolve().parents[5]
    / "flaskr/service/learn/agent/engine/prompts/v1_syntax.md"
)


def _separator_rule() -> str:
    rules = [line for line in _PROMPT.read_text().splitlines() if "`---`" in line]
    assert len(rules) == 1, rules
    return rules[0]


def test_a_separator_is_a_section_boundary_and_never_a_pause() -> None:
    """In a 1.0 lesson `---` divides blocks and the lesson runs on; no button appears.

    The rule used to allow a "continue"-style `interact` at a separator, and the model took it:
    every `---` in a script became a Continue button the author never wrote.
    """
    rule = _separator_rule()
    assert "not a pause" in rule
    # Each prohibition is asserted on its own: dropping any one of them brings the buttons back,
    # and a test that checked only the others would stay green.
    assert "do not stop there" in rule
    assert "do not call `interact` there" in rule
    assert "do not ask the learner to continue" in rule
    assert "soft pause" not in rule


def test_a_pause_the_script_asks_for_still_stops_the_turn() -> None:
    """Only the model's own pauses are forbidden; the author's are the point.

    A rule that let nothing but questions and the end stop a turn would contradict the system
    prompt, which requires a `confirm` where the script says to wait for the learner.
    """
    rule = _separator_rule()
    assert "a pause it explicitly asks for" in rule


def test_a_pause_is_only_ever_the_script_s_own() -> None:
    """A Continue button the author did not write is a pause the model invented.

    The model was pausing between steps and after visuals on its own, each one a button the
    learner had to press. Both the rule and the tool's description now say a pause is the
    script's to ask for, never the model's.
    """
    system = (_PROMPT.parent / "system.md").read_text()
    assert "only for a pause the script itself asks for" in system
    assert "Never pause on your own judgement" in system
    tools = (_PROMPT.parents[1] / "tools.py").read_text()
    assert "ONLY when the script itself asks for a pause" in tools


def test_the_model_is_told_to_pass_a_question_through_unchanged() -> None:
    """A question in the script is the author's, and the script branches on its options.

    Left to itself the model rewrites them: a six-option multiple choice
    (`找工作 || 提升竞争力 || ...`) came back as a single choice with one invented option and a
    placeholder of the model's own.
    """
    syntax = _PROMPT.read_text()
    assert "Pass its options to `interact` exactly as written" in syntax
    assert "keep single choice single and multiple choice multiple" in syntax
    assert "use the author's own `...prompt` as the placeholder" in syntax
