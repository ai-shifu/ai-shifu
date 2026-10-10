"""Domestic payment migration preserves cycles, attempt identity and entitlements."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import timedelta
from itertools import product
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout, provider_state, renewal, subscriptions
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingRenewalEvent,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.billing.payment_policy import manual_payments_are_compatible
from flaskr.service.order.payment_providers.base import PaymentCreationResult
from flaskr.util.datetime import now_utc, to_utc_iso

from tests.service.billing.renewal_execution_test_helpers import (
    create_renewal_subscription,
)

if TYPE_CHECKING:
    from flask import Flask

pytest_plugins = ["tests.service.billing.renewal_execution_app_fixture"]


@pytest.mark.parametrize(
    ("old", "new"), list(product(("pingxx", "alipay", "wechatpay"), repeat=2))
)
def test_manual_payment_compatibility(old: str, new: str) -> None:
    assert manual_payments_are_compatible(old, new)


@pytest.mark.parametrize("provider", ["stripe", "manual", "", "unknown"])
def test_unsupported_payment_modes_are_not_migration_compatible(provider: str) -> None:
    assert not manual_payments_are_compatible("pingxx", provider)


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay"])
def test_manual_notification_does_not_mutate_current_entitlement(provider: str) -> None:
    subscription = create_renewal_subscription(
        "notification", billing_provider="pingxx"
    )
    subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
    subscription.cancel_at_period_end = 1
    original = (
        subscription.billing_provider,
        subscription.current_period_end_at,
        subscription.status,
    )
    for apply in (
        provider_state.apply_subscription_checkout_success,
        provider_state.apply_subscription_checkout_failure,
    ):
        assert not apply(
            Mock(), subscription, payload={}, provider=provider, event_type="payment"
        )
        assert (
            subscription.billing_provider,
            subscription.current_period_end_at,
            subscription.status,
        ) == original
        assert subscription.cancel_at_period_end == 1


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
def test_native_renewal_waits_for_payment_and_keeps_original_attempt(
    billing_renewal_app: Flask, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        subscription = create_renewal_subscription("renewal", billing_provider=provider)
        db.session.add(subscription)
        db.session.flush()
        order = subscriptions.ensure_subscription_renewal_order(
            billing_renewal_app, subscription
        )
        assert order is not None
        assert order.provider_reference_id == ""
        assert order.payment_provider == provider
        assert order.status == BILLING_ORDER_STATUS_PENDING
        assert order.metadata_json["renewal_cycle_start_at"] == to_utc_iso(
            subscription.current_period_end_at
        )
        sync = Mock(
            side_effect=AssertionError(
                "An unpaid business order cannot trigger a provider call"
            )
        )
        monkeypatch.setattr(renewal, "sync_billing_order", sync)
        assert (
            renewal._sync_billing_renewal_order(
                billing_renewal_app, order=order, event=None
            ).status
            == "pending"
        )
        order.provider_reference_id = "original-attempt"
        old_amount = order.payable_amount
        subscription.billing_provider = "pingxx"
        again = subscriptions.ensure_subscription_renewal_order(
            billing_renewal_app, subscription, renewal_event_bid="event"
        )
        assert again.bill_order_bid == order.bill_order_bid
        assert (
            again.payment_provider,
            again.provider_reference_id,
            again.payable_amount,
        ) == (provider, "original-attempt", old_amount)
        assert again.metadata_json["renewal_event_bid"] == "event"


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay"])
@pytest.mark.parametrize("timing", ["early", "boundary", "late"])
def test_manual_paid_renewal_preserves_credit_timing_and_is_idempotent(
    billing_renewal_app: Flask, provider: str, timing: str
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        now = now_utc()
        boundary = (
            now + timedelta(days=5) if timing == "early" else now - timedelta(seconds=1)
        )
        if timing == "late":
            boundary = now - timedelta(days=60)
        subscription = create_renewal_subscription(
            "paid-renewal", billing_provider="pingxx", current_period_end_at=boundary
        )
        subscription.current_period_start_at = boundary - timedelta(days=30)
        subscription.cancel_at_period_end = 1
        subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        db.session.add(subscription)
        db.session.flush()
        order = BillingOrder(
            bill_order_bid="paid-order",
            creator_bid=subscription.creator_bid,
            subscription_bid=subscription.subscription_bid,
            product_bid=subscription.product_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            payment_provider=provider,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=now,
            payable_amount=9900,
            paid_amount=9900,
            currency="CNY",
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary),
                "renewal_cycle_end_at": to_utc_iso(boundary + timedelta(days=30)),
            },
        )
        db.session.add(order)
        db.session.flush()
        assert subscriptions.grant_paid_order_credits(billing_renewal_app, order)
        assert not subscriptions.grant_paid_order_credits(billing_renewal_app, order)
        assert subscription.cancel_at_period_end == 1
        assert (
            CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count()
            == 1
        )
        bucket = CreditWalletBucket.query.filter_by(
            source_bid=order.bill_order_bid
        ).one()
        if timing == "early":
            assert subscription.current_period_end_at == boundary
            assert subscription.billing_provider == "pingxx"
            assert bucket.reserved_credits > 0
            assert bucket.available_credits == 0
        else:
            assert subscription.billing_provider == provider
            assert subscription.current_period_start_at == (
                now if timing == "late" else boundary
            )
            assert bucket.available_credits > 0
        assert (
            BillingRenewalEvent.query.filter_by(
                subscription_bid=subscription.subscription_bid
            ).count()
            > 0
        )


@pytest.mark.parametrize(
    "changed",
    ["payment_provider", "channel", "currency", "payable_amount", "preorder_order_bid"],
)
def test_checkout_reuse_requires_same_payment_and_offset_snapshot(changed: str) -> None:
    metadata = {"checkout_type": "subscription", "preorder_order_bid": "preorder"}
    order = BillingOrder(
        product_bid="product",
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        payment_provider="alipay",
        channel="alipay_qr",
        currency="CNY",
        payable_amount=100,
        campaign_bid="",
        metadata_json=metadata,
    )
    expected = {
        "product_bid": "product",
        "order_type": BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        "payment_provider": "alipay",
        "channel": "alipay_qr",
        "currency": "CNY",
        "payable_amount": 100,
        "checkout_metadata": dict(metadata),
    }
    assert checkout._is_same_subscription_checkout_target(order, **expected)
    if changed == "preorder_order_bid":
        expected["checkout_metadata"][changed] = "another-preorder"
    else:
        expected[changed] = 200 if changed == "payable_amount" else "different"
    assert not checkout._is_same_subscription_checkout_target(order, **expected)


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
def test_old_pingxx_subscription_can_preorder_using_native_provider(
    billing_renewal_app: Flask, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    with billing_renewal_app.app_context():
        subscription = create_renewal_subscription(
            "preorder", billing_provider="pingxx"
        )
        with unit_of_work():
            db.session.add(subscription)
        end_at = subscription.current_period_end_at
        monkeypatch.setattr(
            checkout, "_subscription_checkout_lock", lambda *_: nullcontext()
        )
        monkeypatch.setattr(
            checkout,
            "_resolve_billing_payment_channel",
            lambda *_args, **_kwargs: (
                provider,
                "alipay_qr" if provider == "alipay" else "wx_pub_qr",
            ),
        )
        fake = Mock()
        fake.create_payment.return_value = PaymentCreationResult(
            provider_reference="native-attempt",
            raw_response={},
            extra={"credential": {}},
        )
        monkeypatch.setattr(checkout, "get_payment_provider", lambda _: fake)
        result = checkout.create_billing_subscription_checkout(
            billing_renewal_app,
            subscription.creator_bid,
            {
                "product_bid": subscription.product_bid,
                "payment_provider": provider,
                "action": "preorder",
            },
        )
        order = BillingOrder.query.filter_by(bill_order_bid=result.bill_order_bid).one()
        assert order.payment_provider == provider
        assert subscription.billing_provider == "pingxx"
        assert subscription.current_period_end_at == end_at
        with unit_of_work():
            order.status = BILLING_ORDER_STATUS_PAID
            order.paid_at = now_utc()
            order.paid_amount = order.payable_amount
            subscriptions.grant_paid_order_credits(billing_renewal_app, order)
        assert subscription.billing_provider == "pingxx"
        assert subscription.current_period_end_at == end_at
        assert order.metadata_json["preorder_state"] == "pending_effective"
        assert (
            CreditWalletBucket.query.filter_by(source_bid=order.bill_order_bid)
            .one()
            .reserved_credits
            > 0
        )


@pytest.mark.parametrize(
    ("preorder_provider", "payment_provider"),
    list(product(("pingxx", "alipay", "wechatpay"), ("alipay", "wechatpay"))),
)
def test_paid_preorder_can_fund_native_upgrade_once(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    preorder_provider: str,
    payment_provider: str,
) -> None:
    with billing_renewal_app.app_context():
        now = now_utc()
        subscription = create_renewal_subscription(
            "upgrade",
            billing_provider="pingxx",
            product_bid="bill-product-plan-monthly-pro",
        )
        with unit_of_work():
            db.session.add(subscription)
            db.session.flush()
            preorder = BillingOrder(
                bill_order_bid="offset",
                creator_bid=subscription.creator_bid,
                subscription_bid=subscription.subscription_bid,
                product_bid="bill-product-plan-monthly",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                payment_provider=preorder_provider,
                currency="CNY",
                payable_amount=990,
                paid_amount=990,
                paid_at=now,
                status=BILLING_ORDER_STATUS_PAID,
                metadata_json={
                    "checkout_type": "subscription_preorder",
                    "preorder_state": "pending_effective",
                    "renewal_cycle_start_at": to_utc_iso(
                        subscription.current_period_end_at
                    ),
                    "renewal_cycle_end_at": to_utc_iso(
                        subscription.current_period_end_at + timedelta(days=30)
                    ),
                },
            )
            db.session.add(preorder)
            db.session.flush()
            subscriptions.grant_paid_order_credits(billing_renewal_app, preorder)
        monkeypatch.setattr(
            checkout, "_subscription_checkout_lock", lambda *_: nullcontext()
        )
        monkeypatch.setattr(
            checkout,
            "_resolve_billing_payment_channel",
            lambda *_args, **_kwargs: (
                payment_provider,
                "alipay_qr" if payment_provider == "alipay" else "wx_pub_qr",
            ),
        )
        fake = Mock()
        fake.create_payment.return_value = PaymentCreationResult(
            provider_reference="upgrade-attempt",
            raw_response={},
            extra={"credential": {}},
        )
        monkeypatch.setattr(checkout, "get_payment_provider", lambda _: fake)
        result = checkout.create_billing_subscription_checkout(
            billing_renewal_app,
            subscription.creator_bid,
            {
                "product_bid": "bill-product-plan-yearly-lite",
                "action": "upgrade_immediate",
            },
        )
        order = BillingOrder.query.filter_by(bill_order_bid=result.bill_order_bid).one()
        assert order.payable_amount == 800000 - 990
        assert preorder.metadata_json["preorder_state"] == "pending_effective"
        assert subscription.product_bid == "bill-product-plan-monthly-pro"
        with unit_of_work():
            order.status = BILLING_ORDER_STATUS_PAID
            order.paid_at = now_utc()
            order.paid_amount = order.payable_amount
            assert subscriptions.grant_paid_order_credits(billing_renewal_app, order)
            assert not subscriptions.grant_paid_order_credits(
                billing_renewal_app, order
            )
        assert preorder.payment_provider == preorder_provider
        assert preorder.metadata_json["preorder_state"] == "absorbed_by_upgrade"
        assert subscription.product_bid == "bill-product-plan-yearly-lite"
        assert subscription.billing_provider == payment_provider
        preorder_grant = CreditLedgerEntry.query.filter_by(
            source_bid=preorder.bill_order_bid
        ).one()
        assert (
            CreditWalletBucket.query.filter_by(
                wallet_bucket_bid=preorder_grant.wallet_bucket_bid
            )
            .one()
            .reserved_credits
            == 0
        )
        assert (
            CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count()
            == 1
        )


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
def test_expired_preorder_offset_is_recorded_for_settlement_review(
    billing_renewal_app: Flask, provider: str
) -> None:
    from flaskr.service.billing.consts import BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE

    with billing_renewal_app.app_context(), unit_of_work():
        subscription = create_renewal_subscription(
            "conflict", billing_provider="pingxx"
        )
        db.session.add(subscription)
        db.session.flush()
        order = BillingOrder(
            bill_order_bid="conflicting-upgrade",
            creator_bid=subscription.creator_bid,
            subscription_bid=subscription.subscription_bid,
            product_bid="bill-product-plan-yearly-lite",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            payment_provider=provider,
            currency="CNY",
            payable_amount=799010,
            paid_amount=799010,
            paid_at=now_utc(),
            status=BILLING_ORDER_STATUS_PAID,
            metadata_json={
                "prepaid_offset_amount": 990,
                "preorder_order_bid": "already-effective",
            },
        )
        db.session.add(order)
        db.session.flush()
        old_product = subscription.product_bid
        assert not subscriptions.grant_paid_order_credits(billing_renewal_app, order)
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert (
            order.metadata_json["settlement_review_reason"]
            == "preorder_offset_no_longer_available"
        )
        assert subscription.product_bid == old_product
        assert (
            CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count()
            == 0
        )


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
def test_old_paid_notification_cannot_replace_new_cycle(
    billing_renewal_app: Flask, provider: str
) -> None:
    with billing_renewal_app.app_context(), unit_of_work():
        subscription = create_renewal_subscription(
            "new-cycle", billing_provider=provider
        )
        subscription.current_period_start_at = now_utc()
        db.session.add(subscription)
        order = BillingOrder(
            bill_order_bid="old-paid",
            creator_bid=subscription.creator_bid,
            subscription_bid=subscription.subscription_bid,
            product_bid=subscription.product_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            payment_provider="pingxx",
            currency="CNY",
            payable_amount=990,
            paid_amount=990,
            paid_at=now_utc() - timedelta(days=5),
            status=BILLING_ORDER_STATUS_PAID,
            metadata_json={},
        )
        db.session.add(order)
        db.session.flush()
        assert not subscriptions.grant_paid_order_credits(billing_renewal_app, order)
        assert subscription.billing_provider == provider
        assert order.payment_provider == "pingxx"
        assert (
            order.metadata_json["settlement_review_reason"]
            == "newer_cycle_already_effective"
        )
        assert (
            CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count()
            == 0
        )


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay"])
@pytest.mark.parametrize(
    "outcome", ["closed", "already_paid", "close_failed", "unknown_after_close"]
)
def test_replacement_requires_confirmed_closure_and_preserves_paid_orders(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    outcome: str,
) -> None:
    from flaskr.dao.uow import in_unit_of_work
    from flaskr.service.billing.consts import BILLING_ORDER_STATUS_CANCELED
    from flaskr.service.common.models import AppError
    from flaskr.service.order.payment_providers.base import (
        PaymentCancellationResult,
        PaymentNotificationResult,
    )

    closed = False
    cancel_calls = []

    def sync_reference(**_kwargs: object) -> PaymentNotificationResult:
        paid = outcome == "already_paid"
        confirmed = closed and outcome != "unknown_after_close"
        if provider == "pingxx":
            payload = {
                "charge": {"id": "old-attempt", "paid": paid, "reversed": confirmed}
            }
        else:
            trade = {"out_trade_no": "old-attempt"}
            if provider == "alipay":
                trade["trade_status"] = (
                    "TRADE_SUCCESS"
                    if paid
                    else "TRADE_CLOSED"
                    if confirmed
                    else "WAIT_BUYER_PAY"
                )
            else:
                trade["trade_state"] = (
                    "SUCCESS" if paid else "CLOSED" if confirmed else "NOTPAY"
                )
            payload = {"trade": trade}
        return PaymentNotificationResult(
            order_bid="old-order",
            status="manual_sync",
            provider_payload=payload,
            charge_id="old-attempt",
        )

    def cancel_payment(**_kwargs: object) -> PaymentCancellationResult:
        nonlocal closed
        assert not in_unit_of_work()
        cancel_calls.append(1)
        if outcome == "close_failed":
            message = "Provider close failed"
            raise RuntimeError(message)
        closed = True
        return PaymentCancellationResult(
            provider_reference="old-attempt", raw_response={}, status="cancelled"
        )

    with billing_renewal_app.app_context():
        with unit_of_work():
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
                metadata_json={},
            )
            db.session.add(order)
        fake = Mock()
        fake.sync_reference.side_effect = sync_reference
        fake.cancel_payment.side_effect = cancel_payment
        monkeypatch.setattr(checkout, "get_payment_provider", lambda _: fake)
        monkeypatch.setattr(checkout, "_credit_ledger_lock", lambda *_: nullcontext())
        if outcome == "closed":
            checkout._close_manual_payment_before_replacement(
                billing_renewal_app, "owner", "old-order"
            )
            assert order.status == BILLING_ORDER_STATUS_CANCELED
        else:
            with pytest.raises((AppError, RuntimeError)):
                checkout._close_manual_payment_before_replacement(
                    billing_renewal_app, "owner", "old-order"
                )
            assert order.status == (
                BILLING_ORDER_STATUS_PAID
                if outcome == "already_paid"
                else BILLING_ORDER_STATUS_PENDING
            )
        assert len(cancel_calls) == (0 if outcome == "already_paid" else 1)
        assert order.payment_provider == provider
        assert order.provider_reference_id == "old-attempt"
        assert BillingOrder.query.count() == 1


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
def test_repeated_native_checkout_reuses_credential_and_original_subscription(
    billing_renewal_app: Flask, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    from flaskr.service.billing.models import BillingSubscription

    channel = "alipay_qr" if provider == "alipay" else "wx_pub_qr"
    with billing_renewal_app.app_context():
        monkeypatch.setattr(
            checkout, "_subscription_checkout_lock", lambda *_: nullcontext()
        )
        monkeypatch.setattr(
            checkout,
            "_resolve_billing_payment_channel",
            lambda *_args, **_kwargs: (provider, channel),
        )
        fake = Mock()
        fake.create_payment.return_value = PaymentCreationResult(
            provider_reference="one-attempt",
            raw_response={},
            extra={"credential": {channel: "https://payments.test/qr"}},
        )
        monkeypatch.setattr(checkout, "get_payment_provider", lambda _: fake)
        payload = {"product_bid": "bill-product-plan-monthly"}
        first = checkout.create_billing_subscription_checkout(
            billing_renewal_app, "owner", payload
        )
        second = checkout.create_billing_subscription_checkout(
            billing_renewal_app, "owner", payload
        )
        assert second.bill_order_bid == first.bill_order_bid
        assert second.payment_payload == first.payment_payload
        assert second.reused_existing_order
        assert fake.create_payment.call_count == 1
        assert BillingSubscription.query.filter_by(creator_bid="owner").count() == 1
        assert BillingOrder.query.filter_by(creator_bid="owner").count() == 1


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay"])
def test_reopening_attempt_without_stored_credential_creates_new_order_after_close(
    billing_renewal_app: Flask, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    from flaskr.service.billing.consts import BILLING_ORDER_STATUS_CANCELED
    from flaskr.service.order.payment_providers.base import (
        PaymentCancellationResult,
        PaymentNotificationResult,
    )

    closed = False

    def cancel_payment(**_kwargs: object) -> PaymentCancellationResult:
        nonlocal closed
        closed = True
        return PaymentCancellationResult(
            provider_reference="old-attempt", raw_response={}, status="cancelled"
        )

    def sync_reference(**_kwargs: object) -> PaymentNotificationResult:
        if provider == "pingxx":
            payload = {
                "charge": {"id": "old-attempt", "paid": False, "reversed": closed}
            }
        else:
            payload = {
                "trade": {
                    "out_trade_no": "old-attempt",
                    "trade_status": "TRADE_CLOSED" if closed else "WAIT_BUYER_PAY",
                    "trade_state": "CLOSED" if closed else "NOTPAY",
                }
            }
        return PaymentNotificationResult(
            order_bid="old-order",
            status="manual_sync",
            provider_payload=payload,
            charge_id="old-attempt",
        )

    with billing_renewal_app.app_context():
        channel = "wx_pub_qr" if provider == "wechatpay" else "alipay_qr"
        with unit_of_work():
            old = BillingOrder(
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
                expires_at=now_utc() + timedelta(minutes=30),
                metadata_json={"checkout_type": "subscription"},
            )
            db.session.add(old)
        fake = Mock()
        fake.sync_reference.side_effect = sync_reference
        fake.cancel_payment.side_effect = cancel_payment
        fake.create_payment.return_value = PaymentCreationResult(
            provider_reference="new-attempt",
            raw_response={},
            extra={"credential": {channel: "https://payments.test/new-qr"}},
        )
        monkeypatch.setattr(checkout, "get_payment_provider", lambda _: fake)
        monkeypatch.setattr(checkout, "_credit_ledger_lock", lambda *_: nullcontext())
        monkeypatch.setattr(
            checkout, "_subscription_checkout_lock", lambda *_: nullcontext()
        )
        result = checkout.create_billing_order_checkout(
            billing_renewal_app, "owner", old.bill_order_bid, {"channel": channel}
        )
        assert closed
        assert result.bill_order_bid != old.bill_order_bid
        assert old.status == BILLING_ORDER_STATUS_CANCELED
        assert old.provider_reference_id == "old-attempt"
        new = BillingOrder.query.filter_by(bill_order_bid=result.bill_order_bid).one()
        assert new.provider_reference_id == "new-attempt"
        assert new.payable_amount == old.payable_amount
        assert new.payment_provider == old.payment_provider
        assert new.metadata_json["replaces_bill_order_bid"] == old.bill_order_bid
        assert old.metadata_json["replaced_by_bill_order_bid"] == new.bill_order_bid
