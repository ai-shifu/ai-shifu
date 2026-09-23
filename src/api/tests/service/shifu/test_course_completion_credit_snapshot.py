"""The new completion estimate reads the same pinned outline as learners."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.shifu.admin_operations.course_completion_credit_snapshot import (
    load_course_completion_snapshot,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def course_bid(app: object) -> str:
    bid = "credit-snapshot-versioned"
    yield bid
    with app.app_context():
        for model in (
            LogDraftStruct,
            LogPublishedStruct,
            DraftOutlineItem,
            PublishedOutlineItem,
            DraftShifu,
            PublishedShifu,
        ):
            db.session.query(model).filter(model.shifu_bid == bid).delete()
        db.session.commit()


def _outline(
    model: type[DraftOutlineItem | PublishedOutlineItem],
    *,
    course_bid: str,
    bid: str,
    parent_bid: str = "",
    content: str = "",
    hidden: int = 0,
) -> DraftOutlineItem | PublishedOutlineItem:
    row = model(
        shifu_bid=course_bid,
        outline_item_bid=bid,
        parent_bid=parent_bid,
        title=bid,
        position="1",
        type=401,
        content=content,
        hidden=hidden,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _node(
    row: DraftOutlineItem | PublishedOutlineItem, *children: HistoryItem
) -> HistoryItem:
    return HistoryItem(
        bid=row.outline_item_bid,
        id=row.id,
        type="outline",
        children=list(children),
    )


def _seed_divergent_snapshots(course_bid: str) -> dict[str, object]:
    published_course = PublishedShifu(
        shifu_bid=course_bid,
        title="Published",
        llm_system_prompt="published prompt",
    )
    draft_course = DraftShifu(
        shifu_bid=course_bid,
        title="Draft",
        llm_system_prompt="draft prompt",
    )
    db.session.add_all([published_course, draft_course])
    db.session.flush()
    chapter = _outline(PublishedOutlineItem, course_bid=course_bid, bid="chapter")
    published_lesson = _outline(
        PublishedOutlineItem,
        course_bid=course_bid,
        bid="lesson",
        parent_bid="chapter",
        content="Published lesson text",
    )
    hidden_parent = _outline(
        PublishedOutlineItem,
        course_bid=course_bid,
        bid="hidden-parent",
        hidden=1,
    )
    hidden_parent_child = _outline(
        PublishedOutlineItem,
        course_bid=course_bid,
        bid="hidden-parent-child",
        parent_bid="hidden-parent",
        content="Must not count",
    )
    parent_with_hidden_child = _outline(
        PublishedOutlineItem,
        course_bid=course_bid,
        bid="parent-with-hidden-child",
        content="A chapter is not a raw leaf",
    )
    hidden_child = _outline(
        PublishedOutlineItem,
        course_bid=course_bid,
        bid="hidden-child",
        parent_bid="parent-with-hidden-child",
        content="Also hidden",
        hidden=1,
    )
    published_root = HistoryItem(
        bid=course_bid,
        id=published_course.id,
        type="shifu",
        children=[
            _node(chapter, _node(published_lesson)),
            _node(hidden_parent, _node(hidden_parent_child)),
            _node(parent_with_hidden_child, _node(hidden_child)),
        ],
    )
    db.session.add(
        LogPublishedStruct(
            shifu_bid=course_bid,
            struct_bid="published-credit-snapshot",
            struct=published_root.to_json(),
        )
    )

    draft_lesson = _outline(
        DraftOutlineItem,
        course_bid=course_bid,
        bid="lesson",
        content="Draft lesson text",
    )
    draft_root = HistoryItem(
        bid=course_bid,
        id=draft_course.id,
        type="shifu",
        children=[_node(draft_lesson)],
    )
    db.session.add(
        LogDraftStruct(
            shifu_bid=course_bid,
            struct_bid="draft-credit-snapshot",
            struct=draft_root.to_json(),
        )
    )
    # Later rows are not part of either structure snapshot.
    db.session.add(
        PublishedShifu(
            shifu_bid=course_bid,
            title="Unreferenced publication",
            llm_system_prompt="newer prompt",
        )
    )
    _outline(
        PublishedOutlineItem,
        course_bid=course_bid,
        bid="lesson",
        parent_bid="chapter",
        content="Unreferenced newer lesson",
    )
    db.session.commit()
    return {
        "published_course": published_course,
        "published_lesson": published_lesson,
        "draft_course": draft_course,
        "draft_lesson": draft_lesson,
    }


def test_snapshot_uses_exact_published_and_draft_rows_and_raw_leaf_rules(
    app: object, course_bid: str
) -> None:
    with app.app_context():
        rows = _seed_divergent_snapshots(course_bid)
        published = load_course_completion_snapshot(course_bid, published=True)
        draft = load_course_completion_snapshot(course_bid, published=False)

        assert published.course.id == rows["published_course"].id
        assert published.visible_leaf_outline_bids == ["lesson"]
        assert (
            next(
                row
                for row in published.outline_items
                if row.outline_item_bid == "lesson"
            ).id
            == rows["published_lesson"].id
        )
        assert draft.course.id == rows["draft_course"].id
        assert draft.visible_leaf_outline_bids == ["lesson"]
        assert draft.outline_items[0].id == rows["draft_lesson"].id


def test_snapshot_rejects_mismatched_or_legacy_child_rows(
    app: object, course_bid: str
) -> None:
    with app.app_context():
        rows = _seed_divergent_snapshots(course_bid)
        rows["published_lesson"].parent_bid = "wrong-parent"
        db.session.commit()
        with pytest.raises(ValueError, match="snapshot row is mismatched"):
            load_course_completion_snapshot(course_bid, published=True)

        rows["published_lesson"].parent_bid = "chapter"
        published_log = LogPublishedStruct.query.filter_by(shifu_bid=course_bid).first()
        root = HistoryItem.from_json(published_log.struct)
        root.children[0].children[0].children = [
            HistoryItem(bid="legacy-block", id=1, type="block")
        ]
        published_log.struct = root.to_json()
        db.session.commit()
        with pytest.raises(ValueError, match="structure is invalid"):
            load_course_completion_snapshot(course_bid, published=True)


def test_serving_estimate_uses_snapshot_course_when_draft_is_newer(
    app: object,
    course_bid: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.shifu.admin_operations import courses_detail

    with app.app_context():
        rows = _seed_divergent_snapshots(course_bid)
        artifact = tmp_path / "calibration.json"
        artifact.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(courses_detail, "_COMPLETION_CALIBRATION_PATH", artifact)
        monkeypatch.setattr(courses_detail, "detect_authored_language", lambda *_: "en")
        monkeypatch.setattr(courses_detail, "uses_agent_engine", lambda *_: False)
        passed: dict[str, object] = {}

        def capture_features(**kwargs: object) -> SimpleNamespace:
            passed.update(kwargs)
            return SimpleNamespace(as_mapping=lambda: {"lesson_count": 1.0})

        monkeypatch.setattr(
            courses_detail, "build_course_completion_credit_features", capture_features
        )
        monkeypatch.setattr(
            courses_detail,
            "estimate_course_credits",
            lambda *_args, **_kwargs: SimpleNamespace(
                status="calibrated",
                estimated_credits=Decimal("1.00"),
                recommended_credits=Decimal("2.00"),
                calibration_version="v1",
            ),
        )
        result = courses_detail._build_completion_credit_estimate(
            shifu_bid=course_bid, published=True
        )

        assert result.status == "calibrated"
        assert passed["course"].id == rows["published_course"].id
        assert passed["visible_leaf_outline_bids"] == ["lesson"]
