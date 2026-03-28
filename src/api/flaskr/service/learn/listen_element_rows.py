from __future__ import annotations

import json

from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    ElementVisualDTO,
    GeneratedType,
    LearnStatus,
    OutlineItemUpdateDTO,
    RunElementSSEMessageDTO,
    VariableUpdateDTO,
)
from flaskr.service.learn.listen_element_payloads import (
    _deserialize_payload,
    _prepare_audio_segments_for_element,
    _sanitize_audio_segments_for_storage,
    _serialize_payload,
)
from flaskr.service.learn.listen_element_types import (
    ELEMENT_TYPE_CODES,
    LEGACY_ELEMENT_TYPE_MAP,
    _default_is_marker,
    _default_is_renderable,
    _normalize_bool,
    _normalized_is_speakable,
)
from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord


def _serialize_element_row(
    *,
    progress_record: LearnProgressRecord,
    element: ElementDTO,
    run_session_bid: str,
    run_event_seq: int,
) -> LearnGeneratedElement:
    return LearnGeneratedElement(
        element_bid=element.element_bid or "",
        progress_record_bid=progress_record.progress_record_bid or "",
        user_bid=progress_record.user_bid or "",
        generated_block_bid=element.generated_block_bid or "",
        outline_item_bid=progress_record.outline_item_bid or "",
        shifu_bid=progress_record.shifu_bid or "",
        run_session_bid=run_session_bid,
        run_event_seq=run_event_seq,
        event_type="element",
        role=element.role or "teacher",
        element_index=int(element.element_index or 0),
        element_type=element.element_type.value if element.element_type else "",
        element_type_code=int(element.element_type_code or 0),
        change_type=element.change_type.value if element.change_type else "",
        target_element_bid=element.target_element_bid or "",
        is_renderable=1 if element.is_renderable else 0,
        is_new=1 if element.is_new else 0,
        is_marker=1 if element.is_marker else 0,
        sequence_number=int(element.sequence_number or 0),
        is_speakable=1 if element.is_speakable else 0,
        audio_url=element.audio_url or "",
        audio_segments=json.dumps(
            _sanitize_audio_segments_for_storage(
                element.audio_segments,
                is_final=bool(element.is_final),
            ),
            ensure_ascii=False,
        ),
        is_navigable=int(element.is_navigable or 0),
        is_final=int(element.is_final or 0),
        content_text=element.content_text or "",
        payload=_serialize_payload(element.payload),
        deleted=0,
        status=1,
    )


def _element_from_row(
    row: LearnGeneratedElement,
    *,
    interaction_user_input: str = "",
) -> ElementDTO:
    element_type_raw = str(row.element_type or ElementType.TEXT.value)
    try:
        element_type = ElementType(element_type_raw)
    except ValueError:
        element_type = ElementType.TEXT
    element_type = LEGACY_ELEMENT_TYPE_MAP.get(element_type, element_type)
    change_type = None
    if row.change_type:
        try:
            change_type = ElementChangeType(row.change_type)
        except ValueError:
            change_type = None
    audio_segments_raw = getattr(row, "audio_segments", None) or "[]"
    try:
        audio_segments = json.loads(audio_segments_raw)
        if not isinstance(audio_segments, list):
            audio_segments = []
    except Exception:
        audio_segments = []
    audio_segments = _prepare_audio_segments_for_element(
        audio_segments,
        is_final=bool(row.is_final),
    )
    default_is_renderable = _default_is_renderable(element_type)
    stored_is_renderable = bool(
        getattr(row, "is_renderable", 1 if default_is_renderable else 0)
    )
    stored_is_speakable = bool(getattr(row, "is_speakable", 0))
    dto = ElementDTO(
        run_session_bid=row.run_session_bid or None,
        run_event_seq=int(row.run_event_seq or 0),
        event_type=row.event_type or "element",
        element_bid=row.element_bid or "",
        generated_block_bid=row.generated_block_bid or "",
        element_index=int(row.element_index or 0),
        role=row.role or "teacher",
        element_type=element_type,
        element_type_code=ELEMENT_TYPE_CODES.get(element_type, 0),
        change_type=change_type,
        target_element_bid=row.target_element_bid or None,
        is_renderable=stored_is_renderable and default_is_renderable,
        is_new=bool(getattr(row, "is_new", 1)),
        is_marker=_default_is_marker(element_type),
        sequence_number=int(getattr(row, "sequence_number", 0) or 0),
        is_speakable=_normalized_is_speakable(
            element_type,
            row.content_text or "",
            stored_is_speakable=stored_is_speakable,
        ),
        audio_url=str(getattr(row, "audio_url", "") or ""),
        audio_segments=audio_segments,
        is_navigable=int(row.is_navigable or 0),
        is_final=bool(row.is_final),
        content_text=row.content_text or "",
        payload=_deserialize_payload(row.payload or ""),
    )
    if element_type == ElementType.INTERACTION and interaction_user_input:
        payload = dto.payload or ElementPayloadDTO()
        payload.user_input = interaction_user_input
        dto.payload = payload
    return dto


def _deserialize_event_content(
    row: LearnGeneratedElement,
) -> (
    str | VariableUpdateDTO | OutlineItemUpdateDTO | AudioSegmentDTO | AudioCompleteDTO
):
    raw_text = row.content_text or ""
    if not raw_text:
        return ""

    if row.event_type in {
        GeneratedType.BREAK.value,
        GeneratedType.DONE.value,
        "error",
    }:
        return raw_text

    try:
        payload = json.loads(raw_text)
    except Exception:
        return raw_text

    if not isinstance(payload, dict):
        return raw_text

    if row.event_type == GeneratedType.VARIABLE_UPDATE.value:
        variable_name = str(payload.get("variable_name", "") or "")
        variable_value = str(payload.get("variable_value", "") or "")
        return VariableUpdateDTO(
            variable_name=variable_name,
            variable_value=variable_value,
        )

    if row.event_type == GeneratedType.OUTLINE_ITEM_UPDATE.value:
        status_raw = payload.get("status")
        try:
            status = LearnStatus(status_raw)
        except Exception:
            return raw_text
        return OutlineItemUpdateDTO(
            outline_bid=str(payload.get("outline_bid", "") or ""),
            title=str(payload.get("title", "") or ""),
            status=status,
            has_children=_normalize_bool(payload.get("has_children", False)),
        )

    if row.event_type == GeneratedType.AUDIO_SEGMENT.value:
        if "segment_index" not in payload or "audio_data" not in payload:
            return raw_text
        return AudioSegmentDTO(
            segment_index=int(payload.get("segment_index", 0) or 0),
            audio_data=str(payload.get("audio_data", "") or ""),
            duration_ms=int(payload.get("duration_ms", 0) or 0),
            is_final=_normalize_bool(payload.get("is_final", False)),
            position=int(payload.get("position", 0) or 0),
            stream_element_number=(
                int(payload.get("stream_element_number", 0) or 0)
                if payload.get("stream_element_number") is not None
                else None
            ),
            stream_element_type=(
                str(payload.get("stream_element_type", "") or "")
                if payload.get("stream_element_type") is not None
                else None
            ),
            av_contract=payload.get("av_contract"),
        )

    if row.event_type == GeneratedType.AUDIO_COMPLETE.value:
        if "audio_url" not in payload or "audio_bid" not in payload:
            return raw_text
        return AudioCompleteDTO(
            audio_url=str(payload.get("audio_url", "") or ""),
            audio_bid=str(payload.get("audio_bid", "") or ""),
            duration_ms=int(payload.get("duration_ms", 0) or 0),
            position=int(payload.get("position", 0) or 0),
            stream_element_number=(
                int(payload.get("stream_element_number", 0) or 0)
                if payload.get("stream_element_number") is not None
                else None
            ),
            stream_element_type=(
                str(payload.get("stream_element_type", "") or "")
                if payload.get("stream_element_type") is not None
                else None
            ),
            av_contract=payload.get("av_contract"),
        )

    return raw_text


def _event_from_row(
    row: LearnGeneratedElement,
    *,
    interaction_user_input: str = "",
) -> RunElementSSEMessageDTO:
    content: (
        str
        | ElementDTO
        | VariableUpdateDTO
        | OutlineItemUpdateDTO
        | AudioSegmentDTO
        | AudioCompleteDTO
    )
    if row.event_type == "element":
        content = _normalize_record_element(
            _element_from_row(
                row,
                interaction_user_input=interaction_user_input,
            )
        )
    else:
        content = _deserialize_event_content(row)
    return RunElementSSEMessageDTO(
        type=row.event_type or "element",
        event_type=row.event_type or "element",
        generated_block_bid=row.generated_block_bid or None,
        run_session_bid=row.run_session_bid or None,
        run_event_seq=int(row.run_event_seq or 0),
        content=content,
    )


def _normalize_record_element(element: ElementDTO) -> ElementDTO:
    payload = element.payload
    if payload is None or not payload.previous_visuals:
        return element

    primary_visual_content = next(
        (item.content for item in payload.previous_visuals if item.content),
        "",
    )
    if primary_visual_content and not (element.content_text or ""):
        element.content_text = primary_visual_content

    payload.previous_visuals = [
        ElementVisualDTO(visual_type=item.visual_type, content="")
        for item in payload.previous_visuals
    ]
    element.payload = payload
    return element
