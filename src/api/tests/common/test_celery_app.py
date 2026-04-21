from __future__ import annotations

import sys
import types

from flask import Flask, current_app

import flaskr.common.celery_app as celery_app_module


def _assert_cron_schedule(
    schedule,
    *,
    minute: str,
    hour: str,
    day_of_month: str = "*",
    month_of_year: str = "*",
    day_of_week: str = "*",
) -> None:
    assert getattr(schedule, "_orig_minute") == minute
    assert getattr(schedule, "_orig_hour") == hour
    assert getattr(schedule, "_orig_day_of_month") == day_of_month
    assert getattr(schedule, "_orig_month_of_year") == month_of_year
    assert getattr(schedule, "_orig_day_of_week") == day_of_week


def test_create_celery_app_reuses_flask_config() -> None:
    flask_app = Flask(__name__)
    flask_app.config.update(
        CELERY_BROKER_URL="redis://broker.example:6379/3",
        CELERY_RESULT_BACKEND="redis://backend.example:6379/4",
        CELERY_TASK_ALWAYS_EAGER=True,
        TZ="Asia/Shanghai",
        BILLING_RENEWAL_CRON="*/2 * * * *",
        BILLING_BUCKET_EXPIRE_CRON="*/15 * * * *",
        BILLING_LOW_BALANCE_CRON="30 * * * *",
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
    assert "billing.send_subscription_purchase_sms" in celery_app.tasks
    assert "billing.dispatch_due_renewal_events" in celery_app.tasks
    assert "billing.run_renewal_event" in celery_app.tasks
    assert "billing.retry_failed_renewal" in celery_app.tasks
    assert "billing.aggregate_daily_usage_metrics" in celery_app.tasks
    assert "billing.aggregate_daily_ledger_summary" in celery_app.tasks
    assert "billing.rebuild_daily_aggregates" in celery_app.tasks
    assert "billing.verify_domain_binding" in celery_app.tasks

    beat_schedule = celery_app.conf.beat_schedule
    assert beat_schedule["billing.dispatch_due_renewal_events.schedule"]["task"] == (
        "billing.dispatch_due_renewal_events"
    )
    assert beat_schedule["billing.expire_wallet_buckets.schedule"]["task"] == (
        "billing.expire_wallet_buckets"
    )
    assert beat_schedule["billing.send_low_balance_alert.schedule"]["task"] == (
        "billing.send_low_balance_alert"
    )
    _assert_cron_schedule(
        beat_schedule["billing.dispatch_due_renewal_events.schedule"]["schedule"],
        minute="*/2",
        hour="*",
    )
    _assert_cron_schedule(
        beat_schedule["billing.expire_wallet_buckets.schedule"]["schedule"],
        minute="*/15",
        hour="*",
    )
    _assert_cron_schedule(
        beat_schedule["billing.send_low_balance_alert.schedule"]["schedule"],
        minute="30",
        hour="*",
    )


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


def test_create_celery_app_executes_billing_tasks_in_eager_mode(
    monkeypatch,
) -> None:
    flask_app = Flask(__name__)
    flask_app.config.update(
        CELERY_TASK_ALWAYS_EAGER=True,
        TZ="UTC",
    )
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: flask_app),
    )

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.settle_bill_usage",
        lambda app, *, usage_bid="": {
            "status": "settled",
            "usage_bid": usage_bid,
            "creator_bid": "creator-eager-1",
        },
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.expire_credit_wallet_buckets",
        lambda app, *, creator_bid="", expire_before=None: {
            "status": "expired",
            "creator_bid": creator_bid,
            "expire_before": expire_before.isoformat() if expire_before else None,
            "bucket_count": 1,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.aggregate_daily_usage_metrics",
        lambda app, *, stat_date="", creator_bid="", finalize=False: {
            "status": "finalized" if finalize else "aggregated",
            "stat_date": stat_date,
            "creator_bid": creator_bid or None,
            "finalize": finalize,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.aggregate_daily_ledger_summary",
        lambda app, *, stat_date="", creator_bid="", finalize=False: {
            "status": "finalized" if finalize else "aggregated",
            "stat_date": stat_date,
            "creator_bid": creator_bid or None,
            "finalize": finalize,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.rebuild_daily_aggregates",
        lambda app, *, creator_bid="", shifu_bid="", date_from="", date_to="": {
            "status": "rebuilt",
            "creator_bid": creator_bid or None,
            "shifu_bid": shifu_bid or None,
            "date_from": date_from,
            "date_to": date_to,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.verify_domain_binding",
        lambda app, *, creator_bid="", domain_binding_bid="", host="", verification_token="": {
            "action": "verify",
            "creator_bid": creator_bid or None,
            "binding": {
                "domain_binding_bid": domain_binding_bid or None,
                "host": host or None,
            },
            "verification_token": verification_token or None,
        },
    )

    celery_app = celery_app_module.create_celery_app(flask_app=flask_app)

    settle_result = celery_app.tasks["billing.settle_usage"].apply(
        kwargs={
            "creator_bid": "creator-eager-1",
            "usage_bid": "usage-eager-1",
        }
    )
    expire_result = celery_app.tasks["billing.expire_wallet_buckets"].apply(
        kwargs={
            "creator_bid": "creator-eager-1",
            "expire_before": "2026-04-08T10:00:00",
        }
    )
    aggregate_result = celery_app.tasks["billing.aggregate_daily_usage_metrics"].apply(
        kwargs={
            "stat_date": "2026-04-08",
            "creator_bid": "creator-eager-1",
            "finalize": True,
        }
    )
    ledger_aggregate_result = celery_app.tasks[
        "billing.aggregate_daily_ledger_summary"
    ].apply(
        kwargs={
            "stat_date": "2026-04-08",
            "creator_bid": "creator-eager-1",
            "finalize": True,
        }
    )
    rebuild_result = celery_app.tasks["billing.rebuild_daily_aggregates"].apply(
        kwargs={
            "creator_bid": "creator-eager-1",
            "shifu_bid": "shifu-eager-1",
            "date_from": "2026-04-08",
            "date_to": "2026-04-09",
        }
    )
    verify_domain_result = celery_app.tasks["billing.verify_domain_binding"].apply(
        kwargs={
            "creator_bid": "creator-eager-1",
            "domain_binding_bid": "binding-eager-1",
            "host": "academy.example.com",
            "verification_token": "token-eager-1",
        }
    )

    assert settle_result.get() == {
        "status": "settled",
        "usage_bid": "usage-eager-1",
        "creator_bid": "creator-eager-1",
        "requested_creator_bid": "creator-eager-1",
        "task_name": "billing.settle_usage",
    }
    assert expire_result.get() == {
        "status": "expired",
        "creator_bid": "creator-eager-1",
        "expire_before": "2026-04-08T10:00:00",
        "bucket_count": 1,
        "task_name": "billing.expire_wallet_buckets",
    }
    assert aggregate_result.get() == {
        "status": "finalized",
        "stat_date": "2026-04-08",
        "creator_bid": "creator-eager-1",
        "finalize": True,
        "task_name": "billing.aggregate_daily_usage_metrics",
    }
    assert ledger_aggregate_result.get() == {
        "status": "finalized",
        "stat_date": "2026-04-08",
        "creator_bid": "creator-eager-1",
        "finalize": True,
        "task_name": "billing.aggregate_daily_ledger_summary",
    }
    assert rebuild_result.get() == {
        "status": "rebuilt",
        "creator_bid": "creator-eager-1",
        "shifu_bid": "shifu-eager-1",
        "date_from": "2026-04-08",
        "date_to": "2026-04-09",
        "task_name": "billing.rebuild_daily_aggregates",
    }
    assert verify_domain_result.get() == {
        "action": "verify",
        "creator_bid": "creator-eager-1",
        "binding": {
            "domain_binding_bid": "binding-eager-1",
            "host": "academy.example.com",
        },
        "verification_token": "token-eager-1",
        "task_name": "billing.verify_domain_binding",
    }


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


def test_create_celery_app_uses_default_billing_beat_crons() -> None:
    flask_app = Flask(__name__)
    celery_app = celery_app_module.create_celery_app(flask_app=flask_app)

    beat_schedule = celery_app.conf.beat_schedule

    _assert_cron_schedule(
        beat_schedule["billing.dispatch_due_renewal_events.schedule"]["schedule"],
        minute="*",
        hour="*",
    )
    _assert_cron_schedule(
        beat_schedule["billing.expire_wallet_buckets.schedule"]["schedule"],
        minute="*",
        hour="*",
    )
    _assert_cron_schedule(
        beat_schedule["billing.send_low_balance_alert.schedule"]["schedule"],
        minute="0",
        hour="*",
    )
