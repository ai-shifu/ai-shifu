"""Handle user support for course-administration operations."""

from __future__ import annotations

from flaskr.service.shifu.admin_shared import (
    OPERATOR_USER_LIST_MAX_PAGE_SIZE,
    OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_CREATOR,
    OPERATOR_USER_QUICK_FILTER_GUEST,
    OPERATOR_USER_QUICK_FILTER_LEARNER,
    OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D,
    OPERATOR_USER_QUICK_FILTER_PAID,
    OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_REGISTERED,
    OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D,
    OPERATOR_USER_ROLE_CREATOR,
    OPERATOR_USER_ROLE_LEARNER,
    OPERATOR_USER_ROLE_OPERATOR,
    OPERATOR_USER_ROLE_REGULAR,
    OPERATOR_USER_STATUS_CANCELLED,
    OPERATOR_USER_STATUS_PAID,
    OPERATOR_USER_STATUS_REGISTERED,
    OPERATOR_USER_STATUS_TRIAL,
    OPERATOR_USER_STATUS_UNREGISTERED,
)
from flaskr.service.shifu.admin_user_courses import (
    _load_operator_user_course_count_maps as load_operator_user_course_count_maps,
)
from flaskr.service.shifu.admin_user_courses import (
    _load_operator_user_course_maps as load_operator_user_course_maps,
)
from flaskr.service.shifu.admin_user_credits import (
    _load_operator_user_credit_summary_map as load_operator_user_credit_summary_map,
)
from flaskr.service.shifu.admin_user_profiles import (
    _build_learner_user_bid_subquery as build_learner_user_bid_subquery,
)
from flaskr.service.shifu.admin_user_profiles import (
    _build_operator_user_summary as build_operator_user_summary,
)
from flaskr.service.shifu.admin_user_profiles import (
    _build_recent_learning_active_user_bid_subquery as build_recent_learning_active_user_bid_subquery,
)
from flaskr.service.shifu.admin_user_profiles import (
    _build_recent_paid_user_bid_subquery as build_recent_paid_user_bid_subquery,
)
from flaskr.service.shifu.admin_user_profiles import (
    _build_registered_user_timestamp_subquery as build_registered_user_timestamp_subquery,
)
from flaskr.service.shifu.admin_user_profiles import (
    _find_matching_user_bids_by_identifier as find_matching_user_bids_by_identifier,
)
from flaskr.service.shifu.admin_user_profiles import (
    _load_learner_user_bids as load_learner_user_bids,
)
from flaskr.service.shifu.admin_user_profiles import (
    _load_operator_user_auth_credentials as load_operator_user_auth_credentials,
)
from flaskr.service.shifu.admin_user_profiles import (
    _load_operator_user_contact_map as load_operator_user_contact_map,
)
from flaskr.service.shifu.admin_user_profiles import (
    _load_operator_user_last_learning_map as load_operator_user_last_learning_map,
)
from flaskr.service.shifu.admin_user_profiles import (
    _load_operator_user_last_login_map as load_operator_user_last_login_map,
)
from flaskr.service.shifu.admin_user_profiles import (
    _load_operator_user_or_raise as load_operator_user_or_raise,
)
from flaskr.service.shifu.admin_user_profiles import (
    _load_operator_user_registration_source_map as load_operator_user_registration_source_map,
)
from flaskr.service.shifu.admin_user_profiles import (
    _load_operator_user_total_paid_amount_map as load_operator_user_total_paid_amount_map,
)
from flaskr.service.shifu.admin_user_profiles import (
    _resolve_operator_user_quick_filter as resolve_operator_user_quick_filter,
)
from flaskr.service.shifu.admin_user_profiles import (
    _resolve_recent_days_window as resolve_recent_days_window,
)

__all__ = [
    "OPERATOR_USER_LIST_MAX_PAGE_SIZE",
    "OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D",
    "OPERATOR_USER_QUICK_FILTER_CREATOR",
    "OPERATOR_USER_QUICK_FILTER_GUEST",
    "OPERATOR_USER_QUICK_FILTER_LEARNER",
    "OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D",
    "OPERATOR_USER_QUICK_FILTER_PAID",
    "OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D",
    "OPERATOR_USER_QUICK_FILTER_REGISTERED",
    "OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D",
    "OPERATOR_USER_ROLE_CREATOR",
    "OPERATOR_USER_ROLE_LEARNER",
    "OPERATOR_USER_ROLE_OPERATOR",
    "OPERATOR_USER_ROLE_REGULAR",
    "OPERATOR_USER_STATUS_CANCELLED",
    "OPERATOR_USER_STATUS_PAID",
    "OPERATOR_USER_STATUS_REGISTERED",
    "OPERATOR_USER_STATUS_TRIAL",
    "OPERATOR_USER_STATUS_UNREGISTERED",
    "build_learner_user_bid_subquery",
    "build_operator_user_summary",
    "build_recent_learning_active_user_bid_subquery",
    "build_recent_paid_user_bid_subquery",
    "build_registered_user_timestamp_subquery",
    "find_matching_user_bids_by_identifier",
    "load_learner_user_bids",
    "load_operator_user_auth_credentials",
    "load_operator_user_contact_map",
    "load_operator_user_course_count_maps",
    "load_operator_user_course_maps",
    "load_operator_user_credit_summary_map",
    "load_operator_user_last_learning_map",
    "load_operator_user_last_login_map",
    "load_operator_user_or_raise",
    "load_operator_user_registration_source_map",
    "load_operator_user_total_paid_amount_map",
    "resolve_operator_user_quick_filter",
    "resolve_recent_days_window",
]
