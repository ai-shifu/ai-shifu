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


def get_now_time(app: Flask):
    timezone_str = app.config.get("DEFAULT_TIMEZONE", "Asia/Shanghai")
    tz = pytz.timezone(timezone_str)
    return datetime.now(tz)
