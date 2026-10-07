"""Keep outline transitions on the publication retained by a running lesson."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import context_v2
from flaskr.service.learn.context_v2 import PaidError
from flaskr.service.learn.learn_dtos import GeneratedType, LearnStatus
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
)
from flaskr.service.shifu import shifu_publish_funcs
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_NORMAL, UNIT_TYPE_VALUE_TRIAL
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem

from tests.service.learn.test_run_published_revision import (
    _make_context,
    _seed_course,
)


@pytest.fixture
def progression_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        shifu_publish_funcs, "_run_summary_with_error_handling", lambda *_args: None
    )
    monkeypatch.setattr(
        context_v2, "create_trace_with_root_span", lambda **_kwargs: (None, None)
    )
    monkeypatch.setattr(context_v2, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(
        context_v2,
        "load_memory",
        lambda *_args: SimpleNamespace(as_variables=dict),
    )
    monkeypatch.setattr(
        context_v2, "get_profile_item_definition_list", lambda *_args: []
    )

    def fake_chat_llm(*_args: object, **_kwargs: object) -> object:
        yield SimpleNamespace(result="Generated lesson content")

    monkeypatch.setattr(context_v2, "chat_llm", fake_chat_llm)


def _seed_progression_course(
    app: object, *, second_hidden: bool = False
) -> SimpleNamespace:
    course = _seed_course(app)
    course.second_bid, course.third_bid = uuid4().hex, uuid4().hex
    with app.app_context(), unit_of_work():
        first = DraftOutlineItem.query.filter_by(
            outline_item_bid=course.outline_bid, deleted=0
        ).one()
        first.content = "Old first block"
        first.title = "Old first lesson"
        second = DraftOutlineItem(
            shifu_bid=course.course_bid,
            outline_item_bid=course.second_bid,
            title="Old second lesson",
            position="02",
            type=401,
            hidden=second_hidden,
            content="Old second block",
        )
        third = DraftOutlineItem(
            shifu_bid=course.course_bid,
            outline_item_bid=course.third_bid,
            title="Old third lesson",
            position="03",
            type=401,
            content="Old third block",
        )
        db.session.add_all([second, third])
        db.session.flush()
        draft = DraftShifu.query.filter_by(shifu_bid=course.course_bid, deleted=0).one()
        struct = HistoryItem(
            bid=course.course_bid,
            id=draft.id,
            type="shifu",
            children=[
                HistoryItem(
                    bid=row.outline_item_bid,
                    id=row.id,
                    type="outline",
                    children=[],
                    child_count=1,
                )
                for row in [first, second, third]
            ],
        )
        db.session.add(
            LogDraftStruct(
                struct_bid=uuid4().hex,
                shifu_bid=course.course_bid,
                struct=struct.to_json(),
            )
        )
    shifu_publish_funcs.publish_shifu_draft(
        app, course.user_bid, course.course_bid, "", sync_summary=True
    )
    return course


def _change_and_publish(
    app: object, course: SimpleNamespace, *, remove_second: bool = False
) -> None:
    with app.app_context(), unit_of_work():
        outlines = DraftOutlineItem.query.filter_by(
            shifu_bid=course.course_bid, deleted=0
        ).all()
        for outline in outlines:
            outline.title = outline.title.replace("Old", "New")
            if outline.outline_item_bid == course.second_bid:
                outline.hidden = not outline.hidden
                if remove_second:
                    outline.deleted = 1
    shifu_publish_funcs.publish_shifu_draft(
        app, course.user_bid, course.course_bid, "", sync_summary=True
    )


@pytest.mark.parametrize(
    ("second_hidden", "remove_second"), [(False, False), (True, False), (False, True)]
)
def test_republish_before_block_commit_keeps_bound_transition_visibility_and_title(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    progression_dependencies: object,
    second_hidden: bool,
    remove_second: bool,
) -> None:
    _ = progression_dependencies
    course = _seed_progression_course(app, second_hidden=second_hidden)
    publication = {"done": False}
    publisher_errors = []
    publisher_sessions = []
    original_init_generated_block = context_v2.init_generated_block

    def publish() -> None:
        try:
            with app.app_context():
                publisher_sessions.append(db.session())
                _change_and_publish(app, course, remove_second=remove_second)
        except Exception as exc:
            publisher_errors.append(exc)

    def publish_before_staging(*args: object, **kwargs: object) -> object:
        if not publication["done"]:
            # Resolve the old block first, publish using another real session,
            # and then let the recorder cross its actual finalize boundary.
            publication["done"] = True
            thread = threading.Thread(target=publish)
            thread.start()
            thread.join(timeout=10)
            assert not thread.is_alive()
            assert not publisher_errors
        return original_init_generated_block(*args, **kwargs)

    monkeypatch.setattr(context_v2, "init_generated_block", publish_before_staging)
    expected_next = course.third_bid if second_hidden else course.second_bid
    expected_title = "Old third lesson" if second_hidden else "Old second lesson"
    with app.app_context():
        context = _make_context(app, course)
        retained_struct = context._struct
        run_session = db.session()
        events = list(context.run_inner(app))
        assert publication["done"]
        assert publisher_sessions[0] is not run_session
        assert context._struct is retained_struct
        assert PublishedShifu.query.filter_by(id=retained_struct.id).one().deleted == 1
        updates = [
            event.content
            for event in events
            if event.type == GeneratedType.OUTLINE_ITEM_UPDATE
        ]
        started = [
            update for update in updates if update.status == LearnStatus.IN_PROGRESS
        ]
        assert [(update.outline_bid, update.title) for update in started] == [
            (course.outline_bid, "Old first lesson"),
            (expected_next, expected_title),
        ]
        assert context._current_outline_item.bid == expected_next
        with app.app_context():
            records = LearnProgressRecord.query.filter_by(
                user_bid=course.user_bid
            ).all()
            statuses = {record.outline_item_bid: record.status for record in records}
            assert statuses[course.outline_bid] == LEARN_STATUS_COMPLETED
            assert statuses[expected_next] == LEARN_STATUS_IN_PROGRESS


def test_republish_between_transition_resolution_and_emit_keeps_old_visibility(
    app: object, progression_dependencies: object
) -> None:
    _ = progression_dependencies
    course = _seed_progression_course(app)
    with app.app_context():
        context = _make_context(app, course)
        context._current_attend = context._get_current_attend(course.outline_bid)
        context._recorder.update_progress_pointer(
            context._current_attend, status=LEARN_STATUS_IN_PROGRESS, block_position=1
        )
        updates = context._get_next_outline_item()
        assert [update.outline_bid for update in updates] == [
            course.outline_bid,
            course.second_bid,
        ]
        _change_and_publish(app, course)
        events = list(context._render_outline_updates(updates))
        assert [
            (event.content.outline_bid, event.content.title) for event in events
        ] == [
            (course.outline_bid, "Old first lesson"),
            (course.second_bid, "Old second lesson"),
        ]
        assert context._current_outline_item.bid == course.second_bid


def test_draft_preview_progression_uses_active_draft_visibility_and_titles(
    app: object, progression_dependencies: object
) -> None:
    _ = progression_dependencies
    course = _seed_progression_course(app)
    with app.app_context():
        preview = _make_context(app, course, preview=True)
        published = _make_context(app, course)
        _change_and_publish(app, course)
        for context in [preview, published]:
            context._current_attend = context._get_current_attend(course.outline_bid)
            context._recorder.update_progress_pointer(
                context._current_attend,
                status=LEARN_STATUS_IN_PROGRESS,
                block_position=1,
            )
        preview_updates = preview._get_next_outline_item()
        assert [(update.outline_bid, update.title) for update in preview_updates] == [
            (course.outline_bid, "New first lesson"),
            (course.third_bid, "New third lesson"),
        ]
        published_updates = published._get_next_outline_item()
        assert [(update.outline_bid, update.title) for update in published_updates] == [
            (course.outline_bid, "Old first lesson"),
            (course.second_bid, "Old second lesson"),
        ]


def test_deleted_course_cannot_emit_bound_outline_transitions(
    app: object, progression_dependencies: object
) -> None:
    _ = progression_dependencies
    course = _seed_progression_course(app)
    with app.app_context():
        context = _make_context(app, course)
        context._current_attend = context._get_current_attend(course.outline_bid)
        context._recorder.update_progress_pointer(
            context._current_attend, status=LEARN_STATUS_IN_PROGRESS, block_position=1
        )
        updates = context._get_next_outline_item()
        with unit_of_work():
            PublishedShifu.query.filter_by(shifu_bid=course.course_bid).update(
                {"deleted": 1}
            )
            PublishedOutlineItem.query.filter_by(shifu_bid=course.course_bid).update(
                {"deleted": 1}
            )
        with pytest.raises(AppError) as error:
            list(context._render_outline_updates(updates))
        assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
        with pytest.raises(AppError) as resolution_error:
            context._get_next_outline_item()
        assert resolution_error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]


@pytest.mark.parametrize("mismatch", [False, True])
def test_missing_or_mismatched_bound_transition_row_does_not_use_latest_outline(
    app: object, progression_dependencies: object, mismatch: bool
) -> None:
    _ = progression_dependencies
    course = _seed_progression_course(app)
    with app.app_context():
        context = _make_context(app, course)
        context._current_attend = context._get_current_attend(course.outline_bid)
        context._recorder.update_progress_pointer(
            context._current_attend, status=LEARN_STATUS_IN_PROGRESS, block_position=1
        )
        updates = context._get_next_outline_item()
        second = context._get_outline_struct(course.second_bid)
        second.id = context._current_outline_item.id if mismatch else -1
        for resolve in [
            context._get_next_outline_item,
            lambda: list(context._render_outline_updates(updates)),
        ]:
            with pytest.raises(AppError) as error:
                resolve()
            assert error.value.code == ERROR_CODE["server.shifu.outlineItemNotFound"]


@pytest.mark.parametrize(
    ("old_type", "new_type"),
    [
        (UNIT_TYPE_VALUE_TRIAL, UNIT_TYPE_VALUE_NORMAL),
        (UNIT_TYPE_VALUE_NORMAL, UNIT_TYPE_VALUE_TRIAL),
    ],
)
def test_republish_keeps_bound_outline_type_for_new_progress_authorization(
    app: object,
    progression_dependencies: object,
    old_type: int,
    new_type: int,
) -> None:
    _ = progression_dependencies
    course = _seed_progression_course(app)
    with app.app_context(), unit_of_work():
        DraftOutlineItem.query.filter_by(outline_item_bid=course.second_bid).update(
            {"type": old_type}
        )
    shifu_publish_funcs.publish_shifu_draft(
        app, course.user_bid, course.course_bid, "", sync_summary=True
    )
    with app.app_context():
        context = _make_context(app, course)
        context._is_paid = False
        retained_second_id = context._get_outline_row_id(course.second_bid)
        with unit_of_work():
            DraftOutlineItem.query.filter_by(outline_item_bid=course.second_bid).update(
                {"type": new_type}
            )
        shifu_publish_funcs.publish_shifu_draft(
            app, course.user_bid, course.course_bid, "", sync_summary=True
        )
        retired = PublishedOutlineItem.query.filter_by(id=retained_second_id).one()
        assert retired.deleted == 1
        assert retired.type == old_type
        assert (
            PublishedOutlineItem.query.filter_by(
                outline_item_bid=course.second_bid, deleted=0
            )
            .one()
            .type
            == new_type
        )
        assert not LearnProgressRecord.query.filter_by(
            user_bid=course.user_bid, outline_item_bid=course.second_bid
        ).first()
        if old_type == UNIT_TYPE_VALUE_NORMAL:
            with pytest.raises(PaidError):
                context._get_current_attend(course.second_bid)
            assert not LearnProgressRecord.query.filter_by(
                user_bid=course.user_bid, outline_item_bid=course.second_bid
            ).first()
        else:
            progress = context._get_current_attend(course.second_bid)
            assert progress.outline_item_bid == course.second_bid
            assert progress.shifu_bid == course.course_bid
