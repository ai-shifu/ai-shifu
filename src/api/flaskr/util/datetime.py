from datetime import datetime
import pytz
from flask import Flask


def get_now_time(app: Flask):
    bj_time = pytz.timezone("Asia/Shanghai")
    return datetime.now(bj_time)
