from flask import Flask

from flaskr.util.timezone import (
    format_with_app_timezone,
    serialize_with_app_timezone,
)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["TZ"] = "Asia/Shanghai"
    return app


def test_serialize_with_app_timezone_accepts_mysql_datetime_string() -> None:
    app = _make_app()

    assert (
        serialize_with_app_timezone(app, "2026-05-20 16:40:51", "UTC")
        == "2026-05-20T08:40:51+00:00"
    )
    assert (
        format_with_app_timezone(
            app,
            "2026-05-20 16:40:51",
            "%Y-%m-%d %H:%M:%S",
            "UTC",
        )
        == "2026-05-20 08:40:51"
    )


def test_serialize_with_app_timezone_accepts_offset_datetime_string() -> None:
    app = _make_app()

    assert (
        serialize_with_app_timezone(app, "2026-05-20T08:40:51Z", "Asia/Shanghai")
        == "2026-05-20T16:40:51+08:00"
    )
