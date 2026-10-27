"""Keep directory/history recommendations consistent across each teaching attempt."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.elements import run_adapter
from flaskr.service.learn.learn_dtos import LearnElementRecordDTO, LearnStatus
from flaskr.service.learn.learn_funcs import (
    get_current_lesson_outline,
    get_outline_item_tree,
    reset_learn_record,
)
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS, LEARN_STATUS_RESET
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.util.datetime import now_utc
from sqlalchemy import event


@pytest.fixture
def lesson(app: object, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Create independent formal/preview baselines and current physical versions."""
    identity = uuid4().hex
    # Rendering is covered by the classroom and listen-history suites. Keep the
    # formal integration focused on routing, current physical versions and flags.
    monkeypatch.setattr(
        run_adapter,
        "_get_listen_element_record",
        lambda **_kw: LearnElementRecordDTO(),
    )
    with app.app_context(), unit_of_work():
        for preview, course_model, outline_model, struct_model in [
            (False, PublishedShifu, PublishedOutlineItem, LogPublishedStruct),
            (True, DraftShifu, DraftOutlineItem, LogDraftStruct),
        ]:
            course = course_model(shifu_bid=identity, title="Course")
            outline = outline_model(
                shifu_bid=identity,
                outline_item_bid=identity,
                content="Original",
                type=401,
            )
            db.session.add_all([course, outline])
            db.session.flush()
            db.session.add(
                struct_model(
                    struct_bid=uuid4().hex,
                    shifu_bid=identity,
                    struct=HistoryItem(
                        bid=identity,
                        id=course.id,
                        type="shifu",
                        children=[
                            HistoryItem(
                                bid=identity,
                                id=outline.id,
                                type="outline",
                                content_revision=11,
                            )
                        ],
                    ).to_json(),
                )
            )
            db.session.add(
                LearnAgentSession(
                    agent_session_bid=uuid4().hex,
                    user_bid=identity,
                    shifu_bid=identity,
                    outline_item_bid=identity,
                    active_key=active_key_for(identity, identity, preview_mode=preview),
                    schema_version=1,
                    content_revision=11,
                    session_data=json.dumps(
                        {
                            "script": {"script": "Original"},
                            "messages": [{"kind": "request"}],
                        }
                    ),
                )
            )
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=uuid4().hex,
                user_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                status=LEARN_STATUS_IN_PROGRESS,
            )
        )
    return SimpleNamespace(identity=identity, app=app)


def _assert_flags(lesson: SimpleNamespace, preview: bool, expected: bool) -> None:
    identity, app = lesson.identity, lesson.app
    with app.app_context():
        record = run_adapter.get_listen_element_record(
            app, identity, identity, identity, preview
        )
        assert record.has_content_update_for_current_user is expected
        assert record.__json__()["has_content_update_for_current_user"] is expected
    tree = get_outline_item_tree(app, identity, identity, preview)
    assert tree.outline_items[0].has_content_update_for_current_user is expected


def _change_body(lesson: SimpleNamespace, preview: bool, content: str) -> None:
    model = DraftOutlineItem if preview else PublishedOutlineItem
    struct_model = LogDraftStruct if preview else LogPublishedStruct
    with lesson.app.app_context(), unit_of_work():
        outline = model.query.filter_by(shifu_bid=lesson.identity).one()
        if outline.content == content:
            return
        outline.content = content
        structure = struct_model.query.filter_by(shifu_bid=lesson.identity).one()
        parsed = HistoryItem.from_json(structure.struct)
        parsed.children[0].content_revision += 1
        structure.struct = parsed.to_json()


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("finished", [False, True])
def test_content_changes_reverts_and_resume_do_not_move_the_baseline(
    lesson: SimpleNamespace, preview: bool, finished: bool
) -> None:
    identity, app = lesson.identity, lesson.app
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(
            active_key=active_key_for(identity, identity, preview_mode=preview)
        ).one()
        row.finished = int(finished)
        if finished and not preview:
            LearnProgressRecord.query.filter_by(user_bid=identity).one().status = 603
    _assert_flags(lesson, preview, expected=False)
    _change_body(lesson, preview, "original")  # Equal length and case-only change.
    _assert_flags(lesson, preview, expected=True)
    _assert_flags(lesson, not preview, expected=False)
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(
            active_key=active_key_for(identity, identity, preview_mode=preview)
        ).one()
        document = json.loads(row.session_data)
        document["messages"].append({"kind": "response"})
        row.session_data = json.dumps(document)
        row.turn += 1
        LearnProgressRecord.query.filter_by(
            user_bid=identity
        ).one().updated_at = now_utc()
    _assert_flags(lesson, preview, expected=True)
    _change_body(lesson, preview, "Original")
    # Restoring the old text is a later revision, so the recommendation remains.
    _assert_flags(lesson, preview, expected=True)


@pytest.mark.parametrize("preview", [False, True])
def test_unrelated_settings_and_orphan_versions_do_not_trigger_notices(
    lesson: SimpleNamespace, preview: bool
) -> None:
    identity = lesson.identity
    model = DraftOutlineItem if preview else PublishedOutlineItem
    course_model = DraftShifu if preview else PublishedShifu
    with lesson.app.app_context(), unit_of_work():
        row = model.query.filter_by(shifu_bid=identity).one()
        row.title, row.position, row.llm = "Renamed", "9", "another-model"
        row.ask_enabled_status = 4202
        course_model.query.filter_by(shifu_bid=identity).one().title = "Renamed course"
        db.session.add(
            model(shifu_bid=identity, outline_item_bid=identity, content="Orphan")
        )
    _assert_flags(lesson, preview, expected=False)


@pytest.mark.parametrize("preview", [False, True])
def test_republishing_same_body_uses_the_current_struct_physical_record(
    lesson: SimpleNamespace, preview: bool
) -> None:
    identity = lesson.identity
    model = DraftOutlineItem if preview else PublishedOutlineItem
    struct_model = LogDraftStruct if preview else LogPublishedStruct
    with lesson.app.app_context(), unit_of_work():
        old = model.query.filter_by(shifu_bid=identity).one()
        old.content = "Old version changed"
        new = model(shifu_bid=identity, outline_item_bid=identity, content="Original")
        db.session.add(new)
        db.session.flush()
        structure = struct_model.query.filter_by(shifu_bid=identity).one()
        parsed = HistoryItem.from_json(structure.struct)
        parsed.children[0].id = new.id
        structure.struct = parsed.to_json()
    _assert_flags(lesson, preview, expected=False)


@pytest.mark.parametrize("preview", [False, True])
def test_cleared_body_retakes_are_scoped_and_new_sessions_establish_new_baselines(
    lesson: SimpleNamespace, preview: bool
) -> None:
    identity, app = lesson.identity, lesson.app
    _change_body(lesson, preview, "")
    _assert_flags(lesson, preview, expected=True)
    reset_learn_record(app, identity, identity, identity, preview_mode=preview)
    _assert_flags(lesson, preview, expected=False)
    with app.app_context():
        assert (
            LearnAgentSession.query.filter_by(
                active_key=active_key_for(identity, identity, preview_mode=not preview)
            )
            .one()
            .deleted
            == 0
        )
        progress = LearnProgressRecord.query.filter_by(user_bid=identity).one()
        assert progress.status == (
            LEARN_STATUS_IN_PROGRESS if preview else LEARN_STATUS_RESET
        )
    if preview:
        assert (
            get_outline_item_tree(app, identity, identity, preview_mode=True)
            .outline_items[0]
            .status
            == LearnStatus.NOT_STARTED
        )
    _change_body(lesson, preview, "New attempt")
    with app.app_context(), unit_of_work():
        struct_model = LogDraftStruct if preview else LogPublishedStruct
        structure = struct_model.query.filter_by(shifu_bid=identity).one()
        revision = HistoryItem.from_json(structure.struct).children[0].content_revision
        db.session.add(
            LearnAgentSession(
                agent_session_bid=uuid4().hex,
                user_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                active_key=active_key_for(identity, identity, preview_mode=preview),
                schema_version=1,
                content_revision=revision,
                session_data=json.dumps(
                    {"script": {"script": "New attempt"}, "messages": [{}]}
                ),
            )
        )
        if not preview:
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid=uuid4().hex,
                    user_bid=identity,
                    shifu_bid=identity,
                    outline_item_bid=identity,
                    status=LEARN_STATUS_IN_PROGRESS,
                )
            )
    _assert_flags(lesson, preview, expected=False)
    _change_body(lesson, preview, "Changed again")
    _assert_flags(lesson, preview, expected=True)


@pytest.mark.parametrize("baseline", [None, 0])
@pytest.mark.parametrize("preview", [False, True])
def test_unknown_baselines_never_infer_a_version_from_history(
    lesson: SimpleNamespace, preview: bool, baseline: int | None
) -> None:
    identity = lesson.identity
    _change_body(lesson, preview, "Changed")
    with lesson.app.app_context(), unit_of_work():
        LearnAgentSession.query.filter_by(
            active_key=active_key_for(identity, identity, preview_mode=preview)
        ).one().content_revision = baseline
    _assert_flags(lesson, preview, expected=False)


@pytest.mark.parametrize("preview", [False, True])
def test_missing_current_revision_never_uses_the_physical_row_id(
    lesson: SimpleNamespace, preview: bool
) -> None:
    _change_body(lesson, preview, "Changed")
    struct_model = LogDraftStruct if preview else LogPublishedStruct
    with lesson.app.app_context(), unit_of_work():
        structure = struct_model.query.filter_by(shifu_bid=lesson.identity).one()
        parsed = HistoryItem.from_json(structure.struct)
        parsed.children[0].content_revision = None
        structure.struct = parsed.to_json()
    _assert_flags(lesson, preview, expected=False)


def test_records_query_only_the_requested_published_session(
    lesson: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    loader = run_adapter.load_lesson_content_states

    def capture(**kwargs: object) -> dict:
        calls.append(kwargs["outline_revisions"])
        return loader(**kwargs)

    monkeypatch.setattr(run_adapter, "load_lesson_content_states", capture)
    with lesson.app.app_context():
        identity = lesson.identity
        run_adapter.get_listen_element_record(
            lesson.app, identity, identity, identity, preview_mode=False
        )
    assert len(calls) == 1
    assert list(calls[0]) == [lesson.identity]


def test_preview_without_its_own_session_never_borrows_published_history(
    lesson: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = lesson.identity
    _change_body(lesson, preview=True, content="")
    with lesson.app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(
            active_key=active_key_for(identity, identity, preview_mode=True)
        ).one()
        db.session.delete(row)

    def reject_legacy(**_kw: object) -> LearnElementRecordDTO:
        pytest.fail("Cleared 2.0 draft read formal history")

    monkeypatch.setattr(run_adapter, "_get_listen_element_record", reject_legacy)
    _assert_flags(lesson, preview=True, expected=False)
    reset_learn_record(lesson.app, identity, identity, identity, preview_mode=True)
    with lesson.app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(user_bid=identity).one().status
            == LEARN_STATUS_IN_PROGRESS
        )


def test_preview_classification_uses_the_struct_version_before_any_agent_session(
    lesson: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = lesson.identity
    with lesson.app.app_context(), unit_of_work():
        for row in LearnAgentSession.query.filter_by(user_bid=identity).all():
            db.session.delete(row)
        db.session.add(
            DraftOutlineItem(shifu_bid=identity, outline_item_bid=identity, content="")
        )

    def reject_legacy(**_kw: object) -> LearnElementRecordDTO:
        pytest.fail("An orphan blank draft redirected a current 2.0 preview")

    monkeypatch.setattr(run_adapter, "_get_listen_element_record", reject_legacy)
    _assert_flags(lesson, preview=True, expected=False)
    reset_learn_record(lesson.app, identity, identity, identity, preview_mode=True)
    with lesson.app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(user_bid=identity).one().status
            == LEARN_STATUS_IN_PROGRESS
        )


def test_preview_reuses_the_decoded_document(
    lesson: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn.agent import preview_history

    calls = []
    decode = json.loads

    def capture(value: str, *args: object, **kwargs: object) -> object:
        calls.append(value)
        return decode(value, *args, **kwargs)

    with lesson.app.app_context():
        identity = lesson.identity
        raw = (
            LearnAgentSession.query.filter_by(
                active_key=active_key_for(identity, identity, preview_mode=True)
            )
            .one()
            .session_data
        )
        monkeypatch.setattr(preview_history.json, "loads", capture)
        run_adapter.get_listen_element_record(
            lesson.app, identity, identity, identity, preview_mode=True
        )
    assert calls.count(raw) == 1


@pytest.mark.parametrize("content", ["Original", ""])
def test_agent_preview_directory_does_not_read_formal_progress(
    lesson: SimpleNamespace, content: str
) -> None:
    _change_body(lesson, preview=True, content=content)
    statements = []

    def capture(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    with lesson.app.app_context():
        engine = db.engine
        event.listen(engine, "before_cursor_execute", capture)
        try:
            get_outline_item_tree(
                lesson.app, lesson.identity, lesson.identity, preview_mode=True
            )
        finally:
            event.remove(engine, "before_cursor_execute", capture)
    assert not any("learn_progress_records" in statement for statement in statements)


def test_record_contract_defaults_to_false() -> None:
    assert (
        LearnElementRecordDTO().__json__()["has_content_update_for_current_user"]
        is False
    )


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize(
    "attribute", ["deleted", "hidden", "shifu_bid", "outline_item_bid"]
)
def test_current_physical_outline_must_be_visible_and_match_the_lesson(
    lesson: SimpleNamespace, preview: bool, attribute: str
) -> None:
    _change_body(lesson, preview, "Changed")
    model = DraftOutlineItem if preview else PublishedOutlineItem
    with lesson.app.app_context(), unit_of_work():
        row = model.query.filter_by(shifu_bid=lesson.identity).one()
        setattr(row, attribute, 1 if attribute in {"deleted", "hidden"} else "other")
    with lesson.app.app_context():
        record = run_adapter.get_listen_element_record(
            lesson.app, lesson.identity, lesson.identity, lesson.identity, preview
        )
        assert record.has_content_update_for_current_user is False
    tree = get_outline_item_tree(lesson.app, lesson.identity, lesson.identity, preview)
    assert not any(
        item.has_content_update_for_current_user for item in tree.outline_items
    )


@pytest.mark.parametrize(
    ("turn", "finished", "expected"),
    [(1, 0, LearnStatus.IN_PROGRESS), (0, 1, LearnStatus.COMPLETED)],
)
def test_unknown_legacy_preview_keeps_progress_without_an_update_notice(
    lesson: SimpleNamespace, turn: int, finished: int, expected: LearnStatus
) -> None:
    _change_body(lesson, preview=True, content="Changed")
    with lesson.app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(
            active_key=active_key_for(
                lesson.identity, lesson.identity, preview_mode=True
            )
        ).one()
        row.content_revision, row.turn, row.finished = None, turn, finished
    tree = get_outline_item_tree(
        lesson.app, lesson.identity, lesson.identity, preview_mode=True
    )
    assert tree.outline_items[0].status == expected
    _assert_flags(lesson, preview=True, expected=False)


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("child_type", ["block", "outline"])
def test_only_outline_children_exclude_a_lesson_from_content_update_detection(
    lesson: SimpleNamespace, preview: bool, child_type: str
) -> None:
    _change_body(lesson, preview, "Changed")
    struct_model = LogDraftStruct if preview else LogPublishedStruct
    with lesson.app.app_context(), unit_of_work():
        structure = struct_model.query.filter_by(shifu_bid=lesson.identity).one()
        parsed = HistoryItem.from_json(structure.struct)
        node = parsed.children[0]
        # A legacy block ID can equal an outline table's independent row ID.
        node.children = [HistoryItem(bid="legacy-child", id=node.id, type=child_type)]
        structure.struct = parsed.to_json()
    with lesson.app.app_context():
        current = get_current_lesson_outline(
            shifu_bid=lesson.identity,
            outline_bid=lesson.identity,
            preview_mode=preview,
        )
        assert (current is not None) is (child_type == "block")
    _assert_flags(lesson, preview, expected=child_type == "block")
    if child_type == "block":
        tree = get_outline_item_tree(
            lesson.app, lesson.identity, lesson.identity, preview
        )
        assert tree.outline_items[0].children == []
