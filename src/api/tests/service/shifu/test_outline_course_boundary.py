"""Regression coverage for keeping outline operations inside their course."""

from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.shifu.shifu_outline_funcs import (
    delete_unit,
    get_unit_by_id,
    modify_unit,
)


def _seed_outline(
    shifu_bid: str,
    outline_bid: str,
    *,
    title: str = "Protected lesson",
    parent_bid: str = "",
    position: str = "01",
) -> None:
    db.session.add(
        DraftOutlineItem(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            title=title,
            position=position,
            parent_bid=parent_bid,
            type=401,
            hidden=0,
            llm_system_prompt="Protected prompt",
            deleted=0,
        )
    )
    db.session.commit()


def _latest_outline(shifu_bid: str, outline_bid: str) -> DraftOutlineItem:
    return (
        DraftOutlineItem.query.filter_by(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
        )
        .order_by(DraftOutlineItem.id.desc())
        .first()
    )


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


@pytest.mark.parametrize(
    ("method", "json_body"),
    [
        ("get", None),
        ("post", {"name": "Compromised lesson"}),
        ("delete", None),
    ],
)
def test_outline_http_routes_reject_cross_course_lesson(
    app: object,
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    json_body: dict | None,
) -> None:
    with app.app_context():
        _seed_outline("course-http-b", "lesson-http-b")

    user = SimpleNamespace(user_id="creator-a", is_creator=True, language="en-US")
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda _app, _token: user)
    monkeypatch.setattr(
        "flaskr.service.shifu.route.shifu_permission_verification",
        lambda _app, _user_id, _shifu_bid, _permission: True,
    )

    response = getattr(test_client, method)(
        "/api/shifu/shifus/course-http-a/outlines/lesson-http-b",
        json=json_body,
        headers={"Token": "test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["code"] != 0
    with app.app_context():
        protected = _latest_outline("course-http-b", "lesson-http-b")
        assert protected.title == "Protected lesson"
        assert protected.deleted == 0


def test_same_lesson_id_is_isolated_between_courses(app: object) -> None:
    with app.app_context():
        _seed_outline("course-shared-a", "shared-lesson", title="Course A lesson")
        _seed_outline("course-shared-b", "shared-lesson", title="Course B lesson")

        unit = get_unit_by_id(app, "creator-a", "course-shared-a", "shared-lesson")
        modify_unit(
            app,
            "creator-a",
            "course-shared-a",
            "shared-lesson",
            unit_name="Updated course A lesson",
        )

        course_a = _latest_outline("course-shared-a", "shared-lesson")
        course_b = _latest_outline("course-shared-b", "shared-lesson")

    assert unit.name == "Course A lesson"
    assert course_a.title == "Updated course A lesson"
    assert course_b.title == "Course B lesson"
    assert course_b.deleted == 0


def test_delete_unit_cascades_only_inside_selected_course(app: object) -> None:
    with app.app_context():
        for course_bid in ("course-cascade-a", "course-cascade-b"):
            _seed_outline(course_bid, "shared-chapter", title=f"{course_bid} chapter")
            _seed_outline(
                course_bid,
                "shared-child",
                title=f"{course_bid} child",
                parent_bid="shared-chapter",
                position="0101",
            )

        assert (
            delete_unit(app, "creator-a", "course-cascade-a", "shared-chapter") is True
        )

        course_a_chapter = _latest_outline("course-cascade-a", "shared-chapter")
        course_a_child = _latest_outline("course-cascade-a", "shared-child")
        course_b_chapter = _latest_outline("course-cascade-b", "shared-chapter")
        course_b_child = _latest_outline("course-cascade-b", "shared-child")

    assert course_a_chapter.deleted == 1
    assert course_a_child.deleted == 1
    assert course_b_chapter.deleted == 0
    assert course_b_child.deleted == 0
