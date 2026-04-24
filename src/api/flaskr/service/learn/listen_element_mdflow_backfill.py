from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from flask import Flask

try:
    from markdown_flow import format_content
except ImportError:
    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    @dataclass
    class _FormattedContentPart:
        content: str
        type: str
        number: int

    _VISUAL_KIND_ALIASES = {
        "iframe": "html",
        "video": "html",
        "sandbox": "html",
        "html_table": "html",
        "md_table": "tables",
        "fence": "code",
    }

    def format_content(content: str) -> list[_FormattedContentPart]:
        """
        Compatibility formatter for older markdown_flow builds that do not
        export `format_content`.

        The backfill only needs stable ordered stream parts so the listen
        element adapter can reconstruct final rows. We reuse the shared AV
        segmentation contract to recover text/visual boundaries and normalize
        visual kinds to element protocol types.
        """

        raw_content = str(content or "")
        if not raw_content.strip():
            return []

        contract = build_av_segmentation_contract(raw_content)
        items: list[tuple[int, int, str]] = []

        for segment in contract.get("speakable_segments") or []:
            span = segment.get("source_span") or []
            if len(span) != 2:
                continue
            start, end = int(span[0]), int(span[1])
            if end <= start:
                continue
            items.append((start, end, "text"))

        for boundary in contract.get("visual_boundaries") or []:
            span = boundary.get("source_span") or []
            if len(span) != 2:
                continue
            start, end = int(span[0]), int(span[1])
            if end <= start:
                continue
            kind = str(boundary.get("kind", "") or "")
            items.append((start, end, _VISUAL_KIND_ALIASES.get(kind, kind)))

        if not items:
            return [_FormattedContentPart(content=raw_content, type="text", number=0)]

        items.sort(key=lambda item: (item[0], item[1]))
        return [
            _FormattedContentPart(
                content=raw_content[start:end],
                type=item_type or "text",
                number=index,
            )
            for index, (start, end, item_type) in enumerate(items)
        ]


from flaskr.dao import db
from flaskr.service.learn.const import ROLE_TEACHER
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)


SUPPORTED_BLOCK_TYPES = {
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDANSWER_VALUE,
}
FOLLOW_UP_ELEMENT_TYPES = {
    ElementType.ASK.value,
    ElementType.ANSWER.value,
}
NON_FOLLOW_UP_ANCHOR_TYPES = {
    ElementType.HTML.value,
    ElementType.SVG.value,
    ElementType.DIFF.value,
    ElementType.IMG.value,
    ElementType.TABLES.value,
    ElementType.CODE.value,
    ElementType.LATEX.value,
    ElementType.MD_IMG.value,
    ElementType.MERMAID.value,
    ElementType.TITLE.value,
    ElementType.TEXT.value,
}


@dataclass
class MdflowElementBackfillStats:
    progress_record_bid: str
    progress_record_id: int = 0
    shifu_bid: str = ""
    outline_item_bid: str = ""
    user_bid: str = ""
    run_session_bid: str = ""
    processed_block_groups: int = 0
    inserted_element_rows: int = 0
    overwritten_rows: int = 0
    skipped_existing_groups: int = 0
    skipped_empty_blocks: int = 0
    skipped_orphan_follow_ups: int = 0
    skipped_anchorless_follow_ups: int = 0
    duplicate_blocks_skipped: int = 0
    dry_run: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MdflowElementBackfillBatchStats:
    processed_progress_records: int = 0
    processed_block_groups: int = 0
    inserted_element_rows: int = 0
    overwritten_rows: int = 0
    skipped_existing_groups: int = 0
    skipped_empty_blocks: int = 0
    skipped_orphan_follow_ups: int = 0
    skipped_anchorless_follow_ups: int = 0
    duplicate_blocks_skipped: int = 0
    dry_run: bool = False
    progress_results: list[dict[str, Any]] = field(default_factory=list)
    failed_progress_records: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_progress_record(progress_record_bid: str) -> LearnProgressRecord:
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
    return progress_record


def _load_progress_records(
    *,
    progress_record_bids: list[str] | None,
    after_id: int,
    limit: int,
) -> list[LearnProgressRecord]:
    if progress_record_bids:
        rows = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.progress_record_bid.in_(progress_record_bids),
                LearnProgressRecord.deleted == 0,
            )
            .order_by(LearnProgressRecord.id.asc())
            .all()
        )
        latest_by_bid: dict[str, LearnProgressRecord] = {}
        for row in rows:
            latest_by_bid[row.progress_record_bid or ""] = row
        return sorted(
            latest_by_bid.values(),
            key=lambda item: int(item.id or 0),
        )

    return (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.id > int(after_id or 0),
        )
        .order_by(LearnProgressRecord.id.asc())
        .limit(max(int(limit or 0), 0))
        .all()
    )


def _load_deduped_blocks(
    progress_record_bid: str,
) -> tuple[list[LearnGeneratedBlock], int]:
    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid == progress_record_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type.in_(list(SUPPORTED_BLOCK_TYPES)),
        )
        .order_by(LearnGeneratedBlock.position.asc(), LearnGeneratedBlock.id.asc())
        .all()
    )
    latest_by_bid: dict[str, LearnGeneratedBlock] = {}
    duplicate_count = 0
    for block in blocks:
        block_bid = str(block.generated_block_bid or "")
        if not block_bid:
            continue
        if block_bid in latest_by_bid:
            duplicate_count += 1
        latest_by_bid[block_bid] = block
    deduped = sorted(
        latest_by_bid.values(),
        key=lambda item: (int(item.position or 0), int(item.id or 0)),
    )
    return deduped, duplicate_count


def _make_adapter(
    app: Flask,
    *,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    run_session_bid: str,
):
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter

    return ListenElementRunAdapter(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        run_session_bid=run_session_bid,
    )


def _iter_active_group_rows(
    progress_record_bid: str,
    generated_block_bid: str,
):
    return LearnGeneratedElement.query.filter(
        LearnGeneratedElement.progress_record_bid == progress_record_bid,
        LearnGeneratedElement.generated_block_bid == generated_block_bid,
        LearnGeneratedElement.event_type == "element",
        LearnGeneratedElement.deleted == 0,
        LearnGeneratedElement.status == 1,
    )


def _count_active_group_rows(
    progress_record_bid: str,
    generated_block_bid: str,
) -> int:
    return _iter_active_group_rows(progress_record_bid, generated_block_bid).count()


def _retire_active_group_rows(
    progress_record_bid: str,
    generated_block_bid: str,
) -> int:
    updated = _iter_active_group_rows(progress_record_bid, generated_block_bid).update(
        {"status": 0},
        synchronize_session=False,
    )
    db.session.flush()
    return int(updated or 0)


def _prune_current_run_inactive_rows(
    *,
    run_session_bid: str,
    generated_block_bid: str,
) -> None:
    LearnGeneratedElement.query.filter(
        LearnGeneratedElement.run_session_bid == run_session_bid,
        LearnGeneratedElement.generated_block_bid == generated_block_bid,
        LearnGeneratedElement.event_type == "element",
        LearnGeneratedElement.deleted == 0,
        LearnGeneratedElement.status == 0,
    ).delete(synchronize_session=False)
    db.session.flush()


def _count_current_run_active_rows(
    *,
    run_session_bid: str,
    generated_block_bid: str,
) -> int:
    return LearnGeneratedElement.query.filter(
        LearnGeneratedElement.run_session_bid == run_session_bid,
        LearnGeneratedElement.generated_block_bid == generated_block_bid,
        LearnGeneratedElement.event_type == "element",
        LearnGeneratedElement.deleted == 0,
        LearnGeneratedElement.status == 1,
    ).count()


def _reset_adapter_runtime(adapter: Any, generated_block_bid: str) -> None:
    adapter._block_states.pop(generated_block_bid, None)
    adapter._current_element_bid = None
    adapter._current_ask_anchor_bid = None
    adapter._current_ask_element_bid = None
    adapter._current_answer_element_bid = None


def _latest_anchor_bid_from_messages(messages: list[Any]) -> str:
    for message in reversed(messages):
        content = getattr(message, "content", None)
        if getattr(message, "type", "") != "element" or content is None:
            continue
        if not getattr(content, "is_final", False):
            continue
        element_type = getattr(content, "element_type", None)
        element_type_value = (
            element_type.value
            if hasattr(element_type, "value")
            else str(element_type or "")
        )
        if element_type_value in FOLLOW_UP_ELEMENT_TYPES:
            continue
        if element_type_value not in NON_FOLLOW_UP_ANCHOR_TYPES:
            continue
        return str(getattr(content, "element_bid", "") or "")
    return ""


def _emit_content_group(
    adapter: Any,
    block: LearnGeneratedBlock,
) -> list[Any]:
    messages: list[Any] = []
    content = str(block.generated_content or "")
    for item in format_content(content):
        event = RunMarkdownFlowDTO(
            outline_bid=block.outline_item_bid or "",
            generated_block_bid=block.generated_block_bid or "",
            type=GeneratedType.CONTENT,
            content=item.content,
        ).set_mdflow_stream_parts([(item.content, item.type, item.number)])
        messages.extend(list(adapter._handle_content(event)))
    messages.extend(list(adapter._finalize_block(block.generated_block_bid or "")))
    return messages


def _emit_interaction_group(
    adapter: Any,
    block: LearnGeneratedBlock,
) -> list[Any]:
    event = RunMarkdownFlowDTO(
        outline_bid=block.outline_item_bid or "",
        generated_block_bid=block.generated_block_bid or "",
        type=GeneratedType.INTERACTION,
        content=str(block.block_content_conf or ""),
    )
    return list(adapter._handle_interaction(event))


def _emit_follow_up_group(
    adapter: Any,
    *,
    ask_block: LearnGeneratedBlock,
    answer_block: LearnGeneratedBlock,
    anchor_element_bid: str,
) -> list[Any]:
    messages: list[Any] = []
    generated_block_bid = answer_block.generated_block_bid or ""
    ask_event = RunMarkdownFlowDTO(
        outline_bid=answer_block.outline_item_bid or "",
        generated_block_bid=generated_block_bid,
        type=GeneratedType.ASK,
        content=str(ask_block.generated_content or ""),
        anchor_element_bid=anchor_element_bid,
    )
    messages.extend(list(adapter._handle_ask(ask_event)))

    answer_content = str(answer_block.generated_content or "")
    for item in format_content(answer_content):
        content_event = RunMarkdownFlowDTO(
            outline_bid=answer_block.outline_item_bid or "",
            generated_block_bid=generated_block_bid,
            type=GeneratedType.CONTENT,
            content=item.content,
        ).set_mdflow_stream_parts([(item.content, item.type, item.number)])
        messages.extend(list(adapter._handle_content(content_event)))

    final_answer = adapter._finalize_answer_element(generated_block_bid)
    if final_answer is not None:
        messages.append(final_answer)
    adapter._block_states.pop(generated_block_bid, None)
    return messages


def _resolve_follow_up_answer_block(
    blocks: list[LearnGeneratedBlock],
    index: int,
) -> tuple[LearnGeneratedBlock | None, int]:
    next_index = index + 1
    if next_index >= len(blocks):
        return None, 1
    next_block = blocks[next_index]
    if next_block.type == BLOCK_TYPE_MDANSWER_VALUE:
        return next_block, 2
    if (
        next_block.type == BLOCK_TYPE_MDCONTENT_VALUE
        and int(next_block.role or 0) == ROLE_TEACHER
        and int(next_block.position or 0) == int(blocks[index].position or 0)
    ):
        return next_block, 2
    return None, 1


def _process_progress_record(
    app: Flask,
    progress_record: LearnProgressRecord,
    *,
    overwrite: bool,
    dry_run: bool,
) -> MdflowElementBackfillStats:
    stats = MdflowElementBackfillStats(
        progress_record_bid=progress_record.progress_record_bid or "",
        progress_record_id=int(progress_record.id or 0),
        shifu_bid=progress_record.shifu_bid or "",
        outline_item_bid=progress_record.outline_item_bid or "",
        user_bid=progress_record.user_bid or "",
        run_session_bid=f"mdflow_backfill_{uuid.uuid4().hex}",
        dry_run=dry_run,
    )
    adapter = _make_adapter(
        app,
        shifu_bid=stats.shifu_bid,
        outline_bid=stats.outline_item_bid,
        user_bid=stats.user_bid,
        run_session_bid=stats.run_session_bid,
    )
    blocks, duplicate_count = _load_deduped_blocks(progress_record.progress_record_bid)
    stats.duplicate_blocks_skipped = duplicate_count

    latest_anchor_bid = ""
    index = 0
    while index < len(blocks):
        block = blocks[index]
        block_bid = str(block.generated_block_bid or "")
        block_type = int(block.type or 0)

        if block_type == BLOCK_TYPE_MDASK_VALUE:
            answer_block, consumed = _resolve_follow_up_answer_block(blocks, index)
            if (
                answer_block is None
                or not str(answer_block.generated_content or "").strip()
            ):
                stats.skipped_orphan_follow_ups += 1
                index += consumed
                continue
            answer_bid = str(answer_block.generated_block_bid or "")
            if not latest_anchor_bid:
                stats.skipped_anchorless_follow_ups += 1
                index += consumed
                continue
            existing_rows = _count_active_group_rows(
                progress_record.progress_record_bid,
                answer_bid,
            )
            if existing_rows and not overwrite:
                stats.skipped_existing_groups += 1
                index += consumed
                continue
            if existing_rows:
                stats.overwritten_rows += _retire_active_group_rows(
                    progress_record.progress_record_bid,
                    answer_bid,
                )
            _emit_follow_up_group(
                adapter,
                ask_block=block,
                answer_block=answer_block,
                anchor_element_bid=latest_anchor_bid,
            )
            _prune_current_run_inactive_rows(
                run_session_bid=stats.run_session_bid,
                generated_block_bid=answer_bid,
            )
            stats.processed_block_groups += 1
            stats.inserted_element_rows += _count_current_run_active_rows(
                run_session_bid=stats.run_session_bid,
                generated_block_bid=answer_bid,
            )
            _reset_adapter_runtime(adapter, answer_bid)
            index += consumed
            continue

        if block_type == BLOCK_TYPE_MDANSWER_VALUE:
            stats.skipped_orphan_follow_ups += 1
            index += 1
            continue

        if block_type in {
            BLOCK_TYPE_MDCONTENT_VALUE,
            BLOCK_TYPE_MDERRORMESSAGE_VALUE,
        }:
            content = str(block.generated_content or "")
            if not content.strip():
                stats.skipped_empty_blocks += 1
                index += 1
                continue
            existing_rows = _count_active_group_rows(
                progress_record.progress_record_bid,
                block_bid,
            )
            if existing_rows and not overwrite:
                stats.skipped_existing_groups += 1
                index += 1
                continue
            if existing_rows:
                stats.overwritten_rows += _retire_active_group_rows(
                    progress_record.progress_record_bid,
                    block_bid,
                )
            final_messages = _emit_content_group(adapter, block)
            _prune_current_run_inactive_rows(
                run_session_bid=stats.run_session_bid,
                generated_block_bid=block_bid,
            )
            stats.processed_block_groups += 1
            stats.inserted_element_rows += _count_current_run_active_rows(
                run_session_bid=stats.run_session_bid,
                generated_block_bid=block_bid,
            )
            latest_anchor = _latest_anchor_bid_from_messages(final_messages)
            if latest_anchor:
                latest_anchor_bid = latest_anchor
            _reset_adapter_runtime(adapter, block_bid)
            index += 1
            continue

        if block_type == BLOCK_TYPE_MDINTERACTION_VALUE:
            interaction_content = str(block.block_content_conf or "")
            if not interaction_content.strip():
                stats.skipped_empty_blocks += 1
                index += 1
                continue
            existing_rows = _count_active_group_rows(
                progress_record.progress_record_bid,
                block_bid,
            )
            if existing_rows and not overwrite:
                stats.skipped_existing_groups += 1
                index += 1
                continue
            if existing_rows:
                stats.overwritten_rows += _retire_active_group_rows(
                    progress_record.progress_record_bid,
                    block_bid,
                )
            _emit_interaction_group(adapter, block)
            _prune_current_run_inactive_rows(
                run_session_bid=stats.run_session_bid,
                generated_block_bid=block_bid,
            )
            stats.processed_block_groups += 1
            stats.inserted_element_rows += _count_current_run_active_rows(
                run_session_bid=stats.run_session_bid,
                generated_block_bid=block_bid,
            )
            _reset_adapter_runtime(adapter, block_bid)
            index += 1
            continue

        index += 1

    return stats


def backfill_learn_generated_elements_for_progress(
    app: Flask,
    progress_record_bid: str,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> MdflowElementBackfillStats:
    progress_record = _load_progress_record(progress_record_bid)
    try:
        stats = _process_progress_record(
            app,
            progress_record,
            overwrite=overwrite,
            dry_run=dry_run,
        )
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
        return stats
    except Exception:
        db.session.rollback()
        raise


def backfill_learn_generated_elements_batch(
    app: Flask,
    *,
    progress_record_bids: list[str] | None = None,
    after_id: int = 0,
    limit: int = 100,
    overwrite: bool = False,
    dry_run: bool = False,
) -> MdflowElementBackfillBatchStats:
    batch_stats = MdflowElementBackfillBatchStats(dry_run=dry_run)
    progress_records = _load_progress_records(
        progress_record_bids=progress_record_bids,
        after_id=after_id,
        limit=limit,
    )
    for progress_record in progress_records:
        progress_bid = str(progress_record.progress_record_bid or "")
        try:
            result = backfill_learn_generated_elements_for_progress(
                app,
                progress_bid,
                overwrite=overwrite,
                dry_run=dry_run,
            )
        except Exception as exc:
            batch_stats.failed_progress_records.append(
                {
                    "progress_record_bid": progress_bid,
                    "error": str(exc),
                }
            )
            app.logger.exception(
                "mdflow learn element backfill failed for progress %s",
                progress_bid,
            )
            continue

        batch_stats.processed_progress_records += 1
        batch_stats.processed_block_groups += result.processed_block_groups
        batch_stats.inserted_element_rows += result.inserted_element_rows
        batch_stats.overwritten_rows += result.overwritten_rows
        batch_stats.skipped_existing_groups += result.skipped_existing_groups
        batch_stats.skipped_empty_blocks += result.skipped_empty_blocks
        batch_stats.skipped_orphan_follow_ups += result.skipped_orphan_follow_ups
        batch_stats.skipped_anchorless_follow_ups += (
            result.skipped_anchorless_follow_ups
        )
        batch_stats.duplicate_blocks_skipped += result.duplicate_blocks_skipped
        batch_stats.progress_results.append(result.as_dict())

    return batch_stats
