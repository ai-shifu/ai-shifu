"""Verify connection-owned fencing for recoverable Live turn reservations."""

from __future__ import annotations

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from flaskr.dao import db
from flaskr.service.learn import live_follow_up_persistence as persistence
from sqlalchemy import text


def _connection(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    connection = MagicMock()
    connection.execute.return_value.scalar.return_value = 1
    monkeypatch.setattr(
        persistence,
        "db",
        SimpleNamespace(
            engine=SimpleNamespace(connect=lambda: nullcontext(connection))
        ),
    )
    return connection


def test_lock_owns_connection_through_fresh_context_and_releases_afterward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _connection(monkeypatch)
    app = Flask("live-lock-test")
    with app.app_context():
        g.before_lock = True
        with persistence.live_follow_up_persistence_lock(app, "session-1"):
            assert not hasattr(g, "before_lock")
            assert connection.execute.call_count == 1
        assert g.before_lock is True
    acquire, release = connection.execute.call_args_list
    assert str(acquire.args[0]) == "SELECT GET_LOCK(:name, 5)"
    assert str(release.args[0]) == "SELECT RELEASE_LOCK(:name)"
    assert acquire.args[1] == release.args[1]
    name = acquire.args[1]["name"]
    assert name.startswith("ai-shifu:live:")
    assert len(name) <= 64
    assert "session-1" not in name
    connection.invalidate.assert_not_called()


@pytest.mark.parametrize("result", [0, None])
def test_lock_timeout_never_enters_persistence(
    monkeypatch: pytest.MonkeyPatch, result: int | None
) -> None:
    connection = _connection(monkeypatch)
    connection.execute.return_value.scalar.return_value = result
    with (
        pytest.raises(persistence.LiveFollowUpPersistenceError, match="busy"),
        persistence.live_follow_up_persistence_lock(Flask("live-lock-test"), "s"),
    ):
        pytest.fail("persistence started without exclusive ownership")
    assert connection.execute.call_count == 1


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_body_failure_releases_connection_owned_lock(
    monkeypatch: pytest.MonkeyPatch, error: type[BaseException]
) -> None:
    connection = _connection(monkeypatch)
    with (
        pytest.raises(error),
        persistence.live_follow_up_persistence_lock(Flask("live-lock-test"), "s"),
    ):
        raise error
    assert "RELEASE_LOCK" in str(connection.execute.call_args.args[0])


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_uncertain_acquisition_invalidates_connection(
    monkeypatch: pytest.MonkeyPatch, error: type[BaseException]
) -> None:
    connection = _connection(monkeypatch)
    connection.execute.side_effect = error
    with (
        pytest.raises(error),
        persistence.live_follow_up_persistence_lock(Flask("live-lock-test"), "s"),
    ):
        pytest.fail("persistence started after failed lock acquisition")
    connection.invalidate.assert_called_once()


def test_failed_release_invalidates_without_masking_a_durable_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _connection(monkeypatch)
    acquired = MagicMock()
    acquired.scalar.return_value = 1
    connection.execute.side_effect = [acquired, RuntimeError]
    with persistence.live_follow_up_persistence_lock(Flask("live-lock-test"), "s"):
        pass
    connection.invalidate.assert_called_once()


def test_mysql_worker_disconnect_releases_persistence_ownership(app: Flask) -> None:
    """Run with TEST_SQLALCHEMY_DATABASE_URI against an isolated MySQL database."""
    session_bid = str(uuid.uuid4())
    lock_name = "ai-shifu:live:" + hashlib.sha256(session_bid.encode()).hexdigest()[:48]
    entered = Event()
    started = Event()

    def successor() -> None:
        with app.app_context():
            started.set()
            with persistence.live_follow_up_persistence_lock(app, session_bid):
                entered.set()

    with app.app_context():
        if db.engine.dialect.name != "mysql":
            pytest.skip("requires an isolated MySQL database")
        with (
            db.engine.connect() as abandoned,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            assert (
                abandoned.execute(
                    text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name}
                ).scalar()
                == 1
            )
            waiting = pool.submit(successor)
            try:
                assert started.wait(2)
                assert not entered.wait(0.1)
            finally:
                # Close the physical socket, as a terminated worker would.
                abandoned.invalidate()
            waiting.result(timeout=6)
            assert entered.is_set()
        with db.engine.connect() as probe:
            assert (
                probe.execute(
                    text("SELECT IS_FREE_LOCK(:name)"), {"name": lock_name}
                ).scalar()
                == 1
            )
