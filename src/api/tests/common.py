import datetime
import json


def fmt(o):
    if isinstance(o, datetime.datetime) or isinstance(o, datetime.date):
        return o.isoformat()
    return o.__json__()


def print_json(o):
    print(json.dumps(o, default=fmt, ensure_ascii=False))
