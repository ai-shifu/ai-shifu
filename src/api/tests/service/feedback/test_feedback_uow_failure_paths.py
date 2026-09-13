"""Unit-of-work behavior for feedback submission (B1 migration).

Pre-migration ``submit_feedback`` notified operators BEFORE committing the
feedback row, so a notification failure lost the feedback and a commit
failure produced a notification for a row that never existed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flaskr import dao
from flaskr.service.feedback import funs as feedback_funs
from flaskr.service.feedback.funs import submit_feedback
from flaskr.service.feedback.models import FeedBack


def _committed_feedback_count(app: object, feedback: str) -> int:
    # A separate connection only sees committed rows.
    with app.app_context(), dao.db.engine.connect() as connection:
        rows = connection.execute(
            FeedBack.__table__.select().where(FeedBack.feedback == feedback)
        ).fetchall()
    return len(rows)


def test_notification_fires_only_after_the_row_is_committed(
    app: object, monkeypatch: object
) -> None:
    feedback_text = "uow-feedback-after-commit"
    seen: list[int] = []

    def fake_send_notify(_app: object, _title: str, _lines: list[str]) -> None:
        seen.append(_committed_feedback_count(app, feedback_text))

    monkeypatch.setattr(feedback_funs, "send_notify", fake_send_notify)
    monkeypatch.setattr(
        feedback_funs,
        "load_user_aggregate",
        lambda _user_id: SimpleNamespace(name="Learner", mobile="13800000000"),
    )

    with app.app_context():
        feedback_id = submit_feedback(app, "uow-feedback-user", feedback_text, "")

    assert feedback_id > 0
    # Exactly one notification, and it observed the durable row.
    assert seen == [1]


def test_notification_failure_does_not_lose_the_feedback(
    app: object, monkeypatch: object
) -> None:
    feedback_text = "uow-feedback-notify-boom"

    def failing_send_notify(*_args: object, **_kwargs: object) -> None:
        message = "feishu down"
        raise RuntimeError(message)

    monkeypatch.setattr(feedback_funs, "send_notify", failing_send_notify)
    monkeypatch.setattr(feedback_funs, "load_user_aggregate", lambda _user_id: None)

    with app.app_context():
        feedback_id = submit_feedback(
            app, "uow-feedback-user-2", feedback_text, "a@example.com"
        )

    assert feedback_id > 0
    assert _committed_feedback_count(app, feedback_text) == 1


def test_failure_before_commit_persists_nothing_and_skips_notification(
    app: object, monkeypatch: object
) -> None:
    feedback_text = "uow-feedback-rolled-back"
    notified: list[str] = []
    monkeypatch.setattr(
        feedback_funs, "send_notify", lambda *_a, **_k: notified.append("sent")
    )

    def failing_flush() -> None:
        message = "boom before commit"
        raise RuntimeError(message)

    with app.app_context():
        monkeypatch.setattr(dao.db.session, "flush", failing_flush)
        with pytest.raises(RuntimeError, match="boom before commit"):
            submit_feedback(app, "uow-feedback-user-3", feedback_text, "")
        monkeypatch.undo()

    assert notified == []
    assert _committed_feedback_count(app, feedback_text) == 0
