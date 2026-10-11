"""Detect changed lesson sources from scoped, recognizable teaching snapshots."""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent.models import (
    AGENT_SESSION_SCHEMA_VERSION,
    LearnAgentSession,
    active_key_for,
)
from flaskr.service.learn.lesson_content_updates import (
    LessonContentState,
    _lesson_content_state_query,
    lesson_content_state_from_document,
    load_lesson_content_states,
)
from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem
from sqlalchemy import event
from sqlalchemy.dialects import mysql, sqlite


def _document(source: object = "Original lesson", **overrides: object) -> dict:
    return {
        "script": {"script": source, "constraints": "Old course prompt"},
        "messages": [{"kind": "request", "parts": []}],
        **overrides,
    }


def _seed(
    *,
    document: object,
    current_content: str,
    preview_mode: bool = False,
    raw_document: str | None = None,
    finished: bool = False,
    user_bid: str | None = None,
    shifu_bid: str | None = None,
) -> SimpleNamespace:
    user_bid = user_bid or uuid4().hex
    shifu_bid = shifu_bid or uuid4().hex
    outline_bid = uuid4().hex
    model = DraftOutlineItem if preview_mode else PublishedOutlineItem
    row = LearnAgentSession(
        agent_session_bid=uuid4().hex,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        active_key=active_key_for(user_bid, outline_bid, preview_mode=preview_mode),
        session_data=(
            json.dumps(document, ensure_ascii=False)
            if raw_document is None
            else raw_document
        ),
        schema_version=AGENT_SESSION_SCHEMA_VERSION,
        # Comparing source text does not deserialize pydantic-ai history.
        pydantic_ai_version="older-version",
        turn=0,
        finished=int(finished),
        deleted=0,
    )
    outline = model(
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        content=current_content,
        deleted=0,
    )
    with unit_of_work():
        db.session.add_all([row, outline])
        db.session.flush()
    return SimpleNamespace(
        row=row,
        outline=outline,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        outline_ids={outline_bid: outline.id},
        preview_mode=preview_mode,
    )


def _load(fixture: SimpleNamespace) -> dict[str, LessonContentState]:
    return load_lesson_content_states(
        user_bid=fixture.user_bid,
        shifu_bid=fixture.shifu_bid,
        preview_mode=fixture.preview_mode,
        outline_ids=fixture.outline_ids,
    )


def _parsed_state(fixture: SimpleNamespace, document: object) -> LessonContentState:
    return lesson_content_state_from_document(
        row=fixture.row,
        document=document,
        current_content=fixture.outline.content,
        user_bid=fixture.user_bid,
        shifu_bid=fixture.shifu_bid,
        outline_bid=fixture.outline_bid,
        preview_mode=fixture.preview_mode,
    )


@pytest.mark.parametrize("preview_mode", [False, True])
@pytest.mark.parametrize(
    ("original", "current", "changed"),
    [
        ("Lesson", "Lesson", False),
        ("Lesson", "lesson", True),
        ("café", "cafe", True),
        ("é", "e\u0301", True),
        ("讲解：{{姓名}}", "讲解：{{姓名}}", False),
        ("讲解：{{姓名}}", "讲解：学生", True),
        ("line one\r\nline two\rline three", "line one\nline two\nline three", False),
        ("text", "text ", True),
        (" text", "text", True),
        ("text\n", "text", True),
        ("before\x00after", "before\x00After", True),
        ("before\x00after", "before\x00after", False),
        ("", "New lesson", True),
        ("", "", False),
    ],
)
def test_sql_and_parsed_comparison_preserve_authored_text(
    app: object,
    preview_mode: bool,
    original: str,
    current: str,
    changed: bool,
) -> None:
    document = _document(original)
    with app.app_context():
        fixture = _seed(
            document=document,
            current_content=current,
            preview_mode=preview_mode,
        )
        expected = LessonContentState(started=True, has_content_update=changed)
        assert _load(fixture)[fixture.outline_bid] == expected
        assert _parsed_state(fixture, document) == expected
        # A partial persisted turn may have taught text without advancing turn.
        assert fixture.row.turn == 0


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        "string document",
        {},
        _document(None),
        _document(7),
        _document(source=False),
        _document(["Original lesson"]),
        _document({"source": "Original lesson"}),
        {"script": "Original lesson", "messages": [{}]},
        {"script": {}, "messages": [{}]},
        _document(messages=None),
        _document(messages=[]),
        _document(messages="nonempty string"),
        _document(messages=1),
        _document(messages=True),
        _document(messages={"0": {}}),
        {"script": {"script": "Original lesson"}},
    ],
)
def test_unrecognized_or_unstarted_documents_have_no_baseline(
    app: object, document: object
) -> None:
    with app.app_context():
        fixture = _seed(
            document=document, current_content="Changed lesson", finished=True
        )
        assert _load(fixture)[fixture.outline_bid] == LessonContentState()
        assert _parsed_state(fixture, document) == LessonContentState()


@pytest.mark.parametrize("raw_document", ["", "{", '{"script":', "not json"])
def test_invalid_json_does_not_fail_the_batch(app: object, raw_document: str) -> None:
    with app.app_context():
        broken = _seed(
            document=None,
            raw_document=raw_document,
            current_content="Changed lesson",
        )
        valid = _seed(
            document=_document(),
            current_content="Changed lesson",
            user_bid=broken.user_bid,
            shifu_bid=broken.shifu_bid,
        )
        broken.outline_ids.update(valid.outline_ids)
        assert _load(broken) == {
            broken.outline_bid: LessonContentState(),
            valid.outline_bid: LessonContentState(
                started=True, has_content_update=True
            ),
        }


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("user_bid", "another-user"),
        ("shifu_bid", "another-course"),
        ("outline_item_bid", "another-lesson"),
        ("active_key", None),
        ("active_key", "another-key"),
        ("deleted", 1),
        ("schema_version", AGENT_SESSION_SCHEMA_VERSION + 1),
        ("schema_version", 0),
    ],
)
def test_identity_and_schema_are_required_by_both_paths(
    app: object, attribute: str, value: object
) -> None:
    document = _document()
    with app.app_context():
        fixture = _seed(document=document, current_content="Changed lesson")
        with unit_of_work():
            setattr(fixture.row, attribute, value)
        assert _load(fixture) == {}
        assert _parsed_state(fixture, document) == LessonContentState()


def test_formal_and_preview_use_distinct_current_snapshots(app: object) -> None:
    with app.app_context():
        formal = _seed(document=_document(), current_content="Changed lesson")
        with unit_of_work():
            draft = DraftOutlineItem(
                shifu_bid=formal.shifu_bid,
                outline_item_bid=formal.outline_bid,
                content="Original lesson",
                deleted=0,
            )
            preview_row = LearnAgentSession(
                agent_session_bid=uuid4().hex,
                user_bid=formal.user_bid,
                shifu_bid=formal.shifu_bid,
                outline_item_bid=formal.outline_bid,
                active_key=active_key_for(
                    formal.user_bid, formal.outline_bid, preview_mode=True
                ),
                schema_version=AGENT_SESSION_SCHEMA_VERSION,
                session_data=json.dumps(_document()),
                finished=1,
                deleted=0,
            )
            db.session.add_all([draft, preview_row])
            db.session.flush()
        assert _load(formal)[formal.outline_bid] == LessonContentState(
            started=True, has_content_update=True
        )
        assert load_lesson_content_states(
            user_bid=formal.user_bid,
            shifu_bid=formal.shifu_bid,
            preview_mode=True,
            outline_ids={formal.outline_bid: draft.id},
        )[formal.outline_bid] == LessonContentState(started=True, finished=True)
        formal.preview_mode = True
        assert _parsed_state(formal, _document()) == LessonContentState()


@pytest.mark.parametrize(
    "attribute", ["deleted", "hidden", "shifu_bid", "outline_item_bid"]
)
def test_current_outline_identity_and_liveness_are_required(
    app: object, attribute: str
) -> None:
    with app.app_context():
        fixture = _seed(document=_document(), current_content="Changed lesson")
        with unit_of_work():
            setattr(
                fixture.outline,
                attribute,
                1 if attribute in {"deleted", "hidden"} else "other",
            )
        assert _load(fixture) == {}


def test_physical_row_mapping_is_not_replaced_by_latest_outline(app: object) -> None:
    with app.app_context():
        fixture = _seed(document=_document(), current_content="Original lesson")
        other = _seed(
            document=_document(),
            current_content="Changed lesson",
            user_bid=fixture.user_bid,
            shifu_bid=fixture.shifu_bid,
        )
        with unit_of_work():
            db.session.add(
                PublishedOutlineItem(
                    shifu_bid=fixture.shifu_bid,
                    outline_item_bid=fixture.outline_bid,
                    content="Newer row",
                    deleted=0,
                )
            )
        assert _load(fixture)[fixture.outline_bid].has_content_update is False
        fixture.outline_ids = {
            fixture.outline_bid: other.outline.id,
            other.outline_bid: fixture.outline.id,
        }
        assert _load(fixture) == {}


def test_another_requested_lessons_active_key_cannot_authorize_a_session(
    app: object,
) -> None:
    with app.app_context():
        first = _seed(document=_document(), current_content="Changed lesson")
        second = _seed(
            document=_document(),
            current_content="Changed lesson",
            user_bid=first.user_bid,
            shifu_bid=first.shifu_bid,
        )
        first.outline_ids.update(second.outline_ids)
        with unit_of_work():
            original_key = first.row.active_key
            first.row.active_key = None
            db.session.flush()
            second.row.active_key = original_key
        assert _load(first) == {}
        assert _parsed_state(second, _document()) == LessonContentState()


def test_batch_projects_only_scalar_state_in_one_select(app: object) -> None:
    with app.app_context():
        first = _seed(document=_document(), current_content="Changed lesson")
        second = _seed(
            document=_document(),
            current_content="Original lesson",
            finished=True,
            user_bid=first.user_bid,
            shifu_bid=first.shifu_bid,
        )
        first.outline_ids.update(second.outline_ids)
        db.session.expunge_all()
        statements = []

        def capture(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            assert _load(first) == {
                first.outline_bid: LessonContentState(
                    started=True, has_content_update=True
                ),
                second.outline_bid: LessonContentState(started=True, finished=True),
            }
            assert len(statements) == 1
            assert not db.session.identity_map
            assert "active_key IN" in statements[0]
            first.outline_ids = {}
            assert _load(first) == {}
            assert len(statements) == 1
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)


@pytest.mark.parametrize("dialect", [mysql.dialect(), sqlite.dialect()])
def test_query_compiles_with_guarded_json_and_exact_binary_comparison(
    dialect: object,
) -> None:
    query = _lesson_content_state_query(
        user_bid="learner",
        shifu_bid="course",
        preview_mode=False,
        outline_ids={"lesson": 3},
        dialect_name=dialect.name,
    )
    assert list(query.selected_columns.keys()) == [
        "outline_item_bid",
        "started",
        "finished",
        "source_changed",
    ]
    compiled = str(query.compile(dialect=dialect)).lower()
    assert "json_valid(learn_agent_sessions.session_data)" in compiled
    assert "json_type(" in compiled
    assert "active_key in" in compiled
    if dialect.name == "mysql":
        assert "force index (uq_learn_agent_sessions_active)" in compiled
        assert "json_table(case when" in compiled
        assert "source json path '$.script.script'" in compiled
        assert "messages_present integer exists path '$.messages[*]'" in compiled
        assert "json_extract(" not in compiled
        assert "json_unquote(" in compiled
        assert "json_length(" not in compiled
        assert " as binary)" in compiled
        assert "json_array_length(" not in compiled
    else:
        assert "force index" not in compiled
        assert "json_extract(case when" in compiled
        assert "json_array_length(" in compiled
        assert " as blob)" in compiled


@pytest.mark.parametrize("dialect_name", ["mariadb", "mysql"])
def test_older_mysql_and_mariadb_use_compatible_json_extraction(
    dialect_name: str,
) -> None:
    query = _lesson_content_state_query(
        user_bid="learner",
        shifu_bid="course",
        preview_mode=True,
        outline_ids={"lesson": 3},
        dialect_name=dialect_name,
        mysql_json_table=False,
    )
    compiled = str(query.compile(dialect=mysql.dialect())).lower()
    assert "json_table(" not in compiled
    assert "json_extract(case when" in compiled
    assert "json_unquote(" in compiled
    assert "json_length(" in compiled
