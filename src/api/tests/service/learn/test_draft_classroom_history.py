"""Draft reloads preserve rendered teaching without touching published learning."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn import runscript_v2 as runtime
from flaskr.service.learn.agent import bridge, lesson_entry, routing
from flaskr.service.learn.agent.engine import ScriptBundle, Session
from flaskr.service.learn.agent.models import LearnAgentSession
from flaskr.service.learn.agent.preview_history import (
    begin_preview_run,
)
from flaskr.service.learn.agent.session_store import (
    PreviewGenerationDiscardedError,
    load_agent_session,
    preview_presentation,
    save_agent_session,
)
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    LearnStatus,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learn_funcs import get_outline_item_tree, reset_learn_record
from flaskr.service.learn.listen_elements import (
    ListenElementRunAdapter,
    get_listen_element_record,
)
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.user.repository import create_user_entity
from flaskr.util.datetime import now_utc, to_utc_iso
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import LearnElementRecordDTO
    from flaskr.service.metering.api import UsageContext
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.fixture
def classroom(app: Flask, monkeypatch: pytest.MonkeyPatch) -> tuple:
    """Exercise the real engine, adapter, database and classroom orchestrator offline."""
    identity = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        create_user_entity(user_bid=identity, identify=identity, nickname="Learner")
        course = DraftShifu(shifu_bid=identity, llm="1")
        lesson = DraftOutlineItem(
            shifu_bid=identity, outline_item_bid=identity, content="Teach.", type=401
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
                            bid=identity, id=lesson.id, type="outline", children=[]
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
    monkeypatch.setattr(
        lesson_entry,
        "_resolve",
        lambda *_a, **_k: (
            "Teach a topic, then ask a question. Wait for an answer before proceeding.",
            "",
            LLMSettings(model="test-model", temperature=0.0),
        ),
    )
    monkeypatch.setattr(lesson_entry, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(
        lesson_entry, "create_trace_with_root_span", lambda **_k: (Mock(), Mock())
    )
    monkeypatch.setattr(lesson_entry, "finalize_langfuse_trace", lambda **_k: None)
    monkeypatch.setattr(runtime, "uses_agent_engine", lambda _bid: True)
    monkeypatch.setattr(routing, "uses_agent_engine", lambda _bid: True)

    def drive(make_events: Callable, **_kwargs: object) -> Iterator:
        async def collect() -> list:
            return [event async for event in make_events()]

        return iter(asyncio.run(collect()))

    monkeypatch.setattr(bridge, "iter_turn", drive)

    def run(answer: str | None = None) -> list:
        with app.app_context():
            adapter = ListenElementRunAdapter(
                app,
                shifu_bid=identity,
                outline_bid=identity,
                user_bid=identity,
                persist_only_final=True,
            )
            return list(
                runtime._lesson_events(
                    app=app,
                    user_bid=identity,
                    shifu_bid=identity,
                    outline_bid=identity,
                    user_input=answer,
                    input_type=None,
                    reload_generated_block_bid=None,
                    reload_element_bid=None,
                    listen=False,
                    learning_mode="read",
                    preview_mode=True,
                    stop_event=None,
                    element_adapter=adapter,
                    heartbeat_interval=0.5,
                )
            )

    def history(**overrides: str) -> LearnElementRecordDTO:
        with app.app_context():
            return get_listen_element_record(
                app,
                overrides.get("course", identity),
                overrides.get("lesson", identity),
                overrides.get("user", identity),
                preview_mode=True,
            )

    return identity, run, history, calls


def test_reload_restores_teaching_before_pending_interaction_without_learner_progress(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, calls = classroom
    streamed = run()
    assert streamed[0].type == "outline_item_update"
    assert streamed[0].content.status == LearnStatus.IN_PROGRESS
    with app.app_context():
        assert LearnProgressRecord.query.filter_by(user_bid=identity).count() == 0
        assert LearnGeneratedBlock.query.filter_by(user_bid=identity).count() == 0
    records = history().elements
    assert [item.element_type for item in records] == [
        ElementType.TEXT,
        ElementType.INTERACTION,
    ]
    assert "Teaching before question 1." in records[0].content
    assert "Question 1?" in records[0].content
    restored_ids = [item.element_bid for item in records]
    replay = run("")
    assert [
        event.content.element_bid for event in replay if event.type == "element"
    ] == restored_ids
    assert replay[-1].is_terminal
    assert len(calls) == 1
    assert [item.element_bid for item in history().elements] == restored_ids


def test_multiple_requests_keep_order_and_accepted_answers(classroom: tuple) -> None:
    _identity, run, history, calls = classroom
    run()
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
    assert records[1].payload.user_input == "My answer"
    assert not records[-1].payload or not records[-1].payload.user_input
    assert len(calls) == 2
    assert history(user="someone-else").elements == []
    assert history(course="another-course").elements == []
    assert history(lesson="another-lesson").elements == []


def test_preview_catalog_and_reset_are_independent_of_published_learning(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=uuid.uuid4().hex,
                user_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                status=LEARN_STATUS_IN_PROGRESS,
            )
        )
    published = Session(script=ScriptBundle(script="Published teaching"), turn=9)
    save_agent_session(
        app, published, user_bid=identity, shifu_bid=identity, outline_item_bid=identity
    )
    assert (
        get_outline_item_tree(app, identity, identity, preview_mode=True)
        .outline_items[0]
        .status
        == LearnStatus.NOT_STARTED
    )
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
    assert load_agent_session(app, identity, identity).id == published.id
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(user_bid=identity).one().status
            == LEARN_STATUS_IN_PROGRESS
        )
    run()
    assert "question 2" in history().elements[0].content


def test_preview_reset_rejects_an_in_flight_first_save(
    app: Flask, classroom: tuple
) -> None:
    identity, _run, history, _calls = classroom
    generation = begin_preview_run(
        app,
        user_bid=identity,
        shifu_bid=identity,
        outline_bid=identity,
        run_bid="in-flight",
    )
    reset_learn_record(app, identity, identity, identity, preview_mode=True)
    staged = Mock()
    with pytest.raises(PreviewGenerationDiscardedError):
        save_agent_session(
            app,
            Session(script=ScriptBundle(script="Draft")),
            user_bid=identity,
            shifu_bid=identity,
            outline_item_bid=identity,
            preview_mode=True,
            preview_generation=generation,
            stage=staged,
        )
    staged.assert_not_called()
    assert history().elements == []
    assert load_agent_session(app, identity, identity, preview_mode=True) is None


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
            LearnGeneratedElement(
                element_bid=uuid.uuid4().hex,
                user_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                run_session_bid="unowned",
                event_type="element",
                element_type="text",
                content_text="Do not display this published or unowned content",
                status=1,
            )
        )
    assert history().elements == []
    run()
    assert "Teaching before question 1" in history().elements[0].content
    with app.app_context():
        rows = LearnAgentSession.query.filter_by(user_bid=identity).all()
        assert len(rows) == 2
        assert sum(row.deleted for row in rows) == 1
        active = next(row for row in rows if not row.deleted)
        assert preview_presentation(active)["runs"]
    assert (
        load_agent_session(app, identity, identity, preview_mode=True).id != legacy.id
    )


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


def test_reset_old_generation_cannot_overwrite_a_new_preview(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    with app.app_context():
        old = (
            LearnAgentSession.query.filter_by(user_bid=identity, deleted=0)
            .one()
            .agent_session_bid
        )
    stale = load_agent_session(app, identity, identity, preview_mode=True)
    reset_learn_record(app, identity, identity, identity, preview_mode=True)
    run()
    snapshot = history().model_dump()
    with pytest.raises(PreviewGenerationDiscardedError):
        save_agent_session(
            app,
            stale,
            user_bid=identity,
            shifu_bid=identity,
            outline_item_bid=identity,
            preview_mode=True,
            preview_generation=old,
        )
    assert history().model_dump() == snapshot


@pytest.mark.parametrize("corruption", ["schema", "json"])
def test_unreadable_preview_restarts_its_presentation_together(
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
    assert len(records) == 2
    assert "question 2" in records[0].content
    assert "question 1" not in records[0].content


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


def test_multiple_deferred_questions_keep_controls_and_individual_answers(
    app: Flask, classroom: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity, run, history, _calls = classroom

    async def several_questions(messages: list, _info: object) -> AsyncIterator:
        if any(isinstance(p, ToolCallPart) for m in messages for p in m.parts):
            yield "Completed."
            yield {
                0: DeltaToolCall(
                    name="finish",
                    tool_call_id="finish-many",
                    json_args='{"summary":"Done"}',
                )
            }
            return
        yield "Teaching before both questions."
        yield {
            index: DeltaToolCall(
                name="interact",
                tool_call_id=f"many-{index}",
                json_args=json.dumps({"type": "text", "prompt": f"Question {index}?"}),
            )
            for index in range(2)
        }

    class Gateway(FunctionModel):
        def set_usage_context(self, _context: UsageContext) -> None:
            pass

    gateway = Gateway(stream_function=several_questions)
    monkeypatch.setattr(lesson_entry, "GatewayModel", lambda *_a, **_k: gateway)
    run()
    controls = [
        e for e in history().elements if e.element_type == ElementType.INTERACTION
    ]
    assert len(controls) == 2
    assert len({e.element_bid for e in controls}) == 2
    run("First answer")
    controls = [
        e for e in history().elements if e.element_type == ElementType.INTERACTION
    ]
    assert len(controls) == 2
    assert controls[0].payload.user_input == "First answer"
    assert not controls[1].payload.user_input
    run("Second answer")
    controls = [
        e for e in history().elements if e.element_type == ElementType.INTERACTION
    ]
    assert [e.payload.user_input for e in controls] == ["First answer", "Second answer"]
    assert load_agent_session(app, identity, identity, preview_mode=True).finished


def test_draft_update_timestamp_stays_at_generation_start_after_answer(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    start = now_utc() - timedelta(days=1)
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        row.created_at = start
        DraftOutlineItem.query.filter_by(
            outline_item_bid=identity
        ).one().content = "Edited script"
    run("An answer after editing")
    assert history().last_progress_updated_at == to_utc_iso(start)
    with app.app_context():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        assert row.updated_at > row.created_at


def test_scriptless_draft_keeps_legacy_history_status_and_reset(
    app: Flask, classroom: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity, run, history, _calls = classroom
    progress = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        DraftOutlineItem.query.filter_by(outline_item_bid=identity).one().content = ""
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=progress,
                user_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                status=LEARN_STATUS_IN_PROGRESS,
            )
        )
        db.session.add(
            LearnGeneratedElement(
                element_bid=uuid.uuid4().hex,
                user_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                progress_record_bid=progress,
                generated_block_bid=uuid.uuid4().hex,
                run_session_bid="legacy-fallback",
                event_type="element",
                element_type="text",
                is_final=1,
                content_text="Legacy fallback teaching",
                status=1,
            )
        )

    def no_script(*_a: object, **_k: object) -> None:
        message = "No script"
        raise lesson_entry.LessonNotTeachable(message)

    fallback = []

    def legacy(**kwargs: object) -> Iterator:
        fallback.append(kwargs["element_adapter"].persist_only_final)
        return iter([])

    monkeypatch.setattr(lesson_entry, "_resolve", no_script)
    monkeypatch.setattr(runtime, "run_script_inner", legacy)
    run()
    assert fallback == [False]
    with app.app_context():
        assert LearnAgentSession.query.filter_by(user_bid=identity).count() == 0
    assert history().elements[0].content == "Legacy fallback teaching"
    assert (
        get_outline_item_tree(app, identity, identity, preview_mode=True)
        .outline_items[0]
        .status
        == LearnStatus.IN_PROGRESS
    )
    reset_learn_record(app, identity, identity, identity, preview_mode=True)
    assert history().elements == []
