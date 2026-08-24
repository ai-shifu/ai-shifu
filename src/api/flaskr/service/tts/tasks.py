"""Task entrypoints for TTS background jobs."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask

try:  # pragma: no cover - exercised indirectly when Celery is installed.
    from celery import shared_task
except ImportError:  # pragma: no cover - local fallback for non-Celery test envs.

    def shared_task(*args: object, **kwargs: object) -> object:
        """Register a Celery task with the configured application context."""
        _ = (args, kwargs)

        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            return func

        return decorator


def _create_task_app() -> Flask:
    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app

    return create_app()


@shared_task(name="tts.minimax_clone_voice")
def minimax_clone_voice_task(*, voice_bid: str) -> dict[str, object]:
    """Run the Minimax voice-clone background task."""
    from flaskr.service.tts.api import run_minimax_voice_clone

    app = _create_task_app()
    result = run_minimax_voice_clone(app, voice_bid=voice_bid)
    payload = result.to_payload()
    payload["task_name"] = "tts.minimax_clone_voice"
    return payload
