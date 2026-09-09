"""Verify retry state transitions for background account cancellation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flaskr.service.user import account_cancellation
from flaskr.service.user.tasks import _execute_account_cancellation


class _RetryScheduledError(Exception):
    pass


class _Task:
    def __init__(self, retries: int, max_retries: int = 2) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.max_retries = max_retries
        self.countdowns: list[int] = []

    def retry(self, *, countdown: int) -> BaseException:
        self.countdowns.append(countdown)
        return _RetryScheduledError()


def test_task_exposes_retrying_without_transient_failed_state(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    transitions: list[tuple[str, str]] = []
    monkeypatch.setattr(
        account_cancellation,
        "execute_pending_account_cancellation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        account_cancellation,
        "mark_account_cancellation_retrying",
        lambda _app, *, cancellation_bid: transitions.append(
            ("retrying", cancellation_bid)
        ),
    )
    monkeypatch.setattr(
        account_cancellation,
        "mark_account_cancellation_failed",
        lambda _app, *, cancellation_bid, failure_code: transitions.append(
            (failure_code, cancellation_bid)
        ),
    )
    task = _Task(retries=1)

    with pytest.raises(_RetryScheduledError):
        _execute_account_cancellation(task, cancellation_bid="cancel-bid", app=app)

    assert transitions == [("retrying", "cancel-bid")]
    assert task.countdowns == [2]


def test_task_marks_failed_only_after_last_attempt(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    transitions: list[tuple[str, str]] = []
    monkeypatch.setattr(
        account_cancellation,
        "execute_pending_account_cancellation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        account_cancellation,
        "mark_account_cancellation_retrying",
        lambda _app, *, cancellation_bid: transitions.append(
            ("retrying", cancellation_bid)
        ),
    )
    monkeypatch.setattr(
        account_cancellation,
        "mark_account_cancellation_failed",
        lambda _app, *, cancellation_bid, failure_code: transitions.append(
            (failure_code, cancellation_bid)
        ),
    )

    with pytest.raises(RuntimeError, match="boom"):
        _execute_account_cancellation(
            _Task(retries=2), cancellation_bid="cancel-bid", app=app
        )

    assert transitions == [("execution_failed", "cancel-bid")]
