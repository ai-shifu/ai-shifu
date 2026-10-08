"""Persistence guarantees for the reusable retake core (SQLite integration)."""

from collections.abc import Iterator

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common import AppError
from flaskr.service.learn.retake_ledger import (
    claim_attempt,
    configure_policy,
    finish_attempt,
    get_allowance,
    reserve_attempt,
)
from flaskr.service.learn.retake_models import (
    CourseRetakePolicy,
    LessonRetakeAttempt,
    LessonRetakeRun,
)
from flaskr.service.learn.retake_policy import RetakeRuleError, RetakeState
from flaskr.service.shifu.models import DraftShifu, PublishedShifu

BASE = {"namespace": "test", "shifu_bid": "course"}
LEARNER = {**BASE, "user_bid": "learner", "outline_bid": "lesson-a"}


@pytest.fixture
def app(tmp_path: object) -> Iterator[Flask]:
    """Use an isolated SQL database without booting providers or worker services."""
    application = Flask(__name__)
    application.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path}/retakes.db"
    db.init_app(application)
    with application.app_context():
        # Test-only schema; runtime installation uses the versioned migration.
        CourseRetakePolicy.__table__.create(db.engine)
        LessonRetakeAttempt.__table__.create(db.engine)
        LessonRetakeRun.__table__.create(db.engine)
        DraftShifu.__table__.create(db.engine)
        PublishedShifu.__table__.create(db.engine)
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture(autouse=True)
def clean_ledger(app: Flask) -> Iterator[None]:
    with app.app_context(), unit_of_work():
        LessonRetakeAttempt.query.delete()
        CourseRetakePolicy.query.delete()
    yield
    with app.app_context(), unit_of_work():
        LessonRetakeAttempt.query.delete()
        CourseRetakePolicy.query.delete()


def complete(app: Flask, request_id: str = "one") -> str:
    """Simulate a round reaching its successful durable-content boundary."""
    attempt_id, _ = reserve_attempt(app, **LEARNER, request_id=request_id)
    claim_attempt(app, **BASE, attempt_id=attempt_id, producer_id="worker")
    finish_attempt(
        app,
        **BASE,
        attempt_id=attempt_id,
        producer_id="worker",
        has_durable_content=True,
        producer_stopped=True,
    )
    return attempt_id


def test_unconfigured_course_has_no_policy(app: Flask) -> None:
    assert get_allowance(app, **LEARNER) is None
    with pytest.raises(RetakeRuleError, match="policy_not_enabled"):
        reserve_attempt(app, **LEARNER, request_id="one")


def test_zero_prevents_reservation(app: Flask) -> None:
    configure_policy(app, **BASE, limit=0)
    with pytest.raises(RetakeRuleError, match="retake_limit_reached"):
        reserve_attempt(app, **LEARNER, request_id="one")
    with app.app_context():
        assert LessonRetakeAttempt.query.count() == 0


def test_success_and_repeated_http_request_count_once(app: Flask) -> None:
    configure_policy(app, **BASE, limit=1)
    attempt_id = complete(app)
    assert reserve_attempt(app, **LEARNER, request_id="one") == (
        attempt_id,
        RetakeState.COMMITTED,
    )
    assert get_allowance(app, **LEARNER).used == 1
    with pytest.raises(RetakeRuleError, match="retake_limit_reached"):
        reserve_attempt(app, **LEARNER, request_id="two")


def test_new_request_cannot_start_another_pending_round(app: Flask) -> None:
    configure_policy(app, **BASE, limit=5)
    first = reserve_attempt(app, **LEARNER, request_id="one")
    assert reserve_attempt(app, **LEARNER, request_id="one") == first
    with pytest.raises(RetakeRuleError, match="retake_in_progress"):
        reserve_attempt(app, **LEARNER, request_id="two")
    assert get_allowance(app, **LEARNER).reserved == 1


def test_lessons_learners_and_deployments_are_independent(app: Flask) -> None:
    configure_policy(app, **BASE, limit=1)
    complete(app)
    for values in (
        {**LEARNER, "outline_bid": "lesson-b"},
        {**LEARNER, "user_bid": "another"},
    ):
        assert get_allowance(app, **values).remaining == 1
        reserve_attempt(app, **values, request_id="one")
    assert get_allowance(app, **{**LEARNER, "namespace": "production"}) is None
    configure_policy(app, namespace="production", shifu_bid="course", limit=3)
    assert get_allowance(app, **{**LEARNER, "namespace": "production"}).remaining == 3


def test_policy_changes_preserve_usage_and_inflight_attempt(app: Flask) -> None:
    configure_policy(app, **BASE, limit=2)
    complete(app)
    pending, _ = reserve_attempt(app, **LEARNER, request_id="two")
    claim_attempt(app, **BASE, attempt_id=pending, producer_id="worker")
    configure_policy(app, **BASE, limit=0)
    finish_attempt(
        app,
        **BASE,
        attempt_id=pending,
        producer_id="worker",
        has_durable_content=True,
        producer_stopped=False,
    )
    configure_policy(app, **BASE, limit=None)
    assert get_allowance(app, **LEARNER).used == 2
    configure_policy(app, **BASE, limit=3)
    assert get_allowance(app, **LEARNER).remaining == 1


def test_failure_releases_once_and_old_request_cannot_resurrect(app: Flask) -> None:
    configure_policy(app, **BASE, limit=1)
    attempt_id, _ = reserve_attempt(app, **LEARNER, request_id="one")
    claim_attempt(app, **BASE, attempt_id=attempt_id, producer_id="worker")
    arguments = {
        **BASE,
        "attempt_id": attempt_id,
        "producer_id": "worker",
        "has_durable_content": False,
        "producer_stopped": True,
    }
    assert finish_attempt(app, **arguments) == RetakeState.RELEASED
    assert finish_attempt(app, **arguments) == RetakeState.RELEASED
    assert get_allowance(app, **LEARNER).remaining == 1
    assert reserve_attempt(app, **LEARNER, request_id="one")[1] == RetakeState.RELEASED
    complete(app, request_id="two")


def test_wrong_worker_cannot_finalize(app: Flask) -> None:
    configure_policy(app, **BASE, limit=1)
    attempt_id, _ = reserve_attempt(app, **LEARNER, request_id="one")
    claim_attempt(app, **BASE, attempt_id=attempt_id, producer_id="worker")
    with pytest.raises(RetakeRuleError, match="producer_mismatch"):
        finish_attempt(
            app,
            **BASE,
            attempt_id=attempt_id,
            producer_id="stale-worker",
            has_durable_content=False,
            producer_stopped=True,
        )
    assert get_allowance(app, **LEARNER).reserved == 1


def test_persistence_failure_rolls_back_content_and_count(app: Flask) -> None:
    configure_policy(app, **BASE, limit=1)
    attempt_id, _ = reserve_attempt(app, **LEARNER, request_id="one")
    claim_attempt(app, **BASE, attempt_id=attempt_id, producer_id="worker")

    def broken_stage() -> None:
        policy = db.session.get(CourseRetakePolicy, ("test", "course"))
        policy.lesson_limit = 99
        db.session.flush()
        message = "simulated content persistence failure"
        raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="simulated content"):
        finish_attempt(
            app,
            **BASE,
            attempt_id=attempt_id,
            producer_id="worker",
            has_durable_content=True,
            producer_stopped=False,
            stage=broken_stage,
        )
    allowance = get_allowance(app, **LEARNER)
    assert allowance.limit == 1
    assert allowance.used == 0
    assert allowance.reserved == 1


def test_terminal_retry_does_not_repeat_content_or_restoration(app: Flask) -> None:
    configure_policy(app, **BASE, limit=1)
    attempt_id = complete(app)

    def must_not_run() -> None:
        pytest.fail("terminal retry replayed the content mutation")

    finish_attempt(
        app,
        **BASE,
        attempt_id=attempt_id,
        producer_id="worker",
        has_durable_content=True,
        producer_stopped=False,
        stage=must_not_run,
    )


def test_same_request_id_is_not_shared_between_lessons(app: Flask) -> None:
    configure_policy(app, **BASE, limit=1)
    first, _ = reserve_attempt(app, **LEARNER, request_id="one")
    other, _ = reserve_attempt(
        app, **{**LEARNER, "outline_bid": "lesson-b"}, request_id="one"
    )
    assert first != other


def test_snapshot_timestamp_does_not_restart_on_edit(app: Flask) -> None:
    configure_policy(app, **BASE, limit=2)
    with app.app_context():
        started = db.session.get(CourseRetakePolicy, ("test", "course")).created_at
    configure_policy(app, **BASE, limit=4)
    with app.app_context():
        assert (
            db.session.get(CourseRetakePolicy, ("test", "course")).created_at == started
        )


def test_teacher_first_save_starts_counting_and_adjustments_preserve_usage(
    app: Flask,
) -> None:
    assert get_allowance(app, **LEARNER) is None
    configure_policy(app, **BASE, limit=2)
    assert get_allowance(app, **LEARNER).remaining == 2
    complete(app)
    assert get_allowance(app, **LEARNER).remaining == 1
    other = {**LEARNER, "outline_bid": "lesson-b"}
    assert get_allowance(app, **other).remaining == 2
    configure_policy(app, **BASE, limit=4)
    assert get_allowance(app, **LEARNER).used == 1
    assert get_allowance(app, **LEARNER).remaining == 3
    configure_policy(app, **BASE, limit=0)
    assert get_allowance(app, **LEARNER).used == 1
    with pytest.raises(RetakeRuleError, match="retake_limit_reached"):
        reserve_attempt(app, **LEARNER, request_id="after-reduction")


@pytest.mark.parametrize("old_limit", [None, 0, 2, 50])
def test_default_ten_preserves_usage_and_blocks_eleventh(
    app: Flask, old_limit: int | None
) -> None:
    from flaskr.service.learn.retake_ledger import ensure_default_policy

    configure_policy(app, **BASE, limit=old_limit)
    ensure_default_policy(app, **BASE)
    complete(app, "first")
    ensure_default_policy(app, **BASE)
    assert get_allowance(app, **LEARNER).used == 1
    assert get_allowance(app, **LEARNER).remaining == 9
    for index in range(1, 10):
        complete(app, str(index))
    ensure_default_policy(app, **BASE)
    assert get_allowance(app, **LEARNER).remaining == 0
    with pytest.raises(RetakeRuleError, match="retake_limit_reached"):
        reserve_attempt(app, **LEARNER, request_id="eleventh")
    assert get_allowance(app, **{**LEARNER, "outline_bid": "lesson-b"}).remaining == 10


def test_default_initializes_without_teacher_and_status_hides_balance(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn import retake_service

    monkeypatch.setattr(retake_service, "retake_namespace", lambda _: "test")
    identity = {key: value for key, value in LEARNER.items() if key != "namespace"}
    assert retake_service.read_status(app, **identity) == {
        "available": True,
        "allowed": True,
        "in_progress": False,
        "quota_exempt": False,
    }
    assert get_allowance(app, **LEARNER).limit == 10
    assert retake_service.read_policy(app, "course")["available"] is False
    preview = retake_service.read_status(app, **identity, preview_mode=True)
    assert preview == {
        "available": False,
        "allowed": True,
        "in_progress": False,
        "quota_exempt": False,
    }


def test_retired_teacher_write_is_rejected_without_changing_history(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn import retake_service

    configure_policy(app, **BASE, limit=10)
    complete(app)

    def reject(key: str) -> None:
        raise ValueError(key)

    monkeypatch.setattr(retake_service, "raise_error", reject)
    with pytest.raises(ValueError, match="retakeUnavailable"):
        retake_service.update_policy(app, "course", 100)
    allowance = get_allowance(app, **LEARNER)
    assert (allowance.limit, allowance.used) == (10, 1)


@pytest.mark.parametrize("published_only", [False, True])
def test_course_owner_can_retake_after_ten_without_erasing_history(
    app: Flask, monkeypatch: pytest.MonkeyPatch, published_only: bool
) -> None:
    from flaskr.service.learn import retake_service

    monkeypatch.setattr(retake_service, "retake_namespace", lambda _: "test")
    monkeypatch.setattr(
        retake_service, "stage_reset_records", lambda **_kwargs: {"version": 1}
    )
    with app.app_context(), unit_of_work():
        model = PublishedShifu if published_only else DraftShifu
        db.session.add(model(shifu_bid="course", created_user_bid="learner"))
    configure_policy(app, **BASE, limit=10)
    for index in range(10):
        complete(app, str(index))
    identity = {key: value for key, value in LEARNER.items() if key != "namespace"}
    assert retake_service.read_status(app, **identity) == {
        "available": True,
        "allowed": True,
        "in_progress": False,
        "quota_exempt": True,
    }
    assert retake_service.try_limited_reset(
        app, **identity, request_id="owner-eleventh"
    )
    assert (
        get_allowance(app, **LEARNER).used,
        get_allowance(app, **LEARNER).reserved,
    ) == (10, 1)
    assert retake_service.read_status(app, **identity)["in_progress"] is True
    # Unlimited does not allow a second simultaneous round.
    with pytest.raises(AppError, match="retakeInProgress"):
        retake_service.try_limited_reset(app, **identity, request_id="owner-concurrent")


def test_another_teacher_is_not_exempt_from_this_course(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn import retake_service

    monkeypatch.setattr(retake_service, "retake_namespace", lambda _: "test")
    with app.app_context(), unit_of_work():
        db.session.add(DraftShifu(shifu_bid="course", created_user_bid="actual-owner"))
        db.session.add(DraftShifu(shifu_bid="other-course", created_user_bid="learner"))
    configure_policy(app, **BASE, limit=10)
    for index in range(10):
        complete(app, str(index))
    identity = {key: value for key, value in LEARNER.items() if key != "namespace"}
    assert retake_service.read_status(app, **identity) == {
        "available": True,
        "allowed": False,
        "in_progress": False,
        "quota_exempt": False,
    }
    with pytest.raises(AppError, match="retakeLimitReached"):
        retake_service.try_limited_reset(app, **identity, request_id="eleventh")
