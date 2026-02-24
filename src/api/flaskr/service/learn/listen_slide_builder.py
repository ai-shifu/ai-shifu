from __future__ import annotations

import uuid
from typing import Any

from flaskr.service.learn.learn_dtos import NewSlideDTO


def _normalize_source_span(raw: Any) -> list[int]:
    if not isinstance(raw, list) or len(raw) < 2:
        return []
    try:
        start = int(raw[0])
        end = int(raw[1])
    except (TypeError, ValueError):
        return []
    if start < 0 or end < 0:
        return []
    if end < start:
        return []
    return [start, end]


def _slice_segment_content(raw_content: str, source_span: list[int]) -> str:
    if not source_span:
        return ""
    start, end = source_span
    if start >= len(raw_content) or end <= start:
        return ""
    return raw_content[start : min(end, len(raw_content))]


def _segment_type_for_visual_kind(visual_kind: str, is_placeholder: bool) -> str:
    if is_placeholder:
        return "placeholder"
    if visual_kind in {"iframe", "sandbox", "html_table"}:
        return "sandbox"
    return "markdown"


def build_listen_slides_for_block(
    *,
    raw_content: str,
    generated_block_bid: str,
    av_contract: dict[str, Any] | None,
    slide_index_offset: int = 0,
) -> tuple[list[NewSlideDTO], dict[int, str]]:
    """
    Build listen-mode slides for one generated block (no persistence).

    Returns:
    - slides: ordered slide DTOs for this block
    - audio_position_to_slide_id: mapping for speakable segment positions
    """
    contract = av_contract or {}
    visual_boundaries_raw = contract.get("visual_boundaries") or []
    speakable_segments_raw = contract.get("speakable_segments") or []

    visual_boundaries: list[dict[str, Any]] = []
    for boundary in visual_boundaries_raw:
        if not isinstance(boundary, dict):
            continue
        try:
            position = int(boundary.get("position", 0))
        except (TypeError, ValueError):
            continue
        source_span = _normalize_source_span(boundary.get("source_span"))
        visual_boundaries.append(
            {
                "position": position,
                "kind": str(boundary.get("kind", "") or ""),
                "source_span": source_span,
                "end": source_span[1] if len(source_span) == 2 else -1,
            }
        )
    visual_boundaries.sort(key=lambda item: item["position"])

    speakable_segments: list[dict[str, Any]] = []
    for segment in speakable_segments_raw:
        if not isinstance(segment, dict):
            continue
        try:
            position = int(segment.get("position", 0))
        except (TypeError, ValueError):
            continue
        source_span = _normalize_source_span(segment.get("source_span"))
        speakable_segments.append(
            {
                "position": position,
                "source_span": source_span,
                "source_start": source_span[0] if len(source_span) == 2 else -1,
            }
        )
    speakable_segments.sort(key=lambda item: item["position"])

    if not speakable_segments:
        return [], {}

    slides: list[NewSlideDTO] = []
    audio_position_to_slide_id: dict[int, str] = {}
    slide_id_by_key: dict[str, str] = {}
    next_slide_index = int(slide_index_offset or 0)

    def ensure_slide(
        *,
        key: str,
        visual_kind: str,
        source_span: list[int],
        is_placeholder: bool,
        audio_position: int,
    ) -> str:
        nonlocal next_slide_index
        existing = slide_id_by_key.get(key)
        if existing:
            return existing
        slide_id = uuid.uuid4().hex
        segment_type = _segment_type_for_visual_kind(visual_kind, is_placeholder)
        segment_content = (
            ""
            if is_placeholder
            else _slice_segment_content(raw_content or "", source_span)
        )
        slide = NewSlideDTO(
            slide_id=slide_id,
            generated_block_bid=generated_block_bid,
            slide_index=next_slide_index,
            audio_position=audio_position,
            visual_kind=visual_kind or ("placeholder" if is_placeholder else ""),
            segment_type=segment_type,
            segment_content=segment_content,
            source_span=source_span,
            is_placeholder=is_placeholder,
        )
        slides.append(slide)
        slide_id_by_key[key] = slide_id
        next_slide_index += 1
        return slide_id

    for segment in speakable_segments:
        position = int(segment["position"])
        source_start = int(segment["source_start"])
        preceding_boundary = (
            max(
                (
                    boundary
                    for boundary in visual_boundaries
                    if boundary["end"] >= 0 and boundary["end"] <= source_start
                ),
                key=lambda item: item["end"],
                default=None,
            )
            if source_start >= 0
            else None
        )

        if preceding_boundary is not None:
            boundary_pos = int(preceding_boundary["position"])
            slide_key = f"boundary:{boundary_pos}"
            slide_id = ensure_slide(
                key=slide_key,
                visual_kind=str(preceding_boundary["kind"] or ""),
                source_span=list(preceding_boundary["source_span"] or []),
                is_placeholder=False,
                audio_position=position,
            )
        else:
            # Narration before the first visual (or no visual at all).
            # Create a unique text slide for each audio position to ensure proper navigation.
            slide_key = f"text:{position}"
            slide_id = ensure_slide(
                key=slide_key,
                visual_kind="",
                source_span=list(segment["source_span"] or []),
                is_placeholder=False,
                audio_position=position,
            )

        audio_position_to_slide_id[position] = slide_id

    return slides, audio_position_to_slide_id
