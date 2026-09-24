"""Verify agent lesson lookup, course model identity, paid access, and trace closure."""

import uuid
from collections.abc import Callable
from decimal import Decimal
from unittest.mock import Mock

import pytest
from flaskr.api.llm import model_selection
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import lesson_entry as entry
from flaskr.service.learn.agent.run_agent import TurnOutcome
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
from flaskr.service.order.consts import ORDER_STATUS_INIT, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_NORMAL
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)


@pytest.fixture
def lesson(app: object, monkeypatch: object) -> object:
    identity = uuid.uuid4().hex
    monkeypatch.setitem(app.config, "LLM_MODEL_1_ID", "deployment-model")
    monkeypatch.setitem(app.config, "DEFAULT_LLM_TEMPERATURE", 0.4)
    with app.app_context(), unit_of_work():
        for model, name in ((DraftShifu, "draft"), (PublishedShifu, "published")):
            db.session.add(
                model(
                    shifu_bid=identity,
                    title=name,
                    llm=f"{name}-model",
                    llm_temperature=Decimal("0.2"),
                    price=0,
                )
            )
        for model, name in (
            (DraftOutlineItem, "draft"),
            (PublishedOutlineItem, "published"),
        ):
            db.session.add(
                model(
                    shifu_bid=identity,
                    outline_item_bid=identity,
                    content=f"{name} lesson script",
                    type=UNIT_TYPE_VALUE_NORMAL,
                    position=0,
                )
            )
    yield identity
    with app.app_context(), unit_of_work():
        for model in (
            Order,
            DraftOutlineItem,
            DraftShifu,
            PublishedOutlineItem,
            PublishedShifu,
        ):
            model.query.filter_by(shifu_bid=identity).delete()


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("saved", ["2", "", "legacy-model"])
def test_lesson_resolution_preserves_course_selection_and_revision_metadata(
    app: object, lesson: str, preview: bool, saved: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, course_model = entry._models(preview)
    monkeypatch.setattr(
        model_selection,
        "get_configured_model_slots",
        lambda: [{"index": "2", "model": "provider-model"}],
    )
    with app.app_context(), unit_of_work():
        course = course_model.query.filter_by(shifu_bid=lesson).one()
        course.llm = saved
        record_id = course.id
    with app.app_context():
        script, brief, settings = entry._resolve(
            app,
            user_bid="learner",
            shifu_bid=lesson,
            outline_bid=lesson,
            preview_mode=preview,
        )
    version = "draft" if preview else "published"
    assert script == f"{version} lesson script"
    assert brief == ""
    assert settings.model == saved
    assert float(settings.temperature) == 0.2
    assert settings.usage_metadata == {
        "model_selection_scope": "course",
        "model_selection_original": saved,
        "model_selection_field": "llm",
        "model_selection_table": course_model.__tablename__,
        "model_selection_record_id": record_id,
        "model_index": "2" if saved == "2" else "1",
        "model_selection_fallback": saved != "2",
        "model_selection_fallback_reason": None
        if saved == "2"
        else ("missing_selection" if saved == "" else "invalid_selection"),
    }


@pytest.mark.parametrize("invalid", ["other-course", "blank-script", "deleted"])
def test_unteachable_lesson_falls_back_without_exposing_another_course_script(
    app: object, lesson: str, invalid: str
) -> None:
    with app.app_context(), unit_of_work():
        row = PublishedOutlineItem.query.filter_by(shifu_bid=lesson).one()
        if invalid == "blank-script":
            row.content = " \n"
        elif invalid == "deleted":
            row.deleted = 1
    with app.app_context(), pytest.raises(entry.LessonNotTeachable):
        entry._resolve(
            app,
            user_bid="learner",
            shifu_bid="another-course" if invalid == "other-course" else lesson,
            outline_bid=lesson,
            preview_mode=False,
        )


@pytest.mark.parametrize("order_kind", ["valid", "other-user", "deleted", "unpaid"])
def test_paid_agent_lesson_requires_the_learners_own_successful_active_order(
    app: object, lesson: str, order_kind: str
) -> None:
    with app.app_context(), unit_of_work():
        PublishedShifu.query.filter_by(shifu_bid=lesson).one().price = Decimal(99)
        db.session.add(
            Order(
                order_bid=uuid.uuid4().hex,
                shifu_bid=lesson,
                user_bid="other" if order_kind == "other-user" else "learner",
                status=ORDER_STATUS_INIT
                if order_kind == "unpaid"
                else ORDER_STATUS_SUCCESS,
                deleted=int(order_kind == "deleted"),
            )
        )
    with app.app_context():
        if order_kind == "valid":
            assert (
                entry._resolve(
                    app,
                    user_bid="learner",
                    shifu_bid=lesson,
                    outline_bid=lesson,
                    preview_mode=False,
                )[0]
                == "published lesson script"
            )
        else:
            with pytest.raises(PaidError):
                entry._resolve(
                    app,
                    user_bid="learner",
                    shifu_bid=lesson,
                    outline_bid=lesson,
                    preview_mode=False,
                )


@pytest.mark.parametrize("termination", ["completed", "error", "disconnected"])
def test_agent_turn_always_closes_its_trace_with_the_actual_outcome(
    app: object, monkeypatch: object, termination: str
) -> None:
    settings = LLMSettings(
        model="2",
        temperature=0.25,
        usage_metadata={
            "model_selection_scope": "course",
            "model_selection_original": "2",
        },
    )
    monkeypatch.setattr(entry, "_resolve", lambda *_a, **_kw: ("script", "", settings))
    trace, span = object(), object()
    monkeypatch.setattr(entry, "get_langfuse_client", object)
    monkeypatch.setattr(
        entry, "create_trace_with_root_span", lambda **_kw: (trace, span)
    )
    finalize = Mock()
    monkeypatch.setattr(entry, "finalize_langfuse_trace", finalize)
    gateway = Mock(return_value=object())
    engine = Mock(return_value=object())
    monkeypatch.setattr(entry, "GatewayModel", gateway)
    monkeypatch.setattr(entry, "Engine", engine)
    event = RunMarkdownFlowDTO(
        outline_bid="lesson",
        generated_block_bid="block",
        type=GeneratedType.CONTENT,
        content="Visible answer",
    )

    def produce(*_args: object, **_kwargs: object) -> object:
        yield event
        if termination == "error":
            message = "provider failed"
            raise RuntimeError(message)

    runner = Mock(side_effect=produce)
    monkeypatch.setattr(entry, "run_agent_lesson", runner)
    stream = entry.agent_lesson_events(
        app,
        user_bid="learner",
        shifu_bid="course",
        outline_bid="lesson",
        user_input={"choice": ["a"]},
        listen=True,
        preview_mode=True,
        heartbeat_interval=0.1,
    )
    assert next(stream) is event
    finalize.assert_not_called()
    if termination == "disconnected":
        stream.close()
    elif termination == "error":
        with pytest.raises(RuntimeError, match="provider failed"):
            next(stream)
    else:
        assert list(stream) == []
    finalize.assert_called_once_with(
        trace=trace,
        root_span=span,
        root_span_payload={"metadata": {"end_reason": termination}},
    )
    gateway.assert_called_once_with(
        app,
        "2",
        user_id="learner",
        span=span,
        usage_metadata=settings.usage_metadata,
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
    )
    engine.assert_called_once_with(
        gateway.return_value,
        memory_store=None,
        model_settings={"temperature": 0.25},
        # Without it, a question the controls cannot carry reaches the learner with no controls.
        interaction_check=entry.unrenderable_reason,
    )
    assert runner.call_args.kwargs == {
        "engine": engine.return_value,
        "script": "script",
        "teaching_brief": "",
        "user_bid": "learner",
        "shifu_bid": "course",
        "outline_bid": "lesson",
        "user_input": {"choice": ["a"]},
        "listen": True,
        "preview_mode": True,
        "shifu_model": DraftShifu,
        "heartbeat_interval": 0.1,
        "rewind": None,
    }


def _entry_with_runner(monkeypatch: object) -> Mock:
    """Stub everything around the turn and return the mock standing in for the turn itself."""
    settings = LLMSettings(model="2", temperature=0.25, usage_metadata={})
    monkeypatch.setattr(entry, "_resolve", lambda *_a, **_kw: ("script", "", settings))
    monkeypatch.setattr(entry, "get_langfuse_client", object)
    monkeypatch.setattr(
        entry, "create_trace_with_root_span", lambda **_kw: (object(), object())
    )
    monkeypatch.setattr(entry, "finalize_langfuse_trace", Mock())
    monkeypatch.setattr(entry, "GatewayModel", Mock(return_value=object()))
    monkeypatch.setattr(entry, "Engine", Mock(return_value=object()))
    runner = Mock(side_effect=lambda *_a, **_kw: iter(()))
    monkeypatch.setattr(entry, "run_agent_lesson", runner)
    return runner


def _reload(app: object, **kwargs: object) -> list:
    return list(
        entry.agent_lesson_events(
            app,
            user_bid="learner",
            shifu_bid="course",
            outline_bid="lesson",
            reload_generated_block_bid="block-1",
            **kwargs,
        )
    )


def test_going_back_hands_the_turn_the_plan_for_where_it_went_back_to(
    app: object, monkeypatch: object
) -> None:
    runner = _entry_with_runner(monkeypatch)
    plan = object()
    asked: dict = {}

    def _plan(**kwargs: object) -> object:
        asked.update(kwargs)
        return plan

    monkeypatch.setattr(entry, "plan_rewind", _plan)
    _reload(app, user_input={"way": ["Right"]})

    assert asked == {
        "user_bid": "learner",
        "outline_bid": "lesson",
        "anchor": "block-1",
        "answering": True,
    }
    assert runner.call_args.kwargs["rewind"] is plan


def test_a_lesson_that_cannot_go_back_says_so_instead_of_running(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.common.models import AppError
    from flaskr.service.learn.agent.rewind import RewindUnavailableError

    runner = _entry_with_runner(monkeypatch)

    def _unavailable(**_kwargs: object) -> None:
        raise RewindUnavailableError

    monkeypatch.setattr(entry, "plan_rewind", _unavailable)
    with pytest.raises(AppError):
        _reload(app, user_input="")
    runner.assert_not_called()


def test_a_preview_cannot_go_back(app: object, monkeypatch: object) -> None:
    """A preview keeps no turn blocks to go back to."""
    from flaskr.service.common.models import AppError

    runner = _entry_with_runner(monkeypatch)
    monkeypatch.setattr(entry, "plan_rewind", Mock())
    with pytest.raises(AppError):
        _reload(app, user_input="", preview_mode=True)
    runner.assert_not_called()


def _turn(
    outcomes: list[TurnOutcome | None], calls: list[dict]
) -> Callable[..., object]:
    """Build a turn double: record the call, yield one event, return the next outcome."""

    def produce(*_args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid=f"block-{len(calls)}",
            type=GeneratedType.CONTENT,
            content="said",
        )
        return outcomes[len(calls) - 1]

    return produce


def test_a_turn_that_ran_out_of_content_is_followed_by_the_next_in_the_same_request(
    app: object, monkeypatch: object
) -> None:
    """The browser never sees a turn's end that is not the lesson's, so the host carries on.

    On the simulation environment (2026-09-24, boundary lessons 3-2 and 3-3) a lesson whose
    model stopped without `finish` stayed "in progress" until the learner opened it again.
    """
    runner = _entry_with_runner(monkeypatch)
    calls: list[dict] = []
    runner.side_effect = _turn(
        [
            TurnOutcome(reason="end", taught=True),
            TurnOutcome(reason="end", taught=True),
            TurnOutcome(reason="interaction", taught=True),
        ],
        calls,
    )

    events = list(
        entry.agent_lesson_events(
            app,
            user_bid="learner",
            shifu_bid="course",
            outline_bid="lesson",
            user_input={"choice": ["a"]},
        )
    )

    assert [e.generated_block_bid for e in events] == ["block-1", "block-2", "block-3"]
    # The learner's input belongs to the first turn; the ones after it are the host's continue.
    assert [c["user_input"] for c in calls] == [{"choice": ["a"]}, None, None]


@pytest.mark.parametrize(
    "outcome",
    [
        TurnOutcome(reason="finished", taught=True),
        TurnOutcome(reason="interaction", taught=True),
        # Out of content having said nothing: the model has nothing to add and did not say so.
        TurnOutcome(reason="end", taught=False),
        None,
    ],
)
def test_a_turn_that_waits_ends_or_says_nothing_is_not_followed(
    app: object, monkeypatch: object, outcome: TurnOutcome | None
) -> None:
    runner = _entry_with_runner(monkeypatch)
    calls: list[dict] = []
    runner.side_effect = _turn([outcome, TurnOutcome(reason="end", taught=True)], calls)

    events = list(
        entry.agent_lesson_events(
            app, user_bid="learner", shifu_bid="course", outline_bid="lesson"
        )
    )

    assert len(events) == 1
    assert len(calls) == 1


def test_a_request_runs_only_so_many_turns(app: object, monkeypatch: object) -> None:
    runner = _entry_with_runner(monkeypatch)
    calls: list[dict] = []
    runner.side_effect = _turn([TurnOutcome(reason="end", taught=True)] * 100, calls)

    list(
        entry.agent_lesson_events(
            app, user_bid="learner", shifu_bid="course", outline_bid="lesson"
        )
    )

    assert len(calls) == entry._MAX_TURNS_PER_REQUEST
