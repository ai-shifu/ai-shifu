"""Learner scenarios for the SQL-backed lesson reset limit."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.dao.uow import autonomous_unit_of_work, unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import learn_funcs
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.lesson_reset_limit import (
    get_lesson_reset_status,
    is_reset_receipt_conflict,
)
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
from sqlalchemy.exc import IntegrityError, OperationalError

from tests.common.fixtures.model_factories import make_progress_record

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
                make_progress_record(
                    progress_record_bid=identity,
                    shifu_bid=course.bid,
                    outline_item_bid=lesson or course.lesson,
                    user_bid=learner or course.learner,
                    status=status,
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
    # A preview with no live draft session resets nothing and spends nothing; the
    # uncounted audit row for a live one is covered by the agent preview test below.
    assert [row.counted for row in reset_rows(app, course)] == [1, 1]


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


@pytest.mark.parametrize("preview_mode", [False, True])
def test_empty_reset_retry_preserves_new_learning(
    app: Flask, course: SimpleNamespace, preview_mode: bool
) -> None:
    with app.app_context(), unit_of_work():
        db.session.add(
            DraftOutlineItem(
                shifu_bid=course.bid,
                outline_item_bid=course.lesson,
                content="Teach a test lesson.",
            )
        )
    other_session = start_session(app, course, preview_mode=not preview_mode)

    request_id = "empty-reset-retry"
    assert reset(app, course, preview_mode=preview_mode, request_id=request_id)
    replacement_session = start_session(app, course, preview_mode=preview_mode)
    replacement_progress = [] if preview_mode else start(app, course)
    assert reset(app, course, preview_mode=preview_mode, request_id=request_id)

    assert live_records(app, course) == replacement_progress
    rows = reset_rows(app, course)
    assert len(rows) == 1
    assert (rows[0].counted, bool(rows[0].preview_mode)) == (0, preview_mode)
    assert rows[0].progress_record_bid == ""
    with app.app_context():
        active_sessions = LearnAgentSession.query.filter_by(
            user_bid=course.learner,
            shifu_bid=course.bid,
            outline_item_bid=course.lesson,
            deleted=0,
        ).all()
        assert {row.agent_session_bid for row in active_sessions} == {
            other_session,
            replacement_session,
        }


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
    app: Flask, course: SimpleNamespace
) -> None:
    """The 2.0 draft-preview branch returns early but still leaves an audit row."""
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


@pytest.mark.parametrize(
    ("winning_scope", "quota_used_during_conflict"),
    [
        ("same", False),
        ("another-lesson", False),
        ("another-lesson", True),
        ("preview", False),
    ],
)
def test_duplicate_reset_receipt_rolls_back_before_checking_the_winner(
    app: Flask,
    course: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    winning_scope: str,
    quota_used_during_conflict: bool,
) -> None:
    monkeypatch.setitem(app.config, "LESSON_RESET_LIMIT", 1)
    request_id = "concurrent-receipt"
    winning_lesson = (
        course.other_lesson if winning_scope == "another-lesson" else course.lesson
    )
    winning_preview = winning_scope == "preview"
    if winning_preview:
        with app.app_context(), unit_of_work():
            db.session.add(
                DraftOutlineItem(
                    shifu_bid=course.bid,
                    outline_item_bid=course.lesson,
                    content="Teach a test lesson.",
                )
            )
    assert reset(
        app,
        course,
        lesson=winning_lesson,
        preview_mode=winning_preview,
        request_id=request_id,
    )
    replacement = start(app, course)
    replacement_session = start_session(app, course)
    original_lookup = learn_funcs.find_reset_receipt
    looked_up_ids = []

    def stale_first_lookup(
        user_bid: str, receipt_id: str | None
    ) -> LearnLessonResetRecord | None:
        looked_up_ids.append(receipt_id)
        if len(looked_up_ids) == 1:
            # The first MySQL snapshot can precede the winner's commit.
            return None
        if len(looked_up_ids) == 2 and quota_used_during_conflict:
            # A different reset consumes this lesson's allowance after the failed insert.
            with autonomous_unit_of_work(app):
                learn_funcs.record_lesson_reset(
                    user_bid=course.learner,
                    shifu_bid=course.bid,
                    outline_bid=course.lesson,
                    counted=True,
                    request_id="intervening-reset",
                )
        return original_lookup(user_bid, receipt_id)

    monkeypatch.setattr(learn_funcs, "find_reset_receipt", stale_first_lookup)
    with app.app_context():
        if quota_used_during_conflict:
            with pytest.raises(AppError) as denied:
                reset(app, course, request_id=request_id)
            assert denied.value.code == ERROR_CODE["server.learn.resetLimitReached"]
        else:
            assert reset(app, course, request_id=request_id)
    assert len(looked_up_ids) == (2 if winning_scope == "same" else 3)
    if winning_scope != "same":
        assert looked_up_ids[-1] is None

    kept_learning = winning_scope == "same" or quota_used_during_conflict
    assert live_records(app, course) == (replacement if kept_learning else [])
    rows = reset_rows(app, course)
    assert (rows[0].outline_item_bid, rows[0].counted, bool(rows[0].preview_mode)) == (
        winning_lesson,
        0,
        winning_preview,
    )
    if winning_scope == "same":
        assert len(rows) == 1
    else:
        assert len(rows) == 2
        assert (rows[1].outline_item_bid, rows[1].counted, rows[1].preview_mode) == (
            course.lesson,
            1,
            0,
        )
        assert rows[1].request_id == (
            "intervening-reset" if quota_used_during_conflict else None
        )
    with app.app_context():
        session = LearnAgentSession.query.filter_by(
            agent_session_bid=replacement_session
        ).one()
        assert session.active_key == (
            active_key_for(course.learner, course.lesson) if kept_learning else None
        )


@pytest.mark.parametrize("retry", [True, False])
def test_quota_denial_checks_for_a_concurrent_matching_reset_receipt(
    app: Flask,
    course: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    retry: bool,
) -> None:
    monkeypatch.setitem(app.config, "LESSON_RESET_LIMIT", 1)
    start(app, course)
    assert reset(app, course, request_id="last-reset")
    replacement = start(app, course)
    original_lookup = learn_funcs.find_reset_receipt
    reads = 0

    def stale_first_lookup(
        user_bid: str, receipt_id: str | None
    ) -> LearnLessonResetRecord | None:
        nonlocal reads
        reads += 1
        return None if reads == 1 else original_lookup(user_bid, receipt_id)

    monkeypatch.setattr(learn_funcs, "find_reset_receipt", stale_first_lookup)
    monkeypatch.setattr(
        learn_funcs,
        "record_lesson_reset",
        lambda **_: pytest.fail("Expected quota denial before the receipt insert"),
    )
    with app.app_context():
        if retry:
            assert reset(app, course, request_id="last-reset")
        else:
            with pytest.raises(AppError) as denied:
                reset(app, course, request_id="another-reset")
            assert denied.value.code == ERROR_CODE["server.learn.resetLimitReached"]
    assert reads == 2
    assert live_records(app, course) == replacement
    assert [row.counted for row in reset_rows(app, course)] == [1]


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        ("learn_lesson_reset_records.uq_learn_lesson_reset_records_request", True),
        ("learn_lesson_reset_records.PRIMARY", False),
    ],
)
def test_mysql_reset_receipt_conflict_requires_the_request_index(
    index: str, expected: bool
) -> None:
    original = Exception(1062, f"Duplicate entry 'test' for key '{index}'")
    assert is_reset_receipt_conflict(IntegrityError(None, None, original)) is expected


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


def test_reset_retries_the_whole_transaction_after_a_deadlock(
    app: Flask, course: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deadlocked ledger insert is rolled back and the reset reruns from the top."""
    real_record = learn_funcs.record_lesson_reset
    calls = {"n": 0}

    def flaky_record(**kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            statement = "INSERT INTO learn_lesson_reset_records"
            deadlock = Exception(1213, "Deadlock found")
            raise OperationalError(statement, {}, deadlock)
        return real_record(**kwargs)

    monkeypatch.setattr(learn_funcs, "record_lesson_reset", flaky_record)
    start(app, course)
    assert reset(app, course, request_id="deadlocked-once") is True
    assert calls["n"] == 2
    assert live_records(app, course) == []
    rows = reset_rows(app, course)
    assert len(rows) == 1
    assert rows[0].counted == 1
