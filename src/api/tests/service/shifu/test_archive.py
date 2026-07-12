from datetime import datetime
from decimal import Decimal

import pytest

import flaskr.dao as dao
from flaskr.service.common.models import AppException


def _get_models():
    from flaskr.service.shifu.models import DraftShifu, ShifuUserArchive

    return DraftShifu, ShifuUserArchive


def _get_archive_funcs():
    from flaskr.service.shifu import shifu_draft_funcs

    return shifu_draft_funcs.archive_shifu, shifu_draft_funcs.unarchive_shifu


def _get_draft_module():
    from flaskr.service.shifu import shifu_draft_funcs

    return shifu_draft_funcs


def _seed_shifu(app, shifu_bid: str, owner_bid: str):
    """Create draft shifu row and clear archive state for testing."""
    with app.app_context():
        DraftShifu, ShifuUserArchive = _get_models()
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
    from flaskr.service.shifu.models import ShifuCourseSlug

    shifu_bid = "test-archive-toggle"
    owner_bid = "owner-123"
    course_slug = "archive-stable-course-link"
    _seed_shifu(app, shifu_bid, owner_bid)
    with app.app_context():
        original_binding = ShifuCourseSlug(
            shifu_bid=shifu_bid,
            slug=course_slug,
            version=1,
            is_current=1,
            generation_source="llm",
        )
        dao.db.session.add(original_binding)
        dao.db.session.commit()
        original_binding_state = (
            original_binding.id,
            original_binding.slug,
            original_binding.version,
            original_binding.is_current,
            original_binding.generation_source,
            original_binding.created_at,
            original_binding.retired_at,
        )

    monkeypatch.setattr(
        "flaskr.service.shifu.slug.prepare_course_slug",
        lambda *_args, **_kwargs: pytest.fail(
            "archive lifecycle must not regenerate the course slug"
        ),
    )

    archived_at = datetime(2026, 4, 21, 0, 0, 0)
    unarchived_at = datetime(2026, 4, 22, 0, 0, 0)
    draft_module = _get_draft_module()
    monkeypatch.setattr(draft_module, "now_utc", lambda: archived_at)

    archive_shifu, unarchive_shifu = _get_archive_funcs()
    archive_shifu(app, owner_bid, shifu_bid)

    with app.app_context():
        DraftShifu, ShifuUserArchive = _get_models()
        draft = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        archive = ShifuUserArchive.query.filter_by(
            shifu_bid=shifu_bid, user_bid=owner_bid
        ).first()
        slug_binding = ShifuCourseSlug.query.filter_by(
            shifu_bid=shifu_bid,
            is_current=1,
        ).one()

        assert draft is not None
        assert archive is not None
        assert archive.archived == 1
        assert archive.created_at == archived_at
        assert archive.updated_at == archived_at
        assert archive.archived_at == archived_at
        assert (
            slug_binding.id,
            slug_binding.slug,
            slug_binding.version,
            slug_binding.is_current,
            slug_binding.generation_source,
            slug_binding.created_at,
            slug_binding.retired_at,
        ) == original_binding_state

    monkeypatch.setattr(draft_module, "now_utc", lambda: unarchived_at)
    unarchive_shifu(app, owner_bid, shifu_bid)

    with app.app_context():
        DraftShifu, ShifuUserArchive = _get_models()
        draft = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        archive = ShifuUserArchive.query.filter_by(
            shifu_bid=shifu_bid, user_bid=owner_bid
        ).first()
        slug_bindings = ShifuCourseSlug.query.filter_by(shifu_bid=shifu_bid).all()

        assert draft is not None
        assert archive is not None
        assert archive.archived == 0
        assert archive.created_at == archived_at
        assert archive.updated_at == unarchived_at
        assert archive.archived_at is None
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
            for binding in slug_bindings
        ] == [original_binding_state]


def test_create_shifu_draft_uses_now_utc_for_persisted_timestamps(app, monkeypatch):
    created_at = datetime(2026, 4, 21, 0, 0, 0)
    owner_bid = "owner-create-utc"
    draft_module = _get_draft_module()
    DraftShifu, _ = _get_models()

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


def test_archive_requires_creator_permission(app):
    shifu_bid = "test-archive-permission"
    creator = "creator-1"
    _seed_shifu(app, shifu_bid, creator)
    archive_shifu, _ = _get_archive_funcs()

    with pytest.raises(AppException) as excinfo:
        archive_shifu(app, "intruder", shifu_bid)

    assert "permission" in excinfo.value.message.lower()
