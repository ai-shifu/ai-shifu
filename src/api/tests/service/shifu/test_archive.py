from datetime import datetime
from decimal import Decimal

import pytest

import flaskr.dao as dao
from flaskr.service.common.models import AppException


def _get_models():
    from flaskr.service.shifu.models import (
        DraftOutlineItem,
        DraftShifu,
        LogDraftStruct,
        ShifuUserArchive,
    )

    return DraftOutlineItem, DraftShifu, LogDraftStruct, ShifuUserArchive


def _get_archive_funcs():
    from flaskr.service.shifu import shifu_draft_funcs

    return shifu_draft_funcs.archive_shifu, shifu_draft_funcs.unarchive_shifu


def _get_draft_module():
    from flaskr.service.shifu import shifu_draft_funcs

    return shifu_draft_funcs


def _seed_shifu(app, shifu_bid: str, owner_bid: str):
    """Create draft shifu row and clear archive state for testing."""
    with app.app_context():
        _, DraftShifu, _, ShifuUserArchive = _get_models()
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        ShifuUserArchive.query.filter_by(
            shifu_bid=shifu_bid, user_bid=owner_bid
        ).delete()

        draft = DraftShifu(
            shifu_bid=shifu_bid,
            title="Test Shifu",
            description="desc",
            avatar_res_bid="res",
            keywords="test",
            llm="gpt",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("0"),
            created_user_bid=owner_bid,
            updated_user_bid=owner_bid,
        )
        dao.db.session.add(draft)
        dao.db.session.commit()


def test_archive_then_unarchive_updates_both_tables(app, monkeypatch):
    shifu_bid = "test-archive-toggle"
    owner_bid = "owner-123"
    _seed_shifu(app, shifu_bid, owner_bid)

    archived_at = datetime(2026, 4, 21, 0, 0, 0)
    unarchived_at = datetime(2026, 4, 22, 0, 0, 0)
    draft_module = _get_draft_module()
    monkeypatch.setattr(draft_module, "now_utc", lambda: archived_at)

    archive_shifu, unarchive_shifu = _get_archive_funcs()
    archive_shifu(app, owner_bid, shifu_bid)

    with app.app_context():
        _, DraftShifu, _, ShifuUserArchive = _get_models()
        draft = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        archive = ShifuUserArchive.query.filter_by(
            shifu_bid=shifu_bid, user_bid=owner_bid
        ).first()

        assert draft is not None
        assert archive is not None
        assert archive.archived == 1
        assert archive.created_at == archived_at
        assert archive.updated_at == archived_at
        assert archive.archived_at == archived_at

    monkeypatch.setattr(draft_module, "now_utc", lambda: unarchived_at)
    unarchive_shifu(app, owner_bid, shifu_bid)

    with app.app_context():
        _, DraftShifu, _, ShifuUserArchive = _get_models()
        draft = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        archive = ShifuUserArchive.query.filter_by(
            shifu_bid=shifu_bid, user_bid=owner_bid
        ).first()

        assert draft is not None
        assert archive is not None
        assert archive.archived == 0
        assert archive.created_at == archived_at
        assert archive.updated_at == unarchived_at
        assert archive.archived_at is None


def test_create_shifu_draft_uses_now_utc_for_persisted_timestamps(app, monkeypatch):
    created_at = datetime(2026, 4, 21, 0, 0, 0)
    owner_bid = "owner-create-utc"
    draft_module = _get_draft_module()
    _, DraftShifu, _, _ = _get_models()

    monkeypatch.setattr(draft_module, "now_utc", lambda: created_at)
    monkeypatch.setattr(draft_module, "generate_id", lambda _app: "shifu-create-utc")
    monkeypatch.setattr(
        draft_module,
        "check_text_with_risk_control",
        lambda *_args, **_kwargs: None,
    )
    from flaskr.service.shifu import shifu_outline_funcs

    monkeypatch.setattr(
        shifu_outline_funcs,
        "check_text_with_risk_control",
        lambda *_args, **_kwargs: None,
    )

    result = draft_module.create_shifu_draft(
        app,
        user_id=owner_bid,
        shifu_name="UTC Draft",
        shifu_description="description",
        shifu_image="res",
        shifu_keywords=["utc"],
        shifu_model="gpt-test",
        shifu_temperature=0.3,
        shifu_price=0,
    )

    with app.app_context():
        draft = DraftShifu.query.filter_by(shifu_bid=result.bid).first()

        assert draft is not None
        assert draft.created_at == created_at
        assert draft.updated_at == created_at


def test_create_shifu_draft_initializes_default_chapter_and_lesson(app, monkeypatch):
    owner_bid = "owner-default-outline"
    draft_module = _get_draft_module()
    DraftOutlineItem, _, LogDraftStruct, _ = _get_models()
    from flaskr.service.shifu.shifu_history_manager import HistoryItem

    generated_ids = iter(
        ["shifu-default-outline", "chapter-default-outline", "lesson-default-outline"]
    )

    monkeypatch.setattr(draft_module, "generate_id", lambda _app: next(generated_ids))
    monkeypatch.setattr(
        draft_module,
        "check_text_with_risk_control",
        lambda *_args, **_kwargs: None,
    )

    from flaskr.service.shifu import shifu_outline_funcs

    monkeypatch.setattr(
        shifu_outline_funcs, "generate_id", lambda _app: next(generated_ids)
    )

    result = draft_module.create_shifu_draft(
        app,
        user_id=owner_bid,
        shifu_name="Draft",
        shifu_description="description",
        shifu_image="res",
        shifu_keywords=["keyword"],
        shifu_model="gpt-test",
        shifu_temperature=0.3,
        shifu_price=0,
    )

    with app.app_context():
        outline_items = (
            DraftOutlineItem.query.filter_by(shifu_bid=result.bid, deleted=0)
            .order_by(DraftOutlineItem.position.asc())
            .all()
        )
        latest_struct = (
            LogDraftStruct.query.filter_by(shifu_bid=result.bid, deleted=0)
            .order_by(LogDraftStruct.id.desc())
            .first()
        )

    assert [item.outline_item_bid for item in outline_items] == [
        "chapter-default-outline",
        "lesson-default-outline",
    ]
    assert [item.position for item in outline_items] == ["01", "0101"]
    assert latest_struct is not None
    history = HistoryItem.from_json(latest_struct.struct)
    assert [child.bid for child in history.children] == ["chapter-default-outline"]
    assert [child.bid for child in history.children[0].children] == [
        "lesson-default-outline"
    ]


def test_default_outline_init_rebuilds_latest_struct_from_empty_history(
    app, monkeypatch
):
    owner_bid = "owner-empty-struct-rebuild"
    now_time = datetime(2026, 7, 13, 12, 0, 0)
    draft_module = _get_draft_module()
    DraftOutlineItem, DraftShifu, LogDraftStruct, _ = _get_models()
    from flaskr.service.shifu.shifu_history_manager import HistoryItem
    from flaskr.service.shifu.shifu_outline_funcs import (
        create_default_outlines_for_new_shifu,
    )

    generated_ids = iter(["chapter-empty-struct", "lesson-empty-struct"])
    monkeypatch.setattr(draft_module, "generate_id", lambda _app: "unused-shifu-id")

    from flaskr.service.shifu import shifu_outline_funcs

    monkeypatch.setattr(
        shifu_outline_funcs, "generate_id", lambda _app: next(generated_ids)
    )

    with app.app_context():
        shifu = DraftShifu(
            shifu_bid="shifu-empty-struct",
            title="Draft",
            description="desc",
            avatar_res_bid="res",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal("0.3"),
            price=Decimal("0"),
            deleted=0,
            created_user_bid=owner_bid,
            created_at=now_time,
            updated_user_bid=owner_bid,
            updated_at=now_time,
        )
        dao.db.session.add(shifu)
        dao.db.session.flush()

        empty_history = LogDraftStruct(
            struct_bid="empty-struct-bid",
            shifu_bid=shifu.shifu_bid,
            struct=HistoryItem(
                bid=shifu.shifu_bid,
                id=shifu.id,
                type="shifu",
                children=[],
            ).to_json(),
            created_user_bid=owner_bid,
            created_at=now_time,
            updated_user_bid=owner_bid,
            updated_at=now_time,
        )
        dao.db.session.add(empty_history)
        dao.db.session.flush()

        create_default_outlines_for_new_shifu(
            app=app,
            user_id=owner_bid,
            shifu_id=shifu.shifu_bid,
            chapter_name="Default Chapter",
            lesson_name="Default Lesson",
            now_time=now_time,
            shifu_db_id=shifu.id,
        )
        dao.db.session.commit()

        outline_items = (
            DraftOutlineItem.query.filter_by(shifu_bid=shifu.shifu_bid, deleted=0)
            .order_by(DraftOutlineItem.position.asc())
            .all()
        )
        latest_struct = (
            LogDraftStruct.query.filter_by(shifu_bid=shifu.shifu_bid, deleted=0)
            .order_by(LogDraftStruct.id.desc())
            .first()
        )

    assert [item.outline_item_bid for item in outline_items] == [
        "chapter-empty-struct",
        "lesson-empty-struct",
    ]
    assert [item.position for item in outline_items] == ["01", "0101"]
    assert latest_struct is not None
    rebuilt_history = HistoryItem.from_json(latest_struct.struct)
    assert rebuilt_history.id == shifu.id
    assert [child.bid for child in rebuilt_history.children] == ["chapter-empty-struct"]
    assert [child.bid for child in rebuilt_history.children[0].children] == [
        "lesson-empty-struct"
    ]


def test_create_shifu_draft_skips_risk_check_for_default_outline_content(
    app, monkeypatch
):
    owner_bid = "owner-skip-default-outline-risk"
    draft_module = _get_draft_module()

    draft_risk_calls = []

    monkeypatch.setattr(draft_module, "generate_id", lambda _app: "shifu-risk-skip")

    def fake_draft_risk(*args, **kwargs):
        draft_risk_calls.append((args, kwargs))

    monkeypatch.setattr(
        draft_module,
        "check_text_with_risk_control",
        fake_draft_risk,
    )

    from flaskr.service.shifu import shifu_outline_funcs

    def fail_outline_risk(*_args, **_kwargs):
        raise AssertionError("default outline content should not trigger risk check")

    monkeypatch.setattr(
        shifu_outline_funcs,
        "check_text_with_risk_control",
        fail_outline_risk,
    )

    result = draft_module.create_shifu_draft(
        app,
        user_id=owner_bid,
        shifu_name="Draft",
        shifu_description="description",
        shifu_image="res",
        shifu_keywords=["keyword"],
        shifu_model="gpt-test",
        shifu_temperature=0.3,
        shifu_price=0,
    )

    assert result.bid == "shifu-risk-skip"
    assert len(draft_risk_calls) == 1


def test_create_shifu_draft_raises_when_default_outline_init_fails(app, monkeypatch):
    owner_bid = "owner-outline-init-fail"
    draft_module = _get_draft_module()

    monkeypatch.setattr(draft_module, "generate_id", lambda _app: "shifu-outline-fail")
    monkeypatch.setattr(
        draft_module,
        "check_text_with_risk_control",
        lambda *_args, **_kwargs: None,
    )

    def fail_default_outlines(*_args, **_kwargs):
        raise AppException("outline init failed")

    monkeypatch.setattr(
        draft_module,
        "create_default_outlines_for_new_shifu",
        fail_default_outlines,
    )

    with pytest.raises(AppException):
        draft_module.create_shifu_draft(
            app,
            user_id=owner_bid,
            shifu_name="Draft",
            shifu_description="description",
            shifu_image="res",
            shifu_keywords=["keyword"],
            shifu_model="gpt-test",
            shifu_temperature=0.3,
            shifu_price=0,
        )


def test_archive_requires_creator_permission(app):
    shifu_bid = "test-archive-permission"
    creator = "creator-1"
    _seed_shifu(app, shifu_bid, creator)
    archive_shifu, _ = _get_archive_funcs()

    with pytest.raises(AppException) as excinfo:
        archive_shifu(app, "intruder", shifu_bid)

    assert "permission" in excinfo.value.message.lower()
