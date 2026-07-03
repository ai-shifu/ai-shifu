"""Operator user identity, contact, status, and summary helpers.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Sequence, Set
from sqlalchemy import case, or_
from flaskr.dao import db
from flaskr.service.learn.const import (
    LEARN_STATUS_RESET,
)
from flaskr.service.learn.models import (
    LearnProgressRecord,
)
from flaskr.service.common.models import (
    raise_error,
    raise_param_error,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos_users import (
    AdminOperationUserCourseSummaryDTO,
    AdminOperationUserSummaryDTO,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
)
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
    UserToken,
)

from flaskr.service.shifu.admin_shared import (
    COURSE_USER_LEARNING_STATUS_COMPLETED,
    COURSE_USER_LEARNING_STATUS_LEARNING,
    COURSE_USER_LEARNING_STATUS_NOT_STARTED,
    COURSE_USER_ROLE_CREATOR,
    COURSE_USER_ROLE_NORMAL,
    COURSE_USER_ROLE_OPERATOR,
    COURSE_USER_ROLE_STUDENT,
    OPERATOR_USER_PRELOADED_AUTH_CREDENTIAL_PROVIDERS,
    OPERATOR_USER_QUICK_FILTER_VALUES,
    OPERATOR_USER_REGISTRATION_CREDENTIAL_PROVIDERS,
    OPERATOR_USER_REGISTRATION_SOURCE_EMAIL,
    OPERATOR_USER_REGISTRATION_SOURCE_IMPORTED,
    OPERATOR_USER_REGISTRATION_SOURCE_PHONE,
    OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN,
    OPERATOR_USER_ROLE_CREATOR,
    OPERATOR_USER_ROLE_LEARNER,
    OPERATOR_USER_ROLE_OPERATOR,
    OPERATOR_USER_ROLE_REGULAR,
    OPERATOR_USER_STATUS_UNKNOWN,
    OPERATOR_USER_SUPPORTED_LOGIN_METHOD_PROVIDERS,
    USER_STATE_TO_OPERATOR_STATUS,
    _format_decimal,
    _normalize_identifier,
)


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
