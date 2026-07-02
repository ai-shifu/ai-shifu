import pytest
from sqlalchemy.exc import OperationalError

from flaskr.dao import retry_on_deadlock


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
