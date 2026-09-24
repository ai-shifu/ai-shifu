"""Stable public entry points for cross-service user operations."""

from flaskr.service.user.account_cancellation import (
    cancel_account_subscription_renewals,
    cancel_user_account,
    get_account_cancellation_preview,
    get_account_cancellation_status,
    request_user_account_cancellation,
)
from flaskr.service.user.auth.oauth_origins import is_allowed_oauth_origin
from flaskr.service.user.operator_contact_change import change_operator_user_contact
from flaskr.service.user.repository import (
    UserAggregate,
    ensure_user_for_identifier,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    set_user_state,
    upsert_credential,
)
from flaskr.service.user.utils import (
    ensure_demo_course_permissions,
    load_existing_demo_shifu_ids,
    mark_creator_role_if_needed,
    run_creator_granted_post_auth,
)

__all__ = [
    "UserAggregate",
    "cancel_account_subscription_renewals",
    "cancel_user_account",
    "change_operator_user_contact",
    "ensure_demo_course_permissions",
    "ensure_user_for_identifier",
    "get_account_cancellation_preview",
    "get_account_cancellation_status",
    "is_allowed_oauth_origin",
    "load_existing_demo_shifu_ids",
    "load_user_aggregate",
    "load_user_aggregate_by_identifier",
    "mark_creator_role_if_needed",
    "request_user_account_cancellation",
    "run_creator_granted_post_auth",
    "set_user_state",
    "upsert_credential",
]
