"""Learner scenarios for the minimal successful-reset limit."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING, Never

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.learn import learn_funcs
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.lesson_reset_limit import (
    LessonResetGuard,
    get_lesson_reset_status,
)
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS, LEARN_STATUS_RESET
from flaskr.service.shifu.models import AiCourseAuth, DraftShifu, PublishedOutlineItem

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask

    from tests.common.fixtures.fake_redis import FakeRedis


@pytest.fixture
def reset_course(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SimpleNamespace]:
    """Create independent synthetic learners and two lessons in the test DB."""
    course = SimpleNamespace(
        course=uuid.uuid4().hex,
        owner=uuid.uuid4().hex,
        learner=uuid.uuid4().hex,
        other_learner=uuid.uuid4().hex,
        lesson=uuid.uuid4().hex,
        other_lesson=uuid.uuid4().hex,
    )
    monkeypatch.setitem(app.config, "LESSON_RESET_LIMIT", 2)
    with app.app_context(), unit_of_work():
        db.session.add(
            DraftShifu(
                shifu_bid=course.course, created_user_bid=course.owner, deleted=0
            )
        )
        for lesson in (course.lesson, course.other_lesson):
            db.session.add(
                PublishedOutlineItem(
                    shifu_bid=course.course, outline_item_bid=lesson, deleted=0
                )
            )
    yield course
    with app.app_context(), unit_of_work():
        for model in (
            LearnAgentSession,
            LearnProgressRecord,
            PublishedOutlineItem,
            DraftShifu,
        ):
            model.query.filter_by(shifu_bid=course.course).delete()
        AiCourseAuth.query.filter_by(course_id=course.course).delete()


def start(
    app: Flask,
    course: SimpleNamespace,
    *,
    learner: str | None = None,
    lesson: str | None = None,
    siblings: int = 1,
) -> list[str]:
    """Represent first learning or learning again after a successful reset."""
    identities = [uuid.uuid4().hex for _ in range(siblings)]
    with app.app_context(), unit_of_work():
        for identity in identities:
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid=identity,
                    shifu_bid=course.course,
                    outline_item_bid=lesson or course.lesson,
                    user_bid=learner or course.learner,
                    status=LEARN_STATUS_IN_PROGRESS,
                    deleted=0,
                )
            )
    return identities


def reset(
    app: Flask,
    course: SimpleNamespace,
    *,
    request_id: str | None = None,
    learner: str | None = None,
    lesson: str | None = None,
) -> bool:
    """Use the real service reset, not an independently copied counter algorithm."""
    return learn_funcs.reset_learn_record(
        app,
        course.course,
        lesson or course.lesson,
        learner or course.learner,
        reset_request_id=request_id or uuid.uuid4().hex,
    )


def count(
    app: Flask,
    course: SimpleNamespace,
    client: object,
    *,
    learner: str | None = None,
    lesson: str | None = None,
) -> int:
    """Inspect synthetic counter data as validation evidence, not a public balance."""
    guard = LessonResetGuard(
        app,
        course.course,
        lesson or course.lesson,
        learner or course.learner,
        uuid.uuid4().hex,
    )
    raw = client.get(guard.key)
    return json.loads(raw)["count"] if raw else 0


def status(app: Flask, course: SimpleNamespace) -> dict:
    """Read the learner-visible availability contract without numerical allowance."""
    return get_lesson_reset_status(app, course.course, course.lesson, course.learner)


def test_first_learning_and_empty_reset_are_free(
    app: Flask, reset_course: SimpleNamespace, mock_redis_client: FakeRedis
) -> None:
    """Opening a lesson and resetting nothing consume no additional service."""
    assert reset(app, reset_course)
    assert count(app, reset_course, mock_redis_client) == 0
    start(app, reset_course)
    assert count(app, reset_course, mock_redis_client) == 0
    assert status(app, reset_course) == {"can_reset": True}


def test_two_successful_resets_then_block_preserves_current_content(
    app: Flask, reset_course: SimpleNamespace, mock_redis_client: FakeRedis
) -> None:
    """At a test limit of two, a third reset leaves the latest progress intact."""
    for _ in range(2):
        start(app, reset_course)
        assert reset(app, reset_course)
    current = start(app, reset_course)[0]
    with pytest.raises(AppError) as error:
        reset(app, reset_course)
    assert error.value.code == 4021
    assert count(app, reset_course, mock_redis_client) == 2
    assert status(app, reset_course) == {"can_reset": False}
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )


def test_one_reset_of_sibling_progress_rows_counts_once(
    app: Flask, reset_course: SimpleNamespace, mock_redis_client: FakeRedis
) -> None:
    """One lesson reset is one use even when Ask created sibling learning records."""
    identities = start(app, reset_course, siblings=2)
    reset(app, reset_course)
    assert count(app, reset_course, mock_redis_client) == 1
    with app.app_context():
        assert all(
            LearnProgressRecord.query.filter_by(progress_record_bid=bid).one().status
            == LEARN_STATUS_RESET
            for bid in identities
        )


@pytest.mark.parametrize("published", [False, True])
def test_learner_reset_preserves_preview_and_counts_only_published_state(
    app: Flask,
    reset_course: SimpleNamespace,
    mock_redis_client: FakeRedis,
    *,
    published: bool,
) -> None:
    """An ex-collaborator's preview alone is not a chargeable learner reset."""
    with app.app_context(), unit_of_work():
        for preview in [True, False] if published else [True]:
            db.session.add(
                LearnAgentSession(
                    user_bid=reset_course.learner,
                    shifu_bid=reset_course.course,
                    outline_item_bid=reset_course.lesson,
                    active_key=active_key_for(
                        reset_course.learner,
                        reset_course.lesson,
                        preview_mode=preview,
                    ),
                )
            )
    assert reset(app, reset_course)
    assert count(app, reset_course, mock_redis_client) == int(published)
    with app.app_context():
        assert (
            LearnAgentSession.query.filter_by(
                active_key=active_key_for(
                    reset_course.learner, reset_course.lesson, preview_mode=True
                ),
                deleted=0,
            ).count()
            == 1
        )
        assert (
            LearnAgentSession.query.filter_by(
                user_bid=reset_course.learner,
                shifu_bid=reset_course.course,
                outline_item_bid=reset_course.lesson,
                deleted=0,
            ).count()
            == 1
        )


def test_duplicate_success_cannot_clear_new_learning_or_charge_again(
    app: Flask, reset_course: SimpleNamespace, mock_redis_client: FakeRedis
) -> None:
    """A delayed retry after new learning returns success without clearing it."""
    identity = uuid.uuid4().hex
    start(app, reset_course)
    reset(app, reset_course, request_id=identity)
    current = start(app, reset_course)[0]
    reset(app, reset_course, request_id=identity)
    assert count(app, reset_course, mock_redis_client) == 1
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )


def test_independent_learner_lesson_and_course(
    app: Flask, reset_course: SimpleNamespace, mock_redis_client: FakeRedis
) -> None:
    """Using this lesson does not consume another learner's or lesson's allowance."""
    start(app, reset_course)
    reset(app, reset_course)
    assert (
        count(app, reset_course, mock_redis_client, learner=reset_course.other_learner)
        == 0
    )
    assert (
        count(app, reset_course, mock_redis_client, lesson=reset_course.other_lesson)
        == 0
    )
    other = SimpleNamespace(**{**vars(reset_course), "course": uuid.uuid4().hex})
    assert count(app, other, mock_redis_client) == 0


@pytest.mark.parametrize("collaborator", [None, "1", "2", "3", "4"])
def test_owner_and_all_active_collaborators_are_exempt(
    app: Flask,
    reset_course: SimpleNamespace,
    mock_redis_client: FakeRedis,
    collaborator: str | None,
) -> None:
    """Owner and read/edit/delete/publish collaborators can test without a quota."""
    learner = reset_course.owner if collaborator is None else reset_course.other_learner
    if collaborator is not None:
        with app.app_context(), unit_of_work():
            db.session.add(
                AiCourseAuth(
                    course_id=reset_course.course,
                    user_id=learner,
                    auth_type=json.dumps([collaborator]),
                    status=1,
                )
            )
    for _ in range(3):
        start(app, reset_course, learner=learner)
        reset(app, reset_course, learner=learner)
    assert count(app, reset_course, mock_redis_client, learner=learner) == 0


def test_revoked_or_other_course_collaboration_does_not_exempt(
    app: Flask, reset_course: SimpleNamespace, mock_redis_client: FakeRedis
) -> None:
    """Only an active collaboration on this specific course grants exemption."""
    with app.app_context(), unit_of_work():
        db.session.add_all(
            [
                AiCourseAuth(
                    course_id=reset_course.course,
                    user_id=reset_course.learner,
                    auth_type='["1"]',
                    status=0,
                ),
                AiCourseAuth(
                    course_id=uuid.uuid4().hex,
                    user_id=reset_course.learner,
                    auth_type='["2"]',
                    status=1,
                ),
            ]
        )
    start(app, reset_course)
    reset(app, reset_course)
    assert count(app, reset_course, mock_redis_client) == 1
    with app.app_context(), unit_of_work():
        AiCourseAuth.query.filter_by(user_id=reset_course.learner).delete()


def test_reset_failure_rolls_back_progress_and_consumes_nothing(
    app: Flask,
    reset_course: SimpleNamespace,
    mock_redis_client: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure after staging progress changes restores them and keeps the allowance."""
    current = start(app, reset_course)[0]

    def fail(**_kwargs: object) -> Never:
        message = "injected reset failure"
        raise RuntimeError(message)

    monkeypatch.setattr(learn_funcs, "stage_agent_session_discard", fail)
    with pytest.raises(RuntimeError, match="injected reset failure"):
        reset(app, reset_course)
    assert count(app, reset_course, mock_redis_client) == 0
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )


def test_cross_course_lesson_rejected_without_touching_progress(
    app: Flask, reset_course: SimpleNamespace, mock_redis_client: FakeRedis
) -> None:
    """A wrong course/lesson pairing cannot reset content through an alternate URL."""
    current = start(app, reset_course)[0]
    with pytest.raises(AppError) as error:
        reset(app, reset_course, lesson=uuid.uuid4().hex)
    assert error.value.code == 4004
    assert count(app, reset_course, mock_redis_client) == 0
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )


def test_counter_write_interruption_after_commit_keeps_successful_reset(
    app: Flask,
    reset_course: SimpleNamespace,
    mock_redis_client: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Document the accepted exceptional undercount without claiming SQL rollback."""
    current = start(app, reset_course)[0]

    def interrupted(*_args: object) -> Never:
        message = "injected post-commit Redis interruption"
        raise ConnectionError(message)

    monkeypatch.setattr(mock_redis_client, "eval", interrupted)
    assert reset(app, reset_course)
    assert count(app, reset_course, mock_redis_client) == 0
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_RESET
        )


def test_redis_outage_blocks_only_reset_and_preserves_progress(
    app: Flask,
    reset_course: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis failure before admission must never clear existing learning content."""
    from flaskr.service.learn import lesson_reset_limit

    current = start(app, reset_course)[0]
    monkeypatch.setattr(lesson_reset_limit, "get_redis_client", lambda: None)
    for action in (reset, status):
        with pytest.raises(AppError) as error:
            action(app, reset_course)
        assert error.value.code == 4022
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )
    # Staff reset does not acquire a Redis counter or depend on this outage.
    assert reset(app, reset_course, learner=reset_course.owner)


def test_status_does_not_acquire_or_release_an_active_reset_lock(
    app: Flask, reset_course: SimpleNamespace, mock_redis_client: FakeRedis
) -> None:
    """An advisory read during reset cannot block it or report a false outage."""
    with LessonResetGuard(
        app, reset_course.course, reset_course.lesson, reset_course.learner, "held"
    ) as guard:
        assert status(app, reset_course) == {"can_reset": True}
        guard.check_before_commit()
        assert count(app, reset_course, mock_redis_client) == 0


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        '{"count": -1, "requests": []}',
        '{"count": true, "requests": []}',
        '{"count": 1, "requests": []}',
        '{"count": 1, "requests": [42]}',
    ],
)
def test_status_rejects_malformed_counters_without_changing_them(
    app: Flask,
    reset_course: SimpleNamespace,
    mock_redis_client: FakeRedis,
    raw: str,
) -> None:
    """Read-only status preserves the same fail-closed state validation as reset."""
    guard = LessonResetGuard(
        app, reset_course.course, reset_course.lesson, reset_course.learner, "read"
    )
    mock_redis_client.set(guard.key, raw)
    with pytest.raises(AppError) as error:
        status(app, reset_course)
    assert error.value.code == 4022
    assert mock_redis_client.get(guard.key).decode() == raw


@pytest.fixture
def real_reset_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    """Optionally run a real Redis on an isolated Unix socket, with no remote data."""
    import os
    import shutil
    import subprocess
    import tempfile
    import time
    from pathlib import Path

    from flaskr.service.learn import lesson_reset_limit
    from redis import Redis

    executable = os.environ.get("TEST_REDIS_SERVER") or shutil.which("redis-server")
    if not executable:
        pytest.skip("Real Redis integration requires redis-server or TEST_REDIS_SERVER")
    with tempfile.TemporaryDirectory(prefix="lesson-reset-real-") as directory:
        socket = str(Path(directory) / "redis.sock")
        with subprocess.Popen(
            [
                executable,
                "--port",
                "0",
                "--unixsocket",
                socket,
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) as process:
            client = Redis(unix_socket_path=socket)
            try:
                for _ in range(100):
                    try:
                        if client.ping():
                            break
                    except ConnectionError:
                        pass
                    except Exception:
                        if process.poll() is not None:
                            raise
                    time.sleep(0.02)
                else:
                    pytest.fail("Isolated Redis did not start")
                monkeypatch.setattr(
                    lesson_reset_limit, "get_redis_client", lambda: client
                )
                yield client
            finally:
                client.close()
                process.terminate()
                process.wait(timeout=5)


def test_real_redis_empty_reset_retry_preserves_new_learning_without_charging(
    app: Flask,
    reset_course: SimpleNamespace,
    real_reset_redis: object,
) -> None:
    """A lost empty-reset response can be retried safely within the approved day."""
    identity = uuid.uuid4().hex
    assert reset(app, reset_course, request_id=identity)
    from flaskr.service.learn.lesson_reset_limit import normalize_reset_request_id

    guard = LessonResetGuard(
        app,
        reset_course.course,
        reset_course.lesson,
        reset_course.learner,
        normalize_reset_request_id(identity),
    )
    assert count(app, reset_course, real_reset_redis) == 0
    assert real_reset_redis.get(guard.key) is None
    assert 86390 <= real_reset_redis.ttl(guard.noop_receipt_key) <= 86400
    current = start(app, reset_course)[0]
    assert reset(app, reset_course, request_id=identity)
    assert count(app, reset_course, real_reset_redis) == 0
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )


def test_empty_reset_failure_does_not_store_a_success_receipt(
    app: Flask,
    reset_course: SimpleNamespace,
    mock_redis_client: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollback cancels even a scheduled free reset receipt."""
    original = learn_funcs._stage_lesson_reset

    def fail(*args: object, **kwargs: object) -> Never:
        original(*args, **kwargs)
        message = "injected empty reset rollback"
        raise RuntimeError(message)

    monkeypatch.setattr(learn_funcs, "_stage_lesson_reset", fail)
    with pytest.raises(RuntimeError, match="injected empty reset rollback"):
        reset(app, reset_course)
    assert not mock_redis_client._store


def test_empty_reset_receipt_expires_without_expiring_the_allowance(
    app: Flask,
    reset_course: SimpleNamespace,
    mock_redis_client: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Document the accepted late-retry boundary while retaining charged uses."""
    timestamp = [1000]
    monkeypatch.setattr(mock_redis_client, "_now", lambda: timestamp[0])
    identity = uuid.uuid4().hex
    assert reset(app, reset_course, request_id=identity)
    start(app, reset_course)
    assert reset(app, reset_course)
    current = start(app, reset_course)[0]
    timestamp[0] += 86401
    assert reset(app, reset_course, request_id=identity)
    assert count(app, reset_course, mock_redis_client) == 2
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_RESET
        )


def test_real_redis_status_preserves_an_active_reset_lock(
    app: Flask,
    reset_course: SimpleNamespace,
    real_reset_redis: object,
) -> None:
    """A real Redis status read leaves the active reset's lease and count intact."""
    with LessonResetGuard(
        app, reset_course.course, reset_course.lesson, reset_course.learner, "held"
    ) as guard:
        assert status(app, reset_course) == {"can_reset": True}
        assert real_reset_redis.get(guard.key + ":lock") == guard.token.encode()
        guard.check_before_commit()
        guard.record_success()
        assert status(app, reset_course) == {"can_reset": True}
        assert count(app, reset_course, real_reset_redis) == 1
    assert real_reset_redis.get(guard.key + ":lock") is None


def test_real_redis_concurrent_guard_and_successful_retry(
    app: Flask,
    reset_course: SimpleNamespace,
    real_reset_redis: object,
) -> None:
    """The actual guard and Lua admit only the configured number concurrently."""
    from concurrent.futures import ThreadPoolExecutor

    def attempt(_index: int) -> int:
        try:
            with LessonResetGuard(
                app,
                reset_course.course,
                reset_course.lesson,
                reset_course.learner,
                uuid.uuid4().hex,
            ) as guard:
                guard.check_before_commit()
                guard.record_success()
        except AppError as error:
            return error.code
        else:
            return 0

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(attempt, range(24)))
    assert outcomes.count(0) == 2
    assert set(outcomes) == {0, 4021}
    guard = LessonResetGuard(
        app,
        reset_course.course,
        reset_course.lesson,
        reset_course.learner,
        uuid.uuid4().hex,
    )
    state = json.loads(real_reset_redis.get(guard.key))
    assert state["count"] == 2
    assert real_reset_redis.ttl(guard.key) == -1
    with LessonResetGuard(
        app,
        reset_course.course,
        reset_course.lesson,
        reset_course.learner,
        state["requests"][0],
    ) as retry:
        assert retry.duplicate
    assert json.loads(real_reset_redis.get(guard.key)) == state


def test_real_redis_renews_slow_reset_lease(
    app: Flask,
    reset_course: SimpleNamespace,
    real_reset_redis: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal slow SQL work retains the guard rather than admitting another reset."""
    import time

    from flaskr.service.learn import lesson_reset_limit

    monkeypatch.setattr(lesson_reset_limit, "_LOCK_SECONDS", 1)
    with LessonResetGuard(
        app,
        reset_course.course,
        reset_course.lesson,
        reset_course.learner,
        uuid.uuid4().hex,
    ) as guard:
        time.sleep(1.5)
        assert real_reset_redis.get(guard.key + ":lock") == guard.token.encode()
        guard.check_before_commit()
        guard.record_success()
    assert count(app, reset_course, real_reset_redis) == 1


def test_real_redis_lost_guard_rolls_back_progress_before_commit(
    app: Flask,
    reset_course: SimpleNamespace,
    real_reset_redis: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing admission before commit preserves content and consumes no use."""
    current = start(app, reset_course)[0]
    original = learn_funcs.stage_agent_session_discard
    key = LessonResetGuard(
        app,
        reset_course.course,
        reset_course.lesson,
        reset_course.learner,
        uuid.uuid4().hex,
    ).key

    def lose_lock(**kwargs: object) -> object:
        result = original(**kwargs)
        real_reset_redis.delete(key + ":lock")
        return result

    monkeypatch.setattr(learn_funcs, "stage_agent_session_discard", lose_lock)
    with pytest.raises(AppError) as error:
        reset(app, reset_course)
    assert error.value.code == 4022
    assert count(app, reset_course, real_reset_redis) == 0
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=current)
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )
