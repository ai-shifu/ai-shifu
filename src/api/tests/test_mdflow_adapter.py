from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from flaskr.dao import db
from flaskr.service.common.models import AppException
from flaskr.service.shifu.shifu_history_manager import (
    get_shifu_draft_meta,
    get_shifu_draft_revision,
)
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.shifu.shifu_mdflow_funcs import (
    cleanup_outline_history_versions,
    get_shifu_mdflow,
    get_shifu_mdflow_history,
    get_shifu_mdflow_history_version_detail,
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


def test_get_shifu_mdflow_history_version_detail_returns_content_and_user(app):
    shifu_bid = "shifu-mdflow-history-detail-1"
    outline_bid = "outline-mdflow-history-detail-1"
    user_bid = "user-mdflow-history-detail-1"
    content = "Line 1\nLine 2"

    with app.app_context():
        db.session.add(
            UserInfo(
                user_bid=user_bid,
                user_identify="detail-user@example.com",
                nickname="Detail User",
                deleted=0,
            )
        )
        db.session.commit()

    version_id = _add_outline_version(app, shifu_bid, outline_bid, content, user_bid, 0)

    detail = get_shifu_mdflow_history_version_detail(
        app,
        shifu_bid,
        outline_bid,
        version_id,
        timezone_name="UTC",
    )

    assert detail["version_id"] == version_id
    assert detail["content"] == content
    assert detail["updated_user_bid"] == user_bid
    assert detail["updated_user_name"] == "Detail User"
    assert isinstance(detail["updated_at"], str)
    assert re.match(r"^\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", detail["updated_at_display"])


def test_get_shifu_mdflow_history_version_detail_raises_not_found(app):
    with pytest.raises(AppException):
        get_shifu_mdflow_history_version_detail(
            app,
            "shifu-mdflow-history-detail-2",
            "outline-mdflow-history-detail-2",
            999999,
        )


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


def test_draft_meta_revision_stays_stable_for_metadata_only_updates(app):
    shifu_bid = "shifu-mdflow-meta-1"
    outline_bid = "outline-mdflow-meta-1"

    with app.app_context():
        first = DraftOutlineItem(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            title="Outline V1",
            position="01",
            content="Stable content",
            updated_user_bid="user-meta-1",
            created_user_bid="user-meta-1",
            updated_at=datetime.now(),
        )
        db.session.add(first)
        db.session.commit()
        first_id = int(first.id)

        second = first.clone()
        second.title = "Outline V2"
        second.position = "02"
        second.updated_user_bid = "user-meta-2"
        second.updated_at = datetime.now() + timedelta(minutes=1)
        db.session.add(second)
        db.session.commit()

    revision = get_shifu_draft_revision(app, shifu_bid, outline_bid)
    meta = get_shifu_draft_meta(app, shifu_bid, outline_bid)

    assert revision == first_id
    assert meta["revision"] == first_id
    assert meta["updated_user"] is not None
    assert meta["updated_user"]["user_bid"] == "user-meta-1"


def test_save_shifu_mdflow_conflicts_when_outline_deleted(app):
    shifu_bid = "shifu-mdflow-delete-1"
    outline_bid = "outline-mdflow-delete-1"
    active_revision = _add_outline_version(
        app, shifu_bid, outline_bid, "Current", "user-delete-1", 0
    )

    with app.app_context():
        latest = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.shifu_bid == shifu_bid,
                DraftOutlineItem.outline_item_bid == outline_bid,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        assert latest is not None

        deleted_version = latest.clone()
        deleted_version.deleted = 1
        deleted_version.updated_user_bid = "user-delete-1"
        deleted_version.updated_at = datetime.now() + timedelta(minutes=1)
        db.session.add(deleted_version)
        db.session.commit()
        deleted_revision = int(deleted_version.id)

    assert get_shifu_draft_revision(app, shifu_bid, outline_bid) == deleted_revision

    result = save_shifu_mdflow(
        app,
        "user-delete-1",
        shifu_bid,
        outline_bid,
        "Resurrected content",
        base_revision=active_revision,
    )
    assert result["conflict"] is True
    assert result["meta"]["revision"] == deleted_revision


def test_save_shifu_mdflow_returns_outline_revision_not_history_log(app, monkeypatch):
    shifu_bid = "shifu-mdflow-revision-1"
    outline_bid = "outline-mdflow-revision-1"

    base_id = _add_outline_version(
        app, shifu_bid, outline_bid, "Original", "user-revision-1", 0
    )

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
        lambda *_args, **_kwargs: 999999,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.cleanup_outline_history_versions",
        lambda *_args, **_kwargs: None,
    )

    result = save_shifu_mdflow(
        app,
        "user-revision-2",
        shifu_bid,
        outline_bid,
        "Updated content",
        base_revision=base_id,
    )
    current_revision = get_shifu_draft_revision(app, shifu_bid, outline_bid)

    assert result["conflict"] is False
    assert result["new_revision"] == current_revision
    assert result["new_revision"] != 999999


def test_cleanup_outline_history_preserves_content_anchor_revision(app):
    shifu_bid = "shifu-mdflow-cleanup-1"
    outline_bid = "outline-mdflow-cleanup-1"

    _add_outline_version(app, shifu_bid, outline_bid, "A", "user-clean-1", 0)
    anchor_revision = _add_outline_version(
        app, shifu_bid, outline_bid, "B", "user-clean-1", 1
    )
    _add_outline_version(app, shifu_bid, outline_bid, "B", "user-clean-1", 2)
    latest_revision = _add_outline_version(
        app, shifu_bid, outline_bid, "B", "user-clean-1", 3
    )

    with app.app_context():
        cleanup_outline_history_versions(
            app,
            shifu_bid,
            outline_bid,
            keep_versions=1,
            keep_days=3650,
        )

    with app.app_context():
        active_ids = {
            int(item.id)
            for item in DraftOutlineItem.query.filter(
                DraftOutlineItem.shifu_bid == shifu_bid,
                DraftOutlineItem.outline_item_bid == outline_bid,
                DraftOutlineItem.deleted == 0,
            ).all()
        }

    assert latest_revision in active_ids
    assert anchor_revision in active_ids
    assert get_shifu_draft_revision(app, shifu_bid, outline_bid) == anchor_revision


def test_restore_shifu_mdflow_history_restores_content(app, monkeypatch):
    shifu_bid = "shifu-mdflow-restore-1"
    outline_bid = "outline-mdflow-restore-1"

    old_version_id = _add_outline_version(
        app, shifu_bid, outline_bid, "Old", "user-restore-1", 0
    )
    current_version_id = _add_outline_version(
        app, shifu_bid, outline_bid, "Current", "user-restore-1", 1
    )

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
        "flaskr.service.shifu.shifu_mdflow_funcs.cleanup_outline_history_versions",
        lambda *_args, **_kwargs: None,
    )

    result = restore_shifu_mdflow_history_version(
        app,
        "user-restore-2",
        shifu_bid,
        outline_bid,
        old_version_id,
        base_revision=current_version_id,
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


def test_restore_shifu_mdflow_history_deleted_outline_returns_deleted_flag(app):
    shifu_bid = "shifu-mdflow-restore-deleted-1"
    outline_bid = "outline-mdflow-restore-deleted-1"
    user_bid = "user-restore-deleted-1"

    _add_outline_version(app, shifu_bid, outline_bid, "Version 1", user_bid, 0)
    target_version_id = _add_outline_version(
        app, shifu_bid, outline_bid, "Version 2", user_bid, 1
    )

    with app.app_context():
        latest = (
            DraftOutlineItem.query.filter_by(
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        assert latest is not None
        deleted_snapshot = latest.clone()
        deleted_snapshot.deleted = 1
        deleted_snapshot.updated_user_bid = user_bid
        db.session.add(deleted_snapshot)
        db.session.commit()

    result = restore_shifu_mdflow_history_version(
        app,
        user_bid,
        shifu_bid,
        outline_bid,
        target_version_id,
        base_revision=target_version_id,
    )
    assert result["lesson_deleted"] is True
    assert result["restored"] is False
