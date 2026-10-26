"""Regression cover for the draft-struct history written by outline batches.

``create_outlines_batch`` inserts every node inside a single transaction, and
each insert appends to the shifu draft struct through the real history
manager. The history manager re-reads the newest ``LogDraftStruct`` row before
every append, so that read must join the caller's session: a read on its own
nested app context sees only committed rows, which made a batch overwrite its
own earlier nodes and made a child fail with "Parent history node not found".

These tests deliberately do NOT stub ``save_new_outline_history`` - the point
is to exercise the real read-modify-write against the database.
"""

from __future__ import annotations

import pytest
from flaskr.dao import db
from flaskr.service.shifu import shifu_draft_funcs, shifu_outline_funcs
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.shifu.shifu_draft_funcs import create_shifu_draft
from flaskr.service.shifu.shifu_history_manager import HistoryItem, get_shifu_history
from flaskr.service.shifu.shifu_outline_funcs import (
    create_outline,
    create_outlines_batch,
)

USER_BID = "creator-history-batch"


@pytest.fixture(autouse=True)
def _skip_risk_check(monkeypatch: object) -> None:
    """Drop the external content check; these tests only cover history writes."""
    for module in (shifu_draft_funcs, shifu_outline_funcs):
        monkeypatch.setattr(
            module,
            "check_text_with_risk_control",
            lambda *_args, **_kwargs: None,
            raising=True,
        )


def _new_draft(app: object) -> str:
    draft = create_shifu_draft(app, USER_BID, "History Course", "", "")
    return draft.bid


def _outline_titles(shifu_bid: str) -> list[str]:
    """Return the live outline titles of a shifu, oldest row first."""
    return [
        row.title
        for row in DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.deleted == 0,
        )
        .order_by(DraftOutlineItem.id)
        .all()
    ]


def _history_names(app: object, shifu_bid: str) -> list[tuple[str, list[str]]]:
    """Return the history tree as (title, [child titles]) pairs, top level first."""
    titles = {
        row.outline_item_bid: row.title
        for row in DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.deleted == 0,
        ).all()
    }
    history = get_shifu_history(app, shifu_bid)
    return [
        (titles[node.bid], [titles[child.bid] for child in node.children])
        for node in history.children
    ]


def _assert_ids_match_rows(app: object, shifu_bid: str) -> None:
    """Every history node points at the row id of its outline."""
    row_ids = {
        row.outline_item_bid: row.id
        for row in DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.deleted == 0,
        ).all()
    }
    pending: list[HistoryItem] = list(get_shifu_history(app, shifu_bid).children)
    seen = 0
    while pending:
        node = pending.pop()
        assert node.bid in row_ids, f"history node {node.bid} has no outline row"
        assert node.id == row_ids[node.bid]
        seen += 1
        pending.extend(node.children)
    assert seen == len(row_ids)


def test_nested_batch_records_children_under_their_parent(app: object) -> None:
    """A child created in the same batch as its parent finds the parent node."""
    with app.app_context():
        shifu_bid = _new_draft(app)

        create_outlines_batch(
            app,
            USER_BID,
            shifu_bid,
            [
                {"name": "Chapter A", "children": [{"name": "A1"}, {"name": "A2"}]},
                {"name": "Chapter B", "children": [{"name": "B1"}]},
            ],
        )

        # The default chapter/lesson pair of a new draft comes first.
        assert _history_names(app, shifu_bid)[-2:] == [
            ("Chapter A", ["A1", "A2"]),
            ("Chapter B", ["B1"]),
        ]
        _assert_ids_match_rows(app, shifu_bid)


def test_flat_batch_keeps_every_sibling_in_history(app: object) -> None:
    """Siblings written in one transaction must not overwrite each other."""
    with app.app_context():
        shifu_bid = _new_draft(app)

        create_outlines_batch(
            app,
            USER_BID,
            shifu_bid,
            [{"name": "C1"}, {"name": "C2"}, {"name": "C3"}],
        )

        assert [name for name, _children in _history_names(app, shifu_bid)][-3:] == [
            "C1",
            "C2",
            "C3",
        ]
        _assert_ids_match_rows(app, shifu_bid)


def test_batch_under_existing_parent_appends_to_that_parent(app: object) -> None:
    """A batch nested under a previously committed outline lands under it."""
    with app.app_context():
        shifu_bid = _new_draft(app)
        chapter = create_outline(app, USER_BID, shifu_bid, "", "Chapter A", "", 0)

        create_outlines_batch(
            app,
            USER_BID,
            shifu_bid,
            [{"name": "L1"}, {"name": "L2"}],
            parent_id=chapter.bid,
        )

        assert _history_names(app, shifu_bid)[-1] == ("Chapter A", ["L1", "L2"])
        _assert_ids_match_rows(app, shifu_bid)


def test_batch_rollback_leaves_no_outline_and_no_history(
    app: object, monkeypatch: object
) -> None:
    """A batch that fails midway leaves neither outline rows nor history rows."""
    with app.app_context():
        shifu_bid = _new_draft(app)
        history_before = _history_names(app, shifu_bid)
        titles_before = _outline_titles(shifu_bid)

        original = shifu_outline_funcs.save_new_outline_history
        calls = {"count": 0}

        def _fail_on_second_node(*args: object, **kwargs: object) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                message = "history write failed"
                raise RuntimeError(message)
            original(*args, **kwargs)

        monkeypatch.setattr(
            shifu_outline_funcs,
            "save_new_outline_history",
            _fail_on_second_node,
            raising=True,
        )

        with pytest.raises(RuntimeError, match="history write failed"):
            create_outlines_batch(
                app,
                USER_BID,
                shifu_bid,
                [{"name": "Doomed", "children": [{"name": "Doomed child"}]}],
            )

        db.session.rollback()
        assert _outline_titles(shifu_bid) == titles_before
        assert _history_names(app, shifu_bid) == history_before
