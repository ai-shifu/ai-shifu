"""Real progress, session and recorder writes share the retake transaction."""

import threading
from collections.abc import Iterator
from functools import partial

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent.lesson_record import record_turn_content
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.learn.retake_execution import (
    RetakeExecution,
    owning_retake,
    stage_retake_content,
)
from flaskr.service.learn.retake_ledger import (
    configure_policy,
    get_allowance,
    reserve_attempt,
)
from flaskr.service.learn.retake_models import (
    CourseRetakePolicy,
    LessonRetakeAttempt,
    LessonRetakeRun,
)
from flaskr.service.learn.retake_policy import RetakeRuleError, RetakeState
from flaskr.service.learn.retake_recovery import stage_reset_records
from flaskr.service.learn.run.recorder import RunRecorder
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_RESET,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
)

IDENTITY = {
    "namespace": "test",
    "shifu_bid": "course",
    "user_bid": "learner",
    "outline_bid": "lesson",
}
RECORD_IDENTITY = {
    key: value for (key, value) in IDENTITY.items() if key != "namespace"
}


@pytest.fixture
def app(tmp_path: object) -> Iterator[Flask]:
    application = Flask(__name__)
    application.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path}/execution.db"
    db.init_app(application)
    with application.app_context():
        for model in (
            CourseRetakePolicy,
            LessonRetakeAttempt,
            LessonRetakeRun,
            LearnProgressRecord,
            LearnGeneratedBlock,
            LearnAgentSession,
        ):
            model.__table__.create(db.engine)
        with unit_of_work():
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid="original",
                    user_bid="learner",
                    shifu_bid="course",
                    outline_item_bid="lesson",
                    status=LEARN_STATUS_COMPLETED,
                )
            )
            db.session.add(
                LearnAgentSession(
                    agent_session_bid="original-session",
                    user_bid="learner",
                    shifu_bid="course",
                    outline_item_bid="lesson",
                    active_key=active_key_for("learner", "lesson", preview_mode=False),
                    session_data="original data",
                )
            )
            db.session.add(
                LearnAgentSession(
                    agent_session_bid="preview-session",
                    user_bid="learner",
                    shifu_bid="course",
                    outline_item_bid="lesson",
                    active_key=active_key_for("learner", "lesson", preview_mode=True),
                    session_data="preview data",
                )
            )
        with unit_of_work():
            db.session.add(
                LearnGeneratedBlock(
                    generated_block_bid="original-block",
                    progress_record_bid="original",
                    user_bid="learner",
                    shifu_bid="course",
                    outline_item_bid="lesson",
                    type=BLOCK_TYPE_MDCONTENT_VALUE,
                    role=ROLE_TEACHER,
                    generated_content="Original teaching",
                    status=1,
                )
            )
        configure_policy(application, namespace="test", shifu_bid="course", limit=2)
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


def reserve(app: Flask) -> RetakeExecution:
    (attempt_id, _) = reserve_attempt(
        app,
        **IDENTITY,
        request_id="reset-one",
        stage_reset=partial(stage_reset_records, **RECORD_IDENTITY),
    )
    return RetakeExecution(
        app=app, **IDENTITY, attempt_id=attempt_id, producer_id="producer"
    )


def new_records() -> tuple[LearnProgressRecord, LearnGeneratedBlock]:
    with unit_of_work():
        progress = LearnProgressRecord(
            progress_record_bid="replacement",
            user_bid="learner",
            shifu_bid="course",
            outline_item_bid="lesson",
            status=LEARN_STATUS_IN_PROGRESS,
        )
        block = LearnGeneratedBlock(
            generated_block_bid="new-block",
            progress_record_bid="replacement",
            user_bid="learner",
            shifu_bid="course",
            outline_item_bid="lesson",
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            role=ROLE_TEACHER,
        )
        db.session.add_all([progress, block])
    return (progress, block)


def assert_restored(app: Flask, attempt_id: str) -> None:
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="original")
            .one()
            .status
            == LEARN_STATUS_COMPLETED
        )
        assert (
            LearnAgentSession.query.filter_by(agent_session_bid="original-session")
            .one()
            .deleted
            == 0
        )
        assert (
            LearnAgentSession.query.filter_by(agent_session_bid="preview-session")
            .one()
            .deleted
            == 0
        )
        attempt = db.session.get(LessonRetakeAttempt, attempt_id)
        assert attempt.state == RetakeState.RELEASED
        assert attempt.producer_finished_at is not None
    assert get_allowance(app, **IDENTITY).remaining == 2


def test_failure_before_content_restores_original_records_and_session(
    app: Flask,
) -> None:
    execution = reserve(app)

    def fail_run() -> None:
        with owning_retake(execution):
            new_records()
            reason = "provider failed"
            raise ValueError(reason)

    with pytest.raises(ValueError, match="provider failed"):
        fail_run()
    assert_restored(app, execution.attempt_id)
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="replacement")
            .one()
            .status
            == LEARN_STATUS_RESET
        )


@pytest.mark.parametrize("engine", ["legacy", "agent"])
def test_actual_content_writer_commits_exactly_one_retake(
    app: Flask, engine: str
) -> None:
    execution = reserve(app)
    with owning_retake(execution):
        (progress, block) = new_records()
        for text in ("First teaching", "More teaching"):
            if engine == "legacy":
                RunRecorder(app).finalize_streamed_block(
                    block,
                    text,
                    progress,
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=1,
                )
            else:
                with unit_of_work():
                    record_turn_content(generated_block_bid="new-block", content=text)
            assert get_allowance(app, **IDENTITY).used == 1
        with pytest.raises(RetakeRuleError, match="retake_in_progress"):
            reserve_attempt(app, **IDENTITY, request_id="overlap")
    assert get_allowance(app, **IDENTITY).used == 1
    reserve_attempt(app, **IDENTITY, request_id="after-stop")


def test_content_and_count_roll_back_together(app: Flask) -> None:
    execution = reserve(app)

    def fail_run() -> None:
        with owning_retake(execution):
            new_records()
            with unit_of_work():
                record_turn_content(
                    generated_block_bid="new-block", content="Not committed"
                )
                reason = "write failed"
                raise ValueError(reason)

    with pytest.raises(ValueError, match="write failed"):
        fail_run()
    assert_restored(app, execution.attempt_id)
    with app.app_context():
        assert (
            not LearnGeneratedBlock.query.filter_by(generated_block_bid="new-block")
            .one()
            .generated_content
        )


def test_error_after_partial_success_does_not_refund_or_restore(app: Flask) -> None:
    execution = reserve(app)

    def fail_run() -> None:
        with owning_retake(execution):
            (progress, block) = new_records()
            RunRecorder(app).finalize_streamed_block(
                block,
                "Saved teaching",
                progress,
                status=LEARN_STATUS_IN_PROGRESS,
                block_position=1,
            )
            reason = "tts failed"
            raise ValueError(reason)

    with pytest.raises(ValueError, match="tts failed"):
        fail_run()
    assert get_allowance(app, **IDENTITY).used == 1
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="original")
            .one()
            .status
            == LEARN_STATUS_RESET
        )
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="replacement")
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )


@pytest.mark.parametrize("kind", ["empty", "student", "error"])
def test_non_teaching_blocks_do_not_consume_opportunity(app: Flask, kind: str) -> None:
    execution = reserve(app)
    with owning_retake(execution):
        (_, block) = new_records()
        block.generated_content = "" if kind == "empty" else "Not teaching"
        if kind == "student":
            block.role = ROLE_STUDENT
        if kind == "error":
            block.type = BLOCK_TYPE_MDERRORMESSAGE_VALUE
        RunRecorder(app).save_generated_block(block)
    assert_restored(app, execution.attempt_id)


def test_reset_and_reservation_rollback_together_and_retries_do_not_reset_twice(
    app: Flask,
) -> None:

    def fail() -> dict:
        stage_reset_records(**RECORD_IDENTITY)
        reason = "snapshot failed"
        raise ValueError(reason)

    with pytest.raises(ValueError, match="snapshot failed"):
        reserve_attempt(app, **IDENTITY, request_id="failed", stage_reset=fail)
    with app.app_context():
        assert LessonRetakeAttempt.query.count() == 0
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="original")
            .one()
            .status
            == LEARN_STATUS_COMPLETED
        )
    execution = reserve(app)
    assert (
        reserve_attempt(app, **IDENTITY, request_id="reset-one", stage_reset=fail)[0]
        == execution.attempt_id
    )


def test_lost_http_client_cannot_release_live_producer(app: Flask) -> None:
    execution = reserve(app)
    (started, stop) = (threading.Event(), threading.Event())
    errors = []

    def produce() -> None:
        try:
            with owning_retake(execution):
                new_records()
                started.set()
                assert stop.wait(5)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=produce)
    thread.start()
    try:
        assert started.wait(5)
        assert get_allowance(app, **IDENTITY).reserved == 1
        with pytest.raises(RetakeRuleError, match="retake_in_progress"):
            reserve_attempt(app, **IDENTITY, request_id="second-tab")
        with app.app_context():
            assert (
                LearnProgressRecord.query.filter_by(progress_record_bid="original")
                .one()
                .status
                == LEARN_STATUS_RESET
            )
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()
    assert errors == []
    assert_restored(app, execution.attempt_id)


def test_unbound_writes_do_not_touch_ledger(app: Flask) -> None:
    with app.app_context():
        (progress, block) = new_records()
        RunRecorder(app).finalize_streamed_block(
            block,
            "First study",
            progress,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=1,
        )
        assert LessonRetakeAttempt.query.count() == 0
    assert get_allowance(app, **IDENTITY).used == 0


def test_wrong_lesson_content_does_not_charge_bound_attempt(app: Flask) -> None:
    execution = reserve(app)
    with owning_retake(execution), unit_of_work():
        stage_retake_content(
            shifu_bid="course",
            user_bid="learner",
            outline_bid="another",
            content="Not this lesson",
        )
    assert_restored(app, execution.attempt_id)


def wrapped(app: Flask, events: Iterator, **overrides: object) -> Iterator:
    from flaskr.service.learn.retake_execution import track_retake_events

    arguments = {
        "app": app,
        "shifu_bid": "course",
        "user_bid": "learner",
        "outline_bid": "lesson",
        "preview_mode": False,
        "input_type": "start",
    }
    arguments.update(overrides)
    return track_retake_events(events, **arguments)


def enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "flaskr.service.learn.retake_execution.retake_namespace", lambda _: "test"
    )


def test_generator_close_restores_after_child_finally(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    execution = reserve(app)
    closed = []

    def events() -> Iterator[str]:
        try:
            new_records()
            yield "streaming"
            yield "still streaming"
        finally:
            closed.append(True)

    stream = wrapped(app, events())
    assert next(stream) == "streaming"
    assert get_allowance(app, **IDENTITY).reserved == 1
    stream.close()
    assert closed == [True]
    assert_restored(app, execution.attempt_id)


def test_two_producers_cannot_claim_same_reserved_round(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    execution = reserve(app)
    called = []

    def events() -> Iterator[str]:
        called.append(True)
        yield "started"

    first = wrapped(app, events())
    assert next(first) == "started"
    second = wrapped(app, events())
    with pytest.raises(RetakeRuleError, match="retake_in_progress"):
        next(second)
    assert called == [True]
    first.close()
    assert_restored(app, execution.attempt_id)


@pytest.mark.parametrize(
    "override",
    [
        {"preview_mode": True},
        {"input_type": "ask"},
    ],
)
def test_preview_and_ask_leave_reserved_round_untouched(
    app: Flask, monkeypatch: pytest.MonkeyPatch, override: dict
) -> None:
    enable(monkeypatch)
    execution = reserve(app)
    assert list(wrapped(app, iter(["existing flow"]), **override)) == ["existing flow"]
    with app.app_context():
        assert (
            db.session.get(LessonRetakeAttempt, execution.attempt_id).state
            == RetakeState.RESERVED
        )


def test_generator_first_study_never_reserves(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    assert list(wrapped(app, iter(["first study"]))) == ["first study"]
    assert get_allowance(app, **IDENTITY).used == 0


def test_generator_success_charges_and_closes_once(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    execution = reserve(app)

    def events() -> Iterator[str]:
        progress, block = new_records()
        RunRecorder(app).finalize_streamed_block(
            block, "Saved", progress, status=LEARN_STATUS_IN_PROGRESS, block_position=1
        )
        yield "saved"

    assert list(wrapped(app, events())) == ["saved"]
    with app.app_context():
        row = db.session.get(LessonRetakeAttempt, execution.attempt_id)
        assert row.state == RetakeState.COMMITTED
        assert row.producer_finished_at is not None
    assert get_allowance(app, **IDENTITY).used == 1


def test_empty_first_study_does_not_become_a_paid_retake(app: Flask) -> None:
    with app.app_context(), unit_of_work():
        LearnGeneratedBlock.query.delete()
    with pytest.raises(RetakeRuleError, match="nothing_to_retake"):
        reserve(app)
    with app.app_context():
        assert LessonRetakeAttempt.query.count() == 0
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="original")
            .one()
            .status
            == LEARN_STATUS_COMPLETED
        )


def test_recovery_failure_keeps_reservation_and_does_not_partially_restore(
    app: Flask,
) -> None:
    execution = reserve(app)

    def fail_run() -> None:
        with owning_retake(execution):
            new_records()
            with unit_of_work():
                LearnAgentSession.query.filter_by(
                    agent_session_bid="original-session"
                ).delete()

    with pytest.raises(RetakeRuleError, match="recovery_session_missing"):
        fail_run()
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="original")
            .one()
            .status
            == LEARN_STATUS_RESET
        )
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="replacement")
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )
        row = db.session.get(LessonRetakeAttempt, execution.attempt_id)
        assert row.state == RetakeState.RUNNING
        assert row.producer_finished_at is None
    assert get_allowance(app, **IDENTITY).reserved == 1


@pytest.mark.parametrize(
    "override",
    [
        {"reload_generated_block_bid": "old-block"},
        {"reload_element_bid": "old-element"},
    ],
)
def test_reload_cannot_bypass_pending_retake(
    app: Flask, monkeypatch: pytest.MonkeyPatch, override: dict
) -> None:
    enable(monkeypatch)
    execution = reserve(app)
    with pytest.raises(RetakeRuleError, match="retake_in_progress"):
        list(wrapped(app, iter(["must not generate"]), **override))
    with app.app_context():
        assert (
            db.session.get(LessonRetakeAttempt, execution.attempt_id).state
            == RetakeState.RESERVED
        )


def test_first_study_and_continuation_exclude_concurrent_reset(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    first = wrapped(app, iter(["first study", "still running"]))
    assert next(first) == "first study"
    try:
        with pytest.raises(RetakeRuleError, match="retake_in_progress"):
            reserve(app)
        assert get_allowance(app, **IDENTITY).used == 0
    finally:
        first.close()
    # Once the actual producer stops, a reset is admitted normally.
    reserve(app)


def test_guard_is_held_until_child_generator_cleanup(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    observations = []

    def events() -> Iterator[str]:
        try:
            yield "first study"
        finally:
            try:
                reserve(app)
            except RetakeRuleError as exc:
                observations.append(str(exc))

    stream = wrapped(app, events())
    next(stream)
    stream.close()
    assert observations == ["retake_in_progress"]
    reserve(app)


def test_platform_repair_requires_confirmed_stop_and_exact_worker(app: Flask) -> None:
    from flaskr.service.learn.retake_ledger import claim_attempt
    from flaskr.service.learn.retake_run_guard import (
        acquire_lesson_run,
        repair_stopped_lesson_run,
    )

    execution = reserve(app)
    ownership = acquire_lesson_run(app, **IDENTITY)
    claim_attempt(
        app,
        namespace="test",
        shifu_bid="course",
        attempt_id=execution.attempt_id,
        producer_id=ownership.producer_id,
    )
    arguments = {
        **IDENTITY,
        "expected_producer_id": ownership.producer_id,
        "operator_bid": "operator",
    }
    with pytest.raises(RetakeRuleError, match="repair_requires_confirmed_stop"):
        repair_stopped_lesson_run(app, **arguments, confirmed_stopped=False)
    with pytest.raises(RetakeRuleError, match="producer_mismatch"):
        repair_stopped_lesson_run(
            app,
            **{**arguments, "expected_producer_id": "wrong"},
            confirmed_stopped=True,
        )
    repair_stopped_lesson_run(app, **arguments, confirmed_stopped=True)
    repair_stopped_lesson_run(app, **arguments, confirmed_stopped=True)
    assert_restored(app, execution.attempt_id)
    with app.app_context():
        row = LessonRetakeRun.query.one()
        assert len(row.repair_log) == 1
        assert row.repair_log[0]["operator_bid"] == "operator"
        assert row.repair_log[0]["repaired_at"].endswith("Z")


def test_stale_worker_cannot_release_new_run(app: Flask) -> None:
    from flaskr.service.learn.retake_run_guard import (
        acquire_lesson_run,
        release_lesson_run,
        repair_stopped_lesson_run,
    )

    old = acquire_lesson_run(app, **IDENTITY)
    repair_stopped_lesson_run(
        app,
        **IDENTITY,
        expected_producer_id=old.producer_id,
        operator_bid="operator",
        confirmed_stopped=True,
    )
    new = acquire_lesson_run(app, **IDENTITY)
    release_lesson_run(app, old)
    with pytest.raises(RetakeRuleError, match="retake_in_progress"):
        reserve(app)
    with pytest.raises(RetakeRuleError, match="producer_mismatch"):
        repair_stopped_lesson_run(
            app,
            **IDENTITY,
            expected_producer_id=old.producer_id,
            operator_bid="operator",
            confirmed_stopped=True,
        )
    release_lesson_run(app, new)
    reserve(app)


def test_platform_repair_keeps_delivered_attempt_charged(app: Flask) -> None:
    from flaskr.service.learn.retake_ledger import claim_attempt, finish_attempt
    from flaskr.service.learn.retake_run_guard import (
        acquire_lesson_run,
        repair_stopped_lesson_run,
    )

    execution = reserve(app)
    ownership = acquire_lesson_run(app, **IDENTITY)
    args = {
        "namespace": "test",
        "shifu_bid": "course",
        "attempt_id": execution.attempt_id,
        "producer_id": ownership.producer_id,
    }
    claim_attempt(app, **args)
    finish_attempt(app, **args, has_durable_content=True, producer_stopped=False)
    repair_stopped_lesson_run(
        app,
        **IDENTITY,
        expected_producer_id=ownership.producer_id,
        operator_bid="operator",
        confirmed_stopped=True,
    )
    with app.app_context():
        assert get_allowance(app, **IDENTITY).used == 1
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="original")
            .one()
            .status
            == LEARN_STATUS_RESET
        )
        assert LessonRetakeAttempt.query.one().producer_finished_at is not None


def test_platform_repair_rolls_back_if_original_records_cannot_be_restored(
    app: Flask,
) -> None:
    from flaskr.service.learn.retake_run_guard import (
        acquire_lesson_run,
        repair_stopped_lesson_run,
    )

    execution = reserve(app)
    ownership = acquire_lesson_run(app, **IDENTITY)
    with app.app_context(), unit_of_work():
        LearnProgressRecord.query.filter_by(progress_record_bid="original").delete()
    with pytest.raises(RetakeRuleError):
        repair_stopped_lesson_run(
            app,
            **IDENTITY,
            expected_producer_id=ownership.producer_id,
            operator_bid="operator",
            confirmed_stopped=True,
        )
    with app.app_context():
        assert (
            LessonRetakeAttempt.query.filter_by(attempt_id=execution.attempt_id)
            .one()
            .state
            == RetakeState.RESERVED
        )
        assert LessonRetakeRun.query.one().finished_at is None


@pytest.mark.parametrize(
    "reload_argument", ["reload_generated_block_bid", "reload_element_bid"]
)
def test_inline_regeneration_cannot_bypass_lesson_quota(
    app: Flask, monkeypatch: pytest.MonkeyPatch, reload_argument: str
) -> None:
    enable(monkeypatch)
    invoked = []

    def events() -> Iterator[str]:
        invoked.append(True)
        yield "should not run"

    stream = wrapped(app, events(), **{reload_argument: "original-block"})
    with pytest.raises(RetakeRuleError, match="retake_reload_not_supported"):
        next(stream)
    assert not invoked
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid="original")
            .one()
            .status
            == LEARN_STATUS_COMPLETED
        )
        assert get_allowance(app, **IDENTITY).used == 0


def test_failed_first_study_can_continue_with_zero_retake_allowance(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(monkeypatch)
    configure_policy(app, namespace="test", shifu_bid="course", limit=0)

    def failure() -> Iterator[str]:
        reason = "provider failed before teaching"
        raise ValueError(reason)
        yield  # pragma: no cover -- keep the failing producer lazy

    with pytest.raises(ValueError, match="provider failed before teaching"):
        list(wrapped(app, failure()))
    assert list(wrapped(app, iter(["continued first study"]))) == [
        "continued first study"
    ]
    allowance = get_allowance(app, **IDENTITY)
    assert allowance.used == 0
    assert allowance.reserved == 0
    with app.app_context():
        assert LessonRetakeAttempt.query.count() == 0
        assert LessonRetakeRun.query.one().finished_at is not None
