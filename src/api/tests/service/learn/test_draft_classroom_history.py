"""Verify draft teaching reuses durable lesson records and preserves replay."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from flaskr.api import langfuse_markdownflow
from flaskr.api.langfuse import MockClient
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn.agent import lesson_entry, run_agent
from flaskr.service.learn.agent.lesson_record import stage_turn_block
from flaskr.service.learn.agent.lesson_source import resolve_lesson_source
from flaskr.service.learn.agent.models import LearnAgentSession
from flaskr.service.learn.agent.session_store import (
    _ATTEMPT_SOURCE_KEY,
    load_agent_session,
    save_agent_session,
    stage_lesson_attempt_source,
)
from flaskr.service.learn.elements.run_adapter import (
    ListenElementRunAdapter,
    get_listen_element_record,
)
from flaskr.service.learn.exceptions import DraftTurnAccessRevokedError, PaidError
from flaskr.service.learn.host import lesson as host_lesson
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    LearnStatus,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learn_funcs import (
    get_outline_item_tree,
    reset_learn_record,
    stream_generated_block_audio,
)
from flaskr.service.learn.live_follow_up_config import GEMINI_LIVE_MODEL_ID
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnProgressRecord,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import ASK_MODE_ENABLE, UNIT_TYPE_VALUE_NORMAL
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.user.repository import create_user_entity
from flaskr.util.datetime import now_utc, to_utc_iso
from markdownflow import bridge
from markdownflow.engine import ScriptBundle, Session
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.common.fixtures.model_factories import (
    make_generated_element,
    make_progress_record,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import (
        LearnElementRecordDTO,
        OutlineItemUpdateDTO,
    )
    from flaskr.service.metering.api import UsageContext
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


_SCRIPT = "Teach a topic, then ask a question. Wait for an answer before proceeding."


def _shown(user_input: str | None) -> str:
    """Read the submitted text or choices from a restored control's structured default."""
    if not user_input:
        return ""
    data = json.loads(user_input)
    return data["inputText"] or ",".join(data["selectedValues"])


@pytest.fixture
def classroom(app: Flask, monkeypatch: pytest.MonkeyPatch) -> tuple:
    """Exercise the real engine, adapter, database and classroom orchestrator offline."""
    identity = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        create_user_entity(user_bid=identity, identify=identity, nickname="Learner")
        course = DraftShifu(shifu_bid=identity, created_user_bid=identity, llm="1")
        lesson = DraftOutlineItem(
            shifu_bid=identity, outline_item_bid=identity, content=_SCRIPT, type=401
        )
        db.session.add_all([course, lesson])
        db.session.flush()
        db.session.add(
            LogDraftStruct(
                struct_bid=uuid.uuid4().hex,
                shifu_bid=identity,
                struct=HistoryItem(
                    bid=identity,
                    id=course.id,
                    type="shifu",
                    children=[
                        HistoryItem(
                            bid=identity,
                            id=lesson.id,
                            type="outline",
                            children=[],
                            content_revision=11,
                        )
                    ],
                ).to_json(),
            )
        )
    calls = []

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        calls.append(True)
        number = len(calls)
        if any(
            isinstance(part, ToolCallPart) and part.tool_name == "finish"
            for message in _messages
            for part in message.parts
        ):
            yield "Preview completed."
            return
        if any(
            "finish-preview" in str(getattr(part, "content", ""))
            for message in _messages
            for part in message.parts
        ):
            yield "Final preview teaching."
            yield {
                0: DeltaToolCall(
                    name="finish",
                    tool_call_id="finish",
                    json_args=json.dumps({"summary": "Completed"}),
                )
            }
            return
        yield f"Teaching before question {number}.\n"
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"q-{number}",
                json_args=json.dumps({"type": "text", "prompt": f"Question {number}?"}),
            )
        }

    class Gateway(FunctionModel):
        def set_usage_context(self, context: UsageContext) -> None:
            assert context.progress_record_bid
            assert context.generated_block_bid

    gateway = Gateway(stream_function=model)
    monkeypatch.setattr(lesson_entry, "GatewayModel", lambda *_a, **_k: gateway)

    monkeypatch.setattr(langfuse_markdownflow, "get_langfuse_client", MockClient)

    def drive(make_events: Callable, **_kwargs: object) -> Iterator:
        async def collect() -> list:
            return [event async for event in make_events()]

        return iter(asyncio.run(collect()))

    monkeypatch.setattr(bridge, "iter_turn", drive)

    def run(
        answer: str | None = None,
        *,
        anchor: str | None = None,
        after_open: Callable[[], None] | None = None,
        user_bid: str | None = None,
        preview_mode: bool = True,
    ) -> list:
        learner_bid = user_bid or identity
        with app.app_context():
            adapter = ListenElementRunAdapter(
                app,
                shifu_bid=identity,
                outline_bid=identity,
                user_bid=learner_bid,
                persist_only_final=True,
            )
            events = host_lesson._lesson_events(
                app=app,
                user_bid=learner_bid,
                shifu_bid=identity,
                outline_bid=identity,
                user_input=answer,
                input_type=None,
                reload_generated_block_bid=None,
                reload_element_bid=anchor,
                listen=False,
                learning_mode="read",
                preview_mode=preview_mode,
                stop_event=None,
                element_adapter=adapter,
                heartbeat_interval=0.5,
            )
            if after_open is not None:
                first = next(events)
                assert first.type == "outline_item_update"
                after_open()
                return [first, *events]
            return list(events)

    def history(
        *, preview_mode: bool = True, **overrides: str
    ) -> LearnElementRecordDTO:
        with app.app_context():
            return get_listen_element_record(
                app,
                overrides.get("course", identity),
                overrides.get("lesson", identity),
                overrides.get("user", identity),
                preview_mode=preview_mode,
            )

    return identity, run, history, calls


def _change_draft_body(identity: str, content: str) -> None:
    """Stage the body and its authored revision in the caller's transaction."""
    old = (
        DraftOutlineItem.query.filter_by(outline_item_bid=identity)
        .order_by(DraftOutlineItem.id.desc())
        .first()
    )
    if old.content == content:
        return
    outline = DraftOutlineItem(
        shifu_bid=identity, outline_item_bid=identity, content=content, type=old.type
    )
    db.session.add(outline)
    db.session.flush()
    structure = (
        LogDraftStruct.query.filter_by(shifu_bid=identity)
        .order_by(LogDraftStruct.id.desc())
        .first()
    )
    parsed = HistoryItem.from_json(structure.struct)
    parsed.children[0].id = outline.id
    parsed.children[0].content_revision += 1
    db.session.add(
        LogDraftStruct(
            struct_bid=uuid.uuid4().hex, shifu_bid=identity, struct=parsed.to_json()
        )
    )


def _stage_published_classroom(identity: str, *, price: int = 0) -> None:
    course = PublishedShifu(
        shifu_bid=identity, price=price, ask_enabled_status=ASK_MODE_ENABLE
    )
    outline = PublishedOutlineItem(
        shifu_bid=identity,
        outline_item_bid=identity,
        content=_SCRIPT,
        type=UNIT_TYPE_VALUE_NORMAL,
    )
    db.session.add_all([course, outline])
    db.session.flush()
    db.session.add(
        LogPublishedStruct(
            struct_bid=uuid.uuid4().hex,
            shifu_bid=identity,
            struct=HistoryItem(
                bid=identity,
                id=course.id,
                type="shifu",
                children=[
                    HistoryItem(
                        bid=identity, id=outline.id, type="outline", children=[]
                    )
                ],
            ).to_json(),
        )
    )


def test_published_history_and_audio_check_purchase_before_exposing_draft_teaching(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    with app.app_context(), unit_of_work():
        _stage_published_classroom(identity, price=10)
    assert history().elements
    with app.app_context():
        block = LearnGeneratedBlock.query.filter_by(user_bid=identity).one()
        with pytest.raises(PaidError):
            get_listen_element_record(
                app, identity, identity, identity, preview_mode=False
            )
        with pytest.raises(PaidError):
            list(
                stream_generated_block_audio(
                    app,
                    shifu_bid=identity,
                    generated_block_bid=block.generated_block_bid,
                    user_bid=identity,
                    preview_mode=False,
                )
            )

        with unit_of_work():
            db.session.add(
                Order(
                    order_bid=uuid.uuid4().hex,
                    shifu_bid=identity,
                    user_bid=identity,
                    status=ORDER_STATUS_SUCCESS,
                )
            )
        assert get_listen_element_record(
            app, identity, identity, identity, preview_mode=False
        ).elements


def test_legacy_published_history_uses_published_follow_up_mode_in_draft(
    app: Flask, classroom: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity, run, history, _calls = classroom
    run()
    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.is_live_follow_up_model_available",
        lambda _model: True,
    )
    with app.app_context(), unit_of_work():
        _stage_published_classroom(identity)
        draft = DraftShifu.query.filter_by(shifu_bid=identity, deleted=0).one()
        draft.ask_llm = GEMINI_LIVE_MODEL_ID
        draft.ask_enabled_status = ASK_MODE_ENABLE
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        document = json.loads(row.session_data)
        del document[_ATTEMPT_SOURCE_KEY]
        row.session_data = json.dumps(document)

    assert (
        get_outline_item_tree(app, identity, identity, preview_mode=True)
        .outline_items[0]
        .follow_up_mode
        == "live_voice"
    )
    record = history()
    assert record.elements
    assert record.follow_up_mode == "text"


@pytest.mark.parametrize("preview_mode", [True, False])
def test_chapter_cannot_open_a_lesson_attempt(
    app: Flask, classroom: tuple, preview_mode: bool
) -> None:
    identity, _run, _history, _calls = classroom
    chapter_bid = uuid.uuid4().hex
    outline_model = DraftOutlineItem if preview_mode else PublishedOutlineItem
    structure_model = LogDraftStruct if preview_mode else LogPublishedStruct
    with app.app_context(), unit_of_work():
        if not preview_mode:
            _stage_published_classroom(identity)
        chapter = outline_model(
            shifu_bid=identity,
            outline_item_bid=chapter_bid,
            content="",
            type=UNIT_TYPE_VALUE_NORMAL,
        )
        db.session.add(chapter)
        db.session.flush()
        row = structure_model.query.filter_by(shifu_bid=identity, deleted=0).one()
        structure = HistoryItem.from_json(row.struct)
        structure.children = [
            HistoryItem(
                bid=chapter_bid,
                id=chapter.id,
                type="outline",
                children=structure.children,
            )
        ]
        row.struct = structure.to_json()

    with app.app_context():
        with pytest.raises(AppError) as exc:
            list(
                lesson_entry.complete_empty_lesson(
                    app,
                    user_bid=identity,
                    shifu_bid=identity,
                    outline_bid=chapter_bid,
                    preview_mode=preview_mode,
                )
            )
        assert exc.value.code == ERROR_CODE["server.shifu.lessonNotFoundInCourse"]
        assert LearnProgressRecord.query.filter_by(user_bid=identity).count() == 0


def test_reload_restores_teaching_and_pending_interaction_from_shared_progress(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, calls = classroom
    streamed = run()
    assert streamed[0].type == "outline_item_update"
    assert streamed[0].content.status == LearnStatus.IN_PROGRESS
    with app.app_context():
        progress = LearnProgressRecord.query.filter_by(user_bid=identity).one()
        assert progress.status == LEARN_STATUS_IN_PROGRESS
        assert (
            LearnGeneratedBlock.query.filter_by(user_bid=identity)
            .one()
            .progress_record_bid
            == progress.progress_record_bid
        )
    records = history().elements
    assert [item.element_type for item in records] == [
        ElementType.TEXT,
        ElementType.INTERACTION,
    ]
    assert "Teaching before question 1." in records[0].content
    assert "Question 1?" not in records[0].content
    assert records[1].payload.interaction_question == "Question 1?"
    assert not records[1].payload.user_input
    restored_ids = [item.element_bid for item in records]
    assert len(calls) == 1
    assert [item.element_bid for item in history().elements] == restored_ids


@pytest.mark.parametrize(
    "placeholder_status", [LEARN_STATUS_NOT_STARTED, LEARN_STATUS_LOCKED]
)
def test_newer_placeholder_does_not_hide_started_draft_progress(
    app: Flask, classroom: tuple, placeholder_status: int
) -> None:
    identity, run, history, _calls = classroom
    run()
    previous = [element.element_bid for element in history().elements]
    assert previous
    with app.app_context(), unit_of_work():
        started = LearnProgressRecord.query.filter_by(user_bid=identity).one()
        db.session.add(
            make_progress_record(
                progress_record_bid=uuid.uuid4().hex,
                user_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                block_position=started.block_position,
                status=placeholder_status,
            )
        )
        _change_draft_body(identity, "Updated teaching")

    restored = history()
    assert restored.has_content_update_for_current_user
    assert [element.element_bid for element in restored.elements] == previous
    lesson = get_outline_item_tree(
        app, identity, identity, preview_mode=True
    ).outline_items[0]
    assert lesson.status == LearnStatus.IN_PROGRESS
    assert lesson.has_content_update_for_current_user


def test_multiple_requests_keep_order_and_accepted_answers(classroom: tuple) -> None:
    _identity, run, history, calls = classroom
    for event in run():
        event.__json__()
    history().__json__()
    run("My answer")
    records = history().elements
    assert [item.element_type for item in records] == [
        ElementType.TEXT,
        ElementType.INTERACTION,
        ElementType.TEXT,
        ElementType.INTERACTION,
    ]
    assert "question 1" in records[0].content
    assert "question 2" in records[2].content
    assert "Question 1?" not in records[0].content
    assert "Question 2?" not in records[2].content
    assert records[1].payload.interaction_question == "Question 1?"
    assert records[3].payload.interaction_question == "Question 2?"
    assert _shown(records[1].payload.user_input) == "My answer"
    assert not records[-1].payload or not records[-1].payload.user_input
    assert len(calls) == 2
    assert history(user="someone-else").elements == []
    assert history(course="another-course").elements == []
    assert history(lesson="another-lesson").elements == []


def test_preview_catalog_and_reset_use_the_shared_progress(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    assert (
        get_outline_item_tree(app, identity, identity, preview_mode=True)
        .outline_items[0]
        .status
        == LearnStatus.IN_PROGRESS
    )
    reset_learn_record(app, identity, identity, identity, preview_mode=True)
    assert history().elements == []
    assert (
        get_outline_item_tree(app, identity, identity, preview_mode=True)
        .outline_items[0]
        .status
        == LearnStatus.NOT_STARTED
    )
    assert load_agent_session(app, identity, identity) is None
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(user_bid=identity).one().status
            == LEARN_STATUS_RESET
        )
    run()
    assert "question 2" in history().elements[0].content


def test_preview_history_and_continuation_preserve_the_taught_body(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    original = _SCRIPT
    with app.app_context(), unit_of_work():
        _change_draft_body(identity, original)
    run()
    assert history().has_content_update_for_current_user is False
    with app.app_context(), unit_of_work():
        _change_draft_body(identity, "Changed")
    assert history().has_content_update_for_current_user is True
    run("My answer")
    assert history().has_content_update_for_current_user is True
    assert load_agent_session(app, identity, identity).script.script == original
    with app.app_context(), unit_of_work():
        _change_draft_body(identity, original)
    assert history().has_content_update_for_current_user is True


def test_published_opening_does_not_emit_retained_draft_after_revocation(
    app: Flask, classroom: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity, run, _history, calls = classroom
    learner_bid = uuid.uuid4().hex
    draft_title = "Unpublished lesson title"
    scope = {"user_bid": learner_bid, "shifu_bid": identity, "outline_bid": identity}
    with app.app_context():
        with unit_of_work():
            create_user_entity(
                user_bid=learner_bid, identify=learner_bid, nickname="Collaborator"
            )
            db.session.add(
                AiCourseAuth(
                    course_id=identity, user_id=learner_bid, auth_type="view", status=1
                )
            )
            DraftOutlineItem.query.filter_by(
                outline_item_bid=identity
            ).one().title = draft_title
            _stage_published_classroom(identity)
        draft = resolve_lesson_source(app, **scope, preview_mode=True)
        with unit_of_work():
            assert stage_lesson_attempt_source(**scope, source=draft.source)

    original_open_turn = run_agent._open_turn

    def revoke_after_open(
        app: Flask, **kwargs: object
    ) -> tuple[str, OutlineItemUpdateDTO | None]:
        progress_bid, update = original_open_turn(app, **kwargs)
        assert update is not None
        assert update.title == draft_title
        with unit_of_work():
            AiCourseAuth.query.filter_by(
                course_id=identity, user_id=learner_bid
            ).one().status = 0
        return progress_bid, update

    monkeypatch.setattr(run_agent, "_open_turn", revoke_after_open)
    with pytest.raises(DraftTurnAccessRevokedError) as error:
        run(
            user_bid=learner_bid,
            preview_mode=False,
            after_open=lambda: pytest.fail(
                "The opening update escaped after revocation"
            ),
        )
    assert error.value.code == ERROR_CODE["server.shifu.noPermission"]
    assert calls == []


def test_preview_reset_rejects_an_in_flight_first_save(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    with pytest.raises(lesson_entry.DiscardedTurnError):
        run(
            after_open=lambda: reset_learn_record(
                app, identity, identity, identity, preview_mode=True
            )
        )
    assert history().elements == []
    assert load_agent_session(app, identity, identity) is None


def test_legacy_preview_recovers_once_and_never_uses_published_or_unowned_rows(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    legacy = Session(script=ScriptBundle(script="Legacy draft"), turn=4, finished=True)
    save_agent_session(
        app,
        legacy,
        user_bid=identity,
        shifu_bid=identity,
        outline_item_bid=identity,
        preview_mode=True,
    )
    with app.app_context(), unit_of_work():
        db.session.add(
            make_generated_element(
                element_bid=uuid.uuid4().hex,
                user_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                run_session_bid="unowned",
                element_type="text",
                content_text="Do not display this published or unowned content",
            )
        )
    assert history().elements == []
    run()
    assert "Teaching before question 1" in history().elements[0].content
    with app.app_context():
        rows = LearnAgentSession.query.filter_by(user_bid=identity).all()
        assert len(rows) == 2
        assert all(not row.deleted for row in rows)
    assert load_agent_session(app, identity, identity).id != legacy.id


def test_completed_preview_replays_without_running_a_finished_session(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, calls = classroom
    run()
    streamed = run("finish-preview")
    updates = [
        event.content for event in streamed if event.type == "outline_item_update"
    ]
    assert updates[-1].status == LearnStatus.COMPLETED
    assert streamed[-1].is_terminal
    assert (
        get_outline_item_tree(app, identity, identity, preview_mode=True)
        .outline_items[0]
        .status
        == LearnStatus.COMPLETED
    )
    original = history().model_dump()
    before = len(calls)
    run("")
    assert len(calls) == before
    assert history().model_dump() == original
    reset_learn_record(app, identity, identity, identity, preview_mode=True)
    assert history().elements == []


def test_reset_old_attempt_cannot_overwrite_a_new_preview(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    with app.app_context():
        old = (
            LearnProgressRecord.query.filter_by(user_bid=identity)
            .one()
            .progress_record_bid
        )
    stale = load_agent_session(app, identity, identity)
    reset_learn_record(app, identity, identity, identity, preview_mode=True)
    run()
    snapshot = history().model_dump()
    with app.app_context():
        assert not run_agent._persist(
            app,
            stale,
            memory=[],
            user_bid=identity,
            shifu_bid=identity,
            outline_bid=identity,
            progress_record_bid=old,
            generated_block_bid=uuid.uuid4().hex,
            taught="Discarded content",
        )
    assert history().model_dump() == snapshot


@pytest.mark.parametrize("corruption", ["schema", "json"])
def test_unreadable_preview_recovers_without_erasing_durable_history(
    app: Flask, classroom: tuple, corruption: str
) -> None:
    identity, run, history, _calls = classroom
    run()
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        if corruption == "schema":
            row.schema_version = 999
        else:
            data = json.loads(row.session_data)
            data["messages"] = "unreadable"
            row.session_data = json.dumps(data)
    run()
    records = history().elements
    assert len(records) == 4
    assert "question 1" in records[0].content
    assert "question 2" in records[2].content


@pytest.mark.parametrize("finished", [False, True])
def test_unknown_session_schema_does_not_erase_preview_progress(
    app: Flask, classroom: tuple, finished: bool
) -> None:
    identity, run, history, _calls = classroom
    run()
    if finished:
        run("finish-preview")
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        row.schema_version = 999
        structure = (
            LogDraftStruct.query.filter_by(shifu_bid=identity)
            .order_by(LogDraftStruct.id.desc())
            .first()
        )
        parsed = HistoryItem.from_json(structure.struct)
        parsed.children[0].content_revision += 1
        structure.struct = parsed.to_json()
    tree = get_outline_item_tree(app, identity, identity, preview_mode=True)
    lesson = tree.outline_items[0]
    assert lesson.status == (
        LearnStatus.COMPLETED if finished else LearnStatus.IN_PROGRESS
    )
    assert lesson.has_content_update_for_current_user is False
    assert history().has_content_update_for_current_user is False


def test_preview_reset_cannot_retire_another_courses_lesson(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    before = history().model_dump()
    reset_learn_record(app, "another-course", identity, identity, preview_mode=True)
    assert history().model_dump() == before


def test_draft_follow_ups_restore_at_owned_anchor_and_stay_retired_after_reset(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    anchor = history().elements[0].element_bid
    with app.app_context(), unit_of_work():
        adapter = ListenElementRunAdapter(
            app, shifu_bid=identity, outline_bid=identity, user_bid=identity
        )
        block = uuid.uuid4().hex
        progress = LearnProgressRecord.query.filter_by(user_bid=identity).one()
        stage_turn_block(
            user_bid=identity,
            shifu_bid=identity,
            outline_bid=identity,
            progress_record_bid=progress.progress_record_bid,
            generated_block_bid=block,
            position=0,
        )
        list(
            adapter.process(
                iter(
                    [
                        RunMarkdownFlowDTO(
                            outline_bid=identity,
                            generated_block_bid=block,
                            type=GeneratedType.ASK,
                            content="Explain this paragraph?",
                            anchor_element_bid=anchor,
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=identity,
                            generated_block_bid=block,
                            type=GeneratedType.CONTENT,
                            content="A draft explanation.",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=identity,
                            generated_block_bid=block,
                            type=GeneratedType.BREAK,
                            content="",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=identity,
                            generated_block_bid=block,
                            type=GeneratedType.DONE,
                            content="",
                        ),
                    ]
                )
            )
        )
    restored = history().elements
    assert [item.element_type for item in restored] == [
        ElementType.TEXT,
        ElementType.ASK,
        ElementType.ANSWER,
        ElementType.INTERACTION,
    ]
    assert restored[1].content == "Explain this paragraph?"
    assert restored[2].content == "A draft explanation."
    assert [item["role"] for item in restored[0].payload.asks] == ["student", "teacher"]
    reset_learn_record(app, identity, identity, identity, preview_mode=True)
    run()
    assert all(
        item.element_type not in {ElementType.ASK, ElementType.ANSWER}
        for item in history().elements
    )


def test_draft_update_timestamp_comes_from_the_shared_progress(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    start = now_utc() - timedelta(days=1)
    with app.app_context(), unit_of_work():
        row = LearnProgressRecord.query.filter_by(user_bid=identity, deleted=0).one()
        row.updated_at = start
        _change_draft_body(identity, "Edited script")
    run("An answer after editing")
    assert history().last_progress_updated_at == to_utc_iso(start)
    with app.app_context():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        assert row.updated_at > row.created_at
