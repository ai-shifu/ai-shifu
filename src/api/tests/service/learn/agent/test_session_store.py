"""Storing an agent lesson session: what round-trips, and what is refused rather than guessed at."""

from __future__ import annotations

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import session_store
from flaskr.service.learn.agent.models import (
    AGENT_SESSION_SCHEMA_VERSION,
    LearnAgentSession,
    active_key_for,
)
from markdownflow.engine import ScriptBundle, Session
from pydantic_ai.messages import ModelRequest, UserPromptPart

USER = "learner-1"
SHIFU = "course-a"
OUTLINE = "outline-1"


@pytest.fixture(autouse=True)
def _clean(app: object):  # noqa: ANN202 - pytest fixture
    with app.app_context():
        LearnAgentSession.query.delete()
        db.session.commit()
        yield
        LearnAgentSession.query.delete()
        db.session.commit()


def a_session(**kw: object) -> Session:
    """Build a session with enough on it that a broken round trip would show."""
    session = Session(
        script=ScriptBundle(script="Teach lesson one."),
        user_id=USER,
        **kw,
    )
    session.memory["feeling"] = "good"
    session.turn = 3
    return session


def store(
    app: object,
    session: Session,
    *,
    content_revision: int | None = None,
    preview_mode: bool = False,
) -> None:
    session_store.save_agent_session(
        app,
        session,
        user_bid=USER,
        shifu_bid=SHIFU,
        outline_item_bid=OUTLINE,
        content_revision=content_revision,
        preview_mode=preview_mode,
    )


def test_a_session_survives_a_round_trip(app: object) -> None:
    with app.app_context():
        original = a_session(
            teaching_summaries={"policy:source": "Historical overview"}
        )
        store(app, original)
        loaded = session_store.load_agent_session(app, USER, OUTLINE)

    assert loaded is not None
    assert loaded.teaching_summaries == original.teaching_summaries
    assert loaded.id == original.id
    assert loaded.memory["feeling"] == "good"
    assert loaded.turn == 3
    assert loaded.script.script == "Teach lesson one."


def test_a_learner_who_has_not_started_has_no_session(app: object) -> None:
    with app.app_context():
        assert session_store.load_agent_session(app, USER, OUTLINE) is None


def test_saving_again_replaces_rather_than_appends(app: object) -> None:
    """One row per learner per lesson: history here would only be dead weight."""
    with app.app_context():
        session = a_session()
        store(app, session)
        session.turn = 4
        store(app, session)

        assert LearnAgentSession.query.filter_by(deleted=0).count() == 1
        assert session_store.load_agent_session(app, USER, OUTLINE).turn == 4


def test_the_lesson_and_the_learner_both_select_the_row(app: object) -> None:
    with app.app_context():
        store(app, a_session())
        assert session_store.load_agent_session(app, "someone-else", OUTLINE) is None
        assert session_store.load_agent_session(app, USER, "another-outline") is None


# -- refusing what this build cannot read -------------------------------------------------


def test_a_session_from_another_engine_schema_is_refused(app: object) -> None:
    """The engine is edited in this repository, so a stored history can outlive the code.

    A renamed tool or a changed argument leaves a history the current build cannot resume, and
    resuming it hopefully would fail somewhere further in, with the learner watching.
    """
    with app.app_context():
        store(app, a_session())
        row = LearnAgentSession.query.filter_by(deleted=0).first()
        row.schema_version = AGENT_SESSION_SCHEMA_VERSION + 1
        db.session.commit()

        with pytest.raises(session_store.StoredSessionUnusable, match="schema version"):
            session_store.load_agent_session(app, USER, OUTLINE)


def test_a_history_from_another_pydantic_ai_is_refused(app: object) -> None:
    """The stored messages are pydantic-ai's own serialization, tied to its version."""
    with app.app_context():
        store(app, a_session())
        row = LearnAgentSession.query.filter_by(deleted=0).first()
        row.pydantic_ai_version = "0.0.1-from-the-past"
        db.session.commit()

        with pytest.raises(session_store.StoredSessionUnusable, match="pydantic-ai"):
            session_store.load_agent_session(app, USER, OUTLINE)


def test_an_unreadable_document_is_refused_rather_than_raising_from_the_engine(
    app: object,
) -> None:
    with app.app_context():
        store(app, a_session())
        row = LearnAgentSession.query.filter_by(deleted=0).first()
        row.session_data = "{not json"
        db.session.commit()

        with pytest.raises(session_store.StoredSessionUnusable):
            session_store.load_agent_session(app, USER, OUTLINE)


def test_what_is_written_records_the_versions_it_was_written_with(app: object) -> None:
    """Without these two columns nothing above can tell a stale row from a current one."""
    with app.app_context():
        store(app, a_session())
        row = LearnAgentSession.query.filter_by(deleted=0).first()

        assert row.schema_version == AGENT_SESSION_SCHEMA_VERSION
        assert row.pydantic_ai_version
        assert row.finished == 0
        assert row.shifu_bid == SHIFU


# -- review follow-up --------------------------------------------------------------------


def test_saving_inside_a_caller_transaction_is_refused(app: object) -> None:
    """The durability promise is what callers hold a terminal event on, so it cannot be weakened.

    A nested `unit_of_work()` joins the caller's transaction and commits nothing, so returning from
    here would report a save the caller's later failure could still roll back.
    """
    from flaskr.dao.uow import unit_of_work

    with (
        app.app_context(),
        unit_of_work(),
        pytest.raises(RuntimeError, match="unit_of_work"),
    ):
        store(app, a_session())


def test_only_one_live_row_can_hold_a_lesson(app: object) -> None:
    """Two tabs starting the same lesson must not each get a session.

    The application's read-then-insert cannot decide this on its own: both can read an empty range
    and both insert. The unique index is what settles it.
    """
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        store(app, a_session())
        row = LearnAgentSession.query.filter_by(deleted=0).one()

        db.session.add(
            LearnAgentSession(
                agent_session_bid="second",
                user_bid=USER,
                shifu_bid=SHIFU,
                outline_item_bid=OUTLINE,
                active_key=row.active_key,
                session_data="{}",
                schema_version=AGENT_SESSION_SCHEMA_VERSION,
                pydantic_ai_version="x",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_a_failure_part_way_through_a_save_leaves_nothing_behind(app: object) -> None:
    """The repository requires a mid-flow failure test for anything owning a unit of work."""
    with app.app_context():
        original = a_session()
        store(app, original)
        before = session_store.load_agent_session(app, USER, OUTLINE)
        assert before.turn == 3

        original.turn = 99

        def explode(*_a: object, **_k: object) -> None:
            msg = "writing the progress record failed"
            raise RuntimeError(msg)

        real_apply = session_store._apply
        session_store._apply = explode
        try:
            with pytest.raises(RuntimeError, match="progress record"):
                store(app, original)
        finally:
            session_store._apply = real_apply

        after = session_store.load_agent_session(app, USER, OUTLINE)
        assert after.turn == 3  # the failed save left the stored turn alone


def test_each_save_refreshes_the_timestamp_inside_the_document(app: object) -> None:
    """Otherwise the stored document claims the age of the session's first turn forever."""
    with app.app_context():
        session = a_session()
        store(app, session)
        first = session_store.load_agent_session(app, USER, OUTLINE).updated_at

        session.turn = 4
        store(app, session)
        second = session_store.load_agent_session(app, USER, OUTLINE).updated_at

    assert second > first


def test_previewing_a_lesson_does_not_touch_the_learner_who_is_taking_it(
    app: object,
) -> None:
    """The same person and lesson in two scopes: an author's draft run and a learner's real one."""
    with app.app_context():
        taking = a_session()
        taking.memory["scope"] = "published"
        store(app, taking)

        previewing = a_session()
        previewing.memory["scope"] = "preview"
        session_store.save_agent_session(
            app,
            previewing,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_item_bid=OUTLINE,
            preview_mode=True,
        )

        loaded_taking = session_store.load_agent_session(app, USER, OUTLINE)
        loaded_preview = session_store.load_agent_session(
            app, USER, OUTLINE, preview_mode=True
        )

    assert loaded_taking is not None
    assert loaded_preview is not None
    assert loaded_taking.id == taking.id
    assert loaded_preview.id == previewing.id
    assert loaded_taking.memory["scope"] == "published"
    assert loaded_preview.memory["scope"] == "preview"


def test_resetting_a_lesson_retires_its_session(app: object) -> None:
    """A reset that left the session behind would resume the conversation it just cleared.

    Worse, a session holding `finished=True` reports the lesson complete on the next request and
    never starts it again -- which also breaks taking a course back off the allowlist as a way out.
    """
    from flaskr.service.learn.learn_funcs import reset_learn_record

    with app.app_context():
        finished = a_session()
        finished.finished = True
        store(app, finished)

        reset_learn_record(app, SHIFU, OUTLINE, USER)

        assert session_store.load_agent_session(app, USER, OUTLINE) is None


def test_resetting_published_learning_preserves_the_preview_session(
    app: object,
) -> None:
    """Published retakes do not discard a teacher's independent preview."""
    from flaskr.service.learn.learn_funcs import reset_learn_record

    with app.app_context():
        session_store.save_agent_session(
            app,
            a_session(),
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_item_bid=OUTLINE,
            preview_mode=True,
        )

        reset_learn_record(app, SHIFU, OUTLINE, USER)

        assert (
            session_store.load_agent_session(app, USER, OUTLINE, preview_mode=True)
            is not None
        )


def _teaching_session() -> Session:
    return a_session(messages=[ModelRequest(parts=[UserPromptPart(content="Start")])])


def _revision_row(preview: bool) -> LearnAgentSession:
    return LearnAgentSession.query.filter_by(
        active_key=active_key_for(USER, OUTLINE, preview_mode=preview)
    ).one()


@pytest.mark.parametrize("preview", [False, True])
def test_first_teaching_captures_the_revision_and_continuation_keeps_it(
    app: object, preview: bool
) -> None:
    with app.app_context():
        session = _teaching_session()
        store(app, session, content_revision=11, preview_mode=preview)
        assert _revision_row(preview).content_revision == 11
        session.messages.append(
            ModelRequest(parts=[UserPromptPart(content="Follow up")])
        )
        session.turn += 1
        session.finished = True
        store(app, session, content_revision=12, preview_mode=preview)
        assert _revision_row(preview).content_revision == 11


@pytest.mark.parametrize("preview", [False, True])
def test_empty_first_save_waits_for_actual_messages_before_capturing_revision(
    app: object, preview: bool
) -> None:
    with app.app_context():
        session = a_session()
        session.turn = 0
        store(app, session, content_revision=11, preview_mode=preview)
        assert _revision_row(preview).content_revision is None
        session.messages.append(ModelRequest(parts=[UserPromptPart(content="Start")]))
        store(app, session, content_revision=12, preview_mode=preview)
        assert _revision_row(preview).content_revision == 12


@pytest.mark.parametrize("preview", [False, True])
def test_an_old_started_session_without_a_revision_is_never_backfilled(
    app: object, preview: bool
) -> None:
    with app.app_context():
        session = _teaching_session()
        store(app, session, content_revision=11, preview_mode=preview)
        with unit_of_work():
            _revision_row(preview).content_revision = None
        session.messages.append(
            ModelRequest(parts=[UserPromptPart(content="Continue")])
        )
        store(app, session, content_revision=12, preview_mode=preview)
        assert _revision_row(preview).content_revision is None


@pytest.mark.parametrize("preview", [False, True])
def test_unknown_source_revision_marks_started_and_stays_unknown(
    app: object, preview: bool
) -> None:
    with app.app_context():
        session = _teaching_session()
        store(app, session, content_revision=None, preview_mode=preview)
        assert _revision_row(preview).content_revision == 0
        store(app, session, content_revision=12, preview_mode=preview)
        assert _revision_row(preview).content_revision == 0


@pytest.mark.parametrize("preview", [False, True])
def test_retaking_records_a_new_baseline_without_changing_the_other_scope(
    app: object, preview: bool
) -> None:
    with app.app_context():
        store(app, _teaching_session(), content_revision=11, preview_mode=preview)
        store(app, _teaching_session(), content_revision=21, preview_mode=not preview)
        old_id = _revision_row(preview).id
        with unit_of_work():
            session_store.stage_agent_session_discard(
                user_bid=USER,
                outline_item_bid=OUTLINE,
                preview_mode=preview,
                shifu_bid=SHIFU,
            )
        store(app, _teaching_session(), content_revision=12, preview_mode=preview)
        assert _revision_row(preview).content_revision == 12
        assert _revision_row(preview).id != old_id
        assert db.session.get(LearnAgentSession, old_id).content_revision == 11
        assert _revision_row(not preview).content_revision == 21


def test_preview_reservation_captures_no_baseline_until_teaching_is_saved(
    app: object,
) -> None:
    from flaskr.service.learn.agent.preview_history import begin_preview_run

    with app.app_context():
        generation = begin_preview_run(
            app, user_bid=USER, shifu_bid=SHIFU, outline_bid=OUTLINE, run_bid="run-1"
        )
        assert _revision_row(preview=True).content_revision is None
        session_store.save_agent_session(
            app,
            _teaching_session(),
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_item_bid=OUTLINE,
            preview_mode=True,
            preview_generation=generation,
            content_revision=12,
        )
        assert _revision_row(preview=True).content_revision == 12


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize(
    "unusable", ["schema", "pydantic", "broken-json", "scalar-json"]
)
def test_restarting_an_unusable_session_establishes_the_new_teaching_baseline(
    app: object, preview: bool, unusable: str
) -> None:
    with app.app_context():
        original = _teaching_session()
        store(app, original, content_revision=11, preview_mode=preview)
        with unit_of_work():
            row = _revision_row(preview)
            if unusable == "schema":
                row.schema_version += 1
            elif unusable == "pydantic":
                row.pydantic_ai_version = "incompatible-version"
            else:
                row.session_data = "broken" if unusable == "broken-json" else "null"
        with pytest.raises(session_store.StoredSessionUnusable):
            session_store.load_agent_session(app, USER, OUTLINE, preview_mode=preview)
        restarted = _teaching_session()
        assert restarted.id != original.id
        store(app, restarted, content_revision=12, preview_mode=preview)
        assert _revision_row(preview).content_revision == 12
        assert (
            session_store.load_agent_session(
                app, USER, OUTLINE, preview_mode=preview
            ).id
            == restarted.id
        )


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("revision", [12, None])
def test_a_different_engine_generation_owns_its_own_revision(
    app: object, preview: bool, revision: int | None
) -> None:
    with app.app_context():
        first, second = _teaching_session(), _teaching_session()
        assert first.id != second.id
        store(app, first, content_revision=11, preview_mode=preview)
        store(app, second, content_revision=revision, preview_mode=preview)
        assert _revision_row(preview).content_revision == (revision or 0)
        store(app, second, content_revision=99, preview_mode=preview)
        assert _revision_row(preview).content_revision == (revision or 0)


@pytest.mark.parametrize("preview", [False, True])
def test_empty_restarted_generation_clears_the_previous_attempt_baseline(
    app: object, preview: bool
) -> None:
    with app.app_context():
        store(app, _teaching_session(), content_revision=11, preview_mode=preview)
        restarted = a_session()
        store(app, restarted, content_revision=12, preview_mode=preview)
        assert _revision_row(preview).content_revision is None
        restarted.messages.append(ModelRequest(parts=[UserPromptPart(content="Start")]))
        store(app, restarted, content_revision=13, preview_mode=preview)
        assert _revision_row(preview).content_revision == 13
