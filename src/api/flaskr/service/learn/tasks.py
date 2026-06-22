"""Task entrypoints for learn background jobs."""

from __future__ import annotations

from typing import Any, Callable

try:  # pragma: no cover - exercised indirectly when Celery is installed
    from celery import shared_task
except ImportError:  # pragma: no cover - local fallback for non-Celery test envs

    def shared_task(*args, **kwargs):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator


from flaskr.service.learn.pdf_export import cleanup_expired_pdf_exports


@shared_task(name="learn.cleanup_pdf_exports")
def cleanup_pdf_exports_task() -> dict[str, int]:
    from app import create_app

    app = create_app()
    with app.app_context():
        return cleanup_expired_pdf_exports(app)
