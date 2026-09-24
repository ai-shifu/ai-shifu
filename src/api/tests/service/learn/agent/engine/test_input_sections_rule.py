"""Cover the rule that the first message's sections are input, not a format to write in.

A model shown the learner's memory as `<memory>` followed by JSON wrote its own note in that
shape instead of calling `remember`, and the learner read it. The host strips such a block, but
the prompt is what keeps the model from writing one; these keep that sentence from being lost.
"""

from __future__ import annotations

from pathlib import Path

from tests.service.learn.agent.engine.test_script_authority import _rule

_PROMPTS = (
    Path(__file__).resolve().parents[5] / "flaskr/service/learn/agent/engine/prompts"
)


def test_the_first_message_s_sections_are_not_written_back() -> None:
    rule = _rule(12)
    assert (
        "tagged sections of the first message, such as `<memory>` and `<script>`"
        in rule
    )
    assert "not a format to write in" in rule
    assert "a tool call, or a tool's arguments" in rule


def test_remember_is_the_only_way_to_store_and_answers_are_stored_already() -> None:
    """The leaked note recorded an answer `interact` had already stored under its variable."""
    rule = _rule(4)
    assert "Calling `remember` is the only way to store anything" in rule
    assert "already stored under it; do not store it again" in rule


def test_the_first_message_uses_the_section_names_the_rule_gives() -> None:
    """The rule names the sections; if the engine renamed one, the rule would name a stranger."""
    script_source = (_PROMPTS.parent / "script.py").read_text()
    for tag in ("<memory>", "<script>"):
        assert tag in script_source
