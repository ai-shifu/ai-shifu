from __future__ import annotations

from decimal import Decimal

import pytest

from flaskr.dao import db
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct
from flaskr.service.shifu.repair import repair_shifu_outline_structure
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def _mk_shifu(shifu_bid: str, title: str = "Draft") -> DraftShifu:
    shifu = DraftShifu(
        shifu_bid=shifu_bid,
        title=title,
        description="desc",
        avatar_res_bid="res",
        keywords="",
        llm="gpt-test",
        llm_temperature=Decimal("0.3"),
        price=Decimal("0"),
        deleted=0,
        created_user_bid="owner-1",
        updated_user_bid="owner-1",
    )
    db.session.add(shifu)
    db.session.flush()
    return shifu


def _mk_outline(
    shifu_bid: str,
    outline_bid: str,
    position: str,
    *,
    parent_bid: str = "",
    title: str | None = None,
) -> DraftOutlineItem:
    row = DraftOutlineItem(
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        title=title or outline_bid,
        position=position,
        parent_bid=parent_bid,
        deleted=0,
        created_user_bid="owner-1",
        updated_user_bid="owner-1",
    )
    db.session.add(row)
    db.session.flush()
    return row


def test_repair_shifu_outline_structure_dry_run_is_non_destructive(app):
    with app.app_context():
        _mk_shifu("shifu-dry-run")
        _mk_outline("shifu-dry-run", "root-1", "01")
        _mk_outline("shifu-dry-run", "child-a", "0101", parent_bid="")
        _mk_outline("shifu-dry-run", "child-b", "0101", parent_bid="root-1")
        db.session.commit()

        before_latest_id = db.session.query(db.func.max(DraftOutlineItem.id)).scalar()
        result = repair_shifu_outline_structure(
            app,
            user_bid=None,
            shifu_bids=["shifu-dry-run"],
            dry_run=True,
        )
        after_latest_id = db.session.query(db.func.max(DraftOutlineItem.id)).scalar()

    assert result.status == "dry_run"
    assert result.repaired_shifu_count == 1
    assert result.changed_outline_count == 2
    assert before_latest_id == after_latest_id


def test_repair_shifu_outline_structure_repairs_collision_and_rebuilds_struct(app):
    with app.app_context():
        shifu = _mk_shifu("shifu-repair-1")
        shifu_db_id = shifu.id
        _mk_outline("shifu-repair-1", "root-1", "01")
        _mk_outline("shifu-repair-1", "root-4", "04")
        _mk_outline("shifu-repair-1", "child-a", "0401", parent_bid="")
        _mk_outline("shifu-repair-1", "child-b", "0401", parent_bid="root-4")
        _mk_outline("shifu-repair-1", "child-c", "0402", parent_bid="root-4")
        db.session.commit()

        result = repair_shifu_outline_structure(
            app,
            user_bid="repair-user-1",
            shifu_bids=["shifu-repair-1"],
            dry_run=False,
        )

        latest_rows = (
            DraftOutlineItem.query.filter_by(shifu_bid="shifu-repair-1", deleted=0)
            .order_by(
                DraftOutlineItem.outline_item_bid.asc(),
                DraftOutlineItem.id.desc(),
            )
            .all()
        )
        latest_by_bid = {}
        for row in latest_rows:
            latest_by_bid.setdefault(row.outline_item_bid, row)

        latest_struct = (
            LogDraftStruct.query.filter_by(shifu_bid="shifu-repair-1", deleted=0)
            .order_by(LogDraftStruct.id.desc())
            .first()
        )

    assert result.status == "repaired"
    assert result.repaired_shifu_count == 1
    assert result.changed_outline_count == 3
    assert result.rebuilt_struct_count == 1

    assert latest_by_bid["child-a"].parent_bid == "root-4"
    assert latest_by_bid["child-a"].position == "0401"
    assert latest_by_bid["child-b"].position == "0402"
    assert latest_by_bid["child-c"].position == "0403"

    assert latest_struct is not None
    history = HistoryItem.from_json(latest_struct.struct)
    assert history.id == shifu_db_id
    root4 = next(child for child in history.children if child.bid == "root-4")
    assert [child.bid for child in root4.children] == ["child-a", "child-b", "child-c"]


def test_repair_shifu_outline_structure_skips_invalid_position_format_without_crashing(
    app,
):
    with app.app_context():
        _mk_shifu("shifu-invalid-position")
        _mk_outline("shifu-invalid-position", "root-1", "01")
        _mk_outline(
            "shifu-invalid-position",
            "child-a",
            "010",
            parent_bid="root-1",
        )
        db.session.commit()

        result = repair_shifu_outline_structure(
            app,
            user_bid=None,
            shifu_bids=["shifu-invalid-position"],
            dry_run=True,
        )

    assert result.status == "skipped"
    assert result.repaired_shifu_count == 0
    assert result.changed_outline_count == 0
    assert result.skipped_records[0].shifu_bid == "shifu-invalid-position"
    assert "Unsupported position format" in result.skipped_records[0].reason


def test_repair_shifu_outline_structure_requires_user_bid_before_processing(app):
    with app.app_context():
        _mk_shifu("shifu-user-bid-check")
        _mk_outline("shifu-user-bid-check", "root-1", "01")
        _mk_outline("shifu-user-bid-check", "child-a", "0101", parent_bid="")
        _mk_outline("shifu-user-bid-check", "child-b", "0101", parent_bid="root-1")
        db.session.commit()

    with pytest.raises(ValueError) as exc_info:
        repair_shifu_outline_structure(
            app,
            user_bid=None,
            shifu_bids=["shifu-user-bid-check"],
            dry_run=False,
        )
    assert "user_bid is required" in str(exc_info.value)


def test_repair_shifu_outline_structure_handles_non_numeric_suffixes(app):
    with app.app_context():
        _mk_shifu("shifu-nonnumeric-suffix")
        _mk_outline("shifu-nonnumeric-suffix", "root-1", "01")
        _mk_outline(
            "shifu-nonnumeric-suffix",
            "child-a",
            "010a",
            parent_bid="root-1",
        )
        _mk_outline(
            "shifu-nonnumeric-suffix",
            "child-b",
            "010a",
            parent_bid="root-1",
        )
        db.session.commit()

        result = repair_shifu_outline_structure(
            app,
            user_bid=None,
            shifu_bids=["shifu-nonnumeric-suffix"],
            dry_run=True,
        )

    assert result.status == "dry_run"
    assert result.repaired_shifu_count == 1
    assert result.changed_outline_count == 2


def test_repair_shifu_outline_structure_detects_parent_position_mismatch(app):
    with app.app_context():
        _mk_shifu("shifu-parent-position-mismatch")
        _mk_outline("shifu-parent-position-mismatch", "root-a", "01")
        _mk_outline("shifu-parent-position-mismatch", "root-b", "02")
        _mk_outline(
            "shifu-parent-position-mismatch",
            "child-a",
            "0101",
            parent_bid="root-b",
        )
        db.session.commit()

        result = repair_shifu_outline_structure(
            app,
            user_bid=None,
            shifu_bids=["shifu-parent-position-mismatch"],
            dry_run=True,
        )

    assert result.status == "dry_run"
    assert result.repaired_shifu_count == 1
    assert result.changed_outline_count == 1
    assert result.repaired_records[0].issue_types == ["parent_position_mismatch"]
    assert result.repaired_records[0].changed_outlines[0].outline_item_bid == "child-a"
    assert result.repaired_records[0].changed_outlines[0].old_parent_bid == "root-b"
    assert result.repaired_records[0].changed_outlines[0].new_parent_bid == "root-b"
    assert result.repaired_records[0].changed_outlines[0].old_position == "0101"
    assert result.repaired_records[0].changed_outlines[0].new_position == "0201"
