"""Compare scoped body revisions without inspecting lesson or conversation text."""

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
    lesson_content_state_from_session,
    load_lesson_content_states,
)
from sqlalchemy import event


def _seed(
    *,
    baseline: int | None = 11,
    current: int | None = 12,
    preview: bool = False,
    turn: int = 0,
    finished: int = 0,
    user_bid: str | None = None,
    shifu_bid: str | None = None,
    outline_bid: str | None = None,
) -> SimpleNamespace:
    user_bid, shifu_bid = user_bid or uuid4().hex, shifu_bid or uuid4().hex
    outline_bid = outline_bid or uuid4().hex
    row = LearnAgentSession(
        agent_session_bid=uuid4().hex,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        active_key=active_key_for(user_bid, outline_bid, preview_mode=preview),
        content_revision=baseline,
        # Revision reads do not deserialize history; resuming owns validation.
        session_data="not json",
        schema_version=AGENT_SESSION_SCHEMA_VERSION,
        pydantic_ai_version="older-version",
        turn=turn,
        finished=finished,
        deleted=0,
    )
    with unit_of_work():
        db.session.add(row)
    return SimpleNamespace(
        row=row,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        outline_revisions={outline_bid: current},
        preview_mode=preview,
    )


def _load(fixture: SimpleNamespace) -> dict[str, LessonContentState]:
    return load_lesson_content_states(
        user_bid=fixture.user_bid,
        shifu_bid=fixture.shifu_bid,
        preview_mode=fixture.preview_mode,
        outline_revisions=fixture.outline_revisions,
    )


def _loaded_state(fixture: SimpleNamespace) -> LessonContentState:
    return lesson_content_state_from_session(
        row=fixture.row,
        current_revision=fixture.outline_revisions[fixture.outline_bid],
        user_bid=fixture.user_bid,
        shifu_bid=fixture.shifu_bid,
        outline_bid=fixture.outline_bid,
        preview_mode=fixture.preview_mode,
    )


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize(
    ("baseline", "current", "turn", "finished", "expected"),
    [
        (11, 11, 0, 0, LessonContentState(started=True)),
        (11, 12, 0, 0, LessonContentState(started=True, has_content_update=True)),
        (
            11,
            13,
            9,
            1,
            LessonContentState(started=True, finished=True, has_content_update=True),
        ),
        (11, None, 0, 0, LessonContentState(started=True)),
        (11, 0, 0, 0, LessonContentState(started=True)),
        (0, 12, 0, 0, LessonContentState(started=True)),
        (None, 12, 0, 0, LessonContentState()),
        (None, 12, 3, 0, LessonContentState(started=True)),
        (None, 12, 0, 1, LessonContentState(started=True, finished=True)),
    ],
)
def test_batch_and_loaded_session_agree_on_revisions_and_legacy_progress(
    app: object,
    preview: bool,
    baseline: int | None,
    current: int | None,
    turn: int,
    finished: int,
    expected: LessonContentState,
) -> None:
    with app.app_context():
        fixture = _seed(
            baseline=baseline,
            current=current,
            preview=preview,
            turn=turn,
            finished=finished,
        )
        assert _load(fixture)[fixture.outline_bid] == expected
        assert _loaded_state(fixture) == expected


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("user_bid", "another-user"),
        ("shifu_bid", "another-course"),
        ("outline_item_bid", "another-lesson"),
        ("active_key", None),
        ("active_key", "another-key"),
        ("deleted", 1),
    ],
)
def test_identity_is_required_by_both_paths(
    app: object, attribute: str, value: object
) -> None:
    with app.app_context():
        fixture = _seed()
        with unit_of_work():
            setattr(fixture.row, attribute, value)
        assert _load(fixture) == {}
        assert _loaded_state(fixture) == LessonContentState()


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("schema_version", [0, AGENT_SESSION_SCHEMA_VERSION + 1])
@pytest.mark.parametrize("baseline", [None, 11])
@pytest.mark.parametrize(
    ("turn", "finished", "expected"),
    [
        (1, 0, LessonContentState(started=True)),
        (0, 1, LessonContentState(started=True, finished=True)),
    ],
)
def test_unknown_schema_keeps_scalar_progress_but_cannot_recommend_updates(
    app: object,
    preview: bool,
    schema_version: int,
    baseline: int | None,
    turn: int,
    finished: int,
    expected: LessonContentState,
) -> None:
    with app.app_context():
        fixture = _seed(
            baseline=baseline, preview=preview, turn=turn, finished=finished
        )
        with unit_of_work():
            fixture.row.schema_version = schema_version
        assert _load(fixture)[fixture.outline_bid] == expected
        assert _loaded_state(fixture) == expected


def test_published_and_preview_use_independent_baselines(app: object) -> None:
    with app.app_context():
        formal = _seed()
        preview = _seed(
            baseline=12,
            current=12,
            preview=True,
            user_bid=formal.user_bid,
            shifu_bid=formal.shifu_bid,
            outline_bid=formal.outline_bid,
        )
        assert _load(formal)[formal.outline_bid].has_content_update is True
        assert _load(preview)[preview.outline_bid].has_content_update is False
        formal.preview_mode = True
        assert _loaded_state(formal) == LessonContentState()
        formal.row = None
        assert _loaded_state(formal) == LessonContentState()


def test_another_requested_lessons_active_key_cannot_authorize_a_session(
    app: object,
) -> None:
    with app.app_context():
        first = _seed()
        second = _seed(user_bid=first.user_bid, shifu_bid=first.shifu_bid)
        first.outline_revisions.update(second.outline_revisions)
        with unit_of_work():
            original_key = first.row.active_key
            first.row.active_key = None
            db.session.flush()
            second.row.active_key = original_key
        assert _load(first) == {}
        assert _loaded_state(second) == LessonContentState()


def test_batch_reads_only_scalars_once_and_empty_requests_read_nothing(
    app: object,
) -> None:
    with app.app_context():
        first = _seed()
        second = _seed(
            current=11, finished=1, user_bid=first.user_bid, shifu_bid=first.shifu_bid
        )
        first.outline_revisions.update(second.outline_revisions)
        db.session.expunge_all()
        statements = []

        def capture(
            _conn: object, _cursor: object, statement: str, *_args: object
        ) -> None:
            statements.append(statement.lower())

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
            sql = statements[0]
            assert "active_key in" in sql
            assert "content_revision" in sql
            assert "session_data" not in sql
            assert "json_" not in sql
            assert "outline_items" not in sql
            first.outline_revisions = {}
            assert _load(first) == {}
            assert len(statements) == 1
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
