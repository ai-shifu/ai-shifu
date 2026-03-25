from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any, Generator, Iterable

from flask import Flask
from sqlalchemy import and_, or_

from flaskr.dao import db
from flaskr.util.uuid import generate_id
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_UI
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    BlockType,
    ElementAudioDTO,
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    ElementVisualDTO,
    GeneratedType,
    LearnElementRecordDTO,
    LearnRecordDTO,
    LearnStatus,
    OutlineItemUpdateDTO,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
    VariableUpdateDTO,
)
from flaskr.service.learn.learn_funcs import get_learn_record
from flaskr.service.learn.listen_slide_builder import (
    VisualSegment,
    build_visual_segments_for_block,
)
from flaskr.service.learn.listen_source_span_utils import (
    normalize_source_span,
    slice_source_by_span,
)
from flaskr.service.learn.legacy_record_builder import build_legacy_record_for_progress
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.learn.type_state_machine import TypeInput, TypeStateMachine

ELEMENT_TYPE_CODES = {
    ElementType.HTML: 201,
    ElementType.SVG: 202,
    ElementType.DIFF: 203,
    ElementType.IMG: 204,
    ElementType.INTERACTION: 205,
    ElementType.ASK: 206,
    ElementType.ANSWER: 214,
    ElementType.TABLES: 207,
    ElementType.CODE: 208,
    ElementType.LATEX: 209,
    ElementType.MD_IMG: 210,
    ElementType.MERMAID: 211,
    ElementType.TITLE: 212,
    ElementType.TEXT: 213,
    # Legacy codes kept for backfill compatibility
    ElementType._SANDBOX: 102,
    ElementType._PICTURE: 103,
    ElementType._VIDEO: 104,
}

VISUAL_KIND_ELEMENT_TYPE_ALIASES = {
    "video": ElementType.HTML,
    "iframe": ElementType.HTML,
    "sandbox": ElementType.HTML,
    "html_table": ElementType.HTML,
    "md_table": ElementType.TABLES,
    "fence": ElementType.CODE,
    "md_img": ElementType.MD_IMG,
}

# Mapping from legacy element_type values to new enum values
LEGACY_ELEMENT_TYPE_MAP = {
    ElementType._SANDBOX: ElementType.HTML,
    ElementType._PICTURE: ElementType.IMG,
    ElementType._VIDEO: ElementType.HTML,
}


@dataclass
class LearnElementsBackfillStats:
    progress_record_bid: str
    progress_record_id: int = 0
    shifu_bid: str = ""
    outline_item_bid: str = ""
    user_bid: str = ""
    run_session_bid: str = ""
    generated_blocks_total: int = 0
    audio_records_total: int = 0
    duplicate_blocks_skipped: int = 0
    duplicate_audios_skipped: int = 0
    orphan_audios_skipped: int = 0
    skipped_empty_blocks: int = 0
    existing_active_rows: int = 0
    overwritten_rows: int = 0
    inserted_rows: int = 0
    elements_built: int = 0
    skipped_existing: bool = False
    dry_run: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LearnElementsBackfillBatchResult:
    scanned_progress_records: int = 0
    processed_progress_records: int = 0
    skipped_existing_progress_records: int = 0
    failed_progress_records: int = 0
    inserted_rows: int = 0
    overwritten_rows: int = 0
    duplicate_blocks_skipped: int = 0
    duplicate_audios_skipped: int = 0
    orphan_audios_skipped: int = 0
    skipped_empty_blocks: int = 0
    results: list[LearnElementsBackfillStats] = field(default_factory=list)

    def add(self, result: LearnElementsBackfillStats) -> None:
        self.results.append(result)
        self.scanned_progress_records += 1
        self.inserted_rows += result.inserted_rows
        self.overwritten_rows += result.overwritten_rows
        self.duplicate_blocks_skipped += result.duplicate_blocks_skipped
        self.duplicate_audios_skipped += result.duplicate_audios_skipped
        self.orphan_audios_skipped += result.orphan_audios_skipped
        self.skipped_empty_blocks += result.skipped_empty_blocks
        if result.error:
            self.failed_progress_records += 1
            return
        if result.skipped_existing:
            self.skipped_existing_progress_records += 1
        else:
            self.processed_progress_records += 1

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_bool(raw: Any) -> bool:
    if isinstance(raw, str):
        return raw.strip().lower() == "true"
    return bool(raw)


def _role_value_to_name(role_value: Any) -> str:
    if role_value == ROLE_STUDENT:
        return "student"
    if role_value == ROLE_UI:
        return "ui"
    return "teacher"


def _element_type_for_visual_kind(visual_kind: str) -> ElementType:
    normalized = (visual_kind or "").strip().lower()
    try:
        return ElementType(normalized)
    except ValueError:
        return VISUAL_KIND_ELEMENT_TYPE_ALIASES.get(normalized, ElementType.TEXT)


def _element_type_code(element_type: ElementType) -> int:
    return ELEMENT_TYPE_CODES[element_type]


def _default_is_marker(element_type: ElementType) -> bool:
    return element_type not in {ElementType.TEXT, ElementType.ASK, ElementType.ANSWER}


def _default_is_renderable(element_type: ElementType) -> bool:
    return element_type not in {
        ElementType.TEXT,
        ElementType.ASK,
        ElementType.ANSWER,
        ElementType.INTERACTION,
    }


def _default_is_speakable(element_type: ElementType, content_text: str = "") -> bool:
    return element_type in {ElementType.TEXT, ElementType.ANSWER} and bool(content_text)


def _normalized_is_speakable(
    element_type: ElementType,
    content_text: str = "",
    *,
    stored_is_speakable: bool = False,
) -> bool:
    if element_type not in {ElementType.TEXT, ElementType.ANSWER}:
        return False
    return bool(
        stored_is_speakable or _default_is_speakable(element_type, content_text)
    )


def _stream_element_accepts_audio_target(element_type: ElementType) -> bool:
    return element_type in {
        ElementType.TEXT,
        ElementType.IMG,
        ElementType.MD_IMG,
    }


def _new_element_bid(app: Flask) -> str:
    return generate_id(app)


def _visual_type_for_element(element_type: ElementType) -> str:
    if element_type == ElementType.TABLES:
        return "md_table"
    if element_type == ElementType.CODE:
        return "fence"
    if element_type == ElementType.MD_IMG:
        return "md_img"
    if element_type in {
        ElementType.HTML,
        ElementType.SVG,
        ElementType.DIFF,
        ElementType.IMG,
        ElementType.LATEX,
        ElementType.MERMAID,
    }:
        return element_type.value
    return ""


def _change_type_for_element(element_type: ElementType) -> ElementChangeType:
    if element_type == ElementType.DIFF:
        return ElementChangeType.DIFF
    return ElementChangeType.RENDER


def _payload_from_stream_element(
    element_type: ElementType,
    content: str,
    *,
    audio: ElementAudioDTO | None = None,
) -> ElementPayloadDTO:
    visual_type = _visual_type_for_element(element_type)
    previous_visuals = []
    if visual_type and content:
        previous_visuals.append(
            ElementVisualDTO(visual_type=visual_type, content=content)
        )
    return ElementPayloadDTO(audio=audio, previous_visuals=previous_visuals)


def _serialize_payload(payload: ElementPayloadDTO | None) -> str:
    if payload is None:
        return ""
    return json.dumps(payload.__json__(), ensure_ascii=False)


def _deserialize_payload(raw_payload: str) -> ElementPayloadDTO:
    if not raw_payload:
        return ElementPayloadDTO()
    try:
        payload_dict = json.loads(raw_payload)
    except Exception:
        return ElementPayloadDTO()
    audio_dict = payload_dict.get("audio")
    audio = None
    if isinstance(audio_dict, dict):
        audio = ElementAudioDTO(
            audio_url=str(audio_dict.get("audio_url", "") or ""),
            audio_bid=str(audio_dict.get("audio_bid", "") or ""),
            duration_ms=int(audio_dict.get("duration_ms", 0) or 0),
            position=int(audio_dict.get("position", 0) or 0),
        )
    visuals = []
    for item in payload_dict.get("previous_visuals") or []:
        if not isinstance(item, dict):
            continue
        visuals.append(
            ElementVisualDTO(
                visual_type=str(item.get("visual_type", "") or ""),
                content=str(item.get("content", "") or ""),
            )
        )
    diff_payload = payload_dict.get("diff_payload")
    if not isinstance(diff_payload, list):
        diff_payload = None
    anchor_element_bid = payload_dict.get("anchor_element_bid")
    if anchor_element_bid is not None:
        anchor_element_bid = str(anchor_element_bid or "")
    ask_element_bid = payload_dict.get("ask_element_bid")
    if ask_element_bid is not None:
        ask_element_bid = str(ask_element_bid or "")
    user_input = payload_dict.get("user_input")
    if user_input is not None:
        user_input = str(user_input or "")
    asks = payload_dict.get("asks")
    if not isinstance(asks, list):
        asks = None
    return ElementPayloadDTO(
        audio=audio,
        previous_visuals=visuals,
        anchor_element_bid=anchor_element_bid,
        ask_element_bid=ask_element_bid,
        user_input=user_input,
        diff_payload=diff_payload,
        asks=asks,
    )


def _load_latest_active_element_row(
    element_bid: str,
) -> LearnGeneratedElement | None:
    if not element_bid:
        return None
    return (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.element_bid == element_bid,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        )
        .order_by(
            LearnGeneratedElement.sequence_number.desc(),
            LearnGeneratedElement.run_event_seq.desc(),
            LearnGeneratedElement.id.desc(),
        )
        .first()
    )


def find_latest_ask_element_row(
    progress_record_bid: str,
    anchor_element_bid: str,
) -> LearnGeneratedElement | None:
    rows = find_follow_up_element_rows(progress_record_bid, anchor_element_bid)
    for row in reversed(rows):
        if str(row.element_type or "") == ElementType.ASK.value:
            return row
    return None


def find_follow_up_element_rows(
    progress_record_bid: str,
    anchor_element_bid: str,
) -> list[LearnGeneratedElement]:
    if not progress_record_bid or not anchor_element_bid:
        return []
    rows = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.progress_record_bid == progress_record_bid,
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.element_type.in_(
                [ElementType.ASK.value, ElementType.ANSWER.value]
            ),
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        )
        .order_by(
            LearnGeneratedElement.sequence_number.asc(),
            LearnGeneratedElement.run_event_seq.asc(),
            LearnGeneratedElement.id.asc(),
        )
        .all()
    )
    matched_rows: list[LearnGeneratedElement] = []
    for row in rows:
        payload = _deserialize_payload(row.payload or "")
        if (payload.anchor_element_bid or "") == anchor_element_bid:
            matched_rows.append(row)
    return matched_rows


def find_latest_answer_element_row(
    progress_record_bid: str,
    anchor_element_bid: str,
) -> LearnGeneratedElement | None:
    if not progress_record_bid or not anchor_element_bid:
        return None
    rows = find_follow_up_element_rows(progress_record_bid, anchor_element_bid)
    for row in reversed(rows):
        if str(row.element_type or "") == ElementType.ANSWER.value:
            return row
    return None


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


def _aggregate_segment_text(
    raw_content: str,
    av_contract: dict[str, Any] | None,
    segment_id_by_position: dict[int, str],
) -> dict[str, str]:
    if not raw_content or not isinstance(av_contract, dict):
        return {}
    aggregated: dict[str, list[str]] = {}
    for seg in av_contract.get("speakable_segments") or []:
        if not isinstance(seg, dict):
            continue
        try:
            position = int(seg.get("position", 0))
        except (TypeError, ValueError):
            continue
        segment_id = segment_id_by_position.get(position)
        if not segment_id:
            continue
        source_span = normalize_source_span(seg.get("source_span"))
        text = slice_source_by_span(raw_content, source_span).strip()
        if not text:
            continue
        aggregated.setdefault(segment_id, []).append(text)
    return {
        segment_id: "\n".join(chunks).strip()
        for segment_id, chunks in aggregated.items()
        if chunks
    }


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


def _audio_segment_payload(audio_segment: AudioSegmentDTO) -> dict[str, Any]:
    return {
        "position": int(getattr(audio_segment, "position", 0) or 0),
        "segment_index": int(audio_segment.segment_index or 0),
        "audio_data": str(audio_segment.audio_data or ""),
        "duration_ms": int(audio_segment.duration_ms or 0),
        "is_final": bool(getattr(audio_segment, "is_final", False)),
    }


def _clone_audio_segments(
    audio_segments: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    cloned: list[dict[str, Any]] = []
    for item in list(audio_segments or []):
        if not isinstance(item, dict):
            continue
        segment = dict(item)
        segment["is_final"] = bool(segment.get("is_final", False))
        cloned.append(segment)
    return cloned


def _normalize_audio_segments_for_element(
    audio_segments: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized = _clone_audio_segments(audio_segments)
    if not normalized:
        return []
    for item in normalized:
        item["is_final"] = False
    normalized[-1]["is_final"] = True
    return normalized


def _preserve_audio_segments_for_element(
    audio_segments: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return _clone_audio_segments(audio_segments)


def _prepare_audio_segments_for_element(
    audio_segments: list[dict[str, Any]] | None,
    *,
    is_final: bool,
) -> list[dict[str, Any]]:
    if is_final:
        return _normalize_audio_segments_for_element(audio_segments)
    return _preserve_audio_segments_for_element(audio_segments)


def _mark_last_audio_segment_final(
    audio_segments_by_position: dict[int, list[dict[str, Any]]],
    position: int,
) -> list[dict[str, Any]]:
    segments = audio_segments_by_position.get(position, [])
    if not segments:
        return []
    finalized_segments = [dict(item) for item in segments]
    finalized_segments[-1]["is_final"] = True
    audio_segments_by_position[position] = finalized_segments
    return finalized_segments


def _sanitize_audio_segments_for_storage(
    audio_segments: list[dict[str, Any]] | None,
    *,
    is_final: bool,
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for item in _prepare_audio_segments_for_element(
        audio_segments,
        is_final=is_final,
    ):
        sanitized.append(
            {
                "position": int(item.get("position", 0) or 0),
                "segment_index": int(item.get("segment_index", 0) or 0),
                "audio_data": "",
                "duration_ms": int(item.get("duration_ms", 0) or 0),
                "is_final": bool(item.get("is_final", False)),
            }
        )
    return sanitized


def _pick_default_audio_position(
    audio_by_position: dict[int, ElementAudioDTO],
    audio_segments_by_position: dict[int, list[dict[str, Any]]],
) -> int | None:
    if len(audio_by_position) == 1:
        return next(iter(audio_by_position))
    if len(audio_segments_by_position) == 1:
        return next(iter(audio_segments_by_position))
    if 0 in audio_by_position or 0 in audio_segments_by_position:
        return 0
    return None


def _make_audio_payload(audio: AudioCompleteDTO) -> ElementAudioDTO:
    return ElementAudioDTO(
        audio_url=audio.audio_url or "",
        audio_bid=audio.audio_bid or "",
        duration_ms=int(audio.duration_ms or 0),
        position=int(getattr(audio, "position", 0) or 0),
    )


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


def _build_legacy_record_for_progress(
    progress_record: LearnProgressRecord,
    stats: LearnElementsBackfillStats,
) -> LearnRecordDTO:
    return build_legacy_record_for_progress(
        progress_record,
        include_like_status=False,
        dedupe_blocks_by_bid=True,
        dedupe_audio_by_block_position=True,
        skip_empty_content=True,
        stats=stats,
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
    # Map legacy enum values to new ones
    element_type = LEGACY_ELEMENT_TYPE_MAP.get(element_type, element_type)
    change_type = None
    if row.change_type:
        try:
            change_type = ElementChangeType(row.change_type)
        except ValueError:
            change_type = None
    # Deserialize audio_segments from JSON text
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


def _load_interaction_user_input_by_block_bid(
    rows: list[LearnGeneratedElement],
) -> dict[str, str]:
    interaction_block_bids = {
        row.generated_block_bid or ""
        for row in rows
        if row.event_type == "element"
        and str(row.element_type or "") == ElementType.INTERACTION.value
        and (row.generated_block_bid or "")
    }
    if not interaction_block_bids:
        return {}

    interaction_blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid.in_(list(interaction_block_bids)),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        )
        .order_by(LearnGeneratedBlock.id.asc())
        .all()
    )
    interaction_user_input_by_block_bid: dict[str, str] = {}
    for interaction_block in interaction_blocks:
        interaction_user_input_by_block_bid[
            interaction_block.generated_block_bid or ""
        ] = str(interaction_block.generated_content or "")
    return interaction_user_input_by_block_bid


def _load_interaction_user_input(generated_block_bid: str) -> str:
    if not generated_block_bid:
        return ""

    interaction_block = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == generated_block_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        )
        .order_by(LearnGeneratedBlock.id.desc())
        .first()
    )
    if interaction_block is None:
        return ""
    return str(interaction_block.generated_content or "")


def _load_progress_bid_by_generated_block_bid(
    progress_record_bids: list[str],
) -> dict[str, str]:
    if not progress_record_bids:
        return {}

    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid.in_(progress_record_bids),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        )
        .order_by(LearnGeneratedBlock.id.asc())
        .all()
    )
    progress_bid_by_generated_block_bid: dict[str, str] = {}
    for block in blocks:
        generated_block_bid = block.generated_block_bid or ""
        progress_record_bid = block.progress_record_bid or ""
        if not generated_block_bid or not progress_record_bid:
            continue
        progress_bid_by_generated_block_bid[generated_block_bid] = progress_record_bid
    return progress_bid_by_generated_block_bid


def _build_final_elements_from_rows(
    rows: list[LearnGeneratedElement],
    *,
    interaction_user_input_by_block_bid: dict[str, str],
    include_non_navigable: bool = False,
) -> tuple[list[ElementDTO], list[RunElementSSEMessageDTO] | None]:
    if not rows:
        return [], [] if include_non_navigable else None

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            int(getattr(row, "sequence_number", 0) or 0),
            int(getattr(row, "run_event_seq", 0) or 0),
            int(getattr(row, "id", 0) or 0),
        ),
    )
    latest_by_bid: "OrderedDict[str, ElementDTO]" = OrderedDict()
    for row in sorted_rows:
        if row.event_type != "element" or not row.element_bid:
            continue
        dto = _element_from_row(
            row,
            interaction_user_input=interaction_user_input_by_block_bid.get(
                row.generated_block_bid or "",
                "",
            ),
        )
        if not dto.is_new and dto.target_element_bid:
            if dto.target_element_bid in latest_by_bid:
                latest_by_bid[dto.target_element_bid].apply_patch(dto)
                continue
            # Final snapshot queries only keep the latest active row. When the
            # original create row has already been retired, materialize the
            # patch row back into a standalone final element.
            dto.element_bid = dto.target_element_bid
            dto.target_element_bid = None
            dto.is_new = True
        latest_by_bid[dto.element_bid] = dto

    events = None
    if include_non_navigable:
        events = [
            _event_from_row(
                row,
                interaction_user_input=interaction_user_input_by_block_bid.get(
                    row.generated_block_bid or "",
                    "",
                ),
            )
            for row in sorted_rows
            if row.event_type != GeneratedType.AUDIO_COMPLETE.value
        ]

    return (
        [_normalize_record_element(element) for element in latest_by_bid.values()],
        events,
    )


@dataclass
class BlockMeta:
    progress_record_bid: str = ""
    role: str = "teacher"


@dataclass
class StreamElementState:
    number: int
    element_bid: str
    element_index: int
    element_type: ElementType
    stream_type: str = ""
    content_text: str = ""


@dataclass
class BlockState:
    generated_block_bid: str
    raw_content: str = ""
    audio_by_position: dict[int, ElementAudioDTO] = field(default_factory=dict)
    audio_segments_by_position: dict[int, list[dict[str, Any]]] = field(
        default_factory=dict
    )
    audio_target_element_bid_by_position: dict[int, str] = field(default_factory=dict)
    fallback_element_bid: str | None = None
    latest_av_contract: dict[str, Any] | None = None
    stream_elements: OrderedDict[str, StreamElementState] = field(
        default_factory=OrderedDict
    )
    active_stream_element_key_by_number: dict[int, str] = field(default_factory=dict)
    last_stream_element_key: str | None = None


class ListenElementRunAdapter:
    """Transform legacy listen-mode SSE into scheme-B element events."""

    def __init__(
        self,
        app: Flask,
        *,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
        run_session_bid: str | None = None,
    ):
        self.app = app
        self.shifu_bid = shifu_bid
        self.outline_bid = outline_bid
        self.user_bid = user_bid
        self.run_session_bid = run_session_bid or uuid.uuid4().hex
        self._run_event_seq = 0
        self._sequence_number = 0
        self._state_machine = TypeStateMachine()
        self._block_meta_cache: dict[str, BlockMeta] = {}
        self._block_states: dict[str, BlockState] = {}
        self._max_element_index = -1
        # Track current element bid for audio association
        self._current_element_bid: str | None = None
        # Track anchor element bid during ask flow
        self._current_ask_anchor_bid: str | None = None
        self._current_ask_element_bid: str | None = None
        self._current_answer_element_bid: str | None = None
        self._ask_element_bid_by_block_bid: dict[str, str] = {}
        self._answer_element_bid_by_block_bid: dict[str, str] = {}

    def _next_seq(self) -> int:
        self._run_event_seq += 1
        return self._run_event_seq

    def _next_sequence_number(self) -> int:
        self._sequence_number += 1
        return self._sequence_number

    def _resolve_persisted_is_new(self, element: ElementDTO) -> bool:
        if element.target_element_bid:
            return False
        return bool(element.is_new)

    def _load_block_meta(self, generated_block_bid: str) -> BlockMeta:
        if generated_block_bid in self._block_meta_cache:
            return self._block_meta_cache[generated_block_bid]
        meta = BlockMeta()
        if generated_block_bid:
            block = (
                LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.generated_block_bid == generated_block_bid,
                    LearnGeneratedBlock.deleted == 0,
                )
                .order_by(LearnGeneratedBlock.id.desc())
                .first()
            )
            if block:
                meta = BlockMeta(
                    progress_record_bid=block.progress_record_bid or "",
                    role=_role_value_to_name(block.role),
                )
        self._block_meta_cache[generated_block_bid] = meta
        return meta

    def _ensure_block_state(self, generated_block_bid: str) -> BlockState:
        state = self._block_states.get(generated_block_bid)
        if state is None:
            state = BlockState(generated_block_bid=generated_block_bid)
            self._block_states[generated_block_bid] = state
        return state

    def _resolve_ask_element_bid_for_block(
        self,
        generated_block_bid: str,
        *,
        bind_current: bool = False,
    ) -> str:
        ask_element_bid = self._ask_element_bid_by_block_bid.get(
            generated_block_bid, ""
        )
        if ask_element_bid:
            return ask_element_bid
        if bind_current and self._current_ask_element_bid:
            self._ask_element_bid_by_block_bid[generated_block_bid] = (
                self._current_ask_element_bid
            )
            return self._current_ask_element_bid
        return ""

    def _resolve_answer_element_bid_for_block(self, generated_block_bid: str) -> str:
        return self._answer_element_bid_by_block_bid.get(generated_block_bid, "")

    def _build_follow_up_payload(
        self,
        *,
        anchor_element_bid: str,
        ask_element_bid: str | None = None,
        base_payload: ElementPayloadDTO | None = None,
        audio: ElementAudioDTO | None = None,
    ) -> ElementPayloadDTO:
        payload = base_payload or ElementPayloadDTO()
        payload.audio = audio
        payload.previous_visuals = []
        payload.anchor_element_bid = anchor_element_bid
        payload.ask_element_bid = ask_element_bid
        payload.asks = None
        return payload

    def _build_ask_element(
        self,
        *,
        generated_block_bid: str,
        ask_element_bid: str,
        anchor_element_bid: str,
        content_text: str,
        element_index: int,
        is_new: bool,
        is_final: bool,
        base_payload: ElementPayloadDTO | None = None,
    ) -> ElementDTO:
        return ElementDTO(
            event_type="element",
            element_bid=ask_element_bid,
            generated_block_bid=generated_block_bid,
            element_index=element_index,
            role="student",
            element_type=ElementType.ASK,
            element_type_code=_element_type_code(ElementType.ASK),
            change_type=_change_type_for_element(ElementType.ASK),
            target_element_bid=ask_element_bid if not is_new else None,
            is_new=is_new,
            is_renderable=False,
            is_marker=False,
            is_speakable=False,
            audio_url="",
            audio_segments=[],
            is_navigable=0,
            is_final=is_final,
            content_text=content_text,
            payload=self._build_follow_up_payload(
                anchor_element_bid=anchor_element_bid,
                base_payload=base_payload,
                audio=None,
            ),
        )

    def _build_answer_element(
        self,
        *,
        generated_block_bid: str,
        answer_element_bid: str,
        anchor_element_bid: str,
        ask_element_bid: str,
        content_text: str,
        element_index: int,
        is_new: bool,
        is_final: bool,
        audio: ElementAudioDTO | None = None,
        audio_segments: list[dict[str, Any]] | None = None,
        base_payload: ElementPayloadDTO | None = None,
    ) -> ElementDTO:
        return ElementDTO(
            event_type="element",
            element_bid=answer_element_bid,
            generated_block_bid=generated_block_bid,
            element_index=element_index,
            role="teacher",
            element_type=ElementType.ANSWER,
            element_type_code=_element_type_code(ElementType.ANSWER),
            change_type=_change_type_for_element(ElementType.ANSWER),
            target_element_bid=answer_element_bid if not is_new else None,
            is_new=is_new,
            is_renderable=False,
            is_marker=False,
            is_speakable=_normalized_is_speakable(
                ElementType.ANSWER,
                content_text,
                stored_is_speakable=bool(audio is not None or audio_segments),
            ),
            audio_url=audio.audio_url if audio is not None else "",
            audio_segments=_prepare_audio_segments_for_element(
                audio_segments,
                is_final=is_final,
            ),
            is_navigable=0,
            is_final=is_final,
            content_text=content_text,
            payload=self._build_follow_up_payload(
                anchor_element_bid=anchor_element_bid,
                ask_element_bid=ask_element_bid,
                base_payload=base_payload,
                audio=audio,
            ),
        )

    def _build_answer_element_patch(
        self,
        *,
        generated_block_bid: str,
        answer_element_bid: str,
        anchor_element_bid: str,
        ask_element_bid: str,
        content_text: str,
        is_final: bool,
        audio: ElementAudioDTO | None = None,
        audio_segments: list[dict[str, Any]] | None = None,
    ) -> ElementDTO | None:
        snapshot = self._load_latest_element_snapshot(answer_element_bid)
        if snapshot is None:
            snapshot_row = _load_latest_active_element_row(answer_element_bid)
            if snapshot_row is None:
                return None
            snapshot = _element_from_row(snapshot_row)
        return self._build_answer_element(
            generated_block_bid=generated_block_bid,
            answer_element_bid=answer_element_bid,
            anchor_element_bid=anchor_element_bid,
            ask_element_bid=ask_element_bid,
            content_text=content_text,
            element_index=snapshot.element_index,
            is_new=False,
            is_final=is_final,
            audio=audio,
            audio_segments=audio_segments,
            base_payload=snapshot.payload,
        )

    def _load_follow_up_snapshot(self, element_bid: str) -> ElementDTO | None:
        snapshot = self._load_latest_element_snapshot(element_bid)
        if snapshot is not None:
            return snapshot
        snapshot_row = _load_latest_active_element_row(element_bid)
        if snapshot_row is None:
            return None
        return _element_from_row(snapshot_row)

    def _build_answer_element_from_state(
        self,
        generated_block_bid: str,
        *,
        is_final: bool,
        audio: ElementAudioDTO | None = None,
        audio_segments: list[dict[str, Any]] | None = None,
    ) -> ElementDTO | None:
        ask_element_bid = self._resolve_ask_element_bid_for_block(
            generated_block_bid,
            bind_current=True,
        )
        if not ask_element_bid:
            return None
        ask_snapshot = self._load_follow_up_snapshot(ask_element_bid)
        if ask_snapshot is None:
            return None
        ask_payload = ask_snapshot.payload or ElementPayloadDTO()
        anchor_element_bid = (
            ask_payload.anchor_element_bid or self._current_ask_anchor_bid
        )
        if not anchor_element_bid:
            return None

        state = self._block_states.get(generated_block_bid)
        answer_element_bid = self._resolve_answer_element_bid_for_block(
            generated_block_bid
        )
        has_answer_signal = bool(
            (state and state.raw_content)
            or audio is not None
            or (audio_segments and len(audio_segments) > 0)
            or answer_element_bid
        )
        if not has_answer_signal:
            return None

        if not answer_element_bid:
            answer_element_bid = _new_element_bid(self.app)
            self._answer_element_bid_by_block_bid[generated_block_bid] = (
                answer_element_bid
            )
            self._current_answer_element_bid = answer_element_bid
            return self._build_answer_element(
                generated_block_bid=generated_block_bid,
                answer_element_bid=answer_element_bid,
                anchor_element_bid=anchor_element_bid,
                ask_element_bid=ask_element_bid,
                content_text=state.raw_content if state is not None else "",
                element_index=ask_snapshot.element_index,
                is_new=True,
                is_final=is_final,
                audio=audio,
                audio_segments=audio_segments,
                base_payload=None,
            )

        self._current_answer_element_bid = answer_element_bid
        return self._build_answer_element_patch(
            generated_block_bid=generated_block_bid,
            answer_element_bid=answer_element_bid,
            anchor_element_bid=anchor_element_bid,
            ask_element_bid=ask_element_bid,
            content_text=state.raw_content if state is not None else "",
            is_final=is_final,
            audio=audio,
            audio_segments=audio_segments,
        )

    def _formatted_parts_from_event(
        self, event: RunMarkdownFlowDTO
    ) -> list[tuple[str, str, int]]:
        return event.get_mdflow_stream_parts()

    def _insert_row(
        self,
        *,
        generated_block_bid: str,
        element_index: int,
        event_type: str,
        role: str,
        element_bid: str = "",
        element_type: ElementType | None = None,
        change_type: ElementChangeType | None = None,
        target_element_bid: str | None = None,
        is_renderable: bool = True,
        is_new: bool = True,
        is_marker: bool = False,
        sequence_number: int = 0,
        is_speakable: bool = False,
        audio_url: str = "",
        audio_segments: list | None = None,
        is_navigable: int = 1,
        is_final: int = 0,
        content_text: str = "",
        payload: ElementPayloadDTO | None = None,
        run_event_seq: int,
    ) -> None:
        meta = self._load_block_meta(generated_block_bid)
        row = LearnGeneratedElement(
            element_bid=element_bid or "",
            progress_record_bid=meta.progress_record_bid,
            user_bid=self.user_bid,
            generated_block_bid=generated_block_bid or "",
            outline_item_bid=self.outline_bid,
            shifu_bid=self.shifu_bid,
            run_session_bid=self.run_session_bid,
            run_event_seq=int(run_event_seq or 0),
            event_type=event_type,
            role=role or meta.role,
            element_index=int(element_index or 0),
            element_type=element_type.value if element_type is not None else "",
            element_type_code=(
                _element_type_code(element_type) if element_type is not None else 0
            ),
            change_type=change_type.value if change_type is not None else "",
            target_element_bid=target_element_bid or "",
            is_renderable=1 if is_renderable else 0,
            is_new=1 if is_new else 0,
            is_marker=1 if is_marker else 0,
            sequence_number=int(sequence_number or 0),
            is_speakable=1 if is_speakable else 0,
            audio_url=audio_url or "",
            audio_segments=json.dumps(
                _sanitize_audio_segments_for_storage(
                    audio_segments,
                    is_final=bool(is_final),
                ),
                ensure_ascii=False,
            ),
            is_navigable=int(is_navigable or 0),
            is_final=int(is_final or 0),
            content_text=content_text or "",
            payload=_serialize_payload(payload),
            deleted=0,
            status=1,
        )
        db.session.add(row)
        db.session.flush()

    def _element_message(self, element: ElementDTO) -> RunElementSSEMessageDTO:
        self._persist_element(element)
        return RunElementSSEMessageDTO(
            type="element",
            event_type="element",
            generated_block_bid=element.generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=element.run_event_seq,
            content=element,
        )

    def _persist_element(self, element: ElementDTO) -> None:
        seq = self._next_seq()
        if element.element_type in {ElementType.ASK, ElementType.ANSWER}:
            element.is_new = bool(element.is_new)
        else:
            element.is_new = self._resolve_persisted_is_new(element)
        if not element.is_new and not element.target_element_bid:
            element.target_element_bid = element.element_bid
        # Assign sequence_number (element-level counter)
        element.sequence_number = self._next_sequence_number()
        element.run_session_bid = self.run_session_bid
        element.run_event_seq = seq
        # Feed state machine
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.CONTENT_START, is_new=element.is_new)
        # Track current element for audio association
        self._current_element_bid = (
            element.target_element_bid
            if not element.is_new and element.target_element_bid
            else element.element_bid
        )
        if not element.is_new:
            base_element_bid = element.target_element_bid or element.element_bid
            (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.run_session_bid == self.run_session_bid,
                    LearnGeneratedElement.generated_block_bid
                    == (element.generated_block_bid or ""),
                    LearnGeneratedElement.event_type == "element",
                    LearnGeneratedElement.deleted == 0,
                    LearnGeneratedElement.status == 1,
                    (LearnGeneratedElement.element_bid == base_element_bid)
                    | (LearnGeneratedElement.target_element_bid == base_element_bid),
                ).update(
                    {
                        "status": 0,
                    },
                    synchronize_session=False,
                )
            )
            db.session.flush()
        self._insert_row(
            generated_block_bid=element.generated_block_bid,
            element_index=element.element_index,
            event_type="element",
            role=element.role,
            element_bid=element.element_bid,
            element_type=element.element_type,
            change_type=element.change_type,
            target_element_bid=element.target_element_bid,
            is_renderable=element.is_renderable,
            is_new=element.is_new,
            is_marker=element.is_marker,
            sequence_number=element.sequence_number,
            is_speakable=element.is_speakable,
            audio_url=element.audio_url,
            audio_segments=element.audio_segments,
            is_navigable=element.is_navigable,
            is_final=element.is_final,
            content_text=element.content_text,
            payload=element.payload,
            run_event_seq=seq,
        )

    def _non_element_message(
        self,
        *,
        event_type: str,
        content: str
        | VariableUpdateDTO
        | OutlineItemUpdateDTO
        | AudioSegmentDTO
        | AudioCompleteDTO,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq()
        serialized_text = (
            content
            if isinstance(content, str)
            else json.dumps(content.__json__(), ensure_ascii=False)
        )
        meta = self._load_block_meta(generated_block_bid)
        self._insert_row(
            generated_block_bid=generated_block_bid,
            element_index=max(self._max_element_index, 0),
            event_type=event_type,
            role=meta.role,
            is_navigable=0,
            is_final=1,
            content_text=serialized_text,
            payload=None,
            run_event_seq=seq,
        )
        return RunElementSSEMessageDTO(
            type=event_type,
            event_type=event_type,
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            is_terminal=is_terminal,
            content=content,
        )

    def _stream_non_element_message(
        self,
        *,
        stored_event_type: str,
        emitted_event_type: str,
        content: str
        | VariableUpdateDTO
        | OutlineItemUpdateDTO
        | AudioSegmentDTO
        | AudioCompleteDTO,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq()
        serialized_text = (
            content
            if isinstance(content, str)
            else json.dumps(content.__json__(), ensure_ascii=False)
        )
        meta = self._load_block_meta(generated_block_bid)
        self._insert_row(
            generated_block_bid=generated_block_bid,
            element_index=max(self._max_element_index, 0),
            event_type=stored_event_type,
            role=meta.role,
            is_navigable=0,
            is_final=1,
            content_text=serialized_text,
            payload=None,
            run_event_seq=seq,
        )
        return RunElementSSEMessageDTO(
            type=emitted_event_type,
            event_type=emitted_event_type,
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            is_terminal=is_terminal,
            content=content,
        )

    def make_ephemeral_message(
        self,
        *,
        event_type: str,
        content: str = "",
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq()
        emitted_event_type = (
            GeneratedType.DONE.value
            if event_type == GeneratedType.BREAK.value
            else event_type
        )
        if is_terminal is None and emitted_event_type == GeneratedType.DONE.value:
            is_terminal = event_type == GeneratedType.DONE.value
        return RunElementSSEMessageDTO(
            type=emitted_event_type,
            event_type=emitted_event_type,
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            is_terminal=is_terminal,
            content=content,
        )

    def _make_inter_element_done_message(
        self, generated_block_bid: str
    ) -> RunElementSSEMessageDTO:
        return self.make_ephemeral_message(
            event_type=GeneratedType.DONE.value,
            content="",
            generated_block_bid=generated_block_bid,
            is_terminal=False,
        )

    def _build_fallback_element(self, state: BlockState, role: str) -> ElementDTO:
        if not state.fallback_element_bid:
            state.fallback_element_bid = _new_element_bid(self.app)
            self._max_element_index += 1
        return ElementDTO(
            event_type="element",
            element_bid=state.fallback_element_bid,
            generated_block_bid=state.generated_block_bid,
            element_index=max(self._max_element_index, 0),
            role=role,
            element_type=ElementType.TEXT,
            element_type_code=_element_type_code(ElementType.TEXT),
            change_type=ElementChangeType.RENDER,
            is_renderable=False,
            is_marker=False,
            is_navigable=1,
            is_final=False,
            is_speakable=_default_is_speakable(ElementType.TEXT, state.raw_content),
            content_text=state.raw_content,
            payload=ElementPayloadDTO(audio=None, previous_visuals=[]),
        )

    def _retire_fallback_element(
        self, state: BlockState, *, emit_notification: bool = True
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not state.fallback_element_bid:
            return
        (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == self.run_session_bid,
                LearnGeneratedElement.generated_block_bid == state.generated_block_bid,
                LearnGeneratedElement.element_bid == state.fallback_element_bid,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            ).update(
                {
                    "status": 0,
                },
                synchronize_session=False,
            )
        )
        if not emit_notification:
            return
        # Notify the frontend to remove the retired fallback element.
        # This is ephemeral (not persisted to DB) since the original row's
        # status was already set to 0 above.
        meta = self._load_block_meta(state.generated_block_bid)
        seq = self._next_seq()
        retire_element = ElementDTO(
            event_type="element",
            element_bid=state.fallback_element_bid,
            generated_block_bid=state.generated_block_bid,
            element_index=max(self._max_element_index, 0),
            role=meta.role,
            element_type=ElementType.TEXT,
            element_type_code=_element_type_code(ElementType.TEXT),
            change_type=_change_type_for_element(ElementType.TEXT),
            target_element_bid=state.fallback_element_bid,
            is_new=False,
            is_marker=False,
            is_renderable=False,
            is_navigable=0,
            is_final=True,
            content_text="",
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
        )
        yield RunElementSSEMessageDTO(
            type="element",
            event_type="element",
            generated_block_bid=state.generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            content=retire_element,
        )

    def _load_latest_element_snapshot(self, element_bid: str) -> ElementDTO | None:
        row = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == self.run_session_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
                (LearnGeneratedElement.element_bid == element_bid)
                | (LearnGeneratedElement.target_element_bid == element_bid),
            )
            .order_by(
                LearnGeneratedElement.sequence_number.desc(),
                LearnGeneratedElement.run_event_seq.desc(),
                LearnGeneratedElement.id.desc(),
            )
            .first()
        )
        if row is None:
            return None
        return _element_from_row(row)

    def _build_audio_patch_element(
        self,
        element_bid: str,
        audio_segments: list[dict[str, Any]] | None = None,
        *,
        is_final: bool | None = None,
    ) -> ElementDTO | None:
        snapshot = self._load_latest_element_snapshot(element_bid)
        if snapshot is None:
            return None
        element_is_final = snapshot.is_final if is_final is None else bool(is_final)
        return ElementDTO(
            event_type="element",
            element_bid=element_bid,
            generated_block_bid=snapshot.generated_block_bid,
            element_index=snapshot.element_index,
            role=snapshot.role,
            element_type=snapshot.element_type,
            element_type_code=snapshot.element_type_code,
            change_type=_change_type_for_element(snapshot.element_type),
            target_element_bid=element_bid,
            is_new=False,
            is_renderable=snapshot.is_renderable,
            is_marker=snapshot.is_marker,
            is_speakable=_normalized_is_speakable(
                snapshot.element_type,
                snapshot.content_text,
                stored_is_speakable=snapshot.is_speakable,
            ),
            audio_url=snapshot.audio_url,
            audio_segments=_prepare_audio_segments_for_element(
                audio_segments or snapshot.audio_segments or [],
                is_final=element_is_final,
            ),
            is_navigable=snapshot.is_navigable,
            is_final=element_is_final,
            content_text=snapshot.content_text,
            payload=snapshot.payload,
        )

    def _build_audio_segment_patch_message(
        self,
        element_bid: str,
        audio_segments: list[dict[str, Any]] | None = None,
    ) -> RunElementSSEMessageDTO | None:
        patch_element = self._build_audio_patch_element(
            element_bid,
            audio_segments=audio_segments,
        )
        if patch_element is None:
            return None
        return self._element_message(patch_element)

    def _backfill_audio_url(self, element_bid: str, audio_url: str) -> None:
        """Set audio_url on the element row."""
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.run_session_bid == self.run_session_bid,
            LearnGeneratedElement.element_bid == element_bid,
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ).update({"audio_url": audio_url}, synchronize_session=False)
        db.session.flush()

    def _build_stream_element_message(
        self,
        *,
        state: BlockState,
        role: str,
        stream_state: StreamElementState,
        is_new: bool,
        is_final: bool,
        audio: ElementAudioDTO | None = None,
        audio_segments: list[dict[str, Any]] | None = None,
    ) -> RunElementSSEMessageDTO:
        return self._element_message(
            self._build_stream_element(
                state=state,
                role=role,
                stream_state=stream_state,
                is_new=is_new,
                is_final=is_final,
                audio=audio,
                audio_segments=audio_segments,
            )
        )

    def _build_stream_element(
        self,
        *,
        state: BlockState,
        role: str,
        stream_state: StreamElementState,
        is_new: bool,
        is_final: bool,
        audio: ElementAudioDTO | None = None,
        audio_segments: list[dict[str, Any]] | None = None,
    ) -> ElementDTO:
        payload = _payload_from_stream_element(
            stream_state.element_type,
            stream_state.content_text,
            audio=audio,
        )
        element_bid = stream_state.element_bid
        return ElementDTO(
            event_type="element",
            element_bid=element_bid,
            generated_block_bid=state.generated_block_bid,
            element_index=stream_state.element_index,
            role=role,
            element_type=stream_state.element_type,
            element_type_code=_element_type_code(stream_state.element_type),
            change_type=_change_type_for_element(stream_state.element_type),
            target_element_bid=None if is_new else stream_state.element_bid,
            is_new=is_new,
            is_renderable=_default_is_renderable(stream_state.element_type),
            is_marker=_default_is_marker(stream_state.element_type),
            is_speakable=_normalized_is_speakable(
                stream_state.element_type,
                stream_state.content_text,
                stored_is_speakable=bool(audio is not None or audio_segments),
            ),
            audio_url=audio.audio_url if audio is not None else "",
            audio_segments=_prepare_audio_segments_for_element(
                audio_segments,
                is_final=is_final,
            ),
            is_navigable=1,
            is_final=is_final,
            content_text=stream_state.content_text,
            payload=payload,
        )

    def _resolve_pending_audio_for_stream_element(
        self,
        state: BlockState,
        stream_state: StreamElementState,
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
        self,
        state: BlockState,
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
        self,
        state: BlockState,
        position: int,
    ) -> str | None:
        existing_target = state.audio_target_element_bid_by_position.get(position)
        if existing_target:
            return existing_target

        for stream_state in reversed(list(state.stream_elements.values())):
            if not _stream_element_accepts_audio_target(stream_state.element_type):
                continue
            if not (stream_state.content_text or "").strip():
                continue
            return stream_state.element_bid

        if state.fallback_element_bid and (state.raw_content or "").strip():
            return state.fallback_element_bid

        return None

    def _handle_formatted_content(
        self, event: RunMarkdownFlowDTO, parts: list[tuple[str, str, int]]
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        state = self._ensure_block_state(generated_block_bid)
        meta = self._load_block_meta(generated_block_bid)
        for chunk_content, stream_type, stream_number in parts:
            if not chunk_content:
                continue
            state.raw_content += chunk_content
            previous_active_key = state.last_stream_element_key
            normalized_stream_type = (stream_type or "").strip().lower()
            active_key = state.active_stream_element_key_by_number.get(stream_number)
            stream_state = (
                state.stream_elements.get(active_key)
                if active_key is not None
                else None
            )
            slot_was_interrupted = stream_state is not None and active_key not in (
                None,
                state.last_stream_element_key,
            )
            # mdflow already decides stream boundaries. Keep continuity keyed by
            # its original number/type pair and only project custom element
            # semantics once when a new stream element starts.
            same_mdflow_stream = (
                stream_state is not None
                and not slot_was_interrupted
                and stream_state.stream_type == normalized_stream_type
            )
            try:
                incoming_element_type = ElementType(normalized_stream_type)
            except ValueError:
                incoming_element_type = ElementType.TEXT
            stream_element_type = (
                stream_state.element_type
                if same_mdflow_stream
                else incoming_element_type
            )
            if stream_state is None or slot_was_interrupted or not same_mdflow_stream:
                if slot_was_interrupted:
                    stream_state = None
                    active_key = None
                self._max_element_index += 1
                stream_state = StreamElementState(
                    number=stream_number,
                    element_bid=_new_element_bid(self.app),
                    element_index=max(self._max_element_index, 0),
                    element_type=stream_element_type,
                    stream_type=normalized_stream_type,
                )
                stream_key = f"{stream_number}:{len(state.stream_elements)}"
                state.stream_elements[stream_key] = stream_state
                state.active_stream_element_key_by_number[stream_number] = stream_key
                active_key = stream_key
                is_new = True
            else:
                is_new = False
            stream_state.content_text += chunk_content
            pending_audio = None
            pending_audio_segments = None
            if is_new:
                pending_audio, pending_audio_segments = (
                    self._resolve_pending_audio_for_stream_element(
                        state,
                        stream_state,
                    )
                )
                if (
                    previous_active_key is not None
                    and previous_active_key != active_key
                ):
                    yield self._make_inter_element_done_message(generated_block_bid)
            state.last_stream_element_key = active_key
            yield self._build_stream_element_message(
                state=state,
                role=meta.role,
                stream_state=stream_state,
                is_new=is_new,
                is_final=False,
                audio=pending_audio,
                audio_segments=pending_audio_segments,
            )

    def _retire_stream_elements(
        self, state: BlockState, *, emit_notification: bool = True
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not state.stream_elements:
            return
        target_bids = [item.element_bid for item in state.stream_elements.values()]
        (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == self.run_session_bid,
                LearnGeneratedElement.generated_block_bid == state.generated_block_bid,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
                LearnGeneratedElement.event_type == "element",
                (
                    LearnGeneratedElement.element_bid.in_(target_bids)
                    | LearnGeneratedElement.target_element_bid.in_(target_bids)
                ),
            ).update(
                {
                    "status": 0,
                },
                synchronize_session=False,
            )
        )
        if not emit_notification:
            return
        meta = self._load_block_meta(state.generated_block_bid)
        for stream_state in state.stream_elements.values():
            seq = self._next_seq()
            retire_element = ElementDTO(
                event_type="element",
                element_bid=stream_state.element_bid,
                generated_block_bid=state.generated_block_bid,
                element_index=stream_state.element_index,
                role=meta.role,
                element_type=stream_state.element_type,
                element_type_code=_element_type_code(stream_state.element_type),
                change_type=_change_type_for_element(stream_state.element_type),
                target_element_bid=stream_state.element_bid,
                is_new=False,
                is_marker=_default_is_marker(stream_state.element_type),
                is_renderable=False,
                is_navigable=0,
                is_final=True,
                content_text="",
                run_session_bid=self.run_session_bid,
                run_event_seq=seq,
            )
            yield RunElementSSEMessageDTO(
                type="element",
                event_type="element",
                generated_block_bid=state.generated_block_bid or None,
                run_session_bid=self.run_session_bid,
                run_event_seq=seq,
                content=retire_element,
            )

    def _finalize_stream_elements(
        self, state: BlockState, *, emit: bool = True
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not state.stream_elements:
            return
        meta = self._load_block_meta(state.generated_block_bid)
        for stream_state in state.stream_elements.values():
            audio, audio_segments = self._resolve_stream_audio_for_element_bid(
                state,
                stream_state.element_bid,
            )
            element = self._build_stream_element(
                state=state,
                role=meta.role,
                stream_state=stream_state,
                is_new=False,
                is_final=True,
                audio=audio,
                audio_segments=audio_segments,
            )
            if emit:
                yield self._element_message(element)
            else:
                self._persist_element(element)

    def _handle_content(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        ask_element_bid = self._resolve_ask_element_bid_for_block(
            generated_block_bid,
            bind_current=True,
        )
        if ask_element_bid:
            state = self._ensure_block_state(generated_block_bid)
            state.raw_content += str(event.content or "")
            audio = state.audio_by_position.get(0)
            audio_segments = state.audio_segments_by_position.get(0, [])
            answer_element = self._build_answer_element_from_state(
                generated_block_bid,
                is_final=False,
                audio=audio,
                audio_segments=audio_segments,
            )
            if answer_element is not None:
                yield self._element_message(answer_element)
            return

        formatted_parts = self._formatted_parts_from_event(event)
        if formatted_parts:
            yield from self._handle_formatted_content(event, formatted_parts)
            return
        state = self._ensure_block_state(generated_block_bid)
        state.raw_content += str(event.content or "")
        meta = self._load_block_meta(generated_block_bid)
        fallback = self._build_fallback_element(state, meta.role)
        yield self._element_message(fallback)

    def _handle_audio_complete(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        content = event.content
        if not isinstance(content, AudioCompleteDTO):
            yield self._non_element_message(
                event_type=GeneratedType.AUDIO_COMPLETE.value,
                content=event.content,
                generated_block_bid=generated_block_bid,
            )
            return
        state = self._ensure_block_state(generated_block_bid)
        if isinstance(content.av_contract, dict):
            state.latest_av_contract = content.av_contract
        position = int(getattr(content, "position", 0) or 0)
        state.audio_by_position[position] = _make_audio_payload(content)
        finalized_audio_segments = _mark_last_audio_segment_final(
            state.audio_segments_by_position,
            position,
        )
        ask_element_bid = self._resolve_ask_element_bid_for_block(
            generated_block_bid,
            bind_current=True,
        )
        if ask_element_bid:
            answer_element = self._build_answer_element_from_state(
                generated_block_bid,
                is_final=True,
                audio=state.audio_by_position.get(position),
                audio_segments=finalized_audio_segments,
            )
            if answer_element is not None:
                yield self._element_message(answer_element)
            if not self._state_machine.is_terminated:
                self._state_machine.feed(TypeInput.AUDIO_COMPLETE)
            return
        target_element_bid = self._resolve_audio_target_element_bid(state, position)
        if target_element_bid:
            state.audio_target_element_bid_by_position[position] = target_element_bid
        if target_element_bid and content.audio_url:
            self._backfill_audio_url(target_element_bid, content.audio_url)
            audio_payload = _make_audio_payload(content)
            patch_element = self._build_audio_patch_element(
                target_element_bid,
                audio_segments=finalized_audio_segments,
                is_final=True,
            )
            if patch_element is not None:
                patch_element.audio_url = content.audio_url
                payload = patch_element.payload or ElementPayloadDTO()
                payload.audio = audio_payload
                patch_element.payload = payload
                yield self._element_message(patch_element)
        # Feed state machine
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.AUDIO_COMPLETE)

    def _handle_audio_segment(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        content = event.content
        if isinstance(content, AudioSegmentDTO):
            state = self._ensure_block_state(generated_block_bid)
            if isinstance(content.av_contract, dict):
                state.latest_av_contract = content.av_contract
            position = int(getattr(content, "position", 0) or 0)
            if position not in state.audio_by_position:
                state.audio_by_position[position] = ElementAudioDTO(
                    audio_url="",
                    audio_bid="",
                    duration_ms=int(getattr(content, "duration_ms", 0) or 0),
                    position=position,
                )
            segment_data = _audio_segment_payload(content)
            state.audio_segments_by_position.setdefault(position, []).append(
                segment_data
            )
            ask_element_bid = self._resolve_ask_element_bid_for_block(
                generated_block_bid,
                bind_current=True,
            )
            if ask_element_bid:
                answer_element = self._build_answer_element_from_state(
                    generated_block_bid,
                    is_final=False,
                    audio=state.audio_by_position.get(position),
                    audio_segments=state.audio_segments_by_position.get(position, []),
                )
                if answer_element is not None:
                    yield self._element_message(answer_element)
                if not self._state_machine.is_terminated:
                    self._state_machine.feed(TypeInput.AUDIO_SEGMENT)
                return
            target_element_bid = self._resolve_audio_target_element_bid(state, position)
            if target_element_bid:
                state.audio_target_element_bid_by_position[position] = (
                    target_element_bid
                )
                patch_message = self._build_audio_segment_patch_message(
                    target_element_bid,
                    audio_segments=[segment_data],
                )
                if patch_message is not None:
                    yield patch_message
        # Feed state machine
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.AUDIO_SEGMENT)
        return

    def _finalize_block(
        self, generated_block_bid: str
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not generated_block_bid:
            return
        state = self._block_states.get(generated_block_bid)
        if state is None:
            return
        meta = self._load_block_meta(generated_block_bid)
        visual_segments: list[VisualSegment] = []
        pos_to_seg_id: dict[int, str] = {}
        if (
            isinstance(state.latest_av_contract, dict)
            and (state.raw_content or "").strip()
        ):
            visual_segments, pos_to_seg_id = build_visual_segments_for_block(
                app=self.app,
                raw_content=state.raw_content or "",
                generated_block_bid=generated_block_bid,
                av_contract=state.latest_av_contract,
                element_index_offset=max(self._max_element_index + 1, 0),
            )
            if not visual_segments:
                visual_boundaries = (
                    state.latest_av_contract.get("visual_boundaries") or []
                )
                next_index = max(self._max_element_index + 1, 0)
                for boundary in visual_boundaries:
                    if not isinstance(boundary, dict):
                        continue
                    source_span = normalize_source_span(boundary.get("source_span"))
                    if not source_span:
                        continue
                    visual_kind = str(boundary.get("kind", "") or "")
                    if not visual_kind:
                        continue
                    visual_segments.append(
                        VisualSegment(
                            segment_id=_new_element_bid(self.app),
                            generated_block_bid=generated_block_bid,
                            element_index=next_index,
                            audio_position=int(boundary.get("position", 0) or 0),
                            visual_kind=visual_kind,
                            segment_type="sandbox"
                            if visual_kind in {"iframe", "sandbox", "html_table"}
                            else "markdown",
                            segment_content=slice_source_by_span(
                                state.raw_content, source_span
                            ),
                            source_span=source_span,
                            is_placeholder=False,
                        )
                    )
                    next_index += 1

        if visual_segments:
            had_stream_elements = bool(state.stream_elements)
            if state.stream_elements:
                yield from self._retire_stream_elements(
                    state,
                    emit_notification=False,
                )
            yield from self._retire_fallback_element(
                state,
                emit_notification=not had_stream_elements,
            )
            final_elements = _build_final_elements_for_av_contract(
                app=self.app,
                generated_block_bid=generated_block_bid,
                role=meta.role,
                raw_content=state.raw_content,
                av_contract=state.latest_av_contract,
                visual_segments=visual_segments,
                audio_by_position=state.audio_by_position,
                audio_segments_by_position=state.audio_segments_by_position,
                position_to_segment_id=pos_to_seg_id,
                element_index_offset=max(self._max_element_index + 1, 0),
            )
            for element in final_elements:
                self._max_element_index = max(
                    self._max_element_index, element.element_index
                )
                if had_stream_elements:
                    self._persist_element(element)
                else:
                    yield self._element_message(element)
        elif state.stream_elements:
            yield from self._retire_fallback_element(state, emit_notification=False)
            yield from self._finalize_stream_elements(state, emit=True)
        elif state.fallback_element_bid:
            default_audio_position = _pick_default_audio_position(
                state.audio_by_position,
                state.audio_segments_by_position,
            )
            default_audio = (
                state.audio_by_position.get(default_audio_position)
                if default_audio_position is not None
                else None
            )
            element = ElementDTO(
                event_type="element",
                element_bid=state.fallback_element_bid,
                generated_block_bid=generated_block_bid,
                element_index=max(self._max_element_index, 0),
                role=meta.role,
                element_type=ElementType.TEXT,
                element_type_code=_element_type_code(ElementType.TEXT),
                change_type=_change_type_for_element(ElementType.TEXT),
                target_element_bid=state.fallback_element_bid,
                is_new=False,
                is_renderable=False,
                is_marker=False,
                is_navigable=1,
                is_final=True,
                is_speakable=_default_is_speakable(
                    ElementType.TEXT,
                    state.raw_content,
                ),
                audio_url=default_audio.audio_url if default_audio is not None else "",
                audio_segments=(
                    state.audio_segments_by_position.get(default_audio_position, [])
                    if default_audio_position is not None
                    else []
                ),
                content_text=state.raw_content,
                payload=ElementPayloadDTO(audio=default_audio, previous_visuals=[]),
            )
            self._persist_element(element)
        self._block_states.pop(generated_block_bid, None)

    def _handle_interaction(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        interaction_user_input = _load_interaction_user_input(generated_block_bid)
        payload = ElementPayloadDTO(audio=None, previous_visuals=[])
        if interaction_user_input:
            payload.user_input = interaction_user_input
        self._max_element_index += 1
        element = ElementDTO(
            event_type="element",
            element_bid=_new_element_bid(self.app),
            generated_block_bid=generated_block_bid,
            element_index=max(self._max_element_index, 0),
            role="ui",
            element_type=ElementType.INTERACTION,
            element_type_code=_element_type_code(ElementType.INTERACTION),
            change_type=ElementChangeType.RENDER,
            is_renderable=False,
            is_marker=True,
            is_navigable=0,
            is_final=True,
            content_text=str(event.content or ""),
            payload=payload,
        )
        yield self._element_message(element)

    def _handle_ask(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        """Create a standalone ask sidecar element for the anchor."""
        anchor_bid = getattr(event, "anchor_element_bid", "") or ""
        ask_content = str(event.content or "")
        if not anchor_bid:
            self.app.logger.warning("ASK event without anchor_element_bid, skipping")
            return

        self._current_ask_anchor_bid = anchor_bid
        generated_block_bid = event.generated_block_bid or ""
        meta = self._load_block_meta(generated_block_bid)
        anchor_row = _load_latest_active_element_row(anchor_bid)
        if anchor_row is None:
            self.app.logger.warning("ASK anchor element not found: %s", anchor_bid)
            return
        if not meta.progress_record_bid:
            meta.progress_record_bid = anchor_row.progress_record_bid or ""
            self._block_meta_cache[generated_block_bid] = meta

        ask_element_bid = _new_element_bid(self.app)
        self._current_ask_element_bid = ask_element_bid
        self._current_answer_element_bid = None
        self._ask_element_bid_by_block_bid[generated_block_bid] = ask_element_bid

        ask_element = self._build_ask_element(
            generated_block_bid=generated_block_bid,
            ask_element_bid=ask_element_bid,
            anchor_element_bid=anchor_bid,
            content_text=ask_content,
            element_index=int(anchor_row.element_index or 0),
            is_new=True,
            is_final=True,
            base_payload=ElementPayloadDTO(anchor_element_bid=anchor_bid),
        )
        yield self._element_message(ask_element)

    def _finalize_answer_element(
        self, generated_block_bid: str
    ) -> RunElementSSEMessageDTO | None:
        """Finalize the answer sidecar element on BREAK."""
        state = self._block_states.get(generated_block_bid)
        default_audio_position = (
            _pick_default_audio_position(
                state.audio_by_position,
                state.audio_segments_by_position,
            )
            if state is not None
            else None
        )
        answer_element = self._build_answer_element_from_state(
            generated_block_bid,
            is_final=True,
            audio=(
                state.audio_by_position.get(default_audio_position)
                if state is not None and default_audio_position is not None
                else None
            ),
            audio_segments=(
                state.audio_segments_by_position.get(default_audio_position, [])
                if state is not None and default_audio_position is not None
                else []
            ),
        )
        if answer_element is None:
            return None
        return self._element_message(answer_element)

    def process(
        self, events: Iterable[RunMarkdownFlowDTO]
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        for event in events:
            if event.type == GeneratedType.CONTENT:
                yield from self._handle_content(event)
                continue
            if event.type == GeneratedType.AUDIO_SEGMENT:
                yield from self._handle_audio_segment(event)
                continue
            if event.type == GeneratedType.AUDIO_COMPLETE:
                yield from self._handle_audio_complete(event)
                continue
            if event.type == GeneratedType.ASK:
                yield from self._handle_ask(event)
                continue
            if event.type == GeneratedType.INTERACTION:
                yield from self._handle_interaction(event)
                continue
            if event.type == GeneratedType.BREAK:
                generated_block_bid = event.generated_block_bid or ""
                ask_element_bid = self._resolve_ask_element_bid_for_block(
                    generated_block_bid
                )
                if ask_element_bid:
                    answer_patch = self._finalize_answer_element(
                        generated_block_bid,
                    )
                    if answer_patch is not None:
                        yield answer_patch
                    self._block_states.pop(generated_block_bid, None)
                else:
                    yield from self._finalize_block(generated_block_bid)
                if not self._state_machine.is_terminated:
                    self._state_machine.feed(TypeInput.BLOCK_BREAK)
                self._current_element_bid = None
                self._current_ask_anchor_bid = None
                self._current_ask_element_bid = None
                self._current_answer_element_bid = None
                yield self._stream_non_element_message(
                    stored_event_type=GeneratedType.BREAK.value,
                    emitted_event_type=GeneratedType.DONE.value,
                    content="",
                    generated_block_bid=generated_block_bid,
                    is_terminal=False,
                )
                continue
            if event.type == GeneratedType.DONE:
                for block_id in list(self._block_states.keys()):
                    yield from self._finalize_block(block_id)
                if not self._state_machine.is_terminated:
                    self._state_machine.feed(TypeInput.DONE)
                self._current_element_bid = None
                yield self._non_element_message(
                    event_type=GeneratedType.DONE.value,
                    content="",
                    generated_block_bid=event.generated_block_bid or "",
                    is_terminal=True,
                )
                continue
            if event.type == GeneratedType.VARIABLE_UPDATE:
                yield self._non_element_message(
                    event_type=GeneratedType.VARIABLE_UPDATE.value,
                    content=event.content,
                    generated_block_bid=event.generated_block_bid or "",
                )
                continue
            if event.type == GeneratedType.OUTLINE_ITEM_UPDATE:
                yield self._non_element_message(
                    event_type=GeneratedType.OUTLINE_ITEM_UPDATE.value,
                    content=event.content,
                    generated_block_bid=event.generated_block_bid or "",
                )
                continue


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


def build_listen_elements_from_legacy_record(
    app: Flask,
    legacy_record: LearnRecordDTO,
) -> LearnElementRecordDTO:
    elements: list[ElementDTO] = []
    max_index = -1

    for record in legacy_record.records:
        block_type = record.block_type
        if block_type == BlockType.INTERACTION:
            max_index += 1
            elements.append(
                _interaction_element_from_record(
                    app,
                    record.generated_block_bid,
                    record.content,
                    user_input=record.user_input,
                    role="ui",
                    element_index=max_index,
                )
            )
            continue

        role = "student" if block_type == BlockType.ASK else "teacher"
        visual_segments: list[VisualSegment] = []
        audio_by_position: dict[int, ElementAudioDTO] = {}
        for audio in record.audios or []:
            audio_payload = _make_audio_payload(audio)
            audio_by_position[int(getattr(audio, "position", 0) or 0)] = audio_payload

        persisted_final_elements: list[ElementDTO] = []
        if record.generated_block_bid:
            with app.app_context():
                persisted_final_elements = get_final_elements_for_generated_block(
                    generated_block_bid=record.generated_block_bid,
                )
        if persisted_final_elements:
            text_elements = [
                element
                for element in persisted_final_elements
                if element.element_type == ElementType.TEXT
            ]
            can_bind_audio_to_persisted = True
            for position, audio_payload in audio_by_position.items():
                if position < 0 or position >= len(text_elements):
                    can_bind_audio_to_persisted = False
                    break
                target = text_elements[position]
                target.audio_url = audio_payload.audio_url or ""
                target.audio_segments = []
                target.is_speakable = _default_is_speakable(
                    ElementType.TEXT,
                    target.content_text or "",
                )
                payload = target.payload or ElementPayloadDTO(previous_visuals=[])
                payload.audio = audio_payload
                target.payload = payload

            if can_bind_audio_to_persisted:
                next_index = max_index + 1
                for element in persisted_final_elements:
                    element.element_index = next_index
                    next_index += 1
                    max_index = max(max_index, element.element_index)
                    elements.append(element)
                continue

        if isinstance(record.av_contract, dict) and (record.content or "").strip():
            visual_segments, pos_to_seg_id = build_visual_segments_for_block(
                app=app,
                raw_content=record.content or "",
                generated_block_bid=record.generated_block_bid,
                av_contract=record.av_contract,
                element_index_offset=max_index + 1,
            )

        if visual_segments:
            built_elements = _build_final_elements_for_av_contract(
                app=app,
                generated_block_bid=record.generated_block_bid,
                role=role,
                raw_content=record.content or "",
                av_contract=record.av_contract
                if isinstance(record.av_contract, dict)
                else None,
                visual_segments=visual_segments,
                audio_by_position=audio_by_position,
                audio_segments_by_position={},
                position_to_segment_id=pos_to_seg_id,
                element_index_offset=max_index + 1,
            )
            for element in built_elements:
                max_index = max(max_index, element.element_index)
                elements.append(element)
            continue

        max_index += 1
        elements.append(
            ElementDTO(
                event_type="element",
                element_bid=_new_element_bid(app),
                generated_block_bid=record.generated_block_bid,
                element_index=max_index,
                role=role,
                element_type=ElementType.TEXT,
                element_type_code=_element_type_code(ElementType.TEXT),
                change_type=ElementChangeType.RENDER,
                is_renderable=False,
                is_navigable=1,
                is_final=True,
                is_speakable=_default_is_speakable(
                    ElementType.TEXT,
                    record.content or "",
                ),
                audio_url=(
                    audio_by_position[0].audio_url if audio_by_position.get(0) else ""
                ),
                audio_segments=[],
                content_text=record.content or "",
                payload=ElementPayloadDTO(
                    audio=audio_by_position.get(0),
                    previous_visuals=[],
                ),
            )
        )

    elements.sort(key=lambda item: (item.element_index, item.run_event_seq or 0))
    return LearnElementRecordDTO(elements=elements)


def backfill_learn_generated_elements_for_progress(
    app: Flask,
    progress_record_bid: str,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> LearnElementsBackfillStats:
    progress_record = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.progress_record_bid == progress_record_bid,
            LearnProgressRecord.deleted == 0,
        )
        .order_by(LearnProgressRecord.id.desc())
        .first()
    )
    if progress_record is None:
        raise ValueError(f"progress record not found: {progress_record_bid}")

    stats = LearnElementsBackfillStats(
        progress_record_bid=progress_record.progress_record_bid or progress_record_bid,
        progress_record_id=int(progress_record.id or 0),
        shifu_bid=progress_record.shifu_bid or "",
        outline_item_bid=progress_record.outline_item_bid or "",
        user_bid=progress_record.user_bid or "",
        dry_run=dry_run,
    )

    existing_rows_query = LearnGeneratedElement.query.filter(
        LearnGeneratedElement.progress_record_bid
        == progress_record.progress_record_bid,
        LearnGeneratedElement.deleted == 0,
        LearnGeneratedElement.status == 1,
    )
    stats.existing_active_rows = existing_rows_query.count()
    if stats.existing_active_rows and not overwrite:
        stats.skipped_existing = True
        app.logger.info(
            "Skip learn element backfill for progress %s: %s active rows already exist",
            progress_record.progress_record_bid,
            stats.existing_active_rows,
        )
        return stats

    legacy_record = _build_legacy_record_for_progress(progress_record, stats)
    built_record = build_listen_elements_from_legacy_record(app, legacy_record)
    stats.elements_built = len(built_record.elements)
    stats.inserted_rows = stats.elements_built
    stats.run_session_bid = (
        f"backfill_{progress_record.progress_record_bid}_{uuid.uuid4().hex[:12]}"
    )

    if dry_run:
        app.logger.info(
            "Dry-run learn element backfill prepared: %s",
            stats.as_dict(),
        )
        return stats

    if stats.existing_active_rows:
        stats.overwritten_rows = existing_rows_query.update(
            {
                "status": 0,
            },
            synchronize_session=False,
        )

    for run_event_seq, element in enumerate(built_record.elements, start=1):
        # Assign sequence_number for backfilled elements
        element.sequence_number = run_event_seq
        # Extract audio_url from payload if available
        if (
            element.payload
            and element.payload.audio
            and element.payload.audio.audio_url
        ):
            element.audio_url = element.payload.audio.audio_url
            element.is_speakable = True
        row = _serialize_element_row(
            progress_record=progress_record,
            element=element,
            run_session_bid=stats.run_session_bid,
            run_event_seq=run_event_seq,
        )
        db.session.add(row)

    db.session.commit()
    app.logger.info(
        "Learn element backfill completed: %s",
        stats.as_dict(),
    )
    return stats


def backfill_learn_generated_elements_batch(
    app: Flask,
    *,
    progress_record_bids: list[str] | None = None,
    after_id: int = 0,
    limit: int = 100,
    overwrite: bool = False,
    dry_run: bool = False,
) -> LearnElementsBackfillBatchResult:
    batch_result = LearnElementsBackfillBatchResult()

    if progress_record_bids:
        progress_records = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.progress_record_bid.in_(progress_record_bids),
                LearnProgressRecord.deleted == 0,
            )
            .order_by(LearnProgressRecord.id.asc())
            .all()
        )
        existing_bids = {
            progress_record.progress_record_bid for progress_record in progress_records
        }
        missing_bids = [
            progress_record_bid
            for progress_record_bid in progress_record_bids
            if progress_record_bid not in existing_bids
        ]
        for missing_bid in missing_bids:
            batch_result.add(
                LearnElementsBackfillStats(
                    progress_record_bid=missing_bid,
                    error=f"progress record not found: {missing_bid}",
                    dry_run=dry_run,
                )
            )
    else:
        progress_records = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.id > int(after_id or 0),
            )
            .order_by(LearnProgressRecord.id.asc())
            .limit(max(int(limit or 0), 0))
            .all()
        )

    for progress_record in progress_records:
        try:
            result = backfill_learn_generated_elements_for_progress(
                app,
                progress_record.progress_record_bid,
                overwrite=overwrite,
                dry_run=dry_run,
            )
        except Exception as exc:
            db.session.rollback()
            app.logger.exception(
                "Learn element backfill failed for progress %s",
                progress_record.progress_record_bid,
            )
            result = LearnElementsBackfillStats(
                progress_record_bid=progress_record.progress_record_bid or "",
                progress_record_id=int(progress_record.id or 0),
                shifu_bid=progress_record.shifu_bid or "",
                outline_item_bid=progress_record.outline_item_bid or "",
                user_bid=progress_record.user_bid or "",
                dry_run=dry_run,
                error=str(exc),
            )
        batch_result.add(result)

    return batch_result


def _query_element_rows(
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bids: list[str],
) -> tuple[list[LearnGeneratedElement], dict[str, str]]:
    progress_bid_by_generated_block_bid = _load_progress_bid_by_generated_block_bid(
        progress_record_bids
    )
    relevant_generated_block_bids = list(progress_bid_by_generated_block_bid.keys())
    progress_row_filter = LearnGeneratedElement.progress_record_bid.in_(
        progress_record_bids
    )
    if relevant_generated_block_bids:
        progress_row_filter = or_(
            progress_row_filter,
            and_(
                or_(
                    LearnGeneratedElement.progress_record_bid == "",
                    LearnGeneratedElement.progress_record_bid.is_(None),
                ),
                LearnGeneratedElement.generated_block_bid.in_(
                    relevant_generated_block_bids
                ),
            ),
        )
    rows = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.user_bid == user_bid,
            LearnGeneratedElement.shifu_bid == shifu_bid,
            LearnGeneratedElement.outline_item_bid == outline_bid,
            progress_row_filter,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        )
        .order_by(
            LearnGeneratedElement.sequence_number.asc(),
            LearnGeneratedElement.run_event_seq.asc(),
            LearnGeneratedElement.id.asc(),
        )
        .all()
    )
    active_generated_block_bids = set(progress_bid_by_generated_block_bid.keys())
    if active_generated_block_bids:
        rows = [
            row
            for row in rows
            if not (row.generated_block_bid or "")
            or (row.generated_block_bid or "") in active_generated_block_bids
        ]
    return rows, progress_bid_by_generated_block_bid


def get_final_elements_for_generated_block(
    *,
    generated_block_bid: str,
    user_bid: str = "",
    shifu_bid: str = "",
    include_non_navigable: bool = False,
) -> list[ElementDTO]:
    if not generated_block_bid:
        return []

    filters = [
        LearnGeneratedElement.generated_block_bid == generated_block_bid,
        LearnGeneratedElement.event_type == "element",
        LearnGeneratedElement.deleted == 0,
        LearnGeneratedElement.status == 1,
    ]
    if user_bid:
        filters.append(LearnGeneratedElement.user_bid == user_bid)
    if shifu_bid:
        filters.append(LearnGeneratedElement.shifu_bid == shifu_bid)

    rows = (
        LearnGeneratedElement.query.filter(*filters)
        .order_by(
            LearnGeneratedElement.sequence_number.asc(),
            LearnGeneratedElement.run_event_seq.asc(),
            LearnGeneratedElement.id.asc(),
        )
        .all()
    )
    if not rows:
        return []

    interaction_user_input_by_block_bid = _load_interaction_user_input_by_block_bid(
        rows
    )
    final_elements, _ = _build_final_elements_from_rows(
        rows,
        interaction_user_input_by_block_bid=interaction_user_input_by_block_bid,
        include_non_navigable=include_non_navigable,
    )
    return final_elements


def _dedupe_progress_records_by_block_position(progress_records: list) -> list:
    latest_by_key: dict[tuple[str, str], Any] = {}
    for progress_record in progress_records:
        if progress_record is None:
            continue
        block_position = getattr(progress_record, "block_position", None)
        if block_position is None:
            key = ("bid", str(progress_record.progress_record_bid or ""))
        else:
            key = ("position", str(int(block_position)))
        current = latest_by_key.get(key)
        if current is None or int(progress_record.id or 0) >= int(current.id or 0):
            latest_by_key[key] = progress_record
    return sorted(
        latest_by_key.values(),
        key=lambda item: (
            int(getattr(item, "block_position", 0) or 0),
            int(item.id or 0),
        ),
    )


def _merge_progress_elements(
    app: Flask,
    *,
    progress_records: list,
    rows: list[LearnGeneratedElement],
    progress_bid_by_generated_block_bid: dict[str, str],
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    include_non_navigable: bool,
) -> tuple[list[ElementDTO], list[RunElementSSEMessageDTO] | None]:
    rows_by_progress: dict[str, list[LearnGeneratedElement]] = {}
    for row in rows:
        progress_bid = (
            row.progress_record_bid
            or progress_bid_by_generated_block_bid.get(
                row.generated_block_bid or "",
                "",
            )
        )
        if not progress_bid:
            continue
        rows_by_progress.setdefault(progress_bid, []).append(row)

    interaction_user_input_by_block_bid = _load_interaction_user_input_by_block_bid(
        rows
    )

    collected_elements: list[ElementDTO] = []
    collected_events: list[RunElementSSEMessageDTO] | None = (
        [] if include_non_navigable else None
    )

    for progress_record in progress_records:
        progress_bid = progress_record.progress_record_bid or ""
        progress_rows = rows_by_progress.get(progress_bid, [])
        persisted_elements, persisted_events = _build_final_elements_from_rows(
            progress_rows,
            interaction_user_input_by_block_bid=interaction_user_input_by_block_bid,
            include_non_navigable=include_non_navigable,
        )
        persisted_block_bids = {
            row.generated_block_bid or ""
            for row in progress_rows
            if row.event_type == "element" and (row.generated_block_bid or "")
        }

        legacy_record = build_legacy_record_for_progress(
            progress_record,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            include_like_status=False,
            dedupe_blocks_by_bid=True,
            dedupe_audio_by_block_position=True,
            skip_empty_content=True,
        )
        legacy_records = [
            record
            for record in legacy_record.records
            if (record.generated_block_bid or "") not in persisted_block_bids
        ]
        legacy_elements: list[ElementDTO] = []
        if legacy_records:
            built_record = build_listen_elements_from_legacy_record(
                app,
                LearnRecordDTO(records=legacy_records),
            )
            legacy_elements = [
                _normalize_record_element(element) for element in built_record.elements
            ]
            if include_non_navigable and collected_events is not None:
                for event in built_record.events or []:
                    collected_events.append(event)

        merged_elements = list(persisted_elements) + legacy_elements
        merged_elements.sort(
            key=lambda item: (
                int(item.element_index or 0),
                int(item.run_event_seq or 0),
                item.generated_block_bid or "",
                item.element_bid or "",
            )
        )
        collected_elements.extend(merged_elements)
        if include_non_navigable and collected_events is not None:
            for event in persisted_events or []:
                collected_events.append(event)

    return collected_elements, collected_events


def get_listen_element_record(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    preview_mode: bool,
    include_non_navigable: bool = False,
) -> LearnElementRecordDTO:
    progress_records = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .order_by(LearnProgressRecord.id.asc())
        .all()
    )
    progress_records = _dedupe_progress_records_by_block_position(progress_records)
    progress_record_bids = [
        pr.progress_record_bid for pr in progress_records if pr.progress_record_bid
    ]

    if progress_record_bids:
        rows, progress_bid_map = _query_element_rows(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bids=progress_record_bids,
        )
        collected_elements, collected_events = _merge_progress_elements(
            app,
            progress_records=progress_records,
            rows=rows,
            progress_bid_by_generated_block_bid=progress_bid_map,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            include_non_navigable=include_non_navigable,
        )
        if collected_elements:
            return LearnElementRecordDTO(
                elements=collected_elements,
                events=collected_events,
            )

    legacy_record = get_learn_record(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        preview_mode=preview_mode,
    )
    built_record = build_listen_elements_from_legacy_record(app, legacy_record)
    return LearnElementRecordDTO(
        elements=[
            _normalize_record_element(element) for element in built_record.elements
        ],
        events=built_record.events,
    )
