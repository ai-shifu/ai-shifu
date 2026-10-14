"""Keep computed-use telemetry anonymous, preview-free and independent of delivery."""

from unittest.mock import Mock

import pytest
from flaskr.service.learn.agent import computed_example_analytics as analytics
from flaskr.service.learn.agent import lesson_entry as entry

from .test_lesson_entry_contracts import _entry_with_runner


@pytest.mark.parametrize("mode", ["read", "listen", "classroom"])
@pytest.mark.parametrize("preview", [False, True])
def test_host_counts_only_published_accepted_use_with_exact_mode(
    app: object, monkeypatch: pytest.MonkeyPatch, mode: str, preview: bool
) -> None:
    """Guests and members share the same content-free published-mode signal."""
    _entry_with_runner(monkeypatch)
    queued = Mock()
    monkeypatch.setattr(analytics, "queue_server_event", queued)
    list(
        entry.agent_lesson_events(
            app,
            user_bid="private-user",
            shifu_bid="private-course",
            outline_bid="private-lesson",
            preview_mode=preview,
            learning_mode=mode,
        )
    )
    observer = entry.Engine.call_args.kwargs["computed_example_observer"]
    queued.assert_not_called()
    if preview:
        assert observer is None
    else:
        observer()
        queued.assert_called_once_with(
            app,
            event_name="learner_computed_example_streamed",
            route="/backend/lesson/computed-example",
            data={"surface": "learner", "learning_mode": mode},
        )


def test_tracker_failure_does_not_escape_or_collect_private_fields(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No fallback logging or sensitive identity enriches a failed analytics call."""
    queued = Mock(side_effect=RuntimeError("private error"))
    monkeypatch.setattr(analytics, "queue_server_event", queued)
    observer = analytics.make_computed_example_observer(
        app, preview_mode=False, learning_mode="read"
    )
    observer()
    assert queued.call_args.kwargs["data"] == {
        "surface": "learner",
        "learning_mode": "read",
    }
    assert (
        analytics.make_computed_example_observer(
            app, preview_mode=False, learning_mode="private-mode"
        )
        is None
    )
