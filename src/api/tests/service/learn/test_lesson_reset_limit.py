"""Learner scenarios for the SQL-backed lesson reset limit."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.learn import learn_funcs
from flaskr.service.learn.agent import routing
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.lesson_reset_limit import get_lesson_reset_status
from flaskr.service.learn.models import LearnLessonResetRecord, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


@pytest.fixture
def course(app: Flask, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    """Create one owned course with two published lessons and a limit of two."""
    course = SimpleNamespace(
        bid=uuid.uuid4().hex,
        owner=uuid.uuid4().hex,
        learner=uuid.uuid4().hex,
        lesson=uuid.uuid4().hex,
        other_lesson=uuid.uuid4().hex,
    )
    monkeypatch.setitem(app.config, "LESSON_RESET_LIMIT", 2)
    with app.app_context(), unit_of_work():
        db.session.add(
            DraftShifu(shifu_bid=course.bid, created_user_bid=course.owner, deleted=0)
        )
        for lesson in (course.lesson, course.other_lesson):
            db.session.add(
                PublishedOutlineItem(
                    shifu_bid=course.bid, outline_item_bid=lesson, deleted=0
                )
            )
    yield course
    with app.app_context(), unit_of_work():
        for model in (
            LearnLessonResetRecord,
            LearnAgentSession,
            LearnProgressRecord,
            PublishedOutlineItem,
            DraftOutlineItem,
            DraftShifu,
        ):
            model.query.filter_by(shifu_bid=course.bid).delete()
        AiCourseAuth.query.filter_by(course_id=course.bid).delete()


def start(
    app: Flask,
    course: SimpleNamespace,
    *,
    learner: str | None = None,
    lesson: str | None = None,
    siblings: int = 1,
    status: int = LEARN_STATUS_IN_PROGRESS,
) -> list[str]:
    """Represent first learning or learning again after a reset."""
    identities = [uuid.uuid4().hex for _ in range(siblings)]
    with app.app_context(), unit_of_work():
        for identity in identities:
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid=identity,
                    shifu_bid=course.bid,
                    outline_item_bid=lesson or course.lesson,
                    user_bid=learner or course.learner,
                    status=status,
                    deleted=0,
                )
            )
    return identities


def start_session(
    app: Flask, course: SimpleNamespace, *, preview_mode: bool = False
) -> str:
    """Represent a 2.0 lesson whose state lives only in its agent session."""
    identity = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnAgentSession(
                agent_session_bid=identity,
                user_bid=course.learner,
                shifu_bid=course.bid,
                outline_item_bid=course.lesson,
                session_data="{}",
                schema_version=1,
                pydantic_ai_version="test",
                turn=0,
                finished=0,
                deleted=0,
                active_key=active_key_for(
                    course.learner, course.lesson, preview_mode=preview_mode
                ),
            )
        )
    return identity


def reset(
    app: Flask,
    course: SimpleNamespace,
    *,
    request_id: str | None = None,
    learner: str | None = None,
    lesson: str | None = None,
    preview_mode: bool = False,
) -> bool:
    return learn_funcs.reset_learn_record(
        app,
        course.bid,
        lesson or course.lesson,
        learner or course.learner,
        preview_mode=preview_mode,
        reset_request_id=request_id,
    )


def live_records(app: Flask, course: SimpleNamespace) -> list[str]:
    with app.app_context():
        return [
            row.progress_record_bid
            for row in LearnProgressRecord.query.filter(
                LearnProgressRecord.shifu_bid == course.bid,
                LearnProgressRecord.outline_item_bid == course.lesson,
                LearnProgressRecord.user_bid == course.learner,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            ).all()
        ]


def reset_rows(
    app: Flask, course: SimpleNamespace, *, learner: str | None = None
) -> list[LearnLessonResetRecord]:
    with app.app_context():
        rows = (
            LearnLessonResetRecord.query.filter_by(
                shifu_bid=course.bid, user_bid=learner or course.learner
            )
            .order_by(LearnLessonResetRecord.id)
            .all()
        )
        db.session.expunge_all()
        return rows


def status(app: Flask, course: SimpleNamespace, **kwargs: object) -> bool:
    return get_lesson_reset_status(
        app, course.bid, course.lesson, course.learner, **kwargs
    )["can_reset"]


def test_first_learning_and_empty_reset_cost_nothing(
    app: Flask, course: SimpleNamespace
) -> None:
    assert status(app, course) is True
    assert reset(app, course) is True
    assert reset_rows(app, course) == []
    assert status(app, course) is True


def test_effective_resets_are_recorded_until_the_limit(
    app: Flask, course: SimpleNamespace
) -> None:
    first = start(app, course, siblings=2)
    assert reset(app, course) is True
    assert live_records(app, course) == []
    rows = reset_rows(app, course)
    assert [row.counted for row in rows] == [1]
    assert rows[0].progress_record_bid == first[-1]
    assert rows[0].preview_mode == 0

    start(app, course)
    assert reset(app, course) is True
    assert status(app, course) is True  # nothing chargeable is live yet

    kept = start(app, course)
    assert status(app, course) is False
    with pytest.raises(AppError) as blocked:
        reset(app, course)
    assert blocked.value.code == 4021
    assert live_records(app, course) == kept
    assert len(reset_rows(app, course)) == 2


def test_limit_zero_means_unlimited(
    app: Flask, course: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "LESSON_RESET_LIMIT", 0)
    for _ in range(3):
        start(app, course)
        assert reset(app, course) is True
    assert status(app, course) is True
    rows = reset_rows(app, course)
    assert len(rows) == 3
    assert {row.counted for row in rows} == {0}


def test_lessons_and_learners_are_independent(
    app: Flask, course: SimpleNamespace
) -> None:
    other_learner = uuid.uuid4().hex
    for _ in range(2):
        start(app, course)
        reset(app, course)
    start(app, course)
    assert status(app, course) is False

    start(app, course, lesson=course.other_lesson)
    assert reset(app, course, lesson=course.other_lesson) is True
    start(app, course, learner=other_learner)
    assert reset(app, course, learner=other_learner) is True


def test_owner_and_collaborators_are_recorded_but_not_limited(
    app: Flask, course: SimpleNamespace
) -> None:
    collaborator = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        db.session.add(
            AiCourseAuth(
                course_auth_id=uuid.uuid4().hex,
                course_id=course.bid,
                user_id=collaborator,
                auth_type='["view"]',
                status=1,
            )
        )
    for staff in (course.owner, collaborator):
        for _ in range(3):
            start(app, course, learner=staff)
            assert reset(app, course, learner=staff) is True
        rows = reset_rows(app, course, learner=staff)
        assert len(rows) == 3
        assert {row.counted for row in rows} == {0}
    assert (
        get_lesson_reset_status(app, course.bid, course.lesson, course.owner)[
            "can_reset"
        ]
        is True
    )


def test_retrying_a_landed_reset_neither_clears_new_learning_nor_charges(
    app: Flask, course: SimpleNamespace
) -> None:
    start(app, course)
    assert reset(app, course, request_id="trace-1") is True
    resumed = start(app, course)
    assert reset(app, course, request_id="trace-1") is True
    assert live_records(app, course) == resumed
    assert len(reset_rows(app, course)) == 1
    assert reset(app, course, request_id="trace-2") is True
    assert live_records(app, course) == []
    assert len(reset_rows(app, course)) == 2


def test_agent_session_counts_as_learning_state(
    app: Flask, course: SimpleNamespace
) -> None:
    start_session(app, course)
    assert reset(app, course) is True
    rows = reset_rows(app, course)
    assert len(rows) == 1
    assert rows[0].progress_record_bid == ""
    with app.app_context():
        assert (
            LearnAgentSession.query.filter_by(shifu_bid=course.bid, deleted=0).count()
            == 0
        )


def test_learner_reset_leaves_the_draft_preview_session_alone(
    app: Flask, course: SimpleNamespace
) -> None:
    preview = start_session(app, course, preview_mode=True)
    assert reset(app, course) is True
    assert reset_rows(app, course) == []
    with app.app_context():
        row = LearnAgentSession.query.filter_by(agent_session_bid=preview).one()
        assert row.deleted == 0
        assert row.active_key is not None


def test_preview_reset_is_not_counted_and_status_is_open(
    app: Flask, course: SimpleNamespace
) -> None:
    for _ in range(2):
        start(app, course)
        reset(app, course)
    start(app, course)
    assert status(app, course) is False
    assert status(app, course, preview_mode=True) is True
    assert reset(app, course, preview_mode=True) is True
    rows = reset_rows(app, course)
    assert [row.counted for row in rows] == [1, 1, 0]
    assert rows[-1].preview_mode == 1


def test_lesson_outside_the_course_is_rejected(
    app: Flask, course: SimpleNamespace
) -> None:
    with pytest.raises(AppError) as rejected:
        reset(app, course, lesson=uuid.uuid4().hex)
    assert rejected.value.code == 4004
    with pytest.raises(AppError):
        get_lesson_reset_status(app, course.bid, uuid.uuid4().hex, course.learner)


def test_opened_but_ungenerated_lesson_resets_for_free(
    app: Flask, course: SimpleNamespace
) -> None:
    """Opening a 1.0 lesson only inserts placeholders; resetting them costs nothing."""
    for _ in range(2):
        start(app, course)
        reset(app, course)

    placeholder = start(app, course, status=LEARN_STATUS_NOT_STARTED)
    assert reset(app, course) is True
    assert live_records(app, course) == []
    rows = reset_rows(app, course)
    assert [row.counted for row in rows] == [1, 1, 0]
    assert rows[-1].progress_record_bid == placeholder[0]

    start(app, course, status=LEARN_STATUS_NOT_STARTED)
    start(app, course)
    with pytest.raises(AppError) as blocked:
        reset(app, course)
    assert blocked.value.code == 4021


def test_unlimited_and_exempt_resets_keep_retry_receipts(
    app: Flask, course: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost response must not let a retry clear new learning, whoever resets."""
    monkeypatch.setitem(app.config, "LESSON_RESET_LIMIT", 0)
    start(app, course)
    assert reset(app, course, request_id="lost-response") is True
    resumed = start(app, course)
    assert reset(app, course, request_id="lost-response") is True
    assert live_records(app, course) == resumed
    assert len(reset_rows(app, course)) == 1

    monkeypatch.setitem(app.config, "LESSON_RESET_LIMIT", 2)
    start(app, course, learner=course.owner)
    assert reset(app, course, learner=course.owner, request_id="owner-trace") is True
    resumed = start(app, course, learner=course.owner)
    assert reset(app, course, learner=course.owner, request_id="owner-trace") is True
    with app.app_context():
        live = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == course.owner,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).all()
        assert [row.progress_record_bid for row in live] == resumed


def test_same_trace_id_on_another_lesson_is_not_a_retry(
    app: Flask, course: SimpleNamespace
) -> None:
    start(app, course)
    assert reset(app, course, request_id="shared-trace") is True
    start(app, course, lesson=course.other_lesson)
    assert reset(app, course, lesson=course.other_lesson, request_id="shared-trace")
    rows = reset_rows(app, course)
    assert [row.outline_item_bid for row in rows] == [
        course.lesson,
        course.other_lesson,
    ]
    assert rows[1].request_id is None


def test_agent_preview_reset_is_recorded_as_uncounted(
    app: Flask, course: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 2.0 draft-preview branch returns early but still leaves an audit row."""
    monkeypatch.setattr(routing, "uses_agent_engine", lambda _bid: True)
    with app.app_context(), unit_of_work():
        db.session.add(
            DraftOutlineItem(
                shifu_bid=course.bid, outline_item_bid=course.lesson, deleted=0
            )
        )
    preview = start_session(app, course, preview_mode=True)
    assert reset(app, course, preview_mode=True) is True
    rows = reset_rows(app, course)
    assert [(row.counted, row.preview_mode) for row in rows] == [(0, 1)]
    with app.app_context():
        assert (
            LearnAgentSession.query.filter_by(agent_session_bid=preview).one().deleted
        )
    # Nothing live any more: the next preview reset is empty and leaves no row.
    assert reset(app, course, preview_mode=True) is True
    assert len(reset_rows(app, course)) == 1


def test_status_stays_open_when_nothing_chargeable_remains(
    app: Flask, course: SimpleNamespace
) -> None:
    for _ in range(2):
        start(app, course)
        reset(app, course)
    assert status(app, course) is True
    start(app, course, status=LEARN_STATUS_NOT_STARTED)
    assert status(app, course) is True
    start(app, course)
    assert status(app, course) is False
