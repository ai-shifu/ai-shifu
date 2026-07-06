import datetime
from functools import wraps
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from ..service.common import AppException
import json
import traceback
import decimal
from flaskr.common.shifu_context import clear_shifu_context
from flaskr.i18n import clear_language
from flaskr.i18n import set_language
from flaskr.i18n import _
from flaskr.i18n import _translations


by_pass_login_func = [
    "flasgger.apispec_1",
    "flasgger.apidocs",
    "flasgger.static",
    "login",
    "invoke",
    "update_lesson",
]


def _resolve_supported_language(raw_language: str | None) -> str | None:
    normalized_language = str(raw_language or "").strip()
    if not normalized_language:
        return None

    normalized_language_lower = normalized_language.lower()
    for supported_language in _translations.keys():
        if supported_language.lower() == normalized_language_lower:
            return supported_language

    for supported_language in _translations.keys():
        if supported_language.lower().startswith(normalized_language_lower):
            return supported_language

    return normalized_language


def _extract_request_language() -> str | None:
    raw_language = None
    if request.method.upper() in ("POST", "PUT", "PATCH") and request.is_json:
        payload = request.get_json(silent=True) or {}
        if isinstance(payload, dict):
            language = payload.get("language")
            if language:
                raw_language = str(language).strip()

    if not raw_language:
        accept_language = request.headers.get("Accept-Language", "")
        if accept_language:
            first_part = accept_language.split(",")[0].strip()
            if first_part:
                raw_language = first_part.split(";")[0].strip()

    return _resolve_supported_language(raw_language)


# 装饰器函数，用于跳过Token校验
def bypass_token_validation(func):
    by_pass_login_func.append(func.__name__)

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def register_common_handler(app: Flask) -> Flask:
    @app.errorhandler(AppException)
    def handle_invalid_usage(error: AppException):
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.errorhandler(HTTPException)
    def handle_invalid_http(error: HTTPException):
        app.logger.info(error)
        response = jsonify({"code": error.code, "message": error.description})
        response.status_code = 200
        return response

    @app.errorhandler(Exception)
    def handle_invalid_exception(error: Exception):
        app.logger.error(traceback.format_exc())
        language = _extract_request_language()
        if language:
            set_language(language)
        response = jsonify({"code": -1, "message": _("server.common.operationFailed")})
        response.status_code = 200
        return response

    @app.teardown_request
    def teardown_shifu_context(exception):
        # Ensure shifu context does not leak between requests on the same worker thread
        clear_shifu_context()
        clear_language()

    return app


def fmt(o):
    if isinstance(o, datetime.datetime):
        # Single serialization choke point for datetimes returned by APIs.
        # Stored values are UTC (see now_utc()); treat naive values as UTC and
        # convert aware values to UTC, always emitting ISO 8601 with a 'Z'
        # suffix. Display-time timezone conversion is a pure frontend concern.
        if o.tzinfo is None:
            o = o.replace(tzinfo=datetime.timezone.utc)
        return o.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    elif isinstance(o, datetime.date):
        return o.isoformat()
    elif isinstance(o, decimal.Decimal):
        return str(o)
    else:
        return o.__json__()


def make_common_response(data):
    if data is None:
        data = {}
    response = json.dumps(
        {"code": 0, "message": "success", "data": data}, default=fmt, ensure_ascii=False
    )
    return response
