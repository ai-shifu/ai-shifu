"""Reading a learner's answers: which scope wins, and what stays out of the way."""

from __future__ import annotations

import pytest
from flaskr.dao import db
from flaskr.service.learn.memory import load_learner_memory
from flaskr.service.profile.models import VariableValue

USER = "learner-1"
COURSE = "course-a"
OTHER = "course-b"


def add_value(
    key: str, value: str, shifu_bid: str, user_bid: str = USER
) -> VariableValue:
    """Append a value the way a lesson does: a new row, never an update."""
    row = VariableValue(
        variable_value_bid=f"v{VariableValue.query.count() + 1:04d}",
        variable_bid=f"def-{key}",
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        key=key,
        value=value,
        deleted=0,
    )
    db.session.add(row)
    db.session.commit()
    return row


@pytest.fixture(autouse=True)
def _clean(app: object):  # noqa: ANN202 - pytest fixture
    with app.app_context():
        VariableValue.query.delete()
        db.session.commit()
        yield
        VariableValue.query.delete()
        db.session.commit()


def test_the_newest_row_wins(app: object) -> None:
    with app.app_context():
        add_value("mood", "一般", COURSE)
        add_value("mood", "开心", COURSE)
        memory = load_learner_memory(app, USER, shifu_bid=COURSE)
    assert memory.get("mood") == "开心"


def test_a_course_value_beats_a_global_one(app: object) -> None:
    with app.app_context():
        # The global row is newer, and still loses: a course's own answer is more specific.
        add_value("language", "en", COURSE)
        add_value("language", "zh", "")
        memory = load_learner_memory(app, USER, shifu_bid=COURSE)
    assert memory.get("language") == "en"
    assert memory.entries["language"].scope == "course"


def test_the_global_value_is_the_fallback(app: object) -> None:
    with app.app_context():
        add_value("sex", "female", "")
        memory = load_learner_memory(app, USER, shifu_bid=COURSE)
    assert memory.get("sex") == "female"
    assert memory.global_keys == ["sex"]


def test_another_courses_answer_is_reported_but_never_merged(app: object) -> None:
    """Report another course's answer without merging it.

    Across production data the same variable name answered in two courses disagrees 65% of the
    time, because each course writes its own options.
    """
    with app.app_context():
        add_value("learner_role", "销售管理", COURSE)
        add_value("learner_role", "司法职业院校教师", OTHER)
        memory = load_learner_memory(app, USER, shifu_bid=COURSE)

    assert memory.get("learner_role") == "销售管理"
    assert [e.value for e in memory.elsewhere["learner_role"]] == ["司法职业院校教师"]
    assert memory.elsewhere["learner_role"][0].shifu_bid == OTHER
    assert "司法职业院校教师" not in memory.as_variables().values()


def test_elsewhere_keeps_only_the_newest_row_per_course(app: object) -> None:
    with app.app_context():
        add_value("goal", "旧答案", OTHER)
        add_value("goal", "新答案", OTHER)
        memory = load_learner_memory(app, USER, shifu_bid=COURSE)
    assert [e.value for e in memory.elsewhere["goal"]] == ["新答案"]


def test_without_a_course_only_the_global_scope_is_live(app: object) -> None:
    with app.app_context():
        add_value("nickname_note", "全局值", "")
        add_value("course_only", "课程值", COURSE)
        memory = load_learner_memory(app, USER)
    assert memory.as_variables() == {"nickname_note": "全局值"}
    assert [e.value for e in memory.elsewhere["course_only"]] == ["课程值"]


def test_keys_owned_by_the_user_record_are_skipped(app: object) -> None:
    """Skip the keys the user record owns.

    Their rows here are write-only compatibility data, so trusting them would disagree with what
    the lesson actually sees.
    """
    with app.app_context():
        add_value("sys_user_nickname", "陈旧昵称", "")
        add_value("mood", "开心", COURSE)
        memory = load_learner_memory(app, USER, shifu_bid=COURSE)
        with_them = load_learner_memory(
            app, USER, shifu_bid=COURSE, include_entity_owned=True
        )

    assert "sys_user_nickname" not in memory.entries
    assert memory.as_variables() == {"mood": "开心"}
    assert with_them.get("sys_user_nickname") == "陈旧昵称"


def test_deleted_and_other_learners_rows_are_ignored(app: object) -> None:
    with app.app_context():
        add_value("mood", "别人的", COURSE, user_bid="someone-else")
        row = add_value("dropped", "已删", COURSE)
        row.deleted = 1
        db.session.commit()
        memory = load_learner_memory(app, USER, shifu_bid=COURSE)
    assert memory.as_variables() == {}
    assert memory.elsewhere == {}


def test_a_long_history_is_capped_and_says_so(app: object) -> None:
    with app.app_context():
        for i in range(6):
            add_value("mood", f"第{i}次", COURSE)
        capped = load_learner_memory(app, USER, shifu_bid=COURSE, limit=3)
        whole = load_learner_memory(app, USER, shifu_bid=COURSE, limit=100)

    assert capped.truncated is True
    assert whole.truncated is False
    # Newest first, so a cap drops old history rather than the live value.
    assert capped.get("mood") == "第5次"
