"""Adapt native MarkdownFlow events to course-specific persistence DTOs.

Question rendering and validation are shared application bindings. This module
owns only the course event projection, not engine execution or control grammar.
"""

from __future__ import annotations

from flaskr.api.markdownflow import (
    ContentDelta,
    ErrorEvent,
    Event,
    InteractionRequest,
    MemoryUpdated,
    TurnDone,
    UnrepresentableInteractionError,
    render_interaction,
    render_narrated_interaction,
    render_question,
    unrenderable_reason,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
    VariableUpdateDTO,
)

__all__ = [
    "UnrepresentableInteractionError",
    "render_interaction",
    "render_narrated_interaction",
    "render_question",
    "translate",
    "unrenderable_reason",
]


def render_question(spec: InteractionSpec) -> tuple[str, str]:
    """Render a question with the same host normalization used by validation."""
    prompt, normalized = _as_sent(spec)
    return prompt, render_interaction(normalized)


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
        prompt, controls = render_question(event.spec)
        if prompt.strip():
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
                content=controls,
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
        # Every turn ends in a boundary, a turn that stopped to ask something included. The
        # browser never sees a BREAK -- the SSE framing suppresses it -- but the element adapter
        # finalises the block on it: every element the turn streamed is written then, with its
        # audio. Without it, a turn that ended on a question was never finalised, so its text
        # survived only where an audio patch happened to write it, and its cards not at all --
        # a learner reloading the lesson got the narration back over an empty page.
        #
        # `end` means this turn ran out of content, not that the lesson is over -- the model often
        # never calls `finish`, and the host decides from the script whether anything remains. The
        # element adapter marks DONE terminal and the browser closes the stream on it, so only a
        # finished lesson may use it; BREAK is the boundary a lesson can continue past.
        return [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=(
                    GeneratedType.DONE
                    if event.reason == "finished"
                    else GeneratedType.BREAK
                ),
                content="",
            )
        ]

    if isinstance(event, ErrorEvent):
        # Nothing: 1.0 has no error event, and its DONE is read by the browser as terminal
        # *success* -- it clears the failed flag and closes the stream. Reporting a failure that
        # way would be worse than silence. The host ends the request without a terminal event, so
        # the browser keeps the failure it already recorded.
        return []

    return []
