"""Cover what the syntax prompt tells the model about `---`."""

from __future__ import annotations

from markdownflow.engine.engine import PROMPTS_DIR

from tests.markdownflow.engine.test_script_authority import _rule

_PROMPT = PROMPTS_DIR / "syntax.md"


def _separator_rule() -> str:
    rules = [line for line in _PROMPT.read_text().splitlines() if "`---`" in line]
    assert len(rules) == 1, rules
    return rules[0]


def test_a_separator_is_a_section_boundary_and_never_a_pause() -> None:
    """In a scripted lesson `---` divides blocks and the lesson runs on; no button appears.

    The rule used to allow a "continue"-style `interact` at a separator, and the model took it:
    every `---` in a script became a Continue button the author never wrote.
    """
    rule = _separator_rule()
    assert "separates sections, not turns" in rule
    # Each prohibition is asserted on its own: dropping any one of them brings the buttons back,
    # and a test that checked only the others would stay green.
    assert "Continue directly into the next section" in rule
    assert "do not pause or call `interact` at the divider" in rule
    pause_rule = _rule("Turns and learner input", "Use `confirm` only")
    assert "Do not add pauses between steps" in pause_rule
    assert "soft pause" not in rule


def test_a_pause_the_script_asks_for_still_stops_the_turn() -> None:
    """Only the model's own pauses are forbidden; the author's are the point.

    A rule that let nothing but questions and the end stop a turn would contradict the system
    prompt, which requires a `confirm` where the script says to wait for the learner.
    """
    rule = _separator_rule()
    assert (
        "Authored questions, explicit pauses and the end determine stopping points"
        in rule
    )


def test_a_pause_is_only_ever_the_script_s_own() -> None:
    """A Continue button the author did not write is a pause the model invented.

    The model was pausing between steps and after visuals on its own, each one a button the
    learner had to press. Both the rule and the tool's description now say a pause is the
    script's to ask for, never the model's.
    """
    rule = _rule("Turns and learner input", "Use `confirm` only")
    assert "only for an explicit authored pause, after its content" in rule
    assert (
        "Do not add pauses between steps, after visuals or to check comprehension"
        in rule
    )
    tools = " ".join((_PROMPT.parents[1] / "tools.py").read_text().split())
    assert "Use `confirm` only for an authored pause without a question" in tools
    assert "after presenting content this turn; never add one yourself" in tools


def test_the_model_is_told_not_to_narrate_its_own_work() -> None:
    """Everything the model writes is shown to the learner and read aloud to them.

    Left to itself it opens with a line of English about what it is about to do -- "I'll start
    with a warm welcome and the course cover" -- which was rendered, spoken and subtitled as the
    first thing a learner saw, in a language the lesson was not in.
    """
    rule = _rule("Deliver the authored lesson", "Use Markdown")
    assert "all content is shown and read aloud" in rule
    assert "Begin with the lesson" in rule
    assert (
        "without unsolicited greetings, introductions, filler or announcements of your progress"
        in rule
    )
    assert "the learner's language" in rule


def test_the_model_is_told_to_pass_a_question_through_unchanged() -> None:
    """A question in the script is the author's, and the script branches on its options.

    Left to itself the model rewrites them: a six-option multiple choice
    (`找工作 || 提升竞争力 || ...`) came back as a single choice with one invented option and a
    placeholder of the model's own.
    """
    syntax = _PROMPT.read_text()
    assert "Preserve every authored option, its order, display/value wording" in syntax
    assert "interaction type and placeholder" in syntax
    assert '`A | B` means `type="single"`; `A || B` means `type="multi"`' in syntax
    assert "Do not drop, add or reword choices or invent a hint" in syntax
