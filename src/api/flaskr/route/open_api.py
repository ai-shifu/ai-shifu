"""Open API routes for external partner course order management."""

import hmac
from functools import wraps

from flask import Flask, request

from flaskr.route.common import bypass_token_validation, make_common_response
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.open_api import (
    open_api_grant_order,
    open_api_query_order,
    open_api_revoke_order,
)
from flaskr.service.user.models import UserInfo


def require_api_key(f):
    """Authenticate Open API requests via X-User-Uid + X-Api-Key headers."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        user_uid = request.headers.get("X-User-Uid", "").strip()
        api_key = request.headers.get("X-Api-Key", "").strip()

        if not user_uid or not api_key:
            raise_error("server.openapi.invalidApiKey")

        user = UserInfo.query.filter(
            UserInfo.user_bid == user_uid, UserInfo.deleted == 0
        ).first()
        if not user or not hmac.compare_digest(user.api_key, api_key):
            raise_error("server.openapi.invalidApiKey")

        request.open_api_user_bid = user_uid
        return f(*args, **kwargs)

    return wrapper


def _extract_params():
    """Extract and validate common request parameters."""
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    shifu_bid = str(payload.get("shifu_bid", "")).strip()
    user_identify = str(payload.get("user_identify", "")).strip()
    user_identify_type = str(payload.get("user_identify_type", "phone")).strip().lower()

    if not shifu_bid:
        raise_param_error("shifu_bid")
    if not user_identify:
        raise_param_error("user_identify")
    if user_identify_type not in ("phone", "email"):
        raise_param_error("user_identify_type")

    return shifu_bid, user_identify, user_identify_type


def register_open_api_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/order/query", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_order_query():
        shifu_bid, user_identify, user_identify_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_query_order(
            app, owner_bid, shifu_bid, user_identify, user_identify_type
        )
        return make_common_response(result)

    @app.route(path_prefix + "/order/grant", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_order_grant():
        shifu_bid, user_identify, user_identify_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_grant_order(
            app, owner_bid, shifu_bid, user_identify, user_identify_type
        )
        return make_common_response(result)

    @app.route(path_prefix + "/order/revoke", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_order_revoke():
        shifu_bid, user_identify, user_identify_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_revoke_order(
            app, owner_bid, shifu_bid, user_identify, user_identify_type
        )
        return make_common_response(result)

    return app
