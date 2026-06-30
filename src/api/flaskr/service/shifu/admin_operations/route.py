from __future__ import annotations

import re
from datetime import datetime

from flask import Flask, request
from pydantic import ValidationError

from flaskr.common.config import get_config
from flaskr.route.common import make_common_response
from flaskr.service.billing.api import (
    build_operator_credit_orders_overview,
    build_operator_credit_orders_page,
    get_operator_credit_order_detail,
)
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.api import (
    get_operator_order_detail,
    get_operator_order_overview,
    list_operator_orders,
)
from flaskr.service.promo.api import (
    create_operator_promotion_campaign,
    create_operator_promotion_coupon,
    get_operator_promotion_campaign_detail,
    get_operator_promotion_coupon_detail,
    list_operator_promotion_campaign_redemptions,
    list_operator_promotion_campaigns,
    list_operator_promotion_coupon_codes,
    list_operator_promotion_coupon_usages,
    list_operator_promotion_coupons,
    update_operator_promotion_campaign,
    update_operator_promotion_campaign_status,
    update_operator_promotion_coupon,
    update_operator_promotion_coupon_status,
)
from flaskr.service.referral.api import (
    create_operator_referral_campaign,
    get_operator_referral_campaign_detail,
    get_operator_referral_detail,
    get_operator_referral_overview,
    list_operator_referral_campaigns,
    list_operator_referrals,
    update_operator_referral_campaign,
    update_operator_referral_campaign_status,
    update_operator_referral_status,
)
from flaskr.service.shifu.admin_operations.courses import (
    OPERATOR_ORDER_LIST_MAX_PAGE_SIZE,
    copy_operator_course,
    get_operator_course_chapter_detail,
    get_operator_course_credit_usage_details,
    get_operator_course_credit_usages,
    get_operator_course_detail,
    get_operator_course_follow_up_detail,
    get_operator_course_follow_ups,
    get_operator_course_overview,
    get_operator_course_prompt,
    get_operator_course_ratings,
    get_operator_course_users,
    list_operator_courses,
    transfer_operator_course_creator,
)
from flaskr.service.shifu.admin_operations.credit_notifications import (
    dry_run_operator_credit_notifications,
    get_operator_credit_notification_config,
    get_operator_credit_notification_detail,
    get_operator_credit_notification_overview,
    list_operator_credit_notification_templates,
    list_operator_credit_notifications,
    requeue_operator_credit_notification,
    sync_operator_credit_notification_template,
    update_operator_credit_notification_config,
)
from flaskr.service.shifu.admin_operations.profile_onboarding import (
    get_operator_profile_onboarding_config,
    update_operator_profile_onboarding_config,
)
from flaskr.service.shifu.admin_operations.user_credits import (
    get_operator_user_credit_usage_detail,
    get_operator_user_credits,
    get_operator_user_grant_bootstrap,
    grant_operator_user_credits,
    grant_operator_user_package,
)
from flaskr.service.shifu.admin_operations.users import (
    get_operator_user_detail,
    get_operator_user_overview,
    list_operator_users,
)
from flaskr.service.shifu.admin_operations.voice_clones import (
    OPERATOR_VOICE_CLONE_BILLING_STATUSES,
    OPERATOR_VOICE_CLONE_LIST_MAX_PAGE_SIZE,
    OPERATOR_VOICE_CLONE_STATUSES,
    list_operator_voice_clones,
)
from flaskr.service.shifu.admin_dtos import (
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationUserPackageGrantRequestDTO,
)


MAX_CONTACT_LENGTH = 320
PHONE_PATTERN = re.compile(r"^\d{11}$")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
OPERATOR_USER_STATUS_VALUES = {"unregistered", "registered", "trial", "paid"}
OPERATOR_USER_ROLE_VALUES = {"operator", "creator", "learner", "regular"}
PROMOTION_COUPON_STATUS_VALUES = {"inactive", "not_started", "active", "expired"}
PROMOTION_CAMPAIGN_STATUS_VALUES = {"inactive", "not_started", "active", "ended"}
REFERRAL_CAMPAIGN_STATUS_VALUES = {"inactive", "not_started", "active", "ended"}
PROMOTION_COUPON_USAGE_STATUS_VALUES = {"901", "902", "903", "904"}
CREDIT_NOTIFICATION_STATUS_VALUES = {
    "pending",
    "sent",
    "skipped",
    "skipped_no_mobile",
    "skipped_opt_out",
    "suppressed_duplicate",
    "failed_provider",
}
CREDIT_NOTIFICATION_DELIVERY_STATUS_VALUES = {
    "pending",
    "sent",
    "failed",
    "not_sent",
}
CREDIT_NOTIFICATION_SKIP_REASON_VALUES = {
    "contact",
    "duplicate",
    "policy",
    "stale",
    "template_params",
}


def _parse_datetime_filter(
    value: str, *, field_name: str, is_end: bool = False
) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    for datetime_format in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(normalized, datetime_format)
            if datetime_format == "%Y-%m-%d":
                if is_end:
                    parsed = parsed.replace(hour=23, minute=59, second=59)
                else:
                    parsed = parsed.replace(hour=0, minute=0, second=0)
            return parsed
        except ValueError:
            continue
    raise_param_error(field_name)


def _normalize_query_text(raw_value: object) -> str:
    return str(raw_value or "").strip()


def _parse_choice_query_param(
    raw_value: object,
    *,
    field_name: str,
    allowed_values: set[str],
) -> str:
    normalized = _normalize_query_text(raw_value).lower()
    if not normalized:
        return ""
    if normalized not in allowed_values:
        raise_param_error(field_name)
    return normalized


def _parse_digit_query_param(raw_value: object, *, field_name: str) -> str:
    normalized = _normalize_query_text(raw_value)
    if not normalized:
        return ""
    if not normalized.isdigit():
        raise_param_error(field_name)
    return normalized


def _validate_datetime_range(
    start_time: datetime | None,
    end_time: datetime | None,
    *,
    field_name: str,
) -> None:
    if start_time is not None and end_time is not None and start_time > end_time:
        raise_param_error(field_name)


def _parse_boolean_query_param(
    raw_value: object,
    *,
    field_name: str,
    default: bool = False,
) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    normalized = str(raw_value).strip().lower()
    if not normalized:
        return default
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise_param_error(f"{field_name} is not a boolean")


def _parse_positive_query_int(
    raw_value: object,
    *,
    field_name: str,
    default: int,
    minimum: int = 1,
) -> int:
    if raw_value is None:
        return default
    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError):
        raise_param_error(field_name)
    if parsed_value < minimum:
        raise_param_error(field_name)
    return parsed_value


def _get_login_methods_enabled() -> set[str]:
    """Resolve enabled login methods from configuration."""
    raw = get_config("LOGIN_METHODS_ENABLED", "phone")
    if isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = str(raw).split(",")
    methods = {str(item).strip().lower() for item in items if str(item).strip()}
    if "google" in methods:
        methods.add("email")
    return methods


def _normalize_contact_type(raw_type: str) -> str:
    """Normalize the incoming contact type value."""
    return (raw_type or "").strip().lower()


def _require_operator() -> None:
    user = getattr(request, "user", None)
    if not getattr(user, "is_operator", False):
        raise_error("server.shifu.noPermission")


def _normalize_contacts(raw_contacts: object) -> list[str]:
    """Split and normalize contact identifiers from request payloads."""
    if isinstance(raw_contacts, str):
        items = re.split(r"[,\uFF0C\n]", raw_contacts)
    elif isinstance(raw_contacts, (list, tuple, set)):
        items = list(raw_contacts)
    else:
        items = []
    normalized = []
    for item in items:
        if item is None:
            continue
        trimmed = str(item).strip()
        if trimmed:
            normalized.append(trimmed)
    return normalized


def _validate_contacts(contact_type: str, contacts: list[str]) -> list[str]:
    """Validate and deduplicate contact identifiers."""
    normalized: list[str] = []
    seen: set[str] = set()
    for contact in contacts:
        if not contact or len(contact) > MAX_CONTACT_LENGTH:
            raise_param_error("contact")
        candidate = contact.lower() if contact_type == "email" else contact
        if candidate in seen:
            continue
        seen.add(candidate)
        if contact_type == "phone":
            if not PHONE_PATTERN.match(contact):
                raise_param_error("mobile")
        elif contact_type == "email":
            if not EMAIL_PATTERN.match(candidate):
                raise_param_error("email")
        normalized.append(candidate)
    return normalized


def register_admin_operations_routes(
    app: Flask, *, path_prefix: str = "/api/shifu"
) -> None:
    """Register operator admin operation routes."""

    @app.route(path_prefix + "/admin/operations/courses", methods=["GET"])
    def admin_operations_courses():
        """
        Operator course list
        ---
        tags:
            - Course
        parameters:
            - name: page_index
              type: integer
              required: false
              description: Page index, defaults to 1 when omitted
            - name: page_size
              type: integer
              required: false
              description: Page size, defaults to 20 when omitted
            - name: shifu_bid
              type: string
              required: false
            - name: course_name
              type: string
              required: false
            - name: creator_keyword
              type: string
              required: false
              description: Exact match on user bid, phone, or email
            - name: course_status
              type: string
              required: false
              description: published or unpublished
            - name: start_time
              type: string
              required: false
              description: Course created start date (YYYY-MM-DD)
            - name: end_time
              type: string
              required: false
              description: Course created end date (YYYY-MM-DD)
            - name: updated_start_time
              type: string
              required: false
              description: Course updated start date (YYYY-MM-DD)
            - name: updated_end_time
              type: string
              required: false
              description: Course updated end date (YYYY-MM-DD)
            - name: quick_filter
              type: string
              required: false
              description: draft, published, created_last_7d, learning_active_30d, paid_order_30d
        responses:
            200:
                description: List operator-visible courses
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationCourseListDTO"
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )

        filters = {
            "shifu_bid": _normalize_query_text(request.args.get("shifu_bid")),
            "course_name": _normalize_query_text(request.args.get("course_name")),
            "course_status": _normalize_query_text(request.args.get("course_status")),
            "quick_filter": _normalize_query_text(request.args.get("quick_filter")),
            "creator_keyword": _normalize_query_text(
                request.args.get("creator_keyword")
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
            "updated_start_time": _parse_datetime_filter(
                request.args.get("updated_start_time", ""),
                field_name="updated_start_time",
                is_end=False,
            ),
            "updated_end_time": _parse_datetime_filter(
                request.args.get("updated_end_time", ""),
                field_name="updated_end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        _validate_datetime_range(
            filters["updated_start_time"],
            filters["updated_end_time"],
            field_name="updated_start_time",
        )
        return make_common_response(
            list_operator_courses(app, page_index, page_size, filters)
        )

    @app.route(path_prefix + "/admin/operations/courses/overview", methods=["GET"])
    def admin_operations_course_overview():
        """
        Operator course overview
        ---
        tags:
            - Course
        responses:
            200:
                description: Operator-visible course overview metrics
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationCourseOverviewDTO"
        """
        _require_operator()
        return make_common_response(get_operator_course_overview(app))

    @app.route(path_prefix + "/admin/operations/users", methods=["GET"])
    def admin_operations_users():
        """
        Operator user list
        ---
        tags:
            - User
        parameters:
            - name: page_index
              type: integer
              required: true
            - name: page_size
              type: integer
              required: true
            - name: user_bid
              type: string
              required: false
            - name: identifier
              type: string
              required: false
              description: User phone, email, identify, or user_bid keyword
            - name: mobile
              type: string
              required: false
              description: Deprecated alias for identifier
            - name: nickname
              type: string
              required: false
            - name: user_status
              type: string
              required: false
              description: unregistered, registered, or paid
            - name: user_role
              type: string
              required: false
              description: regular, creator, learner, or operator
            - name: quick_filter
              type: string
              required: false
              description: creator, learner, registered, paid, created_last_30d, registered_last_30d, learning_active_30d, paid_last_30d, guest
            - name: start_time
              type: string
              required: false
              description: User created start date (YYYY-MM-DD)
            - name: end_time
              type: string
              required: false
              description: User created end date (YYYY-MM-DD)
        responses:
            200:
                description: List active users for operators
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationUserListDTO"
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )

        filters = {
            "user_bid": _normalize_query_text(request.args.get("user_bid")),
            "identifier": _normalize_query_text(request.args.get("identifier")),
            "mobile": _normalize_query_text(request.args.get("mobile")),
            "nickname": _normalize_query_text(request.args.get("nickname")),
            "user_status": _parse_choice_query_param(
                request.args.get("user_status"),
                field_name="user_status",
                allowed_values=OPERATOR_USER_STATUS_VALUES,
            ),
            "user_role": _parse_choice_query_param(
                request.args.get("user_role"),
                field_name="user_role",
                allowed_values=OPERATOR_USER_ROLE_VALUES,
            ),
            "quick_filter": _normalize_query_text(request.args.get("quick_filter")),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            list_operator_users(app, page_index, page_size, filters)
        )

    @app.route(path_prefix + "/admin/operations/users/overview", methods=["GET"])
    def admin_operations_user_overview():
        """
        Operator user overview
        ---
        tags:
            - User
        responses:
            200:
                description: Operator-visible user overview metrics
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationUserOverviewDTO"
        """
        _require_operator()
        return make_common_response(get_operator_user_overview(app))

    @app.route(path_prefix + "/admin/operations/voice-clones", methods=["GET"])
    def admin_operations_voice_clones():
        """
        Operator MiniMax cloned voice list
        ---
        tags:
            - TTS
        parameters:
            - name: page_index
              type: integer
              required: false
            - name: page_size
              type: integer
              required: false
            - name: status
              type: string
              required: false
            - name: failure_reason
              type: string
              required: false
            - name: billing_status
              type: string
              required: false
            - name: start_time
              type: string
              required: false
            - name: end_time
              type: string
              required: false
            - name: user_keyword
              type: string
              required: false
            - name: course_keyword
              type: string
              required: false
            - name: voice_keyword
              type: string
              required: false
            - name: minimax_status_code
              type: integer
              required: false
        responses:
            200:
                description: List operator-visible MiniMax cloned voice jobs
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        page_size = min(page_size, OPERATOR_VOICE_CLONE_LIST_MAX_PAGE_SIZE)
        raw_minimax_status_code = _normalize_query_text(
            request.args.get("minimax_status_code")
        )
        minimax_status_code = (
            _parse_positive_query_int(
                raw_minimax_status_code,
                field_name="minimax_status_code",
                default=0,
                minimum=0,
            )
            if raw_minimax_status_code
            else None
        )

        filters = {
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=OPERATOR_VOICE_CLONE_STATUSES,
            ),
            "failure_reason": _normalize_query_text(request.args.get("failure_reason")),
            "billing_status": _parse_choice_query_param(
                request.args.get("billing_status"),
                field_name="billing_status",
                allowed_values=OPERATOR_VOICE_CLONE_BILLING_STATUSES,
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
            "user_keyword": _normalize_query_text(request.args.get("user_keyword")),
            "course_keyword": _normalize_query_text(request.args.get("course_keyword")),
            "voice_keyword": _normalize_query_text(request.args.get("voice_keyword")),
            "minimax_status_code": minimax_status_code,
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            list_operator_voice_clones(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(path_prefix + "/admin/operations/orders", methods=["GET"])
    def admin_operations_orders():
        """
        Operator global order list
        ---
        tags:
            - Order
        parameters:
            - name: page_index
              type: integer
              required: true
            - name: page_size
              type: integer
              required: true
            - name: user_keyword
              type: string
              required: false
              description: Exact match on user bid, phone, or email
            - name: order_bid
              type: string
              required: false
            - name: shifu_bid
              type: string
              required: false
            - name: course_name
              type: string
              required: false
            - name: status
              type: string
              required: false
            - name: order_source
              type: string
              required: false
              description: user_purchase, coupon_redeem, import_activation, or open_api
            - name: payment_channel
              type: string
              required: false
            - name: start_time
              type: string
              required: false
              description: Order created start date (YYYY-MM-DD)
            - name: end_time
              type: string
              required: false
              description: Order created end date (YYYY-MM-DD)
        responses:
            200:
                description: List global operator-visible orders
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        page_size = min(page_size, OPERATOR_ORDER_LIST_MAX_PAGE_SIZE)

        filters = {
            "user_keyword": _normalize_query_text(request.args.get("user_keyword")),
            "order_bid": _normalize_query_text(request.args.get("order_bid")),
            "shifu_bid": _normalize_query_text(request.args.get("shifu_bid")),
            "course_name": _normalize_query_text(request.args.get("course_name")),
            "status": _parse_digit_query_param(
                request.args.get("status"),
                field_name="status",
            ),
            "order_source": _normalize_query_text(request.args.get("order_source")),
            "payment_channel": _normalize_query_text(
                request.args.get("payment_channel")
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            list_operator_orders(app, page_index, page_size, filters)
        )

    @app.route(path_prefix + "/admin/operations/orders/overview", methods=["GET"])
    def admin_operations_order_overview():
        """
        Operator learning order overview
        ---
        tags:
            - Order
        responses:
            200:
                description: Operator-visible learning order overview metrics
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/OrderAdminOverviewDTO"
        """
        _require_operator()
        return make_common_response(get_operator_order_overview(app))

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/overview",
        methods=["GET"],
    )
    def admin_operation_credit_notifications_overview():
        """Return global operator credit notification overview."""
        _require_operator()
        return make_common_response(get_operator_credit_notification_overview(app))

    @app.route(
        path_prefix + "/admin/operations/credit-notifications",
        methods=["GET"],
    )
    def admin_operation_credit_notifications():
        """List operator credit notification records."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "creator_bid": _normalize_query_text(request.args.get("creator_bid")),
            "creator_keyword": _normalize_query_text(
                request.args.get("creator_keyword")
            ),
            "target_user_bid": _normalize_query_text(
                request.args.get("target_user_bid")
            ),
            "mobile": _normalize_query_text(request.args.get("mobile")),
            "notification_type": _normalize_query_text(
                request.args.get("notification_type")
            ),
            "channel": _normalize_query_text(request.args.get("channel")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=CREDIT_NOTIFICATION_STATUS_VALUES,
            ),
            "delivery_status": _parse_choice_query_param(
                request.args.get("delivery_status"),
                field_name="delivery_status",
                allowed_values=CREDIT_NOTIFICATION_DELIVERY_STATUS_VALUES,
            ),
            "skip_reason": _parse_choice_query_param(
                request.args.get("skip_reason"),
                field_name="skip_reason",
                allowed_values=CREDIT_NOTIFICATION_SKIP_REASON_VALUES,
            ),
            "source_type": _normalize_query_text(request.args.get("source_type")),
            "source_bid": _normalize_query_text(request.args.get("source_bid")),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            list_operator_credit_notifications(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/<notification_bid>",
        methods=["GET"],
    )
    def admin_operation_credit_notification_detail(notification_bid: str):
        """Return one operator credit notification record detail."""
        _require_operator()
        return make_common_response(
            get_operator_credit_notification_detail(
                app,
                notification_bid=notification_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/config",
        methods=["GET"],
    )
    def admin_operation_credit_notification_config():
        """Get operator credit notification config."""
        _require_operator()
        return make_common_response(get_operator_credit_notification_config(app))

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/config",
        methods=["POST"],
    )
    def admin_operation_update_credit_notification_config():
        """Update operator credit notification config."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_config")
        return make_common_response(
            update_operator_credit_notification_config(
                app,
                payload=payload,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/profile-onboarding",
        methods=["GET"],
    )
    def admin_operation_profile_onboarding_config():
        """Get operator profile onboarding config."""
        _require_operator()
        return make_common_response(get_operator_profile_onboarding_config(app))

    @app.route(
        path_prefix + "/admin/operations/profile-onboarding",
        methods=["POST"],
    )
    def admin_operation_update_profile_onboarding_config():
        """Update operator profile onboarding config."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("profile_onboarding_config")
        return make_common_response(
            update_operator_profile_onboarding_config(
                app,
                payload=payload,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/templates/sync",
        methods=["POST"],
    )
    def admin_operation_credit_notification_template_sync():
        """Sync one SMS template for operator credit notification config."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_template_sync")
        return make_common_response(
            sync_operator_credit_notification_template(
                app,
                notification_type=str(payload.get("notification_type") or ""),
                template_code=str(payload.get("template_code") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/templates",
        methods=["GET"],
    )
    def admin_operation_credit_notification_templates():
        """List SMS templates for operator credit notification config."""
        _require_operator()
        return make_common_response(list_operator_credit_notification_templates(app))

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/dry-run",
        methods=["POST"],
    )
    def admin_operation_credit_notification_dry_run():
        """Dry-run operator credit notification scans."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_dry_run")
        return make_common_response(
            dry_run_operator_credit_notifications(
                app,
                notification_type=str(payload.get("notification_type") or ""),
                creator_bid=str(payload.get("creator_bid") or ""),
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/credit-notifications/<notification_bid>/requeue",
        methods=["POST"],
    )
    def admin_operation_credit_notification_requeue(notification_bid: str):
        """Requeue one failed provider credit notification."""
        _require_operator()
        return make_common_response(
            requeue_operator_credit_notification(
                app,
                notification_bid=notification_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/orders/<order_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_order_detail(order_bid: str):
        """
        Get operator order detail
        ---
        tags:
            - Order
        parameters:
            - name: order_bid
              in: path
              type: string
              required: true
              description: Order business identifier
        responses:
            200:
                description: Operator order detail
        """
        _require_operator()
        if not str(order_bid or "").strip():
            raise_param_error("order_bid")
        return make_common_response(get_operator_order_detail(app, order_bid))

    @app.route(path_prefix + "/admin/operations/orders/credits", methods=["GET"])
    def admin_operations_credit_orders():
        """
        Operator global credit order list
        ---
        tags:
            - Order
        parameters:
            - name: page_index
              type: integer
              required: false
              description: Page index, defaults to 1 when omitted
            - name: page_size
              type: integer
              required: false
              description: Page size, defaults to 20 when omitted and is capped by OPERATOR_ORDER_LIST_MAX_PAGE_SIZE
            - name: creator_keyword
              type: string
              required: false
            - name: product_keyword
              type: string
              required: false
            - name: bill_order_bid
              type: string
              required: false
            - name: credit_order_kind
              type: string
              required: false
              description: plan or topup
            - name: status
              type: string
              required: false
            - name: payment_provider
              type: string
              required: false
            - name: has_available_credits
              type: boolean
              required: false
              description: Only include orders whose granted credits still have remaining balance
            - name: start_time
              type: string
              required: false
            - name: end_time
              type: string
              required: false
        responses:
            200:
                description: List global operator-visible credit orders
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        page_size = min(page_size, OPERATOR_ORDER_LIST_MAX_PAGE_SIZE)
        start_time = _parse_datetime_filter(
            request.args.get("start_time", ""),
            field_name="start_time",
            is_end=False,
        )
        end_time = _parse_datetime_filter(
            request.args.get("end_time", ""),
            field_name="end_time",
            is_end=True,
        )
        _validate_datetime_range(start_time, end_time, field_name="start_time")
        return make_common_response(
            build_operator_credit_orders_page(
                app,
                page_index=page_index,
                page_size=page_size,
                creator_keyword=_normalize_query_text(
                    request.args.get("creator_keyword")
                ),
                product_keyword=_normalize_query_text(
                    request.args.get("product_keyword")
                ),
                bill_order_bid=_normalize_query_text(
                    request.args.get("bill_order_bid")
                ),
                credit_order_kind=_normalize_query_text(
                    request.args.get("credit_order_kind")
                ),
                status=_normalize_query_text(request.args.get("status")),
                has_available_credits=_parse_boolean_query_param(
                    request.args.get("has_available_credits"),
                    field_name="has_available_credits",
                ),
                payment_provider=_normalize_query_text(
                    request.args.get("payment_provider")
                ),
                start_time=start_time,
                end_time=end_time,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/orders/credits/overview",
        methods=["GET"],
    )
    def admin_operations_credit_order_overview():
        """
        Operator credit order overview
        ---
        tags:
            - Order
        responses:
            200:
                description: Operator-visible credit order overview metrics
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/OperatorCreditOrderOverviewDTO"
        """
        _require_operator()
        return make_common_response(build_operator_credit_orders_overview(app))

    @app.route(path_prefix + "/admin/operations/referrals", methods=["GET"])
    def admin_operations_referrals():
        """List operator-visible referral invite relations."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "campaign_bid": _normalize_query_text(request.args.get("campaign_bid")),
            "inviter_user_bid": _normalize_query_text(
                request.args.get("inviter_user_bid")
            ),
            "invitee_user_bid": _normalize_query_text(
                request.args.get("invitee_user_bid")
            ),
            "invite_code": _normalize_query_text(request.args.get("invite_code")),
            "relation_status": _parse_digit_query_param(
                request.args.get("relation_status"),
                field_name="relation_status",
            ),
            "abnormal_status": _parse_digit_query_param(
                request.args.get("abnormal_status"),
                field_name="abnormal_status",
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            list_operator_referrals(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(path_prefix + "/admin/operations/referrals/overview", methods=["GET"])
    def admin_operations_referrals_overview():
        """Return operator referral overview metrics."""
        _require_operator()
        return make_common_response(get_operator_referral_overview(app))

    @app.route(
        path_prefix + "/admin/operations/referrals/<relation_bid>",
        methods=["GET"],
    )
    def admin_operations_referral_detail(relation_bid: str):
        """Return one operator referral relation detail."""
        _require_operator()
        return make_common_response(
            get_operator_referral_detail(app, relation_bid=relation_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/referrals/<relation_bid>/status",
        methods=["POST"],
    )
    def admin_operations_referral_status(relation_bid: str):
        """Update one referral relation or reward operator status."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_status")
        return make_common_response(
            update_operator_referral_status(
                app,
                relation_bid=relation_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/referrals/<relation_bid>/adjustment",
        methods=["POST"],
    )
    def admin_operations_referral_adjustment(relation_bid: str):
        """Apply an audited operator adjustment to one referral relation."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_adjustment")
        return make_common_response(
            update_operator_referral_status(
                app,
                relation_bid=relation_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/referral-campaigns",
        methods=["GET"],
    )
    def admin_operations_promotion_referral_campaigns():
        """Operator referral campaign configuration list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=REFERRAL_CAMPAIGN_STATUS_VALUES,
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            list_operator_referral_campaigns(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/referral-campaigns",
        methods=["POST"],
    )
    def admin_create_operations_promotion_referral_campaign():
        """Create operator referral campaign configuration."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_campaign")
        return make_common_response(
            create_operator_referral_campaign(
                app,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/referral-campaigns/<campaign_bid>",
        methods=["GET"],
    )
    def admin_operations_promotion_referral_campaign_detail(campaign_bid: str):
        """Get operator referral campaign configuration detail."""
        _require_operator()
        return make_common_response(
            get_operator_referral_campaign_detail(app, campaign_bid=campaign_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/referral-campaigns/<campaign_bid>",
        methods=["POST"],
    )
    def admin_update_operations_promotion_referral_campaign(campaign_bid: str):
        """Update operator referral campaign configuration."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_campaign")
        return make_common_response(
            update_operator_referral_campaign(
                app,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                campaign_bid=campaign_bid,
                payload=payload,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/promotions/referral-campaigns/<campaign_bid>/status",
        methods=["POST"],
    )
    def admin_operations_promotion_referral_campaign_status(campaign_bid: str):
        """Update operator referral campaign configuration status."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_campaign_status")
        return make_common_response(
            update_operator_referral_campaign_status(
                app,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                campaign_bid=campaign_bid,
                enabled=payload.get("enabled"),
            )
        )

    @app.route(path_prefix + "/admin/operations/promotions/coupons", methods=["GET"])
    def admin_operations_promotion_coupons():
        """Operator coupon batch list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )

        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
            "name": _normalize_query_text(request.args.get("name")),
            "course_query": _normalize_query_text(request.args.get("course_query")),
            "shifu_bid": _normalize_query_text(request.args.get("shifu_bid")),
            "course_name": _normalize_query_text(request.args.get("course_name")),
            "usage_type": _normalize_query_text(request.args.get("usage_type")),
            "ops_state": _normalize_query_text(request.args.get("ops_state")),
            "discount_type": _normalize_query_text(request.args.get("discount_type")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=PROMOTION_COUPON_STATUS_VALUES,
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            list_operator_promotion_coupons(app, page_index, page_size, filters)
        )

    @app.route(path_prefix + "/admin/operations/promotions/coupons", methods=["POST"])
    def admin_create_operations_promotion_coupon():
        """Create operator coupon batch."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        return make_common_response(
            create_operator_promotion_coupon(app, request.user.user_id, payload)
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>",
        methods=["POST"],
    )
    def admin_update_operations_promotion_coupon(coupon_bid: str):
        """Update operator coupon batch."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        return make_common_response(
            update_operator_promotion_coupon(
                app, request.user.user_id, coupon_bid, payload
            )
        )

    @app.route(
        path_prefix + "/admin/operations/orders/credits/<bill_order_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_credit_order_detail(bill_order_bid: str):
        """
        Get operator credit order detail
        ---
        tags:
            - Order
        parameters:
            - name: bill_order_bid
              in: path
              type: string
              required: true
              description: Billing order business identifier
        responses:
            200:
                description: Operator credit order detail
        """
        _require_operator()
        if not str(bill_order_bid or "").strip():
            raise_param_error("bill_order_bid")
        return make_common_response(
            get_operator_credit_order_detail(
                app,
                bill_order_bid=bill_order_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>",
        methods=["GET"],
    )
    def admin_operations_promotion_coupon_detail(coupon_bid: str):
        """Get operator coupon batch detail."""
        _require_operator()
        return make_common_response(
            get_operator_promotion_coupon_detail(app, coupon_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>/status",
        methods=["POST"],
    )
    def admin_operations_promotion_coupon_status(coupon_bid: str):
        """Update operator coupon batch status."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        enabled = payload.get("enabled")
        return make_common_response(
            update_operator_promotion_coupon_status(
                app,
                request.user.user_id,
                coupon_bid,
                enabled,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>/usages",
        methods=["GET"],
    )
    def admin_operations_promotion_coupon_usages(coupon_bid: str):
        """Get operator coupon usage list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=PROMOTION_COUPON_USAGE_STATUS_VALUES,
            ),
        }
        return make_common_response(
            list_operator_promotion_coupon_usages(
                app, coupon_bid, page_index, page_size, filters
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>/codes",
        methods=["GET"],
    )
    def admin_operations_promotion_coupon_codes(coupon_bid: str):
        """Get operator coupon code pool list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
        }
        return make_common_response(
            list_operator_promotion_coupon_codes(
                app, coupon_bid, page_index, page_size, filters
            )
        )

    @app.route(path_prefix + "/admin/operations/promotions/campaigns", methods=["GET"])
    def admin_operations_promotion_campaigns():
        """Operator campaign list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )

        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
            "course_query": _normalize_query_text(request.args.get("course_query")),
            "shifu_bid": _normalize_query_text(request.args.get("shifu_bid")),
            "course_name": _normalize_query_text(request.args.get("course_name")),
            "apply_type": _normalize_query_text(request.args.get("apply_type")),
            "channel": _normalize_query_text(request.args.get("channel")),
            "discount_type": _normalize_query_text(request.args.get("discount_type")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=PROMOTION_CAMPAIGN_STATUS_VALUES,
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            list_operator_promotion_campaigns(app, page_index, page_size, filters)
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns",
        methods=["POST"],
    )
    def admin_create_operations_promotion_campaign():
        """Create operator campaign."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        return make_common_response(
            create_operator_promotion_campaign(app, request.user.user_id, payload)
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns/<promo_bid>",
        methods=["GET"],
    )
    def admin_operations_promotion_campaign_detail(promo_bid: str):
        """Get operator campaign detail."""
        _require_operator()
        return make_common_response(
            get_operator_promotion_campaign_detail(app, promo_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns/<promo_bid>",
        methods=["POST"],
    )
    def admin_update_operations_promotion_campaign(promo_bid: str):
        """Update operator campaign."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        return make_common_response(
            update_operator_promotion_campaign(
                app, request.user.user_id, promo_bid, payload
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns/<promo_bid>/status",
        methods=["POST"],
    )
    def admin_operations_promotion_campaign_status(promo_bid: str):
        """Update operator campaign status."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        enabled = payload.get("enabled")
        return make_common_response(
            update_operator_promotion_campaign_status(
                app,
                request.user.user_id,
                promo_bid,
                enabled,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns/<promo_bid>/redemptions",
        methods=["GET"],
    )
    def admin_operations_promotion_campaign_redemptions(promo_bid: str):
        """Get operator campaign redemption list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
        }
        return make_common_response(
            list_operator_promotion_campaign_redemptions(
                app,
                promo_bid,
                page_index,
                page_size,
                filters,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/detail", methods=["GET"]
    )
    def admin_operation_user_detail(user_bid: str):
        """
        Get operator user detail
        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
        responses:
            200:
                description: Operator user detail
        """
        _require_operator()
        return make_common_response(get_operator_user_detail(app, user_bid))

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/credits", methods=["GET"]
    )
    def admin_operation_user_credits(user_bid: str):
        """
        Get operator user credits detail
        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
            - name: page_index
              type: integer
              required: false
            - name: page_size
              type: integer
              required: false
            - name: credit_type
              in: query
              type: string
              required: false
              description: Credit ledger type filter
            - name: grant_source
              in: query
              type: string
              required: false
              description: Grant source filter
            - name: course_query
              in: query
              type: string
              required: false
              description: Course ID exact match or course name fuzzy match for consume rows
            - name: usage_scene
              in: query
              type: string
              required: false
              description: Consume scene filter
            - name: usage_mode
              in: query
              type: string
              required: false
              description: Consume mode filter
            - name: start_time
              in: query
              type: string
              required: false
              description: Inclusive filter start time
            - name: end_time
              in: query
              type: string
              required: false
              description: Inclusive filter end time
        responses:
            200:
                description: Operator user credits detail
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )

        filters = {
            "credit_type": request.args.get("credit_type", ""),
            "grant_source": request.args.get("grant_source", ""),
            "course_query": request.args.get("course_query", ""),
            "usage_scene": request.args.get("usage_scene", ""),
            "usage_mode": request.args.get("usage_mode", ""),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )

        return make_common_response(
            get_operator_user_credits(
                app,
                user_bid=user_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/users/<user_bid>/credits/usages/<usage_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_user_credit_usage_detail(user_bid: str, usage_bid: str):
        """
        Get operator user credit usage content detail
        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
            - name: usage_bid
              in: path
              type: string
              required: true
              description: Usage business identifier
        responses:
            200:
                description: Operator user credit usage content detail
        """
        _require_operator()
        return make_common_response(
            get_operator_user_credit_usage_detail(
                app,
                user_bid=user_bid,
                usage_bid=usage_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/credit-grant/bootstrap",
        methods=["GET"],
    )
    def admin_operation_user_credit_grant_bootstrap(user_bid: str):
        """
        Get operator user grant bootstrap
        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
        responses:
            200:
                description: Operator user grant bootstrap payload
        """
        _require_operator()
        return make_common_response(
            get_operator_user_grant_bootstrap(
                app,
                user_bid=user_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/credits/grant",
        methods=["POST"],
    )
    def admin_operation_user_credit_grant(user_bid: str):
        """
        Grant operator user credits
        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        $ref: "#/components/schemas/AdminOperationUserCreditGrantRequestDTO"
        responses:
            200:
                description: Operator user credits grant result
        """
        _require_operator()
        payload_data = request.get_json(silent=True) or {}
        try:
            payload = AdminOperationUserCreditGrantRequestDTO.model_validate(
                payload_data
            )
        except ValidationError:
            raise_param_error("credits_grant_payload")
        return make_common_response(
            grant_operator_user_credits(
                app,
                user_bid=user_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/packages/grant",
        methods=["POST"],
    )
    def admin_operation_user_package_grant(user_bid: str):
        """
        Grant operator user package
        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        $ref: "#/components/schemas/AdminOperationUserPackageGrantRequestDTO"
        responses:
            200:
                description: Operator user package grant result
        """
        _require_operator()
        payload_data = request.get_json(silent=True) or {}
        try:
            payload = AdminOperationUserPackageGrantRequestDTO.model_validate(
                payload_data
            )
        except ValidationError:
            raise_param_error("package_grant_payload")
        return make_common_response(
            grant_operator_user_package(
                app,
                user_bid=user_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/prompt",
        methods=["GET"],
    )
    def admin_operation_course_prompt(shifu_bid: str):
        """Get operator course prompt."""
        _require_operator()
        return make_common_response(
            get_operator_course_prompt(app, shifu_bid=shifu_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/detail", methods=["GET"]
    )
    def admin_operation_course_detail(shifu_bid: str):
        """
        Get operator course detail
        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
        responses:
            200:
                description: Operator course detail
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationCourseDetailDTO"
        """
        _require_operator()
        return make_common_response(
            get_operator_course_detail(
                app,
                shifu_bid=shifu_bid,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/courses/<shifu_bid>/chapters/<outline_item_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_course_chapter_detail(shifu_bid: str, outline_item_bid: str):
        """
        Get operator course chapter detail
        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: outline_item_bid
              in: path
              type: string
              required: true
              description: Outline item bid
        responses:
            200:
                description: Operator course chapter detail
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationCourseChapterDetailDTO"
        """
        _require_operator()
        return make_common_response(
            get_operator_course_chapter_detail(
                app,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_item_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/users", methods=["GET"]
    )
    def admin_operation_course_users(shifu_bid: str):
        """
        Get operator course users
        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: page
              in: query
              type: integer
              required: false
              description: Page index
            - name: page_size
              in: query
              type: integer
              required: false
              description: Page size
            - name: keyword
              in: query
              type: string
              required: false
              description: User keyword
            - name: user_role
              in: query
              type: string
              required: false
              description: User role filter
            - name: learning_status
              in: query
              type: string
              required: false
              description: Learning status filter
            - name: payment_status
              in: query
              type: string
              required: false
              description: Payment status filter
        responses:
            200:
                description: Operator course user list
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
            "user_role": request.args.get("user_role", ""),
            "learning_status": request.args.get("learning_status", ""),
            "payment_status": request.args.get("payment_status", ""),
        }
        return make_common_response(
            get_operator_course_users(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/credit-usages",
        methods=["GET"],
    )
    def admin_operation_course_credit_usages(shifu_bid: str):
        """
        Get operator course credit usage list
        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: page
              in: query
              type: integer
              required: false
              description: Page index
            - name: page_size
              in: query
              type: integer
              required: false
              description: Page size
            - name: keyword
              in: query
              type: string
              required: false
              description: User keyword
            - name: mode
              in: query
              type: string
              required: false
              description: Credit usage mode filter
            - name: usage_scene
              in: query
              type: string
              required: false
              description: Credit usage scene filter
            - name: view
              in: query
              type: string
              required: false
              description: Credit usage view mode, grouped or raw
            - name: start_time
              in: query
              type: string
              required: false
              description: Inclusive filter start time
            - name: end_time
              in: query
              type: string
              required: false
              description: Inclusive filter end time
        responses:
            200:
                description: Operator course credit usage list
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
            "mode": request.args.get("mode", ""),
            "usage_scene": request.args.get("usage_scene", ""),
            "view": request.args.get("view", ""),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            get_operator_course_credit_usages(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/credit-usages/details",
        methods=["GET"],
    )
    def admin_operation_course_credit_usage_details(shifu_bid: str):
        """
        Get operator course credit usage detail list
        ---
        tags:
            - Shifu
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=10,
        )
        return make_common_response(
            get_operator_course_credit_usage_details(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters={
                    "user_bid": request.args.get("user_bid", ""),
                    "outline_item_bid": request.args.get("outline_item_bid", ""),
                    "usage_scene": request.args.get("usage_scene", ""),
                    "mode": request.args.get("mode", ""),
                },
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/ratings",
        methods=["GET"],
    )
    def admin_operation_course_ratings(shifu_bid: str):
        """
        Get operator course rating list
        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: page
              in: query
              type: integer
              required: false
              description: Page index
            - name: page_size
              in: query
              type: integer
              required: false
              description: Page size
            - name: keyword
              in: query
              type: string
              required: false
              description: User keyword
            - name: chapter_keyword
              in: query
              type: string
              required: false
              description: Chapter or lesson keyword
            - name: score
              in: query
              type: string
              required: false
              description: Rating score filter
            - name: mode
              in: query
              type: string
              required: false
              description: Rating mode filter
            - name: has_comment
              in: query
              type: string
              required: false
              description: Whether to only return rows with comments
            - name: sort_by
              in: query
              type: string
              required: false
              description: Rating sort option
            - name: start_time
              in: query
              type: string
              required: false
              description: Inclusive filter start time
            - name: end_time
              in: query
              type: string
              required: false
              description: Inclusive filter end time
            - name: include_summary
              in: query
              type: boolean
              required: false
              description: Whether to include expensive summary metrics. Defaults to true. When false, summary fields are returned as defaults while total and page_count still reflect the filtered result.
        responses:
            200:
                description: Operator course rating list
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
            "chapter_keyword": request.args.get("chapter_keyword", ""),
            "score": request.args.get("score", ""),
            "mode": request.args.get("mode", ""),
            "has_comment": request.args.get("has_comment", ""),
            "sort_by": request.args.get("sort_by", ""),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        include_summary = _parse_boolean_query_param(
            request.args.get("include_summary", None),
            field_name="include_summary",
            default=True,
        )
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            get_operator_course_ratings(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
                include_summary=include_summary,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/follow-ups",
        methods=["GET"],
    )
    def admin_operation_course_follow_ups(shifu_bid: str):
        """
        Get operator course follow-up list
        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: page
              in: query
              type: integer
              required: false
              description: Page index
            - name: page_size
              in: query
              type: integer
              required: false
              description: Page size
            - name: keyword
              in: query
              type: string
              required: false
              description: User keyword
            - name: chapter_keyword
              in: query
              type: string
              required: false
              description: Chapter or lesson keyword
            - name: source_status
              in: query
              type: string
              required: false
              description: Original output source status filter (resolved or missing)
            - name: start_time
              in: query
              type: string
              required: false
              description: Inclusive filter start time
            - name: end_time
              in: query
              type: string
              required: false
              description: Inclusive filter end time
            - name: include_summary
              in: query
              type: boolean
              required: false
              description: Whether to include expensive summary metrics
        responses:
            200:
                description: Operator course follow-up list
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
            "chapter_keyword": request.args.get("chapter_keyword", ""),
            "source_status": request.args.get("source_status", ""),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        include_summary = _parse_boolean_query_param(
            request.args.get("include_summary", None),
            field_name="include_summary",
            default=True,
        )
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            get_operator_course_follow_ups(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
                include_summary=include_summary,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/courses/<shifu_bid>/follow-ups/<generated_block_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_course_follow_up_detail(
        shifu_bid: str,
        generated_block_bid: str,
    ):
        """
        Get operator course follow-up detail
        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: generated_block_bid
              in: path
              type: string
              required: true
              description: Follow-up generated block bid
        responses:
            200:
                description: Operator course follow-up detail
        """
        _require_operator()
        return make_common_response(
            get_operator_course_follow_up_detail(
                app,
                shifu_bid=shifu_bid,
                generated_block_bid=generated_block_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/copy",
        methods=["POST"],
    )
    def admin_copy_course(shifu_bid: str):
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("payload")
        contact_type = _normalize_contact_type(payload.get("contact_type", ""))
        allowed_methods = _get_login_methods_enabled()
        if contact_type not in {"phone", "email"}:
            raise_param_error("contact_type")
        if allowed_methods and contact_type not in allowed_methods:
            raise_param_error("contact_type")

        identifiers = _validate_contacts(
            contact_type,
            _normalize_contacts(payload.get("identifier", "")),
        )
        if len(identifiers) != 1:
            raise_param_error("contact")

        return make_common_response(
            copy_operator_course(
                app,
                shifu_bid=shifu_bid,
                contact_type=contact_type,
                identifier=identifiers[0],
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                new_course_name=str(payload.get("new_course_name", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/transfer-creator",
        methods=["POST"],
    )
    def admin_transfer_course_creator(shifu_bid: str):
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("payload")
        contact_type = _normalize_contact_type(payload.get("contact_type", ""))
        allowed_methods = _get_login_methods_enabled()
        if contact_type not in {"phone", "email"}:
            raise_param_error("contact_type")
        if allowed_methods and contact_type not in allowed_methods:
            raise_param_error("contact_type")

        identifiers = _validate_contacts(
            contact_type,
            _normalize_contacts(payload.get("identifier", "")),
        )
        if len(identifiers) != 1:
            raise_param_error("contact")

        return make_common_response(
            transfer_operator_course_creator(
                app,
                shifu_bid=shifu_bid,
                contact_type=contact_type,
                identifier=identifiers[0],
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )
