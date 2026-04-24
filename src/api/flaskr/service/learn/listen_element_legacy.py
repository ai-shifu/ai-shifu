from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.learn.learn_dtos import (
    BlockType,
    ElementAudioDTO,
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    LearnElementRecordDTO,
)
from flaskr.service.learn.legacy_record_builder import (
    LegacyLearnRecord,
    build_legacy_record_for_progress,
)
from flaskr.service.learn.listen_element_factory import (
    _build_final_elements_for_av_contract,
    _interaction_element_from_record,
)
from flaskr.service.learn.listen_element_history import (
    get_final_elements_for_generated_block,
)
from flaskr.service.learn.listen_element_matching import (
    get_speakable_text_elements,
)
from flaskr.service.learn.listen_element_payloads import _make_audio_payload
from flaskr.service.learn.listen_element_rows import _serialize_element_row
from flaskr.service.learn.listen_element_types import (
    _default_is_speakable,
    _element_type_code,
    _new_element_bid,
)
from flaskr.service.learn.listen_slide_builder import (
    VisualSegment,
    build_visual_segments_for_block,
)
from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
from flaskr.service.tts.pipeline import build_av_segmentation_contract


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


def _build_legacy_record_for_progress(
    progress_record: LearnProgressRecord,
    stats: LearnElementsBackfillStats,
) -> LegacyLearnRecord:
    return build_legacy_record_for_progress(
        progress_record,
        include_like_status=False,
        dedupe_blocks_by_bid=True,
        dedupe_audio_by_block_position=True,
        skip_empty_content=True,
        stats=stats,
    )


def build_listen_elements_from_legacy_record(
    app: Flask,
    legacy_record: LegacyLearnRecord,
    *,
    prefer_persisted_final_elements: bool = True,
) -> LearnElementRecordDTO:
    elements: list[ElementDTO] = []
    max_index = -1
    last_anchor_element_bid: str = ""

    def _element_type_for_block(bt: BlockType) -> ElementType:
        if bt == BlockType.ASK:
            return ElementType.ASK
        if bt == BlockType.ANSWER:
            return ElementType.ANSWER
        return ElementType.TEXT

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

        is_follow_up = block_type in (BlockType.ASK, BlockType.ANSWER)

        if is_follow_up and not last_anchor_element_bid:
            # Follow-up blocks need a main-timeline anchor so the frontend can
            # attach them to the ask drawer. If we don't have one yet, drop the
            # record rather than rendering it as stray main-timeline text.
            continue

        role = "student" if block_type == BlockType.ASK else "teacher"

        if is_follow_up:
            follow_up_element_type = _element_type_for_block(block_type)
            max_index += 1
            elements.append(
                ElementDTO(
                    event_type="element",
                    element_bid=_new_element_bid(app),
                    generated_block_bid=record.generated_block_bid,
                    element_index=max_index,
                    role=role,
                    element_type=follow_up_element_type,
                    element_type_code=_element_type_code(follow_up_element_type),
                    change_type=ElementChangeType.RENDER,
                    is_renderable=False,
                    is_navigable=0,
                    is_final=True,
                    is_speakable=False,
                    audio_url="",
                    audio_segments=[],
                    content_text=record.content or "",
                    payload=ElementPayloadDTO(
                        anchor_element_bid=last_anchor_element_bid,
                        previous_visuals=[],
                    ),
                )
            )
            continue

        visual_segments: list[VisualSegment] = []
        audio_by_position: dict[int, ElementAudioDTO] = {}
        pos_to_seg_id: dict[int, str] = {}
        for audio in record.audios or []:
            audio_payload = _make_audio_payload(audio)
            audio_by_position[int(getattr(audio, "position", 0) or 0)] = audio_payload

        persisted_final_elements: list[ElementDTO] = []
        if prefer_persisted_final_elements and record.generated_block_bid:
            with app.app_context():
                persisted_final_elements = get_final_elements_for_generated_block(
                    generated_block_bid=record.generated_block_bid,
                )
        if persisted_final_elements:
            text_elements = get_speakable_text_elements(persisted_final_elements)
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
                if persisted_final_elements:
                    last_anchor_element_bid = (
                        persisted_final_elements[-1].element_bid
                        or last_anchor_element_bid
                    )
                continue

        av_contract = None
        if (record.content or "").strip():
            av_contract = build_av_segmentation_contract(
                record.content or "",
                record.generated_block_bid,
            )

        if isinstance(av_contract, dict):
            visual_segments, pos_to_seg_id = build_visual_segments_for_block(
                app=app,
                raw_content=record.content or "",
                generated_block_bid=record.generated_block_bid,
                av_contract=av_contract,
                element_index_offset=max_index + 1,
            )

        if visual_segments:
            built_elements = _build_final_elements_for_av_contract(
                app=app,
                generated_block_bid=record.generated_block_bid,
                role=role,
                raw_content=record.content or "",
                av_contract=av_contract if isinstance(av_contract, dict) else None,
                visual_segments=visual_segments,
                audio_by_position=audio_by_position,
                audio_segments_by_position={},
                position_to_segment_id=pos_to_seg_id,
                element_index_offset=max_index + 1,
            )
            for element in built_elements:
                max_index = max(max_index, element.element_index)
                elements.append(element)
            if built_elements:
                last_anchor_element_bid = (
                    built_elements[-1].element_bid or last_anchor_element_bid
                )
            continue

        max_index += 1
        fallback_element = ElementDTO(
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
        elements.append(fallback_element)
        last_anchor_element_bid = (
            fallback_element.element_bid or last_anchor_element_bid
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

    if stats.existing_active_rows and not dry_run:
        stats.overwritten_rows = existing_rows_query.update(
            {
                "status": 0,
            },
            synchronize_session=False,
        )
        db.session.flush()
        db.session.expire_all()

    legacy_record = _build_legacy_record_for_progress(progress_record, stats)
    built_record = build_listen_elements_from_legacy_record(
        app,
        legacy_record,
        prefer_persisted_final_elements=not (
            overwrite and dry_run and stats.existing_active_rows
        ),
    )
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

    for run_event_seq, element in enumerate(built_record.elements, start=1):
        element.sequence_number = run_event_seq
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
