"""Keep static profile questions faithful to their authored answer contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.api.markdownflow import (
    render_question,
    substitute_variables,
    unrenderable_reason,
)
from markdownflow import InteractionParser, find_unescaped

if TYPE_CHECKING:
    from collections.abc import Mapping

    from flaskr.api.markdownflow import InteractionSpec


def check_authored_interaction(
    spec: InteractionSpec, source: str, variables: Mapping[str, object]
) -> str | None:
    """Reject changed bindings, input kinds, or ordered stored values.

    Display labels, prompts and text hints may be localized. An unassigned
    single button may use the engine's canonical confirm value, unless the
    author explicitly supplied a machine value with ``Display//value``.
    Hosts may match this contract against any authored question in a full script.
    """
    rendered_source = substitute_variables(source, variables)
    parser = InteractionParser()
    authored = parser.parse(rendered_source)
    if authored.get("type") is None:
        return (
            "The authored interaction could not be parsed. Keep its original controls."
        )

    variable = authored.get("variable") or None
    if (spec.variable or None) != variable:
        return "Keep the authored interaction's variable binding unchanged."

    buttons = authored.get("buttons") or []
    has_text = "question" in authored
    multi = bool(authored.get("is_multi_select"))
    expected_type = (
        ("multi_or_text" if multi else "single_or_text")
        if buttons and has_text
        else ("multi" if multi else "single")
        if buttons
        else "text"
    )
    is_confirm = (
        spec.type == "confirm"
        and not variable
        and expected_type == "single"
        and len(buttons) == 1
    )
    if spec.type != expected_type and not is_confirm:
        return (
            f"Use the authored interaction type {expected_type!r}; keep its choice "
            "count and free-text input boundary unchanged."
        )

    expected_values = [button["value"] for button in buttons]
    actual_values = [option.stored for option in spec.options]
    if is_confirm:
        # A short confirm prompt becomes the button label and canonical value
        # in the host renderer. Check the controls the learner actually submits.
        if reason := unrenderable_reason(spec):
            return reason
        _prompt, controls = render_question(spec)
        actual_values = [
            button["value"] for button in parser.parse(controls).get("buttons", [])
        ]
        if find_unescaped(rendered_source, "//") < 0 and actual_values == ["continue"]:
            return None
    if actual_values != expected_values:
        return (
            "Keep every authored option's stored value exactly as written and in its "
            "original order. Do not omit or add options; localize only display labels."
        )
    return None
