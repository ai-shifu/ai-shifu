"""Open API routes for external partner course authorization."""

from functools import wraps

from flask import Flask, request

from flaskr.route.common import bypass_token_validation, make_common_response
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.open_api import (
    open_api_grant_authorization,
    open_api_query_authorization,
    open_api_revoke_authorization,
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
            UserInfo.user_bid == user_uid,
            UserInfo.api_key == api_key,
            UserInfo.deleted == 0,
        ).first()

        if not user:
            raise_error("server.openapi.invalidApiKey")

        request.open_api_user_bid = user_uid
        return f(*args, **kwargs)

    return wrapper


def _extract_params():
    """Extract and validate common request parameters."""
    payload = request.get_json(silent=True) or {}
    phone = str(payload.get("phone", "")).strip()
    course_id = str(payload.get("course_id", "")).strip()
    contact_type = str(payload.get("contact_type", "phone")).strip().lower()

    if not phone:
        raise_param_error("phone")
    if not course_id:
        raise_param_error("course_id")
    if contact_type not in ("phone", "email"):
        raise_param_error("contact_type")

    return phone, course_id, contact_type


def register_open_api_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/authorization/query", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_query():
        phone, course_id, contact_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_query_authorization(
            app, owner_bid, phone, course_id, contact_type
        )
        return make_common_response(result)

    @app.route(path_prefix + "/authorization/grant", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_grant():
        phone, course_id, contact_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_grant_authorization(
            app, owner_bid, phone, course_id, contact_type
        )
        return make_common_response(result)

    @app.route(path_prefix + "/authorization/revoke", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_revoke():
        phone, course_id, contact_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_revoke_authorization(
            app, owner_bid, phone, course_id, contact_type
        )
        return make_common_response(result)

    return app
