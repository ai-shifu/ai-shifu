"""Celery application entrypoint for worker and beat processes."""

from __future__ import annotations

from flaskr.common.celery_app import get_celery_app

celery_app = get_celery_app()
