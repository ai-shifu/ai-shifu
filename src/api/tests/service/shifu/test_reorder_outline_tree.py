from __future__ import annotations

from decimal import Decimal

import pytest

from flaskr.dao import db
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu
from flaskr.service.shifu import shifu_outline_funcs
from flaskr.service.shifu.shifu_outline_funcs import (
    assert_outline_tree_publishable,
    reorder_outline_tree,
)


@pytest.fixture(autouse=True)
def _stub_reorder_side_effects(monkeypatch):
    monkeypatch.setattr(
        shifu_outline_funcs,
        "cleanup_outline_history_versions",
        lambda *args, **kwargs: None,
        raising=True,
    )
    monkeypatch.setattr(
        shifu_outline_funcs,
        "save_outline_tree_history",
        lambda *args, **kwargs: None,
        raising=True,
    )


def _seed_shifu(shifu_bid: str) -> None:
    db.session.add(
        DraftShifu(
            shifu_bid=shifu_bid,
            title="Outline Course",
            description="desc",
            avatar_res_bid="res",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal("0.3"),
            price=Decimal("0"),
            deleted=0,
            created_user_bid="creator-1",
            updated_user_bid="creator-1",
        )
    )
    db.session.commit()


def _add_outline(
    shifu_bid: str,
    outline_bid: str,
    position: str,
    *,
    parent_bid: str = "",
) -> None:
    db.session.add(
        DraftOutlineItem(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            title=outline_bid,
            position=position,
            parent_bid=parent_bid,
            prerequisite_item_bids="",
            llm="",
            llm_temperature=Decimal("0.3"),
            llm_system_prompt="",
            ask_enabled_status=5101,
            ask_llm="",
            ask_llm_temperature=Decimal("0.3"),
            ask_llm_system_prompt="",
            deleted=0,
            created_user_bid="creator-1",
            updated_user_bid="creator-1",
        )
    )
    db.session.flush()


def _latest_outline_by_bid(shifu_bid: str) -> dict[str, DraftOutlineItem]:
    rows = (
        DraftOutlineItem.query.filter_by(shifu_bid=shifu_bid, deleted=0)
        .order_by(
            DraftOutlineItem.outline_item_bid.asc(),
            DraftOutlineItem.id.desc(),
        )
        .all()
    )
    latest_by_bid: dict[str, DraftOutlineItem] = {}
    for row in rows:
        latest_by_bid.setdefault(row.outline_item_bid, row)
    return latest_by_bid


def test_reorder_outline_tree_updates_parent_bid_for_cross_parent_move(app):
    shifu_bid = "shifu_reorder_parent_fix"
    with app.app_context():
        _seed_shifu(shifu_bid)
        _add_outline(shifu_bid, "chapter-1", "01")
        _add_outline(shifu_bid, "lesson-1", "0101", parent_bid="chapter-1")
        _add_outline(shifu_bid, "chapter-2", "02")
        _add_outline(shifu_bid, "lesson-2", "0201", parent_bid="chapter-2")
        db.session.commit()

        reorder_outline_tree(
            app,
            "creator-1",
            shifu_bid,
            [
                {"bid": "chapter-1", "children": []},
                {
                    "bid": "chapter-2",
                    "children": [
                        {"bid": "lesson-2", "children": []},
                        {"bid": "lesson-1", "children": []},
                    ],
                },
            ],
        )

        latest_by_bid = _latest_outline_by_bid(shifu_bid)

        assert latest_by_bid["lesson-1"].parent_bid == "chapter-2"
        assert latest_by_bid["lesson-1"].position == "0202"
        assert latest_by_bid["lesson-2"].parent_bid == "chapter-2"
        assert latest_by_bid["lesson-2"].position == "0201"
        assert_outline_tree_publishable(app, shifu_bid)


def test_reorder_outline_tree_updates_parent_bid_when_promoting_child_to_root(app):
    shifu_bid = "shifu_reorder_root_fix"
    with app.app_context():
        _seed_shifu(shifu_bid)
        _add_outline(shifu_bid, "chapter-1", "01")
        _add_outline(shifu_bid, "lesson-1", "0101", parent_bid="chapter-1")
        _add_outline(shifu_bid, "chapter-2", "02")
        db.session.commit()

        reorder_outline_tree(
            app,
            "creator-1",
            shifu_bid,
            [
                {"bid": "chapter-1", "children": []},
                {"bid": "chapter-2", "children": []},
                {"bid": "lesson-1", "children": []},
            ],
        )

        latest_by_bid = _latest_outline_by_bid(shifu_bid)

        assert latest_by_bid["lesson-1"].parent_bid == ""
        assert latest_by_bid["lesson-1"].position == "03"
        assert_outline_tree_publishable(app, shifu_bid)
