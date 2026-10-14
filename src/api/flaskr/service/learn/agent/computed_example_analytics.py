"""Count accepted canonical artifacts without collecting teaching or learner data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.common.server_analytics import queue_server_event

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask


def make_computed_example_observer(
    app: Flask, *, preview_mode: bool, learning_mode: str
) -> Callable[[], None] | None:
    """Observe published accepted use only; no model offer or browser-view claim."""
    if preview_mode or learning_mode not in {"read", "listen", "classroom"}:
        return None

    def observed() -> None:
        """Enqueue exact non-personal dimensions independently from the stream."""
        try:
            queue_server_event(
                app,
                event_name="learner_computed_example_streamed",
                route="/backend/lesson/computed-example",
                data={"surface": "learner", "learning_mode": learning_mode},
            )
        except Exception:
            # Analytics must never change an accepted lesson response.
            return

    return observed
