"""Handle profile onboarding for course-administration operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.service.common.profile_onboarding import (
    get_profile_onboarding_config,
    update_profile_onboarding_config,
)

if TYPE_CHECKING:
    from flask import Flask


def get_operator_profile_onboarding_config(app: Flask) -> dict[str, Any]:
    """Return operator profile onboarding config."""
    _ = app
    return get_profile_onboarding_config()


def update_operator_profile_onboarding_config(
    app: Flask,
    *,
    payload: dict[str, Any],
    operator_user_bid: str,
) -> dict[str, Any]:
    """Update operator profile onboarding config."""
    return update_profile_onboarding_config(
        app,
        payload=payload,
        operator_user_bid=operator_user_bid,
    )
