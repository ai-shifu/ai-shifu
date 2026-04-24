from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

from sqlalchemy import and_, or_

from flaskr.service.learn.learn_dtos import (
    ElementAudioDTO,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    GeneratedType,
    LearnElementRecordDTO,
    RunElementSSEMessageDTO,
)
from flaskr.service.learn.legacy_record_builder import (
    LegacyLearnRecord,
    build_legacy_record_for_progress,
)
from flaskr.service.learn.listen_element_rows import (
    _element_from_row,
    _event_from_row,
    _normalize_record_element,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED, LearnGeneratedAudio
from flaskr.service.tts.subtitle_utils import normalize_subtitle_cues


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


def _load_progress_bid_by_generated_block_bid(
    progress_record_bids: list[str],
) -> tuple[dict[str, str], dict[str, list[LearnGeneratedBlock]]]:
    if not progress_record_bids:
        return {}, {}

    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid.in_(progress_record_bids),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        )
        .order_by(
            LearnGeneratedBlock.progress_record_bid.asc(),
            LearnGeneratedBlock.position.asc(),
            LearnGeneratedBlock.id.asc(),
        )
        .all()
    )
    progress_bid_by_generated_block_bid: dict[str, str] = {}
    active_blocks_by_progress_bid: dict[str, list[LearnGeneratedBlock]] = {}
    for block in blocks:
        generated_block_bid = block.generated_block_bid or ""
        progress_record_bid = block.progress_record_bid or ""
        if not progress_record_bid:
            continue
        active_blocks_by_progress_bid.setdefault(progress_record_bid, []).append(block)
        if generated_block_bid:
            progress_bid_by_generated_block_bid[generated_block_bid] = (
                progress_record_bid
            )
    return progress_bid_by_generated_block_bid, active_blocks_by_progress_bid


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
    latest_by_bid: OrderedDict[str, ElementDTO] = OrderedDict()
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

    final_elements = _enrich_elements_with_persisted_audio(
        [_normalize_record_element(element) for element in latest_by_bid.values()]
    )
    return (
        final_elements,
        events,
    )


def _load_latest_audio_by_block_position(
    generated_block_bids: list[str],
) -> dict[tuple[str, int], LearnGeneratedAudio]:
    normalized_block_bids = [str(block_bid or "") for block_bid in generated_block_bids]
    normalized_block_bids = [
        block_bid for block_bid in normalized_block_bids if block_bid
    ]
    if not normalized_block_bids:
        return {}

    audio_records = (
        LearnGeneratedAudio.query.filter(
            LearnGeneratedAudio.generated_block_bid.in_(normalized_block_bids),
            LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
            LearnGeneratedAudio.deleted == 0,
        )
        .order_by(
            LearnGeneratedAudio.generated_block_bid.asc(),
            LearnGeneratedAudio.position.asc(),
            LearnGeneratedAudio.id.desc(),
        )
        .all()
    )
    latest_by_block_position: dict[tuple[str, int], LearnGeneratedAudio] = {}
    for audio_record in audio_records:
        block_bid = str(audio_record.generated_block_bid or "")
        position = int(getattr(audio_record, "position", 0) or 0)
        key = (block_bid, position)
        if key in latest_by_block_position:
            continue
        if not audio_record.oss_url:
            continue
        latest_by_block_position[key] = audio_record
    return latest_by_block_position


def _enrich_elements_with_persisted_audio(
    elements: list[ElementDTO],
) -> list[ElementDTO]:
    generated_block_bids = {
        str(element.generated_block_bid or "")
        for element in elements
        if element.generated_block_bid
    }
    latest_audio_by_key = _load_latest_audio_by_block_position(
        list(generated_block_bids)
    )
    if not latest_audio_by_key:
        return elements

    available_positions_by_block: dict[str, list[int]] = {}
    for block_bid, position in latest_audio_by_key.keys():
        available_positions_by_block.setdefault(block_bid, []).append(position)

    for element in elements:
        block_bid = str(element.generated_block_bid or "")
        if not block_bid:
            continue

        payload = element.payload or ElementPayloadDTO()
        payload_audio = payload.audio
        should_enrich = bool(
            payload_audio is not None or element.is_speakable or element.audio_url
        )
        if not should_enrich:
            continue

        resolved_position: int | None = None
        if payload_audio is not None:
            resolved_position = int(getattr(payload_audio, "position", 0) or 0)
        else:
            available_positions = available_positions_by_block.get(block_bid, [])
            if len(available_positions) == 1:
                resolved_position = int(available_positions[0])
            elif 0 in available_positions and (
                element.audio_url or element.is_speakable
            ):
                resolved_position = 0

        if resolved_position is None:
            continue

        audio_record = latest_audio_by_key.get((block_bid, resolved_position))
        if audio_record is None:
            continue

        payload.audio = ElementAudioDTO(
            audio_url=audio_record.oss_url or "",
            audio_bid=audio_record.audio_bid or "",
            duration_ms=int(audio_record.duration_ms or 0),
            position=resolved_position,
            subtitle_cues=normalize_subtitle_cues(
                getattr(audio_record, "subtitle_cues", None)
            ),
        )
        element.payload = payload
        element.audio_url = audio_record.oss_url or element.audio_url

    return elements


def _query_element_rows(
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bids: list[str],
) -> tuple[
    list[LearnGeneratedElement],
    dict[str, str],
    dict[str, list[LearnGeneratedBlock]],
]:
    (
        progress_bid_by_generated_block_bid,
        active_blocks_by_progress_bid,
    ) = _load_progress_bid_by_generated_block_bid(progress_record_bids)
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
    return rows, progress_bid_by_generated_block_bid, active_blocks_by_progress_bid


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


def _dedupe_progress_records_by_block_position(
    progress_records: list[LearnProgressRecord],
) -> list[LearnProgressRecord]:
    latest_by_key: dict[tuple[str, str], LearnProgressRecord] = {}
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


def _group_elements_by_generated_block_bid(
    elements: list[ElementDTO],
) -> OrderedDict[str, list[ElementDTO]]:
    grouped: OrderedDict[str, list[ElementDTO]] = OrderedDict()
    for index, element in enumerate(elements):
        group_key = element.generated_block_bid or f"__ungrouped__:{index}"
        grouped.setdefault(group_key, []).append(element)
    return grouped


def _merge_follow_up_elements_after_anchor(
    elements: list[ElementDTO],
) -> list[ElementDTO]:
    follow_up_by_anchor_bid: dict[str, list[ElementDTO]] = {}
    ordered_non_follow_up_elements: list[ElementDTO] = []

    for element in elements:
        payload = element.payload or ElementPayloadDTO()
        anchor_element_bid = (payload.anchor_element_bid or "").strip()
        if (
            element.element_type in {ElementType.ASK, ElementType.ANSWER}
            and anchor_element_bid
        ):
            follow_up_by_anchor_bid.setdefault(anchor_element_bid, []).append(element)
            continue
        ordered_non_follow_up_elements.append(element)

    if not follow_up_by_anchor_bid:
        return elements

    merged_elements: list[ElementDTO] = []
    appended_element_ids: set[int] = set()

    for element in ordered_non_follow_up_elements:
        merged_elements.append(element)
        appended_element_ids.add(id(element))
        anchor_element_bid = element.element_bid or ""
        for follow_up_element in follow_up_by_anchor_bid.get(anchor_element_bid, []):
            merged_elements.append(follow_up_element)
            appended_element_ids.add(id(follow_up_element))

    for element in elements:
        if id(element) in appended_element_ids:
            continue
        merged_elements.append(element)

    return merged_elements


def _attach_follow_up_history_to_anchor_payload(
    elements: list[ElementDTO],
) -> list[ElementDTO]:
    ask_history_by_anchor_bid: dict[str, list[dict[str, Any]]] = {}

    for element in elements:
        payload = element.payload or ElementPayloadDTO()
        anchor_element_bid = (payload.anchor_element_bid or "").strip()
        if (
            element.element_type not in {ElementType.ASK, ElementType.ANSWER}
            or not anchor_element_bid
        ):
            continue

        ask_history_by_anchor_bid.setdefault(anchor_element_bid, []).append(
            {
                "role": (
                    "student" if element.element_type == ElementType.ASK else "teacher"
                ),
                "content": element.content_text or "",
                "generated_block_bid": element.generated_block_bid or "",
            }
        )

    if not ask_history_by_anchor_bid:
        return elements

    for element in elements:
        anchor_asks = ask_history_by_anchor_bid.get(element.element_bid or "")
        if not anchor_asks:
            continue
        payload = element.payload or ElementPayloadDTO()
        payload.asks = anchor_asks
        element.payload = payload

    return elements


def _merge_progress_elements(
    *,
    progress_records: list[LearnProgressRecord],
    rows: list[LearnGeneratedElement],
    progress_bid_by_generated_block_bid: dict[str, str],
    active_blocks_by_progress_bid: dict[str, list[LearnGeneratedBlock]],
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    include_non_navigable: bool,
    build_record_from_legacy: Callable[[LegacyLearnRecord], LearnElementRecordDTO],
    build_legacy_record_for_progress_fn: Callable[..., LegacyLearnRecord],
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
        active_blocks = active_blocks_by_progress_bid.get(str(progress_bid), [])
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

        legacy_record = build_legacy_record_for_progress_fn(
            progress_record,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            include_like_status=False,
            dedupe_blocks_by_bid=True,
            dedupe_audio_by_block_position=True,
            skip_empty_content=True,
        )
        block_order_by_generated_block_bid = {
            str(block.generated_block_bid or ""): index
            for index, block in enumerate(active_blocks)
            if str(block.generated_block_bid or "")
        }
        next_block_order = len(block_order_by_generated_block_bid)
        for record in legacy_record.records:
            record_block_bid = str(record.generated_block_bid or "")
            if (
                record_block_bid
                and record_block_bid not in block_order_by_generated_block_bid
            ):
                block_order_by_generated_block_bid[record_block_bid] = next_block_order
                next_block_order += 1
        legacy_records = [
            record
            for record in legacy_record.records
            if (record.generated_block_bid or "") not in persisted_block_bids
        ]
        legacy_elements: list[ElementDTO] = []
        if legacy_records:
            built_record = build_record_from_legacy(
                LegacyLearnRecord(records=legacy_records)
            )
            legacy_elements = [
                _normalize_record_element(element) for element in built_record.elements
            ]
            if include_non_navigable and collected_events is not None:
                for event in built_record.events or []:
                    collected_events.append(event)

        persisted_groups = _group_elements_by_generated_block_bid(
            list(persisted_elements)
        )
        legacy_groups = _group_elements_by_generated_block_bid(legacy_elements)
        source_group_order: dict[str, int] = {}
        for group_key in list(persisted_groups.keys()) + list(legacy_groups.keys()):
            if group_key not in source_group_order:
                source_group_order[group_key] = len(source_group_order)

        merged_elements: list[ElementDTO] = []
        ordered_group_keys = list(source_group_order.keys())
        ordered_group_keys.sort(
            key=lambda group_key: (
                0 if group_key in block_order_by_generated_block_bid else 1,
                block_order_by_generated_block_bid.get(group_key, 0),
                source_group_order[group_key],
            )
        )
        for group_key in ordered_group_keys:
            merged_elements.extend(persisted_groups.get(group_key, []))
            merged_elements.extend(legacy_groups.get(group_key, []))
        merged_elements = _attach_follow_up_history_to_anchor_payload(merged_elements)
        collected_elements.extend(
            _merge_follow_up_elements_after_anchor(merged_elements)
        )
        if include_non_navigable and collected_events is not None:
            for event in persisted_events or []:
                collected_events.append(event)

    return collected_elements, collected_events


def get_listen_element_record(
    *,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    include_non_navigable: bool = False,
    build_record_from_legacy: Callable[[LegacyLearnRecord], LearnElementRecordDTO],
    load_fallback_record: Callable[[], LegacyLearnRecord],
    build_legacy_record_for_progress_fn: Callable[
        ..., LegacyLearnRecord
    ] = build_legacy_record_for_progress,
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
        rows, progress_bid_map, active_blocks_by_progress_bid = _query_element_rows(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bids=progress_record_bids,
        )
        collected_elements, collected_events = _merge_progress_elements(
            progress_records=progress_records,
            rows=rows,
            progress_bid_by_generated_block_bid=progress_bid_map,
            active_blocks_by_progress_bid=active_blocks_by_progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            include_non_navigable=include_non_navigable,
            build_record_from_legacy=build_record_from_legacy,
            build_legacy_record_for_progress_fn=build_legacy_record_for_progress_fn,
        )
        if collected_elements:
            return LearnElementRecordDTO(
                elements=collected_elements,
                events=collected_events,
            )

    built_record = build_record_from_legacy(load_fallback_record())
    return LearnElementRecordDTO(
        elements=[
            _normalize_record_element(element) for element in built_record.elements
        ],
        events=built_record.events,
    )
