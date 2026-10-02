"""Verify operator paid-subscription termination behavior."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_TERMINATING,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.operator_subscription_termination import (
    terminate_operator_paid_subscription,
)
from flaskr.service.billing.renewal import _is_subscription_obsolete
from flaskr.service.common.models import AppError
from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    from flask import Flask

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


def test_domestic_paid_plan_termination_preserves_manual_and_topup_credits(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-domestic"
        wallet = CreditWallet(
            wallet_bid="wallet-terminate-domestic",
            creator_bid=creator_bid,
            available_credits=Decimal(16),
            reserved_credits=0,
            lifetime_granted_credits=Decimal(16),
            lifetime_consumed_credits=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-domestic",
            creator_bid=creator_bid,
            product_bid="product-terminate-domestic",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        order = BillingOrder(
            bill_order_bid="order-terminate-domestic",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="pingxx",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=now - timedelta(days=1),
        )
        paid_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-paid",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            priority=20,
            original_credits=Decimal(10),
            available_credits=Decimal(10),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        manual_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-manual",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid="manual-plan-grant",
            priority=20,
            original_credits=Decimal(2),
            available_credits=Decimal(2),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        topup_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-topup",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="topup-order",
            priority=30,
            original_credits=Decimal(4),
            available_credits=Decimal(4),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        grant = CreditLedgerEntry(
            ledger_bid="ledger-terminate-paid-grant",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=paid_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal(10),
            balance_after=Decimal(10),
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                order,
                paid_bucket,
                manual_bucket,
                topup_bucket,
                grant,
            ]
        )
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-1",
            reason="customer request",
        )

        dao.db.session.refresh(subscription)
        dao.db.session.refresh(paid_bucket)
        dao.db.session.refresh(manual_bucket)
        dao.db.session.refresh(topup_bucket)
        assert result["status"] == "terminated"
        assert result["forfeited_credits"] == "10"
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert paid_bucket.available_credits == Decimal(0)
        assert paid_bucket.expired_credits == Decimal(10)
        assert manual_bucket.available_credits == Decimal(2)
        assert topup_bucket.available_credits == Decimal(4)
        assert (
            CreditLedgerEntry.query.filter_by(
                creator_bid=creator_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                idempotency_key="operator_subscription_termination:terminate-request-1",
            ).count()
            == 1
        )

        replay = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-1",
            reason="customer request",
        )
        assert replay["replayed"] is True


def test_zero_balance_paid_plan_still_terminates(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-zero"
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-zero",
            creator_bid=creator_bid,
            product_bid="product-terminate-zero",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="wechatpay",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        order = BillingOrder(
            bill_order_bid="order-terminate-zero",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="wechatpay",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=now - timedelta(days=1),
        )
        dao.db.session.add_all([subscription, order])
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-zero",
            reason="customer request",
        )

        assert result["forfeited_credits"] == "0"
        dao.db.session.refresh(subscription)
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED


def test_zero_balance_manual_plan_still_terminates(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-manual"
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-manual",
            creator_bid=creator_bid,
            product_bid="product-terminate-manual",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        order = BillingOrder(
            bill_order_bid="order-terminate-manual",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="manual",
            provider_reference_id="",
            status=BILLING_ORDER_STATUS_PAID,
            metadata_json={
                "checkout_type": "manual_grant",
                "manual_grant": True,
                "manual_grant_source": "cli",
            },
        )
        dao.db.session.add_all([subscription, order])
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-manual",
            reason="operator correction",
        )

        assert result["provider"] == "manual"
        dao.db.session.refresh(subscription)
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED


def test_mixed_paid_and_manual_plan_bucket_terminates_together(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-mixed"
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-mixed",
            creator_bid=creator_bid,
            product_bid="product-terminate-mixed",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="alipay",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        paid_order = BillingOrder(
            bill_order_bid="order-terminate-mixed-paid",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="alipay",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=now - timedelta(days=1),
        )
        manual_order = BillingOrder(
            bill_order_bid="order-terminate-mixed-manual",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="manual",
            provider_reference_id="admin-plan-grant:manual",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=now - timedelta(hours=12),
        )
        wallet = CreditWallet(
            wallet_bid="wallet-terminate-mixed",
            creator_bid=creator_bid,
            available_credits=Decimal(12),
            reserved_credits=0,
            lifetime_granted_credits=Decimal(12),
            lifetime_consumed_credits=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-mixed",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=manual_order.bill_order_bid,
            priority=20,
            original_credits=Decimal(12),
            available_credits=Decimal(12),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        grants = [
            CreditLedgerEntry(
                ledger_bid=f"ledger-terminate-mixed-{index}",
                creator_bid=creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=order.bill_order_bid,
                idempotency_key=f"grant:{order.bill_order_bid}",
                amount=amount,
                balance_after=amount,
            )
            for index, (order, amount) in enumerate(
                ((paid_order, Decimal(10)), (manual_order, Decimal(2)))
            )
        ]
        dao.db.session.add_all(
            [subscription, paid_order, manual_order, wallet, bucket, *grants]
        )
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-mixed",
            reason="customer request",
        )

        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        assert result["forfeited_credits"] == "12"
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert bucket.available_credits == Decimal(0)


def test_terminating_subscription_is_obsolete_for_renewal_worker() -> None:
    subscription = BillingSubscription(status=BILLING_SUBSCRIPTION_STATUS_TERMINATING)

    assert _is_subscription_obsolete(subscription) is True


def test_reserved_balance_rejects_without_changing_subscription(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-reserved"
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-reserved",
            creator_bid=creator_bid,
            product_bid="product-terminate-reserved",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="alipay",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        order = BillingOrder(
            bill_order_bid="order-terminate-reserved",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="alipay",
            status=BILLING_ORDER_STATUS_PAID,
        )
        wallet = CreditWallet(
            wallet_bid="wallet-terminate-reserved",
            creator_bid=creator_bid,
            available_credits=0,
            reserved_credits=Decimal(2),
            lifetime_granted_credits=Decimal(2),
            lifetime_consumed_credits=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-reserved",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            priority=20,
            original_credits=Decimal(2),
            available_credits=0,
            reserved_credits=Decimal(2),
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        dao.db.session.add_all([subscription, order, wallet, bucket])
        dao.db.session.commit()

        with pytest.raises(AppError):
            terminate_operator_paid_subscription(
                billing_wallet_lifecycle_app,
                creator_bid=creator_bid,
                operator_user_bid="operator-terminate",
                request_id="terminate-request-reserved",
                reason="customer request",
            )

        dao.db.session.refresh(subscription)
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
