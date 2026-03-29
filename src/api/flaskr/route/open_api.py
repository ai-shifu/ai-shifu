"""Open API routes for external partner course enrollment management."""

import hmac
from functools import wraps

from flask import Flask, request

from flaskr.route.common import bypass_token_validation, make_common_response
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.open_api import (
    open_api_grant_enrollment,
    open_api_query_enrollment,
    open_api_revoke_enrollment,
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
    course_id = str(payload.get("course_id", "")).strip()
    enroll_id = str(payload.get("enroll_id", "")).strip()
    enroll_id_type = str(payload.get("enroll_id_type", "phone")).strip().lower()

    if not course_id:
        raise_param_error("course_id")
    if not enroll_id:
        raise_param_error("enroll_id")
    if enroll_id_type not in ("phone", "email"):
        raise_param_error("enroll_id_type")

    return enroll_id, course_id, enroll_id_type


def register_open_api_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/enroll/query", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_enroll_query():
        enroll_id, course_id, enroll_id_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_query_enrollment(
            app, owner_bid, enroll_id, course_id, enroll_id_type
        )
        return make_common_response(result)

    @app.route(path_prefix + "/enroll/grant", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_enroll_grant():
        enroll_id, course_id, enroll_id_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_grant_enrollment(
            app, owner_bid, enroll_id, course_id, enroll_id_type
        )
        return make_common_response(result)

    @app.route(path_prefix + "/enroll/revoke", methods=["POST"])
    @bypass_token_validation
    @require_api_key
    def open_api_enroll_revoke():
        enroll_id, course_id, enroll_id_type = _extract_params()
        owner_bid = request.open_api_user_bid
        result = open_api_revoke_enrollment(
            app, owner_bid, enroll_id, course_id, enroll_id_type
        )
        return make_common_response(result)

    return app
