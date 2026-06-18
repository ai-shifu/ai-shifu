from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Sequence, Set

from flask import Flask, current_app
from sqlalchemy import and_, case, false, literal, not_, or_
from sqlalchemy.orm import defer

from flaskr.common.cache_provider import cache as redis
from flaskr.common.config import get_redis_key_prefix
from flaskr.common.umami_client import get_course_visit_count_30d
from flaskr.i18n import _
from flaskr.dao import db
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import (
    BillingOrder,
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
from flaskr.service.learn.learn_dtos import ElementType
from flaskr.service.learn.listen_element_payloads import _deserialize_payload
from flaskr.service.learn.const import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.common.models import (
    raise_error,
    raise_error_with_args,
    raise_param_error,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.profile.models import Variable
from flaskr.util import generate_id
from flaskr.service.shifu.admin_dtos import (
    AdminOperationCourseListDTO,
    AdminOperationCourseChapterDetailDTO,
    AdminOperationCourseDetailBasicInfoDTO,
    AdminOperationCourseDetailChapterDTO,
    AdminOperationCourseDetailDTO,
    AdminOperationCourseCreditUsageDetailItemDTO,
    AdminOperationCourseCreditUsageDetailListDTO,
    AdminOperationCourseCreditUsageItemDTO,
    AdminOperationCourseCreditUsageListDTO,
    AdminOperationCourseFollowUpCurrentRecordDTO,
    AdminOperationCourseFollowUpDetailBasicInfoDTO,
    AdminOperationCourseFollowUpDetailDTO,
    AdminOperationCourseFollowUpItemDTO,
    AdminOperationCourseFollowUpListDTO,
    AdminOperationCourseFollowUpSummaryDTO,
    AdminOperationCourseFollowUpTimelineItemDTO,
    AdminOperationCourseDetailMetricsDTO,
    AdminOperationCoursePromptDTO,
    AdminOperationCourseRatingItemDTO,
    AdminOperationCourseRatingListDTO,
    AdminOperationCourseRatingSummaryDTO,
    AdminOperationCourseOverviewDTO,
    AdminOperationCourseUserDTO,
    AdminOperationCourseSummaryDTO,
)
from flaskr.service.shifu.course_activity import load_course_activity_map
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    SHIFU_NAME_MAX_LENGTH,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.demo_courses import (
    is_builtin_demo_course,
    load_builtin_demo_titles,
    load_demo_shifu_bids,
)
from flaskr.service.shifu.shifu_draft_funcs import (
    check_text_with_risk_control,
    get_latest_shifu_draft,
)
from flaskr.service.shifu.shifu_history_manager import (
    HistoryItem,
    save_outline_tree_history,
    save_shifu_history,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.service.user.consts import (
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
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    load_user_aggregate_by_identifier,
    set_user_state,
    upsert_credential,
)
from flaskr.util.timezone import serialize_with_app_timezone
from flaskr.service.user.utils import (
    ensure_demo_course_permissions,
    load_existing_demo_shifu_ids,
    mark_creator_role_if_needed,
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


def _get_legacy_admin_symbol(name: str, fallback: Any) -> Any:
    admin_module = sys.modules.get("flaskr.service.shifu.admin")
    if admin_module is None:
        return fallback
    return getattr(admin_module, name, fallback)


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


def _format_operator_datetime(value: Any) -> str:
    normalized_value = _coerce_operator_datetime(value)
    if not normalized_value:
        return ""
    serialized_value = serialize_with_app_timezone(
        current_app._get_current_object(),
        normalized_value,
        tz_name="UTC",
    )
    return str(serialized_value or "").replace("+00:00", "Z")


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
        created_at=_format_operator_datetime(resolved_created_at),
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
        created_at=_format_operator_datetime(getattr(usage_row, "created_at", None)),
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
        created_at=_format_operator_datetime(course.created_at),
        updated_at=_format_operator_datetime(updated_at),
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


def _copy_course_variable_definitions(
    *,
    source_shifu_bid: str,
    target_shifu_bid: str,
    creator_user_bid: str,
    updated_user_bid: str,
    now: datetime,
) -> None:
    variable_definitions = (
        Variable.query.filter(
            Variable.shifu_bid == source_shifu_bid,
            Variable.deleted == 0,
        )
        .order_by(Variable.id.asc())
        .all()
    )
    for definition in variable_definitions:
        db.session.add(
            Variable(
                variable_bid=generate_id(current_app),
                shifu_bid=target_shifu_bid,
                key=str(definition.key or "").strip(),
                is_hidden=definition.is_hidden,
                deleted=0,
                created_at=now,
                created_user_bid=creator_user_bid,
                updated_at=now,
                updated_user_bid=updated_user_bid,
            )
        )


def _run_course_copy_draft_risk_check(
    app: Flask,
    *,
    source_draft: DraftShifu,
    target_shifu_bid: str,
    operator_user_bid: str,
    new_course_name: str,
) -> None:
    draft_to_check = source_draft.clone()
    draft_to_check.shifu_bid = target_shifu_bid
    draft_to_check.title = new_course_name
    check_content = str(draft_to_check.get_str_to_check() or "").strip()
    if check_content:
        _get_legacy_admin_symbol(
            "check_text_with_risk_control", check_text_with_risk_control
        )(app, target_shifu_bid, operator_user_bid, check_content)


def _run_course_copy_outline_risk_check(
    app: Flask,
    *,
    source_outline: DraftOutlineItem,
    target_outline_bid: str,
    operator_user_bid: str,
) -> None:
    outline_to_check = source_outline.clone()
    outline_to_check.outline_item_bid = target_outline_bid
    outline_check_content = str(outline_to_check.get_str_to_check() or "").strip()
    if outline_check_content:
        _get_legacy_admin_symbol(
            "check_text_with_risk_control", check_text_with_risk_control
        )(app, target_outline_bid, operator_user_bid, outline_check_content)

    markdown_content = str(outline_to_check.content or "").strip()
    if markdown_content:
        _get_legacy_admin_symbol(
            "check_text_with_risk_control", check_text_with_risk_control
        )(app, target_outline_bid, operator_user_bid, markdown_content)


def _validate_operator_target_contact(contact_type: str, identifier: str) -> str:
    normalized_contact_type = str(contact_type or "").strip().lower()
    normalized_identifier = _normalize_identifier(identifier)
    if normalized_contact_type not in {"phone", "email"}:
        raise_param_error("contact_type")
    if (
        not normalized_identifier
        or len(normalized_identifier) > OPERATOR_TARGET_CONTACT_MAX_LENGTH
    ):
        raise_param_error("contact")
    if normalized_contact_type == "phone":
        if not OPERATOR_TARGET_PHONE_PATTERN.match(normalized_identifier):
            raise_param_error("mobile")
        return normalized_identifier
    if not OPERATOR_TARGET_EMAIL_PATTERN.match(normalized_identifier):
        raise_param_error("email")
    return normalized_identifier.lower()


def _prepare_operator_target_creator(
    app: Flask,
    *,
    contact_type: str,
    identifier: str,
    previous_creator_user_bid: str = "",
    allow_same_user: bool = False,
) -> Dict[str, Any]:
    normalized_contact_type = str(contact_type or "").strip().lower()
    normalized_identifier = _validate_operator_target_contact(
        normalized_contact_type, identifier
    )

    lookup_providers = (
        ["email", "google"] if normalized_contact_type == "email" else ["phone"]
    )

    existing_aggregate = load_user_aggregate_by_identifier(
        normalized_identifier,
        providers=lookup_providers,
    )
    created_new_user = False
    granted_demo_permissions = False
    if existing_aggregate is None:
        target_aggregate, created_new_user = ensure_user_for_identifier(
            app,
            provider=normalized_contact_type,
            identifier=normalized_identifier,
            defaults={
                "identify": normalized_identifier,
                "nickname": "",
                "state": USER_STATE_REGISTERED,
            },
        )
    else:
        target_aggregate = existing_aggregate

    target_user_bid = str(target_aggregate.user_bid or "").strip()
    if not target_user_bid:
        raise_error("server.shifu.transferCreatorTargetNotFound")
    if (
        previous_creator_user_bid
        and not allow_same_user
        and target_user_bid == previous_creator_user_bid
    ):
        raise_error("server.shifu.transferCreatorSameUser")

    should_grant_demo_permissions = created_new_user
    if (
        existing_aggregate is not None
        and existing_aggregate.state == USER_STATE_UNREGISTERED
    ):
        set_user_state(target_user_bid, USER_STATE_REGISTERED)
        should_grant_demo_permissions = True

    upsert_credential(
        app,
        user_bid=target_user_bid,
        provider_name=normalized_contact_type,
        subject_id=normalized_identifier,
        subject_format=normalized_contact_type,
        identifier=normalized_identifier,
        metadata={},
        verified=True,
    )

    if should_grant_demo_permissions:
        demo_shifu_ids = load_existing_demo_shifu_ids()
        if demo_shifu_ids:
            ensure_demo_course_permissions(
                app,
                target_user_bid,
                demo_ids=demo_shifu_ids,
            )
            granted_demo_permissions = True

    creator_granted_now = mark_creator_role_if_needed(target_user_bid)
    return {
        "target_aggregate": target_aggregate,
        "target_user_bid": target_user_bid,
        "normalized_identifier": normalized_identifier,
        "created_new_user": created_new_user,
        "granted_demo_permissions": granted_demo_permissions,
        "creator_granted_now": creator_granted_now,
    }


def _load_recent_learning_active_course_bids(
    *,
    since: datetime,
    shifu_bids: Optional[Sequence[str]] = None,
) -> Set[str]:
    query = db.session.query(LearnProgressRecord.shifu_bid).filter(
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
        LearnProgressRecord.created_at >= since,
    )
    if shifu_bids is not None:
        normalized_shifu_bids = [
            str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
        ]
        if not normalized_shifu_bids:
            return set()
        query = query.filter(LearnProgressRecord.shifu_bid.in_(normalized_shifu_bids))
    rows = query.distinct().all()
    return {
        str(shifu_bid or "").strip()
        for (shifu_bid,) in rows
        if str(shifu_bid or "").strip()
    }


def _load_recent_paid_order_course_bids(
    *,
    since: datetime,
    shifu_bids: Optional[Sequence[str]] = None,
) -> Set[str]:
    query = db.session.query(Order.shifu_bid).filter(
        Order.deleted == 0,
        Order.status == ORDER_STATUS_SUCCESS,
        Order.created_at >= since,
    )
    if shifu_bids is not None:
        normalized_shifu_bids = [
            str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
        ]
        if not normalized_shifu_bids:
            return set()
        query = query.filter(Order.shifu_bid.in_(normalized_shifu_bids))
    rows = query.distinct().all()
    return {
        str(shifu_bid or "").strip()
        for (shifu_bid,) in rows
        if str(shifu_bid or "").strip()
    }


def _clear_shifu_permission_cache(app: Flask, user_id: str, shifu_bid: str) -> None:
    prefixes = {
        app.config.get("CACHE_KEY_PREFIX", "") or "",
        get_redis_key_prefix(app),
    }
    for prefix in prefixes:
        cache_key = f"{prefix}shifu_permission:{user_id}:{shifu_bid}"
        redis.delete(cache_key)


def _clear_shifu_creator_cache(app: Flask, shifu_bid: str) -> None:
    prefixes = {
        get_redis_key_prefix(app),
        "ai-shifu",
    }
    for prefix in prefixes:
        cache_key = f"{prefix}:shifu_creator:{shifu_bid}"
        redis.delete(cache_key)


def _update_course_creator_bid(
    shifu_bid: str,
    creator_user_bid: str,
    updated_user_bid: str = "",
) -> None:
    draft_values = {DraftShifu.created_user_bid: creator_user_bid}
    published_values = {PublishedShifu.created_user_bid: creator_user_bid}
    normalized_updated_user_bid = str(updated_user_bid or "").strip()
    if normalized_updated_user_bid:
        updated_at = datetime.now()
        draft_values[DraftShifu.updated_user_bid] = normalized_updated_user_bid
        draft_values[DraftShifu.updated_at] = updated_at
        published_values[PublishedShifu.updated_user_bid] = normalized_updated_user_bid
        published_values[PublishedShifu.updated_at] = updated_at
    DraftShifu.query.filter(DraftShifu.shifu_bid == shifu_bid).update(
        draft_values,
        synchronize_session=False,
    )
    PublishedShifu.query.filter(PublishedShifu.shifu_bid == shifu_bid).update(
        published_values,
        synchronize_session=False,
    )


def transfer_operator_course_creator(
    app: Flask,
    *,
    shifu_bid: str,
    contact_type: str,
    identifier: str,
    operator_user_bid: str = "",
) -> Dict[str, Any]:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_contact_type = str(contact_type or "").strip().lower()
        normalized_identifier = _normalize_identifier(identifier)
        normalized_operator_user_bid = str(operator_user_bid or "").strip()

        latest_course = _load_latest_course_for_transfer(normalized_shifu_bid)
        if not latest_course:
            raise_error("server.shifu.shifuNotFound")
        if not _is_operator_visible_course(latest_course):
            raise_error("server.shifu.transferCreatorDemoNotAllowed")

        previous_creator_user_bid = str(latest_course.created_user_bid or "").strip()
        target_creator_result = _prepare_operator_target_creator(
            app,
            contact_type=normalized_contact_type,
            identifier=normalized_identifier,
            previous_creator_user_bid=previous_creator_user_bid,
        )
        target_aggregate = target_creator_result["target_aggregate"]
        target_user_bid = target_creator_result["target_user_bid"]
        created_new_user = target_creator_result["created_new_user"]
        granted_demo_permissions = target_creator_result["granted_demo_permissions"]
        creator_granted_now = target_creator_result["creator_granted_now"]
        _update_course_creator_bid(
            normalized_shifu_bid,
            target_user_bid,
            updated_user_bid=normalized_operator_user_bid,
        )
        if normalized_operator_user_bid and getattr(latest_course, "id", 0):
            save_shifu_history(
                app,
                normalized_operator_user_bid,
                normalized_shifu_bid,
                int(latest_course.id),
            )

        db.session.commit()
        if previous_creator_user_bid:
            _clear_shifu_permission_cache(
                app, previous_creator_user_bid, normalized_shifu_bid
            )
        _clear_shifu_permission_cache(app, target_user_bid, normalized_shifu_bid)
        _clear_shifu_creator_cache(app, normalized_shifu_bid)
        if creator_granted_now:
            _get_legacy_admin_symbol(
                "run_creator_granted_post_auth", run_creator_granted_post_auth
            )(
                app,
                user_id=target_user_bid,
                source="operator_transfer_creator",
                login_context="admin",
                created_new_user=created_new_user,
                language=target_aggregate.user_language,
            )
        return {
            "shifu_bid": normalized_shifu_bid,
            "previous_creator_user_bid": previous_creator_user_bid,
            "target_creator_user_bid": target_user_bid,
            "created_new_user": created_new_user,
            "granted_demo_permissions": granted_demo_permissions,
        }


def copy_operator_course(
    app: Flask,
    *,
    shifu_bid: str,
    contact_type: str,
    identifier: str,
    operator_user_bid: str,
    new_course_name: str = "",
) -> Dict[str, Any]:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_contact_type = str(contact_type or "").strip().lower()
        normalized_identifier = _normalize_identifier(identifier)
        normalized_operator_user_bid = str(operator_user_bid or "").strip()
        if not normalized_operator_user_bid:
            raise_param_error("operator_user_bid")

        source_draft = get_latest_shifu_draft(normalized_shifu_bid)
        if not source_draft:
            raise_error("server.shifu.copyCourseDraftNotFound")
        if not _is_operator_visible_course(source_draft):
            raise_error("server.shifu.copyCourseDemoNotAllowed")

        action_user_bid = normalized_operator_user_bid
        now = datetime.now()
        new_shifu_bid = generate_id(app)
        resolved_new_course_name = _resolve_course_copy_title(
            source_draft.title,
            new_course_name,
        )
        source_outlines = _load_latest_active_draft_outlines(normalized_shifu_bid)
        outline_bid_map: Dict[str, str] = {
            str(item.outline_item_bid or "").strip(): generate_id(app)
            for item in source_outlines
        }

        _run_course_copy_draft_risk_check(
            app,
            source_draft=source_draft,
            target_shifu_bid=new_shifu_bid,
            operator_user_bid=action_user_bid,
            new_course_name=resolved_new_course_name,
        )
        for source_outline in source_outlines:
            old_outline_bid = str(source_outline.outline_item_bid or "").strip()
            _run_course_copy_outline_risk_check(
                app,
                source_outline=source_outline,
                target_outline_bid=outline_bid_map[old_outline_bid],
                operator_user_bid=action_user_bid,
            )

        target_creator_result = _prepare_operator_target_creator(
            app,
            contact_type=normalized_contact_type,
            identifier=normalized_identifier,
            previous_creator_user_bid=str(source_draft.created_user_bid or "").strip(),
            allow_same_user=True,
        )
        target_aggregate = target_creator_result["target_aggregate"]
        target_user_bid = target_creator_result["target_user_bid"]
        created_new_user = target_creator_result["created_new_user"]
        granted_demo_permissions = target_creator_result["granted_demo_permissions"]
        creator_granted_now = target_creator_result["creator_granted_now"]

        new_draft = source_draft.clone()
        new_draft.shifu_bid = new_shifu_bid
        new_draft.title = resolved_new_course_name
        new_draft.created_at = now
        new_draft.updated_at = now
        new_draft.created_user_bid = target_user_bid
        new_draft.updated_user_bid = action_user_bid
        new_draft.deleted = 0
        db.session.add(new_draft)
        db.session.flush()

        source_outline_map = {
            str(item.outline_item_bid or "").strip(): item for item in source_outlines
        }
        copied_outlines: Dict[str, DraftOutlineItem] = {}

        for source_outline in source_outlines:
            old_outline_bid = str(source_outline.outline_item_bid or "").strip()
            new_outline_bid = outline_bid_map[old_outline_bid]

            new_outline = source_outline.clone()
            new_outline.shifu_bid = new_shifu_bid
            new_outline.outline_item_bid = new_outline_bid
            new_outline.parent_bid = ""
            new_outline.prerequisite_item_bids = ""
            new_outline.created_at = now
            new_outline.updated_at = now
            new_outline.created_user_bid = target_user_bid
            new_outline.updated_user_bid = action_user_bid
            new_outline.deleted = 0
            db.session.add(new_outline)
            db.session.flush()
            copied_outlines[old_outline_bid] = new_outline

        for old_outline_bid, copied_outline in copied_outlines.items():
            source_outline = source_outline_map[old_outline_bid]
            parent_old_bid = str(source_outline.parent_bid or "").strip()
            if parent_old_bid:
                copied_outline.parent_bid = outline_bid_map.get(parent_old_bid, "")

            prerequisite_old_bids = [
                bid.strip()
                for bid in str(source_outline.prerequisite_item_bids or "").split(",")
                if bid.strip()
            ]
            copied_outline.prerequisite_item_bids = ",".join(
                outline_bid_map[bid]
                for bid in prerequisite_old_bids
                if bid in outline_bid_map
            )

        save_shifu_history(app, action_user_bid, new_shifu_bid, new_draft.id)
        outline_tree = _build_outline_history_tree(list(copied_outlines.values()))
        save_outline_tree_history(
            app,
            action_user_bid,
            new_shifu_bid,
            outline_tree,
            new_draft.id,
        )
        _copy_course_variable_definitions(
            source_shifu_bid=normalized_shifu_bid,
            target_shifu_bid=new_shifu_bid,
            creator_user_bid=target_user_bid,
            updated_user_bid=action_user_bid,
            now=now,
        )

        db.session.commit()
        if creator_granted_now:
            _get_legacy_admin_symbol(
                "run_creator_granted_post_auth", run_creator_granted_post_auth
            )(
                app,
                user_id=target_user_bid,
                source="operator_copy_course",
                login_context="admin",
                created_new_user=created_new_user,
                language=target_aggregate.user_language,
            )

        return {
            "source_shifu_bid": normalized_shifu_bid,
            "new_shifu_bid": new_shifu_bid,
            "new_course_name": resolved_new_course_name,
            "target_creator_user_bid": target_user_bid,
            "created_new_user": created_new_user,
            "granted_demo_permissions": granted_demo_permissions,
        }


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


def _load_operator_course_detail_source(shifu_bid: str):
    draft, published = _load_latest_course_versions(shifu_bid)
    visible_draft = draft if draft and _is_operator_visible_course(draft) else None
    visible_published = (
        published if published and _is_operator_visible_course(published) else None
    )
    if visible_draft is None and visible_published is None:
        return None
    return {
        "course": visible_draft or visible_published,
        "course_status": (
            COURSE_STATUS_PUBLISHED if visible_published else COURSE_STATUS_UNPUBLISHED
        ),
        "outline_model": DraftOutlineItem if visible_draft else PublishedOutlineItem,
    }


def _load_latest_outline_items(model, shifu_bid: str):
    latest_subquery = (
        db.session.query(db.func.max(model.id).label("max_id"))
        .filter(
            model.shifu_bid == shifu_bid,
        )
        .group_by(model.outline_item_bid)
        .subquery()
    )
    rows = (
        db.session.query(model)
        .filter(
            model.id.in_(db.session.query(latest_subquery.c.max_id)),
            model.deleted == 0,
        )
        .all()
    )

    def _position_key(item) -> tuple[tuple[int, int | str], ...]:
        position = str(getattr(item, "position", "") or "").strip()
        if not position:
            return ()
        key_parts: list[tuple[int, int | str]] = []
        for part in position.split("."):
            normalized_part = part.strip()
            if not normalized_part:
                continue
            if normalized_part.isdigit():
                key_parts.append((0, int(normalized_part)))
            else:
                key_parts.append((1, normalized_part))
        return tuple(key_parts)

    return sorted(rows, key=_position_key)


def _resolve_learning_permission(item_type: Optional[int]) -> str:
    if item_type == UNIT_TYPE_VALUE_GUEST:
        return "guest"
    if item_type == UNIT_TYPE_VALUE_TRIAL:
        return "free"
    if item_type == UNIT_TYPE_VALUE_NORMAL:
        return "paid"
    return "unknown"


def _resolve_content_status(item) -> str:
    if str(getattr(item, "content", "") or "").strip():
        return "has"
    return "empty"


def _resolve_outline_prompt_source(item) -> str:
    parent_bid = str(getattr(item, "parent_bid", "") or "").strip()
    if parent_bid:
        return PROMPT_SOURCE_LESSON
    return PROMPT_SOURCE_CHAPTER


def _resolve_prompt_with_fallback(
    *,
    outline_item,
    outline_item_map: Dict[str, DraftOutlineItem | PublishedOutlineItem],
    course,
    field_name: str,
) -> tuple[str, str]:
    current_item = outline_item
    visited_bids: set[str] = set()

    while current_item is not None:
        prompt_value = str(getattr(current_item, field_name, "") or "").strip()
        if prompt_value:
            return prompt_value, _resolve_outline_prompt_source(current_item)

        parent_bid = str(getattr(current_item, "parent_bid", "") or "").strip()
        if not parent_bid or parent_bid in visited_bids:
            break
        visited_bids.add(parent_bid)
        current_item = outline_item_map.get(parent_bid)

    course_prompt_value = str(getattr(course, field_name, "") or "").strip()
    if course_prompt_value:
        return course_prompt_value, PROMPT_SOURCE_COURSE

    return "", ""


def _build_chapter_tree(
    items,
    user_map: Dict[str, Dict[str, str]],
    *,
    follow_up_count_map: Dict[str, int],
    rating_count_map: Dict[str, int],
    rating_score_map: Dict[str, str],
) -> list[AdminOperationCourseDetailChapterDTO]:
    node_map: Dict[str, AdminOperationCourseDetailChapterDTO] = {}
    ordered_nodes: list[AdminOperationCourseDetailChapterDTO] = []
    for item in items:
        bid = str(item.outline_item_bid or "").strip()
        if not bid:
            continue
        modifier_user_bid = str(getattr(item, "updated_user_bid", "") or "").strip()
        modifier = user_map.get(modifier_user_bid, {})
        node = AdminOperationCourseDetailChapterDTO(
            outline_item_bid=bid,
            title=item.title or "",
            parent_bid=item.parent_bid or "",
            position=item.position or "",
            node_type="chapter" if not (item.parent_bid or "").strip() else "lesson",
            learning_permission=_resolve_learning_permission(
                getattr(item, "type", None)
            ),
            is_visible=not bool(getattr(item, "hidden", 0)),
            content_status=_resolve_content_status(item),
            follow_up_count=int(follow_up_count_map.get(bid, 0) or 0),
            rating_score=rating_score_map.get(bid, ""),
            rating_count=int(rating_count_map.get(bid, 0) or 0),
            modifier_user_bid=modifier_user_bid,
            modifier_mobile=modifier.get("mobile", ""),
            modifier_email=modifier.get("email", ""),
            modifier_nickname=modifier.get("nickname", ""),
            updated_at=_format_operator_datetime(item.updated_at),
            children=[],
        )
        node_map[bid] = node
        ordered_nodes.append(node)

    roots: list[AdminOperationCourseDetailChapterDTO] = []
    for node in ordered_nodes:
        parent_bid = node.parent_bid.strip()
        parent = node_map.get(parent_bid) if parent_bid else None
        if parent is None:
            roots.append(node)
            continue
        parent.children.append(node)

    def _rollup_learning_stats(
        node: AdminOperationCourseDetailChapterDTO,
    ) -> tuple[int, int]:
        follow_up_count = int(node.follow_up_count or 0)
        rating_count = int(node.rating_count or 0)
        for child in node.children:
            child_follow_up_count, child_rating_count = _rollup_learning_stats(child)
            follow_up_count += child_follow_up_count
            rating_count += child_rating_count
        node.follow_up_count = follow_up_count
        node.rating_count = rating_count
        return follow_up_count, rating_count

    for root in roots:
        _rollup_learning_stats(root)
    return roots


def _load_outline_learning_stats(
    shifu_bid: str,
    outline_item_bids: Sequence[str],
) -> tuple[Dict[str, int], Dict[str, int], Dict[str, str]]:
    normalized_outline_item_bids = [
        str(outline_item_bid or "").strip()
        for outline_item_bid in outline_item_bids
        if str(outline_item_bid or "").strip()
    ]
    if not normalized_outline_item_bids:
        return {}, {}, {}

    follow_up_rows = (
        db.session.query(
            LearnGeneratedBlock.outline_item_bid,
            db.func.count(LearnGeneratedBlock.id),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
            LearnGeneratedBlock.outline_item_bid.in_(normalized_outline_item_bids),
        )
        .group_by(LearnGeneratedBlock.outline_item_bid)
        .all()
    )
    follow_up_count_map = {
        str(outline_item_bid or "").strip(): int(count or 0)
        for outline_item_bid, count in follow_up_rows
        if str(outline_item_bid or "").strip()
    }

    rating_rows = (
        db.session.query(
            LearnLessonFeedback.outline_item_bid,
            db.func.count(LearnLessonFeedback.id),
            db.func.avg(LearnLessonFeedback.score),
        )
        .filter(
            LearnLessonFeedback.shifu_bid == shifu_bid,
            LearnLessonFeedback.deleted == 0,
            LearnLessonFeedback.outline_item_bid.in_(normalized_outline_item_bids),
        )
        .group_by(LearnLessonFeedback.outline_item_bid)
        .all()
    )
    rating_count_map: Dict[str, int] = {}
    rating_score_map: Dict[str, str] = {}
    for outline_item_bid, count, score in rating_rows:
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        if not normalized_outline_item_bid:
            continue
        rating_count_map[normalized_outline_item_bid] = int(count or 0)
        rating_score_map[normalized_outline_item_bid] = _format_average_score(score)

    return follow_up_count_map, rating_count_map, rating_score_map


def _load_operator_course_outline_items(
    shifu_bid: str,
) -> tuple[dict[str, object], list[DraftOutlineItem | PublishedOutlineItem]]:
    detail_source = _load_operator_course_detail_source(shifu_bid)
    if detail_source is None:
        raise_error("server.shifu.shifuNotFound")

    outline_model = detail_source["outline_model"]
    outline_items = _load_latest_outline_items(outline_model, shifu_bid)

    return detail_source, outline_items


def _resolve_visible_leaf_outline_bids(
    outline_items: Sequence[DraftOutlineItem | PublishedOutlineItem],
) -> list[str]:
    visible_item_bids: Set[str] = set()
    visible_parent_bids: Set[str] = set()
    for item in outline_items:
        if bool(getattr(item, "hidden", 0)):
            continue
        outline_item_bid = str(getattr(item, "outline_item_bid", "") or "").strip()
        parent_bid = str(getattr(item, "parent_bid", "") or "").strip()
        if not outline_item_bid:
            continue
        visible_item_bids.add(outline_item_bid)
        if parent_bid:
            visible_parent_bids.add(parent_bid)
    return sorted(visible_item_bids - visible_parent_bids)


def _build_course_outline_context_map(
    outline_items: Sequence[DraftOutlineItem | PublishedOutlineItem],
) -> Dict[str, Dict[str, str]]:
    outline_item_map = {
        str(getattr(item, "outline_item_bid", "") or "").strip(): item
        for item in outline_items
        if str(getattr(item, "outline_item_bid", "") or "").strip()
    }
    context_map: Dict[str, Dict[str, str]] = {}

    for outline_item_bid, item in outline_item_map.items():
        lesson_title = str(getattr(item, "title", "") or "").strip()
        lesson_outline_item_bid = outline_item_bid
        chapter_title = lesson_title
        chapter_outline_item_bid = outline_item_bid
        current_item = item
        visited_bids = {outline_item_bid}

        while current_item is not None:
            parent_bid = str(getattr(current_item, "parent_bid", "") or "").strip()
            if not parent_bid or parent_bid in visited_bids:
                break
            visited_bids.add(parent_bid)
            parent_item = outline_item_map.get(parent_bid)
            if parent_item is None:
                break
            chapter_title = str(getattr(parent_item, "title", "") or "").strip()
            chapter_outline_item_bid = parent_bid
            current_item = parent_item

        context_map[outline_item_bid] = {
            "chapter_outline_item_bid": chapter_outline_item_bid,
            "chapter_title": chapter_title,
            "lesson_outline_item_bid": lesson_outline_item_bid,
            "lesson_title": lesson_title,
        }

    return context_map


def _build_course_follow_up_base_subquery(shifu_bid: str):
    return (
        db.session.query(
            LearnGeneratedBlock.id.label("id"),
            LearnGeneratedBlock.generated_block_bid.label("generated_block_bid"),
            LearnGeneratedBlock.progress_record_bid.label("progress_record_bid"),
            LearnGeneratedBlock.user_bid.label("user_bid"),
            LearnGeneratedBlock.outline_item_bid.label("outline_item_bid"),
            LearnGeneratedBlock.generated_content.label("follow_up_content"),
            LearnGeneratedBlock.created_at.label("created_at"),
            db.func.row_number()
            .over(
                partition_by=LearnGeneratedBlock.progress_record_bid,
                order_by=(
                    LearnGeneratedBlock.created_at.asc(),
                    LearnGeneratedBlock.id.asc(),
                ),
            )
            .label("turn_index"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
        )
        .subquery()
    )


def _build_follow_up_user_keyword_filter(
    user_bid_column: Any, keyword: str
) -> Any | None:
    normalized = _normalize_identifier(keyword)
    if not normalized:
        return None

    credential_match_exists = (
        db.session.query(AuthCredential.id)
        .filter(
            AuthCredential.user_bid == user_bid_column,
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            AuthCredential.identifier.ilike(f"%{normalized}%"),
        )
        .exists()
    )

    user_filters = [UserEntity.nickname.ilike(f"%{normalized}%")]
    if "@" in normalized or normalized.isdigit():
        user_filters.append(UserEntity.user_identify.ilike(f"%{normalized}%"))

    user_match_exists = (
        db.session.query(UserEntity.id)
        .filter(
            UserEntity.user_bid == user_bid_column,
            UserEntity.deleted == 0,
            or_(*user_filters),
        )
        .exists()
    )

    return or_(credential_match_exists, user_match_exists)


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


def _resolve_follow_up_matching_outline_bids(
    outline_context_map: Dict[str, Dict[str, str]],
    chapter_keyword: str,
) -> Optional[Set[str]]:
    normalized_keyword = str(chapter_keyword or "").strip().lower()
    if not normalized_keyword:
        return None

    return {
        outline_item_bid
        for outline_item_bid, context in outline_context_map.items()
        if normalized_keyword
        in str(context.get("chapter_title", "") or "").strip().lower()
        or normalized_keyword
        in str(context.get("lesson_title", "") or "").strip().lower()
    }


def _resolve_follow_up_answer_block(
    blocks: Sequence[LearnGeneratedBlock],
    index: int,
) -> LearnGeneratedBlock | None:
    ask_position = int(blocks[index].position or 0)
    for next_block in blocks[index + 1 :]:
        next_block_type = int(next_block.type or 0)
        next_block_role = int(next_block.role or 0)
        if (
            next_block_type == BLOCK_TYPE_MDASK_VALUE
            and next_block_role == ROLE_STUDENT
        ):
            return None
        if next_block_type == BLOCK_TYPE_MDANSWER_VALUE:
            return next_block
        if (
            next_block_type == BLOCK_TYPE_MDCONTENT_VALUE
            and next_block_role == ROLE_TEACHER
            and int(next_block.position or 0) == ask_position
        ):
            return next_block
    return None


def _resolve_follow_up_answer_content(block: LearnGeneratedBlock | None) -> str:
    if block is None:
        return ""

    generated_content = str(getattr(block, "generated_content", "") or "").strip()
    if generated_content:
        return generated_content

    return str(getattr(block, "block_content_conf", "") or "").strip()


def _load_follow_up_groups_for_progress_record(
    progress_record_bid: str,
) -> list[dict[str, Any]]:
    normalized_progress_record_bid = str(progress_record_bid or "").strip()
    if not normalized_progress_record_bid:
        return []

    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid == normalized_progress_record_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            or_(
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                    LearnGeneratedBlock.role == ROLE_STUDENT,
                ),
                LearnGeneratedBlock.type == BLOCK_TYPE_MDANSWER_VALUE,
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
                    LearnGeneratedBlock.role == ROLE_TEACHER,
                ),
            ),
        )
        .order_by(LearnGeneratedBlock.created_at.asc(), LearnGeneratedBlock.id.asc())
        .all()
    )
    groups: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if (
            int(block.type or 0) != BLOCK_TYPE_MDASK_VALUE
            or int(block.role or 0) != ROLE_STUDENT
        ):
            continue
        answer_block = _resolve_follow_up_answer_block(blocks, index)
        groups.append(
            {
                "ask_block": block,
                "answer_block": answer_block,
            }
        )
    return groups


def _load_follow_up_groups_for_progress_records(
    progress_record_bids: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    normalized_progress_record_bids = sorted(
        {
            str(progress_record_bid or "").strip()
            for progress_record_bid in progress_record_bids
            if str(progress_record_bid or "").strip()
        }
    )
    if not normalized_progress_record_bids:
        return {}

    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid.in_(
                normalized_progress_record_bids
            ),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            or_(
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                    LearnGeneratedBlock.role == ROLE_STUDENT,
                ),
                LearnGeneratedBlock.type == BLOCK_TYPE_MDANSWER_VALUE,
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
                    LearnGeneratedBlock.role == ROLE_TEACHER,
                ),
            ),
        )
        .order_by(
            LearnGeneratedBlock.progress_record_bid.asc(),
            LearnGeneratedBlock.created_at.asc(),
            LearnGeneratedBlock.id.asc(),
        )
        .all()
    )
    blocks_by_progress_record: dict[str, list[LearnGeneratedBlock]] = {}
    for block in blocks:
        progress_record_bid = str(
            getattr(block, "progress_record_bid", "") or ""
        ).strip()
        if not progress_record_bid:
            continue
        blocks_by_progress_record.setdefault(progress_record_bid, []).append(block)

    groups_by_progress_record: dict[str, list[dict[str, Any]]] = {}
    for progress_record_bid, progress_blocks in blocks_by_progress_record.items():
        groups: list[dict[str, Any]] = []
        for index, block in enumerate(progress_blocks):
            if (
                int(block.type or 0) != BLOCK_TYPE_MDASK_VALUE
                or int(block.role or 0) != ROLE_STUDENT
            ):
                continue
            groups.append(
                {
                    "ask_block": block,
                    "answer_block": _resolve_follow_up_answer_block(
                        progress_blocks, index
                    ),
                }
            )
        groups_by_progress_record[progress_record_bid] = groups
    return groups_by_progress_record


def _resolve_follow_up_source_from_element(
    *,
    shifu_bid: str,
    user_bid: str,
    progress_record_bid: str,
    answer_generated_block_bid: str,
    fallback_position: int,
    ask_created_at: datetime | None,
) -> dict[str, Any]:
    normalized_answer_generated_block_bid = str(
        answer_generated_block_bid or ""
    ).strip()
    normalized_user_bid = str(user_bid or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()
    normalized_progress_record_bid = str(progress_record_bid or "").strip()
    if (
        not normalized_answer_generated_block_bid
        or not normalized_user_bid
        or not normalized_shifu_bid
        or not normalized_progress_record_bid
    ):
        return {}

    follow_up_elements = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.generated_block_bid
            == normalized_answer_generated_block_bid,
            LearnGeneratedElement.user_bid == normalized_user_bid,
            LearnGeneratedElement.shifu_bid == normalized_shifu_bid,
            LearnGeneratedElement.progress_record_bid == normalized_progress_record_bid,
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
    if not follow_up_elements:
        return {}

    anchor_element_bid = ""
    for row in follow_up_elements:
        payload = _deserialize_payload(str(getattr(row, "payload", "") or ""))
        anchor_element_bid = str(
            getattr(payload, "anchor_element_bid", "") or ""
        ).strip()
        if anchor_element_bid:
            break
    if not anchor_element_bid:
        return {}

    anchor_query = LearnGeneratedElement.query.filter(
        LearnGeneratedElement.shifu_bid == normalized_shifu_bid,
        LearnGeneratedElement.user_bid == normalized_user_bid,
        LearnGeneratedElement.progress_record_bid == normalized_progress_record_bid,
        LearnGeneratedElement.event_type == "element",
        or_(
            LearnGeneratedElement.element_bid == anchor_element_bid,
            LearnGeneratedElement.target_element_bid == anchor_element_bid,
        ),
        LearnGeneratedElement.deleted == 0,
    )
    if ask_created_at is not None:
        anchor_query = anchor_query.filter(
            LearnGeneratedElement.created_at <= ask_created_at
        )
    anchor_element = anchor_query.order_by(
        LearnGeneratedElement.created_at.desc(),
        LearnGeneratedElement.sequence_number.desc(),
        LearnGeneratedElement.run_event_seq.desc(),
        LearnGeneratedElement.id.desc(),
    ).first()
    if anchor_element is None:
        return {
            "source_output_content": "",
            "source_output_type": "element",
            "source_position": int(fallback_position or 0),
            "source_element_bid": anchor_element_bid,
            "source_element_type": "",
        }

    return {
        "source_output_content": str(getattr(anchor_element, "content_text", "") or ""),
        "source_output_type": "element",
        "source_position": int(fallback_position or 0),
        "source_element_bid": anchor_element_bid,
        "source_element_type": str(getattr(anchor_element, "element_type", "") or ""),
    }


def _resolve_follow_up_source_from_blocks(
    ask_block: LearnGeneratedBlock,
) -> dict[str, Any]:
    progress_record_bid = str(
        getattr(ask_block, "progress_record_bid", "") or ""
    ).strip()
    if not progress_record_bid:
        return {}

    position = int(getattr(ask_block, "position", 0) or 0)
    query = LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.progress_record_bid == progress_record_bid,
        LearnGeneratedBlock.deleted == 0,
        LearnGeneratedBlock.role == ROLE_TEACHER,
        LearnGeneratedBlock.position == position,
        LearnGeneratedBlock.type.in_(
            [BLOCK_TYPE_MDINTERACTION_VALUE, BLOCK_TYPE_MDCONTENT_VALUE]
        ),
    )
    ask_created_at = getattr(ask_block, "created_at", None)
    ask_block_id = int(getattr(ask_block, "id", 0) or 0)
    if ask_created_at is not None and ask_block_id > 0:
        query = query.filter(
            or_(
                LearnGeneratedBlock.created_at < ask_created_at,
                and_(
                    LearnGeneratedBlock.created_at == ask_created_at,
                    LearnGeneratedBlock.id < ask_block_id,
                ),
            )
        )
    elif ask_block_id > 0:
        query = query.filter(LearnGeneratedBlock.id < ask_block_id)

    source_block = query.order_by(
        LearnGeneratedBlock.created_at.desc(),
        LearnGeneratedBlock.id.desc(),
    ).first()
    if source_block is None:
        return {}

    source_type = (
        "interaction"
        if int(getattr(source_block, "type", 0) or 0) == BLOCK_TYPE_MDINTERACTION_VALUE
        else "content"
    )
    if source_type == "interaction":
        source_content = str(
            getattr(source_block, "block_content_conf", "") or ""
        ).strip()
        if not source_content:
            source_content = str(getattr(source_block, "generated_content", "") or "")
    else:
        source_content = str(
            getattr(source_block, "generated_content", "") or ""
        ).strip()
        if not source_content:
            source_content = str(getattr(source_block, "block_content_conf", "") or "")

    return {
        "source_output_content": source_content,
        "source_output_type": source_type,
        "source_position": int(getattr(source_block, "position", 0) or 0),
        "source_element_bid": "",
        "source_element_type": "",
    }


def _resolve_follow_up_source(
    *,
    ask_block: LearnGeneratedBlock,
    answer_block: LearnGeneratedBlock | None,
) -> dict[str, Any]:
    fallback_position = int(getattr(ask_block, "position", 0) or 0)
    if answer_block is not None:
        source = _resolve_follow_up_source_from_element(
            shifu_bid=str(getattr(ask_block, "shifu_bid", "") or ""),
            user_bid=str(getattr(ask_block, "user_bid", "") or ""),
            progress_record_bid=str(
                getattr(ask_block, "progress_record_bid", "") or ""
            ),
            answer_generated_block_bid=str(
                getattr(answer_block, "generated_block_bid", "") or ""
            ),
            fallback_position=fallback_position,
            ask_created_at=getattr(ask_block, "created_at", None),
        )
        if source:
            return source

    source = _resolve_follow_up_source_from_blocks(ask_block)
    if source:
        return source

    return {
        "source_output_content": "",
        "source_output_type": "",
        "source_position": fallback_position,
        "source_element_bid": "",
        "source_element_type": "",
    }


def _build_follow_up_source_status_map(
    *,
    shifu_bid: str,
    generated_block_bids: list[str],
) -> dict[str, bool]:
    normalized_generated_block_bids = sorted(
        {
            str(generated_block_bid or "").strip()
            for generated_block_bid in generated_block_bids
            if str(generated_block_bid or "").strip()
        }
    )
    if not normalized_generated_block_bids:
        return {}

    ask_blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.generated_block_bid.in_(
                normalized_generated_block_bids
            ),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
        )
        .order_by(LearnGeneratedBlock.id.asc())
        .all()
    )
    if not ask_blocks:
        return {}

    groups_cache = _load_follow_up_groups_for_progress_records(
        [
            str(getattr(ask_block, "progress_record_bid", "") or "")
            for ask_block in ask_blocks
        ]
    )
    answer_block_map: dict[str, LearnGeneratedBlock | None] = {}
    for groups in groups_cache.values():
        for group in groups:
            group_ask_block = group.get("ask_block")
            group_generated_block_bid = str(
                getattr(group_ask_block, "generated_block_bid", "") or ""
            ).strip()
            if not group_generated_block_bid:
                continue
            answer_block_map[group_generated_block_bid] = group.get("answer_block")
    source_status_map: dict[str, bool] = {}

    for ask_block in ask_blocks:
        generated_block_bid = str(
            getattr(ask_block, "generated_block_bid", "") or ""
        ).strip()
        if not generated_block_bid:
            continue

        source_info = _resolve_follow_up_source(
            ask_block=ask_block,
            answer_block=answer_block_map.get(generated_block_bid),
        )
        source_status_map[generated_block_bid] = bool(
            str(source_info.get("source_output_content", "") or "").strip()
        )

    return source_status_map


def _load_course_related_user_bids(
    shifu_bid: str,
    *,
    creator_user_bid: str,
) -> tuple[Set[str], Set[str]]:
    order_user_bids = {
        str(user_bid or "").strip()
        for (user_bid,) in db.session.query(Order.user_bid)
        .filter(
            Order.shifu_bid == shifu_bid,
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid != "",
        )
        .all()
        if str(user_bid or "").strip()
    }
    permission_user_bids = {
        str(user_bid or "").strip()
        for (user_bid,) in db.session.query(AiCourseAuth.user_id)
        .filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.status == 1,
            AiCourseAuth.user_id != "",
        )
        .all()
        if str(user_bid or "").strip()
    }
    learning_user_bids = {
        str(user_bid or "").strip()
        for (user_bid,) in db.session.query(LearnProgressRecord.user_bid)
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid != "",
        )
        .distinct()
        .all()
        if str(user_bid or "").strip()
    }

    learner_user_bids = order_user_bids | permission_user_bids | learning_user_bids
    related_user_bids = set(learner_user_bids)
    normalized_creator_user_bid = str(creator_user_bid or "").strip()
    if normalized_creator_user_bid:
        related_user_bids.add(normalized_creator_user_bid)
    return related_user_bids, learner_user_bids


def _load_course_user_paid_amount_map(
    shifu_bid: str,
    user_bids: Sequence[str],
) -> Dict[str, Decimal]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
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
            Order.shifu_bid == shifu_bid,
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


def _load_course_user_last_learning_map(
    shifu_bid: str,
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
            LearnProgressRecord.user_bid,
            db.func.max(LearnProgressRecord.updated_at).label("last_learning_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
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


def _load_course_user_joined_at_map(
    shifu_bid: str,
    user_bids: Sequence[str],
    *,
    creator_user_bid: str,
    course_created_at: Optional[datetime],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    joined_at_map: Dict[str, datetime] = {}

    def _merge_rows(rows: Sequence[tuple[str, Any]]) -> None:
        for user_bid, joined_at in rows:
            normalized_user_bid = str(user_bid or "").strip()
            normalized_joined_at = _coerce_operator_datetime(joined_at)
            if not normalized_user_bid or normalized_joined_at is None:
                continue
            current = joined_at_map.get(normalized_user_bid)
            if current is None or normalized_joined_at < current:
                joined_at_map[normalized_user_bid] = normalized_joined_at

    _merge_rows(
        db.session.query(
            Order.user_bid,
            db.func.min(Order.created_at).label("joined_at"),
        )
        .filter(
            Order.shifu_bid == shifu_bid,
            Order.user_bid.in_(normalized_user_bids),
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
        )
        .group_by(Order.user_bid)
        .all()
    )
    _merge_rows(
        db.session.query(
            AiCourseAuth.user_id,
            db.func.min(
                db.func.coalesce(AiCourseAuth.updated_at, AiCourseAuth.created_at)
            ).label("joined_at"),
        )
        .filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.user_id.in_(normalized_user_bids),
            AiCourseAuth.status == 1,
        )
        .group_by(AiCourseAuth.user_id)
        .all()
    )
    _merge_rows(
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.min(LearnProgressRecord.created_at).label("joined_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )

    normalized_creator_user_bid = str(creator_user_bid or "").strip()
    normalized_course_created_at = _coerce_operator_datetime(course_created_at)
    if normalized_creator_user_bid and normalized_course_created_at:
        current = joined_at_map.get(normalized_creator_user_bid)
        if current is None or normalized_course_created_at < current:
            joined_at_map[normalized_creator_user_bid] = normalized_course_created_at

    return joined_at_map


def _load_course_user_learned_lesson_count_map(
    shifu_bid: str,
    user_bids: Sequence[str],
    leaf_outline_bids: Sequence[str],
) -> Dict[str, int]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    normalized_leaf_outline_bids = [
        str(outline_item_bid or "").strip()
        for outline_item_bid in leaf_outline_bids
        if str(outline_item_bid or "").strip()
    ]
    if not normalized_user_bids or not normalized_leaf_outline_bids:
        return {}

    rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.count(db.func.distinct(LearnProgressRecord.outline_item_bid)).label(
                "learned_lesson_count"
            ),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.outline_item_bid.in_(normalized_leaf_outline_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): int(learned_lesson_count or 0)
        for user_bid, learned_lesson_count in rows
        if str(user_bid or "").strip()
    }


def get_operator_course_detail(
    app: Flask,
    *,
    shifu_bid: str,
) -> AdminOperationCourseDetailDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        course = detail_source["course"]
        course_status = detail_source["course_status"]

        creator_user_bid = str(course.created_user_bid or "").strip()
        visit_count_30d = _get_legacy_admin_symbol(
            "get_course_visit_count_30d", get_course_visit_count_30d
        )(app, normalized_shifu_bid)
        learner_count = (
            db.session.query(db.func.count(db.distinct(LearnProgressRecord.user_bid)))
            .filter(
                LearnProgressRecord.shifu_bid == normalized_shifu_bid,
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            )
            .scalar()
            or 0
        )
        order_amount_expr = _build_course_order_amount_expr()
        order_summary = (
            db.session.query(
                db.func.count(Order.id).label("order_count"),
                db.func.coalesce(db.func.sum(order_amount_expr), 0).label(
                    "order_amount"
                ),
            )
            .filter(
                Order.shifu_bid == normalized_shifu_bid,
                Order.deleted == 0,
                Order.status == ORDER_STATUS_SUCCESS,
            )
            .first()
        )
        follow_up_count = (
            db.session.query(db.func.count(LearnGeneratedBlock.id))
            .filter(
                LearnGeneratedBlock.shifu_bid == normalized_shifu_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                LearnGeneratedBlock.role == ROLE_STUDENT,
            )
            .scalar()
            or 0
        )
        rating_score = (
            db.session.query(db.func.avg(LearnLessonFeedback.score))
            .filter(
                LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
                LearnLessonFeedback.deleted == 0,
            )
            .scalar()
        )
        detail_user_bids = {
            user_bid
            for user_bid in [creator_user_bid]
            + [
                str(getattr(item, "updated_user_bid", "") or "")
                for item in outline_items
            ]
            if str(user_bid or "").strip()
        }
        detail_user_map = _load_user_map(sorted(detail_user_bids))
        creator = detail_user_map.get(creator_user_bid, {})
        outline_learning_stats = _load_outline_learning_stats(
            normalized_shifu_bid,
            [
                str(getattr(item, "outline_item_bid", "") or "")
                for item in outline_items
            ],
        )
        follow_up_count_map, rating_count_map, rating_score_map = outline_learning_stats
        visible_leaf_outline_bids = _resolve_visible_leaf_outline_bids(outline_items)
        credit_metrics = _build_operator_course_credit_metrics(
            normalized_shifu_bid,
            visible_leaf_outline_bids,
        )

        return AdminOperationCourseDetailDTO(
            basic_info=AdminOperationCourseDetailBasicInfoDTO(
                shifu_bid=normalized_shifu_bid,
                course_name=course.title or "",
                course_status=course_status,
                creator_user_bid=creator_user_bid,
                creator_mobile=creator.get("mobile", ""),
                creator_email=creator.get("email", ""),
                creator_nickname=creator.get("nickname", ""),
                created_at=_format_operator_datetime(course.created_at),
                updated_at=_format_operator_datetime(course.updated_at),
            ),
            metrics=AdminOperationCourseDetailMetricsDTO(
                visit_count_30d=int(visit_count_30d),
                learner_count=int(learner_count),
                order_count=int(getattr(order_summary, "order_count", 0) or 0),
                order_amount=_format_decimal(
                    Decimal(str(getattr(order_summary, "order_amount", 0) or 0))
                ),
                follow_up_count=int(follow_up_count),
                rating_score=_format_average_score(rating_score),
                credit_consumed_total=credit_metrics["credit_consumed_total"],
                credit_usage_count=credit_metrics["credit_usage_count"],
                credit_user_count=credit_metrics["credit_user_count"],
                completed_credit_user_count=credit_metrics[
                    "completed_credit_user_count"
                ],
                completed_user_avg_credits=credit_metrics["completed_user_avg_credits"],
            ),
            chapters=_build_chapter_tree(
                outline_items,
                detail_user_map,
                follow_up_count_map=follow_up_count_map,
                rating_count_map=rating_count_map,
                rating_score_map=rating_score_map,
            ),
        )


def get_operator_course_prompt(
    app: Flask,
    *,
    shifu_bid: str,
) -> AdminOperationCoursePromptDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        detail_source = _load_operator_course_detail_source(normalized_shifu_bid)
        if detail_source is None:
            raise_error("server.shifu.shifuNotFound")

        course = detail_source["course"]
        return AdminOperationCoursePromptDTO(
            course_prompt=str(getattr(course, "llm_system_prompt", "") or "").strip()
        )


def get_operator_course_users(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> PageNationDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            COURSE_USER_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        course = detail_source["course"]
        creator_user_bid = str(course.created_user_bid or "").strip()
        related_user_bids, learner_user_bids = _load_course_related_user_bids(
            normalized_shifu_bid,
            creator_user_bid=creator_user_bid,
        )
        if not related_user_bids:
            return PageNationDTO(safe_page_index, safe_page_size, 0, [])

        ordered_user_bids = sorted(related_user_bids)
        users = (
            UserEntity.query.filter(
                UserEntity.user_bid.in_(ordered_user_bids),
                UserEntity.deleted == 0,
            )
            .order_by(UserEntity.created_at.desc(), UserEntity.id.desc())
            .all()
        )
        if not users:
            return PageNationDTO(safe_page_index, safe_page_size, 0, [])

        user_bids = [
            str(user.user_bid or "").strip() for user in users if user.user_bid
        ]
        contact_map = _load_course_user_contact_map(user_bids)
        last_login_map = _load_operator_user_last_login_map(user_bids)
        paid_amount_map = _load_course_user_paid_amount_map(
            normalized_shifu_bid, user_bids
        )
        last_learning_map = _load_course_user_last_learning_map(
            normalized_shifu_bid, user_bids
        )
        joined_at_map = _load_course_user_joined_at_map(
            normalized_shifu_bid,
            user_bids,
            creator_user_bid=creator_user_bid,
            course_created_at=getattr(course, "created_at", None),
        )
        visible_leaf_outline_bids = _resolve_visible_leaf_outline_bids(outline_items)
        total_lesson_count = len(visible_leaf_outline_bids)
        learned_lesson_count_map = _load_course_user_learned_lesson_count_map(
            normalized_shifu_bid,
            user_bids,
            visible_leaf_outline_bids,
        )

        keyword = str(filters.get("keyword", "") or "").strip().lower()
        user_role_filter = str(filters.get("user_role", "") or "").strip().lower()
        learning_status_filter = (
            str(filters.get("learning_status", "") or "").strip().lower()
        )
        payment_status_filter = (
            str(filters.get("payment_status", "") or "").strip().lower()
        )

        items_with_sort_keys: list[
            tuple[
                tuple[datetime, datetime, datetime, datetime, str],
                AdminOperationCourseUserDTO,
            ]
        ] = []
        for user in users:
            user_bid = str(user.user_bid or "").strip()
            if not user_bid:
                continue
            contact = contact_map.get(user_bid, {})
            learned_lesson_count = int(learned_lesson_count_map.get(user_bid, 0) or 0)
            learning_status = _resolve_course_user_learning_status(
                learned_lesson_count=learned_lesson_count,
                total_lesson_count=total_lesson_count,
            )
            total_paid_amount = paid_amount_map.get(user_bid)
            is_paid = bool(total_paid_amount and total_paid_amount > 0)
            user_role = _resolve_course_user_role(
                is_creator=bool(user.is_creator),
                is_operator=bool(user.is_operator),
                is_student=user_bid in learner_user_bids,
            )

            if keyword:
                haystack = [
                    user_bid.lower(),
                    str(contact.get("mobile", "") or "").lower(),
                    str(contact.get("email", "") or "").lower(),
                    str(user.nickname or "").lower(),
                ]
                if not any(keyword in value for value in haystack if value):
                    continue

            if (
                user_role_filter
                and user_role_filter != "all"
                and user_role != user_role_filter
            ):
                continue
            if (
                learning_status_filter
                and learning_status_filter != "all"
                and learning_status != learning_status_filter
            ):
                continue
            if payment_status_filter == "paid" and not is_paid:
                continue
            if payment_status_filter == "unpaid" and is_paid:
                continue

            last_learning_at = last_learning_map.get(user_bid)
            joined_at = joined_at_map.get(user_bid)
            last_login_at = last_login_map.get(user_bid)
            dto = AdminOperationCourseUserDTO(
                user_bid=user_bid,
                mobile=str(contact.get("mobile", "") or ""),
                email=str(contact.get("email", "") or ""),
                nickname=user.nickname or "",
                user_role=user_role,
                learned_lesson_count=learned_lesson_count,
                total_lesson_count=total_lesson_count,
                learning_status=learning_status,
                is_paid=is_paid,
                total_paid_amount=_format_decimal(total_paid_amount),
                last_learning_at=_format_operator_datetime(last_learning_at),
                joined_at=_format_operator_datetime(joined_at),
                last_login_at=_format_operator_datetime(last_login_at),
            )
            items_with_sort_keys.append(
                (
                    (
                        last_learning_at or datetime.min,
                        joined_at or datetime.min,
                        last_login_at or datetime.min,
                        getattr(user, "created_at", None) or datetime.min,
                        user_bid,
                    ),
                    dto,
                )
            )

        items_with_sort_keys.sort(key=lambda item: item[0], reverse=True)
        items = [item for _, item in items_with_sort_keys]
        total = len(items)
        start = (safe_page_index - 1) * safe_page_size
        end = start + safe_page_size
        paged_items = items[start:end]
        return PageNationDTO(safe_page_index, safe_page_size, total, paged_items)


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
                    created_at=_format_operator_datetime(
                        getattr(row, "created_at", None)
                    ),
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


def get_operator_course_follow_ups(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
    include_summary: bool = True,
) -> AdminOperationCourseFollowUpListDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            COURSE_FOLLOW_UP_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        _detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        outline_context_map = _build_course_outline_context_map(outline_items)

        keyword = str(filters.get("keyword", "") or "").strip()
        chapter_keyword = str(filters.get("chapter_keyword", "") or "").strip().lower()
        source_status = str(filters.get("source_status", "") or "").strip().lower()
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        if source_status not in {"", "resolved", "missing"}:
            raise_param_error("source_status")
        follow_up_base = _build_course_follow_up_base_subquery(normalized_shifu_bid)
        user_keyword_filter = _build_follow_up_user_keyword_filter(
            follow_up_base.c.user_bid,
            keyword,
        )
        matching_outline_item_bids = _resolve_follow_up_matching_outline_bids(
            outline_context_map,
            chapter_keyword,
        )

        if chapter_keyword and not matching_outline_item_bids:
            return AdminOperationCourseFollowUpListDTO(
                summary=AdminOperationCourseFollowUpSummaryDTO(
                    follow_up_count=0,
                    user_count=0,
                    lesson_count=0,
                    latest_follow_up_at="",
                ),
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        filtered_query = db.session.query(follow_up_base)
        if user_keyword_filter is not None:
            filtered_query = filtered_query.filter(user_keyword_filter)
        if matching_outline_item_bids is not None:
            filtered_query = filtered_query.filter(
                follow_up_base.c.outline_item_bid.in_(
                    sorted(matching_outline_item_bids)
                )
            )
        if start_time:
            filtered_query = filtered_query.filter(
                follow_up_base.c.created_at >= start_time
            )
        if end_time:
            filtered_query = filtered_query.filter(
                follow_up_base.c.created_at <= end_time
            )

        summary_row = None
        filtered_source_status_map: dict[str, bool] | None = None
        if source_status:
            filtered_rows = filtered_query.order_by(
                follow_up_base.c.created_at.desc(),
                follow_up_base.c.id.desc(),
            ).all()
            filtered_source_status_map = _build_follow_up_source_status_map(
                shifu_bid=normalized_shifu_bid,
                generated_block_bids=[
                    str(getattr(row, "generated_block_bid", "") or "")
                    for row in filtered_rows
                ],
            )
            filtered_rows = [
                row
                for row in filtered_rows
                if filtered_source_status_map.get(
                    str(getattr(row, "generated_block_bid", "") or "").strip(), False
                )
                == (source_status == "resolved")
            ]
            total = len(filtered_rows)
            if include_summary:
                unique_user_bids = {
                    str(getattr(row, "user_bid", "") or "").strip()
                    for row in filtered_rows
                    if str(getattr(row, "user_bid", "") or "").strip()
                }
                unique_outline_item_bids = {
                    str(getattr(row, "outline_item_bid", "") or "").strip()
                    for row in filtered_rows
                    if str(getattr(row, "outline_item_bid", "") or "").strip()
                }
                latest_follow_up_at = max(
                    (
                        getattr(row, "created_at", None)
                        for row in filtered_rows
                        if getattr(row, "created_at", None) is not None
                    ),
                    default=None,
                )
                summary = AdminOperationCourseFollowUpSummaryDTO(
                    follow_up_count=total,
                    user_count=len(unique_user_bids),
                    lesson_count=len(unique_outline_item_bids),
                    latest_follow_up_at=_format_operator_datetime(latest_follow_up_at),
                )
            else:
                summary = AdminOperationCourseFollowUpSummaryDTO(follow_up_count=total)
        else:
            filtered_follow_ups = filtered_query.subquery()
            if include_summary:
                summary_row = db.session.query(
                    db.func.count(filtered_follow_ups.c.id).label("follow_up_count"),
                    db.func.count(
                        db.func.distinct(
                            db.func.nullif(filtered_follow_ups.c.user_bid, "")
                        )
                    ).label("user_count"),
                    db.func.count(
                        db.func.distinct(
                            db.func.nullif(filtered_follow_ups.c.outline_item_bid, "")
                        )
                    ).label("lesson_count"),
                    db.func.max(filtered_follow_ups.c.created_at).label(
                        "latest_follow_up_at"
                    ),
                ).one()
                total = int(getattr(summary_row, "follow_up_count", 0) or 0)
            else:
                total = int(
                    db.session.query(db.func.count(filtered_follow_ups.c.id)).scalar()
                    or 0
                )

        if total == 0:
            return AdminOperationCourseFollowUpListDTO(
                summary=AdminOperationCourseFollowUpSummaryDTO(),
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        start = (safe_page_index - 1) * safe_page_size
        if source_status:
            paged_rows = filtered_rows[start : start + safe_page_size]
        else:
            paged_rows = (
                db.session.query(filtered_follow_ups)
                .order_by(
                    filtered_follow_ups.c.created_at.desc(),
                    filtered_follow_ups.c.id.desc(),
                )
                .offset(start)
                .limit(safe_page_size)
                .all()
            )
        user_map = _load_user_map(
            sorted(
                {
                    str(getattr(row, "user_bid", "") or "").strip()
                    for row in paged_rows
                    if str(getattr(row, "user_bid", "") or "").strip()
                }
            )
        )
        if source_status and filtered_source_status_map is not None:
            source_status_map = filtered_source_status_map
        else:
            source_status_map = _build_follow_up_source_status_map(
                shifu_bid=normalized_shifu_bid,
                generated_block_bids=[
                    str(getattr(row, "generated_block_bid", "") or "")
                    for row in paged_rows
                ],
            )

        items: list[AdminOperationCourseFollowUpItemDTO] = []
        for row in paged_rows:
            generated_block_bid = str(
                getattr(row, "generated_block_bid", "") or ""
            ).strip()
            outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            created_at = getattr(row, "created_at", None)
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
            items.append(
                AdminOperationCourseFollowUpItemDTO(
                    generated_block_bid=generated_block_bid,
                    progress_record_bid=str(
                        getattr(row, "progress_record_bid", "") or ""
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
                    follow_up_content=str(getattr(row, "follow_up_content", "") or ""),
                    has_source_output=bool(
                        source_status_map.get(generated_block_bid, False)
                    ),
                    turn_index=int(getattr(row, "turn_index", 0) or 0),
                    created_at=_format_operator_datetime(created_at),
                )
            )
        if not source_status and include_summary:
            summary = AdminOperationCourseFollowUpSummaryDTO(
                follow_up_count=total,
                user_count=int(getattr(summary_row, "user_count", 0) or 0),
                lesson_count=int(getattr(summary_row, "lesson_count", 0) or 0),
                latest_follow_up_at=_format_operator_datetime(
                    getattr(summary_row, "latest_follow_up_at", None)
                ),
            )
        elif not source_status:
            summary = AdminOperationCourseFollowUpSummaryDTO(follow_up_count=total)
        return AdminOperationCourseFollowUpListDTO(
            summary=summary,
            items=items,
            page=safe_page_index,
            page_size=safe_page_size,
            total=total,
            page_count=math.ceil(total / safe_page_size) if safe_page_size else 0,
        )


def get_operator_course_ratings(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
    include_summary: bool = True,
) -> AdminOperationCourseRatingListDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            COURSE_RATING_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        _detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        outline_context_map = _build_course_outline_context_map(outline_items)
        keyword = _normalize_identifier(str(filters.get("keyword", "") or "")).lower()
        chapter_keyword = str(filters.get("chapter_keyword", "") or "").strip().lower()
        score_filter = str(filters.get("score", "") or "").strip()
        mode_filter = _resolve_course_rating_mode(str(filters.get("mode", "") or ""))
        has_comment_filter = str(filters.get("has_comment", "") or "").strip().lower()
        sort_by = _resolve_course_rating_sort_by(str(filters.get("sort_by", "") or ""))
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")

        normalized_score_filter: Optional[int] = None
        if score_filter:
            if score_filter not in {"1", "2", "3", "4", "5"}:
                raise_param_error("score")
            normalized_score_filter = int(score_filter)
        if str(filters.get("mode", "") or "").strip() and not mode_filter:
            raise_param_error("mode")
        if has_comment_filter and has_comment_filter != "true":
            raise_param_error("has_comment")
        if str(filters.get("sort_by", "") or "").strip() and not sort_by:
            raise_param_error("sort_by")

        rated_at_expression = db.func.coalesce(
            LearnLessonFeedback.updated_at,
            LearnLessonFeedback.created_at,
        )
        base_filters = [
            LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
            LearnLessonFeedback.deleted == 0,
        ]

        user_keyword_filter = _build_follow_up_user_keyword_filter(
            LearnLessonFeedback.user_bid,
            keyword,
        )
        if user_keyword_filter is not None:
            base_filters.append(user_keyword_filter)

        matching_outline_item_bids = _resolve_follow_up_matching_outline_bids(
            outline_context_map,
            chapter_keyword,
        )
        if matching_outline_item_bids is not None:
            if not matching_outline_item_bids:
                return AdminOperationCourseRatingListDTO(
                    summary=AdminOperationCourseRatingSummaryDTO(),
                    items=[],
                    page=safe_page_index,
                    page_size=safe_page_size,
                    total=0,
                    page_count=0,
                )
            base_filters.append(
                LearnLessonFeedback.outline_item_bid.in_(
                    sorted(matching_outline_item_bids)
                )
            )

        if normalized_score_filter is not None:
            base_filters.append(LearnLessonFeedback.score == normalized_score_filter)
        if mode_filter:
            base_filters.append(LearnLessonFeedback.mode == mode_filter)
        if has_comment_filter == "true":
            base_filters.append(
                db.func.trim(db.func.coalesce(LearnLessonFeedback.comment, "")) != ""
            )
        if start_time:
            base_filters.append(rated_at_expression >= start_time)
        if end_time:
            base_filters.append(rated_at_expression <= end_time)

        summary_source = (
            db.session.query(
                LearnLessonFeedback.id.label("id"),
                LearnLessonFeedback.score.label("score"),
                LearnLessonFeedback.user_bid.label("user_bid"),
                rated_at_expression.label("rated_at"),
            )
            .filter(*base_filters)
            .subquery()
        )
        if include_summary:
            summary_row = db.session.query(
                db.func.avg(summary_source.c.score).label("average_score"),
                db.func.count(summary_source.c.id).label("rating_count"),
                db.func.count(
                    db.func.distinct(db.func.nullif(summary_source.c.user_bid, ""))
                ).label("user_count"),
                db.func.max(summary_source.c.rated_at).label("latest_rated_at"),
            ).one()
            total = int(getattr(summary_row, "rating_count", 0) or 0)
        else:
            summary_row = None
            total = int(
                db.session.query(db.func.count(summary_source.c.id)).scalar() or 0
            )

        if total == 0:
            return AdminOperationCourseRatingListDTO(
                summary=AdminOperationCourseRatingSummaryDTO(),
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        start = (safe_page_index - 1) * safe_page_size
        page_query = db.session.query(
            LearnLessonFeedback.id.label("id"),
            LearnLessonFeedback.lesson_feedback_bid.label("lesson_feedback_bid"),
            LearnLessonFeedback.progress_record_bid.label("progress_record_bid"),
            LearnLessonFeedback.user_bid.label("user_bid"),
            LearnLessonFeedback.outline_item_bid.label("outline_item_bid"),
            LearnLessonFeedback.score.label("score"),
            LearnLessonFeedback.comment.label("comment"),
            LearnLessonFeedback.mode.label("mode"),
            rated_at_expression.label("rated_at"),
        ).filter(*base_filters)
        ordered_query = page_query.order_by(
            rated_at_expression.desc(),
            LearnLessonFeedback.id.desc(),
        )
        if sort_by == "score_asc":
            ordered_query = page_query.order_by(
                LearnLessonFeedback.score.asc(),
                rated_at_expression.desc(),
                LearnLessonFeedback.id.desc(),
            )
        page_rows = ordered_query.offset(start).limit(safe_page_size).all()
        user_map = _load_user_map(
            sorted(
                {
                    str(getattr(row, "user_bid", "") or "").strip()
                    for row in page_rows
                    if str(getattr(row, "user_bid", "") or "").strip()
                }
            )
        )

        items: list[AdminOperationCourseRatingItemDTO] = []
        for row in page_rows:
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
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
            items.append(
                AdminOperationCourseRatingItemDTO(
                    lesson_feedback_bid=str(
                        getattr(row, "lesson_feedback_bid", "") or ""
                    ),
                    progress_record_bid=str(
                        getattr(row, "progress_record_bid", "") or ""
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
                    score=int(getattr(row, "score", 0) or 0),
                    comment=str(getattr(row, "comment", "") or ""),
                    mode=_resolve_course_rating_mode(
                        str(getattr(row, "mode", "") or "")
                    ),
                    rated_at=_format_operator_datetime(getattr(row, "rated_at", None)),
                )
            )

        if include_summary:
            summary = AdminOperationCourseRatingSummaryDTO(
                average_score=_format_average_score(
                    getattr(summary_row, "average_score", None)
                ),
                rating_count=total,
                user_count=int(getattr(summary_row, "user_count", 0) or 0),
                latest_rated_at=_format_operator_datetime(
                    getattr(summary_row, "latest_rated_at", None)
                ),
            )
        else:
            summary = AdminOperationCourseRatingSummaryDTO()
        return AdminOperationCourseRatingListDTO(
            summary=summary,
            items=items,
            page=safe_page_index,
            page_size=safe_page_size,
            total=total,
            page_count=math.ceil(total / safe_page_size) if safe_page_size else 0,
        )


def get_operator_course_follow_up_detail(
    app: Flask,
    *,
    shifu_bid: str,
    generated_block_bid: str,
) -> AdminOperationCourseFollowUpDetailDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_generated_block_bid = str(generated_block_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")
        if not normalized_generated_block_bid:
            raise_param_error("generated_block_bid is required")

        detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        course = detail_source["course"]
        outline_context_map = _build_course_outline_context_map(outline_items)
        ask_block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.shifu_bid == normalized_shifu_bid,
                LearnGeneratedBlock.generated_block_bid
                == normalized_generated_block_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                LearnGeneratedBlock.role == ROLE_STUDENT,
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        if ask_block is None:
            raise_param_error("generated_block_bid")

        progress_record_bid = str(ask_block.progress_record_bid or "").strip()
        groups = _load_follow_up_groups_for_progress_record(progress_record_bid)
        selected_group_index = next(
            (
                index
                for index, group in enumerate(groups)
                if str(group["ask_block"].generated_block_bid or "").strip()
                == normalized_generated_block_bid
            ),
            -1,
        )
        if selected_group_index < 0:
            raise_param_error("generated_block_bid")

        selected_group = groups[selected_group_index]
        user_map = _load_user_map([str(ask_block.user_bid or "").strip()])
        user = user_map.get(str(ask_block.user_bid or "").strip(), {})
        context = outline_context_map.get(
            str(ask_block.outline_item_bid or "").strip(),
            {
                "chapter_title": "",
                "lesson_title": "",
            },
        )

        timeline: list[AdminOperationCourseFollowUpTimelineItemDTO] = []
        for index, group in enumerate(groups):
            current_ask_block = group["ask_block"]
            is_current = index == selected_group_index
            timeline.append(
                AdminOperationCourseFollowUpTimelineItemDTO(
                    role="student",
                    content=str(
                        getattr(current_ask_block, "generated_content", "") or ""
                    ),
                    created_at=_format_operator_datetime(
                        getattr(current_ask_block, "created_at", None)
                    ),
                    is_current=is_current,
                )
            )
            answer_block = group.get("answer_block")
            answer_content = _resolve_follow_up_answer_content(answer_block)
            if answer_content:
                timeline.append(
                    AdminOperationCourseFollowUpTimelineItemDTO(
                        role="teacher",
                        content=answer_content,
                        created_at=_format_operator_datetime(
                            getattr(answer_block, "created_at", None)
                        ),
                        is_current=is_current,
                    )
                )

        selected_answer_block = selected_group.get("answer_block")
        source_info = _resolve_follow_up_source(
            ask_block=ask_block,
            answer_block=selected_answer_block,
        )
        return AdminOperationCourseFollowUpDetailDTO(
            basic_info=AdminOperationCourseFollowUpDetailBasicInfoDTO(
                generated_block_bid=normalized_generated_block_bid,
                progress_record_bid=progress_record_bid,
                user_bid=str(ask_block.user_bid or ""),
                mobile=str(user.get("mobile", "") or ""),
                email=str(user.get("email", "") or ""),
                nickname=str(user.get("nickname", "") or ""),
                course_name=str(getattr(course, "title", "") or ""),
                shifu_bid=normalized_shifu_bid,
                chapter_title=str(context.get("chapter_title", "") or ""),
                lesson_title=str(context.get("lesson_title", "") or ""),
                created_at=_format_operator_datetime(
                    getattr(ask_block, "created_at", None)
                ),
                turn_index=selected_group_index + 1,
            ),
            current_record=AdminOperationCourseFollowUpCurrentRecordDTO(
                follow_up_content=str(
                    getattr(ask_block, "generated_content", "") or ""
                ),
                answer_content=_resolve_follow_up_answer_content(selected_answer_block),
                source_output_content=str(
                    source_info.get("source_output_content", "") or ""
                ),
                source_output_type=str(source_info.get("source_output_type", "") or ""),
                source_position=int(source_info.get("source_position", 0) or 0),
                source_element_bid=str(source_info.get("source_element_bid", "") or ""),
                source_element_type=str(
                    source_info.get("source_element_type", "") or ""
                ),
            ),
            timeline=timeline,
        )


def get_operator_course_chapter_detail(
    app: Flask,
    *,
    shifu_bid: str,
    outline_item_bid: str,
) -> AdminOperationCourseChapterDetailDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")
        if not normalized_outline_item_bid:
            raise_param_error("outline_item_bid is required")

        detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        course = detail_source["course"]
        outline_item_map = {
            str(item.outline_item_bid or "").strip(): item
            for item in outline_items
            if str(item.outline_item_bid or "").strip()
        }
        outline_item = outline_item_map.get(normalized_outline_item_bid)
        if outline_item is None:
            raise_error("server.shifu.outlineItemNotFound")

        llm_system_prompt, llm_system_prompt_source = _resolve_prompt_with_fallback(
            outline_item=outline_item,
            outline_item_map=outline_item_map,
            course=course,
            field_name="llm_system_prompt",
        )
        return AdminOperationCourseChapterDetailDTO(
            outline_item_bid=normalized_outline_item_bid,
            title=outline_item.title or "",
            content=getattr(outline_item, "content", "") or "",
            llm_system_prompt=llm_system_prompt,
            llm_system_prompt_source=llm_system_prompt_source,
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


def _build_latest_billing_order_subquery(*, creator_bid: str):
    normalized_creator_bid = str(creator_bid or "").strip()
    return (
        db.session.query(
            BillingOrder.bill_order_bid.label("bill_order_bid"),
            db.func.max(BillingOrder.id).label("max_id"),
        )
        .filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == normalized_creator_bid,
        )
        .group_by(BillingOrder.bill_order_bid)
        .subquery()
    )


def _find_operator_course_bids_by_name(course_name: str) -> Set[str]:
    normalized_course_name = str(course_name or "").strip().lower()
    if not normalized_course_name:
        return set()

    def _load_matching_bids(model) -> Set[str]:
        latest_subquery = (
            db.session.query(db.func.max(model.id).label("max_id"))
            .filter(model.deleted == 0)
            .group_by(model.shifu_bid)
            .subquery()
        )
        rows = (
            db.session.query(model.shifu_bid)
            .join(latest_subquery, latest_subquery.c.max_id == model.id)
            .filter(model.title.ilike(f"%{normalized_course_name}%"))
            .all()
        )
        return {
            str(shifu_bid or "").strip()
            for (shifu_bid,) in rows
            if str(shifu_bid or "").strip()
        }

    matching_bids: Set[str] = set()
    matching_bids.update(_load_matching_bids(DraftShifu))
    matching_bids.update(_load_matching_bids(PublishedShifu))
    return matching_bids


def _build_operator_course_query_filter(
    shifu_bid_column: Any,
    course_query: str,
) -> Any | None:
    normalized_course_query = str(course_query or "").strip()
    if not normalized_course_query:
        return None

    course_filters = [shifu_bid_column == normalized_course_query]
    matching_course_bids = _find_operator_course_bids_by_name(normalized_course_query)
    if matching_course_bids:
        course_filters.append(shifu_bid_column.in_(sorted(matching_course_bids)))
    return or_(*course_filters)


def _build_operator_course_overview(app: Flask) -> AdminOperationCourseOverviewDTO:
    if not _can_use_operator_course_sql_optimization(app):
        return _build_operator_course_overview_legacy(app)

    candidate_query = _build_operator_course_candidate_query(
        shifu_bid="",
        course_name="",
        creator_bids=None,
        start_time=None,
        end_time=None,
    )
    if candidate_query is None:
        return AdminOperationCourseOverviewDTO()
    candidate_subquery = candidate_query.subquery("operator_course_overview_candidates")
    now = datetime.now()
    created_window_start, created_window_end = _resolve_created_last_7d_window(now)
    recent_activity_window_start = now - timedelta(days=30)
    aggregate_row = db.session.query(
        db.func.count(candidate_subquery.c.shifu_bid).label("total_course_count"),
        db.func.sum(
            case(
                (candidate_subquery.c.course_status == COURSE_STATUS_UNPUBLISHED, 1),
                else_=0,
            )
        ).label("draft_course_count"),
        db.func.sum(
            case(
                (candidate_subquery.c.course_status == COURSE_STATUS_PUBLISHED, 1),
                else_=0,
            )
        ).label("published_course_count"),
        db.func.sum(
            case(
                (
                    and_(
                        candidate_subquery.c.created_at >= created_window_start,
                        candidate_subquery.c.created_at <= created_window_end,
                    ),
                    1,
                ),
                else_=0,
            )
        ).label("created_last_7d_course_count"),
    ).one()
    total_course_count = int(aggregate_row.total_course_count or 0)
    if total_course_count == 0:
        return AdminOperationCourseOverviewDTO()
    learning_active_30d_course_count = (
        db.session.query(db.func.count(db.distinct(candidate_subquery.c.shifu_bid)))
        .select_from(candidate_subquery)
        .join(
            LearnProgressRecord,
            and_(
                LearnProgressRecord.shifu_bid == candidate_subquery.c.shifu_bid,
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
                LearnProgressRecord.created_at >= recent_activity_window_start,
            ),
        )
        .scalar()
        or 0
    )
    paid_order_30d_course_count = (
        db.session.query(db.func.count(db.distinct(candidate_subquery.c.shifu_bid)))
        .select_from(candidate_subquery)
        .join(
            Order,
            and_(
                Order.shifu_bid == candidate_subquery.c.shifu_bid,
                Order.deleted == 0,
                Order.status == ORDER_STATUS_SUCCESS,
                Order.created_at >= recent_activity_window_start,
            ),
        )
        .scalar()
        or 0
    )

    return AdminOperationCourseOverviewDTO(
        total_course_count=total_course_count,
        draft_course_count=int(aggregate_row.draft_course_count or 0),
        published_course_count=int(aggregate_row.published_course_count or 0),
        created_last_7d_course_count=int(
            aggregate_row.created_last_7d_course_count or 0
        ),
        learning_active_30d_course_count=int(learning_active_30d_course_count or 0),
        paid_order_30d_course_count=int(paid_order_30d_course_count or 0),
    )


def get_operator_course_overview(app: Flask) -> AdminOperationCourseOverviewDTO:
    with app.app_context():
        return _build_operator_course_overview(app)


def _can_use_operator_course_sql_optimization(app: Flask) -> bool:
    try:
        return current_app._get_current_object() is app and db.engine is not None
    except (RuntimeError, KeyError):
        return False


def _build_operator_course_overview_legacy(
    app: Flask,
) -> AdminOperationCourseOverviewDTO:
    draft_rows = _load_latest_shifus(
        DraftShifu,
        shifu_bid="",
        course_name="",
        creator_bids=None,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
    )
    published_rows = _load_latest_shifus(
        PublishedShifu,
        shifu_bid="",
        course_name="",
        creator_bids=None,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
    )
    merged_courses, published_bids, _ = _merge_courses(draft_rows, published_rows)
    total_course_count = len(merged_courses)
    if total_course_count == 0:
        return AdminOperationCourseOverviewDTO()

    now = datetime.now()
    created_window_start, created_window_end = _resolve_created_last_7d_window(now)
    recent_activity_window_start = now - timedelta(days=30)
    visible_shifu_bids = [
        str(course.shifu_bid or "").strip()
        for course in merged_courses
        if str(course.shifu_bid or "").strip()
    ]
    learning_active_30d_course_count = len(
        _load_recent_learning_active_course_bids(
            since=recent_activity_window_start,
            shifu_bids=visible_shifu_bids,
        )
    )
    paid_order_30d_course_count = len(
        _load_recent_paid_order_course_bids(
            since=recent_activity_window_start,
            shifu_bids=visible_shifu_bids,
        )
    )

    return AdminOperationCourseOverviewDTO(
        total_course_count=total_course_count,
        draft_course_count=sum(
            1
            for course in merged_courses
            if _resolve_course_status(course.shifu_bid or "", published_bids)
            == COURSE_STATUS_UNPUBLISHED
        ),
        published_course_count=sum(
            1
            for course in merged_courses
            if _resolve_course_status(course.shifu_bid or "", published_bids)
            == COURSE_STATUS_PUBLISHED
        ),
        created_last_7d_course_count=sum(
            1
            for course in merged_courses
            if course.created_at
            and created_window_start <= course.created_at <= created_window_end
        ),
        learning_active_30d_course_count=learning_active_30d_course_count,
        paid_order_30d_course_count=paid_order_30d_course_count,
    )


def _list_operator_courses_legacy(
    app: Flask,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> AdminOperationCourseListDTO:
    safe_page_index = max(int(page_index or 1), 1)
    safe_page_size = max(int(page_size or 20), 1)
    filters = filters or {}

    shifu_bid = str(filters.get("shifu_bid", "") or "").strip()
    course_name = str(filters.get("course_name", "") or "").strip()
    course_status = str(filters.get("course_status", "") or "").strip().lower()
    quick_filter = _resolve_course_quick_filter(filters.get("quick_filter", ""))
    creator_keyword = str(filters.get("creator_keyword", "") or "").strip()
    start_time = filters.get("start_time")
    end_time = filters.get("end_time")
    updated_start_time = filters.get("updated_start_time")
    updated_end_time = filters.get("updated_end_time")

    creator_bids = _find_matching_creator_bids(creator_keyword)
    draft_rows = _load_latest_shifu_seeds(
        DraftShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=None,
        updated_end_time=None,
    )
    published_rows = _load_latest_shifu_seeds(
        PublishedShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=None,
        updated_end_time=None,
    )

    merged_courses, published_bids, selected_sources = _merge_courses(
        draft_rows, published_rows
    )
    activity_map = _load_course_activity_map(draft_rows, published_rows)

    def resolve_activity(course) -> Dict[str, Any]:
        return activity_map.get(str(course.shifu_bid or "").strip(), {})

    def resolve_updated_at(course) -> Optional[datetime]:
        activity = resolve_activity(course)
        return activity.get("updated_at") or course.updated_at

    if course_status in {COURSE_STATUS_PUBLISHED, COURSE_STATUS_UNPUBLISHED}:
        merged_courses = [
            course
            for course in merged_courses
            if _resolve_course_status(course.shifu_bid or "", published_bids)
            == course_status
        ]
    if updated_start_time:
        merged_courses = [
            course
            for course in merged_courses
            if (resolve_updated_at(course) or datetime.min) >= updated_start_time
        ]
    if updated_end_time:
        merged_courses = [
            course
            for course in merged_courses
            if (resolve_updated_at(course) or datetime.min) <= updated_end_time
        ]
    if quick_filter:
        if quick_filter == COURSE_QUICK_FILTER_DRAFT:
            merged_courses = [
                course
                for course in merged_courses
                if _resolve_course_status(course.shifu_bid or "", published_bids)
                == COURSE_STATUS_UNPUBLISHED
            ]
        elif quick_filter == COURSE_QUICK_FILTER_PUBLISHED:
            merged_courses = [
                course
                for course in merged_courses
                if _resolve_course_status(course.shifu_bid or "", published_bids)
                == COURSE_STATUS_PUBLISHED
            ]
        elif quick_filter == COURSE_QUICK_FILTER_CREATED_LAST_7D:
            created_window_start, created_window_end = _resolve_created_last_7d_window()
            merged_courses = [
                course
                for course in merged_courses
                if course.created_at
                and created_window_start <= course.created_at <= created_window_end
            ]
        else:
            visible_shifu_bids = [
                str(course.shifu_bid or "").strip()
                for course in merged_courses
                if str(course.shifu_bid or "").strip()
            ]
            if quick_filter == COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D:
                matched_shifu_bids = _load_recent_learning_active_course_bids(
                    since=datetime.now() - timedelta(days=30),
                    shifu_bids=visible_shifu_bids,
                )
            else:
                matched_shifu_bids = _load_recent_paid_order_course_bids(
                    since=datetime.now() - timedelta(days=30),
                    shifu_bids=visible_shifu_bids,
                )
            merged_courses = [
                course
                for course in merged_courses
                if str(course.shifu_bid or "").strip() in matched_shifu_bids
            ]
    merged_courses = sorted(
        merged_courses,
        key=lambda item: (
            resolve_updated_at(item) or datetime.min,
            item.created_at or datetime.min,
            item.shifu_bid or "",
        ),
        reverse=True,
    )
    total = len(merged_courses)
    page_offset = (safe_page_index - 1) * safe_page_size
    page_items = merged_courses[page_offset : page_offset + safe_page_size]
    draft_page_items = [
        course
        for course in page_items
        if selected_sources.get(str(course.shifu_bid or "").strip()) == "draft"
    ]
    published_page_items = [
        course
        for course in page_items
        if selected_sources.get(str(course.shifu_bid or "").strip()) == "published"
    ]
    _attach_course_prompt_flags(DraftShifu, draft_page_items)
    _attach_course_prompt_flags(PublishedShifu, published_page_items)

    user_bids = {
        user_bid
        for course in page_items
        for user_bid in [
            course.created_user_bid,
            resolve_activity(course).get("updated_user_bid") or course.updated_user_bid,
        ]
        if user_bid and user_bid != "system"
    }
    user_map = _load_user_map(list(user_bids))
    items = [
        _build_course_summary(
            course,
            user_map,
            _resolve_course_status(course.shifu_bid or "", published_bids),
            resolve_activity(course),
        )
        for course in page_items
    ]
    return AdminOperationCourseListDTO(
        items=items,
        page=safe_page_index,
        page_size=safe_page_size,
        total=total,
        page_count=((total + safe_page_size - 1) // safe_page_size) if total else 0,
    )


def list_operator_courses(
    app: Flask,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> AdminOperationCourseListDTO:
    with app.app_context():
        if not _can_use_operator_course_sql_optimization(app):
            return _list_operator_courses_legacy(app, page_index, page_size, filters)

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = max(int(page_size or 20), 1)
        filters = filters or {}

        shifu_bid = str(filters.get("shifu_bid", "") or "").strip()
        course_name = str(filters.get("course_name", "") or "").strip()
        course_status = str(filters.get("course_status", "") or "").strip().lower()
        quick_filter = _resolve_course_quick_filter(filters.get("quick_filter", ""))
        creator_keyword = str(filters.get("creator_keyword", "") or "").strip()
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        updated_start_time = filters.get("updated_start_time")
        updated_end_time = filters.get("updated_end_time")

        creator_bids = _find_matching_creator_bids(creator_keyword)
        candidate_query = _build_operator_course_candidate_query(
            shifu_bid=shifu_bid,
            course_name=course_name,
            creator_bids=creator_bids,
            start_time=start_time,
            end_time=end_time,
            include_activity=True,
        )
        if candidate_query is None:
            return AdminOperationCourseListDTO(
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )
        candidate_subquery = candidate_query.subquery("operator_course_candidates")
        query = db.session.query(candidate_subquery)

        if course_status in {COURSE_STATUS_PUBLISHED, COURSE_STATUS_UNPUBLISHED}:
            query = query.filter(candidate_subquery.c.course_status == course_status)
        if quick_filter:
            if quick_filter == COURSE_QUICK_FILTER_DRAFT:
                query = query.filter(
                    candidate_subquery.c.course_status == COURSE_STATUS_UNPUBLISHED
                )
            elif quick_filter == COURSE_QUICK_FILTER_PUBLISHED:
                query = query.filter(
                    candidate_subquery.c.course_status == COURSE_STATUS_PUBLISHED
                )
            elif quick_filter == COURSE_QUICK_FILTER_CREATED_LAST_7D:
                created_window_start, created_window_end = (
                    _resolve_created_last_7d_window()
                )
                query = query.filter(
                    candidate_subquery.c.created_at >= created_window_start,
                    candidate_subquery.c.created_at <= created_window_end,
                )
            else:
                if quick_filter == COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D:
                    active_course_query = db.session.query(
                        LearnProgressRecord.shifu_bid
                    ).filter(
                        LearnProgressRecord.deleted == 0,
                        LearnProgressRecord.status != LEARN_STATUS_RESET,
                        LearnProgressRecord.created_at
                        >= datetime.now() - timedelta(days=30),
                    )
                    query = query.filter(
                        candidate_subquery.c.shifu_bid.in_(active_course_query)
                    )
                else:
                    paid_course_query = db.session.query(Order.shifu_bid).filter(
                        Order.deleted == 0,
                        Order.status == ORDER_STATUS_SUCCESS,
                        Order.created_at >= datetime.now() - timedelta(days=30),
                    )
                    query = query.filter(
                        candidate_subquery.c.shifu_bid.in_(paid_course_query)
                    )

        if updated_start_time:
            query = query.filter(
                candidate_subquery.c.activity_updated_at >= updated_start_time
            )
        if updated_end_time:
            query = query.filter(
                or_(
                    candidate_subquery.c.activity_updated_at.is_(None),
                    candidate_subquery.c.activity_updated_at <= updated_end_time,
                )
            )

        total = int(query.count() or 0)
        page_offset = (safe_page_index - 1) * safe_page_size
        page_rows = (
            query.order_by(
                candidate_subquery.c.activity_updated_at.desc(),
                candidate_subquery.c.created_at.desc(),
                candidate_subquery.c.shifu_bid.desc(),
            )
            .offset(page_offset)
            .limit(safe_page_size)
            .all()
        )
        page_items = [_build_operator_course_list_candidate(row) for row in page_rows]

        draft_page_items = [
            course for course in page_items if course.selected_source == "draft"
        ]
        published_page_items = [
            course for course in page_items if course.selected_source == "published"
        ]
        _attach_course_prompt_flags(DraftShifu, draft_page_items)
        _attach_course_prompt_flags(PublishedShifu, published_page_items)

        def resolve_activity(course) -> Dict[str, Any]:
            return {
                "updated_at": course.activity_updated_at or course.updated_at,
                "updated_user_bid": course.activity_updated_user_bid
                or course.updated_user_bid,
            }

        user_bids = {
            user_bid
            for course in page_items
            for user_bid in [
                course.created_user_bid,
                resolve_activity(course).get("updated_user_bid")
                or course.activity_updated_user_bid
                or course.updated_user_bid,
            ]
            if user_bid and user_bid != "system"
        }
        user_map = _load_user_map(list(user_bids))
        items = [
            _build_course_summary(
                course,
                user_map,
                course.course_status,
                resolve_activity(course),
            )
            for course in page_items
        ]
        return AdminOperationCourseListDTO(
            items=items,
            page=safe_page_index,
            page_size=safe_page_size,
            total=total,
            page_count=((total + safe_page_size - 1) // safe_page_size) if total else 0,
        )
