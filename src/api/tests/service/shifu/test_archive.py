from decimal import Decimal

import pytest

import flaskr.dao as dao
from flaskr.service.common.models import AppException


def _get_models():
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu

    return DraftShifu, PublishedShifu


def _get_archive_funcs():
    from flaskr.service.shifu import shifu_draft_funcs

    return shifu_draft_funcs.archive_shifu, shifu_draft_funcs.unarchive_shifu


def _seed_shifu(app, shifu_bid: str, owner_bid: str):
    """Create draft & published shifu rows for testing."""
    with app.app_context():
        DraftShifu, PublishedShifu = _get_models()
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        PublishedShifu.query.filter_by(shifu_bid=shifu_bid).delete()

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
        published = PublishedShifu(
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
        dao.db.session.add(published)
        dao.db.session.commit()


def test_archive_then_unarchive_updates_both_tables(app):
    shifu_bid = "test-archive-toggle"
    owner_bid = "owner-123"
    _seed_shifu(app, shifu_bid, owner_bid)

    archive_shifu, unarchive_shifu = _get_archive_funcs()
    archive_shifu(app, owner_bid, shifu_bid)

    with app.app_context():
        DraftShifu, PublishedShifu = _get_models()
        draft = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        published = PublishedShifu.query.filter_by(shifu_bid=shifu_bid).first()

        assert draft.archived == 1
        assert draft.archived_at is not None
        assert published.archived == 1
        assert published.archived_at is not None

    unarchive_shifu(app, owner_bid, shifu_bid)

    with app.app_context():
        DraftShifu, PublishedShifu = _get_models()
        draft = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        published = PublishedShifu.query.filter_by(shifu_bid=shifu_bid).first()

        assert draft.archived == 0
        assert draft.archived_at is None
        assert published.archived == 0
        assert published.archived_at is None


def test_archive_requires_creator_permission(app):
    shifu_bid = "test-archive-permission"
    creator = "creator-1"
    _seed_shifu(app, shifu_bid, creator)
    archive_shifu, _ = _get_archive_funcs()

    with pytest.raises(AppException) as excinfo:
        archive_shifu(app, "intruder", shifu_bid)

    assert "noPermission" in excinfo.value.message
