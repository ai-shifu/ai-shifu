"""Verify operator paid-subscription termination behavior."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_MANUAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
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
from flaskr.service.billing.provider_state import (
    can_billing_order_become_paid_from_provider,
)
from flaskr.service.billing.renewal import _is_subscription_obsolete
from flaskr.service.billing.subscriptions import grant_paid_order_credits
from flaskr.service.billing.wallets import load_or_create_credit_bucket_by_category
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
            expected_subscription_bid=subscription.subscription_bid,
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
            expected_subscription_bid=subscription.subscription_bid,
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
            expected_subscription_bid=subscription.subscription_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-zero",
            reason="customer request",
        )

        assert result["forfeited_credits"] == "0"
        dao.db.session.refresh(subscription)
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED


@pytest.mark.parametrize(
    "payable_status",
    [
        BILLING_ORDER_STATUS_PENDING,
        BILLING_ORDER_STATUS_FAILED,
        BILLING_ORDER_STATUS_TIMEOUT,
        BILLING_ORDER_STATUS_CANCELED,
    ],
)
def test_provider_payable_upgrade_blocks_operator_termination(
    billing_wallet_lifecycle_app: Flask,
    payable_status: int,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-pending-upgrade"
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-pending-upgrade",
            creator_bid=creator_bid,
            product_bid="product-current-plan",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="wechatpay",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        paid_order = BillingOrder(
            bill_order_bid="order-current-paid-plan",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="wechatpay",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=now - timedelta(days=1),
        )
        pending_upgrade = BillingOrder(
            bill_order_bid="order-pending-plan-upgrade",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            product_bid="product-upgraded-plan",
            subscription_bid=subscription.subscription_bid,
            payment_provider="wechatpay",
            status=payable_status,
        )
        dao.db.session.add_all([subscription, paid_order, pending_upgrade])
        dao.db.session.commit()

        with pytest.raises(AppError):
            terminate_operator_paid_subscription(
                billing_wallet_lifecycle_app,
                creator_bid=creator_bid,
                expected_subscription_bid=subscription.subscription_bid,
                operator_user_bid="operator-terminate",
                request_id="terminate-request-pending-upgrade",
                reason="customer request",
            )

        dao.db.session.refresh(subscription)
        dao.db.session.refresh(pending_upgrade)
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert pending_upgrade.status == payable_status


def test_replaced_canceled_order_cannot_block_operator_termination() -> None:
    replaced_order = BillingOrder(
        payment_provider="stripe",
        status=BILLING_ORDER_STATUS_CANCELED,
        metadata_json={"invalidated_reason": "replaced_by_new_package"},
    )

    assert can_billing_order_become_paid_from_provider(replaced_order) is False


def test_zero_balance_paid_bucket_does_not_forfeit_independent_reward_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-independent-reward"
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-independent-reward",
            creator_bid=creator_bid,
            product_bid="product-terminate-independent-reward",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="wechatpay",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        paid_order = BillingOrder(
            bill_order_bid="order-terminate-independent-paid",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="wechatpay",
            status=BILLING_ORDER_STATUS_PAID,
        )
        reward_order = BillingOrder(
            bill_order_bid="order-terminate-independent-reward",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid="product-referral-reward",
            subscription_bid="subscription-referral-reward",
            payment_provider="manual",
            status=BILLING_ORDER_STATUS_PAID,
            metadata_json={"referral_invitation_reward": True},
        )
        wallet = CreditWallet(
            wallet_bid="wallet-terminate-independent-reward",
            creator_bid=creator_bid,
            available_credits=Decimal(5),
            reserved_credits=0,
            lifetime_granted_credits=Decimal(15),
            lifetime_consumed_credits=Decimal(10),
            version=0,
        )
        paid_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-independent-paid",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=paid_order.bill_order_bid,
            priority=20,
            original_credits=Decimal(10),
            available_credits=0,
            reserved_credits=0,
            consumed_credits=Decimal(10),
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        reward_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-independent-reward",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=reward_order.bill_order_bid,
            priority=20,
            original_credits=Decimal(5),
            available_credits=Decimal(5),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now,
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        grants = [
            CreditLedgerEntry(
                ledger_bid=f"ledger-{order.bill_order_bid}",
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
            for order, bucket, amount in (
                (paid_order, paid_bucket, Decimal(10)),
                (reward_order, reward_bucket, Decimal(5)),
            )
        ]
        dao.db.session.add_all(
            [
                subscription,
                paid_order,
                reward_order,
                wallet,
                paid_bucket,
                reward_bucket,
                *grants,
            ]
        )
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            expected_subscription_bid=subscription.subscription_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-independent-reward",
            reason="customer request",
        )

        dao.db.session.refresh(paid_bucket)
        dao.db.session.refresh(reward_bucket)
        assert result["forfeited_credits"] == "0"
        assert paid_bucket.available_credits == Decimal(0)
        assert reward_bucket.available_credits == Decimal(5)


def test_termination_rejects_a_subscription_changed_after_confirmation(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        subscription = BillingSubscription(
            subscription_bid="subscription-current-after-dialog",
            creator_bid="creator-changed-after-dialog",
            product_bid="product-current-after-dialog",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        order = BillingOrder(
            bill_order_bid="order-current-after-dialog",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="manual",
            status=BILLING_ORDER_STATUS_PAID,
        )
        dao.db.session.add_all([subscription, order])
        dao.db.session.commit()

        with pytest.raises(AppError):
            terminate_operator_paid_subscription(
                billing_wallet_lifecycle_app,
                creator_bid=subscription.creator_bid,
                expected_subscription_bid="subscription-shown-in-old-dialog",
                operator_user_bid="operator-terminate",
                request_id="terminate-request-stale-dialog",
                reason="customer request",
            )

        dao.db.session.refresh(subscription)
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE


def test_pending_termination_bucket_is_not_reused_for_a_new_plan_grant(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        wallet = CreditWallet(
            wallet_bid="wallet-pending-termination",
            creator_bid="creator-pending-termination",
            available_credits=Decimal(5),
            reserved_credits=0,
            lifetime_granted_credits=Decimal(5),
            lifetime_consumed_credits=0,
            version=0,
        )
        old_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-pending-termination",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="old-order",
            priority=20,
            original_credits=Decimal(5),
            available_credits=Decimal(5),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={
                "operator_termination_pending_subscription_bid": "old-subscription"
            },
        )
        dao.db.session.add_all([wallet, old_bucket])
        dao.db.session.flush()

        new_bucket = load_or_create_credit_bucket_by_category(
            billing_wallet_lifecycle_app,
            wallet=wallet,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_bid="new-order",
            effective_from=now,
            effective_to=now + timedelta(days=365),
        )

        assert new_bucket.wallet_bucket_bid != old_bucket.wallet_bucket_bid
        assert old_bucket.available_credits == Decimal(5)


@pytest.mark.parametrize(
    ("status", "operation_status"),
    [
        (BILLING_SUBSCRIPTION_STATUS_TERMINATING, "prepared"),
        (BILLING_SUBSCRIPTION_STATUS_CANCELED, "terminated"),
    ],
)
def test_late_paid_event_cannot_grant_or_reactivate_operator_terminated_plan(
    billing_wallet_lifecycle_app: Flask,
    status: int,
    operation_status: str,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        subscription = BillingSubscription(
            subscription_bid=f"subscription-late-{operation_status}",
            creator_bid=f"creator-late-{operation_status}",
            product_bid="product-late-event",
            status=status,
            billing_provider="manual",
            metadata_json={
                "operator_paid_subscription_termination": {
                    "status": operation_status,
                    "request_id": f"request-{operation_status}",
                }
            },
        )
        order = BillingOrder(
            bill_order_bid=f"order-late-{operation_status}",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="manual",
            status=BILLING_ORDER_STATUS_PAID,
        )
        dao.db.session.add_all([subscription, order])
        dao.db.session.commit()

        assert grant_paid_order_credits(billing_wallet_lifecycle_app, order) is False
        dao.db.session.commit()

        dao.db.session.refresh(subscription)
        assert subscription.status == status
        assert (
            CreditLedgerEntry.query.filter_by(
                creator_bid=subscription.creator_bid
            ).count()
            == 0
        )


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
            metadata_json={},
        )
        dao.db.session.add_all([subscription, order])
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            expected_subscription_bid=subscription.subscription_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-manual",
            reason="operator correction",
        )

        assert result["provider"] == "manual"
        dao.db.session.refresh(subscription)
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED


def test_historical_manual_order_type_plan_terminates_and_forfeits_credits(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-historical-manual"
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-historical-manual",
            creator_bid=creator_bid,
            product_bid="product-terminate-historical-manual",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
        )
        competing_subscription = BillingSubscription(
            subscription_bid="subscription-terminate-competing",
            creator_bid=creator_bid,
            product_bid="product-terminate-competing",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=60),
        )
        order = BillingOrder(
            bill_order_bid="order-terminate-historical-manual",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_MANUAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="manual",
            status=BILLING_ORDER_STATUS_PAID,
            metadata_json={},
        )
        wallet = CreditWallet(
            wallet_bid="wallet-terminate-historical-manual",
            creator_bid=creator_bid,
            available_credits=Decimal(5),
            reserved_credits=0,
            lifetime_granted_credits=Decimal(5),
            lifetime_consumed_credits=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-historical-manual",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            priority=20,
            original_credits=Decimal(5),
            available_credits=Decimal(5),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        grant = CreditLedgerEntry(
            ledger_bid="ledger-terminate-historical-manual",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal(5),
            balance_after=Decimal(5),
        )
        dao.db.session.add_all(
            [subscription, competing_subscription, order, wallet, bucket, grant]
        )
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            expected_subscription_bid=subscription.subscription_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-historical-manual",
            reason="operator correction",
        )

        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        assert result["forfeited_credits"] == "5"
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert competing_subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert bucket.available_credits == Decimal(0)


@pytest.mark.parametrize(
    "mixed_metadata",
    [
        {"checkout_type": "trial_bootstrap"},
        {
            "checkout_type": "referral_invitation_reward",
            "referral_invitation_reward": True,
        },
    ],
)
def test_mixed_paid_and_active_reward_bucket_terminates_together(
    billing_wallet_lifecycle_app: Flask,
    mixed_metadata: dict[str, object],
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
        reward_order = BillingOrder(
            bill_order_bid="order-terminate-mixed-manual",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid="subscription-reward-mixed-into-paid-bucket",
            payment_provider="manual",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=now - timedelta(hours=12),
            metadata_json=mixed_metadata,
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
            source_bid=reward_order.bill_order_bid,
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
                ((paid_order, Decimal(10)), (reward_order, Decimal(2)))
            )
        ]
        dao.db.session.add_all(
            [subscription, paid_order, reward_order, wallet, bucket, *grants]
        )
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            expected_subscription_bid=subscription.subscription_bid,
            operator_user_bid="operator-terminate",
            request_id="terminate-request-mixed",
            reason="customer request",
        )

        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(wallet)
        assert result["forfeited_credits"] == "12"
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert bucket.available_credits == Decimal(0)
        assert bucket.expired_credits == Decimal(12)
        assert wallet.available_credits == Decimal(0)


def test_terminating_subscription_is_obsolete_for_renewal_worker() -> None:
    subscription = BillingSubscription(status=BILLING_SUBSCRIPTION_STATUS_TERMINATING)

    assert _is_subscription_obsolete(subscription) is True


def test_pending_termination_finishes_only_the_pinned_changed_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = "creator-terminate-stale-snapshot"
        request_id = "terminate-request-stale-snapshot"
        subscription = BillingSubscription(
            subscription_bid="subscription-terminate-stale-snapshot",
            creator_bid=creator_bid,
            product_bid="product-terminate-stale-snapshot",
            status=BILLING_SUBSCRIPTION_STATUS_TERMINATING,
            billing_provider="manual",
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=30),
            metadata_json={
                "operator_paid_subscription_termination": {
                    "request_id": request_id,
                    "status": "prepared",
                    "operator_user_bid": "operator-terminate",
                    "reason": "operator correction",
                    "paid_order_bids": ["order-terminate-stale-snapshot"],
                    "bucket_bid": "bucket-terminate-stale-snapshot",
                    "bucket_updated_at": "2000-01-01T00:00:00",
                }
            },
        )
        order = BillingOrder(
            bill_order_bid="order-terminate-stale-snapshot",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="manual",
            status=BILLING_ORDER_STATUS_PAID,
        )
        wallet = CreditWallet(
            wallet_bid="wallet-terminate-stale-snapshot",
            creator_bid=creator_bid,
            available_credits=Decimal(10),
            reserved_credits=0,
            lifetime_granted_credits=Decimal(10),
            lifetime_consumed_credits=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-terminate-stale-snapshot",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            priority=20,
            original_credits=Decimal(3),
            available_credits=Decimal(3),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            updated_at=now,
        )
        grant = CreditLedgerEntry(
            ledger_bid="ledger-terminate-stale-snapshot",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key="grant:order-terminate-stale-snapshot",
            amount=Decimal(3),
            balance_after=Decimal(3),
        )
        new_plan_subscription = BillingSubscription(
            subscription_bid="subscription-new-plan-during-termination",
            creator_bid=creator_bid,
            product_bid="product-new-plan-during-termination",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            current_period_start_at=now,
            current_period_end_at=now + timedelta(days=365),
        )
        new_plan_order = BillingOrder(
            bill_order_bid="order-new-plan-during-termination",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=new_plan_subscription.product_bid,
            subscription_bid=new_plan_subscription.subscription_bid,
            payment_provider="manual",
            status=BILLING_ORDER_STATUS_PAID,
        )
        late_paid_order = BillingOrder(
            bill_order_bid="order-late-paid-during-termination",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            payment_provider="manual",
            status=BILLING_ORDER_STATUS_PAID,
        )
        new_plan_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-new-plan-during-termination",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-new-plan-during-termination",
            priority=20,
            original_credits=Decimal(7),
            available_credits=Decimal(7),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now,
            effective_to=now + timedelta(days=365),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        new_plan_grant = CreditLedgerEntry(
            ledger_bid="ledger-new-plan-during-termination",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=new_plan_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=new_plan_order.bill_order_bid,
            idempotency_key=f"grant:{new_plan_order.bill_order_bid}",
            amount=Decimal(7),
            balance_after=Decimal(10),
        )
        dao.db.session.add_all(
            [
                subscription,
                order,
                wallet,
                bucket,
                grant,
                new_plan_subscription,
                new_plan_order,
                late_paid_order,
                new_plan_bucket,
                new_plan_grant,
            ]
        )
        dao.db.session.commit()

        result = terminate_operator_paid_subscription(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            expected_subscription_bid=subscription.subscription_bid,
            operator_user_bid="different-operator",
            request_id="different-request",
            reason="different reason",
        )

        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(new_plan_bucket)
        dao.db.session.refresh(wallet)
        assert result["forfeited_credits"] == "3"
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert bucket.available_credits == Decimal(0)
        assert new_plan_bucket.available_credits == Decimal(7)
        assert wallet.available_credits == Decimal(7)


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
        grant = CreditLedgerEntry(
            ledger_bid="ledger-terminate-reserved",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal(2),
            balance_after=Decimal(0),
        )
        dao.db.session.add_all([subscription, order, wallet, bucket, grant])
        dao.db.session.commit()

        with pytest.raises(AppError):
            terminate_operator_paid_subscription(
                billing_wallet_lifecycle_app,
                creator_bid=creator_bid,
                expected_subscription_bid=subscription.subscription_bid,
                operator_user_bid="operator-terminate",
                request_id="terminate-request-reserved",
                reason="customer request",
            )

        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(wallet)
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert bucket.available_credits == Decimal(0)
        assert bucket.reserved_credits == Decimal(2)
        assert wallet.reserved_credits == Decimal(2)
