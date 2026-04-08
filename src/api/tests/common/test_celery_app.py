from __future__ import annotations

import sys
import types

from flask import Flask, current_app

import flaskr.common.celery_app as celery_app_module


def test_create_celery_app_reuses_flask_config() -> None:
    flask_app = Flask(__name__)
    flask_app.config.update(
        CELERY_BROKER_URL="redis://broker.example:6379/3",
        CELERY_RESULT_BACKEND="redis://backend.example:6379/4",
        CELERY_TASK_ALWAYS_EAGER=True,
        TZ="Asia/Shanghai",
    )

    celery_app = celery_app_module.create_celery_app(flask_app=flask_app)

    assert celery_app.conf["broker_url"] == "redis://broker.example:6379/3"
    assert celery_app.conf["result_backend"] == "redis://backend.example:6379/4"
    assert celery_app.conf["task_always_eager"] is True
    assert celery_app.conf["timezone"] == "Asia/Shanghai"
    assert getattr(celery_app, "flask_app") is flask_app
    assert "billing.settle_usage" in celery_app.tasks
    assert "billing.replay_usage_settlement" in celery_app.tasks
    assert "billing.expire_wallet_buckets" in celery_app.tasks
    assert "billing.reconcile_provider_reference" in celery_app.tasks
    assert "billing.send_low_balance_alert" in celery_app.tasks
    assert "billing.run_renewal_event" in celery_app.tasks
    assert "billing.retry_failed_renewal" in celery_app.tasks


def test_create_celery_app_runs_tasks_in_flask_app_context() -> None:
    flask_app = Flask(__name__)
    flask_app.config.update(
        CELERY_TASK_ALWAYS_EAGER=True,
        EXAMPLE_VALUE="from-flask-context",
    )
    celery_app = celery_app_module.create_celery_app(flask_app=flask_app)

    @celery_app.task(name="tests.echo_current_app_value")
    def echo_current_app_value() -> str:
        return current_app.config["EXAMPLE_VALUE"]

    result = echo_current_app_value.apply()

    assert result.get() == "from-flask-context"


def test_get_celery_app_loads_flask_app_from_app_factory(
    monkeypatch,
) -> None:
    fake_flask_app = Flask(__name__)
    fake_flask_app.config.update(CELERY_TASK_ALWAYS_EAGER=True)

    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_flask_app),
    )
    monkeypatch.setattr(celery_app_module, "__CELERY_APP__", None)

    celery_app = celery_app_module.get_celery_app()

    assert getattr(celery_app, "flask_app") is fake_flask_app
