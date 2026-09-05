"""Shared HTTP response and route-access primitives."""

from __future__ import annotations

import datetime
import decimal
import json
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from flask import Flask, Response, current_app, request
from werkzeug.exceptions import RequestEntityTooLarge

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")

by_pass_login_func = [
    "flasgger.apispec_1",
    "flasgger.apidocs",
    "flasgger.static",
    "login",
    "invoke",
    "update_lesson",
]


def sensitive_body(*, max_bytes: int) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Omit a route's bodies from logs and bound parsing before authentication."""

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        func._sensitive_body_max_bytes = max_bytes
        return func

    return decorate


def get_sensitive_body_limit() -> int | None:
    """Resolve the matched endpoint's opt-in body policy without reading input."""
    view = current_app.view_functions.get(request.endpoint)
    return getattr(view, "_sensitive_body_max_bytes", None)


def init_sensitive_body_policy(app: Flask) -> None:
    """Install body limits before authentication or other shared JSON parsing."""

    @app.before_request
    def limit_sensitive_request_body() -> None:
        max_bytes = get_sensitive_body_limit()
        if max_bytes is None:
            return
        configured_limit = request.max_content_length
        max_bytes = (
            min(max_bytes, configured_limit)
            if configured_limit is not None
            else max_bytes
        )
        if request.content_length is not None and request.content_length > max_bytes:
            raise RequestEntityTooLarge
        # Werkzeug may return a truncated stream at its limit without raising.
        # Read one bounded overflow byte for chunked bodies and cache accepted
        # input so auth/context parsing cannot consume it before the route.
        request.max_content_length = max_bytes + 1
        if len(request.get_data(cache=True)) > max_bytes:
            raise RequestEntityTooLarge

    @app.after_request
    def prevent_sensitive_body_caching(response: Response) -> Response:
        if get_sensitive_body_limit() is not None:
            response.headers["Cache-Control"] = "no-store"
        return response


def bypass_token_validation(func: Callable[P, R]) -> Callable[P, R]:
    """Mark a route as exempt from token validation."""
    by_pass_login_func.append(func.__name__)

    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> R:
        return func(*args, **kwargs)

    return wrapper


def fmt(o: object) -> object:
    """Serialize a value for the shared API response envelope."""
    if isinstance(o, datetime.datetime):
        # Single serialization choke point for datetimes returned by APIs.
        # Stored values are UTC (see now_utc()); treat naive values as UTC and
        # convert aware values to UTC, always emitting ISO 8601 with a 'Z'
        # suffix. Display-time timezone conversion is a pure frontend concern.
        if o.tzinfo is None:
            o = o.replace(tzinfo=datetime.UTC)
        return o.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")
    if isinstance(o, datetime.date):
        return o.isoformat()
    if isinstance(o, decimal.Decimal):
        return str(o)
    return o.__json__()


def make_common_response(data: object) -> str:
    """Build the common JSON response envelope."""
    if data is None:
        data = {}
    return json.dumps(
        {"code": 0, "message": "success", "data": data},
        default=fmt,
        ensure_ascii=False,
    )


__all__ = [
    "by_pass_login_func",
    "bypass_token_validation",
    "fmt",
    "get_sensitive_body_limit",
    "init_sensitive_body_policy",
    "make_common_response",
    "sensitive_body",
]
