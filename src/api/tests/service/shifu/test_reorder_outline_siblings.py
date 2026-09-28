"""Protect atomic sibling-order merges, complete history, and rollback."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu import shifu_outline_funcs as outlines
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct
from flaskr.service.shifu.shifu_history_manager import (
    HistoryItem,
    get_shifu_history,
    save_outline_tree_history,
)
from sqlalchemy import update
from sqlalchemy.dialects import mysql

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def sibling_course(app: object) -> Iterator[SimpleNamespace]:
    with app.app_context():
        bid = uuid.uuid4().hex
        course = DraftShifu(shifu_bid=bid, title="Sibling reorder", deleted=0)
        db.session.add(course)
        db.session.flush()
        entries = [
            ("chapter-a", "", "01"),
            ("a1", "chapter-a", "0101"),
            ("a2", "chapter-a", "0102"),
            ("a-child", "a2", "010201"),
            ("chapter-b", "", "02"),
            ("b1", "chapter-b", "0201"),
            ("b2", "chapter-b", "0202"),
            ("sparse", "", "04"),
            ("sparse-child", "sparse", "0409"),
        ]
        rows = {}
        nodes = {}
        roots = []
        for item_bid, parent, position in entries:
            row = DraftOutlineItem(
                shifu_bid=bid,
                outline_item_bid=item_bid,
                parent_bid=parent,
                position=position,
                title=item_bid,
                content=f"Content for {item_bid}",
                llm_system_prompt="Keep teaching settings",
                hidden=1,
                type=401,
                deleted=0,
            )
            db.session.add(row)
            db.session.flush()
            rows[item_bid] = row
            node = HistoryItem(bid=item_bid, id=row.id, type="outline")
            nodes[item_bid] = node
            (nodes[parent].children if parent else roots).append(node)
        nodes["b1"].children = [HistoryItem(bid="legacy-block", id=17, type="block")]
        save_outline_tree_history(app, "teacher", bid, roots, shifu_id=course.id)
        db.session.commit()
        yield SimpleNamespace(bid=bid, root_id=course.id, rows=rows)
        db.session.rollback()
        for model in (DraftOutlineItem, LogDraftStruct, DraftShifu):
            model.query.filter_by(shifu_bid=bid).delete()
        db.session.commit()


def _latest(course: SimpleNamespace) -> dict[str, DraftOutlineItem]:
    rows = (
        DraftOutlineItem.query.filter_by(shifu_bid=course.bid)
        .order_by(DraftOutlineItem.id.desc())
        .all()
    )
    latest = {}
    for row in rows:
        latest.setdefault(row.outline_item_bid, row)
    return {bid: row for bid, row in latest.items() if row.deleted == 0}


def _history_nodes(root: HistoryItem) -> dict[str, HistoryItem]:
    found = {}
    pending = list(root.children)
    while pending:
        item = pending.pop()
        found[item.bid] = item
        pending.extend(item.children)
    return found


def _counts(course: SimpleNamespace) -> tuple[int, int]:
    return (
        DraftOutlineItem.query.filter_by(shifu_bid=course.bid).count(),
        LogDraftStruct.query.filter_by(shifu_bid=course.bid).count(),
    )


def test_two_groups_merge_without_overwriting_order_children_or_content(
    app: object,
    sibling_course: SimpleNamespace,
) -> None:
    course = sibling_course
    assert outlines.reorder_outline_siblings(app, "teacher", course.bid, ["b2", "b1"])
    after_b = _latest(course)
    b_versions = {bid: after_b[bid].id for bid in ("chapter-b", "b1", "b2")}
    assert outlines.reorder_outline_siblings(app, "teacher", course.bid, ["a2", "a1"])
    latest = _latest(course)
    assert {bid: latest[bid].id for bid in b_versions} == b_versions
    assert latest["a2"].position == "0101"
    assert latest["a-child"].position == "010101"
    assert latest["b2"].position == "0201"
    assert latest["b1"].position == "0202"
    assert latest["sparse"].position == "04"
    assert latest["sparse-child"].position == "0409"
    for bid, row in latest.items():
        original = course.rows[bid]
        assert row.content == original.content
        assert row.parent_bid == original.parent_bid
        assert row.llm_system_prompt == original.llm_system_prompt
        assert row.hidden == original.hidden
        assert row.type == original.type
    history = get_shifu_history(app, course.bid)
    nodes = _history_nodes(history)
    assert history.id == course.root_id
    assert set(nodes) == set(latest) | {"legacy-block"}
    assert [item.bid for item in nodes["chapter-a"].children] == ["a2", "a1"]
    assert [item.bid for item in nodes["chapter-b"].children] == ["b2", "b1"]
    assert nodes["b1"].children == [
        HistoryItem(bid="legacy-block", id=17, type="block")
    ]
    assert all(nodes[bid].id == row.id for bid, row in latest.items())


def test_root_reorder_preserves_all_subtrees(
    app: object, sibling_course: SimpleNamespace
) -> None:
    course = sibling_course
    outlines.reorder_outline_siblings(
        app, "teacher", course.bid, ["chapter-b", "sparse", "chapter-a"]
    )
    latest = _latest(course)
    assert latest["chapter-b"].position == "01"
    assert latest["b1"].position == "0101"
    assert latest["a-child"].position == "030201"
    history = get_shifu_history(app, course.bid)
    assert [item.bid for item in history.children] == [
        "chapter-b",
        "sparse",
        "chapter-a",
    ]
    assert set(_history_nodes(history)) == set(latest) | {"legacy-block"}


@pytest.mark.parametrize(
    "order",
    [
        None,
        "a1,a2",
        [],
        [""],
        [" "],
        [None],
        [1],
        [{}],
        ["a1", "a1"],
        ["a1"],
        ["a1", "missing"],
        ["a1", "b1"],
        ["a1", "a2", "b1"],
    ],
)
def test_invalid_or_partial_sibling_groups_write_nothing(
    app: object,
    sibling_course: SimpleNamespace,
    order: object,
) -> None:
    before = _counts(sibling_course)
    with pytest.raises(AppError) as error:
        outlines.reorder_outline_siblings(app, "teacher", sibling_course.bid, order)
    assert error.value.code == ERROR_CODE["server.common.paramsError"]
    assert _counts(sibling_course) == before


def test_tombstones_are_deduplicated_before_removing_deleted_nodes(
    app: object,
    sibling_course: SimpleNamespace,
) -> None:
    deleted = sibling_course.rows["a1"].clone()
    deleted.deleted = 1
    db.session.add(deleted)
    db.session.commit()
    before = _counts(sibling_course)
    with pytest.raises(AppError):
        outlines.reorder_outline_siblings(
            app, "teacher", sibling_course.bid, ["a2", "a1"]
        )
    assert _counts(sibling_course) == before
    outlines.reorder_outline_siblings(app, "teacher", sibling_course.bid, ["a2"])
    assert "a1" not in _history_nodes(get_shifu_history(app, sibling_course.bid))


@pytest.mark.parametrize("parent", ["absent-parent", "a-child"])
def test_invalid_parent_graph_is_rejected_without_losing_nodes(
    app: object,
    sibling_course: SimpleNamespace,
    parent: str,
) -> None:
    row = sibling_course.rows["a2"].clone()
    row.parent_bid = parent
    db.session.add(row)
    db.session.commit()
    before = _counts(sibling_course)
    with pytest.raises(AppError) as error:
        outlines.reorder_outline_siblings(
            app, "teacher", sibling_course.bid, ["b2", "b1"]
        )
    assert error.value.code == ERROR_CODE["server.shifu.outlineStructureBroken"]
    assert _counts(sibling_course) == before


def test_locking_reads_refresh_cached_outline_and_history_rows(
    app: object,
    sibling_course: SimpleNamespace,
) -> None:
    course = sibling_course
    cached = course.rows["a2"]
    old_content = cached.content
    log = LogDraftStruct.query.filter_by(shifu_bid=course.bid).first()
    history = HistoryItem.from_json(log.struct)
    history.id = 1234
    _history_nodes(history)["b1"].children[0].id = 99
    db.session.execute(
        update(DraftOutlineItem.__table__)
        .where(DraftOutlineItem.id == cached.id)
        .values(content="Latest saved content")
    )
    db.session.execute(
        update(LogDraftStruct.__table__)
        .where(LogDraftStruct.id == log.id)
        .values(struct=history.to_json())
    )
    assert cached.content == old_content
    outlines.reorder_outline_siblings(app, "teacher", course.bid, ["a2", "a1"])
    assert _latest(course)["a2"].content == "Latest saved content"
    saved = get_shifu_history(app, course.bid)
    assert saved.id == 1234
    assert _history_nodes(saved)["legacy-block"].id == 99


def test_late_history_failure_rolls_back_all_cloned_rows(
    app: object,
    sibling_course: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _counts(sibling_course)
    original = outlines.save_outline_tree_history

    def fail_after_history(*args: object, **kwargs: object) -> None:
        original(*args, **kwargs)
        message = "history failure after flush"
        raise RuntimeError(message)

    monkeypatch.setattr(outlines, "save_outline_tree_history", fail_after_history)
    with pytest.raises(RuntimeError, match="history failure after flush"):
        outlines.reorder_outline_siblings(
            app, "teacher", sibling_course.bid, ["a2", "a1"]
        )
    assert _counts(sibling_course) == before
    assert _latest(sibling_course)["a1"].position == "0101"


def test_current_reads_lock_direct_selects_without_snapshot_subqueries(
    app: object,
    sibling_course: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.orm import Query

    statements = []
    original = Query._iter

    def record_query(query: Query) -> object:
        statements.append(str(query.statement.compile(dialect=mysql.dialect())))
        return original(query)

    monkeypatch.setattr(Query, "_iter", record_query)
    outlines.reorder_outline_siblings(app, "teacher", sibling_course.bid, ["a2", "a1"])
    current = [sql for sql in statements if "FOR UPDATE" in sql]
    assert any("shifu_draft_shifus" in sql for sql in current)
    assert any("shifu_draft_outline_items" in sql for sql in current)
    assert any("shifu_log_draft_structs" in sql for sql in current)
    assert all("max(" not in sql.lower() for sql in current)
    outline_reads = [sql for sql in current if "shifu_draft_outline_items" in sql]
    assert len(outline_reads) == 2
    assert "content" not in outline_reads[0]
    assert "content" in outline_reads[1]
    assert " IN (" in outline_reads[1]
