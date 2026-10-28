"""Preserved label characters determine the public reference length boundary."""

import pytest
from markdown_it.common.utils import normalizeReference
from markdownflow.engine import ScriptBundle, collected_names, render_first_prompt
from markdownflow.engine.tools import script_options


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize("escape", [r"\:", r"\[", r"\]", "\\\\", r"\q"])
@pytest.mark.parametrize("oversized", [False, True])
def test_casefold_equivalence_does_not_bypass_the_public_label_bound(
    oversized: bool, escape: str, spelling: str, newline: str
) -> None:
    """A valid 999-character definition cannot validate a 1000-character use."""
    label = escape * 499 + ("SS" if oversized else "ß")
    definition = escape * 499 + "ß"
    assert len(label) == (1000 if oversized else 999)
    assert len(definition) == 999
    assert normalizeReference(label) == normalizeReference(definition)
    source = (
        f"![?[{spelling} A | B]][{label}]\n\n[{definition}]: /x\n\n"
        "Read {{goal}}.\n\n?[{{visible}} C | D]"
    ).replace("\n", newline)
    expected_names = {"visible"} | (
        {"goal"} if oversized or spelling.startswith("%") else set()
    )
    assert collected_names(source) == frozenset(expected_names)
    assert script_options(source) == (
        {"A": "A", "B": "B", "C": "C", "D": "D"} if oversized else {"C": "C", "D": "D"}
    )
    prompt = render_first_prompt(ScriptBundle(script=source), {"goal": "current"})
    if oversized:
        assert "current" not in prompt
    elif not spelling.startswith("%"):
        assert '"current"' in prompt


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize("oversized", [False, True])
def test_escaped_label_bounds_count_a_physical_crlf_as_one_character(
    oversized: bool, spelling: str, newline: str
) -> None:
    """Physical line-ending normalization cannot change the label character budget."""
    prefix = r"\:" * 498
    label = prefix + newline + ("SSS" if oversized else "SS")
    definition = prefix + " " + ("Sß" if oversized else "SS")
    assert len(label.replace("\r\n", "\n")) == (1000 if oversized else 999)
    assert len(definition) == 999
    assert normalizeReference(label) == normalizeReference(definition)
    source = f"![?[{spelling} A | B]][{label}]\n\n[{definition}]: /x"
    expected_names = (
        frozenset({"goal"}) if oversized or spelling.startswith("%") else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == ({"A": "A", "B": "B"} if oversized else {})
