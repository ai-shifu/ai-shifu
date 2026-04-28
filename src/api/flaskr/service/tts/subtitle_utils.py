from __future__ import annotations

from typing import Any


def normalize_subtitle_cues(
    subtitle_cues: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw_item in list(subtitle_cues or []):
        item: dict[str, Any] | None = None
        if isinstance(raw_item, dict):
            item = raw_item
        elif hasattr(raw_item, "model_dump"):
            dumped_item = raw_item.model_dump()
            if isinstance(dumped_item, dict):
                item = dumped_item
        elif hasattr(raw_item, "__dict__"):
            item = {
                "text": getattr(raw_item, "text", ""),
                "start_ms": getattr(raw_item, "start_ms", 0),
                "end_ms": getattr(raw_item, "end_ms", 0),
                "segment_index": getattr(raw_item, "segment_index", 0),
                "position": getattr(raw_item, "position", 0),
            }
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "") or "").strip()
        if not text:
            continue
        start_ms = max(int(item.get("start_ms", 0) or 0), 0)
        end_ms = max(int(item.get("end_ms", start_ms) or start_ms), start_ms)
        segment_index = max(int(item.get("segment_index", 0) or 0), 0)
        position = max(int(item.get("position", 0) or 0), 0)
        normalized.append(
            {
                "text": text,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "segment_index": segment_index,
                "position": position,
            }
        )
    normalized.sort(
        key=lambda cue: (
            int(cue.get("position", 0) or 0),
            int(cue.get("segment_index", 0) or 0),
            int(cue.get("start_ms", 0) or 0),
            int(cue.get("end_ms", 0) or 0),
        )
    )
    return normalized


def append_subtitle_cue(
    subtitle_cues: list[dict[str, Any]],
    *,
    text: str,
    duration_ms: int,
    segment_index: int,
    position: int = 0,
) -> list[dict[str, Any]]:
    cue_text = str(text or "").strip()
    if not cue_text:
        return subtitle_cues

    start_ms = int(subtitle_cues[-1].get("end_ms", 0) or 0) if subtitle_cues else 0
    safe_duration_ms = max(int(duration_ms or 0), 0)
    subtitle_cues.append(
        {
            "text": cue_text,
            "start_ms": start_ms,
            "end_ms": start_ms + safe_duration_ms,
            "segment_index": max(int(segment_index or 0), 0),
            "position": max(int(position or 0), 0),
        }
    )
    return subtitle_cues


def select_subtitle_cues_for_segments(
    subtitle_cues: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    segment_indices: tuple[int, ...] | list[int],
    *,
    duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Return cues for uploaded audio segments, rebased to the selected audio."""

    selected_indices = {int(index or 0) for index in segment_indices}
    selected_cues = [
        cue
        for cue in normalize_subtitle_cues(subtitle_cues)
        if int(cue.get("segment_index", 0) or 0) in selected_indices
    ]
    if not selected_cues:
        return []

    base_start_ms = min(int(cue.get("start_ms", 0) or 0) for cue in selected_cues)
    max_duration_ms = int(duration_ms) if duration_ms is not None else None
    rebased_cues: list[dict[str, Any]] = []
    for cue in selected_cues:
        start_ms = max(int(cue.get("start_ms", 0) or 0) - base_start_ms, 0)
        end_ms = max(
            int(cue.get("end_ms", start_ms) or start_ms) - base_start_ms, start_ms
        )
        if max_duration_ms is not None:
            if start_ms >= max_duration_ms:
                continue
            end_ms = min(end_ms, max_duration_ms)
        rebased_cues.append(
            {
                **cue,
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
        )
    return normalize_subtitle_cues(rebased_cues)
