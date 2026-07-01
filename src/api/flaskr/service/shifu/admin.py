from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from json import JSONDecodeError
from typing import Any, Dict, Iterable, Optional, Sequence, Set

from flask import current_app
from sqlalchemy import and_, case, literal, not_, or_
from sqlalchemy.orm import defer

from flaskr.common.umami_client import get_course_visit_count_30d
from flaskr.i18n import _
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
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.billing.primitives import (
    credit_decimal_to_number,
    quantize_credit_amount as _quantize_credit_amount,
    safe_int as _safe_int,
)
from flaskr.service.billing.queries import load_primary_active_subscription
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.learn.const import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.common.models import (
    raise_error,
    raise_error_with_args,
    raise_param_error,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos import (
    AdminOperationCourseCreditUsageDetailItemDTO,
    AdminOperationCourseCreditUsageItemDTO,
    AdminOperationCourseSummaryDTO,
    AdminOperationUserCreditLedgerItemDTO,
    AdminOperationUserCreditSummaryDTO,
    AdminOperationUserCourseSummaryDTO,
    AdminOperationUserSummaryDTO,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    SHIFU_NAME_MAX_LENGTH,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.course_activity import load_course_activity_map
from flaskr.service.shifu.demo_courses import (
    is_builtin_demo_course,
    load_builtin_demo_titles,
    load_demo_shifu_bids,
)
from flaskr.service.shifu.shifu_draft_funcs import (
    check_text_with_risk_control,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
    UserToken,
)
from flaskr.service.user.utils import (
    run_creator_granted_post_auth,
)
from markdown_flow import MarkdownFlow

COURSE_STATUS_PUBLISHED = "published"
COURSE_STATUS_UNPUBLISHED = "unpublished"
COURSE_QUICK_FILTER_DRAFT = "draft"
COURSE_QUICK_FILTER_PUBLISHED = "published"
COURSE_QUICK_FILTER_CREATED_LAST_7D = "created_last_7d"
COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D = "learning_active_30d"
COURSE_QUICK_FILTER_PAID_ORDER_30D = "paid_order_30d"
COURSE_QUICK_FILTER_VALUES = {
    COURSE_QUICK_FILTER_DRAFT,
    COURSE_QUICK_FILTER_PUBLISHED,
    COURSE_QUICK_FILTER_CREATED_LAST_7D,
    COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D,
    COURSE_QUICK_FILTER_PAID_ORDER_30D,
}
PROMPT_SOURCE_LESSON = "lesson"
PROMPT_SOURCE_CHAPTER = "chapter"
PROMPT_SOURCE_COURSE = "course"
COURSE_USER_LIST_MAX_PAGE_SIZE = 100
COURSE_USER_ROLE_OPERATOR = "operator"
COURSE_USER_ROLE_CREATOR = "creator"
COURSE_USER_ROLE_STUDENT = "student"
COURSE_USER_ROLE_NORMAL = "normal"
COURSE_USER_LEARNING_STATUS_NOT_STARTED = "not_started"
COURSE_USER_LEARNING_STATUS_LEARNING = "learning"
COURSE_USER_LEARNING_STATUS_COMPLETED = "completed"
OPERATOR_USER_STATUS_UNREGISTERED = "unregistered"
OPERATOR_USER_STATUS_REGISTERED = "registered"
OPERATOR_USER_STATUS_TRIAL = "trial"
OPERATOR_USER_STATUS_PAID = "paid"
OPERATOR_USER_STATUS_UNKNOWN = "unknown"
OPERATOR_USER_LIST_MAX_PAGE_SIZE = 100
OPERATOR_ORDER_LIST_MAX_PAGE_SIZE = 100
OPERATOR_USER_ROLE_REGULAR = "regular"
OPERATOR_USER_ROLE_CREATOR = "creator"
OPERATOR_USER_ROLE_OPERATOR = "operator"
OPERATOR_USER_ROLE_LEARNER = "learner"
OPERATOR_USER_QUICK_FILTER_CREATOR = "creator"
OPERATOR_USER_QUICK_FILTER_LEARNER = "learner"
OPERATOR_USER_QUICK_FILTER_REGISTERED = "registered"
OPERATOR_USER_QUICK_FILTER_PAID = "paid"
OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D = "created_last_30d"
OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D = "registered_last_30d"
OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D = "learning_active_30d"
OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D = "paid_last_30d"
OPERATOR_USER_QUICK_FILTER_GUEST = "guest"
OPERATOR_USER_QUICK_FILTER_VALUES = {
    OPERATOR_USER_QUICK_FILTER_CREATOR,
    OPERATOR_USER_QUICK_FILTER_LEARNER,
    OPERATOR_USER_QUICK_FILTER_REGISTERED,
    OPERATOR_USER_QUICK_FILTER_PAID,
    OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D,
    OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_GUEST,
}
OPERATOR_USER_REGISTRATION_CREDENTIAL_PROVIDERS = (
    "phone",
    "email",
    "google",
    "wechat",
)
OPERATOR_USER_REGISTRATION_SOURCE_PHONE = "phone"
OPERATOR_USER_REGISTRATION_SOURCE_EMAIL = "email"
OPERATOR_USER_REGISTRATION_SOURCE_GOOGLE = "google"
OPERATOR_USER_REGISTRATION_SOURCE_WECHAT = "wechat"
OPERATOR_USER_REGISTRATION_SOURCE_IMPORTED = "imported"
OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN = "unknown"
OPERATOR_USER_SUPPORTED_LOGIN_METHOD_PROVIDERS = {
    "phone",
    "email",
    "google",
    "wechat",
}
OPERATOR_USER_SUPPORTED_REGISTRATION_SOURCE_PROVIDERS = (
    OPERATOR_USER_SUPPORTED_LOGIN_METHOD_PROVIDERS | {"manual", "import", "imported"}
)
OPERATOR_USER_PRELOADED_AUTH_CREDENTIAL_PROVIDERS = (
    OPERATOR_USER_SUPPORTED_REGISTRATION_SOURCE_PROVIDERS | {"password"}
)
COURSE_FOLLOW_UP_LIST_MAX_PAGE_SIZE = 100
COURSE_RATING_LIST_MAX_PAGE_SIZE = 100
COURSE_CREDIT_USAGE_LIST_MAX_PAGE_SIZE = 100
COURSE_CREDIT_USAGE_VIEW_GROUPED = "grouped"
COURSE_CREDIT_USAGE_VIEW_RAW = "raw"
COURSE_CREDIT_USAGE_MODE_LEARN = "learn"
COURSE_CREDIT_USAGE_MODE_LISTEN = "listen"
COURSE_CREDIT_USAGE_MODE_ASK = "ask"
COURSE_CREDIT_USAGE_MODE_MIXED = "mixed"
COURSE_CREDIT_USAGE_SCENE_LEARNING = "learning"
COURSE_CREDIT_USAGE_SCENE_PREVIEW = "preview"
COURSE_CREDIT_USAGE_SCENE_DEBUG = "debug"
OPERATOR_USER_CREDIT_GRANT_SOURCE_REWARD = "reward"
OPERATOR_USER_CREDIT_GRANT_SOURCE_COMPENSATION = "compensation"
OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL = "manual_credit"
OPERATOR_USER_CREDIT_GRANT_TYPE_REFERRAL_REWARD = "referral_reward"
OPERATOR_USER_CREDIT_TYPE_ALL = "all"
OPERATOR_USER_CREDIT_TYPE_CONSUME = "consume"
OPERATOR_USER_CREDIT_TYPE_GRANT = "grant"
OPERATOR_USER_CREDIT_TYPE_OTHER = "other"
OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL = "all"
OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_SUBSCRIPTION = "subscription"
OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION = "trial_subscription"
OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP = "topup"
OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL = "manual"
OPERATOR_USER_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION = "align_subscription"
OPERATOR_USER_CREDIT_VALIDITY_1D = "1d"
OPERATOR_USER_CREDIT_VALIDITY_7D = "7d"
OPERATOR_USER_CREDIT_VALIDITY_1M = "1m"
OPERATOR_USER_CREDIT_VALIDITY_3M = "3m"
OPERATOR_USER_CREDIT_VALIDITY_1Y = "1y"

OPERATOR_USER_CREDIT_GRANT_SOURCES = {
    OPERATOR_USER_CREDIT_GRANT_SOURCE_REWARD,
    OPERATOR_USER_CREDIT_GRANT_SOURCE_COMPENSATION,
}
OPERATOR_USER_CREDIT_GRANT_TYPES = {
    OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL,
    OPERATOR_USER_CREDIT_GRANT_TYPE_REFERRAL_REWARD,
}
OPERATOR_USER_CREDIT_FILTER_TYPES = {
    OPERATOR_USER_CREDIT_TYPE_ALL,
    OPERATOR_USER_CREDIT_TYPE_CONSUME,
    OPERATOR_USER_CREDIT_TYPE_GRANT,
    OPERATOR_USER_CREDIT_TYPE_OTHER,
}


def _resolve_operator_credit_grant_type(
    grant_type: str,
    *,
    fallback: str = OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL,
) -> str:
    normalized_grant_type = str(grant_type or "").strip().lower()
    if normalized_grant_type == "manual_grant":
        return OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL
    if normalized_grant_type in OPERATOR_USER_CREDIT_GRANT_TYPES:
        return normalized_grant_type
    return fallback


OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCES = {
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL,
}
OPERATOR_USER_CREDIT_VALIDITY_PRESETS = {
    OPERATOR_USER_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_VALIDITY_1D,
    OPERATOR_USER_CREDIT_VALIDITY_7D,
    OPERATOR_USER_CREDIT_VALIDITY_1M,
    OPERATOR_USER_CREDIT_VALIDITY_3M,
    OPERATOR_USER_CREDIT_VALIDITY_1Y,
}
OPERATOR_TARGET_CONTACT_MAX_LENGTH = 320
OPERATOR_TARGET_PHONE_PATTERN = re.compile(r"^\d{11}$")
OPERATOR_TARGET_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)

USER_STATE_TO_OPERATOR_STATUS = {
    USER_STATE_UNREGISTERED: OPERATOR_USER_STATUS_UNREGISTERED,
    USER_STATE_REGISTERED: OPERATOR_USER_STATUS_REGISTERED,
    USER_STATE_TRAIL: OPERATOR_USER_STATUS_REGISTERED,
    USER_STATE_PAID: OPERATOR_USER_STATUS_PAID,
    str(USER_STATE_UNREGISTERED): OPERATOR_USER_STATUS_UNREGISTERED,
    str(USER_STATE_REGISTERED): OPERATOR_USER_STATUS_REGISTERED,
    str(USER_STATE_TRAIL): OPERATOR_USER_STATUS_REGISTERED,
    str(USER_STATE_PAID): OPERATOR_USER_STATUS_PAID,
}


def _format_decimal(value: Optional[Decimal]) -> str:
    if value is None:
        return "0"
    if isinstance(value, str):
        normalized = value
    else:
        normalized = "{0:.2f}".format(value)
    if normalized.endswith(".00"):
        return normalized[:-3]
    return normalized


def _coerce_operator_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            current_app.logger.warning(
                "Failed to parse operator datetime value '%s'",
                value,
            )
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    current_app.logger.warning(
        "Unexpected operator datetime value type '%s'",
        type(value).__name__,
    )
    return None


def _format_average_score(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    return "{0:.1f}".format(value)


def _resolve_course_rating_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"read", "listen"}:
        return normalized
    return ""


def _resolve_course_rating_sort_by(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "latest_desc"}:
        return "latest_desc"
    if normalized == "score_asc":
        return normalized
    return ""


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


def _normalize_metadata_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


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
    subscription_end_map: Dict[str, datetime] = {}
    for creator_bid in normalized_creator_bids:
        subscription = load_primary_active_subscription(creator_bid, as_of=as_of)
        if subscription is None or subscription.current_period_end_at is None:
            continue
        subscription_end_map[creator_bid] = subscription.current_period_end_at
    return subscription_end_map


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


def _normalize_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if "@" in normalized:
        return normalized.lower()
    return normalized


def _load_course_user_contact_map(
    user_bids: Sequence[str],
) -> Dict[str, Dict[str, str]]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    credential_rows = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(normalized_user_bids),
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    contact_map: Dict[str, Dict[str, str]] = {
        user_bid: {"mobile": "", "email": ""} for user_bid in normalized_user_bids
    }
    for credential in credential_rows:
        user_bid = str(credential.user_bid or "").strip()
        if not user_bid:
            continue
        resolved = contact_map.setdefault(user_bid, {"mobile": "", "email": ""})
        identifier = str(credential.identifier or "").strip()
        if (
            credential.provider_name == "phone"
            and not resolved["mobile"]
            and identifier
        ):
            resolved["mobile"] = identifier
        if (
            credential.provider_name in {"email", "google"}
            and not resolved["email"]
            and identifier
        ):
            resolved["email"] = identifier

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(normalized_user_bids),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.asc())
        .all()
    )
    for user in users:
        user_bid = str(user.user_bid or "").strip()
        if not user_bid:
            continue
        resolved = contact_map.setdefault(user_bid, {"mobile": "", "email": ""})
        identify = str(user.user_identify or "").strip()
        if len(identify) == 11 and identify.isdigit() and not resolved["mobile"]:
            resolved["mobile"] = identify
        elif "@" in identify and not resolved["email"]:
            resolved["email"] = identify
    return contact_map


def _load_user_map(user_bids: Sequence[str]) -> Dict[str, Dict[str, str]]:
    if not user_bids:
        return {}

    credentials = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(list(user_bids)),
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            AuthCredential.deleted == 0,
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    phone_map: Dict[str, str] = {}
    email_map: Dict[str, str] = {}
    for credential in credentials:
        user_bid = credential.user_bid or ""
        if not user_bid:
            continue
        if credential.provider_name == "phone" and user_bid not in phone_map:
            phone_map[user_bid] = credential.identifier or ""
        if (
            credential.provider_name in {"email", "google"}
            and user_bid not in email_map
        ):
            email_map[user_bid] = credential.identifier or ""

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(list(user_bids)),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.asc())
        .all()
    )
    user_map: Dict[str, Dict[str, str]] = {}
    for user in users:
        mobile = phone_map.get(user.user_bid, "")
        email = email_map.get(user.user_bid, "")
        identify = user.user_identify or ""
        if not mobile and identify.isdigit():
            mobile = identify
        if not email and "@" in identify:
            email = identify
        user_map[user.user_bid] = {
            "mobile": mobile or "",
            "email": email or "",
            "identify": identify,
            "nickname": user.nickname or "",
        }
    return user_map


def _load_operator_user_last_login_map(
    user_bids: Sequence[str],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    rows = (
        db.session.query(
            UserToken.user_id.label("user_bid"),
            db.func.max(UserToken.created).label("last_login_at"),
        )
        .filter(
            UserToken.user_id.in_(normalized_user_bids),
            UserToken.token != "",
        )
        .group_by(UserToken.user_id)
        .all()
    )
    return {
        str(user_bid or "").strip(): last_login_at
        for user_bid, last_login_at in rows
        if str(user_bid or "").strip() and last_login_at
    }


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

    now = datetime.now()
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


def _resolve_course_user_role(
    *,
    is_creator: bool,
    is_operator: bool,
    is_student: bool,
) -> str:
    if is_operator:
        return COURSE_USER_ROLE_OPERATOR
    if is_creator:
        return COURSE_USER_ROLE_CREATOR
    if is_student:
        return COURSE_USER_ROLE_STUDENT
    return COURSE_USER_ROLE_NORMAL


def _resolve_course_user_learning_status(
    *,
    learned_lesson_count: int,
    total_lesson_count: int,
) -> str:
    if total_lesson_count > 0 and learned_lesson_count >= total_lesson_count:
        return COURSE_USER_LEARNING_STATUS_COMPLETED
    if learned_lesson_count > 0:
        return COURSE_USER_LEARNING_STATUS_LEARNING
    return COURSE_USER_LEARNING_STATUS_NOT_STARTED


def _build_course_order_amount_expr():
    return case(
        (Order.paid_price > 0, Order.paid_price),
        (Order.payable_price > 0, Order.payable_price),
        else_=0,
    )


def _find_matching_creator_bids(keyword: str) -> Optional[Set[str]]:
    normalized = _normalize_identifier(keyword)
    if not normalized:
        return None

    user_bids = {
        row[0]
        for row in db.session.query(UserEntity.user_bid)
        .filter(
            UserEntity.deleted == 0,
            or_(
                UserEntity.user_bid == normalized,
                UserEntity.user_identify == normalized,
            ),
        )
        .all()
        if row and row[0]
    }

    credential_rows = (
        db.session.query(AuthCredential.user_bid)
        .filter(
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email"]),
            AuthCredential.identifier == normalized,
        )
        .all()
    )
    for row in credential_rows:
        if row and row[0]:
            user_bids.add(row[0])

    return user_bids


def _resolve_operator_user_status(raw_state: object) -> str:
    return USER_STATE_TO_OPERATOR_STATUS.get(
        raw_state,
        USER_STATE_TO_OPERATOR_STATUS.get(
            str(raw_state).strip(), OPERATOR_USER_STATUS_UNKNOWN
        ),
    )


def _resolve_operator_user_quick_filter(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if normalized not in OPERATOR_USER_QUICK_FILTER_VALUES:
        raise_param_error("quick_filter")
    return normalized


def _resolve_recent_days_window(
    days: int,
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    safe_days = max(int(days or 0), 1)
    current = now or datetime.now()
    start = (current - timedelta(days=safe_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_of_day = current.replace(hour=23, minute=59, second=59, microsecond=999999)
    end = min(end_of_day, current)
    return start, end


def _build_operator_user_roles(
    *,
    is_creator: bool,
    is_operator: bool,
    is_learner: bool,
) -> list[str]:
    roles: list[str] = []
    if is_operator:
        roles.append(OPERATOR_USER_ROLE_OPERATOR)
    if is_creator:
        roles.append(OPERATOR_USER_ROLE_CREATOR)
    if is_learner:
        roles.append(OPERATOR_USER_ROLE_LEARNER)
    if not roles:
        roles.append(OPERATOR_USER_ROLE_REGULAR)
    return roles


def _resolve_operator_user_role(
    *,
    is_creator: bool,
    is_operator: bool,
    is_learner: bool,
) -> str:
    return _build_operator_user_roles(
        is_creator=is_creator,
        is_operator=is_operator,
        is_learner=is_learner,
    )[0]


def _build_learner_user_bid_subquery():
    order_query = db.session.query(Order.user_bid.label("user_bid")).filter(
        Order.deleted == 0,
        Order.status == ORDER_STATUS_SUCCESS,
        Order.user_bid != "",
    )
    progress_query = db.session.query(
        LearnProgressRecord.user_bid.label("user_bid")
    ).filter(
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
        LearnProgressRecord.user_bid != "",
    )
    permission_query = db.session.query(AiCourseAuth.user_id.label("user_bid")).filter(
        AiCourseAuth.status == 1,
        AiCourseAuth.user_id != "",
    )
    return order_query.union(progress_query, permission_query).subquery()


def _build_recent_learning_active_user_bid_subquery(
    *,
    since: datetime,
    until: datetime,
):
    activity_at = db.func.coalesce(
        LearnProgressRecord.updated_at,
        LearnProgressRecord.created_at,
    )
    return (
        db.session.query(LearnProgressRecord.user_bid.label("user_bid"))
        .filter(
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid != "",
            activity_at >= since,
            activity_at <= until,
        )
        .distinct()
        .subquery()
    )


def _build_recent_paid_user_bid_subquery(
    *,
    since: datetime,
    until: datetime,
):
    return (
        db.session.query(Order.user_bid.label("user_bid"))
        .filter(
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid != "",
            Order.created_at >= since,
            Order.created_at <= until,
        )
        .distinct()
        .subquery()
    )


def _build_registered_user_timestamp_subquery():
    registered_states = [USER_STATE_REGISTERED, USER_STATE_TRAIL, USER_STATE_PAID]
    credential_subquery = (
        db.session.query(
            AuthCredential.user_bid.label("user_bid"),
            db.func.min(AuthCredential.created_at).label("registered_at"),
        )
        .filter(
            AuthCredential.deleted == 0,
            AuthCredential.state == CREDENTIAL_STATE_VERIFIED,
            AuthCredential.provider_name.in_(
                OPERATOR_USER_REGISTRATION_CREDENTIAL_PROVIDERS
            ),
            AuthCredential.user_bid != "",
        )
        .group_by(AuthCredential.user_bid)
        .subquery()
    )
    return (
        db.session.query(
            UserEntity.user_bid.label("user_bid"),
            db.func.coalesce(
                credential_subquery.c.registered_at, UserEntity.created_at
            ).label("registered_at"),
        )
        .outerjoin(
            credential_subquery, credential_subquery.c.user_bid == UserEntity.user_bid
        )
        .filter(
            UserEntity.deleted == 0,
            UserEntity.state.in_(registered_states),
            UserEntity.user_bid != "",
        )
        .subquery()
    )


def _load_learner_user_bids(user_bids: Optional[Sequence[str]] = None) -> Set[str]:
    learner_subquery = _build_learner_user_bid_subquery()
    query = db.session.query(learner_subquery.c.user_bid)
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in (user_bids or []) if user_bid
    ]
    if normalized_user_bids:
        query = query.filter(learner_subquery.c.user_bid.in_(normalized_user_bids))
    return {row[0] for row in query.all() if row and row[0]}


def _normalize_login_method(provider_name: str) -> str:
    normalized = str(provider_name or "").strip().lower()
    if not normalized:
        return ""
    if normalized in OPERATOR_USER_SUPPORTED_LOGIN_METHOD_PROVIDERS:
        return normalized
    return "unknown"


def _normalize_registration_source(provider_name: str) -> str:
    normalized = str(provider_name or "").strip().lower()
    if normalized in OPERATOR_USER_SUPPORTED_LOGIN_METHOD_PROVIDERS:
        return normalized
    if normalized in {"manual", "import", "imported"}:
        return OPERATOR_USER_REGISTRATION_SOURCE_IMPORTED
    return OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN


def _load_operator_user_auth_credentials(
    user_bids: Sequence[str],
) -> list[AuthCredential]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return []

    return AuthCredential.query.filter(
        AuthCredential.user_bid.in_(normalized_user_bids),
        AuthCredential.provider_name.in_(
            sorted(OPERATOR_USER_PRELOADED_AUTH_CREDENTIAL_PROVIDERS)
        ),
        AuthCredential.deleted == 0,
    ).all()


def _load_operator_user_registration_source_map(
    user_bids: Sequence[str],
    *,
    users: Optional[Sequence[UserEntity]] = None,
    credential_rows: Optional[Sequence[AuthCredential]] = None,
) -> Dict[str, str]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}

    resolved_credential_rows = sorted(
        list(
            credential_rows
            if credential_rows is not None
            else _load_operator_user_auth_credentials(normalized_user_bids)
        ),
        key=lambda credential: (
            getattr(credential, "created_at", None) or datetime.min,
            int(getattr(credential, "id", 0) or 0),
        ),
    )
    registration_source_map: Dict[str, str] = {}
    for credential in resolved_credential_rows:
        user_bid = str(credential.user_bid or "").strip()
        if not user_bid or user_bid in registration_source_map:
            continue
        registration_source = _normalize_registration_source(
            credential.provider_name or ""
        )
        if registration_source == OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN:
            continue
        registration_source_map[user_bid] = registration_source

    if len(registration_source_map) == len(normalized_user_bids):
        return registration_source_map

    if users is None:
        resolved_users = (
            UserEntity.query.filter(
                UserEntity.user_bid.in_(normalized_user_bids),
                UserEntity.deleted == 0,
            )
            .order_by(UserEntity.id.asc())
            .all()
        )
    else:
        resolved_users = list(users)
    for user in resolved_users:
        user_bid = str(user.user_bid or "").strip()
        if not user_bid or user_bid in registration_source_map:
            continue
        identify = str(user.user_identify or "").strip()
        if identify.isdigit():
            registration_source_map[user_bid] = OPERATOR_USER_REGISTRATION_SOURCE_PHONE
        elif "@" in identify:
            registration_source_map[user_bid] = OPERATOR_USER_REGISTRATION_SOURCE_EMAIL
        else:
            registration_source_map[user_bid] = (
                OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN
            )
    return registration_source_map


def _load_operator_user_last_login_map(
    user_bids: Sequence[str],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}

    rows = (
        db.session.query(
            UserToken.user_id.label("user_bid"),
            db.func.max(UserToken.created).label("last_login_at"),
        )
        .filter(
            UserToken.user_id.in_(normalized_user_bids),
            UserToken.token != "",
        )
        .group_by(UserToken.user_id)
        .all()
    )
    return {
        str(user_bid or "").strip(): last_login_at
        for user_bid, last_login_at in rows
        if str(user_bid or "").strip() and last_login_at
    }


def _load_operator_user_total_paid_amount_map(
    user_bids: Sequence[str],
) -> Dict[str, Decimal]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}

    counted_order_amount_expr = _build_course_order_amount_expr()
    rows = (
        db.session.query(
            Order.user_bid,
            db.func.coalesce(db.func.sum(counted_order_amount_expr), 0).label(
                "total_paid_amount"
            ),
        )
        .filter(
            Order.user_bid.in_(normalized_user_bids),
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
        )
        .group_by(Order.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): Decimal(str(total_paid_amount or 0))
        for user_bid, total_paid_amount in rows
        if str(user_bid or "").strip()
    }


def _load_operator_user_last_learning_map(
    user_bids: Sequence[str],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}

    rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.max(LearnProgressRecord.updated_at).label("last_learning_at"),
        )
        .filter(
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): last_learning_at
        for user_bid, last_learning_at in rows
        if str(user_bid or "").strip() and last_learning_at
    }


def _load_operator_user_contact_map(
    user_bids: Sequence[str],
    *,
    users: Optional[Sequence[UserEntity]] = None,
    credential_rows: Optional[Sequence[AuthCredential]] = None,
) -> Dict[str, Dict[str, Any]]:
    if not user_bids:
        return {}

    resolved_credential_rows = sorted(
        list(
            credential_rows
            if credential_rows is not None
            else _load_operator_user_auth_credentials(user_bids)
        ),
        key=lambda credential: int(getattr(credential, "id", 0) or 0),
        reverse=True,
    )
    contact_map: Dict[str, Dict[str, Any]] = {
        user_bid: {"mobile": "", "email": "", "login_methods": []}
        for user_bid in user_bids
    }
    for credential in resolved_credential_rows:
        user_bid = str(credential.user_bid or "").strip()
        if not user_bid:
            continue
        resolved = contact_map.setdefault(
            user_bid,
            {"mobile": "", "email": "", "login_methods": []},
        )
        login_method = _normalize_login_method(credential.provider_name or "")
        if login_method and login_method not in resolved["login_methods"]:
            resolved["login_methods"].insert(0, login_method)
        if (
            credential.provider_name == "phone"
            and credential.state == CREDENTIAL_STATE_VERIFIED
            and not resolved["mobile"]
            and credential.identifier
        ):
            resolved["mobile"] = credential.identifier
        if (
            credential.provider_name in {"email", "google"}
            and credential.state == CREDENTIAL_STATE_VERIFIED
            and not resolved["email"]
            and credential.identifier
        ):
            resolved["email"] = credential.identifier

    if users is None:
        resolved_users = (
            UserEntity.query.filter(
                UserEntity.user_bid.in_(list(user_bids)),
                UserEntity.deleted == 0,
            )
            .order_by(UserEntity.id.asc())
            .all()
        )
    else:
        resolved_users = list(users)
    for user in resolved_users:
        resolved = contact_map.setdefault(
            user.user_bid or "",
            {"mobile": "", "email": "", "login_methods": []},
        )
        identify = str(user.user_identify or "").strip()
        if identify.isdigit():
            if not resolved["mobile"]:
                resolved["mobile"] = identify
            if "phone" not in resolved["login_methods"]:
                resolved["login_methods"].append("phone")
        elif "@" in identify:
            if not resolved["email"]:
                resolved["email"] = identify
            if "email" not in resolved["login_methods"]:
                resolved["login_methods"].append("email")
    return contact_map


def _find_matching_user_bids_by_identifier(keyword: str) -> Optional[Set[str]]:
    normalized = str(keyword or "").strip()
    if not normalized:
        return None

    like_pattern = f"%{normalized}%"
    credential_rows = db.session.query(
        AuthCredential.user_bid.label("user_bid")
    ).filter(
        AuthCredential.deleted == 0,
        AuthCredential.provider_name.in_(["phone", "email", "google"]),
        AuthCredential.identifier.ilike(like_pattern),
    )
    identify_rows = db.session.query(UserEntity.user_bid.label("user_bid")).filter(
        UserEntity.deleted == 0,
        or_(
            UserEntity.user_bid.ilike(like_pattern),
            UserEntity.user_identify.ilike(like_pattern),
        ),
    )
    bids = {
        str(row.user_bid or "").strip()
        for row in credential_rows.union(identify_rows).all()
    }
    return {bid for bid in bids if bid}


def _build_operator_user_summary(
    user: UserEntity,
    contact_map: Dict[str, Dict[str, Any]],
    learner_user_bids: Set[str],
    registration_source_map: Dict[str, str],
    last_login_map: Dict[str, datetime],
    total_paid_amount_map: Dict[str, Decimal],
    last_learning_map: Dict[str, datetime],
    credit_summary_map: Dict[str, Dict[str, Any]],
    *,
    learning_courses_map: Optional[
        Dict[str, list[AdminOperationUserCourseSummaryDTO]]
    ] = None,
    created_courses_map: Optional[
        Dict[str, list[AdminOperationUserCourseSummaryDTO]]
    ] = None,
    learning_course_count_map: Optional[Dict[str, int]] = None,
    created_course_count_map: Optional[Dict[str, int]] = None,
) -> AdminOperationUserSummaryDTO:
    user_bid = str(user.user_bid or "").strip()
    contact = contact_map.get(user.user_bid or "", {})
    is_learner = user_bid in learner_user_bids
    credit_summary = credit_summary_map.get(user_bid)
    has_credit_account = bool(user.is_creator) or credit_summary is not None
    learning_courses = list((learning_courses_map or {}).get(user_bid, []) or [])
    created_courses = list((created_courses_map or {}).get(user_bid, []) or [])
    return AdminOperationUserSummaryDTO(
        user_bid=user_bid,
        mobile=str(contact.get("mobile", "") or ""),
        email=str(contact.get("email", "") or ""),
        nickname=user.nickname or "",
        user_status=_resolve_operator_user_status(user.state),
        user_role=_resolve_operator_user_role(
            is_creator=bool(user.is_creator),
            is_operator=bool(user.is_operator),
            is_learner=is_learner,
        ),
        user_roles=_build_operator_user_roles(
            is_creator=bool(user.is_creator),
            is_operator=bool(user.is_operator),
            is_learner=is_learner,
        ),
        login_methods=list(contact.get("login_methods", []) or []),
        registration_source=registration_source_map.get(
            user_bid,
            OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN,
        ),
        language=user.language or "",
        learning_courses=learning_courses,
        learning_course_count=max(
            int(
                (learning_course_count_map or {}).get(
                    user_bid,
                    len(learning_courses),
                )
                or 0
            ),
            0,
        ),
        created_courses=created_courses,
        created_course_count=max(
            int(
                (created_course_count_map or {}).get(
                    user_bid,
                    len(created_courses),
                )
                or 0
            ),
            0,
        ),
        total_paid_amount=_format_decimal(total_paid_amount_map.get(user_bid)),
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
        last_login_at=last_login_map.get(user_bid),
        last_learning_at=last_learning_map.get(user_bid),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


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
                current_app.logger.info(
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


def _load_operator_user_or_raise(user_bid: str) -> UserEntity:
    normalized_user_bid = str(user_bid or "").strip()
    if not normalized_user_bid:
        raise_param_error("user_bid is required")

    user = (
        UserEntity.query.filter(
            UserEntity.user_bid == normalized_user_bid,
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.desc())
        .first()
    )
    if user is None:
        raise_error("server.user.userNotFound")
    return user


def _assert_operator_user_grant_target_supported(user: UserEntity) -> None:
    if bool(getattr(user, "is_creator", False)) or bool(
        getattr(user, "is_operator", False)
    ):
        return
    raise_error("server.billing.adminPlanGrantRoleUnsupported")


@dataclass
class OperatorCourseListSeed:
    id: int
    shifu_bid: str
    title: str
    price: Any
    llm: str
    created_user_bid: str
    updated_user_bid: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    has_course_prompt: Optional[bool] = None


@dataclass
class OperatorCourseListCandidate:
    id: int
    shifu_bid: str
    title: str
    price: Any
    llm: str
    created_user_bid: str
    updated_user_bid: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    selected_source: str
    course_status: str
    activity_updated_at: Optional[datetime] = None
    activity_updated_user_bid: str = ""
    has_course_prompt: Optional[bool] = None


def _build_operator_course_list_seed(row) -> OperatorCourseListSeed:
    return OperatorCourseListSeed(
        id=int(row.id),
        shifu_bid=str(row.shifu_bid or ""),
        title=str(row.title or ""),
        price=row.price,
        llm=str(row.llm or ""),
        created_user_bid=str(row.created_user_bid or ""),
        updated_user_bid=str(row.updated_user_bid or ""),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _build_operator_course_list_candidate(row) -> OperatorCourseListCandidate:
    return OperatorCourseListCandidate(
        id=int(row.id),
        shifu_bid=str(row.shifu_bid or ""),
        title=str(row.title or ""),
        price=row.price,
        llm=str(row.llm or ""),
        created_user_bid=str(row.created_user_bid or ""),
        updated_user_bid=str(row.updated_user_bid or ""),
        created_at=row.created_at,
        updated_at=row.updated_at,
        selected_source=str(row.selected_source or "").strip(),
        course_status=str(row.course_status or "").strip(),
        activity_updated_at=getattr(row, "activity_updated_at", None),
        activity_updated_user_bid=str(
            getattr(row, "activity_updated_user_bid", "") or ""
        ).strip(),
    )


def _build_operator_visible_course_filter(
    shifu_bid_column,
    title_column,
    created_user_bid_column,
):
    normalized_shifu_bid = db.func.trim(db.func.coalesce(shifu_bid_column, ""))
    normalized_title = db.func.trim(db.func.coalesce(title_column, ""))
    normalized_created_user_bid = db.func.trim(
        db.func.coalesce(created_user_bid_column, "")
    )
    conditions = [
        db.func.length(normalized_shifu_bid) > 0,
        not_(
            and_(
                normalized_created_user_bid == "system",
                normalized_title.in_(sorted(load_builtin_demo_titles())),
            )
        ),
    ]
    demo_shifu_bids = sorted(load_demo_shifu_bids())
    if demo_shifu_bids:
        conditions.append(not_(normalized_shifu_bid.in_(demo_shifu_bids)))
    return and_(*conditions)


def _build_latest_operator_course_rows_query(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
):
    latest_subquery = db.session.query(db.func.max(model.id).label("max_id")).filter(
        model.deleted == 0
    )
    if shifu_bid:
        latest_subquery = latest_subquery.filter(model.shifu_bid == shifu_bid)
    latest_subquery = latest_subquery.group_by(model.shifu_bid).subquery()

    query = db.session.query(
        model.id.label("id"),
        model.shifu_bid.label("shifu_bid"),
        model.title.label("title"),
        model.price.label("price"),
        model.llm.label("llm"),
        model.created_user_bid.label("created_user_bid"),
        model.updated_user_bid.label("updated_user_bid"),
        model.created_at.label("created_at"),
        model.updated_at.label("updated_at"),
    ).join(latest_subquery, model.id == latest_subquery.c.max_id)

    if course_name:
        query = query.filter(model.title.ilike(f"%{course_name}%"))
    if creator_bids is not None:
        if not creator_bids:
            return None
        query = query.filter(model.created_user_bid.in_(creator_bids))
    if start_time:
        query = query.filter(model.created_at >= start_time)
    if end_time:
        query = query.filter(model.created_at <= end_time)
    return query


def _build_latest_operator_course_rows_subquery(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    alias_name: str,
):
    base_query = _build_latest_operator_course_rows_query(
        model,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
    )
    if base_query is None:
        return None
    return base_query.cte(alias_name)


def _build_operator_course_candidate_query(
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    include_activity: bool = False,
):
    draft_rows_subquery = _build_latest_operator_course_rows_subquery(
        DraftShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        alias_name="operator_course_draft_rows",
    )
    published_rows_subquery = _build_latest_operator_course_rows_subquery(
        PublishedShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        alias_name="operator_course_published_rows",
    )
    if draft_rows_subquery is None or published_rows_subquery is None:
        return None

    draft_visible_subquery = (
        db.session.query(draft_rows_subquery)
        .filter(
            _build_operator_visible_course_filter(
                draft_rows_subquery.c.shifu_bid,
                draft_rows_subquery.c.title,
                draft_rows_subquery.c.created_user_bid,
            )
        )
        .cte("operator_course_draft_visible")
    )
    published_visible_subquery = (
        db.session.query(published_rows_subquery)
        .filter(
            _build_operator_visible_course_filter(
                published_rows_subquery.c.shifu_bid,
                published_rows_subquery.c.title,
                published_rows_subquery.c.created_user_bid,
            )
        )
        .cte("operator_course_published_visible")
    )

    candidate_bids_subquery = (
        db.session.query(draft_visible_subquery.c.shifu_bid.label("shifu_bid"))
        .union(
            db.session.query(published_visible_subquery.c.shifu_bid.label("shifu_bid"))
        )
        .cte("operator_course_candidate_bids")
    )
    latest_activity_subquery = (
        _build_operator_course_latest_activity_subquery(
            candidate_bids_subquery,
            draft_visible_subquery,
            published_visible_subquery,
        )
        if include_activity
        else None
    )

    selected_source_expr = case(
        (draft_visible_subquery.c.id.isnot(None), literal("draft")),
        else_=literal("published"),
    )
    course_status_expr = case(
        (published_visible_subquery.c.id.isnot(None), literal(COURSE_STATUS_PUBLISHED)),
        else_=literal(COURSE_STATUS_UNPUBLISHED),
    )
    selected_columns = [
        case(
            (draft_visible_subquery.c.id.isnot(None), draft_visible_subquery.c.id),
            else_=published_visible_subquery.c.id,
        ).label("id"),
        candidate_bids_subquery.c.shifu_bid.label("shifu_bid"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.title,
            ),
            else_=published_visible_subquery.c.title,
        ).label("title"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.price,
            ),
            else_=published_visible_subquery.c.price,
        ).label("price"),
        case(
            (draft_visible_subquery.c.id.isnot(None), draft_visible_subquery.c.llm),
            else_=published_visible_subquery.c.llm,
        ).label("llm"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.created_user_bid,
            ),
            else_=published_visible_subquery.c.created_user_bid,
        ).label("created_user_bid"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.updated_user_bid,
            ),
            else_=published_visible_subquery.c.updated_user_bid,
        ).label("updated_user_bid"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.created_at,
            ),
            else_=published_visible_subquery.c.created_at,
        ).label("created_at"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.updated_at,
            ),
            else_=published_visible_subquery.c.updated_at,
        ).label("updated_at"),
        selected_source_expr.label("selected_source"),
        course_status_expr.label("course_status"),
    ]
    if latest_activity_subquery is not None:
        selected_columns.extend(
            [
                latest_activity_subquery.c.updated_at.label("activity_updated_at"),
                latest_activity_subquery.c.updated_user_bid.label(
                    "activity_updated_user_bid"
                ),
            ]
        )
    candidate_query = (
        db.session.query(*selected_columns)
        .select_from(candidate_bids_subquery)
        .outerjoin(
            draft_visible_subquery,
            draft_visible_subquery.c.shifu_bid == candidate_bids_subquery.c.shifu_bid,
        )
        .outerjoin(
            published_visible_subquery,
            published_visible_subquery.c.shifu_bid
            == candidate_bids_subquery.c.shifu_bid,
        )
    )
    if latest_activity_subquery is not None:
        candidate_query = candidate_query.outerjoin(
            latest_activity_subquery,
            latest_activity_subquery.c.shifu_bid == candidate_bids_subquery.c.shifu_bid,
        )
    return candidate_query


def _build_latest_outline_activity_subquery(
    model,
    candidate_bids_subquery,
    *,
    alias_name: str,
):
    latest_outline_rows_subquery = (
        db.session.query(
            model.shifu_bid.label("shifu_bid"),
            model.outline_item_bid.label("outline_item_bid"),
            db.func.max(model.id).label("max_id"),
        )
        .join(
            candidate_bids_subquery,
            model.shifu_bid == candidate_bids_subquery.c.shifu_bid,
        )
        .group_by(model.shifu_bid, model.outline_item_bid)
        .cte(f"{alias_name}_latest_rows")
    )
    current_outline_rows_subquery = (
        db.session.query(
            model.shifu_bid.label("shifu_bid"),
            model.updated_at.label("updated_at"),
            model.updated_user_bid.label("updated_user_bid"),
            model.id.label("id"),
        )
        .join(
            latest_outline_rows_subquery,
            model.id == latest_outline_rows_subquery.c.max_id,
        )
        .filter(model.deleted == 0)
        .cte(f"{alias_name}_current_rows")
    )
    ranked_outline_activity_subquery = db.session.query(
        current_outline_rows_subquery.c.shifu_bid.label("shifu_bid"),
        current_outline_rows_subquery.c.updated_at.label("updated_at"),
        current_outline_rows_subquery.c.updated_user_bid.label("updated_user_bid"),
        db.func.row_number()
        .over(
            partition_by=current_outline_rows_subquery.c.shifu_bid,
            order_by=[
                current_outline_rows_subquery.c.updated_at.desc(),
                current_outline_rows_subquery.c.id.desc(),
            ],
        )
        .label("row_num"),
    ).cte(f"{alias_name}_ranked")
    return (
        db.session.query(
            ranked_outline_activity_subquery.c.shifu_bid.label("shifu_bid"),
            ranked_outline_activity_subquery.c.updated_at.label("updated_at"),
            ranked_outline_activity_subquery.c.updated_user_bid.label(
                "updated_user_bid"
            ),
        )
        .filter(ranked_outline_activity_subquery.c.row_num == 1)
        .cte(alias_name)
    )


def _build_operator_course_latest_activity_subquery(
    candidate_bids_subquery,
    draft_visible_subquery,
    published_visible_subquery,
):
    draft_outline_activity_subquery = _build_latest_outline_activity_subquery(
        DraftOutlineItem,
        candidate_bids_subquery,
        alias_name="operator_course_draft_outline_activity",
    )
    published_outline_activity_subquery = _build_latest_outline_activity_subquery(
        PublishedOutlineItem,
        candidate_bids_subquery,
        alias_name="operator_course_published_outline_activity",
    )

    activity_sources_subquery = (
        db.session.query(
            draft_visible_subquery.c.shifu_bid.label("shifu_bid"),
            draft_visible_subquery.c.updated_at.label("updated_at"),
            draft_visible_subquery.c.updated_user_bid.label("updated_user_bid"),
            literal(2).label("priority"),
        )
        .union_all(
            db.session.query(
                published_visible_subquery.c.shifu_bid.label("shifu_bid"),
                published_visible_subquery.c.updated_at.label("updated_at"),
                published_visible_subquery.c.updated_user_bid.label("updated_user_bid"),
                literal(1).label("priority"),
            ),
            db.session.query(
                draft_outline_activity_subquery.c.shifu_bid.label("shifu_bid"),
                draft_outline_activity_subquery.c.updated_at.label("updated_at"),
                draft_outline_activity_subquery.c.updated_user_bid.label(
                    "updated_user_bid"
                ),
                literal(3).label("priority"),
            ),
            db.session.query(
                published_outline_activity_subquery.c.shifu_bid.label("shifu_bid"),
                published_outline_activity_subquery.c.updated_at.label("updated_at"),
                published_outline_activity_subquery.c.updated_user_bid.label(
                    "updated_user_bid"
                ),
                literal(4).label("priority"),
            ),
        )
        .cte("operator_course_activity_sources")
    )
    ranked_activity_subquery = db.session.query(
        activity_sources_subquery.c.shifu_bid.label("shifu_bid"),
        activity_sources_subquery.c.updated_at.label("updated_at"),
        activity_sources_subquery.c.updated_user_bid.label("updated_user_bid"),
        db.func.row_number()
        .over(
            partition_by=activity_sources_subquery.c.shifu_bid,
            order_by=[
                activity_sources_subquery.c.updated_at.desc(),
                activity_sources_subquery.c.priority.desc(),
            ],
        )
        .label("row_num"),
    ).cte("operator_course_ranked_activity")
    return (
        db.session.query(
            ranked_activity_subquery.c.shifu_bid.label("shifu_bid"),
            ranked_activity_subquery.c.updated_at.label("updated_at"),
            ranked_activity_subquery.c.updated_user_bid.label("updated_user_bid"),
        )
        .filter(ranked_activity_subquery.c.row_num == 1)
        .cte("operator_course_latest_activity")
    )


def _build_latest_shifus_query(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    updated_start_time: Optional[datetime],
    updated_end_time: Optional[datetime],
    lightweight: bool = False,
):
    is_mapped_model = hasattr(model, "__mapper__")
    latest_subquery = db.session.query(db.func.max(model.id).label("max_id")).filter(
        model.deleted == 0
    )
    if shifu_bid:
        latest_subquery = latest_subquery.filter(model.shifu_bid == shifu_bid)
    latest_subquery = latest_subquery.group_by(model.shifu_bid).subquery()
    latest_rows = db.session.query(model).filter(
        model.id.in_(db.session.query(latest_subquery.c.max_id))
    )
    if is_mapped_model and not lightweight:
        latest_rows = latest_rows.options(defer(model.llm_system_prompt))
    if course_name:
        latest_rows = latest_rows.filter(model.title.ilike(f"%{course_name}%"))
    if creator_bids is not None:
        if not creator_bids:
            return []
        latest_rows = latest_rows.filter(model.created_user_bid.in_(creator_bids))
    if start_time:
        latest_rows = latest_rows.filter(model.created_at >= start_time)
    if end_time:
        latest_rows = latest_rows.filter(model.created_at <= end_time)
    if updated_start_time:
        latest_rows = latest_rows.filter(model.updated_at >= updated_start_time)
    if updated_end_time:
        latest_rows = latest_rows.filter(model.updated_at <= updated_end_time)
    return latest_rows.order_by(model.updated_at.desc(), model.id.desc())


def _load_latest_shifus(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    updated_start_time: Optional[datetime],
    updated_end_time: Optional[datetime],
    attach_prompt_flags: bool = False,
    lightweight: bool = False,
):
    ordered_query = _build_latest_shifus_query(
        model,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=updated_start_time,
        updated_end_time=updated_end_time,
        lightweight=lightweight,
    )
    if isinstance(ordered_query, list):
        return []

    if lightweight and hasattr(model, "__mapper__"):
        rows = ordered_query.with_entities(
            model.id.label("id"),
            model.shifu_bid.label("shifu_bid"),
            model.title.label("title"),
            model.price.label("price"),
            model.llm.label("llm"),
            model.created_user_bid.label("created_user_bid"),
            model.updated_user_bid.label("updated_user_bid"),
            model.created_at.label("created_at"),
            model.updated_at.label("updated_at"),
        ).all()
        return [_build_operator_course_list_seed(row) for row in rows]

    rows = ordered_query.all()
    if hasattr(model, "__mapper__") and attach_prompt_flags:
        _attach_course_prompt_flags(model, rows)
    return rows


def _load_latest_shifu_seeds(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    updated_start_time: Optional[datetime],
    updated_end_time: Optional[datetime],
) -> list[OperatorCourseListSeed]:
    ordered_query = _build_latest_shifus_query(
        model,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=updated_start_time,
        updated_end_time=updated_end_time,
        lightweight=True,
    )
    if isinstance(ordered_query, list):
        return []

    rows = ordered_query.with_entities(
        model.id.label("id"),
        model.shifu_bid.label("shifu_bid"),
        model.title.label("title"),
        model.price.label("price"),
        model.llm.label("llm"),
        model.created_user_bid.label("created_user_bid"),
        model.updated_user_bid.label("updated_user_bid"),
        model.created_at.label("created_at"),
        model.updated_at.label("updated_at"),
    ).all()
    return [_build_operator_course_list_seed(row) for row in rows]


def _attach_course_prompt_flags(model, rows) -> None:
    course_ids = [getattr(row, "id", None) for row in rows if getattr(row, "id", None)]
    if not course_ids:
        return

    has_course_prompt_rows = (
        db.session.query(
            model.id,
            case(
                (
                    db.func.length(
                        db.func.trim(db.func.coalesce(model.llm_system_prompt, ""))
                    )
                    > 0,
                    True,
                ),
                else_=False,
            ).label("has_course_prompt"),
        )
        .filter(model.id.in_(course_ids))
        .all()
    )
    has_course_prompt_map = {
        row_id: bool(has_course_prompt)
        for row_id, has_course_prompt in has_course_prompt_rows
    }
    for row in rows:
        setattr(
            row,
            "has_course_prompt",
            bool(has_course_prompt_map.get(getattr(row, "id", None), False)),
        )


def _build_course_summary(
    course,
    user_map: Dict[str, Dict[str, str]],
    course_status: str,
    activity: Optional[Dict[str, Any]] = None,
) -> AdminOperationCourseSummaryDTO:
    resolved_activity = activity or {}
    creator = user_map.get(course.created_user_bid or "", {})
    updater_user_bid = str(
        resolved_activity.get("updated_user_bid") or course.updated_user_bid or ""
    ).strip()
    updater = user_map.get(updater_user_bid, {})
    updated_at = resolved_activity.get("updated_at") or course.updated_at
    has_course_prompt = getattr(course, "has_course_prompt", None)
    if has_course_prompt is None:
        has_course_prompt = bool(
            str(getattr(course, "llm_system_prompt", "") or "").strip()
        )
    return AdminOperationCourseSummaryDTO(
        shifu_bid=course.shifu_bid or "",
        course_name=course.title or "",
        course_status=course_status,
        price=_format_decimal(course.price),
        course_model=str(course.llm or "").strip(),
        has_course_prompt=bool(has_course_prompt),
        creator_user_bid=course.created_user_bid or "",
        creator_mobile=creator.get("mobile", ""),
        creator_email=creator.get("email", ""),
        creator_nickname=creator.get("nickname", ""),
        updater_user_bid=updater_user_bid,
        updater_mobile=updater.get("mobile", ""),
        updater_email=updater.get("email", ""),
        updater_nickname=updater.get("nickname", ""),
        created_at=course.created_at,
        updated_at=updated_at,
    )


def _is_operator_visible_course(course) -> bool:
    return bool(course.shifu_bid) and not is_builtin_demo_course(
        shifu_bid=course.shifu_bid,
        title=course.title,
        created_user_bid=course.created_user_bid,
    )


def _resolve_course_status(shifu_bid: str, published_bids: Set[str]) -> str:
    if shifu_bid in published_bids:
        return COURSE_STATUS_PUBLISHED
    return COURSE_STATUS_UNPUBLISHED


def _resolve_course_quick_filter(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if normalized not in COURSE_QUICK_FILTER_VALUES:
        raise_param_error("quick_filter")
    return normalized


def _resolve_created_last_7d_window(
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    current = now or datetime.now()
    start = (current - timedelta(days=6)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = current.replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end


def _load_course_activity_map(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
) -> Dict[str, Dict[str, Any]]:
    return load_course_activity_map(drafts, published)


def _load_latest_course_for_transfer(shifu_bid: str):
    draft = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    if draft:
        return draft

    return (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )


def _load_latest_active_draft_outlines(shifu_bid: str) -> list[DraftOutlineItem]:
    latest_outline_ids = (
        db.session.query(
            DraftOutlineItem.outline_item_bid.label("outline_item_bid"),
            db.func.max(DraftOutlineItem.id).label("max_id"),
        )
        .filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
        )
        .group_by(DraftOutlineItem.outline_item_bid)
        .subquery()
    )
    return (
        db.session.query(DraftOutlineItem)
        .join(latest_outline_ids, DraftOutlineItem.id == latest_outline_ids.c.max_id)
        .filter(DraftOutlineItem.deleted == 0)
        .order_by(DraftOutlineItem.position.asc(), DraftOutlineItem.id.asc())
        .all()
    )


def _build_course_copy_title(source_title: str) -> str:
    normalized_title = str(source_title or "").strip() or _(
        "server.shifu.copyCourseTitleFallback"
    )
    suffix = _("server.shifu.copyCourseTitleSuffix")
    if len(normalized_title) + len(suffix) <= SHIFU_NAME_MAX_LENGTH:
        return f"{normalized_title}{suffix}"
    return f"{normalized_title[: SHIFU_NAME_MAX_LENGTH - len(suffix)]}{suffix}"


def _resolve_course_copy_title(source_title: str, requested_title: str) -> str:
    normalized_requested_title = str(requested_title or "").strip()
    if normalized_requested_title:
        if len(normalized_requested_title) > SHIFU_NAME_MAX_LENGTH:
            raise_error_with_args(
                "server.shifu.shifuNameTooLong",
                max_length=SHIFU_NAME_MAX_LENGTH,
            )
        return normalized_requested_title
    return _build_course_copy_title(source_title)


def _build_outline_history_tree(
    outlines: Sequence[DraftOutlineItem],
) -> list[HistoryItem]:
    outline_children_map: Dict[str, list[DraftOutlineItem]] = {}
    for outline in outlines:
        parent_bid = str(outline.parent_bid or "").strip()
        outline_children_map.setdefault(parent_bid, []).append(outline)

    def _count_blocks(content: str) -> int:
        if not content:
            return 0
        mdflow = MarkdownFlow(content).set_output_language(
            get_markdownflow_output_language()
        )
        return len(mdflow.get_all_blocks())

    def _build(parent_bid: str) -> list[HistoryItem]:
        children = outline_children_map.get(parent_bid, [])
        children.sort(key=lambda item: (item.position or "", item.id))
        history_items: list[HistoryItem] = []
        for child in children:
            history_items.append(
                HistoryItem(
                    bid=str(child.outline_item_bid or "").strip(),
                    id=int(child.id),
                    type="outline",
                    children=_build(str(child.outline_item_bid or "").strip()),
                    child_count=_count_blocks(child.content or ""),
                )
            )
        return history_items

    return _build("")


def _merge_courses(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
):
    course_map = {}
    published_bids: Set[str] = set()
    selected_sources: Dict[str, str] = {}
    for course in drafts:
        visible = _is_operator_visible_course(course)
        if visible:
            course_map[course.shifu_bid] = course
            selected_sources[course.shifu_bid] = "draft"
    for course in published:
        visible = _is_operator_visible_course(course)
        if visible:
            published_bids.add(course.shifu_bid)
        if visible and course.shifu_bid not in course_map:
            course_map[course.shifu_bid] = course
            selected_sources[course.shifu_bid] = "published"
    return (
        sorted(
            course_map.values(),
            key=lambda item: (
                item.updated_at or datetime.min,
                item.created_at or datetime.min,
                item.shifu_bid or "",
            ),
            reverse=True,
        ),
        published_bids,
        selected_sources,
    )


def _load_latest_course_versions(
    shifu_bid: str,
) -> tuple[Optional[DraftShifu], Optional[PublishedShifu]]:
    draft = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    published = (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )
    return draft, published


def _load_latest_courses_by_shifu_bids(
    model,
    shifu_bids: Sequence[str],
    *,
    lightweight: bool = False,
):
    normalized_shifu_bids = [
        str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
    ]
    if not normalized_shifu_bids:
        return []

    latest_subquery = (
        db.session.query(db.func.max(model.id).label("max_id"))
        .filter(
            model.deleted == 0,
            model.shifu_bid.in_(normalized_shifu_bids),
        )
        .group_by(model.shifu_bid)
        .subquery()
    )
    query = db.session.query(model).filter(
        model.id.in_(db.session.query(latest_subquery.c.max_id))
    )
    if lightweight and hasattr(model, "__mapper__"):
        rows = query.with_entities(
            model.id.label("id"),
            model.shifu_bid.label("shifu_bid"),
            model.title.label("title"),
            model.price.label("price"),
            model.llm.label("llm"),
            model.created_user_bid.label("created_user_bid"),
            model.updated_user_bid.label("updated_user_bid"),
            model.created_at.label("created_at"),
            model.updated_at.label("updated_at"),
        ).all()
        return [_build_operator_course_list_seed(row) for row in rows]
    return query.all()


def _build_operator_user_course_summary(
    course,
    published_bids: Set[str],
    *,
    completed_lesson_count: int = 0,
    total_lesson_count: int = 0,
) -> AdminOperationUserCourseSummaryDTO:
    return AdminOperationUserCourseSummaryDTO(
        shifu_bid=course.shifu_bid or "",
        course_name=course.title or "",
        course_status=_resolve_course_status(course.shifu_bid or "", published_bids),
        completed_lesson_count=max(int(completed_lesson_count or 0), 0),
        total_lesson_count=max(int(total_lesson_count or 0), 0),
    )


def _load_visible_published_leaf_outline_bids_by_shifu(
    shifu_bids: Sequence[str],
) -> Dict[str, list[str]]:
    normalized_shifu_bids = [
        str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
    ]
    if not normalized_shifu_bids:
        return {}

    latest_outline_subquery = (
        db.session.query(db.func.max(PublishedOutlineItem.id).label("max_id"))
        .filter(PublishedOutlineItem.shifu_bid.in_(normalized_shifu_bids))
        .group_by(
            PublishedOutlineItem.shifu_bid,
            PublishedOutlineItem.outline_item_bid,
        )
        .subquery()
    )
    outline_rows = (
        db.session.query(
            PublishedOutlineItem.shifu_bid,
            PublishedOutlineItem.outline_item_bid,
            PublishedOutlineItem.parent_bid,
        )
        .filter(
            PublishedOutlineItem.id.in_(
                db.session.query(latest_outline_subquery.c.max_id)
            ),
            PublishedOutlineItem.deleted == 0,
            PublishedOutlineItem.hidden == 0,
        )
        .all()
    )

    visible_bids_by_shifu: Dict[str, Set[str]] = {}
    parent_bids_by_shifu: Dict[str, Set[str]] = {}
    for shifu_bid, outline_item_bid, parent_bid in outline_rows:
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        normalized_parent_bid = str(parent_bid or "").strip()
        if not normalized_shifu_bid or not normalized_outline_item_bid:
            continue
        visible_bids_by_shifu.setdefault(normalized_shifu_bid, set()).add(
            normalized_outline_item_bid
        )
        if normalized_parent_bid:
            parent_bids_by_shifu.setdefault(normalized_shifu_bid, set()).add(
                normalized_parent_bid
            )

    return {
        shifu_bid: sorted(
            outline_item_bid
            for outline_item_bid in visible_bids
            if outline_item_bid not in parent_bids_by_shifu.get(shifu_bid, set())
        )
        for shifu_bid, visible_bids in visible_bids_by_shifu.items()
    }


def _is_completed_leaf_progress_statuses(record_statuses: Sequence[int]) -> bool:
    if not record_statuses:
        return False
    return int(record_statuses[-1] or 0) == LEARN_STATUS_COMPLETED


def _load_learning_progress_counts_by_user_and_course(
    user_bids: Sequence[str],
    shifu_bids: Sequence[str],
    leaf_outline_bids_by_shifu: Dict[str, list[str]],
) -> Dict[tuple[str, str], tuple[int, int]]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    normalized_shifu_bids = [
        str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
    ]
    if not normalized_user_bids or not normalized_shifu_bids:
        return {}

    all_leaf_outline_bids = sorted(
        {
            outline_item_bid
            for outline_item_bids in leaf_outline_bids_by_shifu.values()
            for outline_item_bid in outline_item_bids
            if outline_item_bid
        }
    )
    if not all_leaf_outline_bids:
        return {}

    leaf_outline_bids_by_shifu_set = {
        shifu_bid: set(outline_item_bids)
        for shifu_bid, outline_item_bids in leaf_outline_bids_by_shifu.items()
    }

    progress_rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            LearnProgressRecord.shifu_bid,
            LearnProgressRecord.outline_item_bid,
            LearnProgressRecord.status,
        )
        .filter(
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.shifu_bid.in_(normalized_shifu_bids),
            LearnProgressRecord.outline_item_bid.in_(all_leaf_outline_bids),
            LearnProgressRecord.deleted == 0,
        )
        .order_by(
            LearnProgressRecord.user_bid.asc(),
            LearnProgressRecord.shifu_bid.asc(),
            LearnProgressRecord.outline_item_bid.asc(),
            LearnProgressRecord.created_at.asc(),
            LearnProgressRecord.id.asc(),
        )
        .all()
    )

    statuses_by_user_course_outline: Dict[tuple[str, str, str], list[int]] = {}
    for user_bid, shifu_bid, outline_item_bid, status in progress_rows:
        normalized_user_bid = str(user_bid or "").strip()
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        if (
            not normalized_user_bid
            or not normalized_shifu_bid
            or not normalized_outline_item_bid
        ):
            continue
        if normalized_outline_item_bid not in leaf_outline_bids_by_shifu_set.get(
            normalized_shifu_bid, set()
        ):
            continue
        statuses_by_user_course_outline.setdefault(
            (
                normalized_user_bid,
                normalized_shifu_bid,
                normalized_outline_item_bid,
            ),
            [],
        ).append(int(status or 0))

    completed_counts_by_user_course: Dict[tuple[str, str], int] = {}
    for (
        user_bid,
        shifu_bid,
        _outline_item_bid,
    ), record_statuses in statuses_by_user_course_outline.items():
        if not _is_completed_leaf_progress_statuses(record_statuses):
            continue
        completed_counts_by_user_course[(user_bid, shifu_bid)] = (
            completed_counts_by_user_course.get((user_bid, shifu_bid), 0) + 1
        )

    progress_counts: Dict[tuple[str, str], tuple[int, int]] = {}
    for user_bid in normalized_user_bids:
        for shifu_bid in normalized_shifu_bids:
            total_lesson_count = len(leaf_outline_bids_by_shifu.get(shifu_bid, []))
            if total_lesson_count <= 0:
                continue
            progress_counts[(user_bid, shifu_bid)] = (
                completed_counts_by_user_course.get((user_bid, shifu_bid), 0),
                total_lesson_count,
            )
    return progress_counts


def _load_operator_user_course_maps(
    user_bids: Sequence[str],
) -> tuple[
    Dict[str, list[AdminOperationUserCourseSummaryDTO]],
    Dict[str, list[AdminOperationUserCourseSummaryDTO]],
]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}, {}

    created_courses_map: Dict[str, list[AdminOperationUserCourseSummaryDTO]] = {
        user_bid: [] for user_bid in normalized_user_bids
    }
    learning_courses_map: Dict[str, list[AdminOperationUserCourseSummaryDTO]] = {
        user_bid: [] for user_bid in normalized_user_bids
    }

    creator_bids = set(normalized_user_bids)
    created_drafts = _load_latest_shifus(
        DraftShifu,
        shifu_bid="",
        course_name="",
        creator_bids=creator_bids,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
        lightweight=True,
    )
    created_published = _load_latest_shifus(
        PublishedShifu,
        shifu_bid="",
        course_name="",
        creator_bids=creator_bids,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
        lightweight=True,
    )
    merged_created_courses, created_published_bids, _ = _merge_courses(
        created_drafts,
        created_published,
    )
    for course in merged_created_courses:
        creator_user_bid = str(course.created_user_bid or "").strip()
        if creator_user_bid not in created_courses_map:
            continue
        created_courses_map[creator_user_bid].append(
            _build_operator_user_course_summary(course, created_published_bids)
        )

    learned_activity_subquery = (
        db.session.query(
            Order.user_bid.label("user_bid"),
            Order.shifu_bid.label("shifu_bid"),
            Order.created_at.label("activity_at"),
        )
        .filter(
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid.in_(normalized_user_bids),
            Order.shifu_bid != "",
        )
        .union_all(
            db.session.query(
                LearnProgressRecord.user_bid.label("user_bid"),
                LearnProgressRecord.shifu_bid.label("shifu_bid"),
                LearnProgressRecord.updated_at.label("activity_at"),
            ).filter(
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
                LearnProgressRecord.user_bid.in_(normalized_user_bids),
                LearnProgressRecord.shifu_bid != "",
            ),
            db.session.query(
                AiCourseAuth.user_id.label("user_bid"),
                AiCourseAuth.course_id.label("shifu_bid"),
                db.func.coalesce(
                    AiCourseAuth.updated_at,
                    AiCourseAuth.created_at,
                ).label("activity_at"),
            ).filter(
                AiCourseAuth.status == 1,
                AiCourseAuth.user_id.in_(normalized_user_bids),
                AiCourseAuth.course_id != "",
            ),
        )
        .subquery()
    )
    learned_rows = (
        db.session.query(
            learned_activity_subquery.c.user_bid.label("user_bid"),
            learned_activity_subquery.c.shifu_bid.label("shifu_bid"),
            db.func.max(learned_activity_subquery.c.activity_at).label(
                "last_activity_at"
            ),
        )
        .group_by(
            learned_activity_subquery.c.user_bid,
            learned_activity_subquery.c.shifu_bid,
        )
        .all()
    )
    learned_shifu_bids = sorted(
        {
            str(row.shifu_bid or "").strip()
            for row in learned_rows
            if str(row.shifu_bid or "").strip()
        }
    )
    learned_drafts = _load_latest_courses_by_shifu_bids(
        DraftShifu,
        learned_shifu_bids,
        lightweight=True,
    )
    learned_published = _load_latest_courses_by_shifu_bids(
        PublishedShifu,
        learned_shifu_bids,
        lightweight=True,
    )
    merged_learned_courses, learned_published_bids, _ = _merge_courses(
        learned_drafts,
        learned_published,
    )
    learning_progress_counts = _load_learning_progress_counts_by_user_and_course(
        normalized_user_bids,
        learned_shifu_bids,
        _load_visible_published_leaf_outline_bids_by_shifu(learned_shifu_bids),
    )
    learned_course_map = {
        str(course.shifu_bid or "").strip(): course for course in merged_learned_courses
    }
    sorted_learned_rows = sorted(
        learned_rows,
        key=lambda row: (
            row.last_activity_at or datetime.min,
            str(row.shifu_bid or "").strip(),
        ),
        reverse=True,
    )
    for row in sorted_learned_rows:
        resolved_user_bid = str(row.user_bid or "").strip()
        resolved_shifu_bid = str(row.shifu_bid or "").strip()
        if not resolved_user_bid or not resolved_shifu_bid:
            continue
        course = learned_course_map.get(resolved_shifu_bid)
        if course is None:
            continue
        completed_lesson_count, total_lesson_count = learning_progress_counts.get(
            (resolved_user_bid, resolved_shifu_bid),
            (0, 0),
        )
        learning_courses_map[resolved_user_bid].append(
            _build_operator_user_course_summary(
                course,
                learned_published_bids,
                completed_lesson_count=completed_lesson_count,
                total_lesson_count=total_lesson_count,
            )
        )

    return created_courses_map, learning_courses_map


def _load_operator_user_course_count_maps(
    user_bids: Sequence[str],
) -> tuple[Dict[str, int], Dict[str, int]]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}, {}

    created_course_count_map = {user_bid: 0 for user_bid in normalized_user_bids}
    learning_course_count_map = {user_bid: 0 for user_bid in normalized_user_bids}

    creator_bids = set(normalized_user_bids)
    created_drafts = _load_latest_shifus(
        DraftShifu,
        shifu_bid="",
        course_name="",
        creator_bids=creator_bids,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
        lightweight=True,
    )
    created_published = _load_latest_shifus(
        PublishedShifu,
        shifu_bid="",
        course_name="",
        creator_bids=creator_bids,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
        lightweight=True,
    )
    merged_created_courses, _, _ = _merge_courses(created_drafts, created_published)
    for course in merged_created_courses:
        creator_user_bid = str(course.created_user_bid or "").strip()
        if creator_user_bid not in created_course_count_map:
            continue
        created_course_count_map[creator_user_bid] += 1

    learned_activity_subquery = (
        db.session.query(
            Order.user_bid.label("user_bid"),
            Order.shifu_bid.label("shifu_bid"),
            Order.created_at.label("activity_at"),
        )
        .filter(
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid.in_(normalized_user_bids),
            Order.shifu_bid != "",
        )
        .union_all(
            db.session.query(
                LearnProgressRecord.user_bid.label("user_bid"),
                LearnProgressRecord.shifu_bid.label("shifu_bid"),
                LearnProgressRecord.updated_at.label("activity_at"),
            ).filter(
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
                LearnProgressRecord.user_bid.in_(normalized_user_bids),
                LearnProgressRecord.shifu_bid != "",
            ),
            db.session.query(
                AiCourseAuth.user_id.label("user_bid"),
                AiCourseAuth.course_id.label("shifu_bid"),
                db.func.coalesce(
                    AiCourseAuth.updated_at,
                    AiCourseAuth.created_at,
                ).label("activity_at"),
            ).filter(
                AiCourseAuth.status == 1,
                AiCourseAuth.user_id.in_(normalized_user_bids),
                AiCourseAuth.course_id != "",
            ),
        )
        .subquery()
    )
    learned_rows = (
        db.session.query(
            learned_activity_subquery.c.user_bid.label("user_bid"),
            learned_activity_subquery.c.shifu_bid.label("shifu_bid"),
        )
        .group_by(
            learned_activity_subquery.c.user_bid,
            learned_activity_subquery.c.shifu_bid,
        )
        .all()
    )
    learned_shifu_bids = sorted(
        {
            str(row.shifu_bid or "").strip()
            for row in learned_rows
            if str(row.shifu_bid or "").strip()
        }
    )
    learned_drafts = _load_latest_courses_by_shifu_bids(
        DraftShifu,
        learned_shifu_bids,
        lightweight=True,
    )
    learned_published = _load_latest_courses_by_shifu_bids(
        PublishedShifu,
        learned_shifu_bids,
        lightweight=True,
    )
    merged_learned_courses, _, _ = _merge_courses(learned_drafts, learned_published)
    visible_learned_shifu_bids = {
        str(course.shifu_bid or "").strip()
        for course in merged_learned_courses
        if str(course.shifu_bid or "").strip()
    }
    for row in learned_rows:
        resolved_user_bid = str(row.user_bid or "").strip()
        resolved_shifu_bid = str(row.shifu_bid or "").strip()
        if (
            resolved_user_bid not in learning_course_count_map
            or resolved_shifu_bid not in visible_learned_shifu_bids
        ):
            continue
        learning_course_count_map[resolved_user_bid] += 1

    return created_course_count_map, learning_course_count_map


# Public compatibility exports for split admin operation modules. Keep these
# aliases until the remaining legacy helpers are moved out of this module.
build_learner_user_bid_subquery = _build_learner_user_bid_subquery
build_operator_user_summary = _build_operator_user_summary
build_recent_learning_active_user_bid_subquery = (
    _build_recent_learning_active_user_bid_subquery
)
build_recent_paid_user_bid_subquery = _build_recent_paid_user_bid_subquery
build_registered_user_timestamp_subquery = _build_registered_user_timestamp_subquery
find_matching_user_bids_by_identifier = _find_matching_user_bids_by_identifier
load_learner_user_bids = _load_learner_user_bids
load_operator_user_auth_credentials = _load_operator_user_auth_credentials
load_operator_user_contact_map = _load_operator_user_contact_map
load_operator_user_course_count_maps = _load_operator_user_course_count_maps
load_operator_user_course_maps = _load_operator_user_course_maps
load_operator_user_credit_summary_map = _load_operator_user_credit_summary_map
load_operator_user_last_learning_map = _load_operator_user_last_learning_map
load_operator_user_last_login_map = _load_operator_user_last_login_map
load_operator_user_or_raise = _load_operator_user_or_raise
load_operator_user_registration_source_map = _load_operator_user_registration_source_map
load_operator_user_total_paid_amount_map = _load_operator_user_total_paid_amount_map
resolve_operator_user_quick_filter = _resolve_operator_user_quick_filter
resolve_recent_days_window = _resolve_recent_days_window


from flaskr.service.shifu.admin_operations import courses as _operator_courses  # noqa: E402

# Backward-compatible exports for existing imports from shifu.admin.
_OPERATOR_COURSE_COMPAT_EXPORTS = (
    "_resolve_operator_credit_grant_type",
    "_format_decimal",
    "_coerce_operator_datetime",
    "_format_average_score",
    "_resolve_course_rating_mode",
    "_resolve_course_rating_sort_by",
    "_resolve_course_credit_usage_mode",
    "_resolve_course_credit_usage_mode_filter",
    "_resolve_course_credit_usage_scene",
    "_resolve_course_credit_usage_scene_filter",
    "_build_course_credit_usage_scene_filter",
    "_resolve_course_credit_usage_view",
    "_build_course_credit_usage_model_display",
    "_build_course_credit_usage_group_key",
    "_build_operator_course_credit_usage_item",
    "_build_course_credit_usage_generation_name_expr",
    "_build_course_credit_usage_ask_filter",
    "_build_course_credit_usage_learn_filter",
    "_build_operator_course_credit_usage_ledger_totals_subquery",
    "_build_operator_course_credit_usage_base_query",
    "_resolve_course_credit_usage_output_summary",
    "_load_course_credit_usage_output_summary_map",
    "_build_operator_course_credit_usage_detail_item",
    "_apply_course_credit_usage_filters",
    "_build_course_credit_usage_covered_completed_user_subquery",
    "_build_operator_course_credit_metrics",
    "_normalize_metadata_json",
    "_normalize_identifier",
    "_load_course_user_contact_map",
    "_load_user_map",
    "_resolve_course_user_role",
    "_resolve_course_user_learning_status",
    "_build_course_order_amount_expr",
    "_find_matching_creator_bids",
    "_load_operator_user_last_login_map",
    "_build_operator_course_list_seed",
    "_build_operator_course_list_candidate",
    "_build_operator_visible_course_filter",
    "_build_latest_operator_course_rows_query",
    "_build_latest_operator_course_rows_subquery",
    "_build_operator_course_candidate_query",
    "_build_latest_outline_activity_subquery",
    "_build_operator_course_latest_activity_subquery",
    "_build_latest_shifus_query",
    "_load_latest_shifus",
    "_load_latest_shifu_seeds",
    "_attach_course_prompt_flags",
    "_build_course_summary",
    "_is_operator_visible_course",
    "_resolve_course_status",
    "_resolve_course_quick_filter",
    "_resolve_created_last_7d_window",
    "_load_course_activity_map",
    "_load_latest_course_for_transfer",
    "_load_latest_active_draft_outlines",
    "_build_course_copy_title",
    "_resolve_course_copy_title",
    "_build_outline_history_tree",
    "_copy_course_variable_definitions",
    "_run_course_copy_draft_risk_check",
    "_run_course_copy_outline_risk_check",
    "_validate_operator_target_contact",
    "_prepare_operator_target_creator",
    "_load_recent_learning_active_course_bids",
    "_load_recent_paid_order_course_bids",
    "_clear_shifu_permission_cache",
    "_clear_shifu_creator_cache",
    "_update_course_creator_bid",
    "transfer_operator_course_creator",
    "copy_operator_course",
    "_merge_courses",
    "_load_latest_course_versions",
    "_load_operator_course_detail_source",
    "_load_latest_outline_items",
    "_resolve_learning_permission",
    "_resolve_content_status",
    "_resolve_outline_prompt_source",
    "_resolve_prompt_with_fallback",
    "_build_chapter_tree",
    "_load_outline_learning_stats",
    "_load_operator_course_outline_items",
    "_resolve_visible_leaf_outline_bids",
    "_build_course_outline_context_map",
    "_build_course_follow_up_base_subquery",
    "_build_follow_up_user_keyword_filter",
    "_build_credit_usage_user_keyword_filter",
    "_resolve_follow_up_matching_outline_bids",
    "_resolve_follow_up_answer_block",
    "_resolve_follow_up_answer_content",
    "_load_follow_up_groups_for_progress_record",
    "_resolve_follow_up_source_from_element",
    "_resolve_follow_up_source_from_blocks",
    "_resolve_follow_up_source",
    "_load_course_related_user_bids",
    "_load_course_user_paid_amount_map",
    "_load_course_user_last_learning_map",
    "_load_course_user_joined_at_map",
    "_load_course_user_learned_lesson_count_map",
    "get_operator_course_detail",
    "get_operator_course_prompt",
    "get_operator_course_users",
    "get_operator_course_credit_usages",
    "get_operator_course_credit_usage_details",
    "get_operator_course_follow_ups",
    "get_operator_course_ratings",
    "get_operator_course_follow_up_detail",
    "get_operator_course_chapter_detail",
    "_load_bill_usage_record_map",
    "_build_latest_bill_usage_record_subquery",
    "_build_latest_billing_order_subquery",
    "_find_operator_course_bids_by_name",
    "_build_operator_course_query_filter",
    "_build_operator_course_overview",
    "get_operator_course_overview",
    "_can_use_operator_course_sql_optimization",
    "_build_operator_course_overview_legacy",
    "_list_operator_courses_legacy",
    "list_operator_courses",
    "load_existing_demo_shifu_ids",
)

_copy_course_variable_definitions = _operator_courses._copy_course_variable_definitions
_run_course_copy_draft_risk_check = _operator_courses._run_course_copy_draft_risk_check
_run_course_copy_outline_risk_check = (
    _operator_courses._run_course_copy_outline_risk_check
)
_validate_operator_target_contact = _operator_courses._validate_operator_target_contact
_prepare_operator_target_creator = _operator_courses._prepare_operator_target_creator
_load_recent_learning_active_course_bids = (
    _operator_courses._load_recent_learning_active_course_bids
)
_load_recent_paid_order_course_bids = (
    _operator_courses._load_recent_paid_order_course_bids
)
_clear_shifu_permission_cache = _operator_courses._clear_shifu_permission_cache
_clear_shifu_creator_cache = _operator_courses._clear_shifu_creator_cache
_update_course_creator_bid = _operator_courses._update_course_creator_bid
transfer_operator_course_creator = _operator_courses.transfer_operator_course_creator
copy_operator_course = _operator_courses.copy_operator_course
_load_operator_course_detail_source = (
    _operator_courses._load_operator_course_detail_source
)
_load_latest_outline_items = _operator_courses._load_latest_outline_items
_resolve_learning_permission = _operator_courses._resolve_learning_permission
_resolve_content_status = _operator_courses._resolve_content_status
_resolve_outline_prompt_source = _operator_courses._resolve_outline_prompt_source
_resolve_prompt_with_fallback = _operator_courses._resolve_prompt_with_fallback
_build_chapter_tree = _operator_courses._build_chapter_tree
_load_outline_learning_stats = _operator_courses._load_outline_learning_stats
_load_operator_course_outline_items = (
    _operator_courses._load_operator_course_outline_items
)
_resolve_visible_leaf_outline_bids = (
    _operator_courses._resolve_visible_leaf_outline_bids
)
_build_course_outline_context_map = _operator_courses._build_course_outline_context_map
_build_course_follow_up_base_subquery = (
    _operator_courses._build_course_follow_up_base_subquery
)
_build_follow_up_user_keyword_filter = (
    _operator_courses._build_follow_up_user_keyword_filter
)
_build_credit_usage_user_keyword_filter = (
    _operator_courses._build_credit_usage_user_keyword_filter
)
_resolve_follow_up_matching_outline_bids = (
    _operator_courses._resolve_follow_up_matching_outline_bids
)
_resolve_follow_up_answer_block = _operator_courses._resolve_follow_up_answer_block
_resolve_follow_up_answer_content = _operator_courses._resolve_follow_up_answer_content
_load_follow_up_groups_for_progress_record = (
    _operator_courses._load_follow_up_groups_for_progress_record
)
_resolve_follow_up_source_from_element = (
    _operator_courses._resolve_follow_up_source_from_element
)
_resolve_follow_up_source_from_blocks = (
    _operator_courses._resolve_follow_up_source_from_blocks
)
_resolve_follow_up_source = _operator_courses._resolve_follow_up_source
_load_course_related_user_bids = _operator_courses._load_course_related_user_bids
_load_course_user_paid_amount_map = _operator_courses._load_course_user_paid_amount_map
_load_course_user_last_learning_map = (
    _operator_courses._load_course_user_last_learning_map
)
_load_course_user_joined_at_map = _operator_courses._load_course_user_joined_at_map
_load_course_user_learned_lesson_count_map = (
    _operator_courses._load_course_user_learned_lesson_count_map
)
get_operator_course_detail = _operator_courses.get_operator_course_detail
get_operator_course_prompt = _operator_courses.get_operator_course_prompt
get_operator_course_users = _operator_courses.get_operator_course_users
get_operator_course_credit_usages = _operator_courses.get_operator_course_credit_usages
get_operator_course_credit_usage_details = (
    _operator_courses.get_operator_course_credit_usage_details
)
get_operator_course_follow_ups = _operator_courses.get_operator_course_follow_ups
get_operator_course_ratings = _operator_courses.get_operator_course_ratings
get_operator_course_follow_up_detail = (
    _operator_courses.get_operator_course_follow_up_detail
)
get_operator_course_chapter_detail = (
    _operator_courses.get_operator_course_chapter_detail
)
_load_bill_usage_record_map = _operator_courses._load_bill_usage_record_map
_build_latest_bill_usage_record_subquery = (
    _operator_courses._build_latest_bill_usage_record_subquery
)
_build_latest_billing_order_subquery = (
    _operator_courses._build_latest_billing_order_subquery
)
_find_operator_course_bids_by_name = (
    _operator_courses._find_operator_course_bids_by_name
)
_build_operator_course_query_filter = (
    _operator_courses._build_operator_course_query_filter
)
_build_operator_course_overview = _operator_courses._build_operator_course_overview
get_operator_course_overview = _operator_courses.get_operator_course_overview
_can_use_operator_course_sql_optimization = (
    _operator_courses._can_use_operator_course_sql_optimization
)
_build_operator_course_overview_legacy = (
    _operator_courses._build_operator_course_overview_legacy
)
_list_operator_courses_legacy = _operator_courses._list_operator_courses_legacy
list_operator_courses = _operator_courses.list_operator_courses
load_existing_demo_shifu_ids = _operator_courses.load_existing_demo_shifu_ids

_OPERATOR_COURSE_FORWARDABLE_NAMES = _OPERATOR_COURSE_COMPAT_EXPORTS + (
    "check_text_with_risk_control",
    "datetime",
    "get_course_visit_count_30d",
    "run_creator_granted_post_auth",
)


class _AdminCompatibilityModule(type(sys)):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in _OPERATOR_COURSE_FORWARDABLE_NAMES and hasattr(
            _operator_courses, name
        ):
            setattr(_operator_courses, name, value)


sys.modules[__name__].__class__ = _AdminCompatibilityModule


__all__ = (
    "get_course_visit_count_30d",
    "UNIT_TYPE_VALUE_GUEST",
    "UNIT_TYPE_VALUE_NORMAL",
    "UNIT_TYPE_VALUE_TRIAL",
    "check_text_with_risk_control",
    "load_existing_demo_shifu_ids",
    "run_creator_granted_post_auth",
    "_resolve_operator_credit_grant_type",
    "_format_average_score",
    "_resolve_course_rating_mode",
    "_resolve_course_rating_sort_by",
    "_resolve_course_credit_usage_view",
    "_build_course_credit_usage_model_display",
    "_build_course_credit_usage_group_key",
    "_build_operator_course_credit_usage_item",
    "_load_course_credit_usage_output_summary_map",
    "_build_operator_course_credit_usage_detail_item",
    "_apply_course_credit_usage_filters",
    "_build_operator_course_credit_metrics",
    "_load_course_user_contact_map",
    "_load_user_map",
    "_resolve_course_user_role",
    "_resolve_course_user_learning_status",
    "_find_matching_creator_bids",
    "_build_operator_course_list_candidate",
    "_build_operator_course_candidate_query",
    "_load_latest_shifu_seeds",
    "_build_course_summary",
    "_resolve_course_quick_filter",
    "_resolve_created_last_7d_window",
    "_load_course_activity_map",
    "_load_latest_course_for_transfer",
    "_load_latest_active_draft_outlines",
    "_resolve_course_copy_title",
    "_build_outline_history_tree",
    "_copy_course_variable_definitions",
    "_run_course_copy_draft_risk_check",
    "_run_course_copy_outline_risk_check",
    "_validate_operator_target_contact",
    "_prepare_operator_target_creator",
    "_load_recent_learning_active_course_bids",
    "_load_recent_paid_order_course_bids",
    "_clear_shifu_permission_cache",
    "_clear_shifu_creator_cache",
    "_update_course_creator_bid",
    "transfer_operator_course_creator",
    "copy_operator_course",
    "_load_latest_course_versions",
    "_load_operator_course_detail_source",
    "_resolve_learning_permission",
    "_resolve_content_status",
    "_resolve_outline_prompt_source",
    "_resolve_prompt_with_fallback",
    "_build_chapter_tree",
    "_load_outline_learning_stats",
    "_load_operator_course_outline_items",
    "_resolve_visible_leaf_outline_bids",
    "_build_course_follow_up_base_subquery",
    "_build_follow_up_user_keyword_filter",
    "_resolve_follow_up_matching_outline_bids",
    "_resolve_follow_up_answer_block",
    "_resolve_follow_up_answer_content",
    "_load_follow_up_groups_for_progress_record",
    "_resolve_follow_up_source_from_element",
    "_resolve_follow_up_source_from_blocks",
    "_resolve_follow_up_source",
    "_load_course_related_user_bids",
    "_load_course_user_paid_amount_map",
    "_load_course_user_last_learning_map",
    "_load_course_user_joined_at_map",
    "_load_course_user_learned_lesson_count_map",
    "get_operator_course_detail",
    "get_operator_course_prompt",
    "get_operator_course_users",
    "get_operator_course_credit_usages",
    "get_operator_course_credit_usage_details",
    "get_operator_course_follow_ups",
    "get_operator_course_ratings",
    "get_operator_course_follow_up_detail",
    "get_operator_course_chapter_detail",
    "_load_bill_usage_record_map",
    "_build_latest_billing_order_subquery",
    "_find_operator_course_bids_by_name",
    "_build_operator_course_query_filter",
    "_build_operator_course_overview",
    "get_operator_course_overview",
    "_can_use_operator_course_sql_optimization",
    "_build_operator_course_overview_legacy",
    "_list_operator_courses_legacy",
    "list_operator_courses",
)
