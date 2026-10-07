"""Exercise self-service memory against real SQLite rows and authenticated routes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.memory import load_memory
from flaskr.service.profile.api import (
    course_memory_deletion_state,
    delete_course_memory,
    list_course_memory,
)
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.repository import create_user_entity

if TYPE_CHECKING:
    from flask import Flask


def _row(
    user: str, course: str, key: str, value: str, *, deleted: int = 0
) -> VariableValue:
    row = VariableValue(
        user_bid=user,
        shifu_bid=course,
        key=key,
        value=value,
        variable_value_bid=uuid4().hex,
        deleted=deleted,
    )
    db.session.add(row)
    return row


def test_listing_paginates_current_full_values_and_isolates_scopes(app: Flask) -> None:
    with app.app_context():
        user, course = uuid4().hex, uuid4().hex
        with unit_of_work():
            for i in range(103):
                _row(user, course, f"item_{i}", str(i))
            _row(user, course, "item_0", "z" * 40000)
            _row(user, course, "sys_custom", "system")
            _row(user, course, "sys_user_nickname", "canonical")
            _row(user, "", "global", "global")
            _row(user, uuid4().hex, "elsewhere", "other course")
            _row(uuid4().hex, course, "other_user", "other learner")
        items, cursor = [], None
        while True:
            page = list_course_memory(
                user, course, before=int(cursor) if cursor else None
            )
            items.extend(page["items"])
            cursor = page["next_before"]
            if cursor is None:
                break
        assert len(items) == 103
        assert len({item["key"] for item in items}) == 103
        assert next(i["value"] for i in items if i["key"] == "item_0") == "z" * 40000


def test_delete_invalidates_history_without_touching_other_scopes(app: Flask) -> None:
    with app.app_context():
        user, course = uuid4().hex, uuid4().hex
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            db.session.add(
                Variable(variable_bid=uuid4().hex, shifu_bid=course, key="goal")
            )
            old = _row(user, course, "goal", "old")
            newest = _row(user, course, "goal", "new")
            global_row = _row(user, "", "goal", "global fallback")
            other = _row(uuid4().hex, course, "goal", "other")
            elsewhere = _row(user, uuid4().hex, "goal", "elsewhere")
        assert delete_course_memory(user, course, old.id) == {"conflict": True}
        assert not newest.deleted
        assert delete_course_memory(user, course, newest.id) == {"conflict": False}
        assert old.deleted
        assert newest.deleted
        assert not global_row.deleted
        assert not other.deleted
        assert not elsewhere.deleted
        assert list_course_memory(user, course)["items"] == []
        assert (
            "goal"
            not in load_memory(
                app, user, course, include_course_variables=True
            ).variables
        )
        assert delete_course_memory(user, course, newest.id) == {"conflict": False}
        assert delete_course_memory(user, course, other.id) == {"conflict": False}
        assert not other.deleted
        before, deleted = course_memory_deletion_state(user, course)
        assert deleted == {"goal"}
        with unit_of_work():
            recreated = _row(user, course, "goal", "deliberately saved again")
        after, deleted = course_memory_deletion_state(user, course)
        assert after == before
        assert not deleted
        assert list_course_memory(user, course)["items"][0]["value_id"] == str(
            recreated.id
        )
        assert delete_course_memory(user, course, newest.id) == {"conflict": True}


def test_delete_rolls_back_all_versions_on_flush_failure(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        user, course = uuid4().hex, uuid4().hex
        with unit_of_work():
            old = _row(user, course, "goal", "old")
            newest = _row(user, course, "goal", "new")
        selected = newest.id
        original_flush = db.session.flush

        def fail(*_args: object, **_kwargs: object) -> None:
            if any(
                isinstance(row, VariableValue) and row.deleted for row in db.session.new
            ):
                message = "injected storage failure after invalidation"
                raise RuntimeError(message)
            original_flush(*_args, **_kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(db.session, "flush", fail)
            with pytest.raises(RuntimeError, match="injected"):
                delete_course_memory(user, course, selected)
        assert not old.deleted
        assert not newest.deleted


def test_deletion_generation_advances_past_a_newer_legacy_retired_row(
    app: Flask,
) -> None:
    with app.app_context():
        user, course = uuid4().hex, uuid4().hex
        with unit_of_work():
            live = _row(user, course, "goal", "still current")
            _row(user, course, "goal", "retired version", deleted=1)
        before, deleted = course_memory_deletion_state(user, course)
        assert not deleted
        assert list_course_memory(user, course)["items"][0]["value_id"] == str(live.id)
        delete_course_memory(user, course, live.id)
        after, deleted = course_memory_deletion_state(user, course)
        assert after["goal"] > before["goal"]
        assert deleted == {"goal"}
        delete_course_memory(user, course, live.id)
        assert course_memory_deletion_state(user, course)[0] == after


def test_memory_routes_require_authentication(test_client: object) -> None:
    response = test_client.get("/api/user/course-memory?course_id=" + "a" * 32)
    assert response.get_json(force=True)["code"] != 0


@pytest.mark.parametrize(
    "query",
    [
        "",
        "course_id=",
        "course_id=bad",
        "course_id=" + "a" * 32 + "&before=-1",
        "course_id=" + "a" * 32 + "&before=0",
        "course_id=" + "a" * 32 + "&before=99999999999999999999",
    ],
)
def test_route_rejects_invalid_scope_and_cursor(
    test_client: object, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda *_: SimpleNamespace(user_id=uuid4().hex, language="en-US"),
    )
    assert (
        test_client.get("/api/user/course-memory?" + query).get_json(force=True)["code"]
        != 0
    )


def test_route_uses_authenticated_owner_and_shared_datetime_envelope(
    app: Flask, test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, course = uuid4().hex, uuid4().hex
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda *_: SimpleNamespace(user_id=user, language="en-US"),
    )
    with app.app_context(), unit_of_work():
        value = _row(user, course, "goal", "private value")
        db.session.flush()
        bid = str(value.id)
    result = test_client.get(f"/api/user/course-memory?course_id={course}").get_json(
        force=True
    )
    assert result["code"] == 0
    assert result["data"]["items"][0]["updated_at"].endswith("Z")
    forged = test_client.post(
        "/api/user/course-memory",
        json={"course_id": course, "value_id": bid, "user_bid": user},
    ).get_json(force=True)
    assert forged["code"] != 0
    result = test_client.post(
        "/api/user/course-memory", json={"course_id": course, "value_id": bid}
    ).get_json(force=True)
    assert result == {"code": 0, "message": "success", "data": {"conflict": False}}
