"""Keep static profile questions faithful to their authored answer contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.api.markdownflow import substitute_variables
from markdownflow import InteractionParser

if TYPE_CHECKING:
    from collections.abc import Mapping

    from flaskr.api.markdownflow import InteractionSpec


def check_authored_interaction(
    spec: InteractionSpec, source: str, variables: Mapping[str, object]
) -> str | None:
    """Reject changed bindings, input kinds, or ordered stored values.

    Display labels, unbound questions and text hints may be localized.
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
    question = spec.source_question or spec.variable
    if (variable is not None or not spec.question_owns_memory) and (
        question or None
    ) != variable:
        return "Use the exact question written inside the authored interaction."

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
    if spec.type != expected_type:
        return (
            f"Use the authored interaction type {expected_type!r}; keep its choice "
            "count and free-text input boundary unchanged."
        )

    expected_values = [button["value"] for button in buttons]
    actual_values = [option.stored for option in spec.options]
    if actual_values != expected_values:
        return (
            "Keep every authored option's stored value exactly as written and in its "
            "original order. Do not omit or add options; localize only display labels."
        )
    return None
