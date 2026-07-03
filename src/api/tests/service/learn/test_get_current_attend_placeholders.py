"""Regression tests for the `_get_current_attend` ancestor-placeholder loop.

The loop walks the outline parent path (chapter -> unit -> lesson) and stages
one NOT_STARTED placeholder per outline node that has no progress record yet.
A pre-existing bug stamped every placeholder with the LEAF's
``outline_item_bid`` instead of the current node's own bid, so one call
created N duplicate leaf rows and no ancestor ever got a record of its own
(flagged in the B6-PR2 adversarial review; see
docs/exec-plans/active/learn-run-decomposition.md Decision Log).

Existing suites monkeypatch ``_get_current_attend`` outright, so these tests
drive the placeholder loop directly against a real session.
"""

from types import SimpleNamespace

import pytest
from flask import Flask

import flaskr.dao as dao
from flaskr.service.learn.context_v2 import RunScriptContextV2
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_NOT_STARTED
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_TRIAL
from flaskr.service.shifu.models import PublishedOutlineItem
from flaskr.service.shifu.shifu_history_manager import HistoryItem

USER_BID = "user-attend-00000000000000000001"
SHIFU_BID = "shifu-attend-0000000000000000001"
CHAPTER_BID = "chapter-attend-000000000000000001"
UNIT_BID = "unit-attend-00000000000000000001"
LEAF_BID = "leaf-attend-00000000000000000001"


@pytest.fixture
def attend_app() -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _build_struct() -> HistoryItem:
    leaf = HistoryItem(bid=LEAF_BID, id=4, type="outline", children=[])
    unit = HistoryItem(bid=UNIT_BID, id=3, type="outline", children=[leaf])
    chapter = HistoryItem(bid=CHAPTER_BID, id=2, type="outline", children=[unit])
    return HistoryItem(bid=SHIFU_BID, id=1, type="shifu", children=[chapter])


def _seed_leaf_outline_row() -> None:
    dao.db.session.add(
        PublishedOutlineItem(
            outline_item_bid=LEAF_BID,
            shifu_bid=SHIFU_BID,
            title="leaf lesson",
            type=UNIT_TYPE_VALUE_TRIAL,
            deleted=0,
        )
    )
    dao.db.session.commit()


def _make_context(app: Flask) -> RunScriptContextV2:
    # Bypass __init__: the placeholder loop only touches the attributes below.
    ctx = RunScriptContextV2.__new__(RunScriptContextV2)
    ctx.app = app
    ctx._user_info = SimpleNamespace(user_id=USER_BID, mobile="13800000000", email="")
    ctx._is_paid = True
    ctx._preview_mode = False
    ctx._outline_model = PublishedOutlineItem
    ctx._struct = _build_struct()
    # _recorder is a lazy property that builds RunRecorder(self.app) on
    # first use, so setting ctx.app above is enough.
    return ctx


def _rows_by_bid() -> dict[str, list[LearnProgressRecord]]:
    rows: dict[str, list[LearnProgressRecord]] = {}
    for row in LearnProgressRecord.query.filter(
        LearnProgressRecord.user_bid == USER_BID
    ).all():
        rows.setdefault(row.outline_item_bid, []).append(row)
    return rows


def test_placeholders_carry_each_ancestors_own_bid(attend_app):
    """One call creates exactly one row per outline node on the parent path,
    each stamped with that node's own bid — not N copies of the leaf's bid."""
    _seed_leaf_outline_row()
    ctx = _make_context(attend_app)

    attend_info = ctx._get_current_attend(LEAF_BID)

    assert attend_info.outline_item_bid == LEAF_BID
    rows = _rows_by_bid()
    assert sorted(rows.keys()) == sorted([CHAPTER_BID, UNIT_BID, LEAF_BID])
    for bid, bid_rows in rows.items():
        assert len(bid_rows) == 1, f"duplicate placeholder rows for {bid}"
        row = bid_rows[0]
        assert row.status == LEARN_STATUS_NOT_STARTED
        assert row.block_position == 0
        assert row.shifu_bid == SHIFU_BID
        assert row.progress_record_bid


def test_existing_ancestor_record_is_reused_not_duplicated(attend_app):
    """An ancestor that already has a non-reset record keeps it; only the
    missing nodes get placeholders."""
    _seed_leaf_outline_row()
    existing = LearnProgressRecord(
        progress_record_bid="progress-existing-0000000000001",
        shifu_bid=SHIFU_BID,
        outline_item_bid=CHAPTER_BID,
        user_bid=USER_BID,
        status=LEARN_STATUS_NOT_STARTED,
        block_position=0,
    )
    dao.db.session.add(existing)
    dao.db.session.commit()
    ctx = _make_context(attend_app)

    attend_info = ctx._get_current_attend(LEAF_BID)

    assert attend_info.outline_item_bid == LEAF_BID
    rows = _rows_by_bid()
    assert len(rows[CHAPTER_BID]) == 1
    assert rows[CHAPTER_BID][0].progress_record_bid == (
        "progress-existing-0000000000001"
    )
    assert len(rows[UNIT_BID]) == 1
    assert len(rows[LEAF_BID]) == 1


def test_second_call_returns_leaf_record_without_new_rows(attend_app):
    """A repeat call finds the leaf row via the fast path and stages nothing."""
    _seed_leaf_outline_row()
    ctx = _make_context(attend_app)
    first = ctx._get_current_attend(LEAF_BID)

    second = ctx._get_current_attend(LEAF_BID)

    assert second.progress_record_bid == first.progress_record_bid
    assert (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == USER_BID
        ).count()
        == 3
    )


def test_direct_ancestor_call_stamps_own_bids(attend_app):
    """The hot-path call shape: ``render_outline_updates`` calls
    ``_get_current_attend`` with ANCESTOR bids directly on chapter/unit
    transitions. Each created row must carry its own node's bid, and the
    returned record must be the requested node's — not the leaf's."""
    _seed_leaf_outline_row()
    dao.db.session.add(
        PublishedOutlineItem(
            outline_item_bid=UNIT_BID,
            shifu_bid=SHIFU_BID,
            title="unit",
            type=UNIT_TYPE_VALUE_TRIAL,
            deleted=0,
        )
    )
    dao.db.session.commit()
    ctx = _make_context(attend_app)

    attend_info = ctx._get_current_attend(UNIT_BID)

    assert attend_info.outline_item_bid == UNIT_BID
    rows = _rows_by_bid()
    # Parent path of the unit is shifu -> chapter -> unit: rows exist for
    # chapter and unit, each under its own bid; nothing under the leaf's.
    assert sorted(rows.keys()) == sorted([CHAPTER_BID, UNIT_BID])
    assert all(len(bid_rows) == 1 for bid_rows in rows.values())
