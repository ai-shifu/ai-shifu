from unittest.mock import MagicMock

import pytest
from flaskr import dao
from flaskr.dao import retry_on_deadlock
from sqlalchemy.exc import OperationalError


class _FakeOrig(Exception):
    def __init__(self, errno, message):
        super().__init__(errno, message)
        self.args = (errno, message)


def _operational_error(errno):
    return OperationalError("SELECT 1", {}, _FakeOrig(errno, "boom"))


def test_retries_deadlock_then_succeeds():
    calls = {"n": 0}

    @retry_on_deadlock(max_attempts=3, backoff_seconds=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _operational_error(1213)
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retries_lock_wait_timeout():
    calls = {"n": 0}

    @retry_on_deadlock(max_attempts=2, backoff_seconds=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _operational_error(1205)
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 2


def test_reraises_after_exhausting_attempts():
    calls = {"n": 0}

    @retry_on_deadlock(max_attempts=3, backoff_seconds=0)
    def always_deadlock():
        calls["n"] += 1
        raise _operational_error(1213)

    with pytest.raises(OperationalError):
        always_deadlock()
    assert calls["n"] == 3


def test_does_not_retry_non_retryable_operational_error():
    calls = {"n": 0}

    @retry_on_deadlock(max_attempts=3, backoff_seconds=0)
    def other_error():
        calls["n"] += 1
        raise _operational_error(1146)  # table doesn't exist

    with pytest.raises(OperationalError):
        other_error()
    assert calls["n"] == 1


def test_rolls_back_session_on_every_caught_error(monkeypatch):
    """Session must be rolled back on each catch, including retries and the
    final failed attempt, so the broken session is not reused later.
    """
    fake_db = MagicMock()
    monkeypatch.setattr(dao, "db", fake_db)

    @retry_on_deadlock(max_attempts=3, backoff_seconds=0)
    def always_deadlock():
        raise _operational_error(1213)

    with pytest.raises(OperationalError):
        always_deadlock()
    # 3 attempts -> 3 rollbacks (two retries + the final re-raise).
    assert fake_db.session.rollback.call_count == 3


def test_rolls_back_session_on_non_retryable_error(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(dao, "db", fake_db)

    @retry_on_deadlock(max_attempts=3, backoff_seconds=0)
    def other_error():
        raise _operational_error(1146)

    with pytest.raises(OperationalError):
        other_error()
    assert fake_db.session.rollback.call_count == 1


def test_protocol_interrupt_invalidates_and_does_not_retry(monkeypatch):
    from flaskr import dao

    invalidations = []
    monkeypatch.setattr(
        dao,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
    )
    calls = {"n": 0}

    @retry_on_deadlock(max_attempts=3, backoff_seconds=0)
    def desynced():
        calls["n"] += 1
        raise _operational_error(2014)

    with pytest.raises(OperationalError):
        desynced()

    assert calls["n"] == 1  # no retry on a desynced stream
    assert invalidations == ["retry_on_deadlock protocol interrupt"]


def test_rollback_db_failure_escalates_and_stops_retrying(monkeypatch):
    from flaskr import dao

    invalidations = []
    monkeypatch.setattr(
        dao,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
    )

    class _BrokenSession:
        def rollback(self):
            raise OperationalError("ROLLBACK", {}, Exception())

    class _FakeDb:
        session = _BrokenSession()

    monkeypatch.setattr(dao, "db", _FakeDb)
    calls = {"n": 0}

    @retry_on_deadlock(max_attempts=3, backoff_seconds=0)
    def deadlocked():
        calls["n"] += 1
        raise _operational_error(1213)

    with pytest.raises(OperationalError):
        deadlocked()

    assert calls["n"] == 1  # rollback failure aborts the retry loop
    assert invalidations == ["retry_on_deadlock rollback failure"]
