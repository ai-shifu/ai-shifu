"""Protect payment reuse, historical data and retries at checkout boundaries."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout, subscriptions
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppError
from flaskr.service.order.payment_providers.base import (
    PaymentCancellationResult,
    PaymentCreationResult,
    PaymentNotificationResult,
)
from flaskr.util.datetime import now_utc
from sqlalchemy import update

from tests.service.billing.renewal_execution_test_helpers import (
    create_renewal_subscription,
)

if TYPE_CHECKING:
    from flask import Flask

pytest_plugins = ["tests.service.billing.renewal_execution_app_fixture"]


@pytest.mark.parametrize("provider", [" Pingxx ", "Alipay", "WeChatPay"])
def test_historical_provider_names_create_usable_renewals(
    billing_renewal_app: Flask, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        subscription = create_renewal_subscription("case", billing_provider=provider)
        db.session.add(subscription)
        db.session.flush()
        order = subscriptions.ensure_subscription_renewal_order(
            billing_renewal_app, subscription
        )
        assert order.payment_provider == provider.strip().lower()
        assert subscription.billing_provider == provider
        creator_bid = subscription.creator_bid
        bill_order_bid = order.bill_order_bid
    monkeypatch.setattr(checkout, "_credit_ledger_lock", lambda *_: nullcontext())
    result = checkout.sync_billing_order(
        billing_renewal_app, creator_bid, bill_order_bid, {}
    )
    assert result.status == "pending"


def test_closure_retry_stops_when_same_order_reappears(
    billing_renewal_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checkout, "_subscription_checkout_lock", lambda *_: nullcontext()
    )
    monkeypatch.setattr(
        checkout,
        "_resolve_billing_payment_channel",
        lambda *_args, **_kwargs: ("alipay", "alipay_qr"),
    )
    prepare = Mock(side_effect=checkout._ManualPaymentNeedsClosureError("old-order"))
    close = Mock()
    monkeypatch.setattr(checkout, "_prepare_subscription_checkout", prepare)
    monkeypatch.setattr(checkout, "_close_manual_payment_before_replacement", close)
    with pytest.raises(AppError):
        checkout.create_billing_subscription_checkout(
            billing_renewal_app, "owner", {"product_bid": "bill-product-plan-monthly"}
        )
    assert prepare.call_count == 2
    close.assert_called_once_with(billing_renewal_app, "owner", "old-order")


def _create_manual_order(
    provider: str, *, saved_credential: bool = True
) -> BillingOrder:
    channel = "wx_pub_qr" if provider == "wechatpay" else "alipay_qr"
    order = BillingOrder(
        bill_order_bid="old-order",
        creator_bid="owner",
        product_bid="bill-product-plan-monthly",
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        payment_provider=provider,
        currency="CNY",
        status=BILLING_ORDER_STATUS_PENDING,
        payable_amount=990,
        provider_reference_id="old-attempt",
        channel=channel,
        created_at=now_utc() - timedelta(minutes=20),
        expires_at=now_utc() + timedelta(minutes=10),
        metadata_json={
            "provider_extra": {"credential": {channel: "https://payments.test/old"}}
        }
        if saved_credential
        else {},
    )
    db.session.add(order)
    return order


@pytest.mark.parametrize("metadata", [None, ["legacy"], "legacy", 1])
def test_replacement_handles_non_object_historical_metadata(
    billing_renewal_app: Flask, monkeypatch: pytest.MonkeyPatch, metadata: object
) -> None:
    with billing_renewal_app.app_context():
        with unit_of_work():
            order = _create_manual_order("alipay", saved_credential=False)
            order.metadata_json = metadata

        def close(*_args: object) -> None:
            with unit_of_work():
                order.status = BILLING_ORDER_STATUS_CANCELED
                db.session.add(order)

        monkeypatch.setattr(checkout, "_close_manual_payment_before_replacement", close)
        prepared = checkout._prepare_existing_billing_order_checkout(
            billing_renewal_app,
            creator_bid="owner",
            bill_order_bid=order.bill_order_bid,
            product_bid=order.product_bid,
        )
        new = BillingOrder.query.filter_by(bill_order_bid=prepared.bill_order_bid).one()
        assert new.bill_order_bid != order.bill_order_bid
        assert new.metadata_json["replaces_bill_order_bid"] == order.bill_order_bid
        assert order.metadata_json["replaced_by_bill_order_bid"] == new.bill_order_bid
        assert order.provider_reference_id == "old-attempt"


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
@pytest.mark.parametrize(
    "provider_state", ["open", "closed", "paid", "unknown", "query_error"]
)
def test_saved_native_credential_is_reconciled_before_reuse(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    provider_state: str,
) -> None:
    states = {
        "open": ("WAIT_BUYER_PAY", "NOTPAY"),
        "closed": ("TRADE_CLOSED", "CLOSED"),
        "paid": ("TRADE_SUCCESS", "SUCCESS"),
        "unknown": ("UNKNOWN", "UNKNOWN"),
    }

    def sync(**_kwargs: object) -> PaymentNotificationResult:
        if provider_state == "query_error":
            message = "Provider unavailable"
            raise RuntimeError(message)
        alipay_state, wechat_state = states[provider_state]
        return PaymentNotificationResult(
            order_bid="old-order",
            status="manual_sync",
            provider_payload={
                "trade": {
                    "out_trade_no": "old-attempt",
                    "trade_status": alipay_state,
                    "trade_state": wechat_state,
                }
            },
        )

    fake = Mock()
    fake.sync_reference.side_effect = sync
    fake.cancel_payment.return_value = PaymentCancellationResult(
        provider_reference="old-attempt", status="failed", raw_response={}
    )
    fake.create_payment.return_value = PaymentCreationResult(
        provider_reference="new-attempt",
        raw_response={},
        extra={
            "credential": {
                "alipay_qr"
                if provider == "alipay"
                else "wx_pub_qr": "https://payments.test/new"
            }
        },
    )
    monkeypatch.setattr(checkout, "get_payment_provider", lambda _: fake)
    monkeypatch.setattr(checkout, "_credit_ledger_lock", lambda *_: nullcontext())
    monkeypatch.setattr(
        checkout, "_subscription_checkout_lock", lambda *_: nullcontext()
    )
    with billing_renewal_app.app_context():
        with unit_of_work():
            order = _create_manual_order(provider)
        if provider_state in {"paid", "unknown", "query_error"}:
            with pytest.raises(
                RuntimeError if provider_state == "query_error" else AppError
            ):
                checkout.create_billing_order_checkout(
                    billing_renewal_app, "owner", order.bill_order_bid, {}
                )
            fake.create_payment.assert_not_called()
            assert BillingOrder.query.count() == 1
            assert order.status == (
                BILLING_ORDER_STATUS_PAID
                if provider_state == "paid"
                else BILLING_ORDER_STATUS_PENDING
            )
            assert CreditLedgerEntry.query.filter_by(
                source_bid=order.bill_order_bid
            ).count() == (1 if provider_state == "paid" else 0)
        else:
            result = checkout.create_billing_order_checkout(
                billing_renewal_app, "owner", order.bill_order_bid, {}
            )
            if provider_state == "open":
                assert result.bill_order_bid == order.bill_order_bid
                fake.create_payment.assert_not_called()
            else:
                assert result.bill_order_bid != order.bill_order_bid
                assert order.status == BILLING_ORDER_STATUS_CANCELED
                fake.create_payment.assert_called_once()
            fake.cancel_payment.assert_not_called()
        assert order.provider_reference_id == "old-attempt"
        assert fake.sync_reference.call_count > 0
        if provider_state != "paid":
            assert CreditWalletBucket.query.count() == 0


@pytest.mark.parametrize("advanced_state", ["subscription", "preorder"])
def test_paid_upgrade_reloads_state_before_spending_preorder_offset(
    billing_renewal_app: Flask, advanced_state: str
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        subscription = create_renewal_subscription("cached", billing_provider="pingxx")
        db.session.add(subscription)
        db.session.flush()
        preorder = BillingOrder(
            bill_order_bid="prepaid",
            creator_bid=subscription.creator_bid,
            subscription_bid=subscription.subscription_bid,
            product_bid=subscription.product_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            payment_provider="pingxx",
            currency="CNY",
            status=BILLING_ORDER_STATUS_PAID,
            paid_amount=990,
            metadata_json={
                "checkout_type": "subscription_preorder",
                "preorder_state": "pending_effective",
            },
        )
        upgrade = BillingOrder(
            bill_order_bid="upgrade",
            creator_bid=subscription.creator_bid,
            subscription_bid=subscription.subscription_bid,
            product_bid="bill-product-plan-yearly-lite",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            payment_provider="alipay",
            currency="CNY",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=now_utc(),
            payable_amount=800000 - 990,
            paid_amount=800000 - 990,
            metadata_json={
                "preorder_order_bid": "prepaid",
                "prepaid_offset_amount": 990,
            },
        )
        db.session.add_all([preorder, upgrade])
        db.session.flush()
        # Represent a boundary worker's newer persisted state while the ORM
        # still holds snapshots read before acquiring the settlement row lock.
        if advanced_state == "subscription":
            db.session.execute(
                update(BillingSubscription)
                .where(BillingSubscription.id == subscription.id)
                .values(
                    current_period_start_at=now_utc(),
                    metadata_json={"active_cycle_order_bid": "boundary-order"},
                )
                .execution_options(synchronize_session=False)
            )
            reason = "newer_cycle_already_effective"
        else:
            db.session.execute(
                update(BillingOrder)
                .where(BillingOrder.id == preorder.id)
                .values(
                    metadata_json={
                        "checkout_type": "subscription_preorder",
                        "preorder_state": "effective_applied",
                    }
                )
                .execution_options(synchronize_session=False)
            )
            reason = "preorder_offset_no_longer_available"
        assert not subscriptions.grant_paid_order_credits(billing_renewal_app, upgrade)
        assert upgrade.status == BILLING_ORDER_STATUS_PAID
        assert upgrade.metadata_json["settlement_review_reason"] == reason
        assert subscription.billing_provider == "pingxx"
        assert CreditLedgerEntry.query.count() == 0
        assert CreditWalletBucket.query.count() == 0
