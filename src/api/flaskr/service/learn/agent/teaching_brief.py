"""Refresh course instructions without rewriting a saved lesson or learner input."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from markdownflow.engine.memory_context import parse_initial_memory_prompt
from markdownflow.engine.script import collected_names, substitute_variables
from pydantic_ai.messages import ModelRequest, UserPromptPart

if TYPE_CHECKING:
    from markdownflow.engine import ScriptBundle, Session


def refresh_teaching_brief(session: Session, brief: str) -> None:
    """Update only the initial engine constraints and their bundle snapshot.

    Older hosts updated the bundle without updating the model's initial message,
    so compare the message on every resume, even when the bundle already matches.
    """
    previous = session.script
    session.script = replace(previous, constraints=brief or None)
    for index, message in enumerate(session.messages):
        if not isinstance(message, ModelRequest):
            continue
        for part_index, part in enumerate(message.parts):
            if not isinstance(part, UserPromptPart):
                continue
            if not isinstance(part.content, str):
                return
            refreshed = _refresh_prompt(part.content, session, previous, brief)
            if refreshed != part.content:
                parts = list(message.parts)
                parts[part_index] = replace(part, content=refreshed)
                session.messages[index] = replace(message, parts=parts)
            return


def _refresh_prompt(
    content: str, session: Session, previous: ScriptBundle, brief: str
) -> str:
    """Recognize the saved script exactly before touching the following constraints."""
    parsed = parse_initial_memory_prompt(content)
    if parsed is None:
        return content
    snapshots = (
        session.initial_variables or {},
        parsed.memory,
        {**parsed.memory, **(session.initial_variables or {})},
    )
    collected = collected_names(previous.script)
    scripts = [previous.script]
    scripts.extend(
        substitute_variables(
            previous.script, values, collected=collected, unavailable=True
        )
        for values in snapshots
    )
    script_end = max(
        (
            parsed.script_start + len(document)
            for script in scripts
            if content.startswith(
                document := f"<script>\n{script}\n</script>", parsed.script_start
            )
        ),
        default=None,
    )
    if script_end is None:
        return content
    learner_suffixes = [
        "\n\n" + text
        for text in session.request_inputs
        if text and content.endswith("\n\n" + text)
    ]
    learner_start = len(content) - max(map(len, learner_suffixes), default=0)
    end = script_end
    opening = "\n\n<constraints>\n"
    closing = "\n</constraints>"
    if (
        previous.constraints
        and script_end < learner_start
        and content.startswith(opening, script_end)
    ):
        start = script_end + len(opening)
        current = [brief]
        current.extend(
            substitute_variables(brief, values, collected=collected, unavailable=True)
            for values in snapshots
        )
        if brief and any(
            content.startswith(candidate + closing, start)
            and start + len(candidate) + len(closing) <= learner_start
            for candidate in current
        ):
            # An unchanged course brief may still have its historical expanded
            # representation. Preserve it just like the saved script and extras.
            return content
        candidates = [previous.constraints or ""]
        candidates.extend(
            substitute_variables(
                previous.constraints or "",
                values,
                collected=collected,
                unavailable=True,
            )
            for values in snapshots
        )
        end = next(
            (
                start + len(candidate) + len(closing)
                for candidate in candidates
                if content.startswith(candidate + closing, start)
                and start + len(candidate) + len(closing) <= learner_start
            ),
            None,
        )
        if end is None:
            # A bundle already refreshed by the old host no longer identifies the
            # historical constraint text. Only known host extras can establish
            # its end; a lone closing tag could belong to an initial learner input.
            if not previous.extras:
                return content
            extras = "\n\n".join(
                f'<extra name="{name}">\n{body}\n</extra>'
                for name, body in previous.extras.items()
            )
            boundaries = []
            at = content.find(closing, start)
            while 0 <= at < learner_start:
                boundary = at + len(closing)
                if boundary <= learner_start and content.startswith(
                    "\n\n" + extras, boundary
                ):
                    boundaries.append(boundary)
                at = content.find(closing, boundary)
            if len(boundaries) != 1:
                return content
            end = boundaries[0]
    replacement = opening + brief + closing if brief else ""
    return content[:script_end] + replacement + content[end:]
