"""Answer follow-up questions without the 1.0 script run context."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.ask import (
    FollowUpCancelledError,
    follow_up_events,
    follow_up_run,
)
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
)
from flaskr.service.shifu.consts import BLOCK_TYPE_MDASK_VALUE
from flaskr.service.shifu.models import DraftShifu, PublishedOutlineItem, PublishedShifu

from tests.service.learn import published_course as revision
from tests.service.learn.test_run_published_follow_up import (
    follow_up_dependencies,  # noqa: F401 - pytest fixture
)

runtime_dependencies = revision.runtime_dependencies


@pytest.fixture
def ask_runtime(
    monkeypatch: pytest.MonkeyPatch,
    follow_up_dependencies: SimpleNamespace,  # noqa: F811 - pytest fixture
) -> SimpleNamespace:
    traces = []
    finalized = []

    def create_trace(**kwargs: object) -> tuple[MagicMock, None]:
        traces.append(kwargs)
        return MagicMock(), None

    monkeypatch.setattr(follow_up_run, "create_trace_with_root_span", create_trace)
    monkeypatch.setattr(follow_up_run, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(
        follow_up_run, "finalize_langfuse_trace", lambda **k: finalized.append(k)
    )
    monkeypatch.setattr(
        follow_up_run,
        "load_memory",
        lambda *_args, **_kwargs: SimpleNamespace(as_variables=dict),
    )
    return SimpleNamespace(
        traces=traces, finalized=finalized, calls=follow_up_dependencies
    )


def _learner(monkeypatch: pytest.MonkeyPatch, user_bid: str) -> None:
    monkeypatch.setattr(
        follow_up_run,
        "load_user_aggregate",
        lambda _bid: SimpleNamespace(
            user_id=user_bid, mobile="", email="learner@example.com"
        ),
    )


def _progress(course: SimpleNamespace, *, position: int) -> str:
    progress_bid = uuid4().hex
    with unit_of_work():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=progress_bid,
                shifu_bid=course.course_bid,
                outline_item_bid=course.outline_bid,
                user_bid=course.user_bid,
                status=LEARN_STATUS_IN_PROGRESS,
                block_position=position,
            )
        )
    return progress_bid


def _ask(app: object, course: SimpleNamespace, **overrides: object) -> list:
    arguments = {
        "user_bid": course.user_bid,
        "outline_bid": course.outline_bid,
        "user_input": {"input": ["Explain this"]},
        "reload_generated_block_bid": None,
        "reload_element_bid": None,
        "listen": False,
        "learning_mode": "read",
        "preview_mode": False,
        "stop_event": None,
        **overrides,
    }
    return list(follow_up_events(app, **arguments))


def _ask_block(course: SimpleNamespace) -> LearnGeneratedBlock:
    # Scoped to this test's learner and lesson: the database is shared across tests.
    return LearnGeneratedBlock.query.filter_by(
        type=BLOCK_TYPE_MDASK_VALUE,
        user_bid=course.user_bid,
        outline_item_bid=course.outline_bid,
    ).one()


def test_answers_at_the_learners_position(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        progress_bid = _progress(course, position=1)
        events = _ask(app, course)

        assert any(
            e.type == GeneratedType.CONTENT and e.content == "Follow-up answer"
            for e in events
        )
        block = _ask_block(course)
        assert block.progress_record_bid == progress_bid
        assert block.position == 1
        assert block.generated_content == "Explain this"
        assert ask_runtime.calls.llm, "the follow-up reached the model"
        assert (
            "<course_prompt>\nOld lesson prompt\n</course_prompt>"
            in ask_runtime.calls.llm[-1]["messages"][0]["content"]
        )
        trace = ask_runtime.traces[-1]["trace_payload"]
        assert trace["metadata"]["scene"] == "lesson_runtime"
        assert trace["metadata"]["outline_item_bid"] == course.outline_bid


def test_an_anchored_question_is_asked_at_the_anchor_block(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        progress_bid = _progress(course, position=2)
        anchor_bid = uuid4().hex
        with unit_of_work():
            db.session.add(
                LearnGeneratedBlock(
                    generated_block_bid=anchor_bid,
                    progress_record_bid=progress_bid,
                    user_bid=course.user_bid,
                    shifu_bid=course.course_bid,
                    outline_item_bid=course.outline_bid,
                    position=0,
                    status=1,
                )
            )
        _ask(app, course, reload_generated_block_bid=anchor_bid)

        assert _ask_block(course).position == 0


def test_an_anchor_from_another_lesson_is_ignored(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        progress_bid = _progress(course, position=2)
        foreign_bid = uuid4().hex
        with unit_of_work():
            db.session.add(
                LearnGeneratedBlock(
                    generated_block_bid=foreign_bid,
                    progress_record_bid=progress_bid,
                    user_bid=course.user_bid,
                    shifu_bid=course.course_bid,
                    outline_item_bid=uuid4().hex,
                    position=0,
                    status=1,
                )
            )
        _ask(app, course, reload_generated_block_bid=foreign_bid)

        assert _ask_block(course).position == 2


def _sell_lesson(course: SimpleNamespace) -> None:
    with unit_of_work():
        PublishedShifu.query.filter_by(shifu_bid=course.course_bid).update(
            {"price": 10}
        )
        PublishedOutlineItem.query.filter_by(
            outline_item_bid=course.outline_bid
        ).update({"type": 402})


def test_an_unbought_paid_lesson_is_refused_before_anything_is_written(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _sell_lesson(course)
        with pytest.raises(PaidError):
            _ask(app, course)

        assert (
            LearnProgressRecord.query.filter_by(user_bid=course.user_bid).count() == 0
        )
        assert (
            LearnGeneratedBlock.query.filter_by(user_bid=course.user_bid).count() == 0
        )
        assert ask_runtime.calls.llm == []


def test_a_guest_may_ask_in_a_trial_lesson_like_the_2_0_lesson_allows(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    monkeypatch.setattr(
        follow_up_run,
        "load_user_aggregate",
        lambda _bid: SimpleNamespace(user_id=course.user_bid, mobile="", email=""),
    )
    with app.app_context():
        _ask(app, course)

        assert _ask_block(course).user_bid == course.user_bid
        assert ask_runtime.calls.llm


def test_a_question_before_the_lesson_started_creates_a_placeholder(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _ask(app, course)

        record = LearnProgressRecord.query.filter_by(
            outline_item_bid=course.outline_bid, user_bid=course.user_bid
        ).one()
        assert record.status == LEARN_STATUS_NOT_STARTED
        assert _ask_block(course).progress_record_bid == record.progress_record_bid


@pytest.mark.parametrize("preview", [False, True])
def test_a_deleted_course_is_refused(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
    preview: bool,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _progress(course, position=0)
        # The course is deleted after the request resolved its structure.
        struct = follow_up_run.get_shifu_struct(app, course.course_bid, preview)
        monkeypatch.setattr(follow_up_run, "get_shifu_struct", lambda *_args: struct)
        model = DraftShifu if preview else PublishedShifu
        with unit_of_work():
            model.query.filter_by(shifu_bid=course.course_bid).update({"deleted": 1})
        with pytest.raises(AppError) as error:
            _ask(app, course, preview_mode=preview)
        assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
        assert ask_runtime.calls.llm == []


def test_a_closed_stream_stops_the_answer(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    stop_event = threading.Event()
    stop_event.set()
    with app.app_context():
        _progress(course, position=0)
        with pytest.raises(FollowUpCancelledError):
            _ask(app, course, stop_event=stop_event)
        assert ask_runtime.calls.llm == []


def test_each_question_gets_its_own_trace_in_the_lessons_session(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    monkeypatch.setattr(follow_up_run, "get_request_id", lambda: "request-1")
    native_id = uuid4().hex
    with app.app_context():
        progress_bid = _progress(course, position=0)
        with unit_of_work():
            # The lesson's turns trace under the native id stored in its session data.
            db.session.add(
                LearnAgentSession(
                    agent_session_bid=uuid4().hex,
                    user_bid=course.user_bid,
                    shifu_bid=course.course_bid,
                    outline_item_bid=course.outline_bid,
                    session_data=json.dumps({"id": native_id}),
                    active_key=active_key_for(course.user_bid, course.outline_bid),
                )
            )
        _ask(app, course)
        _ask(app, course)

    first, second = (trace["trace_payload"] for trace in ask_runtime.traces)
    assert first["id"] != second["id"]
    assert first["id"] != "request-1"
    assert first["session_id"] == second["session_id"] == native_id
    assert first["metadata"]["request_id"] == "request-1"
    assert first["metadata"]["progress_record_bid"] == progress_bid
    assert len(ask_runtime.finalized) == 2


def test_a_question_before_the_lesson_session_exists_has_no_session(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _progress(course, position=0)
        _ask(app, course)

    assert "session_id" not in ask_runtime.traces[-1]["trace_payload"]


def test_a_tracing_outage_does_not_stop_the_answer(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies

    def outage(**_kwargs: object) -> None:
        message = "langfuse unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(follow_up_run, "create_trace_with_root_span", outage)
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _progress(course, position=0)
        events = _ask(app, course)

    assert any(
        e.type == GeneratedType.CONTENT and e.content == "Follow-up answer"
        for e in events
    )
    finalized = ask_runtime.finalized[-1]
    # The no-op handles keep the admitted trace id for usage correlation.
    assert finalized["trace"].trace_id == finalized["root_span"].trace_id
    assert finalized["trace"].trace_id


def test_a_failure_before_the_session_is_known_leaves_one_error_trace(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _sell_lesson(course)
        with pytest.raises(PaidError):
            _ask(app, course)

    assert len(ask_runtime.traces) == 1
    assert "session_id" not in ask_runtime.traces[0]["trace_payload"]
    assert len(ask_runtime.finalized) == 1
    root = ask_runtime.finalized[0]["root_span_payload"]
    assert root["level"] == "ERROR"
    assert root["status_message"] == "PaidError"
