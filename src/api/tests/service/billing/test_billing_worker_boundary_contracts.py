"""Verify worker batching, payload contracts and failures without a broker."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.billing import provider_catalog_sync, tasks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProviderCatalogSnapshot,
    BillingSubscription,
    CreditWallet,
)
from flaskr.service.billing.provider_catalog import (
    ProviderAccountSnapshot,
    ProviderProductSnapshot,
)
from flaskr.util.datetime import now_utc

from tests.service.billing.test_billing_tasks import (
    billing_task_integration_app as worker_app,
)

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["worker_app"]


@pytest.mark.parametrize("shape", ["dict", "to_task_payload", "to_payload", "__json__"])
def test_reconcile_worker_normalizes_identifiers_and_serializes_result_without_mutating_it(
    worker_app: Flask,
    shape: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"status": "reconciled", "bill_order_bid": "order-1"}
    result = (
        dict(payload)
        if shape == "dict"
        else SimpleNamespace(**{shape: lambda: dict(payload)})
    )
    reconcile = Mock(return_value=result)
    monkeypatch.setattr(tasks, "_create_task_app", lambda: worker_app)
    monkeypatch.setattr(tasks, "reconcile_billing_provider_reference", reconcile)
    actual = tasks.reconcile_provider_reference_task(
        creator_bid=" teacher ",
        payment_provider=" stripe ",
        provider_reference_id=" ref ",
        bill_order_bid=" order-1 ",
        session_id=" session ",
    )
    reconcile.assert_called_once_with(
        worker_app,
        creator_bid="teacher",
        payment_provider="stripe",
        provider_reference_id="ref",
        bill_order_bid="order-1",
        session_id="session",
    )
    assert actual == {**payload, "task_name": "billing.reconcile_provider_reference"}
    assert "task_name" not in payload
    if shape == "dict":
        assert "task_name" not in result


def test_unsupported_worker_result_is_rejected_instead_of_returning_success(
    worker_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "_create_task_app", lambda: worker_app)
    monkeypatch.setattr(
        tasks, "reconcile_billing_provider_reference", Mock(return_value=object())
    )
    with pytest.raises(TypeError, match="Unsupported task payload type"):
        tasks.reconcile_provider_reference_task()


def test_legacy_low_balance_result_preserves_alert_payload_contract() -> None:
    alert = {"threshold": "3"}
    result = tasks.LowBalanceAlertTaskResult(
        status="candidate",
        creator_count=1,
        alert_count=3,
        creators=[
            tasks.LowBalanceAlertCandidate(
                creator_bid="teacher",
                wallet_available_credits="2",
                alerts=[
                    SimpleNamespace(__json__=lambda: {"threshold": "1"}),
                    alert,
                    "legacy",
                ],
            )
        ],
    )
    payload = result.to_task_payload()
    assert payload == {
        "status": "candidate",
        "creator_count": 1,
        "alert_count": 3,
        "task_name": "billing.send_low_balance_alert",
        "creators": [
            {
                "creator_bid": "teacher",
                "wallet_available_credits": "2",
                "alerts": [{"threshold": "1"}, {"threshold": "3"}, "legacy"],
            }
        ],
    }
    payload["creators"][0]["alerts"][1]["threshold"] = "changed"
    assert alert == {"threshold": "3"}


def test_low_balance_candidates_merge_wallet_and_subscription_owners(
    worker_app: Flask,
) -> None:
    del worker_app
    for creator, deleted in [("owner-a", 0), ("owner-b", 0), ("deleted", 1), ("", 0)]:
        db.session.add(
            CreditWallet(wallet_bid=uuid4().hex, creator_bid=creator, deleted=deleted)
        )
    for creator, deleted in [("owner-a", 0), ("owner-c", 0), ("deleted", 1), (" ", 0)]:
        db.session.add(
            BillingSubscription(
                subscription_bid=uuid4().hex, creator_bid=creator, deleted=deleted
            )
        )
    db.session.commit()
    assert tasks._collect_low_balance_creator_bids() == [
        "owner-a",
        "owner-b",
        "owner-c",
    ]


def test_expiration_batch_continues_after_provider_failure_and_counts_terminal_outcomes(
    worker_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = now_utc()
    outcomes = [
        "transport",
        "timeout",
        "paid",
        "failed",
        "canceled",
        "refunded",
        "pending",
    ]
    for index, status in enumerate(outcomes):
        db.session.add(
            BillingOrder(
                bill_order_bid=status,
                creator_bid="owner",
                status=BILLING_ORDER_STATUS_PENDING,
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                expires_at=now - timedelta(minutes=10 - index),
            )
        )
    for bid, changes in [
        ("future", {"expires_at": now + timedelta(hours=1)}),
        ("paid-before", {"status": BILLING_ORDER_STATUS_PAID}),
        ("deleted", {"deleted": 1}),
        ("other-owner", {"creator_bid": "other"}),
    ]:
        db.session.add(
            BillingOrder(
                **{
                    "bill_order_bid": bid,
                    "creator_bid": "owner",
                    "status": BILLING_ORDER_STATUS_PENDING,
                    "expires_at": now - timedelta(minutes=30),
                    **changes,
                }
            )
        )
    db.session.commit()
    observed = []

    def synchronize(app: Flask, creator: str, bid: str, payload: dict) -> object:
        assert app is worker_app
        assert creator == "owner"
        assert payload == {}
        observed.append(bid)
        if bid == "transport":
            message = "provider unavailable"
            raise RuntimeError(message)
        return (
            {"status": bid}
            if bid in {"timeout", "canceled"}
            else SimpleNamespace(status=bid)
        )

    monkeypatch.setattr(tasks, "sync_billing_order", synchronize)
    result = tasks._expire_pending_billing_orders(
        worker_app, creator_bid=" owner ", expire_before=now
    )
    assert observed == outcomes
    assert result["inspected_count"] == 7
    assert (
        result["timeout_count"] == result["paid_count"] == result["failed_count"] == 1
    )
    assert result["terminal_count"] == 3
    assert result["failed_bill_order_bids"] == ["transport"]
    assert result["bill_order_bids"] == outcomes[1:]


@pytest.mark.parametrize("raw", [None, "{", "[]", "null"])
def test_invalid_renewal_worker_config_disables_dispatch_without_broker_access(
    worker_app: Flask,
    raw: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = Mock()
    monkeypatch.setattr(tasks, "get_config", lambda *_: raw)
    monkeypatch.setattr(tasks.run_renewal_event_task, "apply_async", broker)
    assert tasks.dispatch_due_renewal_events(worker_app)["status"] == "noop_disabled"
    broker.assert_not_called()


@pytest.mark.parametrize(
    ("task", "scanner", "task_name"),
    [
        (
            "scan_credit_expiring_notifications_task",
            "_scan_credit_expiring_notifications",
            "billing.scan_credit_expiring_notifications",
        ),
        (
            "scan_low_balance_notifications_task",
            "_scan_low_balance_notifications",
            "billing.scan_low_balance_notifications",
        ),
    ],
)
@pytest.mark.parametrize("failed", [False, True])
def test_scan_worker_normalizes_owner_and_propagates_failure(
    worker_app: Flask,
    task: str,
    scanner: str,
    task_name: str,
    failed: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan = Mock(return_value={"status": "processed", "enqueued_count": 2})
    if failed:
        scan.side_effect = RuntimeError("scan failed")
    monkeypatch.setattr(tasks, "_create_task_app", lambda: worker_app)
    monkeypatch.setattr(tasks, scanner, scan)
    if failed:
        with pytest.raises(RuntimeError, match="scan failed"):
            getattr(tasks, task)(creator_bid=" teacher ")
    else:
        assert getattr(tasks, task)(creator_bid=" teacher ") == {
            "status": "processed",
            "enqueued_count": 2,
            "task_name": task_name,
        }
    scan.assert_called_once_with(worker_app, creator_bid="teacher")


def test_catalog_worker_persists_real_catalog_snapshot_and_reports_count(
    worker_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = Mock()
    reader.retrieve_account_snapshot.return_value = ProviderAccountSnapshot(
        "stripe", "acct_owner", livemode=False
    )
    reader.list_product_snapshots.return_value = [
        ProviderProductSnapshot("stripe", "prod_worker", active=True, livemode=False)
    ]
    reader.list_price_snapshots.return_value = []
    monkeypatch.setattr(tasks, "_create_task_app", lambda: worker_app)
    monkeypatch.setattr(
        provider_catalog_sync, "StripeCatalogReadAdapter", Mock(return_value=reader)
    )
    result = tasks.reconcile_provider_catalog_task()
    snapshot = BillingProviderCatalogSnapshot.query.one()
    assert snapshot.object_id == "prod_worker"
    assert snapshot.provider_account_id == "acct_owner"
    assert result["task_name"] == "billing.reconcile_provider_catalog"
    assert result["products"] == result["processed"] == 1
    assert result["prices"] == 0


def test_successful_subscription_sms_worker_returns_a_serializable_result(
    worker_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deliver = Mock(return_value={"status": "sent", "bill_order_bid": "order-1"})
    monkeypatch.setattr(tasks, "_create_task_app", lambda: worker_app)
    monkeypatch.setattr(tasks, "_deliver_subscription_purchase_sms", deliver)
    result = tasks.send_subscription_purchase_sms_task(bill_order_bid=" order-1 ")
    deliver.assert_called_once_with(worker_app, bill_order_bid="order-1")
    assert result["status"] == "sent"
    assert result["task_name"] == "billing.send_subscription_purchase_sms"
