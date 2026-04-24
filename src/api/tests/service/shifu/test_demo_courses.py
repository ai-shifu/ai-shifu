from __future__ import annotations

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.shifu.demo_courses import is_builtin_demo_shifu
from flaskr.service.shifu.models import PublishedShifu


@pytest.fixture
def demo_course_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_is_builtin_demo_shifu_matches_configured_demo_id(
    demo_course_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": (
            "demo-configured-1" if key == "DEMO_SHIFU_BID" else default
        ),
    )

    assert is_builtin_demo_shifu(demo_course_app, "demo-configured-1") is True


def test_is_builtin_demo_shifu_matches_system_title_fallback(
    demo_course_app: Flask,
) -> None:
    with demo_course_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="demo-fallback-1",
                title="AI-Shifu Creation Guide",
                created_user_bid="system",
            )
        )
        dao.db.session.commit()

    assert is_builtin_demo_shifu(demo_course_app, "demo-fallback-1") is True


def test_is_builtin_demo_shifu_excludes_other_system_courses(
    demo_course_app: Flask,
) -> None:
    with demo_course_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="system-course-1",
                title="Custom System Course",
                created_user_bid="system",
            )
        )
        dao.db.session.commit()

    assert is_builtin_demo_shifu(demo_course_app, "system-course-1") is False
