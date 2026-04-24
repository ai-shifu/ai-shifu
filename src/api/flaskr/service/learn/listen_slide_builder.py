from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid

from flask import Flask

from flaskr.util.uuid import generate_id
from flaskr.service.learn.listen_source_span_utils import (
    normalize_source_span,
    slice_source_by_span,
)


@dataclass
class VisualSegment:
    """Lightweight internal segment produced from av_contract boundaries."""

    segment_id: str
    generated_block_bid: str
    element_index: int
    audio_position: int = 0
    visual_kind: str = ""
    segment_type: str = ""
    segment_content: str = ""
    source_span: list[int] = field(default_factory=list)
    is_placeholder: bool = False


def _segment_type_for_visual_kind(visual_kind: str, is_placeholder: bool) -> str:
    if is_placeholder:
        return "placeholder"
    if visual_kind in {"iframe", "sandbox", "html_table"}:
        return "sandbox"
    return "markdown"


def build_visual_segments_for_block(
    *,
    app: Flask | None = None,
    raw_content: str,
    generated_block_bid: str,
    av_contract: dict[str, Any] | None,
    element_index_offset: int = 0,
) -> tuple[list[VisualSegment], dict[int, str]]:
    """
    Build visual segments for one generated block from its av_contract.

    Returns:
    - segments: ordered visual segments for this block
    - audio_position_to_segment_id: mapping for speakable segment positions
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
        source_span = normalize_source_span(boundary.get("source_span"))
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
        source_span = normalize_source_span(segment.get("source_span"))
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

    segments: list[VisualSegment] = []
    audio_position_to_segment_id: dict[int, str] = {}
    segment_id_by_key: dict[str, str] = {}
    next_element_index = int(element_index_offset or 0)

    def ensure_segment(
        *,
        key: str,
        visual_kind: str,
        source_span: list[int],
        is_placeholder: bool,
        audio_position: int,
    ) -> str:
        nonlocal next_element_index
        existing = segment_id_by_key.get(key)
        if existing:
            return existing
        segment_id = generate_id(app) if app is not None else uuid.uuid4().hex
        segment_type = _segment_type_for_visual_kind(visual_kind, is_placeholder)
        segment_content = (
            ""
            if is_placeholder
            else slice_source_by_span(raw_content or "", source_span)
        )
        seg = VisualSegment(
            segment_id=segment_id,
            generated_block_bid=generated_block_bid,
            element_index=next_element_index,
            audio_position=audio_position,
            visual_kind=visual_kind or ("placeholder" if is_placeholder else ""),
            segment_type=segment_type,
            segment_content=segment_content,
            source_span=source_span,
            is_placeholder=is_placeholder,
        )
        segments.append(seg)
        segment_id_by_key[key] = segment_id
        next_element_index += 1
        return segment_id

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
            seg_key = f"boundary:{boundary_pos}"
            segment_id = ensure_segment(
                key=seg_key,
                visual_kind=str(preceding_boundary["kind"] or ""),
                source_span=list(preceding_boundary["source_span"] or []),
                is_placeholder=False,
                audio_position=position,
            )
        else:
            # Narration before the first visual (or no visual at all).
            seg_key = f"text:{position}"
            segment_id = ensure_segment(
                key=seg_key,
                visual_kind="",
                source_span=list(segment["source_span"] or []),
                is_placeholder=False,
                audio_position=position,
            )

        audio_position_to_segment_id[position] = segment_id

    return segments, audio_position_to_segment_id
