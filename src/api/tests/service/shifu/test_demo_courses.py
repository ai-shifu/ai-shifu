from __future__ import annotations

import json

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.shifu.demo_courses import is_builtin_demo_shifu
from flaskr.service.shifu.models import PublishedShifu, ShifuCourseSlug


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


@pytest.mark.parametrize("existing_bid", [None, "existing-demo-course"])
def test_process_demo_course_routes_new_and_update_imports_through_slug_aware_path(
    demo_course_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    existing_bid: str | None,
) -> None:
    from flaskr.command import update_shifu_demo as demo_module

    imported: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    config_updates: list[tuple[str, str, str]] = []

    def fake_get_config(key: str, default=None):
        values = {
            "DEMO_SHIFU_BID": existing_bid,
            "DEMO_SHIFU_HASH": "stale-demo-hash" if existing_bid else None,
        }
        return values.get(key, default)

    def fake_import_shifu(app, shifu_bid, file_storage, user_id):
        imported.append(
            {
                "app": app,
                "shifu_bid": shifu_bid,
                "user_id": user_id,
                "filename": file_storage.filename,
                "has_content": bool(file_storage.read()),
            }
        )
        return shifu_bid or "new-demo-course"

    def fake_publish(app, user_id, shifu_bid, base_url, *, sync_summary):
        published.append(
            {
                "app": app,
                "user_id": user_id,
                "shifu_bid": shifu_bid,
                "base_url": base_url,
                "sync_summary": sync_summary,
            }
        )

    monkeypatch.setattr(demo_module, "get_config", fake_get_config)
    monkeypatch.setattr(demo_module, "import_shifu", fake_import_shifu)
    monkeypatch.setattr(demo_module, "publish_shifu_draft", fake_publish)
    monkeypatch.setattr(
        demo_module,
        "_upsert_config",
        lambda _app, key, value, remark: config_updates.append((key, value, remark)),
    )

    result = demo_module._process_demo_shifu(
        demo_course_app,
        "cn_demo.json",
        "DEMO_SHIFU_BID",
        "Demo BID",
        "DEMO_SHIFU_HASH",
        "Demo hash",
    )

    expected_bid = existing_bid or "new-demo-course"
    assert result == expected_bid
    assert imported == [
        {
            "app": demo_course_app,
            "shifu_bid": existing_bid,
            "user_id": "system",
            "filename": "cn_demo.json",
            "has_content": True,
        }
    ]
    assert published == [
        {
            "app": demo_course_app,
            "user_id": "system",
            "shifu_bid": expected_bid,
            "base_url": "",
            "sync_summary": True,
        }
    ]
    assert config_updates[0] == ("DEMO_SHIFU_BID", expected_bid, "Demo BID")
    assert config_updates[1][0] == "DEMO_SHIFU_HASH"
    assert len(config_updates[1][1]) == 64
    assert config_updates[1][2] == "Demo hash"


def test_process_demo_course_real_import_creates_slug_and_update_preserves_binding(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.command import update_shifu_demo as demo_module
    from flaskr.service.shifu import (
        shifu_import_export_funcs as import_module,
        shifu_publish_funcs as publish_module,
    )

    config_values: dict[str, str] = {}
    slug_model_titles: list[str] = []

    monkeypatch.setattr(
        demo_module,
        "get_config",
        lambda key, default=None: config_values.get(key, default),
    )
    monkeypatch.setattr(
        demo_module,
        "_upsert_config",
        lambda _app, key, value, _remark: config_values.__setitem__(key, value),
    )
    monkeypatch.setattr(
        import_module,
        "check_text_with_risk_control",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        publish_module,
        "_run_summary_with_error_handling",
        lambda *_args, **_kwargs: None,
    )

    def fake_slug_model(_app, **kwargs):
        slug_model_titles.append(kwargs["title"])
        return json.dumps({"slug": "integrated-demo-course-link"})

    monkeypatch.setattr(
        "flaskr.service.shifu.slug._invoke_slug_model",
        fake_slug_model,
    )

    first_bid = demo_module._process_demo_shifu(
        app,
        "cn_demo.json",
        "TEST_DEMO_SHIFU_BID",
        "Test demo BID",
        "TEST_DEMO_SHIFU_HASH",
        "Test demo hash",
    )

    with app.app_context():
        original_binding = ShifuCourseSlug.query.filter_by(
            shifu_bid=first_bid,
            is_current=1,
        ).one()
        original_binding_state = (
            original_binding.id,
            original_binding.slug,
            original_binding.version,
            original_binding.is_current,
            original_binding.generation_source,
            original_binding.created_at,
            original_binding.retired_at,
        )
        assert original_binding.slug == "integrated-demo-course-link"
        assert PublishedShifu.query.filter_by(
            shifu_bid=first_bid,
            deleted=0,
        ).one()

    config_values["TEST_DEMO_SHIFU_HASH"] = "stale-demo-hash"
    second_bid = demo_module._process_demo_shifu(
        app,
        "cn_demo.json",
        "TEST_DEMO_SHIFU_BID",
        "Test demo BID",
        "TEST_DEMO_SHIFU_HASH",
        "Test demo hash",
    )

    with app.app_context():
        bindings = ShifuCourseSlug.query.filter_by(shifu_bid=first_bid).all()
        assert second_bid == first_bid
        assert slug_model_titles == ["AI 师傅课程优化进阶"]
        assert [
            (
                binding.id,
                binding.slug,
                binding.version,
                binding.is_current,
                binding.generation_source,
                binding.created_at,
                binding.retired_at,
            )
            for binding in bindings
        ] == [original_binding_state]
        assert PublishedShifu.query.filter_by(
            shifu_bid=first_bid,
            deleted=0,
        ).one()
