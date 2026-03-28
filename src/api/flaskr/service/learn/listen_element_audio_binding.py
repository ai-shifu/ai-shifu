from __future__ import annotations

from typing import Any

from flaskr.service.learn.learn_dtos import ElementAudioDTO, ElementType
from flaskr.service.learn.listen_element_payloads import (
    _pick_default_audio_position,
)


def _stream_element_accepts_audio_target(element_type: ElementType) -> bool:
    return element_type == ElementType.TEXT


def _ordered_stream_audio_targets(state: Any) -> list[Any]:
    return [
        stream_state
        for stream_state in state.stream_elements.values()
        if _stream_element_accepts_audio_target(stream_state.element_type)
        and (stream_state.content_text or "").strip()
    ]


def _resolve_pending_audio_for_stream_element(
    state: Any,
    stream_state: Any,
) -> tuple[ElementAudioDTO | None, list[dict[str, Any]] | None]:
    if not _stream_element_accepts_audio_target(stream_state.element_type):
        return None, None
    default_audio_position = _pick_default_audio_position(
        state.audio_by_position,
        state.audio_segments_by_position,
    )
    if default_audio_position is None:
        return None, None
    if default_audio_position in state.audio_target_element_bid_by_position:
        return None, None
    has_pending_audio = bool(
        state.audio_by_position.get(default_audio_position)
        or state.audio_segments_by_position.get(default_audio_position)
    )
    if not has_pending_audio:
        return None, None
    state.audio_target_element_bid_by_position[default_audio_position] = (
        stream_state.element_bid
    )
    return (
        state.audio_by_position.get(default_audio_position),
        state.audio_segments_by_position.get(default_audio_position, []),
    )


def _resolve_stream_audio_for_element_bid(
    state: Any,
    element_bid: str,
) -> tuple[ElementAudioDTO | None, list[dict[str, Any]]]:
    matched_positions = [
        position
        for position, target_element_bid in (
            state.audio_target_element_bid_by_position.items()
        )
        if target_element_bid == element_bid
    ]
    if matched_positions:
        position = matched_positions[-1]
        return (
            state.audio_by_position.get(position),
            state.audio_segments_by_position.get(position, []),
        )

    if state.fallback_element_bid and state.fallback_element_bid == element_bid:
        default_audio_position = _pick_default_audio_position(
            state.audio_by_position,
            state.audio_segments_by_position,
        )
        if default_audio_position is None:
            return None, []
        return (
            state.audio_by_position.get(default_audio_position),
            state.audio_segments_by_position.get(default_audio_position, []),
        )

    if len(state.stream_elements) != 1:
        return None, []
    lone_stream_state = next(iter(state.stream_elements.values()))
    if (
        lone_stream_state.element_bid != element_bid
        or not _stream_element_accepts_audio_target(lone_stream_state.element_type)
    ):
        return None, []

    default_audio_position = _pick_default_audio_position(
        state.audio_by_position,
        state.audio_segments_by_position,
    )
    if default_audio_position is None:
        return None, []
    return (
        state.audio_by_position.get(default_audio_position),
        state.audio_segments_by_position.get(default_audio_position, []),
    )


def _resolve_audio_target_element_bid(
    state: Any,
    position: int,
) -> str | None:
    existing_target = state.audio_target_element_bid_by_position.get(position)
    if existing_target:
        return existing_target

    ordered_targets = _ordered_stream_audio_targets(state)
    if 0 <= position < len(ordered_targets):
        return ordered_targets[position].element_bid

    for stream_state in reversed(ordered_targets):
        return stream_state.element_bid

    if state.fallback_element_bid and (state.raw_content or "").strip():
        return state.fallback_element_bid

    return None
