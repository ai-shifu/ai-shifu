"""Protect payment reuse, historical data and retries at checkout boundaries."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout, provider_state, subscriptions
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
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
from flaskr.util.datetime import now_utc, to_utc_iso
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


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay"])
@pytest.mark.parametrize(
    "status", [BILLING_ORDER_STATUS_PENDING, BILLING_ORDER_STATUS_PAID]
)
def test_stripe_renewal_keeps_its_identity_after_provider_change(
    billing_renewal_app: Flask, provider: str, status: int
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        # November has 30 days, so both providers find the same cycle window.
        subscription = create_renewal_subscription(
            "stripe-identity",
            billing_provider="stripe",
            provider_subscription_id="sub_original",
            current_period_end_at=datetime(2026, 11, 10, 15, 59, 59),
        )
        db.session.add(subscription)
        db.session.flush()
        order = subscriptions.ensure_subscription_renewal_order(
            billing_renewal_app, subscription
        )
        order.status = status
        identity = (
            order.creator_bid,
            order.product_bid,
            order.payment_provider,
            order.provider_reference_id,
            order.currency,
            order.payable_amount,
            order.channel,
            dict(order.metadata_json),
        )
        subscription.billing_provider = provider
        product = BillingProduct.query.filter_by(product_bid=order.product_bid).one()
        product.price_amount = int(product.price_amount) + 100
        product.currency = "USD"
        again = subscriptions.ensure_subscription_renewal_order(
            billing_renewal_app, subscription, renewal_event_bid="next-event"
        )
        assert again.bill_order_bid == order.bill_order_bid
        assert (
            again.creator_bid,
            again.product_bid,
            again.payment_provider,
            again.provider_reference_id,
            again.currency,
            again.payable_amount,
            again.channel,
            {**again.metadata_json, "renewal_event_bid": None},
        ) == identity
        assert again.metadata_json["renewal_event_bid"] == "next-event"
        assert BillingOrder.query.count() == 1


@pytest.mark.parametrize(
    "status",
    [
        BILLING_ORDER_STATUS_PAID,
        BILLING_ORDER_STATUS_FAILED,
        BILLING_ORDER_STATUS_TIMEOUT,
        BILLING_ORDER_STATUS_CANCELED,
    ],
)
def test_terminal_stripe_renewal_keeps_its_amount_and_contract(
    billing_renewal_app: Flask, status: int
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        subscription = create_renewal_subscription(
            "stripe-terminal", billing_provider="stripe"
        )
        db.session.add(subscription)
        db.session.flush()
        order = subscriptions.ensure_subscription_renewal_order(
            billing_renewal_app, subscription
        )
        order.status = status
        original = (order.provider_reference_id, order.currency, order.payable_amount)
        product = BillingProduct.query.filter_by(product_bid=order.product_bid).one()
        product.price_amount = int(product.price_amount) + 100
        subscription.provider_subscription_id = "sub_replacement"
        again = subscriptions.ensure_subscription_renewal_order(
            billing_renewal_app, subscription, renewal_event_bid="retry-event"
        )
        assert again.bill_order_bid == order.bill_order_bid
        assert (again.provider_reference_id, again.currency, again.payable_amount) == (
            original
        )
        assert again.status == status
        assert again.metadata_json["renewal_event_bid"] == "retry-event"
        assert BillingOrder.query.count() == 1


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
                    # Matches the 990 payable amount of _create_manual_order.
                    "total_amount": "9.90",
                    "amount": {"total": 990},
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


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay"])
def test_closed_timed_out_trade_can_be_replaced_without_closing_again(
    billing_renewal_app: Flask, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    fake = Mock()
    fake.sync_reference.return_value = PaymentNotificationResult(
        order_bid="old-order",
        status="manual_sync",
        provider_payload={"charge": {"id": "old-attempt", "reversed": True}}
        if provider == "pingxx"
        else {
            "trade": {
                "out_trade_no": "old-attempt",
                "trade_status": "TRADE_CLOSED",
                "trade_state": "CLOSED",
            }
        },
    )
    fake.cancel_payment.return_value = PaymentCancellationResult(
        provider_reference="old-attempt", status="failed", raw_response={}
    )
    fake.create_payment.return_value = PaymentCreationResult(
        provider_reference="new-attempt", raw_response={}, extra={}
    )
    monkeypatch.setattr(checkout, "get_payment_provider", lambda _: fake)
    monkeypatch.setattr(checkout, "_credit_ledger_lock", lambda *_: nullcontext())
    monkeypatch.setattr(
        checkout, "_subscription_checkout_lock", lambda *_: nullcontext()
    )
    monkeypatch.setattr(
        checkout,
        "_resolve_billing_payment_channel",
        lambda *_args, **_kwargs: (
            provider,
            "wx_pub_qr" if provider == "wechatpay" else "alipay_qr",
        ),
    )
    with billing_renewal_app.app_context():
        with unit_of_work():
            order = _create_manual_order(provider)
            order.status = BILLING_ORDER_STATUS_TIMEOUT
        result = checkout.create_billing_subscription_checkout(
            billing_renewal_app, "owner", {"product_bid": order.product_bid}
        )
        assert result.bill_order_bid != order.bill_order_bid
        assert order.status == BILLING_ORDER_STATUS_CANCELED
        assert order.provider_reference_id == "old-attempt"
        assert BillingOrder.query.count() == 2
        assert CreditLedgerEntry.query.count() == 0
        fake.sync_reference.assert_called_once()
        fake.cancel_payment.assert_not_called()
        fake.create_payment.assert_called_once()


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay"])
@pytest.mark.parametrize(
    "advance",
    [
        "paid_order",
        "provider_update",
        "checkout_success",
        "historical_marker",
        "same_cycle_provider_update",
        "same_cycle_checkout_success",
    ],
)
def test_old_manual_payment_cannot_replace_a_later_cycle(
    billing_renewal_app: Flask, provider: str, advance: str
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        subscription = create_renewal_subscription("cycle", billing_provider=provider)
        db.session.add(subscription)
        old = _create_manual_order(provider)
        old.creator_bid = subscription.creator_bid
        old.subscription_bid = subscription.subscription_bid
        old.status = BILLING_ORDER_STATUS_PAID
        old.paid_at = now_utc() - timedelta(days=2)
        old.paid_amount = old.payable_amount
        db.session.flush()
        assert subscriptions.grant_paid_order_credits(billing_renewal_app, old)
        assert (
            subscription.metadata_json["active_cycle_order_bid"] == old.bill_order_bid
        )
        next_start = old.paid_at + timedelta(days=1)
        next_end = next_start + timedelta(days=30)
        if advance == "paid_order":
            later = BillingOrder(
                bill_order_bid="stripe-cycle",
                creator_bid=old.creator_bid,
                subscription_bid=old.subscription_bid,
                product_bid=old.product_bid,
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                payment_provider="stripe",
                currency="CNY",
                status=BILLING_ORDER_STATUS_PAID,
                payable_amount=990,
                paid_amount=990,
                paid_at=next_start,
                metadata_json={},
            )
            db.session.add(later)
            db.session.flush()
            assert subscriptions.grant_paid_order_credits(billing_renewal_app, later)
            assert "active_cycle_order_bid" not in subscription.metadata_json
        elif advance in {"provider_update", "same_cycle_provider_update"}:
            if advance == "same_cycle_provider_update":
                next_start = subscription.current_period_start_at
            provider_state._apply_billing_subscription_provider_update(
                billing_renewal_app,
                subscription,
                provider="stripe",
                event_type="customer.subscription.updated",
                payload={},
                data_object={
                    "id": "sub_stripe_cycle",
                    "status": "active",
                    "current_period_start": next_start,
                    "current_period_end": next_end,
                },
            )
            assert subscription.current_period_start_at == next_start
            assert subscription.current_period_end_at == next_end
            assert "active_cycle_order_bid" not in subscription.metadata_json
        elif advance in {"checkout_success", "same_cycle_checkout_success"}:
            provider_state._apply_subscription_checkout_success(
                billing_renewal_app,
                subscription,
                provider="stripe",
                event_type="checkout.session.completed",
                payload={"subscription": "sub_stripe_cycle"},
            )
            assert "active_cycle_order_bid" not in subscription.metadata_json
            if advance == "checkout_success":
                subscription.current_period_start_at = next_start
                subscription.current_period_end_at = next_end
        else:
            # Historical state may retain an old marker even on the same provider.
            subscription.current_period_start_at = next_start
            subscription.current_period_end_at = next_end
            subscription.last_renewed_at = next_start
        db.session.flush()
        cycle_snapshot = (
            subscription.billing_provider,
            subscription.current_period_start_at,
            subscription.current_period_end_at,
            subscription.last_renewed_at,
            dict(subscription.metadata_json),
        )
        bucket_snapshots = [
            (bucket.wallet_bucket_bid, bucket.effective_from, bucket.effective_to)
            for bucket in CreditWalletBucket.query.order_by(CreditWalletBucket.id).all()
        ]
        ledger_count = CreditLedgerEntry.query.count()
        assert not subscriptions._activate_subscription_for_paid_order(
            billing_renewal_app, old
        )
        assert not subscriptions.grant_paid_order_credits(billing_renewal_app, old)
        assert old.status == BILLING_ORDER_STATUS_PAID
        assert (
            old.metadata_json["settlement_review_reason"]
            == "newer_cycle_already_effective"
        )
        assert cycle_snapshot == (
            subscription.billing_provider,
            subscription.current_period_start_at,
            subscription.current_period_end_at,
            subscription.last_renewed_at,
            subscription.metadata_json,
        )
        assert bucket_snapshots == [
            (bucket.wallet_bucket_bid, bucket.effective_from, bucket.effective_to)
            for bucket in CreditWalletBucket.query.order_by(CreditWalletBucket.id).all()
        ]
        assert CreditLedgerEntry.query.count() == ledger_count


@pytest.mark.parametrize("old_provider", ["pingxx", "alipay", "wechatpay"])
@pytest.mark.parametrize("new_provider", ["pingxx", "alipay", "wechatpay"])
@pytest.mark.parametrize("precedence", ["paid_at", "created_at", "row_id"])
def test_same_boundary_manual_orders_keep_the_newer_paid_cycle(
    billing_renewal_app: Flask,
    old_provider: str,
    new_provider: str,
    precedence: str,
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        boundary = now_utc() - timedelta(days=2)
        subscription = create_renewal_subscription(
            "same-boundary", billing_provider=old_provider
        )
        db.session.add(subscription)
        old = _create_manual_order(old_provider)
        old.creator_bid = subscription.creator_bid
        old.subscription_bid = subscription.subscription_bid
        old.order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        old.status = BILLING_ORDER_STATUS_PAID
        old.paid_at = boundary
        old.paid_amount = old.payable_amount
        old.created_at = boundary - timedelta(days=1)
        old.metadata_json = {
            "applied_cycle_start_at": to_utc_iso(boundary),
            "applied_cycle_end_at": to_utc_iso(boundary + timedelta(days=30)),
        }
        db.session.flush()
        assert subscriptions.grant_paid_order_credits(billing_renewal_app, old)
        newer = BillingOrder(
            bill_order_bid="newer-order",
            creator_bid=old.creator_bid,
            subscription_bid=old.subscription_bid,
            product_bid="bill-product-plan-monthly-pro",
            order_type=old.order_type,
            payment_provider=new_provider,
            currency=old.currency,
            status=BILLING_ORDER_STATUS_PAID,
            payable_amount=19900,
            paid_amount=19900,
            paid_at=boundary + timedelta(minutes=1)
            if precedence == "paid_at"
            else boundary,
            created_at=old.created_at + timedelta(minutes=1)
            if precedence == "created_at"
            else old.created_at,
            metadata_json=dict(old.metadata_json),
        )
        db.session.add(newer)
        db.session.flush()
        # Same-boundary protection must still accept a legitimate newer payment.
        assert not subscriptions._is_stale_manual_cycle(newer, subscription, boundary)
        assert subscriptions.grant_paid_order_credits(billing_renewal_app, newer)
        assert subscription.product_bid == newer.product_bid
        assert subscription.billing_provider == new_provider
        assert subscription.current_period_start_at == boundary
        snapshot = (
            subscription.product_bid,
            subscription.billing_provider,
            subscription.current_period_start_at,
            subscription.current_period_end_at,
            dict(subscription.metadata_json),
        )
        buckets = [
            (b.wallet_bucket_bid, b.available_credits, b.effective_from, b.effective_to)
            for b in CreditWalletBucket.query.order_by(CreditWalletBucket.id).all()
        ]
        ledger_count = CreditLedgerEntry.query.count()
        assert not subscriptions._activate_subscription_for_paid_order(
            billing_renewal_app, old
        )
        assert not subscriptions.grant_paid_order_credits(billing_renewal_app, old)
        assert snapshot == (
            subscription.product_bid,
            subscription.billing_provider,
            subscription.current_period_start_at,
            subscription.current_period_end_at,
            subscription.metadata_json,
        )
        assert buckets == [
            (b.wallet_bucket_bid, b.available_credits, b.effective_from, b.effective_to)
            for b in CreditWalletBucket.query.order_by(CreditWalletBucket.id).all()
        ]
        assert CreditLedgerEntry.query.count() == ledger_count


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
