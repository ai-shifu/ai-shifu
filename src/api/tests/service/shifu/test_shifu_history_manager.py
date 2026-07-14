from __future__ import annotations

import pytest

from flaskr.dao import db
from flaskr.service.shifu.models import DraftShifu, LogDraftStruct
from flaskr.service.shifu.shifu_history_manager import (
    HistoryItem,
    save_new_outline_history,
    save_shifu_history,
)


def _seed_shifu(shifu_bid: str, user_bid: str) -> DraftShifu:
    shifu = DraftShifu(
        shifu_bid=shifu_bid,
        title="History Course",
        created_user_bid=user_bid,
        updated_user_bid=user_bid,
        deleted=0,
    )
    db.session.add(shifu)
    db.session.flush()
    return shifu


def test_save_new_outline_history_raises_when_parent_missing(app):
    shifu_bid = "history-parent-missing"
    user_bid = "creator-history"

    with app.app_context():
        shifu = _seed_shifu(shifu_bid, user_bid)
        save_shifu_history(app, user_bid, shifu_bid, shifu.id)

        before_count = LogDraftStruct.query.filter_by(
            shifu_bid=shifu_bid, deleted=0
        ).count()

        with pytest.raises(RuntimeError, match="Parent history node not found"):
            save_new_outline_history(
                app,
                user_bid,
                shifu_bid,
                outline_bid="outline-1",
                id=123,
                parent_bid="missing-parent",
            )

        after_logs = (
            LogDraftStruct.query.filter_by(shifu_bid=shifu_bid, deleted=0)
            .order_by(LogDraftStruct.id.asc())
            .all()
        )

    assert len(after_logs) == before_count
    latest_history = HistoryItem.from_json(after_logs[-1].struct)
    assert latest_history.children == []
