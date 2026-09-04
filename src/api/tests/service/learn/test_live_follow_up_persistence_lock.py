"""Verify connection-owned fencing for recoverable Live turn reservations."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from flaskr.service.learn import live_follow_up_persistence as persistence


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
