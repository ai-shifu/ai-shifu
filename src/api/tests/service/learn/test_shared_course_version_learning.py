"""Run the same learning attempt before and after a course's first publication."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.api import langfuse_markdownflow
from flaskr.api import markdownflow as runtime_markdownflow
from flaskr.api.langfuse import MockClient
from flaskr.common.http import make_common_response
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn.agent import lesson_entry
from flaskr.service.learn.agent.lesson_source import resolve_lesson_source
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.agent.session_store import (
    _ATTEMPT_SOURCE_KEY,
    PREVIEW_PRESENTATION_KEY,
    load_agent_session,
    load_lesson_attempt_source,
)
from flaskr.service.learn.const import (
    CONTEXT_INTERACTION_NEXT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.elements.run_adapter import (
    ListenElementRunAdapter,
    get_listen_element_record,
)
from flaskr.service.learn.host import lesson as host_lesson
from flaskr.service.learn.learn_dtos import (
    ElementDTO,
    ElementType,
    GeneratedType,
    LearnStatus,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learn_funcs import get_outline_item_tree, reset_learn_record
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnLessonResetRecord,
    LearnProgressRecord,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
)
from flaskr.service.shifu import shifu_publish_funcs
from flaskr.service.shifu.consts import (
    ASK_MODE_DISABLE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.user.repository import create_user_entity
from markdownflow import bridge
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.common.fixtures.model_factories import make_progress_record

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from flask import Flask
    from flaskr.service.metering.api import UsageContext
    from markdownflow.engine.events import Event
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


_DraftOnly = tuple[str, str, str, str, list[list["ModelMessage"]]]


@pytest.fixture
def draft_only(
    app: Flask, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> _DraftOnly:
    course_bid, lesson_bid, learner_bid, owner_bid = (uuid4().hex for _ in range(4))
    with app.app_context(), unit_of_work():
        create_user_entity(
            user_bid=learner_bid, identify=learner_bid, nickname="Learner"
        )
        course = DraftShifu(
            shifu_bid=course_bid,
            title="First release",
            created_user_bid=owner_bid,
            llm="1",
        )
        outline = DraftOutlineItem(
            shifu_bid=course_bid,
            outline_item_bid=lesson_bid,
            title="First lesson",
            content="Explain the draft, then ask for a response.",
            type=401,
        )
        db.session.add_all([course, outline])
        db.session.flush()
        db.session.add_all(
            [
                AiCourseAuth(
                    course_id=course_bid,
                    user_id=learner_bid,
                    auth_type="view",
                    status=1,
                ),
                LogDraftStruct(
                    struct_bid=uuid4().hex,
                    shifu_bid=course_bid,
                    struct=HistoryItem(
                        bid=course_bid,
                        id=course.id,
                        type="shifu",
                        children=[
                            HistoryItem(
                                bid=lesson_bid,
                                id=outline.id,
                                type="outline",
                                content_revision=11,
                            )
                        ],
                    ).to_json(),
                ),
            ]
        )

    turns = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        turns.append(messages)
        number = len(turns)
        yield f"Teaching segment {number}."
        first_turn_questions = getattr(request, "param", 1)
        prompts = [f"Question {number}?"]
        if number == 1 and first_turn_questions == 2:
            prompts.append("Deferred question?")
        yield {
            index: DeltaToolCall(
                name="interact",
                tool_call_id=f"question-{number}-{index}",
                json_args=json.dumps({"type": "text", "prompt": prompt}),
            )
            for index, prompt in enumerate(prompts)
        }

    class Gateway(FunctionModel):
        def set_usage_context(self, context: UsageContext) -> None:
            assert context.progress_record_bid
            assert context.generated_block_bid

    gateway = Gateway(stream_function=model)
    monkeypatch.setattr(lesson_entry, "GatewayModel", lambda *_a, **_kw: gateway)
    monkeypatch.setattr(langfuse_markdownflow, "get_langfuse_client", MockClient)
    monkeypatch.setattr(shifu_publish_funcs, "get_shifu_summary", lambda *_args: None)

    def drive(
        make_events: Callable[[], AsyncIterator[Event]], **_kwargs: object
    ) -> Iterator[Event]:
        async def collect() -> list[Event]:
            return [event async for event in make_events()]

        return iter(asyncio.run(collect()))

    monkeypatch.setattr(bridge, "iter_turn", drive)
    return course_bid, lesson_bid, learner_bid, owner_bid, turns


def _run(
    app: Flask,
    course: str,
    lesson: str,
    user: str,
    *,
    preview: bool,
    answer: str | None = None,
    anchor: str | None = None,
    received: list[RunElementSSEMessageDTO] | None = None,
) -> list[RunElementSSEMessageDTO]:
    if received is None:
        received = []
    with app.app_context():
        received.extend(
            host_lesson._lesson_events(
                app=app,
                user_bid=user,
                shifu_bid=course,
                outline_bid=lesson,
                user_input=answer,
                input_type=None,
                reload_generated_block_bid=None,
                reload_element_bid=anchor,
                listen=False,
                learning_mode="read",
                preview_mode=preview,
                stop_event=None,
                element_adapter=ListenElementRunAdapter(
                    app,
                    shifu_bid=course,
                    outline_bid=lesson,
                    user_bid=user,
                    persist_only_final=True,
                ),
                heartbeat_interval=0.5,
            )
        )
    return received


def _publish(app: Flask, owner: str, course: str) -> None:
    shifu_publish_funcs.publish_shifu_draft(
        app, owner, course, "https://example.invalid", sync_summary=True
    )


def test_unpublished_draft_uses_same_progress_and_pending_question_after_first_publish(
    app: Flask, draft_only: _DraftOnly
) -> None:
    course, lesson, user, owner, turns = draft_only
    with app.app_context():
        assert PublishedShifu.query.filter_by(shifu_bid=course).first() is None

    _run(app, course, lesson, user, preview=True)
    with app.app_context():
        before = get_listen_element_record(app, course, lesson, user, preview_mode=True)
        assert any(
            "Teaching segment 1." in element.content for element in before.elements
        )
        progress = LearnProgressRecord.query.filter_by(
            user_bid=user, shifu_bid=course
        ).one()
        progress_bid = progress.progress_record_bid
        assert LearnGeneratedBlock.query.filter_by(
            progress_record_bid=progress_bid
        ).count()
        assert (
            get_outline_item_tree(app, course, user, preview_mode=True)
            .outline_items[0]
            .status
            == LearnStatus.IN_PROGRESS
        )
        session_id = load_agent_session(app, user, lesson).id

    _publish(app, owner, course)
    with app.app_context():
        published = get_listen_element_record(
            app, course, lesson, user, preview_mode=False
        )
        assert [el.element_bid for el in published.elements] == [
            el.element_bid for el in before.elements
        ]
        assert not published.has_content_update_for_current_user
        assert (
            get_outline_item_tree(app, course, user, preview_mode=False)
            .outline_items[0]
            .status
            == LearnStatus.IN_PROGRESS
        )
        assert load_agent_session(app, user, lesson).id == session_id

    _run(app, course, lesson, user, preview=False, answer="My first answer")
    with app.app_context():
        assert len(turns) >= 2
        assert load_agent_session(app, user, lesson).id == session_id
        assert (
            LearnProgressRecord.query.filter_by(user_bid=user, shifu_bid=course)
            .one()
            .progress_record_bid
            == progress_bid
        )
        scope = {"user_bid": user, "shifu_bid": course, "outline_bid": lesson}
        assert load_lesson_attempt_source(**scope).preview_mode
        draft = get_listen_element_record(app, course, lesson, user, preview_mode=True)
        published = get_listen_element_record(
            app, course, lesson, user, preview_mode=False
        )
        assert [el.element_bid for el in draft.elements] == [
            el.element_bid for el in published.elements
        ]
        assert any(
            "My first answer" in (el.payload.user_input or "")
            for el in published.elements
            if el.payload
        )

    reset_learn_record(app, course, lesson, user, preview_mode=False)
    with app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=progress_bid)
            .one()
            .status
            == LEARN_STATUS_RESET
        )
        assert not get_listen_element_record(
            app, course, lesson, user, preview_mode=True
        ).elements

    _run(app, course, lesson, user, preview=False)
    with app.app_context():
        assert not load_lesson_attempt_source(**scope).preview_mode
        assert load_agent_session(app, user, lesson).id != session_id


def test_published_entry_cannot_resume_private_draft_after_access_is_revoked(
    app: Flask, draft_only: _DraftOnly
) -> None:
    course, lesson, user, owner, turns = draft_only
    _run(app, course, lesson, user, preview=True)
    _publish(app, owner, course)
    with app.app_context(), unit_of_work():
        AiCourseAuth.query.filter_by(course_id=course, user_id=user).one().status = 0

    with app.app_context(), pytest.raises(AppError):
        get_listen_element_record(app, course, lesson, user, preview_mode=False)
    with pytest.raises(AppError):
        _run(app, course, lesson, user, preview=False, answer="Stale response")
    assert len(turns) == 1


def test_revoking_draft_permission_discards_pending_formal_teaching(
    app: Flask, draft_only: _DraftOnly, monkeypatch: pytest.MonkeyPatch
) -> None:
    course, lesson, user, owner, turns = draft_only
    _run(app, course, lesson, user, preview=True)
    _publish(app, owner, course)
    with app.app_context():
        saved_session = load_agent_session(app, user, lesson)
        assert saved_session is not None
        saved_turn = saved_session.turn

    iter_turn = runtime_markdownflow.iter_turn

    def revoke_during_turn(
        make_events: Callable[[], AsyncIterator[Event]], **kwargs: object
    ) -> Iterator[Event]:
        events = iter_turn(make_events, **kwargs)
        first_event = next(events)
        with app.app_context(), unit_of_work():
            AiCourseAuth.query.filter_by(
                course_id=course, user_id=user
            ).one().status = 0
        yield first_event
        yield from events

    monkeypatch.setattr(runtime_markdownflow, "iter_turn", revoke_during_turn)
    received = []
    with pytest.raises(AppError) as error:
        _run(
            app,
            course,
            lesson,
            user,
            preview=False,
            answer="Uncommitted response",
            received=received,
        )
    assert error.value.code == ERROR_CODE["server.shifu.noPermission"]
    assert not any(event.type == "element" for event in received)
    assert len(turns) == 2
    with app.app_context():
        stored_session = load_agent_session(app, user, lesson)
        assert stored_session is not None
        assert stored_session.turn == saved_turn


def test_switching_to_different_version_preserves_the_existing_attempt(
    app: Flask, draft_only: _DraftOnly
) -> None:
    course, lesson, user, owner, turns = draft_only
    _publish(app, owner, course)
    with app.app_context(), unit_of_work():
        old = DraftOutlineItem.query.filter_by(outline_item_bid=lesson).one()
        new = DraftOutlineItem(
            shifu_bid=course,
            outline_item_bid=lesson,
            title=old.title,
            content="Teach the changed draft scenario.",
            type=old.type,
            ask_enabled_status=ASK_MODE_DISABLE,
        )
        db.session.add(new)
        db.session.flush()
        current = LogDraftStruct.query.filter_by(shifu_bid=course).one()
        tree = HistoryItem.from_json(current.struct)
        tree.children[0].id = new.id
        tree.children[0].content_revision += 1
        current.struct = tree.to_json()
        old.deleted = 1

    _run(app, course, lesson, user, preview=True)
    with app.app_context():
        draft = get_listen_element_record(app, course, lesson, user, preview_mode=True)
        published = get_listen_element_record(
            app, course, lesson, user, preview_mode=False
        )
        assert [el.element_bid for el in published.elements] == [
            el.element_bid for el in draft.elements
        ]
        assert not draft.has_content_update_for_current_user
        assert published.has_content_update_for_current_user
        assert published.__json__()["follow_up_mode"] == "disabled"
        assert (
            get_outline_item_tree(app, course, user, preview_mode=False)
            .outline_items[0]
            .follow_up_mode
            == "text"
        )

    _run(app, course, lesson, user, preview=False, answer="Keep the same attempt")
    assert "Teach the changed draft scenario." in str(turns[-1])
    reset_learn_record(app, course, lesson, user, preview_mode=False)
    _run(app, course, lesson, user, preview=False)
    assert "Explain the draft, then ask for a response." in str(turns[-1])
    assert "Teach the changed draft scenario." not in str(turns[-1])


def _store_as_legacy_preview(app: Flask, course: str, lesson: str, user: str) -> str:
    """Convert the saved fixture into the pre-sharing preview storage format."""
    with app.app_context(), unit_of_work():
        # Represent the same teaching written by the old isolated preview path:
        # no progress or blocks, but exact adapter run and turn ownership.
        row = LearnAgentSession.query.filter_by(user_bid=user, shifu_bid=course).one()
        progress = LearnProgressRecord.query.filter_by(
            user_bid=user, shifu_bid=course
        ).one()
        blocks = (
            LearnGeneratedBlock.query.filter_by(
                progress_record_bid=progress.progress_record_bid
            )
            .filter(LearnGeneratedBlock.block_content_conf.contains('"agent_turn"'))
            .order_by(LearnGeneratedBlock.id.asc())
            .all()
        )
        turns, questions, runs = [], {}, set()
        for block in blocks:
            bid = block.generated_block_bid
            turn = json.loads(block.block_content_conf)["agent_turn"]
            questions[bid] = turn.pop("question_ids", [])
            turns.append(
                {
                    "block_bid": bid,
                    "record": turn,
                    "answered_question_id": turn.pop("answered_question_id", None),
                }
            )
            for element in LearnGeneratedElement.query.filter_by(
                generated_block_bid=bid
            ).all():
                runs.add(element.run_session_bid)
                element.progress_record_bid = ""
            db.session.delete(block)
        document = json.loads(row.session_data)
        del document[_ATTEMPT_SOURCE_KEY]
        document[PREVIEW_PRESENTATION_KEY] = {
            "version": 1,
            "runs": sorted(runs),
            "questions": questions,
            "answers": {},
            "turns": turns,
        }
        row.session_data = json.dumps(document)
        row.active_key = active_key_for(user, lesson, preview_mode=True)
        db.session.delete(progress)
        return document["id"]


def test_first_publication_can_resume_a_verifiable_legacy_preview(
    app: Flask, draft_only: _DraftOnly
) -> None:
    course, lesson, user, owner, _turns = draft_only
    _run(app, course, lesson, user, preview=True)
    session_id = _store_as_legacy_preview(app, course, lesson, user)

    _publish(app, owner, course)
    with app.app_context(), unit_of_work():
        DraftOutlineItem.query.filter_by(
            outline_item_bid=lesson
        ).one().ask_enabled_status = ASK_MODE_DISABLE
    with app.app_context():
        restored = get_listen_element_record(
            app, course, lesson, user, preview_mode=False
        )
        assert any("Teaching segment 1." in el.content for el in restored.elements)
        assert restored.follow_up_mode == "disabled"
        assert load_agent_session(app, user, lesson) is None

    _run(
        app, course, lesson, user, preview=False, answer="Answer to the legacy question"
    )
    with app.app_context():
        assert load_agent_session(app, user, lesson).id == session_id
        restored = get_listen_element_record(
            app, course, lesson, user, preview_mode=False
        )
        assert any(
            "Answer to the legacy question" in (el.payload.user_input or "")
            for el in restored.elements
            if el.payload
        )


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("draft_only", [2], indirect=True)
def test_deferred_question_keeps_original_control_through_first_publish(
    app: Flask, draft_only: _DraftOnly, legacy: bool
) -> None:
    course, lesson, user, owner, _turns = draft_only

    def controls(*, preview: bool) -> list[ElementDTO]:
        return [
            element
            for element in get_listen_element_record(
                app, course, lesson, user, preview_mode=preview
            ).elements
            if element.element_type == ElementType.INTERACTION
        ]

    _run(app, course, lesson, user, preview=True)
    with app.app_context():
        assert PublishedShifu.query.filter_by(shifu_bid=course).first() is None
        first, deferred = controls(preview=True)
        session_id = load_agent_session(app, user, lesson).id
        progress_bid = (
            LearnProgressRecord.query.filter_by(user_bid=user, shifu_bid=course)
            .one()
            .progress_record_bid
        )

    _run(app, course, lesson, user, preview=True, answer="Answer A")
    with app.app_context():
        preview = controls(preview=True)
        assert [item.element_bid for item in preview] == [
            first.element_bid,
            deferred.element_bid,
        ]
        assert json.loads(preview[0].payload.user_input)["inputText"] == "Answer A"
        assert not preview[1].payload.user_input
        assert (
            load_agent_session(app, user, lesson).pending[0].tool_call_id
            == "question-1-1"
        )

    if legacy:
        assert _store_as_legacy_preview(app, course, lesson, user) == session_id
    _publish(app, owner, course)

    if not legacy:
        with app.app_context():
            assert [item.element_bid for item in controls(preview=False)] == [
                first.element_bid,
                deferred.element_bid,
            ]

    _run(
        app,
        course,
        lesson,
        user,
        preview=False,
        answer="Answer B",
        anchor=deferred.element_bid,
    )
    with app.app_context():
        assert load_agent_session(app, user, lesson).id == session_id
        active_progress = LearnProgressRecord.query.filter_by(
            user_bid=user, shifu_bid=course
        ).one()
        assert (active_progress.progress_record_bid != progress_bid) is legacy
        published = controls(preview=False)
        assert [item.element_bid for item in published[:2]] == [
            first.element_bid,
            deferred.element_bid,
        ]
        assert [
            json.loads(item.payload.user_input)["inputText"] for item in published[:2]
        ] == [
            "Answer A",
            "Answer B",
        ]
        assert [item.payload.interaction_question for item in published] == [
            "Question 1?",
            "Deferred question?",
            "Question 2?",
        ]


def test_started_formal_progress_blocks_legacy_preview_promotion(
    app: Flask, draft_only: _DraftOnly
) -> None:
    course, lesson, user, owner, _turns = draft_only
    _run(app, course, lesson, user, preview=True)
    session_id = _store_as_legacy_preview(app, course, lesson, user)
    _publish(app, owner, course)
    formal_bid, placeholder_bid = uuid4().hex, uuid4().hex
    scope = {"user_bid": user, "shifu_bid": course, "outline_item_bid": lesson}
    with app.app_context(), unit_of_work():
        db.session.add(
            make_progress_record(
                **scope, progress_record_bid=formal_bid, status=LEARN_STATUS_IN_PROGRESS
            )
        )
        db.session.flush()
        db.session.add(
            make_progress_record(
                **scope,
                progress_record_bid=placeholder_bid,
                status=LEARN_STATUS_NOT_STARTED,
            )
        )

    with app.app_context():
        version = resolve_lesson_source(
            app,
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            preview_mode=False,
            promote_legacy=True,
        )
        assert not version.source.preview_mode
        assert version.progress_record_bid == formal_bid
        assert load_agent_session(app, user, lesson) is None
        assert load_agent_session(app, user, lesson, preview_mode=True).id == session_id
        assert (
            LearnProgressRecord.query.filter_by(progress_record_bid=placeholder_bid)
            .one()
            .status
            == LEARN_STATUS_NOT_STARTED
        )


@pytest.mark.parametrize(
    ("last_turn", "recover_in_draft"),
    [
        ("missing", False),
        ("missing_question", False),
        ("silent_finish", False),
        ("silent_finish", True),
    ],
)
def test_legacy_preview_promotion_requires_recoverable_turn_presentation(
    app: Flask, draft_only: _DraftOnly, last_turn: str, recover_in_draft: bool
) -> None:
    course, lesson, user, owner, _turns = draft_only
    chapter_bid, next_lesson_bid, earlier_lesson_bid, hidden_lesson_bid = (
        uuid4().hex for _ in range(4)
    )
    _run(app, course, lesson, user, preview=True)

    if last_turn == "silent_finish":

        async def finish(
            _messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[dict[int, DeltaToolCall]]:
            yield {
                0: DeltaToolCall(name="finish", tool_call_id="finish", json_args="{}")
            }

        lesson_entry.GatewayModel().stream_function = finish

    _run(app, course, lesson, user, preview=True, answer="First answer")
    session_id = _store_as_legacy_preview(app, course, lesson, user)
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(user_bid=user, shifu_bid=course).one()
        turns = json.loads(row.session_data)[PREVIEW_PRESENTATION_KEY]["turns"]
        first_turn, second_turn = turns
        assert LearnGeneratedElement.query.filter_by(
            generated_block_bid=first_turn["block_bid"], event_type="element"
        ).count()
        final_rows = LearnGeneratedElement.query.filter_by(
            generated_block_bid=second_turn["block_bid"]
        ).all()
        assert final_rows
        if last_turn == "silent_finish":
            assert any(row.event_type == GeneratedType.DONE.value for row in final_rows)
            assert all(row.event_type != "element" for row in final_rows)
            lesson_row = DraftOutlineItem.query.filter_by(outline_item_bid=lesson).one()
            lesson_row.position = "0103"
            lesson_row.parent_bid = chapter_bid
            db.session.add_all(
                [
                    DraftOutlineItem(
                        shifu_bid=course,
                        outline_item_bid=chapter_bid,
                        position="01",
                        title="Completed chapter",
                    ),
                    DraftOutlineItem(
                        shifu_bid=course,
                        outline_item_bid=next_lesson_bid,
                        position="02",
                        title="Next lesson",
                    ),
                    DraftOutlineItem(
                        shifu_bid=course,
                        outline_item_bid=earlier_lesson_bid,
                        parent_bid=chapter_bid,
                        position="0101",
                    ),
                    DraftOutlineItem(
                        shifu_bid=course,
                        outline_item_bid=hidden_lesson_bid,
                        parent_bid=chapter_bid,
                        position="0102",
                        hidden=1,
                    ),
                ]
            )
        else:
            for snapshot in final_rows:
                if (
                    last_turn == "missing"
                    or snapshot.element_type == ElementType.INTERACTION.value
                ):
                    db.session.delete(snapshot)

    _publish(app, owner, course)
    if last_turn == "silent_finish":
        with app.app_context(), unit_of_work():
            # The next lesson is visible only in the published catalog.
            DraftOutlineItem.query.filter_by(
                outline_item_bid=next_lesson_bid
            ).one().hidden = 1
    with app.app_context():
        version = resolve_lesson_source(
            app,
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            preview_mode=recover_in_draft,
            promote_legacy=True,
        )
        if last_turn == "silent_finish":
            assert version.source.preview_mode
            assert load_agent_session(app, user, lesson).id == session_id
            progress_rows = LearnProgressRecord.query.filter_by(
                shifu_bid=course, user_bid=user
            )
            completed_outline = {
                lesson: LEARN_STATUS_COMPLETED,
                chapter_bid: LEARN_STATUS_COMPLETED,
                next_lesson_bid: LEARN_STATUS_IN_PROGRESS,
            }
            lesson_update = {
                "outline_bid": lesson,
                "status": "completed",
                "title": "First lesson",
                "has_children": False,
            }
            chapter_update = {
                "outline_bid": chapter_bid,
                "status": "completed",
                "title": "Completed chapter",
                "has_children": True,
            }
            next_update = {
                "outline_bid": next_lesson_bid,
                "status": "in_progress",
                "title": "Next lesson",
                "has_children": False,
            }
            if recover_in_draft:
                assert {row.outline_item_bid: row.status for row in progress_rows} == {
                    lesson: LEARN_STATUS_COMPLETED,
                }
                draft = get_listen_element_record(
                    app, course, lesson, user, preview_mode=True
                )
                assert make_common_response(draft).get_json()["data"][
                    "outline_progress_updates"
                ] == [lesson_update]
                block_rows = LearnGeneratedBlock.query.filter_by(
                    shifu_bid=course, user_bid=user
                )
                blocks_before = block_rows.count()
                for _ in range(2):
                    reopened = get_listen_element_record(
                        app, course, lesson, user, preview_mode=False
                    )
                    payload = make_common_response(reopened).get_json()["data"]
                    assert payload["outline_progress_updates"] == [
                        lesson_update,
                        chapter_update,
                        next_update,
                    ]
                    assert (
                        sum(
                            CONTEXT_INTERACTION_NEXT in item.content
                            for item in reopened.elements
                        )
                        == 1
                    )
                assert block_rows.count() == blocks_before
            assert {
                row.outline_item_bid: row.status for row in progress_rows
            } == completed_outline
            if recover_in_draft:
                assert reset_learn_record(app, course, next_lesson_bid, user)
                reopened = get_listen_element_record(
                    app, course, lesson, user, preview_mode=False
                )
                payload = make_common_response(reopened).get_json()["data"]
                assert payload["outline_progress_updates"] == [
                    lesson_update,
                    chapter_update,
                    {**next_update, "status": "not_started"},
                ]
                assert (
                    progress_rows.filter_by(outline_item_bid=next_lesson_bid)
                    .one()
                    .status
                    == LEARN_STATUS_RESET
                )
                with unit_of_work():
                    db.session.add(
                        make_progress_record(
                            user_bid=user,
                            shifu_bid=course,
                            outline_item_bid=next_lesson_bid,
                            progress_record_bid=uuid4().hex,
                            status=LEARN_STATUS_COMPLETED,
                        )
                    )
                reopened = get_listen_element_record(
                    app, course, lesson, user, preview_mode=False
                )
                payload = make_common_response(reopened).get_json()["data"]
                assert payload["outline_progress_updates"] == [
                    lesson_update,
                    chapter_update,
                    {**next_update, "status": "completed"},
                ]
                earlier_attempt_bid = uuid4().hex
                with unit_of_work():
                    progress_rows.filter_by(
                        outline_item_bid=chapter_bid
                    ).one().status = LEARN_STATUS_IN_PROGRESS
                    db.session.add_all(
                        [
                            make_progress_record(
                                user_bid=user,
                                shifu_bid=course,
                                outline_item_bid=bid,
                                progress_record_bid=uuid4().hex,
                                status=LEARN_STATUS_RESET,
                            )
                            for bid in (earlier_lesson_bid, hidden_lesson_bid)
                        ]
                    )
                    db.session.add(
                        make_progress_record(
                            user_bid=user,
                            shifu_bid=course,
                            outline_item_bid=earlier_lesson_bid,
                            progress_record_bid=earlier_attempt_bid,
                            status=LEARN_STATUS_NOT_STARTED,
                        )
                    )
                earlier_attempt = progress_rows.filter_by(
                    progress_record_bid=earlier_attempt_bid
                )
                for retake_status in (
                    LEARN_STATUS_NOT_STARTED,
                    LEARN_STATUS_IN_PROGRESS,
                ):
                    with unit_of_work():
                        earlier_attempt.one().status = retake_status
                    reopened = get_listen_element_record(
                        app, course, lesson, user, preview_mode=False
                    )
                    assert reopened.outline_progress_updates[1].__json__() == {
                        **chapter_update,
                        "status": "in_progress",
                    }
                    assert (
                        progress_rows.filter_by(outline_item_bid=chapter_bid)
                        .one()
                        .status
                        == LEARN_STATUS_IN_PROGRESS
                    )
                with unit_of_work():
                    earlier_attempt.one().status = LEARN_STATUS_COMPLETED
                reopened = get_listen_element_record(
                    app, course, lesson, user, preview_mode=False
                )
                assert reopened.outline_progress_updates[1].__json__() == chapter_update
                assert reset_learn_record(app, course, earlier_lesson_bid, user)
                reopened = get_listen_element_record(
                    app, course, lesson, user, preview_mode=False
                )
                assert reopened.outline_progress_updates[1].__json__() == chapter_update
        else:
            assert not version.source.preview_mode
            assert load_agent_session(app, user, lesson) is None
            assert (
                load_agent_session(app, user, lesson, preview_mode=True).id
                == session_id
            )


def test_legacy_preview_promotion_retains_answers_and_exact_anchored_follow_ups(
    app: Flask, draft_only: _DraftOnly
) -> None:
    course, lesson, user, owner, _turns = draft_only
    _run(app, course, lesson, user, preview=True)
    _run(app, course, lesson, user, preview=True, answer="First answer")
    _store_as_legacy_preview(app, course, lesson, user)
    scope = {"user_bid": user, "shifu_bid": course, "outline_item_bid": lesson}
    follow_ups = []
    with app.app_context(), unit_of_work():
        anchor_bid = (
            LearnGeneratedElement.query.filter_by(
                **scope, event_type="element", element_type=ElementType.TEXT.value
            )
            .order_by(LearnGeneratedElement.id)
            .first()
            .element_bid
        )
        for index, anchor in enumerate([anchor_bid, anchor_bid, "unrelated-anchor"]):
            placeholder_bid, question_bid, answer_bid = (uuid4().hex for _ in range(3))
            question, answer = f"Follow-up {index}?", f"Reply {index}."
            follow_ups.append((placeholder_bid, question_bid, answer_bid))
            db.session.add(
                make_progress_record(
                    **scope,
                    progress_record_bid=placeholder_bid,
                    status=LEARN_STATUS_NOT_STARTED,
                )
            )
            for bid, content, role, kind in (
                (question_bid, question, ROLE_STUDENT, BLOCK_TYPE_MDASK_VALUE),
                (answer_bid, answer, ROLE_TEACHER, BLOCK_TYPE_MDANSWER_VALUE),
            ):
                db.session.add(
                    LearnGeneratedBlock(
                        **scope,
                        progress_record_bid=placeholder_bid,
                        generated_block_bid=bid,
                        generated_content=content,
                        role=role,
                        type=kind,
                        status=1,
                    )
                )
            db.session.flush()
            adapter = ListenElementRunAdapter(
                app, user_bid=user, shifu_bid=course, outline_bid=lesson
            )
            list(
                adapter.process(
                    RunMarkdownFlowDTO(
                        outline_bid=lesson,
                        generated_block_bid=answer_bid,
                        type=event_type,
                        content=content,
                        anchor_element_bid=anchor
                        if event_type == GeneratedType.ASK
                        else "",
                    )
                    for event_type, content in (
                        (GeneratedType.ASK, question),
                        (GeneratedType.CONTENT, answer),
                        (GeneratedType.BREAK, ""),
                    )
                )
            )

    _publish(app, owner, course)
    with app.app_context():
        version = resolve_lesson_source(
            app,
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            preview_mode=False,
            promote_legacy=True,
        )
        assert version.source.preview_mode
        restored = get_listen_element_record(
            app, course, lesson, user, preview_mode=False
        )
        assert any(
            "First answer" in (element.payload.user_input or "")
            for element in restored.elements
            if element.payload
        )
        assert [
            element.content
            for element in restored.elements
            if element.element_type in {ElementType.ASK, ElementType.ANSWER}
        ] == ["Follow-up 0?", "Reply 0.", "Follow-up 1?", "Reply 1."]
        for index, (placeholder_bid, question_bid, answer_bid) in enumerate(follow_ups):
            expected = version.progress_record_bid if index < 2 else placeholder_bid
            for bid in (question_bid, answer_bid):
                assert (
                    LearnGeneratedBlock.query.filter_by(generated_block_bid=bid)
                    .one()
                    .progress_record_bid
                    == expected
                )


def test_retry_of_empty_reset_preserves_the_draft_attempt_started_after_it(
    app: Flask, draft_only: _DraftOnly
) -> None:
    course, lesson, user, owner, _turns = draft_only
    _publish(app, owner, course)
    request_id = "empty-reset-retry"
    assert reset_learn_record(
        app, course, lesson, user, preview_mode=False, reset_request_id=request_id
    )
    _run(app, course, lesson, user, preview=True)
    with app.app_context():
        started = load_agent_session(app, user, lesson)
        assert started is not None
        assert started.pending
    assert reset_learn_record(
        app, course, lesson, user, preview_mode=True, reset_request_id=request_id
    )
    with app.app_context():
        resumed = load_agent_session(app, user, lesson)
        assert resumed is not None
        assert resumed.id == started.id
        receipt = LearnLessonResetRecord.query.filter_by(
            user_bid=user, shifu_bid=course
        ).one()
        assert receipt.counted == 0
        assert receipt.progress_record_bid == ""
