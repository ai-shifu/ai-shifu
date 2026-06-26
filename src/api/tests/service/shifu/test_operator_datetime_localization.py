"""Operator admin datetimes are localized server-side from the request timezone.

The operator route guard stores the browser timezone on ``flask.g`` and the
serialization helpers read it; absent a timezone they fall back to UTC (``Z``).
"""

from datetime import datetime

from flask import g

from flaskr.service.order.admin import _format_admin_datetime
from flaskr.service.shifu.admin_operations.courses import (
    _format_operator_datetime,
)


def test_operator_datetime_localizes_to_request_timezone(app) -> None:
    dt = datetime(2026, 6, 25, 1, 0, 0)  # naive UTC (DB canonical)

    with app.test_request_context("/?timezone=Asia/Shanghai"):
        g.operator_timezone = "Asia/Shanghai"
        assert _format_admin_datetime(dt) == "2026-06-25T09:00:00+08:00"
        assert _format_operator_datetime(dt) == "2026-06-25T09:00:00+08:00"


def test_operator_datetime_falls_back_to_utc(app) -> None:
    dt = datetime(2026, 6, 25, 1, 0, 0)

    with app.test_request_context("/"):
        # No timezone captured -> UTC, serialized with a trailing Z.
        assert _format_admin_datetime(dt) == "2026-06-25T01:00:00Z"
        assert _format_operator_datetime(dt) == "2026-06-25T01:00:00Z"
