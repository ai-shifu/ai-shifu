"""Regression coverage for keeping outline operations inside their course."""

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.shifu.shifu_outline_funcs import (
    delete_unit,
    get_unit_by_id,
    modify_unit,
)


def _seed_outline(shifu_bid: str, outline_bid: str) -> None:
    db.session.add(
        DraftOutlineItem(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            title="Protected lesson",
            position="01",
            parent_bid="",
            type=401,
            hidden=0,
            llm_system_prompt="Protected prompt",
            deleted=0,
        )
    )
    db.session.commit()


def test_get_unit_rejects_outline_from_another_course(app: object) -> None:
    with app.app_context():
        _seed_outline("course-b-read", "lesson-b-read")

        with pytest.raises(AppError):
            get_unit_by_id(app, "creator-a", "course-a-read", "lesson-b-read")

        own_course_unit = get_unit_by_id(
            app, "creator-b", "course-b-read", "lesson-b-read"
        )

    assert own_course_unit.name == "Protected lesson"


def test_modify_unit_rejects_outline_from_another_course(app: object) -> None:
    with app.app_context():
        _seed_outline("course-b-modify", "lesson-b-modify")

        with pytest.raises(AppError):
            modify_unit(
                app,
                "creator-a",
                "course-a-modify",
                "lesson-b-modify",
                unit_name="Compromised lesson",
            )

        stored = DraftOutlineItem.query.filter_by(
            shifu_bid="course-b-modify",
            outline_item_bid="lesson-b-modify",
            deleted=0,
        ).one()

    assert stored.title == "Protected lesson"


def test_delete_unit_rejects_outline_from_another_course(app: object) -> None:
    with app.app_context():
        _seed_outline("course-b-delete", "lesson-b-delete")

        with pytest.raises(AppError):
            delete_unit(app, "creator-a", "course-a-delete", "lesson-b-delete")

        stored = DraftOutlineItem.query.filter_by(
            shifu_bid="course-b-delete",
            outline_item_bid="lesson-b-delete",
        ).one()

    assert stored.deleted == 0
