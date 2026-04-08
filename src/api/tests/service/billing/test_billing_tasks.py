from __future__ import annotations

from datetime import datetime
import sys
import types

from flask import Flask
import pytest

from flaskr.service.billing.tasks import (
    expire_wallet_buckets_task,
    reconcile_provider_reference_task,
    replay_usage_settlement_task,
    retry_failed_renewal_task,
    run_renewal_event_task,
    send_low_balance_alert_task,
    settle_usage_task,
)


def test_settle_usage_task_calls_settlement_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )

    captured: dict[str, object] = {}

    def _fake_settle_bill_usage(app, *, usage_bid: str = ""):
        captured["app"] = app
        captured["usage_bid"] = usage_bid
        return {
            "status": "settled",
            "creator_bid": "creator-task-1",
            "usage_bid": usage_bid,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.settle_bill_usage",
        _fake_settle_bill_usage,
    )

    payload = settle_usage_task(
        creator_bid="creator-task-1",
        usage_bid="usage-task-1",
    )

    assert captured == {
        "app": fake_app,
        "usage_bid": "usage-task-1",
    }
    assert payload["status"] == "settled"
    assert payload["task_name"] == "billing.settle_usage"
    assert payload["requested_creator_bid"] == "creator-task-1"


def test_settle_usage_task_normalizes_empty_creator_bid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: object()),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.settle_bill_usage",
        lambda app, *, usage_bid="": {"status": "noop", "usage_bid": usage_bid},
    )

    payload = settle_usage_task(creator_bid="  ", usage_bid="usage-task-2")

    assert payload["status"] == "noop"
    assert payload["requested_creator_bid"] is None
    assert payload["task_name"] == "billing.settle_usage"


def test_replay_usage_settlement_task_calls_replay_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )

    captured: dict[str, object] = {}

    def _fake_replay_bill_usage_settlement(
        app,
        *,
        creator_bid: str = "",
        usage_bid: str = "",
        usage_id=None,
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["usage_bid"] = usage_bid
        captured["usage_id"] = usage_id
        return {
            "status": "already_settled",
            "creator_bid": creator_bid,
            "usage_bid": usage_bid,
            "replay": True,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.replay_bill_usage_settlement",
        _fake_replay_bill_usage_settlement,
    )

    payload = replay_usage_settlement_task(
        creator_bid="creator-task-2",
        usage_bid="usage-task-2",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-2",
        "usage_bid": "usage-task-2",
        "usage_id": None,
    }
    assert payload["status"] == "already_settled"
    assert payload["task_name"] == "billing.replay_usage_settlement"
    assert payload["replay"] is True


def test_expire_wallet_buckets_task_calls_wallet_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )

    captured: dict[str, object] = {}

    def _fake_expire_credit_wallet_buckets(app, *, creator_bid="", expire_before=None):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["expire_before"] = expire_before
        return {"status": "expired", "bucket_count": 2}

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.expire_credit_wallet_buckets",
        _fake_expire_credit_wallet_buckets,
    )

    payload = expire_wallet_buckets_task(
        creator_bid="creator-task-expire",
        expire_before="2026-04-08T12:34:56",
    )

    assert captured["app"] is fake_app
    assert captured["creator_bid"] == "creator-task-expire"
    assert captured["expire_before"] == datetime(2026, 4, 8, 12, 34, 56)
    assert payload["status"] == "expired"
    assert payload["task_name"] == "billing.expire_wallet_buckets"


def test_reconcile_provider_reference_task_delegates_to_reconcile_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )

    captured: dict[str, object] = {}

    def _fake_run_reconcile_provider_reference(
        app,
        *,
        creator_bid="",
        payment_provider="",
        provider_reference_id="",
        billing_order_bid="",
        session_id="",
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["payment_provider"] = payment_provider
        captured["provider_reference_id"] = provider_reference_id
        captured["billing_order_bid"] = billing_order_bid
        captured["session_id"] = session_id
        return {"status": "paid", "billing_order_bid": billing_order_bid}

    monkeypatch.setattr(
        "flaskr.service.billing.tasks._run_reconcile_provider_reference",
        _fake_run_reconcile_provider_reference,
    )

    payload = reconcile_provider_reference_task(
        creator_bid="creator-task-reconcile",
        payment_provider="stripe",
        provider_reference_id="cs_task_reconcile",
        billing_order_bid="billing-order-task-reconcile",
        session_id="cs_task_reconcile",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-reconcile",
        "payment_provider": "stripe",
        "provider_reference_id": "cs_task_reconcile",
        "billing_order_bid": "billing-order-task-reconcile",
        "session_id": "cs_task_reconcile",
    }
    assert payload["status"] == "paid"
    assert payload["task_name"] == "billing.reconcile_provider_reference"


def test_send_low_balance_alert_task_filters_to_low_balance_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.build_billing_overview",
        lambda app, creator_bid, timezone_name=None: {
            "creator_bid": creator_bid,
            "wallet": {"available_credits": "0E-10"},
            "billing_alerts": [
                {"code": "low_balance", "severity": "warning"},
                {"code": "subscription_past_due", "severity": "error"},
            ],
        },
    )

    payload = send_low_balance_alert_task(creator_bid="creator-task-alert")

    assert payload["status"] == "alerts_found"
    assert payload["creator_count"] == 1
    assert payload["alert_count"] == 1
    assert payload["creators"][0]["creator_bid"] == "creator-task-alert"
    assert payload["creators"][0]["alerts"] == [
        {"code": "low_balance", "severity": "warning"}
    ]
    assert payload["task_name"] == "billing.send_low_balance_alert"


def test_run_renewal_event_task_delegates_to_renewal_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.run_billing_renewal_event",
        lambda app, **kwargs: {
            "status": "applied",
            "renewal_event_bid": kwargs["renewal_event_bid"],
            "event_status": "succeeded",
        },
    )

    payload = run_renewal_event_task(
        renewal_event_bid="renewal-task-1",
        subscription_bid="subscription-task-1",
        creator_bid="creator-task-1",
    )

    assert payload["status"] == "applied"
    assert payload["renewal_event_bid"] == "renewal-task-1"
    assert payload["event_status"] == "succeeded"
    assert payload["task_name"] == "billing.run_renewal_event"


def test_retry_failed_renewal_task_reuses_reconcile_helper_when_reference_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )

    captured: dict[str, object] = {}

    def _fake_run_reconcile_provider_reference(
        app,
        *,
        creator_bid="",
        payment_provider="",
        provider_reference_id="",
        billing_order_bid="",
        session_id="",
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["payment_provider"] = payment_provider
        captured["provider_reference_id"] = provider_reference_id
        captured["billing_order_bid"] = billing_order_bid
        captured["session_id"] = session_id
        return {"status": "paid", "billing_order_bid": billing_order_bid}

    monkeypatch.setattr(
        "flaskr.service.billing.tasks._run_reconcile_provider_reference",
        _fake_run_reconcile_provider_reference,
    )

    payload = retry_failed_renewal_task(
        renewal_event_bid="renewal-task-retry",
        billing_order_bid="billing-order-retry",
        provider_reference_id="cs_retry_task",
        payment_provider="stripe",
        creator_bid="creator-task-retry",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-retry",
        "payment_provider": "stripe",
        "provider_reference_id": "cs_retry_task",
        "billing_order_bid": "billing-order-retry",
        "session_id": "cs_retry_task",
    }
    assert payload["status"] == "paid"
    assert payload["renewal_event_bid"] == "renewal-task-retry"
    assert payload["task_name"] == "billing.retry_failed_renewal"
