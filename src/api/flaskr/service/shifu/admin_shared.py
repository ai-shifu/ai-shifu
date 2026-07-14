"""Shared constants and formatting helpers for operator admin services.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from flask import current_app
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)


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


def _normalize_metadata_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _normalize_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if "@" in normalized:
        return normalized.lower()
    return normalized
