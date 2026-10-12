"""Keep body revisions stable through authoring, publication, and legacy upgrades."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.shifu import shifu_history_manager as history
from flaskr.service.shifu import shifu_mdflow_funcs as mdflow
from flaskr.service.shifu import shifu_publish_funcs as publishing
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from sqlalchemy import event


@pytest.fixture
def revision_course(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[str, str, int]]:
    course, lesson = uuid4().hex, uuid4().hex
    monkeypatch.setattr(mdflow, "check_text_with_risk_control", lambda *_a: None)
    monkeypatch.setattr(mdflow, "get_profile_item_definition_list", lambda *_a: [])
    monkeypatch.setattr(
        publishing, "_run_summary_with_error_handling", lambda *_a: None
    )
    with app.app_context():
        draft = DraftShifu(
            shifu_bid=course, title="Revision course", llm="ultimate", ask_llm="fast"
        )
        outline = DraftOutlineItem(
            shifu_bid=course,
            outline_item_bid=lesson,
            title="Lesson",
            position="01",
            content="Alpha\nBeta",
        )
        db.session.add_all([draft, outline])
        db.session.flush()
        history.save_shifu_history(app, "revision-author", course, draft.id)
        history.save_new_outline_history(
            app, "revision-author", course, lesson, outline.id, ""
        )
        baseline = int(outline.id)
        db.session.commit()
        yield course, lesson, baseline
        db.session.rollback()
        for model in (
            LogDraftStruct,
            LogPublishedStruct,
            DraftOutlineItem,
            PublishedOutlineItem,
            DraftShifu,
            PublishedShifu,
        ):
            model.query.filter_by(shifu_bid=course).delete(synchronize_session=False)
        db.session.commit()


def _revision(app: object, course: str, lesson: str) -> int:
    return history.outline_content_revisions(history.get_shifu_history(app, course))[
        lesson
    ]


def _publish(app: object, course: str, lesson: str) -> int:
    publishing.publish_shifu_draft(
        app, "revision-author", course, "https://example.test", sync_summary=True
    )
    row = (
        LogPublishedStruct.query.filter_by(shifu_bid=course)
        .order_by(LogPublishedStruct.id.desc())
        .first()
    )
    return history.outline_content_revisions(history.HistoryItem.from_json(row.struct))[
        lesson
    ]


def test_body_revision_is_shared_with_editor_and_stable_for_line_endings_and_republish(
    app: object, revision_course: tuple[str, str, int]
) -> None:
    course, lesson, baseline = revision_course
    assert _publish(app, course, lesson) == baseline
    for text in ("Alpha\r\nBeta", "Alpha\rBeta", "Alpha\nBeta"):
        result = mdflow.save_shifu_mdflow(
            app, "revision-author", course, lesson, text, base_revision=baseline
        )
        assert result == {"conflict": False, "new_revision": baseline}
        assert _revision(app, course, lesson) == baseline
        assert history.get_shifu_draft_meta(app, course, lesson)["revision"] == baseline
        assert _publish(app, course, lesson) == baseline


@pytest.mark.parametrize("changed", ["alpha\nBeta", "Alpha\nBeta ", "Alpha\nBETA", ""])
def test_changed_body_and_restore_each_get_new_revisions(
    app: object, revision_course: tuple[str, str, int], changed: str
) -> None:
    course, lesson, baseline = revision_course
    result = mdflow.save_shifu_mdflow(app, "revision-author", course, lesson, changed)
    changed_revision = result["new_revision"]
    assert changed_revision > baseline
    assert _revision(app, course, lesson) == changed_revision
    assert _publish(app, course, lesson) == changed_revision
    restored = mdflow.restore_shifu_mdflow_history_version(
        app, "revision-author", course, lesson, baseline
    )
    assert restored["restored"] is True
    assert restored["new_revision"] > changed_revision
    assert _revision(app, course, lesson) == restored["new_revision"]
    assert _publish(app, course, lesson) == restored["new_revision"]


def test_metadata_and_tree_rebuild_keep_body_revision(
    app: object, revision_course: tuple[str, str, int]
) -> None:
    course, lesson, baseline = revision_course
    outline = DraftOutlineItem.query.filter_by(id=baseline).one()
    renamed = outline.clone()
    renamed.title = "Renamed"
    renamed.llm_system_prompt = "New prompt"
    renamed.ask_enabled_status = 5102
    db.session.add(renamed)
    db.session.flush()
    history.save_outline_history(app, "revision-author", course, lesson, renamed.id)
    assert _revision(app, course, lesson) == baseline
    moved = renamed.clone()
    moved.position = "02"
    db.session.add(moved)
    db.session.flush()
    history.save_outline_tree_history(
        app,
        "revision-author",
        course,
        [history.HistoryItem(bid=lesson, id=moved.id, type="outline")],
    )
    db.session.commit()
    assert _revision(app, course, lesson) == baseline
    assert history.get_shifu_draft_revision(app, course, lesson) == baseline
    assert _publish(app, course, lesson) == baseline


def test_legacy_revision_is_initialized_on_write_without_read_backfill(
    app: object, revision_course: tuple[str, str, int]
) -> None:
    course, lesson, baseline = revision_course
    latest = (
        LogDraftStruct.query.filter_by(shifu_bid=course)
        .order_by(LogDraftStruct.id.desc())
        .first()
    )
    struct = history.HistoryItem.from_json(latest.struct)
    struct.children[0].content_revision = None
    latest.struct = struct.to_json()
    db.session.commit()
    logs_before = LogDraftStruct.query.filter_by(shifu_bid=course).count()
    assert (
        history.outline_content_revisions(history.get_shifu_history(app, course)) == {}
    )
    assert history.get_shifu_draft_revision(app, course, lesson) == baseline
    assert LogDraftStruct.query.filter_by(shifu_bid=course).count() == logs_before
    assert _publish(app, course, lesson) == baseline
    assert _revision(app, course, lesson) == baseline
    assert LogDraftStruct.query.filter_by(shifu_bid=course).count() == logs_before + 1


def test_publication_recovers_only_the_exact_row_being_published(
    app: object, revision_course: tuple[str, str, int]
) -> None:
    course, lesson, baseline = revision_course
    original = DraftOutlineItem.query.filter_by(id=baseline).one()
    result = mdflow.save_shifu_mdflow(app, "revision-author", course, lesson, "Changed")
    revisions = history.ensure_outline_content_revisions(
        app, "revision-author", course, [original]
    )
    assert revisions == {lesson: baseline}
    assert _revision(app, course, lesson) == result["new_revision"]


def test_cleanup_preserves_recorded_restore_revision_after_intermediate_history_expires(
    app: object, revision_course: tuple[str, str, int]
) -> None:
    course, lesson, baseline = revision_course
    changed = mdflow.save_shifu_mdflow(
        app, "revision-author", course, lesson, "Changed"
    )
    restored = mdflow.restore_shifu_mdflow_history_version(
        app, "revision-author", course, lesson, baseline
    )
    restored_revision = restored["new_revision"]
    DraftOutlineItem.query.filter_by(id=changed["new_revision"]).one().deleted = 1
    renamed = DraftOutlineItem.query.filter_by(id=restored_revision).one().clone()
    renamed.title = "Renamed after restoring"
    db.session.add(renamed)
    db.session.flush()
    history.save_outline_history(app, "revision-author", course, lesson, renamed.id)

    mdflow.cleanup_outline_history_versions(app, course, lesson, keep_versions=1)

    assert DraftOutlineItem.query.filter_by(id=restored_revision).one().deleted == 0
    assert _revision(app, course, lesson) == restored_revision
    assert history.get_shifu_draft_revision(app, course, lesson) == restored_revision
    assert (
        history.get_shifu_draft_meta(app, course, lesson)["revision"]
        == restored_revision
    )


def test_cleanup_preserves_a_legacy_anchor_established_at_the_lookback_limit(
    app: object,
    revision_course: tuple[str, str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    course, lesson, baseline = revision_course
    monkeypatch.setattr(history, "OUTLINE_CONTENT_LOOKBACK_LIMIT", 2)
    latest = (
        LogDraftStruct.query.filter_by(shifu_bid=course)
        .order_by(LogDraftStruct.id.desc())
        .first()
    )
    struct = history.HistoryItem.from_json(latest.struct)
    struct.children[0].content_revision = None
    original = DraftOutlineItem.query.filter_by(id=baseline).one()
    rows = []
    for title in ("Rename one", "Rename two", "Rename three"):
        renamed = original.clone()
        renamed.title = title
        db.session.add(renamed)
        db.session.flush()
        rows.append(renamed)
    struct.children[0].id = rows[-1].id
    latest.struct = struct.to_json()
    db.session.flush()
    recorded = history.ensure_outline_content_revisions(
        app, "revision-author", course, [rows[-1]]
    )[lesson]
    assert recorded == rows[-2].id
    mdflow.cleanup_outline_history_versions(app, course, lesson, keep_versions=1)
    assert DraftOutlineItem.query.filter_by(id=recorded).one().deleted == 0
    assert _revision(app, course, lesson) == recorded
    assert history.get_shifu_draft_revision(app, course, lesson) == recorded


def test_publish_locks_before_reading_drafts_and_reads_current_structure_for_update(
    app: object,
    revision_course: tuple[str, str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    course, lesson, baseline = revision_course
    locked = False
    original_lock = publishing.lock_shifu_for_outline_write
    original_load = publishing.load_existing_outline_items
    original_history = history.get_shifu_history
    history_lock_modes = []

    def lock(shifu_bid: str) -> None:
        nonlocal locked
        original_lock(shifu_bid)
        locked = True

    def load(*args: object, **kwargs: object) -> object:
        assert locked
        return original_load(*args, **kwargs)

    def read_history(*args: object, **kwargs: object) -> object:
        history_lock_modes.append(kwargs.get("for_update", False))
        return original_history(*args, **kwargs)

    monkeypatch.setattr(publishing, "lock_shifu_for_outline_write", lock)
    monkeypatch.setattr(publishing, "load_existing_outline_items", load)
    monkeypatch.setattr(history, "get_shifu_history", read_history)
    assert _publish(app, course, lesson) == baseline
    assert locked
    assert history_lock_modes == [True]


@pytest.mark.parametrize("lesson_count", [10, 100])
@pytest.mark.parametrize("entrypoint", ["history_write", "publication"])
def test_legacy_revision_initialization_batches_reads_across_lessons(
    app: object,
    revision_course: tuple[str, str, int],
    lesson_count: int,
    entrypoint: str,
) -> None:
    course, _, _ = revision_course
    lessons = [uuid4().hex for _ in range(lesson_count)]
    db.session.execute(
        DraftOutlineItem.__table__.insert(),
        [
            {
                "shifu_bid": course,
                "outline_item_bid": lesson,
                "content": content,
            }
            for lesson in lessons
            # The restored body spans two pages and must not reuse the first A.
            for content in ["Alpha\nBeta", "Changed"]
            + ["Alpha\r\nBeta", "Alpha\rBeta", "Alpha\nBeta"] * 7
        ],
    )
    versions = {lesson: [] for lesson in lessons}
    for row in (
        db.session.query(DraftOutlineItem.outline_item_bid, DraftOutlineItem.id)
        .filter(
            DraftOutlineItem.shifu_bid == course,
            DraftOutlineItem.outline_item_bid.in_(lessons),
        )
        .order_by(DraftOutlineItem.id)
        .all()
    ):
        versions[row.outline_item_bid].append(row.id)
    expected = {lesson: ids[2] for lesson, ids in versions.items()}
    latest_log = (
        LogDraftStruct.query.filter_by(shifu_bid=course)
        .order_by(LogDraftStruct.id.desc())
        .first()
    )
    struct = history.HistoryItem.from_json(latest_log.struct)
    struct.children.extend(
        history.HistoryItem(bid=lesson, id=ids[-1], type="outline")
        for lesson, ids in versions.items()
    )
    latest_log.struct = struct.to_json()
    db.session.flush()
    outlines = DraftOutlineItem.query.filter(
        DraftOutlineItem.id.in_([ids[-1] for ids in versions.values()])
    ).all()
    queries = []

    def record_query(
        _conn: object,
        _cursor: object,
        statement: str,
        _params: object,
        _context: object,
        _many: object,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT") and (
            DraftOutlineItem.__tablename__ in statement
        ):
            queries.append(statement)

    event.listen(db.engine, "before_cursor_execute", record_query)
    try:
        if entrypoint == "history_write":
            history.save_shifu_history(app, "revision-author", course, struct.id)
        else:
            assert (
                history.ensure_outline_content_revisions(
                    app, "revision-author", course, outlines
                )
                == expected
            )
        # Both sizes use two pages per bounded group, not two queries per lesson.
        # Authoring also loads the group's exact current rows once.
        group_count = 1 if lesson_count == 10 else 5
        assert len(queries) == group_count * (3 if entrypoint == "history_write" else 2)
        actual = history.outline_content_revisions(
            history.get_shifu_history(app, course)
        )
        assert {lesson: actual[lesson] for lesson in lessons} == expected

        queries.clear()
        history.save_shifu_history(app, "revision-author", course, struct.id)
        assert (
            history.ensure_outline_content_revisions(
                app, "revision-author", course, outlines
            )
            == expected
        )
        assert queries == []
    finally:
        event.remove(db.engine, "before_cursor_execute", record_query)


def test_batch_recovery_keeps_per_lesson_lookback_and_exact_physical_row_bounds(
    revision_course: tuple[str, str, int],
) -> None:
    course, _, _ = revision_course
    lessons = [uuid4().hex for _ in range(3)]
    db.session.execute(
        DraftOutlineItem.__table__.insert(),
        [
            {"shifu_bid": course, "outline_item_bid": lesson, "content": "Same"}
            for lesson in lessons
            for _ in range(history.OUTLINE_CONTENT_LOOKBACK_LIMIT + 1)
        ],
    )
    versions = {lesson: [] for lesson in lessons}
    for row in (
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == course,
            DraftOutlineItem.outline_item_bid.in_(lessons),
        )
        .order_by(DraftOutlineItem.id)
        .all()
    ):
        versions[row.outline_item_bid].append(row)
    first, second, third = [versions[lesson] for lesson in lessons]
    # Deleted rows do not consume the active-version lookback budget.
    third[-2].deleted = 1
    db.session.flush()
    assert history._outline_content_anchor_ids([first[-1], second[500], third[-1]]) == {
        first[-1].id: first[1].id,
        second[500].id: second[0].id,
        third[-1].id: third[0].id,
    }


def test_batch_initialization_validates_each_node_identity_and_preserves_recorded_revision(
    revision_course: tuple[str, str, int],
) -> None:
    course, lesson, baseline = revision_course
    original = DraftOutlineItem.query.filter_by(id=baseline).one()
    renamed = original.clone()
    deleted = original.clone()
    deleted.outline_item_bid = uuid4().hex
    deleted.deleted = 1
    db.session.add_all([renamed, deleted])
    db.session.flush()
    struct = history.HistoryItem(
        bid=course,
        id=0,
        type="shifu",
        children=[
            history.HistoryItem(bid=lesson, id=renamed.id, type="outline"),
            history.HistoryItem(bid="wrong-lesson", id=renamed.id, type="outline"),
            history.HistoryItem(bid=lesson, id=0, type="outline"),
            history.HistoryItem(
                bid=deleted.outline_item_bid, id=deleted.id, type="outline"
            ),
            history.HistoryItem(
                bid=lesson, id=renamed.id, type="outline", content_revision=renamed.id
            ),
        ],
    )
    history._initialize_outline_content_revisions(course, struct)
    assert [node.content_revision for node in struct.children] == [
        baseline,
        None,
        None,
        None,
        renamed.id,
    ]
    foreign = history.HistoryItem(
        bid="other-course",
        id=0,
        type="shifu",
        children=[history.HistoryItem(bid=lesson, id=renamed.id, type="outline")],
    )
    history._initialize_outline_content_revisions("other-course", foreign)
    assert foreign.children[0].content_revision is None
