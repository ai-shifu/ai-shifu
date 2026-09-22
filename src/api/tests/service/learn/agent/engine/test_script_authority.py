"""Cover where the script's authority ends and the model's judgement begins.

Step 3 of the rollout loosens "follow the script exactly" into "the script is the task". The
loosening has a line in it that must not move: a lesson may be taught differently for different
learners, but it teaches what the author wrote and nothing else. These assert both halves, so
neither can be dropped without the suite noticing.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS = (
    Path(__file__).resolve().parents[5] / "flaskr/service/learn/agent/engine/prompts"
)
_SYSTEM = (_PROMPTS / "system.md").read_text()


def _rule(number: int) -> str:
    """Return the numbered rule from the system prompt, so a test reads only its own rule."""
    lines = [line for line in _SYSTEM.splitlines() if line.startswith(f"{number}. ")]
    assert len(lines) == 1, f"rule {number} is not a single line: {lines}"
    return lines[0]


def test_the_subject_matter_stays_the_author_s() -> None:
    """A lesson free to teach its own way is not free to teach its own material.

    This is the half that must survive the loosening: an engine that may add a question is one
    turn away from adding a claim, and a learner cannot tell which of the two they were given.
    """
    rule = _rule(1)
    assert "What it teaches is the author's" in rule
    assert "do not invent facts, claims, examples, or subject matter" in rule
    # Nor quietly borrow from a lesson the learner has not reached, or has already passed.
    assert "do not bring in material from elsewhere in the course" in rule


def test_teaching_may_be_adapted_to_the_learner() -> None:
    """The half being loosened: ask, check, re-explain, split a step.

    Each is named rather than implied. "Use your judgement" is read by a model as permission to
    do anything, and by a cautious one as permission to do nothing.
    """
    rule = _rule(1)
    assert "How you teach it is yours" in rule
    assert "ask something the script did not list" in rule
    assert "put a point another way" in rule
    assert "work through a step in stages" in rule


def test_what_is_added_serves_a_step_rather_than_becoming_one() -> None:
    """Otherwise the lesson grows: each added question is a step the next turn must also cover."""
    rule = _rule(1)
    assert "never becomes a step of its own" in rule
    assert "it never replaces one" in rule


def test_a_turn_holds_what_belongs_together() -> None:
    """One step per turn was the rule; it made a lesson of one-line turns out of small steps."""
    rule = _rule(8)
    assert "a step may take several turns" in rule
    assert "two may share one turn" in rule


def test_order_and_pending_questions_still_bind() -> None:
    """Pacing was loosened; sequence was not.

    Running past an asked question is the failure this engine has produced most often, in three
    different disguises, so the prompt says it as well as the host enforcing it.
    """
    rule = _rule(8)
    assert "Never deliver a later step before an earlier one" in rule
    assert "never run past a question you have asked" in rule


def test_the_script_may_still_loop_and_retry() -> None:
    """Loops were never forbidden, so step 3 does not have to add them -- only not lose them."""
    rule = _rule(5)
    assert "conditions, loops, and retries" in rule
    assert "honour any limits the author sets" in rule
