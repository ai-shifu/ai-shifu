from decimal import Decimal
from datetime import timedelta

from flaskr.dao import db
from flaskr.service.learn.learn_funcs import get_outline_item_tree, get_shifu_info
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def test_get_shifu_info_returns_dto(app):
    with app.app_context():
        shifu = PublishedShifu(
            shifu_bid="shifu-learn-1",
            title="Test Shifu",
            description="Desc",
            price=Decimal("9.99"),
            keywords="a,b",
        )
        db.session.add(shifu)
        db.session.commit()

    dto = get_shifu_info(app, "shifu-learn-1", preview_mode=False)
    assert dto.bid == "shifu-learn-1"
    assert dto.title == "Test Shifu"
    assert dto.price == "9.99"
    assert dto.keywords == ["a", "b"]


def test_get_shifu_info_preview_mode_uses_draft_tts_flag(app):
    with app.app_context():
        draft = DraftShifu(
            shifu_bid="shifu-learn-tts",
            title="Draft Shifu",
            description="Draft Desc",
            price=Decimal("1.00"),
            keywords="listen",
            tts_enabled=1,
        )
        published = PublishedShifu(
            shifu_bid="shifu-learn-tts",
            title="Published Shifu",
            description="Published Desc",
            price=Decimal("2.00"),
            keywords="listen",
            tts_enabled=0,
        )
        db.session.add_all([draft, published])
        db.session.commit()

    preview_dto = get_shifu_info(app, "shifu-learn-tts", preview_mode=True)
    live_dto = get_shifu_info(app, "shifu-learn-tts", preview_mode=False)

    assert preview_dto.title == "Draft Shifu"
    assert preview_dto.tts_enabled is True
    assert live_dto.title == "Published Shifu"
    assert live_dto.tts_enabled is False


def test_get_outline_item_tree_preview_mode(app):
    with app.app_context():
        outline = DraftOutlineItem(
            outline_item_bid="outline-learn-1",
            shifu_bid="shifu-learn-1",
            title="Outline",
            position="1",
            type=401,
            hidden=0,
        )
        db.session.add(outline)
        db.session.commit()

        struct = HistoryItem(
            bid="shifu-learn-1",
            id=0,
            type="shifu",
            children=[
                HistoryItem(
                    bid="outline-learn-1",
                    id=outline.id,
                    type="outline",
                    children=[],
                )
            ],
        ).to_json()
        log = LogDraftStruct(
            struct_bid="struct-learn-1",
            shifu_bid="shifu-learn-1",
            struct=struct,
        )
        db.session.add(log)
        db.session.commit()

    result = get_outline_item_tree(app, "shifu-learn-1", "user-1", preview_mode=True)
    assert result.outline_items
    assert result.outline_items[0].bid == "outline-learn-1"
    assert result.outline_items[0].is_paid is True
    assert result.outline_items[0].has_content_update_for_current_user is False


def test_get_outline_item_tree_marks_published_lesson_updates_for_current_user(app):
    with app.app_context():
        chapter = PublishedOutlineItem(
            outline_item_bid="chapter-learn-1",
            shifu_bid="shifu-learn-published-1",
            title="Chapter",
            position="1",
            type=401,
            hidden=0,
        )
        lesson = PublishedOutlineItem(
            outline_item_bid="lesson-learn-1",
            shifu_bid="shifu-learn-published-1",
            title="Lesson",
            position="1.1",
            type=401,
            hidden=0,
        )
        db.session.add_all([chapter, lesson])
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid="progress-learn-1",
            shifu_bid="shifu-learn-published-1",
            outline_item_bid="lesson-learn-1",
            user_bid="user-1",
            status=602,
        )
        db.session.add(progress)
        db.session.commit()

        progress.updated_at = lesson.updated_at
        db.session.commit()

        lesson.updated_at = lesson.updated_at + timedelta(minutes=1)
        db.session.commit()

        struct = HistoryItem(
            bid="shifu-learn-published-1",
            id=0,
            type="shifu",
            children=[
                HistoryItem(
                    bid="chapter-learn-1",
                    id=chapter.id,
                    type="outline",
                    children=[
                        HistoryItem(
                            bid="lesson-learn-1",
                            id=lesson.id,
                            type="outline",
                            children=[],
                        )
                    ],
                )
            ],
        ).to_json()
        log = LogPublishedStruct(
            struct_bid="struct-learn-published-1",
            shifu_bid="shifu-learn-published-1",
            struct=struct,
        )
        published = PublishedShifu(
            shifu_bid="shifu-learn-published-1",
            title="Published Shifu",
            description="Desc",
            price=Decimal("9.99"),
            keywords="a,b",
        )
        db.session.add_all([log, published])
        db.session.commit()

    result = get_outline_item_tree(
        app, "shifu-learn-published-1", "user-1", preview_mode=False
    )

    assert result.outline_items
    assert result.outline_items[0].has_content_update_for_current_user is False
    assert (
        result.outline_items[0].children[0].has_content_update_for_current_user
        is True
    )
