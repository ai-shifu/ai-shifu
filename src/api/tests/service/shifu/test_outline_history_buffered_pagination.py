"""Buffered keyset pagination for outline version scans.

These scans used yield_per (server-side cursors); an early break left an
unexhausted result stream on the pooled connection. The helper must return
the same newest-first sequence in fully-buffered batches and stay correct
across batch boundaries and max_rows caps.
"""

from flaskr.dao import db
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.shifu.shifu_history_manager import (
    iter_outline_item_versions_desc,
)

SHIFU = "shifu-history-pg"
OUTLINE = "outline-history-pg"


def _seed_versions(count: int) -> list[int]:
    rows = []
    for index in range(count):
        rows.append(
            DraftOutlineItem(
                outline_item_bid=OUTLINE,
                shifu_bid=SHIFU,
                title=f"v{index}",
                content=f"content-{index}",
                position="01",
                deleted=0,
            )
        )
    db.session.add_all(rows)
    db.session.commit()
    return sorted((int(row.id) for row in rows), reverse=True)


def _cleanup():
    DraftOutlineItem.query.filter(DraftOutlineItem.shifu_bid == SHIFU).delete()
    db.session.commit()


def test_yields_all_versions_newest_first_across_batches(app):
    with app.app_context():
        _cleanup()
        expected_ids = _seed_versions(7)

        got = [
            int(row.id)
            for row in iter_outline_item_versions_desc(SHIFU, OUTLINE, batch_size=3)
        ]

        assert got == expected_ids
        _cleanup()


def test_max_rows_caps_the_scan(app):
    with app.app_context():
        _cleanup()
        expected_ids = _seed_versions(6)

        got = [
            int(row.id)
            for row in iter_outline_item_versions_desc(
                SHIFU, OUTLINE, batch_size=2, max_rows=5
            )
        ]

        assert got == expected_ids[:5]
        _cleanup()


def test_early_break_leaves_session_usable(app):
    with app.app_context():
        _cleanup()
        expected_ids = _seed_versions(5)

        iterator = iter_outline_item_versions_desc(SHIFU, OUTLINE, batch_size=2)
        first = next(iterator)
        assert int(first.id) == expected_ids[0]
        # Caller breaks mid-scan; the session must remain fully usable.
        iterator.close()

        count = DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == SHIFU
        ).count()
        assert count == 5
        _cleanup()


def test_skips_deleted_versions(app):
    with app.app_context():
        _cleanup()
        ids = _seed_versions(4)
        DraftOutlineItem.query.filter(DraftOutlineItem.id == ids[1]).update(
            {"deleted": 1}
        )
        db.session.commit()

        got = [
            int(row.id)
            for row in iter_outline_item_versions_desc(SHIFU, OUTLINE, batch_size=2)
        ]

        assert got == [ids[0]] + ids[2:]
        _cleanup()
