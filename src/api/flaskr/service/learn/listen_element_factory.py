from __future__ import annotations

from typing import Any

from flask import Flask

from flaskr.service.learn.learn_dtos import (
    ElementAudioDTO,
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    ElementVisualDTO,
)
from flaskr.service.learn.listen_element_payloads import (
    _normalize_audio_segments_for_element,
)
from flaskr.service.learn.listen_element_types import (
    _change_type_for_element,
    _default_is_marker,
    _default_is_renderable,
    _default_is_speakable,
    _element_type_code,
    _element_type_for_visual_kind,
    _new_element_bid,
)
from flaskr.service.learn.listen_slide_builder import VisualSegment
from flaskr.service.learn.listen_source_span_utils import (
    normalize_source_span,
    slice_source_by_span,
)


def _visuals_from_segment(
    segment: VisualSegment, raw_content: str
) -> list[ElementVisualDTO]:
    source_span = normalize_source_span(segment.source_span)
    visual_kind = segment.visual_kind or ""
    if not visual_kind:
        return []
    content = slice_source_by_span(raw_content, source_span)
    if not content:
        return []
    return [ElementVisualDTO(visual_type=visual_kind, content=content)]


def _element_payload_from_segment(
    segment: VisualSegment,
    raw_content: str,
    audio: ElementAudioDTO | None = None,
) -> ElementPayloadDTO:
    return ElementPayloadDTO(
        audio=audio,
        previous_visuals=_visuals_from_segment(segment, raw_content),
    )


def _text_for_speakable_segment(raw_content: str, segment: dict[str, Any]) -> str:
    source_span = normalize_source_span(segment.get("source_span"))
    text = slice_source_by_span(raw_content, source_span).strip()
    if text:
        return text
    return str(segment.get("text", "") or "").strip()


def _build_visual_element_from_segment(
    *,
    segment: VisualSegment,
    raw_content: str,
    role: str,
) -> ElementDTO:
    element_type = _element_type_for_visual_kind(segment.visual_kind or "")
    return ElementDTO(
        event_type="element",
        element_bid=segment.segment_id,
        generated_block_bid=segment.generated_block_bid,
        element_index=segment.element_index,
        role=role,
        element_type=element_type,
        element_type_code=_element_type_code(element_type),
        change_type=_change_type_for_element(element_type),
        is_renderable=_default_is_renderable(element_type),
        is_marker=_default_is_marker(element_type),
        is_navigable=1,
        is_final=True,
        content_text="",
        payload=_element_payload_from_segment(segment, raw_content),
    )


def _build_text_element(
    *,
    app: Flask,
    generated_block_bid: str,
    role: str,
    element_index: int,
    content_text: str,
    audio: ElementAudioDTO | None = None,
    audio_segments: list[dict[str, Any]] | None = None,
) -> ElementDTO:
    audio_segments = _normalize_audio_segments_for_element(audio_segments)
    return ElementDTO(
        event_type="element",
        element_bid=_new_element_bid(app),
        generated_block_bid=generated_block_bid,
        element_index=element_index,
        role=role,
        element_type=ElementType.TEXT,
        element_type_code=_element_type_code(ElementType.TEXT),
        change_type=ElementChangeType.RENDER,
        is_renderable=False,
        is_navigable=1,
        is_final=True,
        is_speakable=_default_is_speakable(ElementType.TEXT, content_text),
        audio_url=audio.audio_url if audio is not None else "",
        audio_segments=audio_segments,
        content_text=content_text,
        payload=ElementPayloadDTO(
            audio=audio,
            previous_visuals=[],
        ),
    )


def _build_final_elements_for_av_contract(
    *,
    app: Flask,
    generated_block_bid: str,
    role: str,
    raw_content: str,
    av_contract: dict[str, Any] | None,
    visual_segments: list[VisualSegment],
    audio_by_position: dict[int, ElementAudioDTO],
    audio_segments_by_position: dict[int, list[dict[str, Any]]],
    position_to_segment_id: dict[int, str] | None = None,
    element_index_offset: int = 0,
) -> list[ElementDTO]:
    visual_by_id = {segment.segment_id: segment for segment in visual_segments}
    speakable_segments_raw = (
        (av_contract or {}).get("speakable_segments") or []
        if isinstance(av_contract, dict)
        else []
    )
    speakable_segments: list[dict[str, Any]] = []
    for item in speakable_segments_raw:
        if not isinstance(item, dict):
            continue
        try:
            position = int(item.get("position", 0))
        except (TypeError, ValueError):
            continue
        speakable_segments.append({"position": position, **item})
    speakable_segments.sort(key=lambda item: int(item["position"]))

    next_element_index = int(element_index_offset or 0)
    position_to_segment_id = position_to_segment_id or {}
    emitted_visual_ids: set[str] = set()
    built: list[ElementDTO] = []

    if speakable_segments:
        for item in speakable_segments:
            position = int(item["position"])
            segment_id = position_to_segment_id.get(position, "")
            visual_segment = visual_by_id.get(segment_id)
            if (
                visual_segment is not None
                and (visual_segment.visual_kind or "").strip()
            ):
                if visual_segment.segment_id not in emitted_visual_ids:
                    visual_segment.element_index = next_element_index
                    built.append(
                        _build_visual_element_from_segment(
                            segment=visual_segment,
                            raw_content=raw_content,
                            role=role,
                        )
                    )
                    emitted_visual_ids.add(visual_segment.segment_id)
                    next_element_index += 1

            text = _text_for_speakable_segment(raw_content, item)
            if not text:
                continue
            built.append(
                _build_text_element(
                    app=app,
                    generated_block_bid=generated_block_bid,
                    role=role,
                    element_index=next_element_index,
                    content_text=text,
                    audio=audio_by_position.get(position),
                    audio_segments=audio_segments_by_position.get(position, []),
                )
            )
            next_element_index += 1

        for segment in visual_segments:
            if segment.segment_id in emitted_visual_ids:
                continue
            if not (segment.visual_kind or "").strip():
                continue
            segment.element_index = next_element_index
            built.append(
                _build_visual_element_from_segment(
                    segment=segment,
                    raw_content=raw_content,
                    role=role,
                )
            )
            next_element_index += 1
        return built

    for segment in visual_segments:
        if (segment.visual_kind or "").strip():
            segment.element_index = next_element_index
            built.append(
                _build_visual_element_from_segment(
                    segment=segment,
                    raw_content=raw_content,
                    role=role,
                )
            )
            next_element_index += 1
            continue
        text = slice_source_by_span(raw_content, segment.source_span).strip()
        if not text:
            text = (segment.segment_content or "").strip()
        if not text:
            continue
        built.append(
            _build_text_element(
                app=app,
                generated_block_bid=generated_block_bid,
                role=role,
                element_index=next_element_index,
                content_text=text,
                audio=audio_by_position.get(segment.audio_position),
                audio_segments=audio_segments_by_position.get(
                    segment.audio_position, []
                ),
            )
        )
        next_element_index += 1
    return built


def _interaction_element_from_record(
    app: Flask,
    generated_block_bid: str,
    content: str,
    *,
    user_input: str = "",
    role: str,
    element_index: int,
) -> ElementDTO:
    return ElementDTO(
        event_type="element",
        element_bid=_new_element_bid(app),
        generated_block_bid=generated_block_bid,
        element_index=element_index,
        role=role,
        element_type=ElementType.INTERACTION,
        element_type_code=_element_type_code(ElementType.INTERACTION),
        change_type=ElementChangeType.RENDER,
        is_renderable=False,
        is_marker=True,
        is_navigable=0,
        is_final=True,
        content_text=content or "",
        payload=ElementPayloadDTO(
            audio=None,
            previous_visuals=[],
            user_input=user_input or None,
        ),
    )
