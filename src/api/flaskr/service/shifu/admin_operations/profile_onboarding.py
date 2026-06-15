from __future__ import annotations

from typing import Any

from flask import Flask

from flaskr.service.common.profile_onboarding import (
    get_profile_onboarding_config,
    update_profile_onboarding_config,
)


def get_operator_profile_onboarding_config(app: Flask) -> dict[str, Any]:
    return get_profile_onboarding_config()


def update_operator_profile_onboarding_config(
    app: Flask,
    *,
    payload: dict[str, Any],
    operator_user_bid: str,
) -> dict[str, Any]:
    return update_profile_onboarding_config(
        app,
        payload=payload,
        operator_user_bid=operator_user_bid,
    )
