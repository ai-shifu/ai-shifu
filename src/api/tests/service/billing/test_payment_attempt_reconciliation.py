"""Verify provider-backed subscription payment-attempt reconciliation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
)
from flaskr.service.billing.models import BillingOrder
from flaskr.service.billing.payment_attempt_reconciliation import (
    reconcile_subscription_payment_attempts,
)
from flaskr.service.order.models import StripeOrder

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


def test_reconciliation_does_not_close_a_replaced_provider_reference(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import payment_attempt_reconciliation as reconciliation

    provider = Mock()

    def replace_reference(**_kwargs: object) -> SimpleNamespace:
        current = BillingOrder.query.filter_by(
            bill_order_bid="reconcile-replaced-reference"
        ).one()
        current.provider_reference_id = "new-provider-attempt"
        dao.db.session.add(current)
        dao.db.session.commit()
        return SimpleNamespace(status="cancelled")

    provider.cancel_payment.side_effect = replace_reference
    monkeypatch.setattr(
        reconciliation, "get_payment_provider", Mock(return_value=provider)
    )
    with billing_wallet_lifecycle_app.app_context():
        order = BillingOrder(
            bill_order_bid="reconcile-replaced-reference",
            creator_bid="reconcile-creator",
            subscription_bid="reconcile-subscription",
            product_bid="reconcile-product",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            payment_provider="alipay",
            provider_reference_id="old-provider-attempt",
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
        assert result.attempts[0].reason == "provider_reference_changed"
        assert order.status == BILLING_ORDER_STATUS_FAILED
        assert order.provider_reference_id == "new-provider-attempt"
        assert order.metadata_json is None


def test_reconciliation_keeps_provider_payable_attempt_unresolved(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import payment_attempt_reconciliation as reconciliation

    provider = Mock()
    provider.cancel_payment.return_value = SimpleNamespace(status="pending")
    monkeypatch.setattr(
        reconciliation, "get_payment_provider", Mock(return_value=provider)
    )
    with billing_wallet_lifecycle_app.app_context():
        order = BillingOrder(
            bill_order_bid="reconcile-still-payable",
            creator_bid="reconcile-creator",
            subscription_bid="reconcile-subscription",
            product_bid="reconcile-product",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            payment_provider="alipay",
            provider_reference_id="provider-attempt",
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
        assert result.attempts[0].reason == "provider_attempt_still_payable"
        assert order.status == BILLING_ORDER_STATUS_FAILED
        assert order.metadata_json is None


def test_reconciliation_runs_without_an_existing_app_context(
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
        dao.db.session.add(
            BillingOrder(
                bill_order_bid="reconcile-without-context",
                creator_bid="reconcile-creator",
                subscription_bid="reconcile-subscription",
                product_bid="reconcile-product",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                payment_provider="alipay",
                provider_reference_id="provider-attempt",
                status=BILLING_ORDER_STATUS_FAILED,
            )
        )
        dao.db.session.commit()

    result = reconcile_subscription_payment_attempts(
        billing_wallet_lifecycle_app,
        creator_bid="reconcile-creator",
        subscription_bid="reconcile-subscription",
        operation_id="reconcile-operation",
    )

    assert result.settled is True
    assert result.attempts[0].status == "closed"


def test_reconciliation_closes_orphan_provider_snapshot_on_paid_order(
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
            bill_order_bid="reconcile-orphan-snapshot",
            creator_bid="reconcile-creator",
            subscription_bid="reconcile-subscription",
            product_bid="reconcile-product",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            payment_provider="stripe",
            provider_reference_id="cs-settled",
            status=BILLING_ORDER_STATUS_PAID,
        )
        snapshot = StripeOrder(
            stripe_order_bid=order.bill_order_bid,
            biz_domain="billing",
            bill_order_bid=order.bill_order_bid,
            creator_bid=order.creator_bid,
            checkout_session_id="cs-orphan",
            status=0,
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )
        dao.db.session.add_all([order, snapshot])
        dao.db.session.commit()

        result = reconcile_subscription_payment_attempts(
            billing_wallet_lifecycle_app,
            creator_bid=order.creator_bid,
            subscription_bid=order.subscription_bid,
            operation_id="reconcile-operation",
        )

        dao.db.session.refresh(snapshot)
        assert result.settled is True
        assert len(result.attempts) == 1
        assert result.attempts[0].provider_reference == "cs-orphan"
        assert result.attempts[0].status == "closed"
        assert snapshot.status == 3
        provider.cancel_payment.assert_called_once_with(
            provider_reference="cs-orphan",
            reference_type="checkout_session",
            app=billing_wallet_lifecycle_app,
            context=None,
        )


def test_reconciliation_applies_paid_renewal_invoice_directly(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import payment_attempt_reconciliation as reconciliation

    provider = Mock()
    provider.cancel_payment.return_value = SimpleNamespace(
        status="completed",
        raw_response={"invoice": {"id": "in-paid", "paid": True}},
    )
    update = SimpleNamespace(
        stage_after_state_changes=Mock(),
        dispatch_after_commit=Mock(),
    )

    def apply_paid(locked: BillingOrder, **_kwargs: object) -> SimpleNamespace:
        locked.status = BILLING_ORDER_STATUS_PAID
        return update

    monkeypatch.setattr(
        reconciliation, "get_payment_provider", Mock(return_value=provider)
    )
    monkeypatch.setattr(
        reconciliation,
        "apply_billing_order_provider_update",
        Mock(side_effect=apply_paid),
    )
    with billing_wallet_lifecycle_app.app_context():
        order = BillingOrder(
            bill_order_bid="reconcile-paid-renewal",
            creator_bid="reconcile-creator",
            subscription_bid="reconcile-subscription",
            product_bid="reconcile-product",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            payment_provider="stripe",
            provider_reference_id="sub-test",
            status=BILLING_ORDER_STATUS_FAILED,
            metadata_json={
                "provider_reference_type": "subscription",
                "renewal_cycle_start_at": "2026-10-01T00:00:00",
                "renewal_cycle_end_at": "2026-11-01T00:00:00",
            },
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
        assert result.settled is True
        assert result.attempts[0].status == "paid"
        assert order.status == BILLING_ORDER_STATUS_PAID
        update.stage_after_state_changes.assert_called_once()
        update.dispatch_after_commit.assert_called_once_with(
            billing_wallet_lifecycle_app
        )


def test_reconciliation_marks_paid_orphan_snapshot_terminal(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import payment_attempt_reconciliation as reconciliation

    provider = Mock()
    provider.cancel_payment.return_value = SimpleNamespace(status="completed")
    monkeypatch.setattr(
        reconciliation, "get_payment_provider", Mock(return_value=provider)
    )
    with billing_wallet_lifecycle_app.app_context():
        order = BillingOrder(
            bill_order_bid="reconcile-paid-orphan",
            creator_bid="reconcile-creator",
            subscription_bid="reconcile-subscription",
            product_bid="reconcile-product",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            payment_provider="stripe",
            provider_reference_id="cs-settled",
            status=BILLING_ORDER_STATUS_PAID,
        )
        snapshot = StripeOrder(
            stripe_order_bid=order.bill_order_bid,
            biz_domain="billing",
            bill_order_bid=order.bill_order_bid,
            creator_bid=order.creator_bid,
            checkout_session_id="cs-paid-orphan",
            status=0,
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )
        dao.db.session.add_all([order, snapshot])
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

        dao.db.session.refresh(snapshot)
        assert result.attempts[0].status == "paid"
        assert replay.attempts == ()
        assert snapshot.status == 1
        provider.cancel_payment.assert_called_once()
