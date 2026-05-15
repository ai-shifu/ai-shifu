from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import flaskr.dao as dao
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
)
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
                [
                    "draft-sort-older",
                    "draft-sort-newer",
                    "draft-sort-same-time-a",
                    "draft-sort-same-time-b",
                ]
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
            title="MMM Same Time Title A",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 12, 10, 0, 0),
            updated_at=same_updated_at,
        )
        _seed_draft(
            shifu_bid="draft-sort-same-time-b",
            title="MMM Same Time Title B",
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

    assert [item.bid for item in result.data[:4]] == [
        "draft-sort-newer",
        "draft-sort-same-time-b",
        "draft-sort-same-time-a",
        "draft-sort-older",
    ]


def test_get_shifu_draft_list_prefers_latest_outline_activity(app):
    owner_bid = "draft-list-activity-owner"
    with app.app_context():
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid.in_(
                ["draft-activity-course", "draft-activity-reference"]
            )
        ).delete(synchronize_session=False)
        DraftShifu.query.filter(
            DraftShifu.created_user_bid == owner_bid,
            DraftShifu.shifu_bid.in_(
                ["draft-activity-course", "draft-activity-reference"]
            ),
        ).delete(synchronize_session=False)

        _seed_draft(
            shifu_bid="draft-activity-course",
            title="Outline Activity",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 10, 10, 0, 0),
            updated_at=datetime(2026, 5, 10, 10, 0, 0),
        )
        _seed_draft(
            shifu_bid="draft-activity-reference",
            title="Reference Course",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 11, 10, 0, 0),
            updated_at=datetime(2026, 5, 12, 10, 0, 0),
        )
        dao.db.session.flush()

        dao.db.session.add(
            DraftOutlineItem(
                outline_item_bid="draft-activity-outline",
                shifu_bid="draft-activity-course",
                title="Fresh Lesson",
                parent_bid="",
                position="01",
                prerequisite_item_bids="",
                llm="",
                llm_temperature=Decimal("0"),
                llm_system_prompt="",
                ask_enabled_status=5101,
                ask_llm="",
                ask_llm_temperature=Decimal("0"),
                ask_llm_system_prompt="",
                content="",
                type=0,
                hidden=0,
                deleted=0,
                created_at=datetime(2026, 5, 13, 10, 0, 0),
                updated_at=datetime(2026, 5, 13, 10, 0, 0),
                created_user_bid=owner_bid,
                updated_user_bid=owner_bid,
            )
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

    assert [item.bid for item in result.data[:2]] == [
        "draft-activity-course",
        "draft-activity-reference",
    ]


def test_get_shifu_draft_list_ignores_published_outline_activity(app):
    owner_bid = "draft-list-published-outline-owner"
    with app.app_context():
        PublishedOutlineItem.query.filter(
            PublishedOutlineItem.shifu_bid == "draft-published-outline-course"
        ).delete(synchronize_session=False)
        DraftShifu.query.filter(
            DraftShifu.created_user_bid == owner_bid,
            DraftShifu.shifu_bid.in_(
                ["draft-published-outline-course", "draft-published-outline-reference"]
            ),
        ).delete(synchronize_session=False)

        _seed_draft(
            shifu_bid="draft-published-outline-course",
            title="Course With Published Activity",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 10, 10, 0, 0),
            updated_at=datetime(2026, 5, 10, 10, 0, 0),
        )
        _seed_draft(
            shifu_bid="draft-published-outline-reference",
            title="Reference Draft Course",
            owner_bid=owner_bid,
            created_at=datetime(2026, 5, 11, 10, 0, 0),
            updated_at=datetime(2026, 5, 12, 10, 0, 0),
        )
        dao.db.session.flush()

        dao.db.session.add(
            PublishedOutlineItem(
                outline_item_bid="published-outline-activity",
                shifu_bid="draft-published-outline-course",
                title="Published Lesson",
                parent_bid="",
                position="01",
                prerequisite_item_bids="",
                llm="",
                llm_temperature=Decimal("0"),
                llm_system_prompt="",
                ask_enabled_status=5101,
                ask_llm="",
                ask_llm_temperature=Decimal("0"),
                ask_llm_system_prompt="",
                content="",
                type=0,
                hidden=0,
                deleted=0,
                created_at=datetime(2026, 5, 13, 10, 0, 0),
                updated_at=datetime(2026, 5, 13, 10, 0, 0),
                created_user_bid=owner_bid,
                updated_user_bid=owner_bid,
            )
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

    assert [item.bid for item in result.data[:2]] == [
        "draft-published-outline-reference",
        "draft-published-outline-course",
    ]
