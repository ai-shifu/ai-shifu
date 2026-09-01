"""Register shared API handlers and re-export HTTP response helpers."""

import traceback

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from flaskr.common.http import (
    by_pass_login_func,
    bypass_token_validation,
    fmt,
    make_common_response,
)
from flaskr.common.shifu_context import clear_shifu_context
from flaskr.i18n import _, _translations, clear_language, set_language
from flaskr.service.common import AppError

__all__ = [
    "by_pass_login_func",
    "bypass_token_validation",
    "fmt",
    "make_common_response",
    "register_common_handler",
]


def _resolve_supported_language(raw_language: str | None) -> str | None:
    normalized_language = str(raw_language or "").strip()
    if not normalized_language:
        return None

    normalized_language_lower = normalized_language.lower()
    for supported_language in _translations:
        if supported_language.lower() == normalized_language_lower:
            return supported_language

    for supported_language in _translations:
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


def register_common_handler(app: Flask) -> Flask:
    """Register the common routes on the Flask application."""

    @app.errorhandler(AppError)
    def handle_invalid_usage(error: AppError) -> Response:
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.errorhandler(HTTPException)
    def handle_invalid_http(error: HTTPException) -> Response:
        app.logger.info(error)
        response = jsonify({"code": error.code, "message": error.description})
        response.status_code = 200
        return response

    @app.errorhandler(Exception)
    def handle_invalid_exception(error: Exception) -> Response:
        del error
        app.logger.error(traceback.format_exc())
        language = _extract_request_language()
        if language:
            set_language(language)
        response = jsonify({"code": -1, "message": _("server.common.unexpectedError")})
        response.status_code = 200
        return response

    @app.teardown_request
    def teardown_shifu_context(exception: object) -> None:
        # Ensure shifu context does not leak between requests on the same worker thread
        del exception
        clear_shifu_context()
        clear_language()

    return app
