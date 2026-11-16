"""Cover where the script's authority ends and the model's judgement begins.

Step 3 of the rollout loosens "follow the script exactly" into "the script is the task". The
loosening has a line in it that must not move: a lesson may be taught differently for different
learners, but it teaches what the author wrote and nothing else. These assert both halves, so
neither can be dropped without the suite noticing.
"""

from __future__ import annotations

import re

from markdownflow.engine.engine import PROMPTS_DIR

_PROMPTS = PROMPTS_DIR
_SYSTEM = (_PROMPTS / "system.md").read_text()


def _rule(section: str, prefix: str) -> str:
    """Return one bullet from its named section, independent of line wrapping.

    Read as a rule rather than as a line: the prompt is prose, and someone wrapping a long rule
    across two lines has not changed what it says. A parser that insisted on one physical line
    would fail on the reformatting and pass on the deletion, which is exactly backwards.
    """
    match = re.search(rf"(?ms)^# {re.escape(section)}\n(.*?)(?=^# |\Z)", _SYSTEM)
    assert match is not None, f"section {section!r} is not in the system prompt"
    rules = [" ".join(rule.split()) for rule in re.split(r"(?m)^- ", match[1])[1:]]
    matches = [rule for rule in rules if rule.startswith(prefix)]
    assert len(matches) == 1, (section, prefix, matches)
    return matches[0]


def test_the_subject_matter_stays_the_author_s() -> None:
    """A lesson free to teach its own way is not free to teach its own material.

    This is the half that must survive the loosening: an engine that may add a question is one
    turn away from adding a claim, and a learner cannot tell which of the two they were given.
    """
    rule = _rule("Deliver the authored lesson", "The author supplies")
    assert "The author supplies the subject matter, facts, claims and examples" in rule
    assert "Do not invent these" in rule
    # Nor quietly borrow from a lesson the learner has not reached, or has already passed.
    assert "or import material from elsewhere in the course" in rule


def test_teaching_may_be_adapted_to_the_learner() -> None:
    """The half being loosened: ask, check, re-explain, split a step.

    Each is named rather than implied. "Use your judgement" is read by a model as permission to
    do anything, and by a cautious one as permission to do nothing.
    """
    rule = _rule("Deliver the authored lesson", "The author supplies")
    assert "You may rephrase" in rule
    assert "check understanding" in rule
    assert "add a supporting question" in rule
    assert "teach a step in stages when this learner needs it" in rule


def test_what_is_added_serves_a_step_rather_than_becoming_one() -> None:
    """Otherwise the lesson grows: each added question is a step the next turn must also cover."""
    rule = _rule("Deliver the authored lesson", "The author supplies")
    assert "additions serve the current step and never become independent steps" in rule
    sequence = _rule("Deliver the authored lesson", "Interpret the script")
    assert "Never skip, replace or leave a step half-taught" in sequence


def test_a_turn_holds_what_belongs_together() -> None:
    """One step per turn was the rule; it made a lesson of one-line turns out of small steps."""
    teaching = _rule("Deliver the authored lesson", "The author supplies")
    assert "teach a step in stages" in teaching
    pacing = _rule("Deliver the authored lesson", "Answer side questions")
    assert "Group related content" in pacing


def test_order_and_pending_questions_still_bind() -> None:
    """Pacing was loosened; sequence was not.

    Running past an asked question is the failure this engine has produced most often, in three
    different disguises, so the prompt says it as well as the host enforcing it.
    """
    rule = _rule("Deliver the authored lesson", "Answer side questions")
    assert "without overtaking an earlier step" in rule
    assert "or an unanswered question" in rule
    interaction = _rule("Turns and learner input", "Whenever learner input is needed")
    assert (
        "call the actual `interact` tool, then stop and wait for its result"
        in interaction
    )


def test_the_script_may_still_loop_and_retry() -> None:
    """Loops were never forbidden, so step 3 does not have to add them -- only not lose them."""
    rule = _rule("Deliver the authored lesson", "Interpret the script")
    assert "Execute every step in order" in rule
    assert "including conditions, loops and retry limits" in rule
    assert "keep count" in rule
