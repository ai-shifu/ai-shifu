from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Generator, Iterable

from flask import Flask

from flaskr.dao import db
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
from flaskr.service.learn.type_state_machine import TypeInput, TypeStateMachine

ELEMENT_TYPE_CODES = {
    ElementType.HTML: 201,
    ElementType.SVG: 202,
    ElementType.DIFF: 203,
    ElementType.IMG: 204,
    ElementType.INTERACTION: 205,
    ElementType.TABLES: 206,
    ElementType.CODE: 207,
    ElementType.LATEX: 208,
    ElementType.MD_IMG: 209,
    ElementType.MERMAID: 210,
    ElementType.TITLE: 211,
    ElementType.TEXT: 212,
    # Legacy codes kept for backfill compatibility
    ElementType._SANDBOX: 102,
    ElementType._PICTURE: 103,
    ElementType._VIDEO: 104,
}

VISUAL_KIND_TO_ELEMENT_TYPE = {
    "video": ElementType.HTML,
    "img": ElementType.IMG,
    "md_img": ElementType.MD_IMG,
    "svg": ElementType.SVG,
    "iframe": ElementType.HTML,
    "sandbox": ElementType.HTML,
    "html_table": ElementType.TABLES,
    "md_table": ElementType.TABLES,
    "fence": ElementType.CODE,
    "mermaid": ElementType.MERMAID,
    "latex": ElementType.LATEX,
    "title": ElementType.TITLE,
    "text": ElementType.TEXT,
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
        return {
            "progress_record_bid": self.progress_record_bid,
            "progress_record_id": self.progress_record_id,
            "shifu_bid": self.shifu_bid,
            "outline_item_bid": self.outline_item_bid,
            "user_bid": self.user_bid,
            "run_session_bid": self.run_session_bid,
            "generated_blocks_total": self.generated_blocks_total,
            "audio_records_total": self.audio_records_total,
            "duplicate_blocks_skipped": self.duplicate_blocks_skipped,
            "duplicate_audios_skipped": self.duplicate_audios_skipped,
            "orphan_audios_skipped": self.orphan_audios_skipped,
            "skipped_empty_blocks": self.skipped_empty_blocks,
            "existing_active_rows": self.existing_active_rows,
            "overwritten_rows": self.overwritten_rows,
            "inserted_rows": self.inserted_rows,
            "elements_built": self.elements_built,
            "skipped_existing": self.skipped_existing,
            "dry_run": self.dry_run,
            "error": self.error,
        }


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
        return {
            "scanned_progress_records": self.scanned_progress_records,
            "processed_progress_records": self.processed_progress_records,
            "skipped_existing_progress_records": self.skipped_existing_progress_records,
            "failed_progress_records": self.failed_progress_records,
            "inserted_rows": self.inserted_rows,
            "overwritten_rows": self.overwritten_rows,
            "duplicate_blocks_skipped": self.duplicate_blocks_skipped,
            "duplicate_audios_skipped": self.duplicate_audios_skipped,
            "orphan_audios_skipped": self.orphan_audios_skipped,
            "skipped_empty_blocks": self.skipped_empty_blocks,
            "results": [result.as_dict() for result in self.results],
        }


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
    return VISUAL_KIND_TO_ELEMENT_TYPE.get(normalized, ElementType.TEXT)


def _element_type_code(element_type: ElementType) -> int:
    return ELEMENT_TYPE_CODES[element_type]


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
    return ElementPayloadDTO(
        audio=audio,
        previous_visuals=visuals,
        diff_payload=diff_payload,
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
        audio_segments=json.dumps(element.audio_segments or [], ensure_ascii=False),
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


def _element_from_row(row: LearnGeneratedElement) -> ElementDTO:
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
    return ElementDTO(
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
        is_renderable=bool(getattr(row, "is_renderable", 1)),
        is_new=bool(getattr(row, "is_new", 1)),
        is_marker=bool(getattr(row, "is_marker", 0)),
        sequence_number=int(getattr(row, "sequence_number", 0) or 0),
        is_speakable=bool(getattr(row, "is_speakable", 0)),
        audio_url=str(getattr(row, "audio_url", "") or ""),
        audio_segments=audio_segments,
        is_navigable=int(row.is_navigable or 0),
        is_final=bool(row.is_final),
        content_text=row.content_text or "",
        payload=_deserialize_payload(row.payload or ""),
    )


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


def _event_from_row(row: LearnGeneratedElement) -> RunElementSSEMessageDTO:
    content: (
        str
        | ElementDTO
        | VariableUpdateDTO
        | OutlineItemUpdateDTO
        | AudioSegmentDTO
        | AudioCompleteDTO
    )
    if row.event_type == "element":
        content = _element_from_row(row)
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


@dataclass
class BlockMeta:
    progress_record_bid: str = ""
    role: str = "teacher"


@dataclass
class BlockState:
    generated_block_bid: str
    raw_content: str = ""
    audio_by_position: dict[int, ElementAudioDTO] = field(default_factory=dict)
    fallback_element_bid: str | None = None
    latest_av_contract: dict[str, Any] | None = None


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

    def _next_seq(self) -> int:
        self._run_event_seq += 1
        return self._run_event_seq

    def _next_sequence_number(self) -> int:
        self._sequence_number += 1
        return self._sequence_number

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
            audio_segments=json.dumps(audio_segments or [], ensure_ascii=False),
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
        seq = self._next_seq()
        # Assign sequence_number (element-level counter)
        element.sequence_number = self._next_sequence_number()
        element.run_session_bid = self.run_session_bid
        element.run_event_seq = seq
        # Feed state machine
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.CONTENT_START, is_new=element.is_new)
        # Track current element for audio association
        self._current_element_bid = element.element_bid
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
        return RunElementSSEMessageDTO(
            type="element",
            event_type="element",
            generated_block_bid=element.generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            content=element,
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
            content=content,
        )

    def make_ephemeral_message(
        self,
        *,
        event_type: str,
        content: str = "",
        generated_block_bid: str = "",
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq()
        return RunElementSSEMessageDTO(
            type=event_type,
            event_type=event_type,
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            content=content,
        )

    def _build_fallback_element(self, state: BlockState, role: str) -> ElementDTO:
        if not state.fallback_element_bid:
            state.fallback_element_bid = (
                f"el_{state.generated_block_bid or uuid.uuid4().hex}"
            )
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
            is_navigable=1,
            is_final=False,
            content_text=state.raw_content,
            payload=ElementPayloadDTO(audio=None, previous_visuals=[]),
        )

    def _retire_fallback_element(self, state: BlockState) -> None:
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

    def _append_audio_segment_to_element(
        self, element_bid: str, segment_data: dict
    ) -> None:
        """Append an audio segment entry to the element's audio_segments JSON."""
        row = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == self.run_session_bid,
                LearnGeneratedElement.element_bid == element_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(LearnGeneratedElement.id.desc())
            .first()
        )
        if row is None:
            return
        try:
            segments = json.loads(row.audio_segments or "[]")
            if not isinstance(segments, list):
                segments = []
        except Exception:
            segments = []
        segments.append(segment_data)
        row.audio_segments = json.dumps(segments, ensure_ascii=False)
        db.session.flush()

    def _backfill_audio_url(self, element_bid: str, audio_url: str) -> None:
        """Set audio_url on the element row."""
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.run_session_bid == self.run_session_bid,
            LearnGeneratedElement.element_bid == element_bid,
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ).update(
            {"audio_url": audio_url, "is_speakable": 1},
            synchronize_session=False,
        )
        db.session.flush()

    def _handle_content(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
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
        state.audio_by_position[int(getattr(content, "position", 0) or 0)] = (
            _make_audio_payload(content)
        )
        # Backfill audio_url on the current element
        if self._current_element_bid and content.audio_url:
            self._backfill_audio_url(self._current_element_bid, content.audio_url)
        # Feed state machine
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.AUDIO_COMPLETE)
        yield self._non_element_message(
            event_type=GeneratedType.AUDIO_COMPLETE.value,
            content=content,
            generated_block_bid=generated_block_bid,
        )

    def _handle_audio_segment(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        content = event.content
        if isinstance(content, AudioSegmentDTO) and isinstance(
            content.av_contract, dict
        ):
            state = self._ensure_block_state(generated_block_bid)
            state.latest_av_contract = content.av_contract
        if isinstance(content, AudioSegmentDTO):
            state = self._ensure_block_state(generated_block_bid)
            state.audio_by_position[int(getattr(content, "position", 0) or 0)] = (
                ElementAudioDTO(
                    audio_url="",
                    audio_bid="",
                    duration_ms=int(getattr(content, "duration_ms", 0) or 0),
                    position=int(getattr(content, "position", 0) or 0),
                )
            )
            # Append audio segment to current element's audio_segments
            if self._current_element_bid:
                segment_data = {
                    "position": int(getattr(content, "position", 0) or 0),
                    "segment_index": int(content.segment_index or 0),
                    "duration_ms": int(content.duration_ms or 0),
                    "is_final": content.is_final,
                }
                self._append_audio_segment_to_element(
                    self._current_element_bid, segment_data
                )
        # Feed state machine
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.AUDIO_SEGMENT)
        yield self._non_element_message(
            event_type=GeneratedType.AUDIO_SEGMENT.value,
            content=event.content,
            generated_block_bid=generated_block_bid,
        )

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
        if (
            isinstance(state.latest_av_contract, dict)
            and (state.raw_content or "").strip()
        ):
            visual_segments, _ = build_visual_segments_for_block(
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
                            segment_id=uuid.uuid4().hex,
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
            self._retire_fallback_element(state)
            aggregated_text = _aggregate_segment_text(
                state.raw_content,
                state.latest_av_contract,
                {seg.audio_position: seg.segment_id for seg in visual_segments},
            )
            for seg in visual_segments:
                payload = _element_payload_from_segment(
                    seg,
                    state.raw_content,
                    state.audio_by_position.get(seg.audio_position),
                )
                element_type = _element_type_for_visual_kind(seg.visual_kind or "")
                element = ElementDTO(
                    event_type="element",
                    element_bid=seg.segment_id,
                    generated_block_bid=generated_block_bid,
                    element_index=seg.element_index,
                    role=meta.role,
                    element_type=element_type,
                    element_type_code=_element_type_code(element_type),
                    change_type=ElementChangeType.RENDER,
                    is_navigable=1,
                    is_final=True,
                    content_text=aggregated_text.get(seg.segment_id, ""),
                    payload=payload,
                )
                self._max_element_index = max(
                    self._max_element_index, element.element_index
                )
                yield self._element_message(element)
        elif state.fallback_element_bid:
            element = ElementDTO(
                event_type="element",
                element_bid=state.fallback_element_bid,
                generated_block_bid=generated_block_bid,
                element_index=max(self._max_element_index, 0),
                role=meta.role,
                element_type=ElementType.TEXT,
                element_type_code=_element_type_code(ElementType.TEXT),
                change_type=ElementChangeType.RENDER,
                is_navigable=1,
                is_final=True,
                content_text=state.raw_content,
                payload=ElementPayloadDTO(audio=None, previous_visuals=[]),
            )
            yield self._element_message(element)
        self._block_states.pop(generated_block_bid, None)

    def _handle_interaction(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        meta = self._load_block_meta(generated_block_bid)
        self._max_element_index += 1
        element = ElementDTO(
            event_type="element",
            element_bid=f"el_{generated_block_bid or uuid.uuid4().hex}",
            generated_block_bid=generated_block_bid,
            element_index=max(self._max_element_index, 0),
            role=meta.role,
            element_type=ElementType.INTERACTION,
            element_type_code=_element_type_code(ElementType.INTERACTION),
            change_type=ElementChangeType.RENDER,
            is_navigable=0,
            is_final=True,
            content_text=str(event.content or ""),
            payload=ElementPayloadDTO(audio=None, previous_visuals=[]),
        )
        yield self._element_message(element)

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
            if event.type == GeneratedType.INTERACTION:
                yield from self._handle_interaction(event)
                continue
            if event.type == GeneratedType.BREAK:
                yield from self._finalize_block(event.generated_block_bid or "")
                if not self._state_machine.is_terminated:
                    self._state_machine.feed(TypeInput.BLOCK_BREAK)
                self._current_element_bid = None
                yield self._non_element_message(
                    event_type=GeneratedType.BREAK.value,
                    content="",
                    generated_block_bid=event.generated_block_bid or "",
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
    generated_block_bid: str,
    content: str,
    *,
    role: str,
    element_index: int,
) -> ElementDTO:
    return ElementDTO(
        event_type="element",
        element_bid=f"el_{generated_block_bid or uuid.uuid4().hex}",
        generated_block_bid=generated_block_bid,
        element_index=element_index,
        role=role,
        element_type=ElementType.INTERACTION,
        element_type_code=_element_type_code(ElementType.INTERACTION),
        change_type=ElementChangeType.RENDER,
        is_navigable=0,
        is_final=True,
        content_text=content or "",
        payload=ElementPayloadDTO(audio=None, previous_visuals=[]),
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
                    record.generated_block_bid,
                    record.content,
                    role="ui",
                    element_index=max_index,
                )
            )
            continue

        role = "student" if block_type == BlockType.ASK else "teacher"
        visual_segments: list[VisualSegment] = []
        audio_by_segment_id: dict[str, ElementAudioDTO] = {}
        audio_by_position: dict[int, ElementAudioDTO] = {}
        for audio in record.audios or []:
            audio_payload = _make_audio_payload(audio)
            audio_by_position[int(getattr(audio, "position", 0) or 0)] = audio_payload

        if isinstance(record.av_contract, dict) and (record.content or "").strip():
            visual_segments, pos_to_seg_id = build_visual_segments_for_block(
                raw_content=record.content or "",
                generated_block_bid=record.generated_block_bid,
                av_contract=record.av_contract,
                element_index_offset=max_index + 1,
            )
            for position, segment_id in pos_to_seg_id.items():
                audio_payload = audio_by_position.get(int(position or 0))
                if audio_payload is not None:
                    audio_by_segment_id.setdefault(segment_id, audio_payload)

        if visual_segments:
            aggregated_text = _aggregate_segment_text(
                record.content or "",
                record.av_contract if isinstance(record.av_contract, dict) else None,
                {seg.audio_position: seg.segment_id for seg in visual_segments},
            )
            for seg in visual_segments:
                audio = audio_by_segment_id.get(
                    seg.segment_id
                ) or audio_by_position.get(seg.audio_position)
                payload = ElementPayloadDTO(
                    audio=audio,
                    previous_visuals=_visuals_from_segment(seg, record.content or ""),
                )
                element_type = _element_type_for_visual_kind(seg.visual_kind or "")
                element = ElementDTO(
                    event_type="element",
                    element_bid=seg.segment_id,
                    generated_block_bid=record.generated_block_bid,
                    element_index=seg.element_index,
                    role=role,
                    element_type=element_type,
                    element_type_code=_element_type_code(element_type),
                    change_type=ElementChangeType.RENDER,
                    is_navigable=1,
                    is_final=True,
                    content_text=aggregated_text.get(seg.segment_id, ""),
                    payload=payload,
                )
                max_index = max(max_index, element.element_index)
                elements.append(element)
            continue

        max_index += 1
        elements.append(
            ElementDTO(
                event_type="element",
                element_bid=f"el_{record.generated_block_bid or uuid.uuid4().hex}",
                generated_block_bid=record.generated_block_bid,
                element_index=max_index,
                role=role,
                element_type=ElementType.TEXT,
                element_type_code=_element_type_code(ElementType.TEXT),
                change_type=ElementChangeType.RENDER,
                is_navigable=1,
                is_final=True,
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


def get_listen_element_record(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    preview_mode: bool,
    include_non_navigable: bool = False,
) -> LearnElementRecordDTO:
    progress_record = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
        )
        .order_by(LearnProgressRecord.id.desc())
        .first()
    )
    if progress_record:
        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.user_bid == user_bid,
                LearnGeneratedElement.shifu_bid == shifu_bid,
                LearnGeneratedElement.outline_item_bid == outline_bid,
                LearnGeneratedElement.progress_record_bid
                == progress_record.progress_record_bid,
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
        if rows:
            latest_by_bid: "OrderedDict[str, ElementDTO]" = OrderedDict()
            for row in rows:
                if row.event_type != "element" or not row.element_bid:
                    continue
                dto = _element_from_row(row)
                # For is_new=false elements, apply to target if found
                if not dto.is_new and dto.target_element_bid:
                    if dto.target_element_bid in latest_by_bid:
                        target = latest_by_bid[dto.target_element_bid]
                        target.content_text = dto.content_text
                        target.payload = dto.payload
                        target.is_final = dto.is_final
                        continue
                latest_by_bid[row.element_bid] = dto
            events = None
            if include_non_navigable:
                events = [_event_from_row(row) for row in rows]
            return LearnElementRecordDTO(
                elements=list(latest_by_bid.values()),
                events=events,
            )

    legacy_record = get_learn_record(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        preview_mode=preview_mode,
    )
    return build_listen_elements_from_legacy_record(app, legacy_record)
