"""Verify provider-backed subscription payment-attempt reconciliation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
)
from flaskr.service.billing.models import BillingOrder
from flaskr.service.billing.payment_attempt_reconciliation import (
    reconcile_subscription_payment_attempts,
)

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]

if TYPE_CHECKING:
    import pytest
    from flask import Flask


def test_reconciliation_closes_and_replays_provider_attempt(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import payment_attempt_reconciliation as reconciliation

    provider = Mock()
    provider.cancel_payment.return_value = SimpleNamespace(status="cancelled")
    monkeypatch.setattr(
        reconciliation, "get_payment_provider", Mock(return_value=provider)
    )
    with billing_wallet_lifecycle_app.app_context():
        order = BillingOrder(
            bill_order_bid="reconcile-failed-upgrade",
            creator_bid="reconcile-creator",
            subscription_bid="reconcile-subscription",
            product_bid="reconcile-product",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            payment_provider="alipay",
            provider_reference_id="native-attempt",
            status=BILLING_ORDER_STATUS_FAILED,
        )
        dao.db.session.add(order)
        dao.db.session.commit()

        result = reconcile_subscription_payment_attempts(
            billing_wallet_lifecycle_app,
            creator_bid=order.creator_bid,
            subscription_bid=order.subscription_bid,
            operation_id="reconcile-operation",
        )
        replay = reconcile_subscription_payment_attempts(
            billing_wallet_lifecycle_app,
            creator_bid=order.creator_bid,
            subscription_bid=order.subscription_bid,
            operation_id="reconcile-operation",
        )

        dao.db.session.refresh(order)
        assert result.settled is True
        assert result.attempts[0].status == "closed"
        assert replay.settled is True
        assert replay.attempts[0].status == "closed"
        assert order.status == BILLING_ORDER_STATUS_CANCELED
        assert order.metadata_json["provider_payment_terminal_evidence"] == {
            "provider": "alipay",
            "provider_reference": "native-attempt",
            "status": "canceled",
            "confirmed_at": order.metadata_json["provider_payment_terminal_evidence"][
                "confirmed_at"
            ],
            "operation_id": "reconcile-operation",
        }
        provider.cancel_payment.assert_called_once()


def test_reconciliation_keeps_missing_provider_reference_unresolved(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        order = BillingOrder(
            bill_order_bid="reconcile-missing-reference",
            creator_bid="reconcile-creator",
            subscription_bid="reconcile-subscription",
            product_bid="reconcile-product",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            payment_provider="alipay",
            provider_reference_id="",
            status=BILLING_ORDER_STATUS_FAILED,
        )
        dao.db.session.add(order)
        dao.db.session.commit()

        result = reconcile_subscription_payment_attempts(
            billing_wallet_lifecycle_app,
            creator_bid=order.creator_bid,
            subscription_bid=order.subscription_bid,
            operation_id="reconcile-operation",
        )

        dao.db.session.refresh(order)
        assert result.settled is False
        assert result.attempts[0].status == "unresolved"
        assert result.attempts[0].reason == "missing_provider_reference"
        assert order.status == BILLING_ORDER_STATUS_FAILED
        assert order.metadata_json is None
