"""Verify first-party course visitor recording and counting."""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.learn.course_visits import (
    COURSE_VISIT_WINDOW,
    _build_supported_dialect_upsert,
    count_recent_course_visitors,
    record_course_visit,
)
from flaskr.service.learn.models import LearnCourseVisitor
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import UserInfo as UserEntity
from sqlalchemy.dialects import mysql


def _clear_tables() -> None:
    LearnCourseVisitor.query.delete()
    DraftShifu.query.delete()
    PublishedShifu.query.delete()
    UserEntity.query.delete()
    db.session.commit()


@pytest.fixture(autouse=True)
def _isolate_tables(app: object) -> object:
    with app.app_context():
        _clear_tables()
    yield
    with app.app_context():
        _clear_tables()


def _seed_user(*, user_bid: str, state: int, deleted: int = 0) -> None:
    db.session.add(
        UserEntity(
            user_bid=user_bid,
            user_identify=user_bid,
            nickname=user_bid,
            language="en-US",
            state=state,
            deleted=deleted,
        )
    )


def _build_course(model: object, *, shifu_bid: str) -> object:
    return model(
        shifu_bid=shifu_bid,
        title="Course visit test",
        description="Course visit test",
        avatar_res_bid="",
        keywords="",
        llm="gpt-test",
        llm_temperature=Decimal(0),
        llm_system_prompt="",
        price=Decimal(0),
        deleted=0,
        created_user_bid="teacher-1",
        updated_user_bid="teacher-1",
    )


def _mock_authenticated_user(monkeypatch: object, user_bid: str) -> None:
    user = SimpleNamespace(
        user_id=user_bid,
        is_creator=False,
        is_operator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: user,
        raising=False,
    )


@pytest.mark.parametrize(
    "user_state",
    [USER_STATE_REGISTERED, USER_STATE_TRAIL, USER_STATE_PAID],
)
def test_visit_route_records_eligible_published_course_and_deduplicates(
    app: object,
    test_client: object,
    monkeypatch: object,
    user_state: int,
) -> None:
    first_visit = datetime(2026, 8, 30, 1, 0, 0)
    later_visit = datetime(2026, 8, 30, 2, 0, 0)
    visit_times = iter((first_visit, later_visit))
    monkeypatch.setattr(
        "flaskr.service.learn.course_visits.now_utc",
        lambda: next(visit_times),
    )
    _mock_authenticated_user(monkeypatch, "registered-user")

    with app.app_context():
        _seed_user(user_bid="registered-user", state=user_state)
        db.session.add(_build_course(PublishedShifu, shifu_bid="published-course"))
        db.session.commit()

    first_response = test_client.post(
        "/api/learn/shifu/published-course/visit",
        headers={"Token": "registered-token"},
    )
    second_response = test_client.post(
        "/api/learn/shifu/published-course/visit",
        headers={"Token": "registered-token"},
    )

    assert first_response.get_json(force=True)["data"] == {"recorded": True}
    assert second_response.get_json(force=True)["data"] == {"recorded": True}
    with app.app_context():
        rows = LearnCourseVisitor.query.all()
        assert len(rows) == 1
        assert rows[0].first_visited_at == first_visit
        assert rows[0].last_visited_at == later_visit


def test_visit_upsert_preserves_first_and_last_when_requests_arrive_out_of_order(
    app: object,
    monkeypatch: object,
) -> None:
    first_recorded_at = datetime(2026, 8, 30, 3, 1, 0)
    second_recorded_at = datetime(2026, 8, 30, 3, 0, 0)
    recorded_times = iter((first_recorded_at, second_recorded_at))
    monkeypatch.setattr(
        "flaskr.service.learn.course_visits.now_utc",
        lambda: next(recorded_times),
    )
    earlier_visit = datetime(2026, 8, 29, 23, 0, 0)
    later_visit = datetime(2026, 8, 30, 2, 0, 0)

    with app.app_context():
        _seed_user(user_bid="registered-user", state=USER_STATE_REGISTERED)
        db.session.add(_build_course(PublishedShifu, shifu_bid="published-course"))
        db.session.commit()

        assert record_course_visit(
            app,
            shifu_bid="published-course",
            user_bid="registered-user",
            visited_at=later_visit,
        )
        assert record_course_visit(
            app,
            shifu_bid="published-course",
            user_bid="registered-user",
            visited_at=earlier_visit,
        )

        row = LearnCourseVisitor.query.one()
        assert row.first_visited_at == earlier_visit
        assert row.last_visited_at == later_visit
        assert row.created_at == second_recorded_at
        assert row.updated_at == first_recorded_at


@pytest.mark.parametrize(
    ("user_state", "deleted"),
    [(USER_STATE_UNREGISTERED, 0), (USER_STATE_REGISTERED, 1)],
)
def test_visit_route_excludes_ineligible_user_without_error(
    app: object,
    test_client: object,
    monkeypatch: object,
    user_state: int,
    deleted: int,
) -> None:
    _mock_authenticated_user(monkeypatch, "guest-user")
    with app.app_context():
        _seed_user(user_bid="guest-user", state=user_state, deleted=deleted)
        db.session.add(_build_course(PublishedShifu, shifu_bid="published-course"))
        db.session.commit()

    response = test_client.post(
        "/api/learn/shifu/published-course/visit",
        headers={"Token": "guest-token"},
    )

    assert response.status_code == 200
    assert response.get_json(force=True) == {
        "code": 0,
        "message": "success",
        "data": {"recorded": False},
    }
    with app.app_context():
        assert LearnCourseVisitor.query.count() == 0


def test_visit_route_rejects_nonempty_body_without_recording(
    app: object,
    test_client: object,
    monkeypatch: object,
) -> None:
    _mock_authenticated_user(monkeypatch, "registered-user")
    with app.app_context():
        _seed_user(user_bid="registered-user", state=USER_STATE_REGISTERED)
        db.session.add(_build_course(PublishedShifu, shifu_bid="published-course"))
        db.session.commit()

    response = test_client.post(
        "/api/learn/shifu/published-course/visit",
        json={"user_id": "untrusted-user", "url": "https://example.test/private"},
        headers={"Token": "registered-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] != 0
    with app.app_context():
        assert LearnCourseVisitor.query.count() == 0


def test_visit_route_rejects_malformed_body_without_recording(
    app: object,
    test_client: object,
    monkeypatch: object,
) -> None:
    _mock_authenticated_user(monkeypatch, "registered-user")
    with app.app_context():
        _seed_user(user_bid="registered-user", state=USER_STATE_REGISTERED)
        db.session.add(_build_course(PublishedShifu, shifu_bid="published-course"))
        db.session.commit()

    response = test_client.post(
        "/api/learn/shifu/published-course/visit",
        data="not-json",
        headers={"Token": "registered-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] != 0
    with app.app_context():
        assert LearnCourseVisitor.query.count() == 0


def test_visit_route_rejects_course_without_published_version(
    app: object,
    test_client: object,
    monkeypatch: object,
) -> None:
    _mock_authenticated_user(monkeypatch, "registered-user")
    with app.app_context():
        _seed_user(user_bid="registered-user", state=USER_STATE_REGISTERED)
        db.session.add(_build_course(DraftShifu, shifu_bid="draft-course"))
        db.session.commit()

    response = test_client.post(
        "/api/learn/shifu/draft-course/visit",
        headers={"Token": "registered-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] != 0
    assert payload["message"] == "Course not found"
    with app.app_context():
        assert LearnCourseVisitor.query.count() == 0


def test_visit_route_rejects_missing_course(
    app: object,
    test_client: object,
    monkeypatch: object,
) -> None:
    _mock_authenticated_user(monkeypatch, "registered-user")
    with app.app_context():
        _seed_user(user_bid="registered-user", state=USER_STATE_REGISTERED)
        db.session.commit()

    response = test_client.post(
        "/api/learn/shifu/missing-course/visit",
        headers={"Token": "registered-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] != 0
    assert payload["message"] == "Course not found"
    with app.app_context():
        assert LearnCourseVisitor.query.count() == 0


def test_mysql_visit_upsert_compiles_atomic_min_max_contract() -> None:
    statement = _build_supported_dialect_upsert(
        dialect_name="mysql",
        shifu_bid="course-a",
        user_bid="user-a",
        visited_at=datetime(2026, 8, 30, 12, 0, 0),
        recorded_at=datetime(2026, 8, 30, 12, 0, 1),
    )
    assert statement is not None

    sql = str(statement.compile(dialect=mysql.dialect()))
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert sql.count("CASE WHEN") == 4
    assert "created_at >" in sql
    assert "first_visited_at >" in sql
    assert "last_visited_at <" in sql
    assert "updated_at <" in sql


def test_recent_visitor_count_uses_exact_window_and_isolates_courses(
    app: object,
) -> None:
    as_of = datetime(2026, 8, 30, 12, 0, 0)
    cutoff = as_of - COURSE_VISIT_WINDOW
    with app.app_context():
        db.session.add_all(
            [
                LearnCourseVisitor(
                    shifu_bid="course-a",
                    user_bid="at-boundary",
                    first_visited_at=cutoff,
                    last_visited_at=cutoff,
                ),
                LearnCourseVisitor(
                    shifu_bid="course-a",
                    user_bid="inside-window",
                    first_visited_at=as_of - timedelta(hours=1),
                    last_visited_at=as_of - timedelta(hours=1),
                ),
                LearnCourseVisitor(
                    shifu_bid="course-a",
                    user_bid="outside-window",
                    first_visited_at=cutoff - timedelta(microseconds=1),
                    last_visited_at=cutoff - timedelta(microseconds=1),
                ),
                LearnCourseVisitor(
                    shifu_bid="course-a",
                    user_bid="future-visit",
                    first_visited_at=as_of + timedelta(microseconds=1),
                    last_visited_at=as_of + timedelta(microseconds=1),
                ),
                LearnCourseVisitor(
                    shifu_bid="course-b",
                    user_bid="other-course",
                    first_visited_at=as_of,
                    last_visited_at=as_of,
                ),
            ]
        )
        db.session.commit()

        assert count_recent_course_visitors("course-a", as_of=as_of) == 2
        assert count_recent_course_visitors("course-b", as_of=as_of) == 1
