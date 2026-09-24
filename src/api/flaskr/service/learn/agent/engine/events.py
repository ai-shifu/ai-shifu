"""Events emitted by the engine for one turn. Shapes double as the wire protocol (SSE)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from .interaction import InteractionSpec


class ContentDelta(BaseModel):
    """A piece of the lesson text, as the model produces it."""

    type: Literal["content.delta"] = "content.delta"
    text: str


class Visual(BaseModel):
    """Something to show rather than speak: a slide, diagram, image or table."""

    kind: Literal["html", "svg", "mermaid", "code", "image", "table"]
    content: str
    language: str | None = None


class SegmentStart(BaseModel):
    """Listen mode: a new segment begins. `visual` is None for narration-only segments."""

    type: Literal["segment.start"] = "segment.start"
    segment_id: str
    visual: Visual | None = None


class NarrationDelta(BaseModel):
    """Listen mode: a piece of the spoken track for one segment."""

    type: Literal["narration.delta"] = "narration.delta"
    segment_id: str
    text: str


class SegmentEnd(BaseModel):
    """Listen mode: a segment is complete, with its narration assembled."""

    type: Literal["segment.end"] = "segment.end"
    segment_id: str
    narration: str


class InteractionRequest(BaseModel):
    """The lesson is waiting for the learner. The turn ends here until it is answered."""

    type: Literal["interaction.request"] = "interaction.request"
    id: str
    spec: InteractionSpec
    # The same question put again because the answer to it was not usable. Its text is already in
    # front of the learner; a host that shows the question's text should show only its controls.
    asked_before: bool = False


class ToolCall(BaseModel):
    """The model called one of the engine's tools."""

    type: Literal["tool.call"] = "tool.call"
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """What a tool returned to the model."""

    type: Literal["tool.result"] = "tool.result"
    id: str
    name: str
    content: Any = None


class MemoryUpdated(BaseModel):
    """Something about the learner was written to memory."""

    type: Literal["memory.updated"] = "memory.updated"
    key: str
    value: Any
    scope: Literal["session", "user"] = "session"
    source: Literal["tool", "interaction"] = "tool"


class TurnDone(BaseModel):
    """The turn ended, and why: waiting on an interaction, out of content, or finished."""

    type: Literal["turn.done"] = "turn.done"
    reason: Literal["interaction", "end", "finished"]
    usage: dict[str, int] = Field(default_factory=dict)
    summary: str | None = None  # set when reason == "finished"


class ErrorEvent(BaseModel):
    """The turn failed. The session stays usable; the host decides whether to retry."""

    type: Literal["error"] = "error"
    message: str
    retryable: bool = False


Event = (
    ContentDelta
    | SegmentStart
    | NarrationDelta
    | SegmentEnd
    | InteractionRequest
    | ToolCall
    | ToolResult
    | MemoryUpdated
    | TurnDone
    | ErrorEvent
)
EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)


def to_sse(event: Event) -> str:
    r"""Frame one event for SSE: `data: {json}\n\n`."""
    return (
        "data: "
        + json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        + "\n\n"
    )


def parse_event(data: str | bytes | dict[str, Any]) -> Event:
    """Rebuild an event from what came over the wire."""
    if isinstance(data, dict):
        return EventAdapter.validate_python(data)
    return EventAdapter.validate_json(data)
