from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional, Sequence, Set

from flask import Flask, current_app
from sqlalchemy import and_, case, or_
from sqlalchemy.orm import defer

from flaskr.common.cache_provider import cache as redis
from flaskr.common.config import get_config
from flaskr.common.umami_client import get_course_visit_count_30d
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
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.billing.primitives import (
    quantize_credit_amount as _quantize_credit_amount,
)
from flaskr.service.billing.queries import (
    add_months as _add_months,
    add_years as _add_years,
    load_primary_active_subscription,
)
from flaskr.service.billing.wallets import grant_manual_credit_wallet_balance
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
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
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos import (
    AdminOperationCourseChapterDetailDTO,
    AdminOperationCourseDetailBasicInfoDTO,
    AdminOperationCourseDetailChapterDTO,
    AdminOperationCourseDetailDTO,
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
    AdminOperationCourseUserDTO,
    AdminOperationUserCreditGrantResultDTO,
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationCourseSummaryDTO,
    AdminOperationUserCreditLedgerItemDTO,
    AdminOperationUserCreditLedgerPageDTO,
    AdminOperationUserCreditSummaryDTO,
    AdminOperationUserCourseSummaryDTO,
    AdminOperationUserSummaryDTO,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.demo_courses import is_builtin_demo_course
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
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
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    load_user_aggregate_by_identifier,
    mark_user_roles,
    set_user_state,
    upsert_credential,
)
from flaskr.util.timezone import serialize_with_app_timezone
from flaskr.util.uuid import generate_id
from flaskr.service.user.utils import (
    ensure_demo_course_permissions,
    load_existing_demo_shifu_ids,
)

COURSE_STATUS_PUBLISHED = "published"
COURSE_STATUS_UNPUBLISHED = "unpublished"
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
OPERATOR_USER_REGISTRATION_SOURCE_PHONE = "phone"
OPERATOR_USER_REGISTRATION_SOURCE_EMAIL = "email"
OPERATOR_USER_REGISTRATION_SOURCE_GOOGLE = "google"
OPERATOR_USER_REGISTRATION_SOURCE_WECHAT = "wechat"
OPERATOR_USER_REGISTRATION_SOURCE_IMPORTED = "imported"
OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN = "unknown"
COURSE_FOLLOW_UP_LIST_MAX_PAGE_SIZE = 100
COURSE_RATING_LIST_MAX_PAGE_SIZE = 100
OPERATOR_USER_CREDIT_GRANT_SOURCE_REWARD = "reward"
OPERATOR_USER_CREDIT_GRANT_SOURCE_COMPENSATION = "compensation"
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
OPERATOR_USER_CREDIT_VALIDITY_PRESETS = {
    OPERATOR_USER_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_VALIDITY_1D,
    OPERATOR_USER_CREDIT_VALIDITY_7D,
    OPERATOR_USER_CREDIT_VALIDITY_1M,
    OPERATOR_USER_CREDIT_VALIDITY_3M,
    OPERATOR_USER_CREDIT_VALIDITY_1Y,
}

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


def _format_operator_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""
    serialized_value = serialize_with_app_timezone(
        current_app._get_current_object(),
        value,
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


def _normalize_metadata_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _normalize_credit_amount(value: Any) -> Decimal:
    normalized = str(value or "").strip()
    if not normalized:
        raise_param_error("amount")
    try:
        parsed = _quantize_credit_amount(Decimal(normalized))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        raise_param_error("amount")
    if not parsed.is_finite() or parsed <= Decimal("0"):
        raise_param_error("amount")
    return parsed


def _resolve_operator_credit_grant_expiry(
    *,
    creator_bid: str,
    validity_preset: str,
    granted_at: datetime,
) -> datetime | None:
    normalized_preset = str(validity_preset or "").strip()
    if normalized_preset == OPERATOR_USER_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION:
        subscription = load_primary_active_subscription(
            creator_bid,
            as_of=granted_at,
        )
        if (
            subscription is None
            or subscription.current_period_end_at is None
            or subscription.current_period_end_at <= granted_at
        ):
            raise_error("server.billing.subscriptionInactive")
        return subscription.current_period_end_at
    if normalized_preset == OPERATOR_USER_CREDIT_VALIDITY_1D:
        return granted_at + timedelta(days=1)
    if normalized_preset == OPERATOR_USER_CREDIT_VALIDITY_7D:
        return granted_at + timedelta(days=7)
    if normalized_preset == OPERATOR_USER_CREDIT_VALIDITY_1M:
        return _add_months(granted_at, 1)
    if normalized_preset == OPERATOR_USER_CREDIT_VALIDITY_3M:
        return _add_months(granted_at, 3)
    if normalized_preset == OPERATOR_USER_CREDIT_VALIDITY_1Y:
        return _add_years(granted_at, 1)
    raise_param_error("validity_preset")


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


def _resolve_operator_credit_usage_scene(metadata: Dict[str, Any]) -> int:
    raw_usage_scene = metadata.get("usage_scene")
    try:
        return int(raw_usage_scene or 0)
    except (TypeError, ValueError):
        return 0


def _resolve_operator_credit_display_entry_type(
    row: CreditLedgerEntry,
    *,
    metadata: Dict[str, Any],
) -> str:
    usage_scene = _resolve_operator_credit_usage_scene(metadata)
    amount = Decimal(row.amount or 0)

    if int(row.entry_type or 0) == CREDIT_LEDGER_ENTRY_TYPE_GRANT:
        if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
            checkout_type = str(metadata.get("checkout_type") or "").strip().lower()
            if checkout_type == "trial_bootstrap":
                return "trial_subscription_grant"
            return "subscription_grant"
        if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_TOPUP:
            return "topup_grant"
        if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_GIFT:
            return "gift_grant"
        if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_MANUAL:
            grant_type = str(metadata.get("grant_type") or "").strip().lower()
            if grant_type == "manual_grant":
                return "manual_grant"
            return "manual_credit" if amount >= 0 else "manual_debit"
        return "grant"

    if int(row.entry_type or 0) == CREDIT_LEDGER_ENTRY_TYPE_CONSUME:
        if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_USAGE:
            if usage_scene == BILL_USAGE_SCENE_PREVIEW:
                return "preview_consume"
            if usage_scene == BILL_USAGE_SCENE_DEBUG:
                return "debug_consume"
            if usage_scene == BILL_USAGE_SCENE_PROD:
                return "learning_consume"
        return "consume"

    if int(row.entry_type or 0) == CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT:
        if amount > 0:
            return "manual_credit"
        if amount < 0:
            return "manual_debit"
        return "adjustment"

    if int(row.entry_type or 0) == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE:
        if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
            return "subscription_expire"
        if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_TOPUP:
            return "topup_expire"
        if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_GIFT:
            return "gift_expire"
        return "expire"

    if int(row.entry_type or 0) == CREDIT_LEDGER_ENTRY_TYPE_REFUND:
        return "refund_return"

    return CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant")


def _resolve_operator_credit_display_source_type(
    row: CreditLedgerEntry,
    *,
    metadata: Dict[str, Any],
) -> str:
    if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_USAGE:
        usage_scene = _resolve_operator_credit_usage_scene(metadata)
        if usage_scene == BILL_USAGE_SCENE_PREVIEW:
            return "preview"
        if usage_scene == BILL_USAGE_SCENE_DEBUG:
            return "debug"
        if usage_scene == BILL_USAGE_SCENE_PROD:
            return "learning"
        return "usage"

    if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
        checkout_type = str(metadata.get("checkout_type") or "").strip().lower()
        if checkout_type == "trial_bootstrap":
            return "trial_subscription"
        return "subscription"
    if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_TOPUP:
        return "topup"
    if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_GIFT:
        return "gift"
    if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_REFUND:
        return "refund"
    if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_MANUAL:
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
            int(bucket.source_type or 0) != CREDIT_SOURCE_TYPE_MANUAL
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
    if normalized in {"phone", "email", "google", "wechat"}:
        return normalized
    return "unknown"


def _normalize_registration_source(provider_name: str) -> str:
    normalized = str(provider_name or "").strip().lower()
    if normalized in {"phone", "email", "google", "wechat"}:
        return normalized
    if normalized in {"manual", "import", "imported"}:
        return OPERATOR_USER_REGISTRATION_SOURCE_IMPORTED
    return OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN


def _load_operator_user_registration_source_map(
    user_bids: Sequence[str],
) -> Dict[str, str]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}

    credential_rows = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(normalized_user_bids),
            AuthCredential.deleted == 0,
        )
        .order_by(AuthCredential.created_at.asc(), AuthCredential.id.asc())
        .all()
    )
    registration_source_map: Dict[str, str] = {}
    for credential in credential_rows:
        user_bid = str(credential.user_bid or "").strip()
        if not user_bid or user_bid in registration_source_map:
            continue
        registration_source_map[user_bid] = _normalize_registration_source(
            credential.provider_name or ""
        )

    if len(registration_source_map) == len(normalized_user_bids):
        return registration_source_map

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
) -> Dict[str, Dict[str, Any]]:
    if not user_bids:
        return {}

    credential_rows = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(list(user_bids)),
            AuthCredential.deleted == 0,
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    contact_map: Dict[str, Dict[str, Any]] = {
        user_bid: {"mobile": "", "email": "", "login_methods": []}
        for user_bid in user_bids
    }
    for credential in credential_rows:
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

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(list(user_bids)),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.asc())
        .all()
    )
    for user in users:
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

    credential_rows = (
        db.session.query(AuthCredential.user_bid)
        .filter(
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            AuthCredential.identifier.ilike(f"%{normalized}%"),
        )
        .all()
    )
    user_bids = {row[0] for row in credential_rows if row and row[0]}
    identify_rows = (
        db.session.query(UserEntity.user_bid)
        .filter(
            UserEntity.deleted == 0,
            or_(
                UserEntity.user_bid.ilike(f"%{normalized}%"),
                UserEntity.user_identify.ilike(f"%{normalized}%"),
            ),
        )
        .all()
    )
    for row in identify_rows:
        if row and row[0]:
            user_bids.add(row[0])
    return user_bids


def _build_operator_user_summary(
    user: UserEntity,
    contact_map: Dict[str, Dict[str, Any]],
    learning_courses_map: Dict[str, list[AdminOperationUserCourseSummaryDTO]],
    created_courses_map: Dict[str, list[AdminOperationUserCourseSummaryDTO]],
    learner_user_bids: Set[str],
    registration_source_map: Dict[str, str],
    last_login_map: Dict[str, datetime],
    total_paid_amount_map: Dict[str, Decimal],
    last_learning_map: Dict[str, datetime],
    credit_summary_map: Dict[str, Dict[str, Any]],
) -> AdminOperationUserSummaryDTO:
    user_bid = str(user.user_bid or "").strip()
    contact = contact_map.get(user.user_bid or "", {})
    is_learner = user_bid in learner_user_bids
    credit_summary = credit_summary_map.get(user_bid)
    has_credit_account = bool(user.is_creator) or credit_summary is not None
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
        learning_courses=list(learning_courses_map.get(user_bid, []) or []),
        created_courses=list(created_courses_map.get(user_bid, []) or []),
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
            _format_operator_datetime((credit_summary or {}).get("credits_expire_at"))
            if has_credit_account
            else ""
        ),
        has_active_subscription=bool(
            (credit_summary or {}).get("has_active_subscription", False)
        ),
        last_login_at=_format_operator_datetime(last_login_map.get(user_bid)),
        last_learning_at=_format_operator_datetime(last_learning_map.get(user_bid)),
        created_at=_format_operator_datetime(user.created_at),
        updated_at=_format_operator_datetime(user.updated_at),
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
            _format_operator_datetime((credit_summary or {}).get("credits_expire_at"))
            if has_credit_account
            else ""
        ),
        has_active_subscription=bool(
            (credit_summary or {}).get("has_active_subscription", False)
        ),
    )


def _build_operator_user_credit_ledger_item(
    row: CreditLedgerEntry,
    *,
    order_map: Optional[Dict[str, BillingOrder]] = None,
) -> AdminOperationUserCreditLedgerItemDTO:
    metadata = _normalize_metadata_json(row.metadata_json)
    normalized_source_bid = str(row.source_bid or "").strip()
    order = (order_map or {}).get(normalized_source_bid)
    order_metadata = _normalize_metadata_json(order.metadata_json if order else None)
    merged_metadata = {**order_metadata, **metadata}
    return AdminOperationUserCreditLedgerItemDTO(
        ledger_bid=str(row.ledger_bid or "").strip(),
        created_at=_format_operator_datetime(row.created_at),
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
        expires_at=_format_operator_datetime(row.expires_at),
        consumable_from=_format_operator_datetime(row.consumable_from),
        note=str(merged_metadata.get("note") or "").strip(),
        note_code=_resolve_operator_credit_note_code(
            row,
            metadata=merged_metadata,
        ),
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
    if is_mapped_model:
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

    rows = latest_rows.order_by(model.updated_at.desc(), model.id.desc()).all()
    if is_mapped_model:
        _attach_course_prompt_flags(model, rows)
    return rows


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


def _record_course_activity(
    activity_map: Dict[str, Dict[str, Any]],
    *,
    shifu_bid: str,
    updated_at: Optional[datetime],
    updated_user_bid: str,
    prefer_on_equal: bool = False,
) -> None:
    if not shifu_bid:
        return
    current = activity_map.get(shifu_bid)
    candidate_time = updated_at or datetime.min
    current_time = (
        current.get("updated_at")
        if current and current.get("updated_at")
        else datetime.min
    )
    should_replace = current is None or candidate_time > current_time
    if (
        not should_replace
        and prefer_on_equal
        and current is not None
        and candidate_time == current_time
    ):
        should_replace = True
    if should_replace:
        activity_map[shifu_bid] = {
            "updated_at": updated_at,
            "updated_user_bid": str(updated_user_bid or "").strip(),
        }


def _load_course_activity_map(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
) -> Dict[str, Dict[str, Any]]:
    activity_map: Dict[str, Dict[str, Any]] = {}
    shifu_bids: Set[str] = set()

    for course in list(drafts) + list(published):
        shifu_bid = str(course.shifu_bid or "").strip()
        if not shifu_bid:
            continue
        shifu_bids.add(shifu_bid)
        _record_course_activity(
            activity_map,
            shifu_bid=shifu_bid,
            updated_at=course.updated_at,
            updated_user_bid=course.updated_user_bid or "",
        )

    if not shifu_bids:
        return activity_map

    ordered_shifu_bids = sorted(shifu_bids)
    outline_models = [DraftOutlineItem, PublishedOutlineItem]
    for model in outline_models:
        latest_updated_subquery = (
            db.session.query(
                model.shifu_bid.label("shifu_bid"),
                db.func.max(model.updated_at).label("max_updated_at"),
            )
            .filter(
                model.deleted == 0,
                model.shifu_bid.in_(ordered_shifu_bids),
            )
            .group_by(model.shifu_bid)
            .subquery()
        )
        latest_id_subquery = (
            db.session.query(
                model.shifu_bid.label("shifu_bid"),
                db.func.max(model.id).label("max_id"),
            )
            .join(
                latest_updated_subquery,
                and_(
                    model.shifu_bid == latest_updated_subquery.c.shifu_bid,
                    or_(
                        model.updated_at == latest_updated_subquery.c.max_updated_at,
                        and_(
                            model.updated_at.is_(None),
                            latest_updated_subquery.c.max_updated_at.is_(None),
                        ),
                    ),
                ),
            )
            .filter(
                model.deleted == 0,
                model.shifu_bid.in_(ordered_shifu_bids),
            )
            .group_by(model.shifu_bid)
            .subquery()
        )
        rows = (
            db.session.query(
                model.shifu_bid,
                model.updated_at,
                model.updated_user_bid,
            )
            .join(latest_id_subquery, model.id == latest_id_subquery.c.max_id)
            .all()
        )
        for shifu_bid, updated_at, updated_user_bid in rows:
            normalized_shifu_bid = str(shifu_bid or "").strip()
            if not normalized_shifu_bid:
                continue
            _record_course_activity(
                activity_map,
                shifu_bid=normalized_shifu_bid,
                updated_at=updated_at,
                updated_user_bid=updated_user_bid or "",
                prefer_on_equal=True,
            )

    return activity_map


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


def _clear_shifu_permission_cache(app: Flask, user_id: str, shifu_bid: str) -> None:
    prefixes = {
        app.config.get("CACHE_KEY_PREFIX", "") or "",
        get_config("REDIS_KEY_PREFIX") or "",
    }
    for prefix in prefixes:
        cache_key = f"{prefix}shifu_permission:{user_id}:{shifu_bid}"
        redis.delete(cache_key)


def _clear_shifu_creator_cache(app: Flask, shifu_bid: str) -> None:
    prefixes = {
        app.config.get("REDIS_KEY_PREFIX", "") or "",
        get_config("REDIS_KEY_PREFIX") or "",
        "ai-shifu",
    }
    for prefix in prefixes:
        cache_key = f"{prefix}:shifu_creator:{shifu_bid}"
        redis.delete(cache_key)


def _update_course_creator_bid(shifu_bid: str, creator_user_bid: str) -> None:
    DraftShifu.query.filter(DraftShifu.shifu_bid == shifu_bid).update(
        {DraftShifu.created_user_bid: creator_user_bid},
        synchronize_session=False,
    )
    PublishedShifu.query.filter(PublishedShifu.shifu_bid == shifu_bid).update(
        {PublishedShifu.created_user_bid: creator_user_bid},
        synchronize_session=False,
    )


def transfer_operator_course_creator(
    app: Flask,
    *,
    shifu_bid: str,
    contact_type: str,
    identifier: str,
) -> Dict[str, Any]:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_contact_type = str(contact_type or "").strip().lower()
        normalized_identifier = _normalize_identifier(identifier)

        latest_course = _load_latest_course_for_transfer(normalized_shifu_bid)
        if not latest_course:
            raise_error("server.shifu.shifuNotFound")
        if not _is_operator_visible_course(latest_course):
            raise_error("server.shifu.transferCreatorDemoNotAllowed")

        previous_creator_user_bid = str(latest_course.created_user_bid or "").strip()

        existing_aggregate = load_user_aggregate_by_identifier(
            normalized_identifier,
            providers=[normalized_contact_type],
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
        if target_user_bid == previous_creator_user_bid:
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

        mark_user_roles(target_user_bid, is_creator=True)
        _update_course_creator_bid(normalized_shifu_bid, target_user_bid)

        db.session.commit()
        if previous_creator_user_bid:
            _clear_shifu_permission_cache(
                app, previous_creator_user_bid, normalized_shifu_bid
            )
        _clear_shifu_permission_cache(app, target_user_bid, normalized_shifu_bid)
        _clear_shifu_creator_cache(app, normalized_shifu_bid)
        return {
            "shifu_bid": normalized_shifu_bid,
            "previous_creator_user_bid": previous_creator_user_bid,
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
    for course in drafts:
        visible = _is_operator_visible_course(course)
        if visible:
            course_map[course.shifu_bid] = course
    for course in published:
        visible = _is_operator_visible_course(course)
        if visible:
            published_bids.add(course.shifu_bid)
        if visible and course.shifu_bid not in course_map:
            course_map[course.shifu_bid] = course
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
    return (
        db.session.query(model)
        .filter(model.id.in_(db.session.query(latest_subquery.c.max_id)))
        .all()
    )


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
    )
    merged_created_courses, created_published_bids = _merge_courses(
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
    learned_drafts = _load_latest_courses_by_shifu_bids(DraftShifu, learned_shifu_bids)
    learned_published = _load_latest_courses_by_shifu_bids(
        PublishedShifu, learned_shifu_bids
    )
    merged_learned_courses, learned_published_bids = _merge_courses(
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


def _find_matching_follow_up_user_bids(
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

    def _merge_rows(rows: Sequence[tuple[str, Optional[datetime]]]) -> None:
        for user_bid, joined_at in rows:
            normalized_user_bid = str(user_bid or "").strip()
            if not normalized_user_bid or not joined_at:
                continue
            current = joined_at_map.get(normalized_user_bid)
            if current is None or joined_at < current:
                joined_at_map[normalized_user_bid] = joined_at

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
    if normalized_creator_user_bid and course_created_at:
        current = joined_at_map.get(normalized_creator_user_bid)
        if current is None or course_created_at < current:
            joined_at_map[normalized_creator_user_bid] = course_created_at

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
        visit_count_30d = get_course_visit_count_30d(app, normalized_shifu_bid)
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


def get_operator_course_follow_ups(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
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
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        follow_up_base = _build_course_follow_up_base_subquery(normalized_shifu_bid)
        user_keyword_filter = _find_matching_follow_up_user_bids(
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

        filtered_follow_ups = filtered_query.subquery()
        summary_row = db.session.query(
            db.func.count(filtered_follow_ups.c.id).label("follow_up_count"),
            db.func.count(
                db.func.distinct(db.func.nullif(filtered_follow_ups.c.user_bid, ""))
            ).label("user_count"),
            db.func.count(
                db.func.distinct(
                    db.func.nullif(filtered_follow_ups.c.outline_item_bid, "")
                )
            ).label("lesson_count"),
            db.func.max(filtered_follow_ups.c.created_at).label("latest_follow_up_at"),
        ).one()

        total = int(getattr(summary_row, "follow_up_count", 0) or 0)
        if total == 0:
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

        start = (safe_page_index - 1) * safe_page_size
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
                    turn_index=int(getattr(row, "turn_index", 0) or 0),
                    created_at=_format_operator_datetime(created_at),
                )
            )
        summary = AdminOperationCourseFollowUpSummaryDTO(
            follow_up_count=total,
            user_count=int(getattr(summary_row, "user_count", 0) or 0),
            lesson_count=int(getattr(summary_row, "lesson_count", 0) or 0),
            latest_follow_up_at=_format_operator_datetime(
                getattr(summary_row, "latest_follow_up_at", None)
            ),
        )
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
        rating_rows = (
            LearnLessonFeedback.query.filter(
                LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
                LearnLessonFeedback.deleted == 0,
            )
            .order_by(
                LearnLessonFeedback.updated_at.desc(),
                LearnLessonFeedback.id.desc(),
            )
            .all()
        )
        user_bids = sorted(
            {
                str(getattr(row, "user_bid", "") or "").strip()
                for row in rating_rows
                if str(getattr(row, "user_bid", "") or "").strip()
            }
        )
        user_map = _load_user_map(user_bids)

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

        filtered_items: list[
            tuple[datetime, int, AdminOperationCourseRatingItemDTO]
        ] = []
        total_score = 0
        latest_rated_at: Optional[datetime] = None
        for row in rating_rows:
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
            score = int(getattr(row, "score", 0) or 0)
            comment = str(getattr(row, "comment", "") or "")
            mode = _resolve_course_rating_mode(str(getattr(row, "mode", "") or ""))
            rated_at = getattr(row, "updated_at", None) or getattr(
                row, "created_at", None
            )
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

            if keyword:
                haystack = [
                    str(user.get("mobile", "") or "").lower(),
                    str(user.get("email", "") or "").lower(),
                    str(user.get("nickname", "") or "").lower(),
                ]
                if not any(keyword in value for value in haystack if value):
                    continue

            if chapter_keyword:
                chapter_haystack = [
                    str(context.get("chapter_title", "") or "").lower(),
                    str(context.get("lesson_title", "") or "").lower(),
                ]
                if not any(
                    chapter_keyword in value for value in chapter_haystack if value
                ):
                    continue

            if normalized_score_filter is not None and score != normalized_score_filter:
                continue
            if mode_filter and mode != mode_filter:
                continue
            if has_comment_filter == "true" and not comment.strip():
                continue
            if start_time and (rated_at is None or rated_at < start_time):
                continue
            if end_time and (rated_at is None or rated_at > end_time):
                continue

            if rated_at is not None and (
                latest_rated_at is None or rated_at > latest_rated_at
            ):
                latest_rated_at = rated_at
            filtered_items.append(
                (
                    rated_at or datetime.min,
                    int(getattr(row, "id", 0) or 0),
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
                        score=score,
                        comment=comment,
                        mode=mode,
                        rated_at=_format_operator_datetime(rated_at),
                    ),
                )
            )
            total_score += score

        filtered_items.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if sort_by == "score_asc":
            filtered_items.sort(key=lambda item: item[2].score)

        rows = [item for _, _, item in filtered_items]
        total = len(rows)
        start = (safe_page_index - 1) * safe_page_size
        end = start + safe_page_size
        average_score = (
            _format_average_score(Decimal(total_score) / Decimal(total))
            if total
            else ""
        )
        summary = AdminOperationCourseRatingSummaryDTO(
            average_score=average_score,
            rating_count=total,
            user_count=len({item.user_bid for item in rows if item.user_bid}),
            latest_rated_at=_format_operator_datetime(latest_rated_at),
        )
        return AdminOperationCourseRatingListDTO(
            summary=summary,
            items=rows[start:end],
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


def list_operator_users(
    app: Flask,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> PageNationDTO:
    with app.app_context():
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            OPERATOR_USER_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        user_bid = str(filters.get("user_bid", "") or "").strip()
        identifier = str(
            filters.get("identifier", "") or filters.get("mobile", "") or ""
        ).strip()
        nickname = str(filters.get("nickname", "") or "").strip()
        user_status = str(filters.get("user_status", "") or "").strip().lower()
        user_role = str(filters.get("user_role", "") or "").strip().lower()
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")

        query = UserEntity.query.filter(UserEntity.deleted == 0)
        if user_bid:
            query = query.filter(UserEntity.user_bid == user_bid)
        if nickname:
            query = query.filter(UserEntity.nickname.ilike(f"%{nickname}%"))
        if user_status:
            if user_status == OPERATOR_USER_STATUS_UNREGISTERED:
                query = query.filter(UserEntity.state == USER_STATE_UNREGISTERED)
            elif user_status == OPERATOR_USER_STATUS_REGISTERED:
                query = query.filter(
                    UserEntity.state.in_([USER_STATE_REGISTERED, USER_STATE_TRAIL])
                )
            elif user_status == OPERATOR_USER_STATUS_TRIAL:
                query = query.filter(UserEntity.state == USER_STATE_TRAIL)
            elif user_status == OPERATOR_USER_STATUS_PAID:
                query = query.filter(UserEntity.state == USER_STATE_PAID)
            else:
                query = query.filter(db.text("1 = 0"))
        if user_role == OPERATOR_USER_ROLE_OPERATOR:
            query = query.filter(UserEntity.is_operator == 1)
        elif user_role == OPERATOR_USER_ROLE_CREATOR:
            query = query.filter(
                UserEntity.is_operator == 0,
                UserEntity.is_creator == 1,
            )
        elif user_role == OPERATOR_USER_ROLE_LEARNER:
            learner_subquery = _build_learner_user_bid_subquery()
            query = query.filter(
                UserEntity.is_operator == 0,
                UserEntity.is_creator == 0,
                UserEntity.user_bid.in_(db.session.query(learner_subquery.c.user_bid)),
            )
        elif user_role == OPERATOR_USER_ROLE_REGULAR:
            learner_subquery = _build_learner_user_bid_subquery()
            query = query.filter(
                UserEntity.is_operator == 0,
                UserEntity.is_creator == 0,
                ~UserEntity.user_bid.in_(db.session.query(learner_subquery.c.user_bid)),
            )
        if start_time:
            query = query.filter(UserEntity.created_at >= start_time)
        if end_time:
            query = query.filter(UserEntity.created_at <= end_time)
        if identifier:
            matching_user_bids = _find_matching_user_bids_by_identifier(identifier)
            if not matching_user_bids:
                return PageNationDTO(safe_page_index, safe_page_size, 0, [])
            query = query.filter(UserEntity.user_bid.in_(list(matching_user_bids)))

        total = query.count()
        page_offset = (safe_page_index - 1) * safe_page_size
        page_items = (
            query.order_by(UserEntity.created_at.desc(), UserEntity.id.desc())
            .offset(page_offset)
            .limit(safe_page_size)
            .all()
        )
        user_bids = [
            str(user.user_bid or "").strip() for user in page_items if user.user_bid
        ]
        contact_map = _load_operator_user_contact_map(user_bids)
        created_courses_map, learning_courses_map = _load_operator_user_course_maps(
            user_bids
        )
        learner_user_bids = _load_learner_user_bids(user_bids)
        registration_source_map = _load_operator_user_registration_source_map(user_bids)
        last_login_map = _load_operator_user_last_login_map(user_bids)
        total_paid_amount_map = _load_operator_user_total_paid_amount_map(user_bids)
        last_learning_map = _load_operator_user_last_learning_map(user_bids)
        credit_summary_map = _load_operator_user_credit_summary_map(user_bids)
        items = [
            _build_operator_user_summary(
                user,
                contact_map,
                learning_courses_map,
                created_courses_map,
                learner_user_bids,
                registration_source_map,
                last_login_map,
                total_paid_amount_map,
                last_learning_map,
                credit_summary_map,
            )
            for user in page_items
        ]
        return PageNationDTO(safe_page_index, safe_page_size, total, items)


def get_operator_user_detail(
    app: Flask,
    user_bid: str,
) -> AdminOperationUserSummaryDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        user = _load_operator_user_or_raise(normalized_user_bid)

        contact_map = _load_operator_user_contact_map([normalized_user_bid])
        created_courses_map, learning_courses_map = _load_operator_user_course_maps(
            [normalized_user_bid]
        )
        learner_user_bids = _load_learner_user_bids([normalized_user_bid])
        registration_source_map = _load_operator_user_registration_source_map(
            [normalized_user_bid]
        )
        last_login_map = _load_operator_user_last_login_map([normalized_user_bid])
        total_paid_amount_map = _load_operator_user_total_paid_amount_map(
            [normalized_user_bid]
        )
        last_learning_map = _load_operator_user_last_learning_map([normalized_user_bid])
        credit_summary_map = _load_operator_user_credit_summary_map(
            [normalized_user_bid]
        )
        return _build_operator_user_summary(
            user,
            contact_map,
            learning_courses_map,
            created_courses_map,
            learner_user_bids,
            registration_source_map,
            last_login_map,
            total_paid_amount_map,
            last_learning_map,
            credit_summary_map,
        )


def grant_operator_user_credits(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    payload: AdminOperationUserCreditGrantRequestDTO,
) -> AdminOperationUserCreditGrantResultDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        normalized_operator_user_bid = str(operator_user_bid or "").strip()
        if not normalized_operator_user_bid:
            raise_param_error("operator_user_bid")

        user = _load_operator_user_or_raise(normalized_user_bid)
        normalized_grant_source = str(payload.grant_source or "").strip().lower()
        if normalized_grant_source not in OPERATOR_USER_CREDIT_GRANT_SOURCES:
            raise_param_error("grant_source")

        normalized_validity_preset = str(payload.validity_preset or "").strip().lower()
        if normalized_validity_preset not in OPERATOR_USER_CREDIT_VALIDITY_PRESETS:
            raise_param_error("validity_preset")

        granted_amount = _normalize_credit_amount(payload.amount)
        normalized_request_id = str(payload.request_id or "").strip()
        if not normalized_request_id:
            raise_param_error("request_id")
        normalized_note = str(payload.note or "").strip()
        granted_at = datetime.now()
        expires_at = _resolve_operator_credit_grant_expiry(
            creator_bid=normalized_user_bid,
            validity_preset=normalized_validity_preset,
            granted_at=granted_at,
        )
        grant_bid = generate_id(app)
        grant_result = grant_manual_credit_wallet_balance(
            app,
            creator_bid=normalized_user_bid,
            amount=granted_amount,
            source_bid=grant_bid,
            effective_from=granted_at,
            effective_to=expires_at,
            idempotency_key=f"operator_manual_grant:{normalized_request_id}",
            metadata={
                "checkout_type": "manual_grant",
                "grant_type": "manual_grant",
                "grant_source": normalized_grant_source,
                "validity_preset": normalized_validity_preset,
                "operator_user_bid": normalized_operator_user_bid,
                "grant_channel": "operator_user_management",
                "note": normalized_note,
            },
        )
        if grant_result.status not in {"granted", "noop_existing"}:
            raise_error("server.common.systemError")

        persisted_metadata = _normalize_metadata_json(grant_result.metadata_json)
        resolved_grant_source = str(
            persisted_metadata.get("grant_source") or normalized_grant_source
        ).strip()
        resolved_validity_preset = str(
            persisted_metadata.get("validity_preset") or normalized_validity_preset
        ).strip()
        resolved_amount = _format_decimal(
            _quantize_credit_amount(Decimal(str(grant_result.amount or 0)))
        )
        credit_summary_map = _load_operator_user_credit_summary_map(
            [normalized_user_bid]
        )
        summary = _build_operator_user_credit_summary(
            user=user,
            credit_summary_map=credit_summary_map,
        )
        return AdminOperationUserCreditGrantResultDTO(
            user_bid=normalized_user_bid,
            amount=resolved_amount,
            grant_source=resolved_grant_source,
            validity_preset=resolved_validity_preset,
            expires_at=_format_operator_datetime(grant_result.expires_at),
            wallet_bucket_bid=str(grant_result.wallet_bucket_bid or "").strip(),
            ledger_bid=str(grant_result.ledger_bid or "").strip(),
            summary=summary,
        )


def get_operator_user_credits(
    app: Flask,
    *,
    user_bid: str,
    page_index: int,
    page_size: int,
) -> AdminOperationUserCreditLedgerPageDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            OPERATOR_USER_LIST_MAX_PAGE_SIZE,
        )

        user = _load_operator_user_or_raise(normalized_user_bid)
        credit_summary_map = _load_operator_user_credit_summary_map(
            [normalized_user_bid]
        )
        summary = _build_operator_user_credit_summary(
            user=user,
            credit_summary_map=credit_summary_map,
        )

        query = CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == normalized_user_bid,
        )
        total = query.count()
        page_offset = (safe_page_index - 1) * safe_page_size
        rows = (
            query.order_by(
                CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc()
            )
            .offset(page_offset)
            .limit(safe_page_size)
            .all()
        )
        order_map = _load_billing_order_map(
            [str(row.source_bid or "").strip() for row in rows]
        )
        items = [
            _build_operator_user_credit_ledger_item(row, order_map=order_map)
            for row in rows
        ]
        return AdminOperationUserCreditLedgerPageDTO(
            summary=summary,
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
) -> PageNationDTO:
    with app.app_context():
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = max(int(page_size or 20), 1)
        filters = filters or {}

        shifu_bid = str(filters.get("shifu_bid", "") or "").strip()
        course_name = str(filters.get("course_name", "") or "").strip()
        course_status = str(filters.get("course_status", "") or "").strip().lower()
        creator_keyword = str(filters.get("creator_keyword", "") or "").strip()
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        updated_start_time = filters.get("updated_start_time")
        updated_end_time = filters.get("updated_end_time")

        creator_bids = _find_matching_creator_bids(creator_keyword)
        draft_rows = _load_latest_shifus(
            DraftShifu,
            shifu_bid=shifu_bid,
            course_name=course_name,
            creator_bids=creator_bids,
            start_time=start_time,
            end_time=end_time,
            updated_start_time=None,
            updated_end_time=None,
        )
        published_rows = _load_latest_shifus(
            PublishedShifu,
            shifu_bid=shifu_bid,
            course_name=course_name,
            creator_bids=creator_bids,
            start_time=start_time,
            end_time=end_time,
            updated_start_time=None,
            updated_end_time=None,
        )

        merged_courses, published_bids = _merge_courses(draft_rows, published_rows)
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

        user_bids = {
            user_bid
            for course in page_items
            for user_bid in [
                course.created_user_bid,
                (
                    resolve_activity(course).get("updated_user_bid")
                    or course.updated_user_bid
                ),
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
        return PageNationDTO(safe_page_index, safe_page_size, total, items)
