"""Public event construction and compact request replay."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

REPLAY_DELTA_MARKER = "_profile_replay_delta"


def _profile_research_event(
    event_type: str,
    content: object,
    *,
    generated_block_bid: str | None = None,
    run_session_bid: str | None = None,
    is_terminal: bool | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": event_type,
        "event_type": event_type,
        "content": content,
    }
    if generated_block_bid is not None:
        event["generated_block_bid"] = generated_block_bid
    if run_session_bid is not None:
        event["run_session_bid"] = run_session_bid
    if is_terminal is not None:
        event["is_terminal"] = is_terminal
    return event


def _replay_stream_key(event: Mapping[str, Any]) -> tuple[str, str, str] | None:
    content = event.get("content")
    event_type = str(event.get("event_type") or "")
    if (
        not isinstance(content, str)
        or event.get("is_terminal")
        or event_type not in {"content", "interaction"}
    ):
        return None
    return (
        event_type,
        str(event.get("generated_block_bid") or ""),
        str(event.get("run_session_bid") or ""),
    )


def _compact_replay_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Store cumulative stream events as deltas without changing replay output."""
    previous_content: dict[tuple[str, str, str], str] = {}
    compacted: list[dict[str, Any]] = []
    for event in events:
        stored_event = dict(event)
        stream_key = _replay_stream_key(stored_event)
        if stream_key is not None:
            content = str(stored_event["content"])
            previous = previous_content.get(stream_key, "")
            if content.startswith(previous):
                stored_event["content"] = content[len(previous) :]
                stored_event[REPLAY_DELTA_MARKER] = True
            previous_content[stream_key] = content
        compacted.append(stored_event)
    return compacted


def _expand_replay_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cumulative_content: dict[tuple[str, str, str], str] = {}
    expanded: list[dict[str, Any]] = []
    for event in events:
        replay_event = dict(event)
        is_delta = bool(replay_event.pop(REPLAY_DELTA_MARKER, False))
        stream_key = _replay_stream_key(replay_event)
        if stream_key is not None:
            content = str(replay_event["content"])
            if is_delta:
                content = cumulative_content.get(stream_key, "") + content
                replay_event["content"] = content
            cumulative_content[stream_key] = content
        expanded.append(replay_event)
    return expanded
