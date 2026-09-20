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
    assert "do not call `interact`" in rule
    assert "soft pause" not in rule
