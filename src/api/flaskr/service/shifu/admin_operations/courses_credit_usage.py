"""Operator course credit usage listing and detail queries.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, Optional, Sequence
from flask import Flask
from sqlalchemy import and_, case, false, literal, not_, or_
from flaskr.dao import db
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
)
from flaskr.service.billing.primitives import credit_decimal_to_number
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.learn.const import (
    LEARN_STATUS_COMPLETED,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.common.models import (
    raise_param_error,
)
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseCreditUsageDetailItemDTO,
    AdminOperationCourseCreditUsageDetailListDTO,
    AdminOperationCourseCreditUsageItemDTO,
    AdminOperationCourseCreditUsageListDTO,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
)

from flaskr.service.shifu.admin_operations.courses_shared import (
    COURSE_CREDIT_USAGE_LIST_MAX_PAGE_SIZE,
    COURSE_CREDIT_USAGE_MODE_ASK,
    COURSE_CREDIT_USAGE_MODE_LEARN,
    COURSE_CREDIT_USAGE_MODE_LISTEN,
    COURSE_CREDIT_USAGE_SCENE_DEBUG,
    COURSE_CREDIT_USAGE_SCENE_LEARNING,
    COURSE_CREDIT_USAGE_SCENE_PREVIEW,
    COURSE_CREDIT_USAGE_VIEW_GROUPED,
    COURSE_CREDIT_USAGE_VIEW_RAW,
    _build_course_outline_context_map,
    _load_operator_course_outline_items,
    _load_user_map,
    _normalize_identifier,
    _normalize_metadata_json,
    _resolve_visible_leaf_outline_bids,
)


def _resolve_course_credit_usage_mode(row: BillUsageRecord) -> str:
    usage_type = int(getattr(row, "usage_type", 0) or 0)
    if usage_type == BILL_USAGE_TYPE_TTS:
        return COURSE_CREDIT_USAGE_MODE_LISTEN

    metadata = _normalize_metadata_json(getattr(row, "extra", None))
    generation_name = str(metadata.get("generation_name", "") or "").strip().lower()
    if (
        "/user_follow_ask/" in generation_name
        or generation_name.startswith("lesson_ask/")
        or generation_name.startswith("lesson_preview_ask/")
    ):
        return COURSE_CREDIT_USAGE_MODE_ASK

    return COURSE_CREDIT_USAGE_MODE_LEARN


def _resolve_course_credit_usage_mode_filter(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {
        "",
        "all",
        COURSE_CREDIT_USAGE_MODE_LEARN,
        COURSE_CREDIT_USAGE_MODE_LISTEN,
        COURSE_CREDIT_USAGE_MODE_ASK,
    }:
        return normalized
    return ""


def _resolve_course_credit_usage_scene(row: BillUsageRecord) -> str:
    usage_scene = int(getattr(row, "usage_scene", 0) or 0)
    if usage_scene == BILL_USAGE_SCENE_DEBUG:
        return COURSE_CREDIT_USAGE_SCENE_DEBUG
    if usage_scene == BILL_USAGE_SCENE_PREVIEW:
        return COURSE_CREDIT_USAGE_SCENE_PREVIEW
    if usage_scene == BILL_USAGE_SCENE_PROD:
        return COURSE_CREDIT_USAGE_SCENE_LEARNING
    return ""


def _resolve_course_credit_usage_scene_filter(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {
        "",
        "all",
        COURSE_CREDIT_USAGE_SCENE_LEARNING,
        COURSE_CREDIT_USAGE_SCENE_PREVIEW,
        COURSE_CREDIT_USAGE_SCENE_DEBUG,
    }:
        return normalized
    return ""


def _build_course_credit_usage_scene_filter(value: str) -> Any | None:
    if value == COURSE_CREDIT_USAGE_SCENE_LEARNING:
        return BillUsageRecord.usage_scene == BILL_USAGE_SCENE_PROD
    if value == COURSE_CREDIT_USAGE_SCENE_PREVIEW:
        return BillUsageRecord.usage_scene == BILL_USAGE_SCENE_PREVIEW
    if value == COURSE_CREDIT_USAGE_SCENE_DEBUG:
        return BillUsageRecord.usage_scene == BILL_USAGE_SCENE_DEBUG
    return None


def _resolve_course_credit_usage_view(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", COURSE_CREDIT_USAGE_VIEW_GROUPED}:
        return COURSE_CREDIT_USAGE_VIEW_GROUPED
    if normalized == COURSE_CREDIT_USAGE_VIEW_RAW:
        return normalized
    return ""


def _build_course_credit_usage_model_display(provider: str, model: str) -> str:
    normalized_provider = str(provider or "").strip()
    normalized_model = str(model or "").strip()
    if normalized_provider and normalized_model:
        return f"{normalized_provider} / {normalized_model}"
    return normalized_provider or normalized_model


def _build_course_credit_usage_group_key(
    progress_record_bid: str,
    usage_scene: str,
    usage_mode: str,
    usage_bid: str,
) -> str:
    normalized_progress_record_bid = str(progress_record_bid or "").strip()
    normalized_usage_scene = str(usage_scene or "").strip()
    normalized_usage_mode = str(usage_mode or "").strip()
    normalized_usage_bid = str(usage_bid or "").strip()
    if normalized_progress_record_bid:
        group_parts = [
            value
            for value in (
                normalized_progress_record_bid,
                normalized_usage_scene,
                normalized_usage_mode,
            )
            if value
        ]
        return ":".join(group_parts)
    return normalized_usage_bid


def _build_operator_course_credit_usage_item(
    *,
    usage_row: BillUsageRecord,
    ledger_amount: Any,
    user_map: Dict[str, Dict[str, Any]],
    outline_context_map: Dict[str, Dict[str, str]],
    group_key: str = "",
    usage_count: int = 1,
    usage_mode: str = "",
    provider: str = "",
    model: str = "",
    model_variant_count: int = 0,
    consumed_credits: Any = None,
    created_at: Any = None,
) -> AdminOperationCourseCreditUsageItemDTO:
    user_bid = str(getattr(usage_row, "user_bid", "") or "").strip()
    outline_item_bid = str(getattr(usage_row, "outline_item_bid", "") or "").strip()
    context = outline_context_map.get(
        outline_item_bid,
        {
            "chapter_outline_item_bid": "",
            "chapter_title": "",
            "lesson_outline_item_bid": outline_item_bid,
            "lesson_title": "",
        },
    )
    user = user_map.get(user_bid, {})
    resolved_provider = str(
        provider or getattr(usage_row, "provider", "") or ""
    ).strip()
    resolved_model = str(model or getattr(usage_row, "model", "") or "").strip()
    resolved_usage_mode = usage_mode or _resolve_course_credit_usage_mode(usage_row)
    resolved_usage_scene = _resolve_course_credit_usage_scene(usage_row)
    resolved_created_at = (
        created_at if created_at is not None else getattr(usage_row, "created_at", None)
    )
    if consumed_credits in ("", None):
        resolved_consumed_credits = credit_decimal_to_number(
            abs(Decimal(str(ledger_amount or 0)))
        )
    else:
        resolved_consumed_credits = credit_decimal_to_number(
            Decimal(str(consumed_credits or 0))
        )

    return AdminOperationCourseCreditUsageItemDTO(
        group_key=group_key or str(getattr(usage_row, "usage_bid", "") or ""),
        usage_bid=str(getattr(usage_row, "usage_bid", "") or ""),
        progress_record_bid=str(getattr(usage_row, "progress_record_bid", "") or ""),
        generated_block_bid=str(getattr(usage_row, "generated_block_bid", "") or ""),
        user_bid=user_bid,
        mobile=str(user.get("mobile", "") or ""),
        email=str(user.get("email", "") or ""),
        nickname=str(user.get("nickname", "") or ""),
        chapter_outline_item_bid=str(context.get("chapter_outline_item_bid", "") or ""),
        chapter_title=str(context.get("chapter_title", "") or ""),
        lesson_outline_item_bid=str(context.get("lesson_outline_item_bid", "") or ""),
        lesson_title=str(context.get("lesson_title", "") or ""),
        usage_scene=resolved_usage_scene,
        usage_mode=resolved_usage_mode,
        provider=resolved_provider,
        model=resolved_model,
        usage_count=max(int(usage_count or 0), 1),
        model_variant_count=max(int(model_variant_count or 0), 0),
        consumed_credits=resolved_consumed_credits,
        created_at=resolved_created_at,
    )


def _build_course_credit_usage_generation_name_expr() -> Any:
    return db.func.lower(BillUsageRecord.extra["generation_name"].as_string())


def _build_course_credit_usage_ask_filter(generation_name: Any | None = None) -> Any:
    generation_name = (
        generation_name
        if generation_name is not None
        else _build_course_credit_usage_generation_name_expr()
    )
    return or_(
        generation_name.contains("/user_follow_ask/"),
        generation_name.startswith("lesson_ask/"),
        generation_name.startswith("lesson_preview_ask/"),
    )


def _build_course_credit_usage_learn_filter(
    generation_name: Any | None = None,
) -> Any:
    generation_name = (
        generation_name
        if generation_name is not None
        else _build_course_credit_usage_generation_name_expr()
    )
    return or_(
        generation_name.is_(None),
        generation_name == "",
        not_(_build_course_credit_usage_ask_filter(generation_name)),
    )


def _build_operator_course_credit_usage_ledger_totals_subquery(shifu_bid: str):
    course_usage_bids = (
        db.session.query(BillUsageRecord.usage_bid.label("usage_bid"))
        .filter(
            BillUsageRecord.shifu_bid == shifu_bid,
            BillUsageRecord.deleted == 0,
            BillUsageRecord.billable == 1,
            BillUsageRecord.status == 0,
            BillUsageRecord.record_level == 0,
            BillUsageRecord.usage_scene.in_(
                (
                    BILL_USAGE_SCENE_DEBUG,
                    BILL_USAGE_SCENE_PREVIEW,
                    BILL_USAGE_SCENE_PROD,
                )
            ),
        )
        .subquery()
    )
    return (
        db.session.query(
            CreditLedgerEntry.source_bid.label("usage_bid"),
            db.func.sum(CreditLedgerEntry.amount).label("ledger_amount"),
        )
        .join(
            course_usage_bids,
            course_usage_bids.c.usage_bid == CreditLedgerEntry.source_bid,
        )
        .filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_USAGE,
        )
        .group_by(CreditLedgerEntry.source_bid)
        .subquery()
    )


def _build_operator_course_credit_usage_base_query(
    shifu_bid: str,
    *,
    outline_item_bids: Optional[Sequence[str]] = None,
):
    ledger_totals = _build_operator_course_credit_usage_ledger_totals_subquery(
        shifu_bid
    )
    query = db.session.query(
        BillUsageRecord,
        ledger_totals.c.ledger_amount,
    ).join(
        ledger_totals,
        ledger_totals.c.usage_bid == BillUsageRecord.usage_bid,
    )
    query = query.filter(
        BillUsageRecord.shifu_bid == shifu_bid,
        BillUsageRecord.deleted == 0,
        BillUsageRecord.billable == 1,
        BillUsageRecord.status == 0,
        BillUsageRecord.record_level == 0,
        BillUsageRecord.usage_scene.in_(
            (
                BILL_USAGE_SCENE_DEBUG,
                BILL_USAGE_SCENE_PREVIEW,
                BILL_USAGE_SCENE_PROD,
            )
        ),
        ledger_totals.c.ledger_amount < 0,
    )
    if outline_item_bids is not None:
        normalized_outline_item_bids = [
            str(outline_item_bid or "").strip()
            for outline_item_bid in outline_item_bids
            if str(outline_item_bid or "").strip()
        ]
        query = query.filter(
            BillUsageRecord.outline_item_bid.in_(normalized_outline_item_bids)
        )
    return query


def _resolve_course_credit_usage_output_summary(
    usage_row: BillUsageRecord,
) -> str:
    normalized_generated_block_bid = str(
        getattr(usage_row, "generated_block_bid", "") or ""
    ).strip()
    shifu_bid = str(getattr(usage_row, "shifu_bid", "") or "")
    user_bid = str(getattr(usage_row, "user_bid", "") or "")
    outline_item_bid = str(getattr(usage_row, "outline_item_bid", "") or "")

    def resolve_element_summary(generated_block_bid: str) -> str:
        normalized_block_bid = str(generated_block_bid or "").strip()
        if not normalized_block_bid:
            return ""
        element_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == normalized_block_bid,
                LearnGeneratedElement.shifu_bid == shifu_bid,
                LearnGeneratedElement.user_bid == user_bid,
                LearnGeneratedElement.outline_item_bid == outline_item_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.role == "teacher",
                LearnGeneratedElement.is_final == 1,
                LearnGeneratedElement.is_renderable == 1,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
                LearnGeneratedElement.content_text != "",
            )
            .order_by(
                LearnGeneratedElement.sequence_number.asc(),
                LearnGeneratedElement.run_event_seq.asc(),
                LearnGeneratedElement.id.asc(),
            )
            .limit(20)
            .all()
        )
        return "\n".join(
            str(getattr(row, "content_text", "") or "").strip()
            for row in element_rows
            if str(getattr(row, "content_text", "") or "").strip()
        ).strip()

    def resolve_block_generated_content(generated_block_bid: str) -> str:
        normalized_block_bid = str(generated_block_bid or "").strip()
        if not normalized_block_bid:
            return ""
        block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid == normalized_block_bid,
                LearnGeneratedBlock.shifu_bid == shifu_bid,
                LearnGeneratedBlock.user_bid == user_bid,
                LearnGeneratedBlock.outline_item_bid == outline_item_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type.in_(
                    [
                        BLOCK_TYPE_MDANSWER_VALUE,
                        BLOCK_TYPE_MDCONTENT_VALUE,
                        BLOCK_TYPE_MDINTERACTION_VALUE,
                    ]
                ),
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        if not block:
            return ""
        generated_content = str(getattr(block, "generated_content", "") or "").strip()
        if generated_content:
            return generated_content
        if int(getattr(block, "type", 0) or 0) == BLOCK_TYPE_MDINTERACTION_VALUE:
            return str(getattr(block, "block_content_conf", "") or "").strip()
        return ""

    if normalized_generated_block_bid:
        exact_content = resolve_element_summary(
            normalized_generated_block_bid
        ) or resolve_block_generated_content(normalized_generated_block_bid)
        if exact_content:
            return exact_content

    return ""


def _load_course_credit_usage_output_summary_map(
    usage_rows: Sequence[BillUsageRecord],
) -> dict[str, str]:
    normalized_rows = [
        usage_row
        for usage_row in usage_rows
        if str(getattr(usage_row, "usage_bid", "") or "").strip()
        and str(getattr(usage_row, "generated_block_bid", "") or "").strip()
    ]
    if not normalized_rows:
        return {}

    generated_block_bids = sorted(
        {
            str(getattr(usage_row, "generated_block_bid", "") or "").strip()
            for usage_row in normalized_rows
            if str(getattr(usage_row, "generated_block_bid", "") or "").strip()
        }
    )
    if not generated_block_bids:
        return {}

    def context_key(row: Any) -> tuple[str, str, str, str]:
        return (
            str(getattr(row, "generated_block_bid", "") or "").strip(),
            str(getattr(row, "shifu_bid", "") or "").strip(),
            str(getattr(row, "user_bid", "") or "").strip(),
            str(getattr(row, "outline_item_bid", "") or "").strip(),
        )

    usage_context_keys = {context_key(usage_row) for usage_row in normalized_rows}
    shifu_bids = sorted({key[1] for key in usage_context_keys if key[1]})
    user_bids = sorted({key[2] for key in usage_context_keys if key[2]})
    outline_item_bids = sorted({key[3] for key in usage_context_keys if key[3]})

    element_parts_map: dict[tuple[str, str, str, str], list[str]] = {}
    element_rows = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.generated_block_bid.in_(generated_block_bids),
            LearnGeneratedElement.shifu_bid.in_(shifu_bids),
            LearnGeneratedElement.user_bid.in_(user_bids),
            LearnGeneratedElement.outline_item_bid.in_(outline_item_bids),
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.role == "teacher",
            LearnGeneratedElement.is_final == 1,
            LearnGeneratedElement.is_renderable == 1,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
            LearnGeneratedElement.content_text != "",
        )
        .order_by(
            LearnGeneratedElement.generated_block_bid.asc(),
            LearnGeneratedElement.sequence_number.asc(),
            LearnGeneratedElement.run_event_seq.asc(),
            LearnGeneratedElement.id.asc(),
        )
        .yield_per(100)
    )
    for element in element_rows:
        generated_block_bid = str(
            getattr(element, "generated_block_bid", "") or ""
        ).strip()
        if not generated_block_bid:
            continue
        key = context_key(element)
        if key not in usage_context_keys:
            continue
        parts = element_parts_map.setdefault(key, [])
        if len(parts) >= 20:
            continue
        content = str(getattr(element, "content_text", "") or "").strip()
        if content:
            parts.append(content)

    element_summary_map = {
        key: "\n".join(parts) for key, parts in element_parts_map.items() if parts
    }

    missing_context_keys = [
        key for key in usage_context_keys if not element_summary_map.get(key)
    ]
    missing_context_key_set = set(missing_context_keys)
    missing_block_bids = sorted({key[0] for key in missing_context_keys if key[0]})
    block_summary_map: dict[tuple[str, str, str, str], str] = {}
    if missing_block_bids:
        block_rows = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid.in_(missing_block_bids),
                LearnGeneratedBlock.shifu_bid.in_(shifu_bids),
                LearnGeneratedBlock.user_bid.in_(user_bids),
                LearnGeneratedBlock.outline_item_bid.in_(outline_item_bids),
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type.in_(
                    [
                        BLOCK_TYPE_MDANSWER_VALUE,
                        BLOCK_TYPE_MDCONTENT_VALUE,
                        BLOCK_TYPE_MDINTERACTION_VALUE,
                    ]
                ),
            )
            .order_by(
                LearnGeneratedBlock.generated_block_bid.asc(),
                LearnGeneratedBlock.id.desc(),
            )
            .all()
        )
        for block in block_rows:
            generated_block_bid = str(
                getattr(block, "generated_block_bid", "") or ""
            ).strip()
            key = context_key(block)
            if (
                not generated_block_bid
                or key not in missing_context_key_set
                or key in block_summary_map
            ):
                continue
            generated_content = str(
                getattr(block, "generated_content", "") or ""
            ).strip()
            if generated_content:
                block_summary_map[key] = generated_content
                continue
            if int(getattr(block, "type", 0) or 0) == BLOCK_TYPE_MDINTERACTION_VALUE:
                block_summary_map[key] = str(
                    getattr(block, "block_content_conf", "") or ""
                ).strip()

    summary_by_usage_bid: dict[str, str] = {}
    for usage_row in normalized_rows:
        usage_bid = str(getattr(usage_row, "usage_bid", "") or "").strip()
        generated_block_bid = str(
            getattr(usage_row, "generated_block_bid", "") or ""
        ).strip()
        key = context_key(usage_row)
        summary = element_summary_map.get(key) or block_summary_map.get(key, "")
        if summary:
            summary_by_usage_bid[usage_bid] = summary

    return summary_by_usage_bid


def _build_operator_course_credit_usage_detail_item(
    usage_row: BillUsageRecord,
    ledger_amount: Any,
    output_summary: Optional[str] = None,
) -> AdminOperationCourseCreditUsageDetailItemDTO:
    return AdminOperationCourseCreditUsageDetailItemDTO(
        usage_bid=str(getattr(usage_row, "usage_bid", "") or ""),
        consumed_credits=credit_decimal_to_number(
            abs(Decimal(str(ledger_amount or 0)))
        ),
        input_tokens=int(getattr(usage_row, "input", 0) or 0),
        output_tokens=int(getattr(usage_row, "output", 0) or 0),
        word_count=int(getattr(usage_row, "word_count", 0) or 0),
        duration_ms=int(getattr(usage_row, "duration_ms", 0) or 0),
        segment_count=int(getattr(usage_row, "segment_count", 0) or 0),
        output_summary=(
            output_summary
            if output_summary is not None
            else _resolve_course_credit_usage_output_summary(usage_row)
        ),
        created_at=getattr(usage_row, "created_at", None),
    )


def _apply_course_credit_usage_filters(query: Any, filters: dict) -> Any:
    keyword = str(filters.get("keyword", "") or "").strip()
    mode_filter = _resolve_course_credit_usage_mode_filter(
        str(filters.get("mode", "") or "")
    )
    scene_filter = _resolve_course_credit_usage_scene_filter(
        str(filters.get("usage_scene", "") or "")
    )
    start_time = filters.get("start_time")
    end_time = filters.get("end_time")

    user_keyword_filter = _build_credit_usage_user_keyword_filter(
        BillUsageRecord.user_bid,
        keyword,
    )
    if user_keyword_filter is not None:
        query = query.filter(user_keyword_filter)
    scene_filter_expr = _build_course_credit_usage_scene_filter(scene_filter)
    if scene_filter_expr is not None:
        query = query.filter(scene_filter_expr)
    if start_time:
        query = query.filter(BillUsageRecord.created_at >= start_time)
    if end_time:
        query = query.filter(BillUsageRecord.created_at <= end_time)

    generation_name_expr = _build_course_credit_usage_generation_name_expr()
    if mode_filter == COURSE_CREDIT_USAGE_MODE_LISTEN:
        query = query.filter(BillUsageRecord.usage_type == BILL_USAGE_TYPE_TTS)
    elif mode_filter == COURSE_CREDIT_USAGE_MODE_ASK:
        query = query.filter(
            BillUsageRecord.usage_type != BILL_USAGE_TYPE_TTS,
            _build_course_credit_usage_ask_filter(generation_name_expr),
        )
    elif mode_filter == COURSE_CREDIT_USAGE_MODE_LEARN:
        query = query.filter(
            BillUsageRecord.usage_type != BILL_USAGE_TYPE_TTS,
            _build_course_credit_usage_learn_filter(generation_name_expr),
        )

    return query


def _build_course_credit_usage_covered_completed_user_subquery(
    *,
    shifu_bid: str,
    leaf_outline_bids: Sequence[str],
):
    normalized_leaf_outline_bids = [
        str(outline_item_bid or "").strip()
        for outline_item_bid in leaf_outline_bids
        if str(outline_item_bid or "").strip()
    ]
    if not normalized_leaf_outline_bids:
        return None

    latest_progress_rows = (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
            LearnProgressRecord.outline_item_bid.label("outline_item_bid"),
            LearnProgressRecord.status.label("status"),
            db.func.row_number()
            .over(
                partition_by=[
                    LearnProgressRecord.user_bid,
                    LearnProgressRecord.outline_item_bid,
                ],
                order_by=[
                    LearnProgressRecord.updated_at.desc(),
                    LearnProgressRecord.id.desc(),
                ],
            )
            .label("row_index"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid.in_(normalized_leaf_outline_bids),
            LearnProgressRecord.deleted == 0,
        )
        .subquery()
    )

    completed_lesson_counts = (
        db.session.query(
            latest_progress_rows.c.user_bid.label("user_bid"),
            db.func.count(
                db.func.distinct(latest_progress_rows.c.outline_item_bid)
            ).label("learned_lesson_count"),
        )
        .filter(
            latest_progress_rows.c.row_index == 1,
            latest_progress_rows.c.status == LEARN_STATUS_COMPLETED,
        )
        .group_by(latest_progress_rows.c.user_bid)
        .subquery()
    )
    return (
        db.session.query(completed_lesson_counts.c.user_bid.label("user_bid"))
        .filter(
            completed_lesson_counts.c.learned_lesson_count
            >= len(normalized_leaf_outline_bids)
        )
        .subquery()
    )


def _build_operator_course_credit_metrics(
    shifu_bid: str,
    leaf_outline_bids: Sequence[str],
) -> Dict[str, Any]:
    base_query = _build_operator_course_credit_usage_base_query(
        shifu_bid,
        outline_item_bids=leaf_outline_bids,
    )
    usage_rows = base_query.subquery("operator_course_credit_metric_usages")
    aggregate_row = db.session.query(
        db.func.coalesce(
            db.func.sum(db.func.abs(usage_rows.c.ledger_amount)),
            0,
        ).label("credit_consumed_total"),
        db.func.count(db.func.distinct(usage_rows.c.usage_bid)).label(
            "credit_usage_count"
        ),
        db.func.count(db.func.distinct(usage_rows.c.user_bid)).label(
            "credit_user_count"
        ),
    ).one()

    completed_user_subquery = (
        _build_course_credit_usage_covered_completed_user_subquery(
            shifu_bid=shifu_bid,
            leaf_outline_bids=leaf_outline_bids,
        )
    )
    completed_credit_user_count = 0
    completed_credit_total = Decimal("0")
    if completed_user_subquery is not None:
        completed_row = (
            db.session.query(
                db.func.count(db.func.distinct(usage_rows.c.user_bid)).label(
                    "completed_credit_user_count"
                ),
                db.func.coalesce(
                    db.func.sum(db.func.abs(usage_rows.c.ledger_amount)),
                    0,
                ).label("completed_credit_total"),
            )
            .select_from(usage_rows)
            .join(
                completed_user_subquery,
                completed_user_subquery.c.user_bid == usage_rows.c.user_bid,
            )
            .one()
        )
        completed_credit_user_count = int(
            getattr(completed_row, "completed_credit_user_count", 0) or 0
        )
        completed_credit_total = Decimal(
            str(getattr(completed_row, "completed_credit_total", 0) or 0)
        )

    completed_user_avg_credits = None
    if completed_credit_user_count > 0:
        completed_user_avg_credits = credit_decimal_to_number(
            completed_credit_total / Decimal(completed_credit_user_count)
        )

    return {
        "credit_consumed_total": credit_decimal_to_number(
            abs(Decimal(str(getattr(aggregate_row, "credit_consumed_total", 0) or 0)))
        ),
        "credit_usage_count": int(getattr(aggregate_row, "credit_usage_count", 0) or 0),
        "credit_user_count": int(getattr(aggregate_row, "credit_user_count", 0) or 0),
        "completed_credit_user_count": completed_credit_user_count,
        "completed_user_avg_credits": completed_user_avg_credits,
    }


def _build_credit_usage_user_keyword_filter(
    user_bid_column: Any, keyword: str
) -> Any | None:
    normalized = _normalize_identifier(keyword)
    if not normalized:
        return None

    nickname_match_exists = (
        db.session.query(UserEntity.id)
        .filter(
            UserEntity.user_bid == user_bid_column,
            UserEntity.deleted == 0,
            UserEntity.nickname.ilike(f"%{normalized}%"),
        )
        .exists()
    )

    if "@" in normalized:
        credential_identifier_filter = (
            db.func.lower(AuthCredential.identifier) == normalized
        )
        user_identifier_filter = db.func.lower(UserEntity.user_identify) == normalized
    elif normalized.isdigit():
        credential_identifier_filter = AuthCredential.identifier == normalized
        user_identifier_filter = UserEntity.user_identify == normalized
    else:
        return nickname_match_exists

    credential_match_exists = (
        db.session.query(AuthCredential.id)
        .filter(
            AuthCredential.user_bid == user_bid_column,
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            credential_identifier_filter,
        )
        .exists()
    )

    user_identifier_match_exists = (
        db.session.query(UserEntity.id)
        .filter(
            UserEntity.user_bid == user_bid_column,
            UserEntity.deleted == 0,
            user_identifier_filter,
        )
        .exists()
    )

    return or_(
        nickname_match_exists,
        credential_match_exists,
        user_identifier_match_exists,
    )


def get_operator_course_credit_usages(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> AdminOperationCourseCreditUsageListDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            COURSE_CREDIT_USAGE_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        _detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        outline_context_map = _build_course_outline_context_map(outline_items)
        visible_leaf_outline_bids = _resolve_visible_leaf_outline_bids(outline_items)

        mode_filter = _resolve_course_credit_usage_mode_filter(
            str(filters.get("mode", "") or "")
        )
        scene_filter = _resolve_course_credit_usage_scene_filter(
            str(filters.get("usage_scene", "") or "")
        )
        view = _resolve_course_credit_usage_view(str(filters.get("view", "") or ""))

        if str(filters.get("mode", "") or "").strip() and not mode_filter:
            raise_param_error("mode")
        if str(filters.get("usage_scene", "") or "").strip() and not scene_filter:
            raise_param_error("usage_scene")
        if str(filters.get("view", "") or "").strip() and not view:
            raise_param_error("view")

        query = _build_operator_course_credit_usage_base_query(
            normalized_shifu_bid,
            outline_item_bids=visible_leaf_outline_bids,
        )
        query = _apply_course_credit_usage_filters(query, filters)

        if view == COURSE_CREDIT_USAGE_VIEW_RAW:
            total = query.count()
            rows = (
                query.order_by(
                    BillUsageRecord.created_at.desc(), BillUsageRecord.id.desc()
                )
                .offset((safe_page_index - 1) * safe_page_size)
                .limit(safe_page_size)
                .all()
            )
            user_map = _load_user_map(
                sorted(
                    {
                        str(getattr(usage_row, "user_bid", "") or "").strip()
                        for usage_row, _ledger_amount in rows
                        if str(getattr(usage_row, "user_bid", "") or "").strip()
                    }
                )
            )
            raw_items: list[AdminOperationCourseCreditUsageItemDTO] = []
            for usage_row, ledger_amount in rows:
                model_display = _build_course_credit_usage_model_display(
                    str(getattr(usage_row, "provider", "") or ""),
                    str(getattr(usage_row, "model", "") or ""),
                )
                raw_items.append(
                    _build_operator_course_credit_usage_item(
                        usage_row=usage_row,
                        ledger_amount=ledger_amount,
                        user_map=user_map,
                        outline_context_map=outline_context_map,
                        group_key=str(getattr(usage_row, "usage_bid", "") or ""),
                        usage_count=1,
                        usage_mode=_resolve_course_credit_usage_mode(usage_row),
                        model_variant_count=1 if model_display else 0,
                    )
                )
            return AdminOperationCourseCreditUsageListDTO(
                view=COURSE_CREDIT_USAGE_VIEW_RAW,
                items=raw_items,
                page=safe_page_index,
                page_size=safe_page_size,
                total=total,
                page_count=math.ceil(total / safe_page_size) if safe_page_size else 0,
            )

        usage_rows = query.subquery("operator_course_credit_usage_filtered")
        generation_name_expr = db.func.lower(
            usage_rows.c.extra["generation_name"].as_string()
        )
        usage_mode_expr = case(
            (
                usage_rows.c.usage_type == BILL_USAGE_TYPE_TTS,
                COURSE_CREDIT_USAGE_MODE_LISTEN,
            ),
            (
                and_(
                    usage_rows.c.usage_type != BILL_USAGE_TYPE_TTS,
                    or_(
                        generation_name_expr.contains("/user_follow_ask/"),
                        generation_name_expr.startswith("lesson_ask/"),
                        generation_name_expr.startswith("lesson_preview_ask/"),
                    ),
                ),
                COURSE_CREDIT_USAGE_MODE_ASK,
            ),
            else_=COURSE_CREDIT_USAGE_MODE_LEARN,
        ).label("usage_mode")
        usage_scene_expr = case(
            (
                usage_rows.c.usage_scene == BILL_USAGE_SCENE_DEBUG,
                COURSE_CREDIT_USAGE_SCENE_DEBUG,
            ),
            (
                usage_rows.c.usage_scene == BILL_USAGE_SCENE_PREVIEW,
                COURSE_CREDIT_USAGE_SCENE_PREVIEW,
            ),
            (
                usage_rows.c.usage_scene == BILL_USAGE_SCENE_PROD,
                COURSE_CREDIT_USAGE_SCENE_LEARNING,
            ),
            else_="",
        ).label("usage_scene")
        group_key_expr = db.func.concat(
            usage_rows.c.user_bid,
            literal(":"),
            usage_rows.c.outline_item_bid,
            literal(":"),
            usage_scene_expr,
            literal(":"),
            usage_mode_expr,
        ).label("group_key")

        grouped_query = (
            db.session.query(
                group_key_expr,
                usage_rows.c.user_bid.label("user_bid"),
                usage_rows.c.outline_item_bid.label("outline_item_bid"),
                usage_scene_expr,
                usage_mode_expr,
                db.func.count(db.func.distinct(usage_rows.c.usage_bid)).label(
                    "usage_count"
                ),
                db.func.count(
                    db.func.distinct(
                        db.func.nullif(
                            db.func.concat(
                                db.func.coalesce(usage_rows.c.provider, ""),
                                literal("/"),
                                db.func.coalesce(usage_rows.c.model, ""),
                            ),
                            "/",
                        )
                    )
                ).label("model_variant_count"),
                db.func.coalesce(
                    db.func.sum(db.func.abs(usage_rows.c.ledger_amount)), 0
                ).label("consumed_credits"),
                db.func.max(usage_rows.c.created_at).label("created_at"),
            )
            .select_from(usage_rows)
            .group_by(
                group_key_expr,
                usage_rows.c.user_bid,
                usage_rows.c.outline_item_bid,
                usage_scene_expr,
                usage_mode_expr,
            )
        )
        latest_usage_query = db.session.query(
            group_key_expr,
            usage_rows.c.usage_bid.label("usage_bid"),
            usage_rows.c.progress_record_bid.label("progress_record_bid"),
            usage_rows.c.generated_block_bid.label("generated_block_bid"),
            usage_rows.c.provider.label("provider"),
            usage_rows.c.model.label("model"),
            db.func.row_number()
            .over(
                partition_by=[
                    usage_rows.c.user_bid,
                    usage_rows.c.outline_item_bid,
                    usage_scene_expr,
                    usage_mode_expr,
                ],
                order_by=[usage_rows.c.created_at.desc(), usage_rows.c.id.desc()],
            )
            .label("row_number"),
        ).select_from(usage_rows)

        grouped_subquery = grouped_query.subquery("operator_course_credit_usage_groups")
        latest_usage_subquery = latest_usage_query.subquery(
            "operator_course_credit_usage_latest_rows"
        )
        total = (
            db.session.query(db.func.count()).select_from(grouped_subquery).scalar()
            or 0
        )
        grouped_rows = (
            db.session.query(
                grouped_subquery.c.group_key,
                latest_usage_subquery.c.usage_bid,
                latest_usage_subquery.c.progress_record_bid,
                latest_usage_subquery.c.generated_block_bid,
                grouped_subquery.c.user_bid,
                grouped_subquery.c.outline_item_bid,
                grouped_subquery.c.usage_scene,
                grouped_subquery.c.usage_mode,
                latest_usage_subquery.c.provider,
                latest_usage_subquery.c.model,
                grouped_subquery.c.usage_count,
                grouped_subquery.c.model_variant_count,
                grouped_subquery.c.consumed_credits,
                grouped_subquery.c.created_at,
            )
            .join(
                latest_usage_subquery,
                and_(
                    latest_usage_subquery.c.group_key == grouped_subquery.c.group_key,
                    latest_usage_subquery.c.row_number == 1,
                ),
            )
            .order_by(
                grouped_subquery.c.created_at.desc(), grouped_subquery.c.group_key.asc()
            )
            .offset((safe_page_index - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        user_map = _load_user_map(
            sorted(
                {
                    str(getattr(row, "user_bid", "") or "").strip()
                    for row in grouped_rows
                    if str(getattr(row, "user_bid", "") or "").strip()
                }
            )
        )

        grouped_items: list[AdminOperationCourseCreditUsageItemDTO] = []
        for row in grouped_rows:
            context = outline_context_map.get(
                str(getattr(row, "outline_item_bid", "") or "").strip(),
                {
                    "chapter_outline_item_bid": "",
                    "chapter_title": "",
                    "lesson_outline_item_bid": str(
                        getattr(row, "outline_item_bid", "") or ""
                    ),
                    "lesson_title": "",
                },
            )
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            user = user_map.get(user_bid, {})
            grouped_items.append(
                AdminOperationCourseCreditUsageItemDTO(
                    group_key=str(getattr(row, "group_key", "") or ""),
                    usage_bid=str(getattr(row, "usage_bid", "") or ""),
                    progress_record_bid=str(
                        getattr(row, "progress_record_bid", "") or ""
                    ),
                    generated_block_bid=str(
                        getattr(row, "generated_block_bid", "") or ""
                    ),
                    user_bid=user_bid,
                    mobile=str(user.get("mobile", "") or ""),
                    email=str(user.get("email", "") or ""),
                    nickname=str(user.get("nickname", "") or ""),
                    chapter_outline_item_bid=str(
                        context.get("chapter_outline_item_bid", "") or ""
                    ),
                    chapter_title=str(context.get("chapter_title", "") or ""),
                    lesson_outline_item_bid=str(
                        context.get("lesson_outline_item_bid", "") or ""
                    ),
                    lesson_title=str(context.get("lesson_title", "") or ""),
                    usage_scene=str(getattr(row, "usage_scene", "") or ""),
                    usage_mode=str(getattr(row, "usage_mode", "") or ""),
                    provider=str(getattr(row, "provider", "") or ""),
                    model=str(getattr(row, "model", "") or ""),
                    usage_count=int(getattr(row, "usage_count", 0) or 0),
                    model_variant_count=int(
                        getattr(row, "model_variant_count", 0) or 0
                    ),
                    consumed_credits=credit_decimal_to_number(
                        Decimal(str(getattr(row, "consumed_credits", 0) or 0))
                    ),
                    created_at=getattr(row, "created_at", None),
                )
            )

        return AdminOperationCourseCreditUsageListDTO(
            view=COURSE_CREDIT_USAGE_VIEW_GROUPED,
            items=grouped_items,
            page=safe_page_index,
            page_size=safe_page_size,
            total=int(total or 0),
            page_count=math.ceil(int(total or 0) / safe_page_size)
            if safe_page_size
            else 0,
        )


def get_operator_course_credit_usage_details(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> AdminOperationCourseCreditUsageDetailListDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(max(int(page_size or 10), 1), 50)
        filters = filters or {}
        user_bid = str(filters.get("user_bid", "") or "").strip()
        outline_item_bid = str(filters.get("outline_item_bid", "") or "").strip()
        mode_filter = _resolve_course_credit_usage_mode_filter(
            str(filters.get("mode", "") or "")
        )
        scene_filter = _resolve_course_credit_usage_scene_filter(
            str(filters.get("usage_scene", "") or "")
        )
        if not user_bid:
            raise_param_error("user_bid")
        if not outline_item_bid:
            raise_param_error("outline_item_bid")
        if str(filters.get("mode", "") or "").strip() and not mode_filter:
            raise_param_error("mode")
        if str(filters.get("usage_scene", "") or "").strip() and not scene_filter:
            raise_param_error("usage_scene")

        _detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        visible_leaf_outline_bids = _resolve_visible_leaf_outline_bids(outline_items)
        query = _build_operator_course_credit_usage_base_query(
            normalized_shifu_bid,
            outline_item_bids=visible_leaf_outline_bids,
        )
        query = query.filter(
            BillUsageRecord.user_bid == user_bid,
            BillUsageRecord.outline_item_bid == outline_item_bid,
        )
        query = _apply_course_credit_usage_filters(
            query, {"mode": mode_filter, "usage_scene": scene_filter}
        )

        total = query.count()
        rows = (
            query.order_by(BillUsageRecord.created_at.desc(), BillUsageRecord.id.desc())
            .offset((safe_page_index - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        output_summary_map = _load_course_credit_usage_output_summary_map(
            [usage_row for usage_row, _ledger_amount in rows]
        )
        return AdminOperationCourseCreditUsageDetailListDTO(
            items=[
                _build_operator_course_credit_usage_detail_item(
                    usage_row=usage_row,
                    ledger_amount=ledger_amount,
                    output_summary=output_summary_map.get(
                        str(getattr(usage_row, "usage_bid", "") or "").strip(),
                        "",
                    ),
                )
                for usage_row, ledger_amount in rows
            ],
            page=safe_page_index,
            page_size=safe_page_size,
            total=total,
            page_count=math.ceil(total / safe_page_size) if safe_page_size else 0,
        )


def _load_bill_usage_record_map(
    usage_bids: Sequence[str],
) -> Dict[str, BillUsageRecord]:
    normalized_usage_bids = sorted(
        {
            str(usage_bid or "").strip()
            for usage_bid in usage_bids
            if str(usage_bid or "").strip()
        }
    )
    if not normalized_usage_bids:
        return {}

    rows = (
        BillUsageRecord.query.filter(
            BillUsageRecord.deleted == 0,
            BillUsageRecord.usage_bid.in_(normalized_usage_bids),
        )
        .order_by(BillUsageRecord.id.desc())
        .all()
    )
    usage_map: Dict[str, BillUsageRecord] = {}
    for row in rows:
        usage_bid = str(row.usage_bid or "").strip()
        if usage_bid and usage_bid not in usage_map:
            usage_map[usage_bid] = row
    return usage_map


def _build_latest_bill_usage_record_subquery(
    *,
    user_bid: str = "",
    usage_bids: Sequence[str] | None = None,
):
    normalized_user_bid = str(user_bid or "").strip()
    normalized_usage_bids = [
        str(usage_bid or "").strip()
        for usage_bid in usage_bids or []
        if str(usage_bid or "").strip()
    ]
    query = db.session.query(
        BillUsageRecord.usage_bid.label("usage_bid"),
        db.func.max(BillUsageRecord.id).label("max_id"),
    ).filter(
        BillUsageRecord.deleted == 0,
        BillUsageRecord.record_level == 0,
    )
    if normalized_user_bid:
        query = query.filter(BillUsageRecord.user_bid == normalized_user_bid)
    if usage_bids is not None and not normalized_usage_bids:
        query = query.filter(false())
    if normalized_usage_bids:
        query = query.filter(BillUsageRecord.usage_bid.in_(normalized_usage_bids))
    return query.group_by(BillUsageRecord.usage_bid).subquery()
