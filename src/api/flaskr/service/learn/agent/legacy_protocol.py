"""Translate engine events into the events the 1.0 lesson stream already speaks.

The 1.0 run is two layers: it produces `RunMarkdownFlowDTO` events, and everything downstream --
persisting elements, binding TTS audio, assembling listen-mode slides, the SSE frames the browser
reads -- consumes those. Translating into that inner protocol rather than into the outer element
payload is what lets a 2.0 lesson reach the existing frontend without changing any of it.

Interactions translate back into MarkdownFlow's own `?[...]` syntax, because that is what 1.0 puts
on the wire and what the frontend parses. The engine took that syntax apart into an
`InteractionSpec` to show the model a typed tool; this puts it back together.

Two kinds of event deliberately translate to nothing:

* listen mode (`segment.*`, `narration.*`) needs slide and audio mapping of its own, and belongs
  with the rest of listen mode in its own change;
* tool calls and their results are how the engine talks to the model, not something a learner is
  meant to see.

Nothing calls this yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.learn.agent.engine.events import (
    ContentDelta,
    ErrorEvent,
    InteractionRequest,
    MemoryUpdated,
    TurnDone,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
    VariableUpdateDTO,
)

if TYPE_CHECKING:
    from flaskr.service.learn.agent.engine.events import Event
    from flaskr.service.learn.agent.engine.interaction import InteractionSpec, Option

# MarkdownFlow separates choices with a single bar, and multiple-choice ones with a double bar.
_SINGLE_CHOICE_SEPARATOR = " | "
_MULTI_CHOICE_SEPARATOR = " || "
# A trailing `...placeholder` inside the brackets means free text is accepted as well.
_FREE_TEXT_MARKER = "..."
# `Display//value` shows one thing and stores another.
_DISPLAY_VALUE_SEPARATOR = "//"

_MULTI_CHOICE_TYPES = frozenset({"multi", "multi_or_text"})
_FREE_TEXT_TYPES = frozenset({"text", "single_or_text", "multi_or_text"})


def _render_option(option: Option) -> str:
    """Render one choice, keeping a stored value distinct from the text the learner reads."""
    display = option.display.strip()
    value = (option.value or "").strip()
    if value and value != display:
        return f"{display}{_DISPLAY_VALUE_SEPARATOR}{value}"
    return display


def render_interaction(spec: InteractionSpec) -> str:
    """Rebuild the MarkdownFlow interaction the frontend expects from the engine's typed spec.

    The variable prefix is emitted only when the script named one to store the answer under; a
    confirm carries none by construction, since pressing continue is not an answer.
    """
    separator = (
        _MULTI_CHOICE_SEPARATOR
        if spec.type in _MULTI_CHOICE_TYPES
        else _SINGLE_CHOICE_SEPARATOR
    )
    parts = [_render_option(option) for option in spec.options]
    if spec.type in _FREE_TEXT_TYPES:
        parts.append(f"{_FREE_TEXT_MARKER}{(spec.placeholder or '').strip()}")

    variable = (spec.variable or "").strip()
    prefix = f"%{{{{{variable}}}}} " if variable else ""
    return f"?[{prefix}{separator.join(parts)}]"


def translate(
    event: Event,
    *,
    outline_bid: str,
    generated_block_bid: str,
) -> list[RunMarkdownFlowDTO]:
    """Translate one engine event into the 1.0 events it corresponds to.

    Returns a list because the correspondence is not one to one: an interaction arrives as a
    question plus its controls and leaves as the text event the learner reads followed by the
    interaction event the frontend renders. Events that 1.0 has no place for return nothing.
    """
    if isinstance(event, ContentDelta):
        if not event.text:
            return []
        return [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content=event.text,
            )
        ]

    if isinstance(event, InteractionRequest):
        events = []
        prompt = event.spec.prompt.strip()
        if prompt:
            events.append(
                RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.CONTENT,
                    content=prompt,
                )
            )
        events.append(
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.INTERACTION,
                content=render_interaction(event.spec),
            )
        )
        return events

    if isinstance(event, MemoryUpdated):
        return [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.VARIABLE_UPDATE,
                content=VariableUpdateDTO(
                    variable_name=event.key,
                    variable_value="" if event.value is None else str(event.value),
                ),
            )
        ]

    if isinstance(event, TurnDone):
        # A turn that stopped to ask something is not the end of the lesson: the interaction event
        # already told the frontend to wait, and announcing "done" here would let it move on.
        if event.reason == "interaction":
            return []
        return [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.DONE,
                content="",
            )
        ]

    if isinstance(event, ErrorEvent):
        # 1.0 has no error event of its own; a failed run ends the stream. Closing the turn keeps
        # the frontend from waiting forever, and the host logs and decides whether to retry.
        return [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.DONE,
                content="",
            )
        ]

    return []
