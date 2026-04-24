from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
)
from flaskr.service.billing.checkout import sync_billing_order
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.webhooks import apply_billing_stripe_notification
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from tests.common.fixtures.bill_products import build_bill_products

_MONTHLY_PLAN_CREDITS = Decimal("5.0000000000")


@pytest.fixture
def billing_renewal_compensation_env(monkeypatch: pytest.MonkeyPatch):
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)

    sync_state: dict[str, dict] = {"subscription": {}}

    class FakeStripeProvider:
        def sync_reference(self, *, provider_reference: str, reference_type: str, app):
            assert reference_type == "subscription"
            assert provider_reference == sync_state["subscription"]["id"]
            return PaymentNotificationResult(
                order_bid="",
                status="manual_sync",
                provider_payload={"subscription": dict(sync_state["subscription"])},
                charge_id=None,
            )

    monkeypatch.setattr(
        "flaskr.service.billing.checkout.get_payment_provider",
        lambda channel: FakeStripeProvider(),
    )

    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield {"app": app, "sync_state": sync_state}
        dao.db.session.remove()
        dao.db.drop_all()


def _create_subscription(
    subscription_bid: str,
    *,
    provider_subscription_id: str,
    cycle_start_at: datetime,
) -> BillingSubscription:
    return BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid="creator-1",
        product_bid="bill-product-plan-monthly",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        billing_provider="stripe",
        provider_subscription_id=provider_subscription_id,
        provider_customer_id="cus_renewal_1",
        current_period_start_at=cycle_start_at - timedelta(days=30),
        current_period_end_at=cycle_start_at,
        cancel_at_period_end=0,
        next_product_bid="",
        metadata_json={},
        last_renewed_at=cycle_start_at - timedelta(days=30),
        created_at=cycle_start_at - timedelta(days=60),
        updated_at=cycle_start_at - timedelta(days=1),
    )


def _create_renewal_order(
    subscription: BillingSubscription,
    *,
    bill_order_bid: str,
    cycle_start_at: datetime,
    cycle_end_at: datetime,
) -> BillingOrder:
    return BillingOrder(
        bill_order_bid=bill_order_bid,
        creator_bid=subscription.creator_bid,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        product_bid=subscription.product_bid,
        subscription_bid=subscription.subscription_bid,
        currency="CNY",
        payable_amount=9900,
        paid_amount=0,
        payment_provider="stripe",
        channel="subscription",
        provider_reference_id=subscription.provider_subscription_id,
        status=BILLING_ORDER_STATUS_PENDING,
        metadata_json={
            "provider_reference_type": "subscription",
            "renewal_cycle_start_at": cycle_start_at.isoformat(),
            "renewal_cycle_end_at": cycle_end_at.isoformat(),
        },
    )


def test_sync_billing_order_marks_subscription_renewal_paid(
    billing_renewal_compensation_env,
) -> None:
    app = billing_renewal_compensation_env["app"]
    sync_state = billing_renewal_compensation_env["sync_state"]
    cycle_start_at = datetime(2026, 5, 1, 0, 0, 0)
    cycle_end_at = datetime(2026, 6, 1, 0, 0, 0)

    with app.app_context():
        subscription = _create_subscription(
            "sub-sync-1",
            provider_subscription_id="sub_provider_sync_1",
            cycle_start_at=cycle_start_at,
        )
        order = _create_renewal_order(
            subscription,
            bill_order_bid="bill-renewal-sync-1",
            cycle_start_at=cycle_start_at,
            cycle_end_at=cycle_end_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    sync_state["subscription"] = {
        "id": "sub_provider_sync_1",
        "customer": "cus_renewal_1",
        "status": "active",
        "current_period_start": int(cycle_start_at.timestamp()),
        "current_period_end": int(cycle_end_at.timestamp()),
        "cancel_at_period_end": False,
    }

    payload = sync_billing_order(
        app,
        "creator-1",
        "bill-renewal-sync-1",
        {},
    )

    assert payload.status == "paid"

    with app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid="bill-renewal-sync-1").one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-sync-1"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        bucket = CreditWalletBucket.query.filter_by(
            creator_bid="creator-1",
            source_bid="bill-renewal-sync-1",
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-1",
            source_bid="bill-renewal-sync-1",
        ).one()
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert subscription.current_period_start_at == cycle_start_at
        assert subscription.current_period_end_at == cycle_end_at
        assert wallet.available_credits == _MONTHLY_PLAN_CREDITS
        assert bucket.effective_from == cycle_start_at
        assert bucket.effective_to == cycle_end_at
        assert ledger.balance_after == _MONTHLY_PLAN_CREDITS


def test_stripe_subscription_webhook_matches_pending_renewal_order_and_grants(
    billing_renewal_compensation_env,
) -> None:
    app = billing_renewal_compensation_env["app"]
    cycle_start_at = datetime(2026, 7, 1, 0, 0, 0)
    cycle_end_at = datetime(2026, 8, 1, 0, 0, 0)

    with app.app_context():
        subscription = _create_subscription(
            "sub-webhook-1",
            provider_subscription_id="sub_provider_webhook_1",
            cycle_start_at=cycle_start_at,
        )
        order = _create_renewal_order(
            subscription,
            bill_order_bid="bill-renewal-webhook-1",
            cycle_start_at=cycle_start_at,
            cycle_end_at=cycle_end_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    payload, status_code = apply_billing_stripe_notification(
        app,
        PaymentNotificationResult(
            order_bid="",
            status="customer.subscription.updated",
            provider_payload={
                "type": "customer.subscription.updated",
                "created": int(cycle_end_at.timestamp()),
                "data": {
                    "object": {
                        "id": "sub_provider_webhook_1",
                        "customer": "cus_renewal_1",
                        "status": "active",
                        "current_period_start": int(cycle_start_at.timestamp()),
                        "current_period_end": int(cycle_end_at.timestamp()),
                        "cancel_at_period_end": False,
                        "metadata": {},
                    }
                },
            },
            charge_id=None,
        ),
    )

    assert status_code == 200
    assert payload["status"] == "paid"
    assert payload["bill_order_bid"] == "bill-renewal-webhook-1"

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="bill-renewal-webhook-1"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        ledgers = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-1",
            source_bid="bill-renewal-webhook-1",
        ).all()
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert wallet.available_credits == _MONTHLY_PLAN_CREDITS
        assert len(ledgers) == 1
