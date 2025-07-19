from datetime import datetime
import pytz
from flask import Flask


def get_now_time(app: Flask):
    timezone_str = app.config.get("DEFAULT_TIMEZONE", "Asia/Shanghai")
    tz = pytz.timezone(timezone_str)
    return datetime.now(tz)
