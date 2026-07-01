from datetime import datetime, timezone
import pytz
from flask import Flask


def now_utc() -> datetime:
    """Current UTC time as a naive datetime.

    The database stores UTC. Returning a naive (tz-unaware) value keeps the
    same semantics as ``datetime.utcnow()`` used elsewhere, so it can be
    compared with existing naive timestamps without raising. It is computed
    from ``timezone.utc`` so it does not depend on the process ``TZ`` setting.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def get_now_time(app: Flask):
    timezone_str = app.config.get("DEFAULT_TIMEZONE", "Asia/Shanghai")
    tz = pytz.timezone(timezone_str)
    return datetime.now(tz)
