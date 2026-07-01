"""Tests for outline tree building / publish validation.

Covers the regression behind the production error
``Parent node not found for position: 0201``: an orphaned outline node (its
parent position was deleted) must not silently vanish, and a structurally
un-publishable outline (two live nodes colliding on the same position) must be
blocked with a clear error instead of shipping a broken course.
"""

import pytest

from flaskr.dao import db
from flaskr.service.common.models import AppException
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.shifu.shifu_outline_funcs import (
    build_outline_tree,
    assert_outline_tree_publishable,
)


def _mk_item(shifu_bid, bid, position, parent_bid=""):
    item = DraftOutlineItem()
    item.outline_item_bid = bid
    item.shifu_bid = shifu_bid
    item.title = f"node-{bid}"
    item.position = position
    item.parent_bid = parent_bid
    item.deleted = 0
    db.session.add(item)
    return item


def test_build_outline_tree_lifts_orphan_to_root(app):
    """An orphan whose parent position is missing is attached at root, and its
    own subtree stays attached to it — nothing is dropped."""
    shifu_bid = "shifu_orphan_1"
    with app.app_context():
        _mk_item(shifu_bid, "root1", "01")
        _mk_item(shifu_bid, "child1", "0101", parent_bid="root1")
        # Orphan: position 0201, but parent position 02 does not exist.
        _mk_item(shifu_bid, "orphan", "0201", parent_bid="dead_parent")
        _mk_item(shifu_bid, "orphan_child", "020101", parent_bid="orphan")
        db.session.commit()

        tree = build_outline_tree(app, shifu_bid)

        roots = {n.outline_id for n in tree}
        # Both the real root and the lifted orphan appear at the top level.
        assert roots == {"root1", "orphan"}

        orphan_node = next(n for n in tree if n.outline_id == "orphan")
        # The orphan keeps its own child rather than losing the subtree.
        assert [c.outline_id for c in orphan_node.children] == ["orphan_child"]


def test_build_outline_tree_handles_empty_position_without_cycle(app):
    """A degenerate empty position must not become its own child (which would
    later blow up get_outline_tree_dto with RecursionError). It is lifted to
    the root level like any other orphan."""
    shifu_bid = "shifu_empty_pos_1"
    with app.app_context():
        _mk_item(shifu_bid, "root1", "01")
        # Empty position is the column default; treat it as an orphan, not a
        # self-parent.
        _mk_item(shifu_bid, "broken", "")
        db.session.commit()

        tree = build_outline_tree(app, shifu_bid)

        broken_node = next(n for n in tree if n.outline_id == "broken")
        # The node is at the root and is NOT a child of itself.
        assert broken_node in tree
        assert broken_node not in broken_node.children

        # Rendering the tree must terminate (no self-cycle -> no RecursionError).
        from flaskr.service.shifu.shifu_outline_funcs import get_outline_tree_dto

        dtos = get_outline_tree_dto(tree)
        assert {d.bid for d in dtos} == {"root1", "broken"}


def test_assert_publishable_passes_when_no_collision(app):
    """Orphans alone are tolerated (self-healed); publish is not blocked."""
    shifu_bid = "shifu_orphan_2"
    with app.app_context():
        _mk_item(shifu_bid, "root1", "01")
        _mk_item(shifu_bid, "orphan", "0201", parent_bid="dead_parent")
        db.session.commit()

        # Should not raise.
        assert_outline_tree_publishable(app, shifu_bid)


def test_assert_publishable_raises_on_position_collision(app):
    """Two live nodes sharing a position cannot be reconciled -> block publish."""
    shifu_bid = "shifu_collision_1"
    with app.app_context():
        _mk_item(shifu_bid, "root1", "01")
        _mk_item(shifu_bid, "a", "0101", parent_bid="root1")
        _mk_item(shifu_bid, "b", "0101", parent_bid="root1")  # collision
        db.session.commit()

        with pytest.raises(AppException) as exc_info:
            assert_outline_tree_publishable(app, shifu_bid)
        # 4010 == server.shifu.outlineStructureBroken (see error_codes.json)
        assert exc_info.value.code == 4010
