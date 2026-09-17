"""Storing an agent lesson session: what round-trips, and what is refused rather than guessed at."""

from __future__ import annotations

import pytest
from flaskr.dao import db
from flaskr.service.learn.agent import session_store
from flaskr.service.learn.agent.engine import ScriptBundle, Session
from flaskr.service.learn.agent.models import (
    AGENT_SESSION_SCHEMA_VERSION,
    LearnAgentSession,
)

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


def store(app: object, session: Session) -> None:
    session_store.save_agent_session(
        app,
        session,
        user_bid=USER,
        shifu_bid=SHIFU,
        outline_item_bid=OUTLINE,
    )


def test_a_session_survives_a_round_trip(app: object) -> None:
    with app.app_context():
        original = a_session()
        store(app, original)
        loaded = session_store.load_agent_session(app, USER, OUTLINE)

    assert loaded is not None
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


def test_a_refused_session_can_be_discarded_so_the_lesson_starts_over(
    app: object,
) -> None:
    """What the host does after a refusal, and what a teacher switching engines needs too."""
    with app.app_context():
        store(app, a_session())
        session_store.discard_agent_session(app, USER, OUTLINE)

        assert session_store.load_agent_session(app, USER, OUTLINE) is None
        # The row is soft-deleted, so a support question later still has something to look at.
        assert LearnAgentSession.query.count() == 1
        assert LearnAgentSession.query.first().deleted == 1


def test_a_new_session_starts_cleanly_after_a_discard(app: object) -> None:
    with app.app_context():
        store(app, a_session())
        session_store.discard_agent_session(app, USER, OUTLINE)

        fresh = a_session()
        fresh.turn = 1
        store(app, fresh)

        loaded = session_store.load_agent_session(app, USER, OUTLINE)
        assert loaded is not None
        assert loaded.turn == 1
        assert LearnAgentSession.query.filter_by(deleted=0).count() == 1


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


def test_discarding_inside_a_caller_transaction_is_refused(app: object) -> None:
    from flaskr.dao.uow import unit_of_work

    with (
        app.app_context(),
        unit_of_work(),
        pytest.raises(RuntimeError, match="unit_of_work"),
    ):
        session_store.discard_agent_session(app, USER, OUTLINE)


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


def test_discarding_frees_the_key_for_the_next_start(app: object) -> None:
    """Several discarded rows can pile up: NULL keys do not collide with each other."""
    with app.app_context():
        for _ in range(3):
            store(app, a_session())
            session_store.discard_agent_session(app, USER, OUTLINE)

        assert LearnAgentSession.query.count() == 3
        assert LearnAgentSession.query.filter_by(deleted=0).count() == 0
        assert (
            LearnAgentSession.query.filter(
                LearnAgentSession.active_key.isnot(None)
            ).count()
            == 0
        )

        store(app, a_session())
        assert session_store.load_agent_session(app, USER, OUTLINE) is not None


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


def test_a_failure_part_way_through_a_discard_leaves_the_session_live(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rows are marked, then the commit fails: the learner must still have their session."""
    with app.app_context():
        store(app, a_session())

        def explode() -> None:
            msg = "the commit failed"
            raise RuntimeError(msg)

        monkeypatch.setattr(db.session, "commit", explode)
        with pytest.raises(RuntimeError, match="the commit failed"):
            session_store.discard_agent_session(app, USER, OUTLINE)
        monkeypatch.undo()

        assert session_store.load_agent_session(app, USER, OUTLINE) is not None


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
