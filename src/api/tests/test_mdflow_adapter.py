from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from flaskr.dao import db
from flaskr.service.common.models import AppException
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.shifu.shifu_mdflow_funcs import (
    get_shifu_mdflow,
    get_shifu_mdflow_history,
    parse_shifu_mdflow,
    restore_shifu_mdflow_history_version,
    save_shifu_mdflow,
)
from flaskr.service.user.models import UserInfo


def test_parse_shifu_mdflow_returns_variables(app):
    with app.app_context():
        outline = DraftOutlineItem(
            outline_item_bid="outline-mdflow-1",
            shifu_bid="shifu-mdflow-1",
            title="Outline Title",
            content="Hello {{name}}",
        )
        db.session.add(outline)
        db.session.commit()

    result = parse_shifu_mdflow(app, "shifu-mdflow-1", "outline-mdflow-1")
    assert "name" in result.variables
    assert result.blocks_count >= 1

    content = get_shifu_mdflow(app, "shifu-mdflow-1", "outline-mdflow-1")
    assert content == "Hello {{name}}"


def _add_outline_version(
    app,
    shifu_bid: str,
    outline_bid: str,
    content: str,
    updated_user_bid: str,
    minutes_offset: int,
) -> int:
    with app.app_context():
        item = DraftOutlineItem(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            title="outline",
            content=content,
            updated_user_bid=updated_user_bid,
            updated_at=datetime.now() + timedelta(minutes=minutes_offset),
            created_user_bid=updated_user_bid,
        )
        db.session.add(item)
        db.session.commit()
        return int(item.id)


def test_get_shifu_mdflow_history_includes_baseline_and_masks_user(app):
    shifu_bid = "shifu-mdflow-history-1"
    outline_bid = "outline-mdflow-history-1"
    user_1 = "user-mdflow-history-1"
    user_2 = "user-mdflow-history-2"

    with app.app_context():
        db.session.add(
            UserInfo(
                user_bid=user_1,
                user_identify="alice@example.com",
                nickname="Alice",
                deleted=0,
            )
        )
        db.session.add(
            UserInfo(
                user_bid=user_2,
                user_identify="13812345678",
                nickname="",
                deleted=0,
            )
        )
        db.session.commit()

    id_1 = _add_outline_version(app, shifu_bid, outline_bid, "A", user_1, 0)
    _add_outline_version(app, shifu_bid, outline_bid, "A", user_1, 1)
    id_3 = _add_outline_version(app, shifu_bid, outline_bid, "B", user_1, 2)
    _add_outline_version(app, shifu_bid, outline_bid, "B", user_1, 3)
    id_5 = _add_outline_version(app, shifu_bid, outline_bid, "C", user_2, 4)

    history = get_shifu_mdflow_history(app, shifu_bid, outline_bid, limit=100)
    assert [item["version_id"] for item in history["items"]] == [id_5, id_3, id_1]
    assert isinstance(history["items"][0]["updated_at"], str)
    assert re.match(
        r"^\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",
        history["items"][0]["updated_at_display"],
    )

    latest_user_name = history["items"][0]["updated_user_name"]
    assert latest_user_name != "13812345678"
    assert "****" in latest_user_name

    limited = get_shifu_mdflow_history(app, shifu_bid, outline_bid, limit=2)
    assert [item["version_id"] for item in limited["items"]] == [id_5, id_3]


def test_get_shifu_mdflow_history_uses_request_timezone(app):
    try:
        ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError:
        pytest.skip("Asia/Shanghai timezone is unavailable in test environment")

    shifu_bid = "shifu-mdflow-history-tz-1"
    outline_bid = "outline-mdflow-history-tz-1"

    with app.app_context():
        app_tz = ZoneInfo(app.config.get("TZ", "UTC"))
        item = DraftOutlineItem(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            title="outline",
            content="A",
            updated_user_bid="user-tz-1",
            updated_at=datetime(2026, 3, 3, 0, 0, 0, tzinfo=app_tz),
            created_user_bid="user-tz-1",
        )
        db.session.add(item)
        db.session.commit()

    history_utc = get_shifu_mdflow_history(
        app,
        shifu_bid,
        outline_bid,
        limit=100,
        timezone_name="UTC",
    )
    history_shanghai = get_shifu_mdflow_history(
        app,
        shifu_bid,
        outline_bid,
        limit=100,
        timezone_name="Asia/Shanghai",
    )

    expected_shanghai = datetime(2026, 3, 3, 0, 0, 0, tzinfo=app_tz).astimezone(
        ZoneInfo("Asia/Shanghai")
    )
    expected_utc = datetime(2026, 3, 3, 0, 0, 0, tzinfo=app_tz).astimezone(
        ZoneInfo("UTC")
    )

    assert history_shanghai["items"][0][
        "updated_at_display"
    ] == expected_shanghai.strftime("%m-%d %H:%M:%S")
    assert datetime.fromisoformat(history_shanghai["items"][0]["updated_at"]) == (
        expected_shanghai
    )
    assert history_utc["items"][0]["updated_at_display"] == expected_utc.strftime(
        "%m-%d %H:%M:%S"
    )
    assert datetime.fromisoformat(history_utc["items"][0]["updated_at"]) == expected_utc


def test_save_shifu_mdflow_rejects_outline_from_other_shifu(app):
    _add_outline_version(
        app,
        "shifu-idor-owner",
        "outline-idor-1",
        "Original",
        "user-idor-owner",
        0,
    )

    with pytest.raises(AppException):
        save_shifu_mdflow(
            app,
            "user-attacker",
            "shifu-idor-attacker",
            "outline-idor-1",
            "Tampered",
        )


def test_restore_shifu_mdflow_history_restores_content(app, monkeypatch):
    shifu_bid = "shifu-mdflow-restore-1"
    outline_bid = "outline-mdflow-restore-1"

    old_version_id = _add_outline_version(
        app, shifu_bid, outline_bid, "Old", "user-restore-1", 0
    )
    _add_outline_version(app, shifu_bid, outline_bid, "Current", "user-restore-1", 1)

    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.check_text_with_risk_control",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.get_profile_item_definition_list",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.add_profile_item_quick",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.save_outline_history",
        lambda _app, _user_id, _shifu_bid, _outline_bid, version_id, *_rest: int(
            version_id
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs._cleanup_outline_history_versions",
        lambda *_args, **_kwargs: None,
    )

    result = restore_shifu_mdflow_history_version(
        app,
        "user-restore-2",
        shifu_bid,
        outline_bid,
        old_version_id,
        base_revision=0,
    )
    assert result["restored"] is True
    assert isinstance(result["new_revision"], int)

    with app.app_context():
        latest = (
            DraftOutlineItem.query.filter_by(
                shifu_bid=shifu_bid, outline_item_bid=outline_bid
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        assert latest is not None
        assert latest.content == "Old"


def test_restore_shifu_mdflow_history_passes_base_revision(app, monkeypatch):
    shifu_bid = "shifu-mdflow-restore-2"
    outline_bid = "outline-mdflow-restore-2"

    old_version_id = _add_outline_version(
        app, shifu_bid, outline_bid, "Version 1", "user-restore-3", 0
    )
    _add_outline_version(app, shifu_bid, outline_bid, "Version 2", "user-restore-3", 1)

    captured: dict[str, int | None] = {"base_revision": None}

    def _fake_save(
        _app,
        _user_id,
        _shifu_bid,
        _outline_bid,
        _content,
        base_revision=None,
    ):
        captured["base_revision"] = base_revision
        return {"conflict": True, "meta": {"revision": 99}}

    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.save_shifu_mdflow",
        _fake_save,
    )

    result = restore_shifu_mdflow_history_version(
        app,
        "user-restore-4",
        shifu_bid,
        outline_bid,
        old_version_id,
        base_revision=42,
    )
    assert captured["base_revision"] == 42
    assert result["conflict"] is True
