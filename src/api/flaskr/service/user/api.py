"""Stable public entry points for cross-service user operations."""

from flaskr.service.user.auth.oauth_origins import is_allowed_oauth_origin
from flaskr.service.user.repository import UserAggregate, load_user_aggregate

__all__ = [
    "UserAggregate",
    "is_allowed_oauth_origin",
    "load_user_aggregate",
]
