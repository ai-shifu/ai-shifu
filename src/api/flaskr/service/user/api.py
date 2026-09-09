"""Stable public entry points for cross-service user operations."""

from flaskr.service.user.account_cancellation import (
    cancel_account_subscription_renewals,
    cancel_user_account,
    get_account_cancellation_preview,
)
from flaskr.service.user.auth.oauth_origins import is_allowed_oauth_origin
from flaskr.service.user.repository import UserAggregate, load_user_aggregate

__all__ = [
    "UserAggregate",
    "cancel_account_subscription_renewals",
    "cancel_user_account",
    "get_account_cancellation_preview",
    "is_allowed_oauth_origin",
    "load_user_aggregate",
]
