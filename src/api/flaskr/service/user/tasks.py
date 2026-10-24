"""Background task entrypoints for account lifecycle work."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask

try:  # pragma: no cover - exercised indirectly when Celery is installed
    from celery import shared_task
except ImportError:  # pragma: no cover - local fallback for test environments

    def shared_task(
        *args: object, **kwargs: object
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        """Return a no-Celery decorator used by focused unit tests."""
        _ = (args, kwargs)

        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            return func

        return decorator


def _create_task_app() -> Flask:
    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app

    return create_app(serving_http=False)


class _RetryRequest(Protocol):
    retries: int


class _RetryingTask(Protocol):
    request: _RetryRequest
    max_retries: int

    def retry(self, *, countdown: int) -> BaseException: ...


@shared_task(
    bind=True,
    name="user.execute_account_cancellation",
    max_retries=2,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_account_cancellation_task(
    task: _RetryingTask, cancellation_bid: str
) -> dict[str, Any]:
    """Execute one durable account-cancellation request."""
    return _execute_account_cancellation(
        task,
        cancellation_bid=str(cancellation_bid or "").strip(),
        app=_create_task_app(),
    )


def _execute_account_cancellation(
    task: _RetryingTask, *, cancellation_bid: str, app: Flask
) -> dict[str, Any]:
    """Run the task against an injected app for focused retry tests."""
    from flaskr.service.user.account_cancellation import (
        execute_pending_account_cancellation,
        mark_account_cancellation_failed,
        mark_account_cancellation_retrying,
    )

    try:
        return execute_pending_account_cancellation(
            app,
            cancellation_bid=cancellation_bid,
            record_terminal_failure=False,
        )
    except Exception:
        if int(task.request.retries or 0) >= int(task.max_retries or 0):
            mark_account_cancellation_failed(
                app,
                cancellation_bid=cancellation_bid,
                failure_code="execution_failed",
            )
            raise
        mark_account_cancellation_retrying(
            app,
            cancellation_bid=cancellation_bid,
        )
        raise task.retry(countdown=2 ** int(task.request.retries or 0)) from None
