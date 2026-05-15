from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import flaskr.dao as dao
from flaskr.service.shifu.models import DraftShifu
from flaskr.service.shifu.shifu_draft_funcs import get_shifu_draft_list


def _seed_draft(
    *,
    shifu_bid: str,
    title: str,
    owner_bid: str,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    draft = DraftShifu(
        shifu_bid=shifu_bid,
        title=title,
        description="desc",
        avatar_res_bid="res",
        keywords="test",
        llm="gpt",
        llm_temperature=Decimal("0"),
        llm_system_prompt="",
        price=Decimal("0"),
        created_user_bid=owner_bid,
        updated_user_bid=owner_bid,
        created_at=created_at,
        updated_at=updated_at,
    )
    dao.db.session.add(draft)


def test_get_shifu_draft_list_sorts_by_updated_at_desc_then_id_desc(app):
    owner_bid = "draft-list-owner"
    with app.app_context():
        DraftShifu.query.filter(
            DraftShifu.created_user_bid == owner_bid,
            DraftShifu.shifu_bid.in_(
                ["draft-sort-older", "draft-sort-newer", "draft-sort-same-time-a"]
            ),
        ).delete(synchronize_session=False)

        same_updated_at = datetime(2026, 5, 15, 12, 0, 0)
        _seed_draft(
            shifu_bid="draft-sort-older",
            title="AAA Older Title",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 10, 10, 0, 0),
            updated_at=datetime(2026, 5, 14, 9, 0, 0),
        )
        _seed_draft(
            shifu_bid="draft-sort-newer",
            title="ZZZ Newer Title",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 11, 10, 0, 0),
            updated_at=datetime(2026, 5, 15, 13, 0, 0),
        )
        _seed_draft(
            shifu_bid="draft-sort-same-time-a",
            title="MMM Same Time Title",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 12, 10, 0, 0),
            updated_at=same_updated_at,
        )
        _seed_draft(
            shifu_bid="draft-sort-same-time-a",
            title="MMM Same Time Title",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 12, 10, 0, 0),
            updated_at=same_updated_at,
        )
        dao.db.session.commit()

        result = get_shifu_draft_list(
            app,
            owner_bid,
            page_index=1,
            page_size=10,
            is_favorite=False,
            archived=False,
            creator_only=True,
        )

    assert [item.bid for item in result.data[:3]] == [
        "draft-sort-newer",
        "draft-sort-same-time-a",
        "draft-sort-older",
    ]
