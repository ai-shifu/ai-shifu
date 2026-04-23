"""Shared Celery app factory that reuses the Flask application factory."""

from __future__ import annotations

import importlib
import os
from typing import Any

from celery import Celery, Task
from celery.schedules import crontab
from flask import Flask

_DEFAULT_BROKER_URL = "redis://localhost:6379/0"
_DEFAULT_BILLING_RENEWAL_CRON = "* * * * *"
_DEFAULT_BILLING_BUCKET_EXPIRE_CRON = "* * * * *"
_DEFAULT_BILLING_LOW_BALANCE_CRON = "0 * * * *"

__CELERY_APP__: Celery | None = None


def create_celery_app(flask_app: Flask | None = None) -> Celery:
    """Build a Celery app bound to the Flask app context."""

    resolved_flask_app = flask_app or _load_flask_app()

    class FlaskTask(Task):
        abstract = True

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            with resolved_flask_app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(
        resolved_flask_app.import_name,
        task_cls=FlaskTask,
        include=("flaskr.service.billing.tasks",),
    )
    celery_app.conf.update(_build_celery_config(resolved_flask_app))
    celery_app.flask_app = resolved_flask_app  # type: ignore[attr-defined]
    celery_app.set_default()
    _register_default_tasks()
    return celery_app


def get_celery_app(flask_app: Flask | None = None) -> Celery:
    """Return a cached Celery app or create one on demand."""

    global __CELERY_APP__
    if __CELERY_APP__ is None or flask_app is not None:
        __CELERY_APP__ = create_celery_app(flask_app=flask_app)
    return __CELERY_APP__


def _build_celery_config(flask_app: Flask) -> dict[str, Any]:
    broker_url = (
        flask_app.config.get("CELERY_BROKER_URL")
        or os.getenv("CELERY_BROKER_URL")
        or _DEFAULT_BROKER_URL
    )
    result_backend = (
        flask_app.config.get("CELERY_RESULT_BACKEND")
        or os.getenv("CELERY_RESULT_BACKEND")
        or broker_url
    )
    task_always_eager = _to_bool(
        flask_app.config.get(
            "CELERY_TASK_ALWAYS_EAGER",
            os.getenv("CELERY_TASK_ALWAYS_EAGER", False),
        )
    )
    return {
        "broker_url": broker_url,
        "result_backend": result_backend,
        "task_always_eager": task_always_eager,
        "task_ignore_result": False,
        "broker_connection_retry_on_startup": True,
        "timezone": flask_app.config.get("TZ", "UTC"),
        "imports": ("flaskr.service.billing.tasks",),
        "beat_schedule": _build_billing_beat_schedule(flask_app),
    }


def _build_billing_beat_schedule(flask_app: Flask) -> dict[str, Any]:
    return {
        "billing.dispatch_due_renewal_events.schedule": {
            "task": "billing.dispatch_due_renewal_events",
            "schedule": _resolve_billing_crontab(
                flask_app,
                "BILLING_RENEWAL_CRON",
                _DEFAULT_BILLING_RENEWAL_CRON,
            ),
        },
        "billing.expire_wallet_buckets.schedule": {
            "task": "billing.expire_wallet_buckets",
            "schedule": _resolve_billing_crontab(
                flask_app,
                "BILLING_BUCKET_EXPIRE_CRON",
                _DEFAULT_BILLING_BUCKET_EXPIRE_CRON,
            ),
        },
        "billing.send_low_balance_alert.schedule": {
            "task": "billing.send_low_balance_alert",
            "schedule": _resolve_billing_crontab(
                flask_app,
                "BILLING_LOW_BALANCE_CRON",
                _DEFAULT_BILLING_LOW_BALANCE_CRON,
            ),
        },
    }


def _resolve_billing_crontab(
    flask_app: Flask,
    config_key: str,
    default_expression: str,
):
    raw_expression = str(
        flask_app.config.get(config_key) or os.getenv(config_key) or default_expression
    ).strip()
    schedule = _parse_crontab_expression(raw_expression)
    if schedule is not None:
        return schedule

    flask_app.logger.warning(
        "Invalid %s=%r; falling back to %s",
        config_key,
        raw_expression,
        default_expression,
    )
    fallback_schedule = _parse_crontab_expression(default_expression)
    if fallback_schedule is None:  # pragma: no cover - guarded by constants above
        raise ValueError(f"Invalid default cron expression for {config_key}")
    return fallback_schedule


def _parse_crontab_expression(expression: str):
    normalized_expression = " ".join(str(expression or "").split())
    parts = normalized_expression.split(" ")
    if len(parts) != 5 or any(not part for part in parts):
        return None

    minute, hour, day_of_month, month_of_year, day_of_week = parts
    try:
        return crontab(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        )
    except Exception:
        return None


def _load_flask_app() -> Flask:
    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    app_module = importlib.import_module("app")
    return app_module.create_app()


def _register_default_tasks() -> None:
    importlib.import_module("flaskr.service.billing.tasks")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
