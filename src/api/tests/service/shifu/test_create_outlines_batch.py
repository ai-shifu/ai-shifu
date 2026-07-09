"""Tests for collision-free outline position allocation.

Regression cover for the production error where a brand-new course became
unpublishable because concurrent single-create requests each read the same
sibling snapshot and allocated the *same* ``position`` (e.g. eight chapters all
at ``02``), tripping ``assert_outline_tree_publishable``.

``create_outlines_batch`` allocates positions sequentially inside one locked
transaction, so a batch of siblings can never collide. The per-shifu ``FOR
UPDATE`` lock is a no-op on SQLite, so these tests assert the observable
position-allocation behavior rather than lock contention.
"""

from __future__ import annotations

import pytest

from flaskr.dao import db
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu
from flaskr.service.shifu import shifu_outline_funcs
from flaskr.service.shifu.shifu_outline_funcs import (
    assert_outline_tree_publishable,
    create_outline,
    create_outlines_batch,
)


@pytest.fixture(autouse=True)
def _isolate_side_effects(monkeypatch):
    """Drop the external risk check and history machinery: these tests only
    exercise position allocation and publishability."""
    monkeypatch.setattr(
        shifu_outline_funcs,
        "check_text_with_risk_control",
        lambda *args, **kwargs: None,
        raising=True,
    )
    monkeypatch.setattr(
        shifu_outline_funcs,
        "save_new_outline_history",
        lambda *args, **kwargs: None,
        raising=True,
    )


def _seed_shifu(shifu_bid: str) -> None:
    shifu = DraftShifu(
        shifu_bid=shifu_bid,
        title="Batch Course",
        created_user_bid="creator-1",
        updated_user_bid="creator-1",
        deleted=0,
    )
    db.session.add(shifu)
    db.session.commit()


def _positions(shifu_bid: str) -> list[str]:
    rows = (
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.deleted == 0,
        )
        .order_by(DraftOutlineItem.id)
        .all()
    )
    return [r.position for r in rows]


def test_batch_assigns_unique_sequential_positions(app):
    shifu_bid = "shifu_batch_1"
    with app.app_context():
        _seed_shifu(shifu_bid)

        result = create_outlines_batch(
            app,
            "creator-1",
            shifu_bid,
            [
                {"name": "Chapter A", "children": [{"name": "A1"}, {"name": "A2"}]},
                {"name": "Chapter B", "children": [{"name": "B1"}]},
                {"name": "Chapter C"},
            ],
        )

        # Top-level chapters get distinct incrementing positions.
        assert [n.position for n in result] == ["01", "02", "03"]
        # Children are numbered within their own parent.
        assert [c.position for c in result[0].children] == ["0101", "0102"]
        assert [c.position for c in result[1].children] == ["0201"]
        assert result[2].children == []

        # No two live nodes share a position -> the course is publishable.
        all_positions = _positions(shifu_bid)
        assert len(all_positions) == len(set(all_positions)) == 6
        assert_outline_tree_publishable(app, shifu_bid)


def test_batch_of_many_siblings_never_collides(app):
    shifu_bid = "shifu_batch_many"
    with app.app_context():
        _seed_shifu(shifu_bid)

        create_outlines_batch(
            app,
            "creator-1",
            shifu_bid,
            [{"name": f"Chapter {i}"} for i in range(8)],
        )

        positions = _positions(shifu_bid)
        assert positions == ["01", "02", "03", "04", "05", "06", "07", "08"]
        assert_outline_tree_publishable(app, shifu_bid)


def test_batch_nested_under_existing_parent(app):
    shifu_bid = "shifu_batch_parent"
    with app.app_context():
        _seed_shifu(shifu_bid)
        chapter = create_outline(app, "creator-1", shifu_bid, "", "Chapter A", "", 0)

        lessons = create_outlines_batch(
            app,
            "creator-1",
            shifu_bid,
            [{"name": "L1"}, {"name": "L2"}, {"name": "L3"}],
            parent_id=chapter.bid,
        )

        assert [n.position for n in lessons] == ["0101", "0102", "0103"]
        assert_outline_tree_publishable(app, shifu_bid)


def test_sequential_single_creates_still_increment(app):
    shifu_bid = "shifu_single_seq"
    with app.app_context():
        _seed_shifu(shifu_bid)
        first = create_outline(app, "creator-1", shifu_bid, "", "One", "", 0)
        second = create_outline(app, "creator-1", shifu_bid, "", "Two", "", 0)
        third = create_outline(app, "creator-1", shifu_bid, "", "Three", "", 0)

        assert [first.position, second.position, third.position] == ["01", "02", "03"]
        assert_outline_tree_publishable(app, shifu_bid)


def test_batch_rejects_empty_payload(app):
    shifu_bid = "shifu_batch_empty"
    with app.app_context():
        _seed_shifu(shifu_bid)
        with pytest.raises(AppException) as exc_info:
            create_outlines_batch(app, "creator-1", shifu_bid, [])
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
