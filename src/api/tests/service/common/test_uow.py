"""Tests for the unit-of-work transaction boundary (flaskr/dao/uow.py)."""

import threading
from contextlib import nullcontext

import pytest
from flaskr import dao
from flaskr.dao import uow
from flaskr.service.shifu.models import PublishedShifu


def _make_shifu(bid: str) -> PublishedShifu:
    return PublishedShifu(
        shifu_bid=bid,
        title="UOW Test",
        description="",
        keywords="",
    )


def _count(bid: str) -> int:
    return PublishedShifu.query.filter_by(shifu_bid=bid).count()


def test_outermost_commits_on_clean_exit(app: object) -> None:
    with app.app_context():
        with uow.unit_of_work():
            dao.db.session.add(_make_shifu("uow-commit-1"))
        dao.db.session.expire_all()
        assert _count("uow-commit-1") == 1


def test_outermost_rolls_back_on_exception(app: object) -> None:
    with app.app_context():

        def write_then_fail() -> None:
            with uow.unit_of_work():
                dao.db.session.add(_make_shifu("uow-rollback-1"))
                dao.db.session.flush()
                message = "boom"
                raise RuntimeError(message)

        with pytest.raises(RuntimeError):
            write_then_fail()
        assert _count("uow-rollback-1") == 0


def test_nested_block_joins_outer_transaction(app: object) -> None:
    with app.app_context():

        def helper() -> None:
            with uow.unit_of_work():
                dao.db.session.add(_make_shifu("uow-nested-inner-1"))

        def outer_fails_after_helper() -> None:
            with uow.unit_of_work():
                helper()
                dao.db.session.add(_make_shifu("uow-nested-outer-1"))
                message = "outer fails after helper 'completed'"
                raise RuntimeError(message)

        with pytest.raises(RuntimeError):
            outer_fails_after_helper()

        # The helper's write must be gone too: nested blocks do not commit.
        assert _count("uow-nested-inner-1") == 0
        assert _count("uow-nested-outer-1") == 0


def test_nested_clean_exit_commits_once_at_outermost(app: object) -> None:
    with app.app_context():
        with uow.unit_of_work():
            with uow.unit_of_work():
                dao.db.session.add(_make_shifu("uow-nested-clean-1"))
            # Not yet committed: still inside the outer unit of work.
            assert uow.in_unit_of_work()
        dao.db.session.expire_all()
        assert _count("uow-nested-clean-1") == 1


def test_in_unit_of_work_flag(app: object) -> None:
    with app.app_context():
        assert not uow.in_unit_of_work()
        with uow.unit_of_work():
            assert uow.in_unit_of_work()
        assert not uow.in_unit_of_work()


def test_depth_is_isolated_per_thread(app: object) -> None:
    """The /run producer runs in its own thread; depth must not leak across."""
    seen = {}

    def worker() -> None:
        seen["inside_thread"] = uow.in_unit_of_work()

    with app.app_context(), uow.unit_of_work():
        t = threading.Thread(target=worker)
        t.start()
        t.join()
    assert seen["inside_thread"] is False


def test_depth_resets_after_exception(app: object) -> None:
    with app.app_context():
        message = "boom"
        with pytest.raises(RuntimeError), uow.unit_of_work():
            raise RuntimeError(message)
        assert not uow.in_unit_of_work()


def test_on_commit_outside_uow_runs_immediately(app: object) -> None:
    calls = []
    with app.app_context():
        uow.on_commit(lambda: calls.append("now"))
    assert calls == ["now"]


def test_on_commit_nested_defers_to_outermost_commit(app: object) -> None:
    calls = []
    with app.app_context():
        with uow.unit_of_work():
            with uow.unit_of_work():
                uow.on_commit(lambda: calls.append("notified"))
            # Inner block exited: callback must NOT have fired yet.
            assert calls == []
        assert calls == ["notified"]


def test_on_commit_dropped_on_rollback(app: object) -> None:
    calls = []
    with app.app_context():

        def schedule_then_fail() -> None:
            with uow.unit_of_work():
                uow.on_commit(lambda: calls.append("never"))
                message = "boom"
                raise RuntimeError(message)

        with pytest.raises(RuntimeError):
            schedule_then_fail()
        assert calls == []


def test_on_commit_callback_exception_does_not_propagate(app: object) -> None:
    calls = []

    def boom() -> None:
        message = "callback boom"
        raise RuntimeError(message)

    with app.app_context(), uow.unit_of_work():
        uow.on_commit(boom)
        uow.on_commit(lambda: calls.append("still-runs"))
    # Both scheduled callbacks ran; the failing one was logged, not raised.
    assert calls == ["still-runs"]


def test_on_commit_callback_can_own_a_new_unit_of_work(app: object) -> None:
    """A post-commit callback runs after the depth counter is reset.

    Regression: callbacks used to run while the committing block still
    counted as depth 1, so a callback opening its own ``unit_of_work()`` was
    treated as nested and its writes were never committed. Production hits
    this through ``on_commit(finish_transfer)`` -> post-auth extensions ->
    trial credit bootstrap.
    """

    def callback() -> None:
        assert not uow.in_unit_of_work()
        with uow.unit_of_work():
            dao.db.session.add(_make_shifu("uow-callback-inner-1"))

    with app.app_context():
        with uow.unit_of_work():
            dao.db.session.add(_make_shifu("uow-callback-outer-1"))
            uow.on_commit(callback)
        dao.db.session.expire_all()
        assert _count("uow-callback-outer-1") == 1
        assert _count("uow-callback-inner-1") == 1
        assert not uow.in_unit_of_work()


def test_on_commit_inside_callback_runs_immediately(app: object) -> None:
    calls = []

    def callback() -> None:
        # No unit of work is active any more: the nested on_commit fires now.
        uow.on_commit(lambda: calls.append("inner"))
        calls.append("outer")

    with app.app_context(), uow.unit_of_work():
        uow.on_commit(callback)
    assert calls == ["inner", "outer"]


def test_discard_rolls_back_on_clean_exit(app: object) -> None:
    calls = []
    with app.app_context():
        with uow.unit_of_work(discard=True):
            dao.db.session.add(_make_shifu("uow-discard-1"))
            dao.db.session.flush()
            uow.on_commit(lambda: calls.append("never"))
        assert _count("uow-discard-1") == 0
        assert calls == []
        assert not uow.in_unit_of_work()


def test_nested_discard_propagates_to_outermost(app: object) -> None:
    """A dry run inside a larger unit of work must not commit the caller."""
    with app.app_context():
        with uow.unit_of_work():
            dao.db.session.add(_make_shifu("uow-discard-outer-1"))
            with uow.unit_of_work(discard=True):
                dao.db.session.add(_make_shifu("uow-discard-inner-1"))
        assert _count("uow-discard-outer-1") == 0
        assert _count("uow-discard-inner-1") == 0
        # The flag does not leak into the next unit of work.
        with uow.unit_of_work():
            dao.db.session.add(_make_shifu("uow-discard-after-1"))
        dao.db.session.expire_all()
        assert _count("uow-discard-after-1") == 1


def test_autonomous_unit_of_work_persists_when_caller_rolls_back(
    app: object,
) -> None:
    """Audit/metering rows survive a rollback of the surrounding unit of work."""

    def caller_fails_after_autonomous_write() -> None:
        with uow.unit_of_work():
            dao.db.session.add(_make_shifu("uow-autonomous-outer-1"))
            with uow.autonomous_unit_of_work(app):
                # Runs on its own session at depth 0 even though the caller
                # is already inside a unit of work.
                assert uow.in_unit_of_work()
                dao.db.session.add(_make_shifu("uow-autonomous-inner-1"))
            assert uow.in_unit_of_work()
            dao.db.session.flush()
            message = "boom"
            raise RuntimeError(message)

    with app.app_context():
        with pytest.raises(RuntimeError):
            caller_fails_after_autonomous_write()
        dao.db.session.expire_all()
        assert _count("uow-autonomous-outer-1") == 0
        assert _count("uow-autonomous-inner-1") == 1


def test_autonomous_unit_of_work_runs_own_post_commit_callbacks(
    app: object,
) -> None:
    calls = []
    with app.app_context(), uow.unit_of_work():
        uow.on_commit(lambda: calls.append("outer"))
        with uow.autonomous_unit_of_work(app):
            uow.on_commit(lambda: calls.append("autonomous"))
        # The autonomous block committed and fired its own callback while the
        # caller's callback is still deferred.
        assert calls == ["autonomous"]
    assert calls == ["autonomous", "outer"]


def test_app_context_scope_pushes_when_the_active_context_is_another_app(
    app: object,
) -> None:
    """A context of a different Flask app must not be reused.

    The session would be bound to that app's database (celery FlaskTask /
    multi-app fixtures).
    """
    from flask import Flask, current_app

    other = Flask("uow-other-app")
    with other.app_context():
        assert current_app._get_current_object() is other
        with uow.app_context_scope(app):
            assert current_app._get_current_object() is app
        assert current_app._get_current_object() is other
    with app.app_context(), uow.app_context_scope(app):
        # Same app: the caller's context (and session) is reused.
        assert current_app._get_current_object() is app


def test_app_context_scope_treats_current_app_proxy_as_the_same_app(
    app: object,
) -> None:
    """CLI commands pass ``current_app`` (a proxy); it must reuse the context."""
    from flask import current_app

    with app.app_context():
        scope = uow.app_context_scope(current_app)
        assert isinstance(scope, nullcontext)
