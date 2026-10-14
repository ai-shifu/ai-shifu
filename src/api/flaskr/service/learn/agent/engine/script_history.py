"""Project authored comments out of recognized engine-owned initial prompts."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from .memory_context import parse_initial_memory_prompt
from .script import (
    _COLLECTED_RE,
    _strip_fences,
    collected_names,
    substitute_variables,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .script import ScriptBundle


def _render_documents(
    bundle: ScriptBundle,
    values: Mapping[str, Any],
    collected: frozenset[str],
    *,
    unavailable: bool,
) -> str:
    """Reproduce the host document layout without touching the memory section."""
    parts = [
        "<script>\n"
        + substitute_variables(
            bundle.script, values, collected=collected, unavailable=unavailable
        )
        + "\n</script>"
    ]
    if bundle.constraints:
        parts.append(
            "<constraints>\n"
            + substitute_variables(
                bundle.constraints,
                values,
                collected=collected,
                unavailable=unavailable,
            )
            + "\n</constraints>"
        )
    parts.extend(
        f'<extra name="{name}">\n{body}\n</extra>'
        for name, body in bundle.extras.items()
    )
    return "\n\n".join(parts)


def project_script_history(
    messages: list[ModelMessage],
    bundle: ScriptBundle,
    initial_variables: Mapping[str, Any] | None,
) -> list[ModelMessage]:
    """Copy only a proven initial host-document prefix for the next model request.

    Saved messages, learner JSON, substituted learner values, and later conversation remain
    evidence. Reconstruct the original host rendering from its initial snapshots, then compare
    the entire prefix before replacing it. Unknown or ambiguous history is left intact rather
    than scanning arbitrary rendered text for comment markers.
    """
    clean = bundle.without_comments()
    if clean == bundle:
        return messages
    clean_collected = collected_names(clean.script)
    # Before comment filtering, a collected marker inside an authored comment also suppressed
    # substitution. Reproduce that legacy behavior independently of today's public collector.
    legacy_collected = frozenset(_COLLECTED_RE.findall(_strip_fences(bundle.script)))
    collectors = (legacy_collected, clean_collected)
    for index, request in enumerate(messages):
        if not isinstance(request, ModelRequest):
            continue
        for part_index, part in enumerate(request.parts):
            if not isinstance(part, UserPromptPart):
                continue
            if not isinstance(part.content, str):
                return messages
            parsed = parse_initial_memory_prompt(part.content)
            if parsed is None:
                return messages
            values = {**parsed.memory, **(initial_variables or {})}
            for collected in collectors:
                for unavailable in (True, False):
                    original = _render_documents(
                        bundle, values, collected, unavailable=unavailable
                    )
                    start = parsed.script_start
                    if not part.content.startswith(original, start):
                        continue
                    suffix = part.content[start + len(original) :]
                    if suffix and not suffix.startswith("\n\n"):
                        continue
                    projected = _render_documents(
                        clean, values, clean_collected, unavailable=unavailable
                    )
                    content = part.content[:start] + projected + suffix
                    parts = list(request.parts)
                    parts[part_index] = replace(part, content=content)
                    result = list(messages)
                    result[index] = replace(request, parts=parts)
                    return result
            # Only the first learner prompt can be the engine-owned initial prompt.
            return messages
    return messages
