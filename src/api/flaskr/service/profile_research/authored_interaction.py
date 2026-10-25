"""Keep profile controls faithful to the native authored question contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.api.markdownflow import render_question, unrenderable_reason
from markdownflow.engine.tools import (
    _find_unescaped,
    _script_questions,
    _unescape,
)

if TYPE_CHECKING:
    from flaskr.api.markdownflow import InteractionSpec
    from markdownflow.engine.tools import _Question


def authored_option_values(question: _Question) -> list[tuple[str, str]]:
    """Read exact labels and stored values using the native control escapes."""
    values = []
    for choice in question.choices:
        if not choice.strip():
            continue
        separator = _find_unescaped(choice, "//")
        display = _unescape((choice[:separator] if separator >= 0 else choice).strip())
        value = (
            _unescape(choice[separator + 2 :].strip()) if separator >= 0 else display
        )
        values.append((display, value))
    return values


def check_authored_interaction(
    spec: InteractionSpec, authored: _Question
) -> str | None:
    """Reject changed question keys, input kinds or ordered stored values."""
    if (spec.question or None) != authored.question:
        return "Keep the authored question text unchanged; it is the memory key."
    buttons = authored_option_values(authored)
    expected_type = (
        ("multi_or_text" if authored.multi else "single_or_text")
        if buttons and authored.text
        else ("multi" if authored.multi else "single")
        if buttons
        else "text"
    )
    is_confirm = (
        spec.type == "confirm"
        and not authored.question
        and expected_type == "single"
        and len(buttons) == 1
    )
    if spec.type != expected_type and not is_confirm:
        return f"Use the authored interaction type {expected_type!r}; keep its choices and input boundary unchanged."
    actual_values = [option.stored for option in spec.options]
    if is_confirm:
        if reason := unrenderable_reason(spec):
            return reason
        # A short confirm prompt becomes the rendered button label and forces
        # its stored value to ``continue``. Compare the controls actually sent.
        _prompt, controls = render_question(spec)
        rendered = _script_questions(controls)
        if len(rendered) != 1:
            return "Keep the authored confirmation controls unchanged."
        actual_values = [
            value for _display, value in authored_option_values(rendered[0])
        ]
        if _find_unescaped(authored.choices[0], "//") < 0 and actual_values == [
            "continue"
        ]:
            return None
    if actual_values != [value for _display, value in buttons]:
        return (
            "Keep every authored option's stored value exactly as written and in its "
            "original order. Do not omit or add options; localize only display labels."
        )
    return None
