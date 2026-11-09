"""Answer follow-up questions without the 1.0 script run context."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flaskr.api import markdownflow
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.check_risk.models import RiskControlResult
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import check_text
from flaskr.service.learn.agent.lesson_source import resolve_requested_lesson_source
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.agent.session_store import stage_lesson_attempt_source
from flaskr.service.learn.ask import follow_up_run, handler
from flaskr.service.learn.ask.follow_up_run import (
    FollowUpCancelledError,
    follow_up_events,
)
from flaskr.service.learn.ask.providers import common as provider_common
from flaskr.service.learn.elements.run_adapter import ListenElementRunAdapter
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.host import lesson as host_lesson
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learn_funcs import reset_learn_record
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.memory.api import (
    MemoryUpdate,
    VariableMemoryUpdate,
    load_memory,
    stage_memory,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
)
from flaskr.service.shifu.consts import (
    ASK_MODE_DEFAULT,
    ASK_MODE_DISABLE,
    ASK_MODE_ENABLE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_publish_funcs import publish_shifu_draft
from flaskr.service.user.repository import create_user_entity

from tests.common.fixtures.model_factories import (
    make_generated_block,
    make_generated_element,
    make_progress_record,
)
from tests.service.learn import published_course as revision
from tests.service.learn.test_follow_up_memory_writeback import note_model
from tests.service.learn.test_run_published_follow_up import (
    follow_up_dependencies,  # noqa: F401 - pytest fixture
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flaskr.service.learn.ask.memory_writer import FollowUpMemoryPatch

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
            make_progress_record(
                progress_record_bid=progress_bid,
                shifu_bid=course.course_bid,
                outline_item_bid=course.outline_bid,
                user_bid=course.user_bid,
                status=LEARN_STATUS_IN_PROGRESS,
                block_position=position,
            )
        )
    return progress_bid


def _ask(
    app: object,
    course: SimpleNamespace,
    *,
    element_adapter: ListenElementRunAdapter | None = None,
    received: list | None = None,
    **overrides: object,
) -> list:
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
    if received is None:
        received = []
    events = (
        host_lesson._follow_up_events(
            app=app, element_adapter=element_adapter, **arguments
        )
        if element_adapter is not None
        else follow_up_events(app, **arguments)
    )
    received.extend(events)
    return received


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
        with unit_of_work():
            PublishedOutlineItem.query.filter_by(
                outline_item_bid=course.outline_bid
            ).one().llm_system_prompt = "Retired lesson prompt"
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
            "<course_prompt>\nOld course prompt\n</course_prompt>"
            in ask_runtime.calls.llm[-1]["messages"][0]["content"]
        )
        assert (
            "Retired lesson prompt"
            not in ask_runtime.calls.llm[-1]["messages"][0]["content"]
        )
        trace = ask_runtime.traces[-1]["trace_payload"]
        assert trace["metadata"]["scene"] == "lesson_runtime"
        assert trace["metadata"]["outline_item_bid"] == course.outline_bid


@pytest.mark.parametrize("outcome", ["complete", "reset", "disconnect", "guardrail"])
def test_follow_up_holds_no_database_transaction_while_streaming(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
    outcome: str,
) -> None:
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    scope = {
        "user_bid": course.user_bid,
        "shifu_bid": course.course_bid,
        "outline_bid": course.outline_bid,
    }

    def moderate(*_args: object) -> SimpleNamespace:
        assert not db.session().in_transaction()
        return SimpleNamespace(
            check_result=(
                check_text.CHECK_RESULT_REJECT if outcome == "guardrail" else 0
            ),
            provider="test",
            raw_data={},
            risk_labels=[],
        )

    def guardrail_reply(*_args: object, **_kwargs: object) -> Iterator:
        assert not db.session().in_transaction()
        yield SimpleNamespace(result="Guardrail reply")

    def cold_timeout_config(_key: str) -> str:
        # On a cache miss, the config service reads from the database.
        LearnProgressRecord.query.filter_by(user_bid=course.user_bid).count()
        return "10"

    def provider(**_kwargs: object) -> Iterator:
        assert outcome != "guardrail"
        assert not db.session().in_transaction()
        assert provider_common.provider_timeout_seconds() == 10
        assert provider_common.provider_total_timeout_seconds() == 10
        assert not db.session().in_transaction()
        yield SimpleNamespace(content="First")
        assert not db.session().in_transaction()
        yield SimpleNamespace(content=" answer")
        assert not db.session().in_transaction()

    monkeypatch.setattr(handler, "_run_guardrail", ask_runtime.calls.run_guardrail)
    monkeypatch.setattr(check_text, "check_text", moderate)
    monkeypatch.setattr(check_text, "invoke_llm", guardrail_reply)
    monkeypatch.setattr(provider_common, "get_config", cold_timeout_config)
    monkeypatch.setattr(handler, "stream_ask_provider_response", provider)
    with app.app_context():
        adapter = ListenElementRunAdapter(app, **scope)
        events = host_lesson._follow_up_events(
            app=app,
            **scope,
            user_input="Question",
            reload_generated_block_bid=None,
            reload_element_bid=None,
            listen=False,
            learning_mode="read",
            preview_mode=True,
            stop_event=threading.Event(),
            element_adapter=adapter,
        )

        first = next(events)
        assert first.content.element_type == ElementType.ANSWER
        assert not db.session().in_transaction()

        with app.app_context(), unit_of_work(discard=True):
            assert not LearnGeneratedBlock.query.filter_by(
                user_bid=course.user_bid
            ).count()
            assert not LearnGeneratedElement.query.filter_by(
                user_bid=course.user_bid
            ).count()
        if outcome == "reset":
            with app.app_context():
                reset_learn_record(app, **scope, preview_mode=False)
        if outcome == "disconnect":
            events.close()
        else:
            for _event in events:
                assert not db.session().in_transaction()

        blocks = LearnGeneratedBlock.query.filter_by(user_bid=course.user_bid).all()
        elements = LearnGeneratedElement.query.filter_by(user_bid=course.user_bid).all()
        assert RiskControlResult.query.filter_by(user_id=course.user_bid).count() == 1
        if outcome in {"complete", "guardrail"}:
            answer = "Guardrail reply" if outcome == "guardrail" else "First answer"
            expected_blocks = {
                BLOCK_TYPE_MDASK_VALUE: "Question",
                BLOCK_TYPE_MDANSWER_VALUE: answer,
            }
            if outcome == "guardrail":
                expected_blocks[BLOCK_TYPE_MDINTERACTION_VALUE] = answer
            assert {
                block.type: block.generated_content for block in blocks
            } == expected_blocks
            final_sidecars = {
                row.element_type: row.content_text for row in elements if row.is_final
            }
            assert final_sidecars[ElementType.ASK.value] == "Question"
            assert final_sidecars[ElementType.ANSWER.value] == answer
            assert any(row.event_type == GeneratedType.BREAK.value for row in elements)
            assert all(row.progress_record_bid for row in elements)
        else:
            assert blocks == []
            assert elements == []
            assert not LearnAgentSession.query.filter_by(
                user_bid=course.user_bid
            ).count()


@pytest.mark.parametrize("disabled_at", ["course", "lesson"])
@pytest.mark.parametrize("has_progress", [False, True])
def test_published_follow_up_disabled_without_writing_progress_or_history(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
    disabled_at: str,
    has_progress: bool,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        with unit_of_work():
            published_course = PublishedShifu.query.filter_by(
                shifu_bid=course.course_bid
            ).one()
            published_lesson = PublishedOutlineItem.query.filter_by(
                outline_item_bid=course.outline_bid
            ).one()
            published_course.ask_enabled_status = (
                ASK_MODE_DISABLE if disabled_at == "course" else ASK_MODE_ENABLE
            )
            published_lesson.ask_enabled_status = (
                ASK_MODE_DISABLE if disabled_at == "lesson" else ASK_MODE_DEFAULT
            )
        if has_progress:
            _progress(course, position=0)

        with pytest.raises(AppError) as error:
            _ask(app, course)

        assert error.value.code == ERROR_CODE["server.common.paramsError"]
        assert LearnProgressRecord.query.filter_by(
            user_bid=course.user_bid, shifu_bid=course.course_bid
        ).count() == int(has_progress)
        assert (
            ask_runtime.calls.guardrails
            == ask_runtime.calls.providers
            == ask_runtime.calls.llm
            == []
        )
        assert not LearnGeneratedBlock.query.filter_by(
            user_bid=course.user_bid,
            shifu_bid=course.course_bid,
            outline_item_bid=course.outline_bid,
        ).count()


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
                make_generated_block(
                    generated_block_bid=anchor_bid,
                    progress_record_bid=progress_bid,
                    user_bid=course.user_bid,
                    shifu_bid=course.course_bid,
                    outline_item_bid=course.outline_bid,
                    status=1,
                )
            )
        _ask(app, course, reload_generated_block_bid=anchor_bid)

        assert _ask_block(course).position == 0


def test_retired_block_anchor_cannot_commit_follow_up(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    anchor_bid = uuid4().hex

    def answer(*_args: object, **_kwargs: object) -> Iterator[RunMarkdownFlowDTO]:
        yield RunMarkdownFlowDTO(
            course.outline_bid, uuid4().hex, GeneratedType.CONTENT, "Acknowledged."
        )
        with unit_of_work():
            LearnGeneratedBlock.query.filter_by(
                generated_block_bid=anchor_bid
            ).one().status = 0

    monkeypatch.setattr(follow_up_run, "handle_input_ask", answer)
    with app.app_context():
        progress_bid = _progress(course, position=2)
        with unit_of_work():
            db.session.add(
                make_generated_block(
                    generated_block_bid=anchor_bid,
                    progress_record_bid=progress_bid,
                    user_bid=course.user_bid,
                    shifu_bid=course.course_bid,
                    outline_item_bid=course.outline_bid,
                    status=1,
                )
            )
        with pytest.raises(FollowUpCancelledError):
            _ask(app, course, reload_generated_block_bid=anchor_bid)
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=progress_bid)
            .one()
            .status
            == LEARN_STATUS_IN_PROGRESS
        )
        assert not LearnAgentSession.query.filter_by(user_bid=course.user_bid).count()


@pytest.mark.parametrize(
    ("block_field", "outcome"),
    [
        ("block", "landed"),
        ("block", "retired"),
        ("block", "timeout"),
        ("block", "unknown-block"),
        ("block", "different-block"),
        (None, "landed"),
        (None, "timeout"),
        (None, "foreign-user"),
        (None, "different-attempt"),
        (None, "different-source"),
        (None, "stopped"),
        ("element", "landed"),
        ("element", "foreign-user"),
        ("element", "timeout"),
        ("matching-block", "retired"),
    ],
)
def test_follow_up_waits_for_a_streamed_anchor_before_starting(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
    block_field: str | None,
    outcome: str,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    scope = {
        "user_bid": course.user_bid,
        "shifu_bid": course.course_bid,
        "outline_item_bid": course.outline_bid,
    }
    anchor_element_bid = uuid4().hex
    anchor_block_bid = (
        anchor_element_bid if block_field == "matching-block" else uuid4().hex
    )
    stop_event = threading.Event()
    waits = []
    with app.app_context():
        prior_progress_bid = (
            _progress(course, position=1) if outcome == "different-attempt" else None
        )
        active_progress_bid = _progress(course, position=2)
        anchor_progress_bid = prior_progress_bid or active_progress_bid
        supplied_block_bid = None
        if block_field in ("element", "matching-block"):
            supplied_block_bid = anchor_element_bid
        elif block_field == "block":
            supplied_block_bid = (
                uuid4().hex
                if outcome in ("unknown-block", "different-block")
                else anchor_block_bid
            )
        with unit_of_work():
            db.session.add(
                make_generated_block(
                    **scope,
                    generated_block_bid=anchor_block_bid,
                    progress_record_bid=anchor_progress_bid,
                    status=1,
                )
            )
            if outcome == "different-block":
                db.session.add(
                    make_generated_block(
                        **scope,
                        generated_block_bid=supplied_block_bid,
                        progress_record_bid=active_progress_bid,
                        status=1,
                    )
                )

        def finish_teaching(_delay: float) -> None:
            assert not waits, "The stream should settle at the next poll"
            waits.append(True)
            assert not ask_runtime.calls.llm
            if outcome == "stopped":
                stop_event.set()
                return
            with app.app_context(), unit_of_work():
                if outcome == "retired":
                    LearnGeneratedBlock.query.filter_by(
                        generated_block_bid=anchor_block_bid
                    ).one().status = 0
                    return
                if outcome == "different-source":
                    draft = resolve_requested_lesson_source(
                        shifu_bid=course.course_bid,
                        outline_bid=course.outline_bid,
                        preview_mode=True,
                    )
                    assert stage_lesson_attempt_source(
                        user_bid=course.user_bid,
                        shifu_bid=course.course_bid,
                        outline_bid=course.outline_bid,
                        source=draft.source,
                    )
                db.session.add(
                    make_generated_element(
                        **(
                            scope | {"user_bid": uuid4().hex}
                            if outcome == "foreign-user"
                            else scope
                        ),
                        element_bid=anchor_element_bid,
                        generated_block_bid=anchor_block_bid,
                        progress_record_bid=anchor_progress_bid,
                        element_type="text",
                        content_text="The teaching anchor.",
                        is_final=1,
                    )
                )

        monkeypatch.setattr(stop_event, "wait", finish_teaching)
        if outcome == "timeout":
            monkeypatch.setattr(follow_up_run, "_PENDING_ANCHOR_WAIT_SECONDS", 0)

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=course.course_bid,
            outline_bid=course.outline_bid,
            user_bid=course.user_bid,
        )
        arguments = {
            "element_adapter": None if outcome == "stopped" else adapter,
            "reload_generated_block_bid": supplied_block_bid,
            "reload_element_bid": anchor_element_bid,
            "stop_event": stop_event,
        }
        if outcome == "landed":
            _ask(app, course, **arguments)
            assert "The teaching anchor." in str(ask_runtime.calls.llm[-1]["messages"])
            assert (
                LearnGeneratedElement.query.filter_by(
                    user_bid=course.user_bid, element_type="ask"
                ).count()
                == 1
            )
        else:
            if outcome == "stopped":
                with pytest.raises(FollowUpCancelledError):
                    _ask(app, course, **arguments)
            else:
                with pytest.raises(AppError) as error:
                    _ask(app, course, **arguments)
                assert error.value.code == ERROR_CODE["server.common.paramsError"]
            assert not ask_runtime.calls.llm
            assert not LearnGeneratedElement.query.filter_by(
                user_bid=course.user_bid, element_type="ask"
            ).count()
            assert not LearnGeneratedBlock.query.filter_by(
                user_bid=course.user_bid, type=BLOCK_TYPE_MDASK_VALUE
            ).count()
        assert waits == ([] if outcome in ("timeout", "unknown-block") else [True])


def test_formal_entry_rejects_text_ask_disabled_by_the_retained_draft(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _progress(course, position=0)
        with unit_of_work():
            DraftShifu.query.filter_by(
                shifu_bid=course.course_bid
            ).one().ask_enabled_status = ASK_MODE_DISABLE
            version = resolve_requested_lesson_source(
                shifu_bid=course.course_bid,
                outline_bid=course.outline_bid,
                preview_mode=True,
            )
            assert stage_lesson_attempt_source(
                user_bid=course.user_bid,
                shifu_bid=course.course_bid,
                outline_bid=course.outline_bid,
                source=version.source,
            )
        with pytest.raises(AppError):
            _ask(app, course, preview_mode=False)
        assert not ask_runtime.calls.llm
        assert not ask_runtime.calls.providers
        assert not LearnGeneratedBlock.query.filter_by(user_bid=course.user_bid).count()


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
                make_generated_block(
                    generated_block_bid=foreign_bid,
                    progress_record_bid=progress_bid,
                    user_bid=course.user_bid,
                    shifu_bid=course.course_bid,
                    outline_item_bid=uuid4().hex,
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


@pytest.mark.parametrize("follow_up_disabled", [False, True])
def test_an_unbought_paid_lesson_is_refused_before_anything_is_written(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
    follow_up_disabled: bool,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _sell_lesson(course)
        if follow_up_disabled:
            with unit_of_work():
                PublishedOutlineItem.query.filter_by(
                    outline_item_bid=course.outline_bid
                ).one().ask_enabled_status = ASK_MODE_DISABLE
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


@pytest.mark.parametrize(
    "preview_first", [False, True], ids=["published-first", "draft-first"]
)
def test_follow_ups_share_course_memory_using_the_first_source(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
    preview_first: bool,
) -> None:
    """Both entry points keep the same attempt and declared memory keys."""
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    monkeypatch.setattr(follow_up_run, "load_memory", load_memory)
    returns: list[str] = []
    notes = [
        {"key": "published_goal", "value": "Algebra", "request": None},
        {"key": "draft_goal", "value": "Geometry", "request": None},
        {"key": "shared_goal", "value": "", "request": None},
    ]
    monkeypatch.setattr(
        markdownflow,
        "GatewayModel",
        lambda *_args, **_kwargs: note_model(notes, returns),
    )
    with app.app_context():
        with unit_of_work():
            create_user_entity(
                user_bid=course.user_bid, identify=course.user_bid, nickname="Learner"
            )
            PublishedOutlineItem.query.filter_by(
                outline_item_bid=course.outline_bid
            ).one().content = "?[{{published_goal}}...Enter a goal]\n?[{{shared_goal}}...Enter a goal]"
            DraftOutlineItem.query.filter_by(
                outline_item_bid=course.outline_bid
            ).one().content = (
                "?[{{draft_goal}}...Enter a goal]\n?[{{shared_goal}}...Enter a goal]"
            )

        expected = {}
        for preview in (preview_first, not preview_first):
            admitted = notes[int(preview_first)]
            notes[2]["value"] = notes[int(preview)]["value"]
            returns.clear()
            events = _ask(app, course, preview_mode=preview)

            assert any(event.content == "Acknowledged." for event in events)
            assert sum(result.startswith("remembered ") for result in returns) == 2
            expected[admitted["key"]] = admitted["value"]
            expected["shared_goal"] = notes[2]["value"]
            values = load_memory(
                app, course.user_bid, course.course_bid, include_course_variables=True
            ).as_variables()
            tracked_keys = {note["key"] for note in notes}
            assert {
                key: values[key] for key in tracked_keys & values.keys()
            } == expected
        other_course = load_memory(
            app, course.user_bid, uuid4().hex, include_course_variables=True
        ).as_variables()
        assert not (expected.keys() & other_course.keys())


@pytest.mark.parametrize("reset_preview", [True, False])
def test_either_reset_discards_pending_follow_up_memory(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
    reset_preview: bool,
) -> None:
    """A reset on either surface invalidates an in-flight draft follow-up."""
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    scope = {
        "user_bid": course.user_bid,
        "shifu_bid": course.course_bid,
        "outline_bid": course.outline_bid,
    }

    def answer(
        *_args: object, memory_patch: FollowUpMemoryPatch, **_kwargs: object
    ) -> Iterator[RunMarkdownFlowDTO]:
        memory_patch.variables = [VariableMemoryUpdate("goal", "New value")]
        yield RunMarkdownFlowDTO(
            course.outline_bid, uuid4().hex, GeneratedType.CONTENT, "Acknowledged."
        )
        reset_learn_record(app, **scope, preview_mode=reset_preview)

    monkeypatch.setattr(follow_up_run, "handle_input_ask", answer)
    with app.app_context():
        with unit_of_work():
            create_user_entity(
                user_bid=course.user_bid, identify=course.user_bid, nickname="Learner"
            )
            stage_memory(
                app,
                course.user_bid,
                course.course_bid,
                MemoryUpdate(variables=[VariableMemoryUpdate("goal", "Saved value")]),
            )
        with pytest.raises(FollowUpCancelledError):
            _ask(app, course, preview_mode=True)
        values = load_memory(
            app, course.user_bid, course.course_bid, include_course_variables=True
        ).as_variables()
        assert values["goal"] == "Saved value"


def test_first_publication_continues_a_draft_only_follow_up(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app, publish=False)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        assert not PublishedShifu.query.filter_by(shifu_bid=course.course_bid).count()
        _ask(app, course, preview_mode=True, user_input="What did we learn in draft?")
        publish_shifu_draft(
            app, course.user_bid, course.course_bid, "", sync_summary=True
        )
        _ask(app, course, preview_mode=False)
        progress = LearnProgressRecord.query.filter_by(user_bid=course.user_bid).one()
        assert (
            LearnGeneratedBlock.query.filter_by(
                progress_record_bid=progress.progress_record_bid,
                type=BLOCK_TYPE_MDASK_VALUE,
            ).count()
            == 2
        )
        assert "What did we learn in draft?" in str(
            ask_runtime.calls.llm[-1]["messages"]
        )


def test_formal_follow_up_cannot_resume_draft_after_permission_is_revoked(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _ask(app, course, preview_mode=True)
        new_owner = uuid4().hex
        with unit_of_work():
            for model in (DraftShifu, PublishedShifu):
                model.query.filter_by(shifu_bid=course.course_bid).update(
                    {"created_user_bid": new_owner}
                )
        with pytest.raises(AppError) as error:
            _ask(app, course, preview_mode=False)
        assert error.value.code == ERROR_CODE["server.shifu.noPermission"]
        assert len(ask_runtime.calls.llm) == 1


def test_revoking_draft_permission_discards_pending_formal_follow_up(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies, ask_runtime
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)

    def revoke_after_admission(
        *args: object, **kwargs: object
    ) -> Iterator[RunMarkdownFlowDTO]:
        new_owner = uuid4().hex
        with app.app_context(), unit_of_work():
            for model in (DraftShifu, PublishedShifu):
                model.query.filter_by(shifu_bid=course.course_bid).update(
                    {"created_user_bid": new_owner}
                )
        yield from answer(*args, **kwargs)

    with app.app_context():
        _ask(app, course, preview_mode=True)
        answer = follow_up_run.handle_input_ask
        monkeypatch.setattr(follow_up_run, "handle_input_ask", revoke_after_admission)

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=course.course_bid,
            outline_bid=course.outline_bid,
            user_bid=course.user_bid,
        )
        staged = []
        handle_ask = adapter._handle_ask

        def track_ask_staging(event: RunMarkdownFlowDTO) -> Iterator:
            yield from handle_ask(event)
            staged.append(
                LearnGeneratedElement.query.filter_by(
                    user_bid=course.user_bid, element_type="ask"
                ).count()
            )

        monkeypatch.setattr(adapter, "_handle_ask", track_ask_staging)
        received = []
        with pytest.raises(AppError) as error:
            _ask(
                app,
                course,
                element_adapter=adapter,
                preview_mode=False,
                received=received,
            )
        assert error.value.code == ERROR_CODE["server.shifu.noPermission"]
        assert received == []
        assert staged == [0]
        assert not LearnGeneratedElement.query.filter_by(
            user_bid=course.user_bid
        ).count()
        assert (
            LearnGeneratedBlock.query.filter_by(
                user_bid=course.user_bid, type=BLOCK_TYPE_MDASK_VALUE
            ).count()
            == 1
        )


def test_preview_follow_up_does_not_bypass_purchase_of_published_lesson(
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
        _ask(app, course, preview_mode=True)
        assert (
            LearnProgressRecord.query.filter_by(user_bid=course.user_bid).count() == 1
        )
        with pytest.raises(PaidError):
            _ask(app, course, preview_mode=False)
        assert len(ask_runtime.calls.llm) == 1


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


def test_a_failed_session_lookup_still_answers_without_a_session(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: object,
    ask_runtime: SimpleNamespace,
) -> None:
    _ = runtime_dependencies

    def broken_lookup(*_args: object, **_kwargs: object) -> None:
        message = "session store unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(follow_up_run, "active_session_id", broken_lookup)
    course = revision._seed_course(app)
    _learner(monkeypatch, course.user_bid)
    with app.app_context():
        _progress(course, position=0)
        events = _ask(app, course)

    assert any(
        e.type == GeneratedType.CONTENT and e.content == "Follow-up answer"
        for e in events
    )
    assert "session_id" not in ask_runtime.traces[-1]["trace_payload"]
    assert "level" not in ask_runtime.finalized[-1]["root_span_payload"]
