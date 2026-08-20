from datetime import UTC, datetime

import pytz
from flask import Flask

# Sentinels for ordering and comparing the naive UTC timestamps stored in the
# database, used where a nullable column takes part in a sort key or a range
# check. They are naive on purpose: an aware sentinel raises `TypeError` as
# soon as it meets a stored value.
NAIVE_DATETIME_MIN = datetime.min  # noqa: DTZ901
NAIVE_DATETIME_MAX = datetime.max  # noqa: DTZ901


def now_utc() -> datetime:
    """Return the current UTC time as a naive datetime.

    The database stores UTC. Returning a naive (tz-unaware) value keeps the
    same semantics as ``datetime.utcnow()`` used elsewhere, so it can be
    compared with existing naive timestamps without raising. It is computed
    from ``timezone.utc`` so it does not depend on the process ``TZ`` setting.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_iso(value: datetime | None) -> str | None:
    """Serialize a datetime to a UTC ISO 8601 string with a ``Z`` suffix.

    Mirrors the API fmt sink (``flaskr/route/common.py``): stored values are
    UTC, so naive datetimes are treated as UTC and aware datetimes converted to
    UTC. Use this for payloads that are pre-serialized to strings before the
    response sink (bypassing it), so the frontend can convert to the viewer's
    timezone via ``formatAdminUtcDateTime``. Returns ``None`` for ``None``.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def get_now_time(app: Flask):
    timezone_str = app.config.get("DEFAULT_TIMEZONE", "Asia/Shanghai")
    tz = pytz.timezone(timezone_str)
    return datetime.now(tz)
