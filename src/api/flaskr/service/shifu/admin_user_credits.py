"""Operator user credit summary, ledger, and usage detail helpers.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

import json
from datetime import datetime

from flaskr.util.datetime import now_utc
from decimal import Decimal
from json import JSONDecodeError
from typing import Any, Dict, Optional, Sequence
from flask import current_app
from sqlalchemy import case, not_, or_
from flaskr.dao import db
from flaskr.service.billing.bucket_categories import (
    resolve_wallet_bucket_runtime_category,
    wallet_bucket_requires_active_subscription,
)
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_LABELS,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.billing.primitives import (
    credit_decimal_to_number,
    quantize_credit_amount as _quantize_credit_amount,
    safe_int as _safe_int,
)
from flaskr.service.billing.queries import (
    _ACTIVE_SUBSCRIPTION_STATUSES,
    load_primary_active_subscription,
)
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
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseCreditUsageDetailItemDTO,
    AdminOperationCourseCreditUsageItemDTO,
)
from flaskr.service.shifu.admin_dtos_users import (
    AdminOperationUserCreditLedgerItemDTO,
    AdminOperationUserCreditSummaryDTO,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.models import (
    UserInfo as UserEntity,
)

from flaskr.service.shifu.admin_course_summaries import (
    _load_latest_courses_by_shifu_bids,
    _merge_courses,
)

# The legacy flaskr.service.shifu.admin module bound these names from
# admin_operations.courses at import time; keep the same implementations.
from flaskr.service.shifu.admin_operations.courses_credit_usage import (
    _build_credit_usage_user_keyword_filter,
    _build_latest_bill_usage_record_subquery,
)
from flaskr.service.shifu.admin_operations.courses_shared import (
    _build_course_outline_context_map,
    _load_latest_outline_items,
)
from flaskr.service.shifu.admin_shared import (
    COURSE_CREDIT_USAGE_MODE_ASK,
    COURSE_CREDIT_USAGE_MODE_LEARN,
    COURSE_CREDIT_USAGE_MODE_LISTEN,
    COURSE_CREDIT_USAGE_SCENE_DEBUG,
    COURSE_CREDIT_USAGE_SCENE_LEARNING,
    COURSE_CREDIT_USAGE_SCENE_PREVIEW,
    COURSE_CREDIT_USAGE_VIEW_GROUPED,
    COURSE_CREDIT_USAGE_VIEW_RAW,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCES,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_FILTER_TYPES,
    OPERATOR_USER_CREDIT_GRANT_SOURCES,
    OPERATOR_USER_CREDIT_TYPE_ALL,
    _format_decimal,
    _normalize_metadata_json,
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


def _load_active_subscription_end_map(
    creator_bids: Sequence[str],
    *,
    as_of: datetime,
) -> Dict[str, datetime]:
    normalized_creator_bids = [
        str(creator_bid or "").strip() for creator_bid in creator_bids if creator_bid
    ]
    if not normalized_creator_bids:
        return {}
    # One IN(...) query for the whole page instead of one round trip per
    # creator; the per-creator "primary" pick below mirrors the ordering of
    # load_primary_active_subscription (product sort order, then latest
    # period end, then latest created/id).
    product_sort_order = case(
        (BillingProduct.sort_order.is_(None), -1),
        else_=BillingProduct.sort_order,
    )
    rows = (
        db.session.query(
            BillingSubscription.creator_bid,
            BillingSubscription.current_period_end_at,
            product_sort_order.label("product_sort_order"),
            BillingSubscription.created_at,
            BillingSubscription.id,
        )
        .outerjoin(
            BillingProduct,
            (BillingProduct.product_bid == BillingSubscription.product_bid)
            & (BillingProduct.deleted == 0),
        )
        .filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid.in_(normalized_creator_bids),
            BillingSubscription.status.in_(_ACTIVE_SUBSCRIPTION_STATUSES),
            (
                BillingSubscription.current_period_start_at.is_(None)
                | (BillingSubscription.current_period_start_at <= as_of)
            ),
            BillingSubscription.current_period_end_at.isnot(None),
            BillingSubscription.current_period_end_at > as_of,
        )
        .all()
    )
    best_by_creator: Dict[str, tuple] = {}
    for row in rows:
        sort_key = (
            row.product_sort_order if row.product_sort_order is not None else -1,
            row.current_period_end_at,
            row.created_at or datetime.min,
            row.id,
        )
        current = best_by_creator.get(row.creator_bid)
        if current is None or sort_key > current[0]:
            best_by_creator[row.creator_bid] = (sort_key, row.current_period_end_at)
    return {
        creator_bid: period_end
        for creator_bid, (_, period_end) in best_by_creator.items()
    }


def _load_active_subscription_product_display_name_i18n_key(
    creator_bid: str,
    *,
    as_of: datetime,
) -> str:
    subscription = load_primary_active_subscription(creator_bid, as_of=as_of)
    if subscription is None:
        return ""

    normalized_product_bid = str(subscription.product_bid or "").strip()
    if not normalized_product_bid:
        return ""

    product = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == normalized_product_bid,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )
    return str(getattr(product, "display_name_i18n_key", "") or "").strip()


def _load_billing_order_map(source_bids: Sequence[str]) -> Dict[str, BillingOrder]:
    normalized_source_bids = [
        str(source_bid or "").strip()
        for source_bid in source_bids
        if str(source_bid or "").strip()
    ]
    if not normalized_source_bids:
        return {}

    rows = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.bill_order_bid.in_(normalized_source_bids),
        )
        .order_by(BillingOrder.id.desc())
        .all()
    )
    order_map: Dict[str, BillingOrder] = {}
    for row in rows:
        normalized_source_bid = str(row.bill_order_bid or "").strip()
        if normalized_source_bid and normalized_source_bid not in order_map:
            order_map[normalized_source_bid] = row
    return order_map


def _collect_operator_user_credit_order_source_bids(
    ledger_rows: Sequence[CreditLedgerEntry],
) -> list[str]:
    return [
        str(row.source_bid or "").strip()
        for row in ledger_rows
        if _operator_credit_int(row.source_type)
        in {
            CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            CREDIT_SOURCE_TYPE_TOPUP,
        }
        and str(row.source_bid or "").strip()
    ]


def _resolve_operator_credit_usage_scene(metadata: Dict[str, Any]) -> int:
    raw_usage_scene = metadata.get("usage_scene")
    try:
        return int(raw_usage_scene or 0)
    except (TypeError, ValueError):
        return 0


def _operator_credit_int(value: Any, default: int = 0) -> int:
    candidate = _safe_int(value)
    return candidate if candidate is not None else default


def _resolve_operator_credit_display_entry_type(
    row: CreditLedgerEntry,
    *,
    metadata: Dict[str, Any],
) -> str:
    usage_scene = _resolve_operator_credit_usage_scene(metadata)
    amount = Decimal(row.amount or 0)
    entry_type = _operator_credit_int(row.entry_type)
    source_type = _operator_credit_int(row.source_type)

    if entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT:
        if source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
            checkout_type = str(metadata.get("checkout_type") or "").strip().lower()
            if checkout_type == "trial_bootstrap":
                return "trial_subscription_grant"
            return "subscription_grant"
        if source_type == CREDIT_SOURCE_TYPE_TOPUP:
            return "topup_grant"
        if source_type == CREDIT_SOURCE_TYPE_GIFT:
            return "gift_grant"
        if source_type == CREDIT_SOURCE_TYPE_MANUAL:
            grant_type = str(metadata.get("grant_type") or "").strip().lower()
            if grant_type == "manual_grant":
                return "manual_grant"
            return "manual_credit" if amount >= 0 else "manual_debit"
        return "grant"

    if entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME:
        if source_type == CREDIT_SOURCE_TYPE_USAGE:
            if usage_scene == BILL_USAGE_SCENE_PREVIEW:
                return "preview_consume"
            if usage_scene == BILL_USAGE_SCENE_DEBUG:
                return "debug_consume"
            if usage_scene == BILL_USAGE_SCENE_PROD:
                return "learning_consume"
        return "consume"

    if entry_type == CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT:
        if amount > 0:
            return "manual_credit"
        if amount < 0:
            return "manual_debit"
        return "adjustment"

    if entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE:
        if source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
            return "subscription_expire"
        if source_type == CREDIT_SOURCE_TYPE_TOPUP:
            return "topup_expire"
        if source_type == CREDIT_SOURCE_TYPE_GIFT:
            return "gift_expire"
        return "expire"

    if entry_type == CREDIT_LEDGER_ENTRY_TYPE_REFUND:
        return "refund_return"

    return CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant")


def _resolve_operator_credit_display_source_type(
    row: CreditLedgerEntry,
    *,
    metadata: Dict[str, Any],
) -> str:
    source_type = _operator_credit_int(row.source_type)
    if source_type == CREDIT_SOURCE_TYPE_USAGE:
        usage_scene = _resolve_operator_credit_usage_scene(metadata)
        if usage_scene == BILL_USAGE_SCENE_PREVIEW:
            return "preview"
        if usage_scene == BILL_USAGE_SCENE_DEBUG:
            return "debug"
        if usage_scene == BILL_USAGE_SCENE_PROD:
            return "learning"
        return "usage"

    if source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
        checkout_type = str(metadata.get("checkout_type") or "").strip().lower()
        if checkout_type == "trial_bootstrap":
            return "trial_subscription"
        return "subscription"
    if source_type == CREDIT_SOURCE_TYPE_TOPUP:
        return "topup"
    if source_type == CREDIT_SOURCE_TYPE_GIFT:
        return "gift"
    if source_type == CREDIT_SOURCE_TYPE_REFUND:
        return "refund"
    if source_type == CREDIT_SOURCE_TYPE_MANUAL:
        grant_source = str(metadata.get("grant_source") or "").strip().lower()
        if grant_source in OPERATOR_USER_CREDIT_GRANT_SOURCES:
            return grant_source
        return "manual"
    return CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual")


def _resolve_operator_credit_note_code(
    row: CreditLedgerEntry,
    *,
    metadata: Dict[str, Any],
) -> str:
    note = str(metadata.get("note") or "").strip()
    if note:
        return ""

    checkout_type = str(metadata.get("checkout_type") or "").strip().lower()
    if checkout_type == "trial_bootstrap":
        return "trial_bootstrap"
    if checkout_type == "subscription_renewal":
        return "subscription_renewal"
    if checkout_type == "subscription":
        return "subscription_purchase"
    if checkout_type == "topup":
        return "topup_purchase"
    if checkout_type == "admin_manual_plan_grant":
        return "admin_manual_plan_grant"
    if checkout_type == "manual_grant":
        return "manual_grant"
    grant_type = str(metadata.get("grant_type") or "").strip().lower()
    if grant_type == "manual_grant":
        return "manual_grant"

    reason = str(metadata.get("reason") or "").strip().lower()
    if reason == "subscription_cycle_transition":
        return "subscription_cycle_transition"

    if metadata.get("refund_return"):
        return "refund_return"

    display_entry_type = _resolve_operator_credit_display_entry_type(
        row,
        metadata=metadata,
    )
    if display_entry_type in {
        "learning_consume",
        "preview_consume",
        "debug_consume",
        "manual_credit",
        "manual_debit",
        "manual_grant",
        "subscription_grant",
        "trial_subscription_grant",
        "topup_grant",
        "gift_grant",
        "subscription_expire",
        "topup_expire",
        "gift_expire",
        "refund_return",
    }:
        return display_entry_type

    return ""


def _resolve_operator_user_credit_type_filter(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", *OPERATOR_USER_CREDIT_FILTER_TYPES}:
        return normalized or OPERATOR_USER_CREDIT_TYPE_ALL
    return ""


def _resolve_operator_user_credit_grant_source_filter(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", *OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCES}:
        return normalized or OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL
    return ""


def _build_operator_user_credit_merged_metadata(
    row: CreditLedgerEntry,
    *,
    order_map: Optional[Dict[str, BillingOrder]] = None,
) -> Dict[str, Any]:
    metadata = _normalize_metadata_json(row.metadata_json)
    normalized_source_bid = str(row.source_bid or "").strip()
    order = (order_map or {}).get(normalized_source_bid)
    order_metadata = _normalize_metadata_json(order.metadata_json if order else None)
    return {**order_metadata, **metadata}


def _is_operator_user_credit_grant_row(row: CreditLedgerEntry) -> bool:
    amount = Decimal(row.amount or 0)
    entry_type = _operator_credit_int(row.entry_type)
    if entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT:
        return True
    return entry_type == CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT and amount > 0


def _is_operator_user_credit_consume_row(row: CreditLedgerEntry) -> bool:
    return (
        _operator_credit_int(row.entry_type) == CREDIT_LEDGER_ENTRY_TYPE_CONSUME
        and _operator_credit_int(row.source_type) == CREDIT_SOURCE_TYPE_USAGE
    )


def _is_operator_user_credit_other_row(row: CreditLedgerEntry) -> bool:
    amount = Decimal(row.amount or 0)
    entry_type = _operator_credit_int(row.entry_type)
    if entry_type in {
        CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    }:
        return True
    return entry_type == CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT and amount < 0


def _resolve_operator_user_credit_grant_filter_key(
    row: CreditLedgerEntry,
    *,
    metadata: Dict[str, Any],
) -> str:
    source_type = _operator_credit_int(row.source_type)
    if source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
        checkout_type = str(metadata.get("checkout_type") or "").strip().lower()
        if checkout_type == "trial_bootstrap":
            return OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION
        return OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_SUBSCRIPTION
    if source_type == CREDIT_SOURCE_TYPE_TOPUP:
        return OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP
    if source_type == CREDIT_SOURCE_TYPE_MANUAL:
        return OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL
    return ""


def _load_operator_user_credit_summary_map(
    user_bids: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    now = now_utc()
    active_subscription_end_map = _load_active_subscription_end_map(
        normalized_user_bids,
        as_of=now,
    )
    buckets = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid.in_(normalized_user_bids),
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
            CreditWalletBucket.available_credits > 0,
            or_(
                CreditWalletBucket.effective_from.is_(None),
                CreditWalletBucket.effective_from <= now,
            ),
            or_(
                CreditWalletBucket.effective_to.is_(None),
                CreditWalletBucket.effective_to > now,
            ),
        )
        .order_by(CreditWalletBucket.creator_bid.asc(), CreditWalletBucket.id.asc())
        .all()
    )

    zero = Decimal("0")
    summary_map: Dict[str, Dict[str, Any]] = {}
    order_map = _load_billing_order_map(
        [str(bucket.source_bid or "").strip() for bucket in buckets]
    )
    order_type_cache: Dict[str, Optional[int]] = {
        bill_order_bid: int(order.order_type or 0)
        for bill_order_bid, order in order_map.items()
    }

    def load_order_type(bill_order_bid: str) -> Optional[int]:
        normalized_bill_order_bid = str(bill_order_bid or "").strip()
        if not normalized_bill_order_bid:
            return None
        return order_type_cache.get(normalized_bill_order_bid)

    for bucket in buckets:
        creator_bid = str(bucket.creator_bid or "").strip()
        if not creator_bid:
            continue
        available_credits = Decimal(bucket.available_credits or 0)
        if available_credits <= zero:
            continue

        summary = summary_map.setdefault(
            creator_bid,
            {
                "available_credits": zero,
                "subscription_credits": zero,
                "topup_credits": zero,
                "credits_expire_at": None,
                "has_active_subscription": False,
            },
        )
        if creator_bid in active_subscription_end_map:
            summary["has_active_subscription"] = True
        runtime_category = resolve_wallet_bucket_runtime_category(
            bucket,
            load_order_type=load_order_type,
        )
        if runtime_category == CREDIT_BUCKET_CATEGORY_TOPUP:
            summary["topup_credits"] += available_credits
        else:
            summary["subscription_credits"] += available_credits
        if (
            creator_bid in active_subscription_end_map
            or not wallet_bucket_requires_active_subscription(
                bucket,
                load_order_type=load_order_type,
            )
        ):
            summary["available_credits"] += available_credits

        effective_to = bucket.effective_to
        if creator_bid in active_subscription_end_map:
            summary["credits_expire_at"] = active_subscription_end_map[creator_bid]
            continue
        if (
            _operator_credit_int(bucket.source_type) != CREDIT_SOURCE_TYPE_MANUAL
            or not effective_to
        ):
            continue
        if (
            summary["credits_expire_at"] is None
            or effective_to < summary["credits_expire_at"]
        ):
            summary["credits_expire_at"] = effective_to

    for creator_bid, effective_to in active_subscription_end_map.items():
        summary = summary_map.setdefault(
            creator_bid,
            {
                "available_credits": zero,
                "subscription_credits": zero,
                "topup_credits": zero,
                "credits_expire_at": None,
                "has_active_subscription": True,
            },
        )
        summary["credits_expire_at"] = effective_to
        summary["has_active_subscription"] = True

    return summary_map


def _build_operator_user_credit_summary(
    *,
    user: UserEntity,
    credit_summary_map: Dict[str, Dict[str, Any]],
) -> AdminOperationUserCreditSummaryDTO:
    user_bid = str(user.user_bid or "").strip()
    credit_summary = credit_summary_map.get(user_bid)
    has_credit_account = bool(user.is_creator) or credit_summary is not None
    return AdminOperationUserCreditSummaryDTO(
        available_credits=(
            _format_decimal((credit_summary or {}).get("available_credits"))
            if has_credit_account
            else ""
        ),
        subscription_credits=(
            _format_decimal((credit_summary or {}).get("subscription_credits"))
            if has_credit_account
            else ""
        ),
        topup_credits=(
            _format_decimal((credit_summary or {}).get("topup_credits"))
            if has_credit_account
            else ""
        ),
        credits_expire_at=(
            (credit_summary or {}).get("credits_expire_at")
            if has_credit_account
            else None
        ),
        has_active_subscription=bool(
            (credit_summary or {}).get("has_active_subscription", False)
        ),
    )


def _resolve_operator_user_credit_usage_scene(row: BillUsageRecord) -> str:
    usage_scene = int(getattr(row, "usage_scene", 0) or 0)
    if usage_scene == BILL_USAGE_SCENE_DEBUG:
        return "debug"
    if usage_scene == BILL_USAGE_SCENE_PREVIEW:
        return "preview"
    if usage_scene == BILL_USAGE_SCENE_PROD:
        return "learning"
    return ""


def _load_operator_user_credit_usage_context_map(
    ledger_rows: Sequence[CreditLedgerEntry],
) -> Dict[str, Dict[str, str]]:
    usage_bids = sorted(
        {
            str(row.source_bid or "").strip()
            for row in ledger_rows
            if row.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME
            and row.source_type == CREDIT_SOURCE_TYPE_USAGE
            and str(row.source_bid or "").strip()
        }
    )
    if not usage_bids:
        return {}

    latest_usage_subquery = _build_latest_bill_usage_record_subquery(
        usage_bids=usage_bids
    )
    usage_rows = (
        db.session.query(BillUsageRecord)
        .join(
            latest_usage_subquery, latest_usage_subquery.c.max_id == BillUsageRecord.id
        )
        .filter(latest_usage_subquery.c.usage_bid.in_(usage_bids))
        .all()
    )
    if not usage_rows:
        return {}

    shifu_bids = sorted(
        {
            str(getattr(row, "shifu_bid", "") or "").strip()
            for row in usage_rows
            if str(getattr(row, "shifu_bid", "") or "").strip()
        }
    )
    drafts = _load_latest_courses_by_shifu_bids(DraftShifu, shifu_bids)
    published = _load_latest_courses_by_shifu_bids(PublishedShifu, shifu_bids)
    merged_courses, _published_bids, selected_sources = _merge_courses(
        drafts,
        published,
    )
    course_map = {
        str(getattr(course, "shifu_bid", "") or "").strip(): course
        for course in merged_courses
        if str(getattr(course, "shifu_bid", "") or "").strip()
    }

    outline_context_by_course: Dict[str, Dict[str, Dict[str, str]]] = {}
    for shifu_bid in shifu_bids:
        source = selected_sources.get(shifu_bid)
        if not source:
            continue
        outline_model = DraftOutlineItem if source == "draft" else PublishedOutlineItem
        outline_context_by_course[shifu_bid] = _build_course_outline_context_map(
            _load_latest_outline_items(outline_model, shifu_bid)
        )

    context_map: Dict[str, Dict[str, str]] = {}
    for usage_row in usage_rows:
        usage_bid = str(getattr(usage_row, "usage_bid", "") or "").strip()
        shifu_bid = str(getattr(usage_row, "shifu_bid", "") or "").strip()
        outline_item_bid = str(getattr(usage_row, "outline_item_bid", "") or "").strip()
        if not usage_bid:
            continue
        course = course_map.get(shifu_bid)
        outline_context = outline_context_by_course.get(shifu_bid, {}).get(
            outline_item_bid,
            {},
        )
        context_map[usage_bid] = {
            "usage_bid": usage_bid,
            "course_bid": shifu_bid,
            "course_name": (
                str(getattr(course, "title", "") or "").strip() if course else ""
            ),
            "chapter_title": str(outline_context.get("chapter_title", "") or ""),
            "lesson_title": str(outline_context.get("lesson_title", "") or ""),
            "usage_scene": _resolve_operator_user_credit_usage_scene(usage_row),
            "usage_mode": _resolve_course_credit_usage_mode(usage_row),
        }

    return context_map


def _resolve_operator_user_credit_usage_context(
    usage_row: BillUsageRecord,
) -> Dict[str, str]:
    usage_bid = str(getattr(usage_row, "usage_bid", "") or "").strip()
    shifu_bid = str(getattr(usage_row, "shifu_bid", "") or "").strip()
    outline_item_bid = str(getattr(usage_row, "outline_item_bid", "") or "").strip()
    course_name = ""
    chapter_title = ""
    lesson_title = ""

    if shifu_bid:
        drafts = _load_latest_courses_by_shifu_bids(DraftShifu, [shifu_bid])
        published = _load_latest_courses_by_shifu_bids(PublishedShifu, [shifu_bid])
        merged_courses, _published_bids, selected_sources = _merge_courses(
            drafts,
            published,
        )
        if merged_courses:
            course_name = str(getattr(merged_courses[0], "title", "") or "").strip()

        source = selected_sources.get(shifu_bid)
        if source:
            outline_model = (
                DraftOutlineItem if source == "draft" else PublishedOutlineItem
            )
            outline_context = _build_course_outline_context_map(
                _load_latest_outline_items(outline_model, shifu_bid)
            ).get(outline_item_bid, {})
            chapter_title = str(outline_context.get("chapter_title", "") or "")
            lesson_title = str(outline_context.get("lesson_title", "") or "")

    return {
        "usage_bid": usage_bid,
        "course_bid": shifu_bid,
        "course_name": course_name,
        "chapter_title": chapter_title,
        "lesson_title": lesson_title,
        "usage_scene": _resolve_operator_user_credit_usage_scene(usage_row),
        "usage_mode": _resolve_course_credit_usage_mode(usage_row),
    }


def _load_operator_user_credit_usage_owner_ledger_rows(
    *,
    user_bid: str,
    usage_bid: str,
) -> list[CreditLedgerEntry]:
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == user_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_USAGE,
            CreditLedgerEntry.source_bid == usage_bid,
        )
        .order_by(CreditLedgerEntry.id.asc())
        .all()
    )


def _load_operator_user_credit_usage_main_row(
    usage_bid: str,
) -> BillUsageRecord | None:
    normalized_usage_bid = str(usage_bid or "").strip()
    if not normalized_usage_bid:
        return None
    return (
        BillUsageRecord.query.filter(
            BillUsageRecord.deleted == 0,
            BillUsageRecord.usage_bid == normalized_usage_bid,
        )
        .order_by(
            BillUsageRecord.record_level.asc(),
            BillUsageRecord.id.desc(),
        )
        .first()
    )


def _load_operator_user_credit_usage_segment_rows(
    usage_bid: str,
) -> list[BillUsageRecord]:
    normalized_usage_bid = str(usage_bid or "").strip()
    if not normalized_usage_bid:
        return []
    return (
        BillUsageRecord.query.filter(
            BillUsageRecord.deleted == 0,
            BillUsageRecord.parent_usage_bid == normalized_usage_bid,
            BillUsageRecord.record_level == 1,
        )
        .order_by(
            BillUsageRecord.segment_index.asc(),
            BillUsageRecord.created_at.asc(),
            BillUsageRecord.id.asc(),
        )
        .all()
    )


def _load_generated_block_content_map(
    generated_block_bids: Sequence[str],
) -> Dict[str, str]:
    normalized_bids = sorted(
        {
            str(generated_block_bid or "").strip()
            for generated_block_bid in generated_block_bids
            if str(generated_block_bid or "").strip()
        }
    )
    if not normalized_bids:
        return {}
    rows = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid.in_(normalized_bids),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        )
        .order_by(LearnGeneratedBlock.id.desc())
        .all()
    )
    content_map: Dict[str, str] = {}
    for row in rows:
        generated_block_bid = str(row.generated_block_bid or "").strip()
        if generated_block_bid and generated_block_bid not in content_map:
            content_map[generated_block_bid] = str(row.generated_content or "").strip()
    return content_map


def _load_listen_segment_content_map(
    *,
    progress_record_bid: str,
    generated_block_bid: str,
) -> Dict[int, str]:
    normalized_progress_record_bid = str(progress_record_bid or "").strip()
    normalized_generated_block_bid = str(generated_block_bid or "").strip()
    if not normalized_progress_record_bid and not normalized_generated_block_bid:
        return {}

    query = LearnGeneratedElement.query.filter(
        LearnGeneratedElement.deleted == 0,
        LearnGeneratedElement.status == 1,
        LearnGeneratedElement.event_type == "element",
        LearnGeneratedElement.is_speakable == 1,
    )
    if normalized_generated_block_bid:
        query = query.filter(
            LearnGeneratedElement.generated_block_bid == normalized_generated_block_bid
        )
    if normalized_progress_record_bid:
        query = query.filter(
            LearnGeneratedElement.progress_record_bid == normalized_progress_record_bid
        )
    rows = query.order_by(
        LearnGeneratedElement.sequence_number.asc(),
        LearnGeneratedElement.run_event_seq.asc(),
        LearnGeneratedElement.id.asc(),
    ).all()

    content_map: Dict[int, str] = {}
    fallback_index = 0
    for row in rows:
        content = str(row.content_text or "").strip()
        if not content:
            continue
        segment_indices: list[int] = []
        raw_audio_segments = str(row.audio_segments or "").strip()
        if raw_audio_segments:
            try:
                audio_segments = json.loads(raw_audio_segments)
            except JSONDecodeError:
                current_app.logger.warning(
                    "Invalid listen audio_segments JSON for generated element %s",
                    getattr(row, "element_bid", ""),
                    exc_info=True,
                )
                audio_segments = []
            if isinstance(audio_segments, list):
                for item in audio_segments:
                    if not isinstance(item, dict):
                        continue
                    segment_index = _safe_int(item.get("segment_index", 0))
                    if segment_index is None:
                        continue
                    segment_indices.append(segment_index)
        if not segment_indices:
            segment_indices = [fallback_index]
            fallback_index += 1
        for segment_index in segment_indices:
            content_map.setdefault(segment_index, content)
    return content_map


def _allocate_usage_detail_credits(
    *,
    rows: Sequence[BillUsageRecord],
    total_consumed_credits: Decimal,
) -> Dict[str, Decimal]:
    if not rows or total_consumed_credits <= 0:
        return {}
    total_units = sum(max(int(getattr(row, "total", 0) or 0), 0) for row in rows)
    if len(rows) == 1 or total_units <= 0:
        return {str(getattr(rows[0], "usage_bid", "") or ""): total_consumed_credits}

    allocated: Dict[str, Decimal] = {}
    remaining = total_consumed_credits
    last_usage_bid = str(getattr(rows[-1], "usage_bid", "") or "")
    for row in rows[:-1]:
        usage_bid = str(getattr(row, "usage_bid", "") or "")
        ratio = Decimal(max(int(getattr(row, "total", 0) or 0), 0)) / Decimal(
            total_units
        )
        amount = _quantize_credit_amount(total_consumed_credits * ratio)
        allocated[usage_bid] = amount
        remaining -= amount
    allocated[last_usage_bid] = _quantize_credit_amount(remaining)
    return allocated


def _resolve_usage_detail_item_content(
    row: BillUsageRecord,
    *,
    block_content_map: Dict[str, str],
    listen_content_map: Dict[int, str],
    fallback_content: str,
) -> str:
    metadata = _normalize_metadata_json(getattr(row, "extra", None))
    for key in ("segment_text", "text", "content", "output_text"):
        value = str(metadata.get(key, "") or "").strip()
        if value:
            return value
    generated_block_bid = str(getattr(row, "generated_block_bid", "") or "").strip()
    segment_index = int(getattr(row, "segment_index", 0) or 0)
    return (
        listen_content_map.get(segment_index, "")
        or block_content_map.get(generated_block_bid, "")
        or fallback_content
    )


def _build_operator_user_credit_ledger_item(
    row: CreditLedgerEntry,
    *,
    order_map: Optional[Dict[str, BillingOrder]] = None,
    usage_context_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> AdminOperationUserCreditLedgerItemDTO:
    merged_metadata = _build_operator_user_credit_merged_metadata(
        row,
        order_map=order_map,
    )
    usage_context = (usage_context_map or {}).get(
        str(row.source_bid or "").strip(),
        {},
    )
    return AdminOperationUserCreditLedgerItemDTO(
        ledger_bid=str(row.ledger_bid or "").strip(),
        created_at=row.created_at,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant"),
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        display_entry_type=_resolve_operator_credit_display_entry_type(
            row,
            metadata=merged_metadata,
        ),
        display_source_type=_resolve_operator_credit_display_source_type(
            row,
            metadata=merged_metadata,
        ),
        amount=_format_decimal(Decimal(row.amount or 0)),
        balance_after=_format_decimal(Decimal(row.balance_after or 0)),
        expires_at=row.expires_at,
        consumable_from=row.consumable_from,
        note=str(merged_metadata.get("note") or "").strip(),
        note_code=_resolve_operator_credit_note_code(
            row,
            metadata=merged_metadata,
        ),
        usage_bid=str(usage_context.get("usage_bid", "") or ""),
        course_bid=str(usage_context.get("course_bid", "") or ""),
        course_name=str(usage_context.get("course_name", "") or ""),
        chapter_title=str(usage_context.get("chapter_title", "") or ""),
        lesson_title=str(usage_context.get("lesson_title", "") or ""),
        usage_scene=str(usage_context.get("usage_scene", "") or ""),
        usage_mode=str(usage_context.get("usage_mode", "") or ""),
    )
