"""Shared HTTP response and route-access primitives."""

from __future__ import annotations

import datetime
import decimal
import json
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

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
    "make_common_response",
]
