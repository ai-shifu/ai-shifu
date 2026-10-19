"""Register course-administration operation routes.

The route bodies live in per-domain ``*_routes`` sibling modules. They look up
service functions through this module, so patching a service name here keeps
affecting the registered views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.common.config import get_config
from flaskr.common.http import sensitive_body  # noqa: F401 -- re-exported names
from flaskr.route.admin_profile_onboarding import (
    register_operator_profile_onboarding_routes,
)
from flaskr.route.common import make_common_response  # noqa: F401 -- re-exported names
from flaskr.service.billing.api import (  # noqa: F401 -- re-exported names and patch targets
    build_operator_credit_orders_overview,
    build_operator_credit_orders_page,
    get_operator_credit_order_detail,
)
from flaskr.service.common.models import (  # noqa: F401 -- re-exported names
    raise_error,
    raise_param_error,
)
from flaskr.service.order.api import (  # noqa: F401 -- re-exported names and patch targets
    get_operator_order_detail,
    get_operator_order_overview,
    list_operator_orders,
)
from flaskr.service.promo.api import (  # noqa: F401 -- re-exported names and patch targets
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
from flaskr.service.referral.api import (  # noqa: F401 -- re-exported names and patch targets
    create_operator_referral_campaign,
    get_operator_referral_campaign_detail,
    get_operator_referral_detail,
    get_operator_referral_overview,
    list_operator_referral_campaign_invitations,
    list_operator_referral_campaigns,
    list_operator_referrals,
    update_operator_referral_campaign,
    update_operator_referral_campaign_status,
    update_operator_referral_status,
)
from flaskr.service.shifu.admin_dtos import (  # noqa: F401 -- re-exported names and patch targets
    AdminOperationUserContactChangeRequestDTO,
    AdminOperationUserCreditDeductionRequestDTO,
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationUserPackageGrantRequestDTO,
)
from flaskr.service.shifu.admin_operations.config_rates import (  # noqa: F401 -- re-exported names and patch targets
    get_operator_rate_config,
    update_operator_rate_config,
)
from flaskr.service.shifu.admin_operations.courses import (  # noqa: F401 -- re-exported names and patch targets
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
    transfer_operator_published_courses,
)
from flaskr.service.shifu.admin_operations.courses_routes import (
    register_admin_operations_course_credit_usage_routes,
    register_admin_operations_course_detail_routes,
    register_admin_operations_course_follow_up_routes,
    register_admin_operations_course_list_routes,
    register_admin_operations_course_overview_routes,
    register_admin_operations_course_ownership_routes,
    register_admin_operations_course_rating_routes,
    register_admin_operations_course_user_routes,
)
from flaskr.service.shifu.admin_operations.credit_notifications import (  # noqa: F401 -- re-exported names and patch targets
    dry_run_operator_credit_notifications,
    get_operator_credit_notification_config,
    get_operator_credit_notification_detail,
    get_operator_credit_notification_overview,
    list_operator_credit_notification_email_templates,
    list_operator_credit_notification_templates,
    list_operator_credit_notifications,
    requeue_operator_credit_notification,
    save_operator_credit_notification_email_template,
    sync_operator_credit_notification_template,
    update_operator_credit_notification_config,
    update_operator_credit_notification_email_template_status,
)
from flaskr.service.shifu.admin_operations.credit_notifications_routes import (
    register_admin_operations_credit_notification_routes,
    register_admin_operations_credit_notification_template_routes,
    register_admin_operations_rate_config_routes,
)
from flaskr.service.shifu.admin_operations.orders_routes import (
    register_admin_operations_credit_order_detail_routes,
    register_admin_operations_credit_order_routes,
    register_admin_operations_order_detail_routes,
    register_admin_operations_order_list_routes,
)
from flaskr.service.shifu.admin_operations.promotions_routes import (
    register_admin_operations_promotion_campaign_routes,
    register_admin_operations_promotion_coupon_detail_routes,
    register_admin_operations_promotion_coupon_routes,
)
from flaskr.service.shifu.admin_operations.referrals_routes import (
    register_admin_operations_referral_campaign_member_routes,
    register_admin_operations_referral_campaign_routes,
    register_admin_operations_referral_campaign_update_routes,
    register_admin_operations_referral_routes,
)
from flaskr.service.shifu.admin_operations.route_helpers import (  # noqa: F401 -- re-exported helpers
    CREDIT_NOTIFICATION_DELIVERY_STATUS_VALUES,
    CREDIT_NOTIFICATION_SKIP_REASON_VALUES,
    CREDIT_NOTIFICATION_STATUS_VALUES,
    EMAIL_PATTERN,
    MAX_CONTACT_LENGTH,
    OPERATOR_USER_ROLE_VALUES,
    OPERATOR_USER_STATUS_VALUES,
    PHONE_PATTERN,
    PROMOTION_CAMPAIGN_STATUS_VALUES,
    PROMOTION_COUPON_STATUS_VALUES,
    PROMOTION_COUPON_USAGE_STATUS_VALUES,
    REFERRAL_CAMPAIGN_STATUS_VALUES,
    _normalize_contact_type,
    _normalize_contacts,
    _normalize_query_text,
    _parse_boolean_query_param,
    _parse_choice_query_param,
    _parse_datetime_filter,
    _parse_digit_query_param,
    _parse_positive_query_int,
    _require_operator,
    _validate_contacts,
    _validate_datetime_range,
)
from flaskr.service.shifu.admin_operations.user_credits import (  # noqa: F401 -- re-exported names and patch targets
    deduct_operator_user_credits,
    get_operator_user_credit_usage_detail,
    get_operator_user_credits,
    get_operator_user_grant_bootstrap,
    grant_operator_user_credits,
    grant_operator_user_package,
)
from flaskr.service.shifu.admin_operations.users import (  # noqa: F401 -- re-exported names and patch targets
    get_operator_user_detail,
    get_operator_user_overview,
    list_operator_users,
)
from flaskr.service.shifu.admin_operations.users_routes import (
    register_admin_operations_user_cancellation_routes,
    register_admin_operations_user_credit_routes,
    register_admin_operations_user_detail_routes,
    register_admin_operations_user_grant_routes,
    register_admin_operations_user_list_routes,
)
from flaskr.service.shifu.admin_operations.voice_clones import (  # noqa: F401 -- re-exported names and patch targets
    OPERATOR_VOICE_CLONE_BILLING_STATUSES,
    OPERATOR_VOICE_CLONE_LIST_MAX_PAGE_SIZE,
    OPERATOR_VOICE_CLONE_PROVIDERS,
    OPERATOR_VOICE_CLONE_STATUSES,
    list_operator_voice_clones,
    register_operator_voice_clone,
)
from flaskr.service.shifu.admin_operations.voice_clones_routes import (
    register_admin_operations_voice_clone_list_routes,
    register_admin_operations_voice_clone_registration_routes,
)
from flaskr.service.user.api import (  # noqa: F401 -- re-exported names and patch targets
    cancel_account_subscription_renewals,
    change_operator_user_contact,
    get_account_cancellation_preview,
    get_account_cancellation_status,
    request_user_account_cancellation,
)
from flaskr.util.datetime import parse_naive_utc  # noqa: F401 -- re-exported names

if TYPE_CHECKING:
    from flask import Flask


def _get_login_methods_enabled() -> set[str]:
    """Resolve enabled login methods from configuration."""
    raw = get_config("LOGIN_METHODS_ENABLED", "phone")
    items = raw if isinstance(raw, (list, tuple, set)) else str(raw).split(",")
    methods = {str(item).strip().lower() for item in items if str(item).strip()}
    if "google" in methods:
        methods.add("email")
    return methods


def register_admin_operations_routes(
    app: Flask, *, path_prefix: str = "/api/shifu"
) -> None:
    """Register operator admin operation routes."""
    register_operator_profile_onboarding_routes(
        app,
        path_prefix,
        require_operator=_require_operator,
    )
    register_admin_operations_course_list_routes(app, path_prefix)
    register_admin_operations_course_overview_routes(app, path_prefix)
    register_admin_operations_user_list_routes(app, path_prefix)
    register_admin_operations_voice_clone_list_routes(app, path_prefix)
    register_admin_operations_voice_clone_registration_routes(app, path_prefix)
    register_admin_operations_order_list_routes(app, path_prefix)
    register_admin_operations_credit_notification_routes(app, path_prefix)
    register_admin_operations_rate_config_routes(app, path_prefix)
    register_admin_operations_credit_notification_template_routes(app, path_prefix)
    register_admin_operations_order_detail_routes(app, path_prefix)
    register_admin_operations_credit_order_routes(app, path_prefix)
    register_admin_operations_referral_routes(app, path_prefix)
    register_admin_operations_referral_campaign_routes(app, path_prefix)
    register_admin_operations_referral_campaign_member_routes(app, path_prefix)
    register_admin_operations_referral_campaign_update_routes(app, path_prefix)
    register_admin_operations_promotion_coupon_routes(app, path_prefix)
    register_admin_operations_credit_order_detail_routes(app, path_prefix)
    register_admin_operations_promotion_coupon_detail_routes(app, path_prefix)
    register_admin_operations_promotion_campaign_routes(app, path_prefix)
    register_admin_operations_user_detail_routes(app, path_prefix)
    register_admin_operations_user_cancellation_routes(app, path_prefix)
    register_admin_operations_user_credit_routes(app, path_prefix)
    register_admin_operations_user_grant_routes(app, path_prefix)
    register_admin_operations_course_detail_routes(app, path_prefix)
    register_admin_operations_course_user_routes(app, path_prefix)
    register_admin_operations_course_credit_usage_routes(app, path_prefix)
    register_admin_operations_course_rating_routes(app, path_prefix)
    register_admin_operations_course_follow_up_routes(app, path_prefix)
    register_admin_operations_course_ownership_routes(app, path_prefix)
