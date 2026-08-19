from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing import renewal as billing_renewal
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.primitives import normalize_mysql_datetime
from flaskr.service.billing.renewal import (
    run_billing_renewal_event,
)
from flaskr.service.billing.subscriptions import (
    ensure_subscription_renewal_order,
)
from flaskr.util.datetime import now_utc
from tests.service.billing.renewal_execution_test_helpers import (
    create_credit_wallet,
    create_renewal_event,
    create_renewal_subscription,
    self_managed_cycle_end_after_boundary,
)

pytest_plugins = ["tests.service.billing.renewal_execution_app_fixture"]


def test_run_billing_renewal_event_applies_downgrade_and_reschedules_renewal(
    billing_renewal_app: Flask,
) -> None:
    next_period_end = now_utc() + timedelta(days=30)
    with billing_renewal_app.app_context():
        subscription = create_renewal_subscription(
            "sub-downgrade-1",
            product_bid="bill-product-plan-yearly",
            next_product_bid="bill-product-plan-monthly",
            current_period_end_at=next_period_end,
        )
        event = create_renewal_event(
            "renewal-downgrade-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-downgrade-1",
    )

    assert payload["status"] == "applied"
    assert payload["product_bid"] == "bill-product-plan-monthly"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-downgrade-1"
        ).one()
        renewal_event = BillingRenewalEvent.query.filter_by(
            subscription_bid="sub-downgrade-1",
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        ).one()
        assert subscription.product_bid == "bill-product-plan-monthly"
        assert subscription.next_product_bid == ""
        assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
        assert renewal_event.scheduled_at == normalize_mysql_datetime(next_period_end)


def test_run_billing_downgrade_event_applies_paid_preorder_with_referral_reward(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_cycle_start = now_utc() - timedelta(days=35)
    preorder_snapshot_cycle_end = now_utc() - timedelta(days=5)
    current_cycle_end = now_utc() - timedelta(minutes=1)
    preorder_snapshot_next_cycle_end = self_managed_cycle_end_after_boundary(
        preorder_snapshot_cycle_end
    )
    next_cycle_end = self_managed_cycle_end_after_boundary(current_cycle_end)

    with billing_renewal_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="sub-preorder-downgrade",
            creator_bid="creator-renewal-1",
            product_bid="bill-product-plan-monthly-pro",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            provider_subscription_id="",
            provider_customer_id="customer-sub-preorder-downgrade",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
            cancel_at_period_end=0,
            next_product_bid="bill-product-plan-monthly",
            metadata_json={"preorder_order_bid": "bill-preorder-downgrade-1"},
            created_at=current_cycle_start,
            updated_at=current_cycle_start,
        )
        order = BillingOrder(
            bill_order_bid="bill-preorder-downgrade-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid="bill-product-plan-monthly",
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=990,
            paid_amount=990,
            payment_provider="pingxx",
            channel="alipay_qr",
            provider_reference_id="ch_preorder_downgrade_1",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=preorder_snapshot_cycle_end - timedelta(days=5),
            metadata_json={
                "checkout_type": "subscription_preorder",
                "preorder_state": "pending_effective",
                "provider_reference_type": "charge",
                "preorder_effective_at": preorder_snapshot_cycle_end.isoformat(),
                "renewal_cycle_start_at": preorder_snapshot_cycle_end.isoformat(),
                "renewal_cycle_end_at": preorder_snapshot_next_cycle_end.isoformat(),
            },
        )
        referral_order = BillingOrder(
            bill_order_bid="bill-referral-downgrade-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid="bill-product-plan-monthly-pro",
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="referral_invitation_reward",
            provider_reference_id="referral_reward_downgrade_1",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_end - timedelta(days=4),
            metadata_json={
                "checkout_type": "referral_invitation_reward",
                "referral_invitation_reward": True,
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
            created_at=current_cycle_end - timedelta(days=4),
            updated_at=current_cycle_end - timedelta(days=4),
        )
        event = create_renewal_event(
            "renewal-preorder-downgrade-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            scheduled_at=current_cycle_end,
        )
        wallet = create_credit_wallet(
            subscription.creator_bid,
            available_credits="3.0000000000",
            lifetime_granted_credits="105.0000000000",
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.add(referral_order)
        dao.db.session.add(wallet)
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-preorder-downgrade-1",
                wallet_bid=wallet.wallet_bid,
                creator_bid=subscription.creator_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-current-cycle-preorder-downgrade",
                priority=20,
                original_credits=Decimal("1105.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("1005.0000000000"),
                consumed_credits=Decimal("97.0000000000"),
                expired_credits=Decimal("0"),
                effective_from=current_cycle_start,
                effective_to=current_cycle_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-current-cycle-preorder-downgrade",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-preorder-downgrade-1",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-preorder-downgrade-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-preorder-downgrade-1",
                idempotency_key="grant:bill-preorder-downgrade-1",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("3.0000000000"),
                expires_at=preorder_snapshot_next_cycle_end,
                consumable_from=preorder_snapshot_cycle_end,
                metadata_json={
                    "bill_order_bid": "bill-preorder-downgrade-1",
                    "subscription_bid": "sub-preorder-downgrade",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "pingxx",
                    "grant_reason": "subscription_renewal",
                    "bucket_credit_state": "reserved",
                    "reserved_until": preorder_snapshot_cycle_end.isoformat(),
                },
                created_at=preorder_snapshot_cycle_end - timedelta(days=5),
                updated_at=preorder_snapshot_cycle_end - timedelta(days=5),
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-referral-downgrade-1",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-preorder-downgrade-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-referral-downgrade-1",
                idempotency_key="grant:bill-referral-downgrade-1",
                amount=Decimal("1000.0000000000"),
                balance_after=Decimal("3.0000000000"),
                expires_at=next_cycle_end,
                consumable_from=current_cycle_end,
                metadata_json={
                    "bill_order_bid": "bill-referral-downgrade-1",
                    "subscription_bid": "sub-preorder-downgrade",
                    "product_bid": "bill-product-plan-monthly-pro",
                    "payment_provider": "manual",
                    "grant_reason": "referral_invitation_reward",
                    "bucket_credit_state": "reserved",
                    "reserved_until": current_cycle_end.isoformat(),
                },
                created_at=current_cycle_end - timedelta(days=4),
                updated_at=current_cycle_end - timedelta(days=4),
            )
        )
        dao.db.session.add(event)
        dao.db.session.commit()

    staged_notifications: list[tuple[str, str, bool, bool]] = []
    enqueued_notifications: list[str] = []

    def fake_stage_credit_granted_notification_for_order(
        app: Flask,
        *,
        creator_bid: str,
        bill_order_bid: str,
        commit: bool,
        enqueue: bool,
    ) -> dict[str, str]:
        del app
        staged_notifications.append((creator_bid, bill_order_bid, commit, enqueue))
        return {"status": "pending", "notification_bid": "notif-preorder-release"}

    def fake_enqueue_credit_notification(
        app: Flask,
        *,
        notification_bid: str,
    ) -> dict[str, bool]:
        del app
        enqueued_notifications.append(notification_bid)
        return {"enqueued": True}

    monkeypatch.setattr(
        billing_renewal,
        "_stage_credit_granted_notification_for_order",
        fake_stage_credit_granted_notification_for_order,
        raising=False,
    )
    monkeypatch.setattr(
        billing_renewal,
        "_enqueue_credit_notification",
        fake_enqueue_credit_notification,
        raising=False,
    )

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-preorder-downgrade-1",
    )

    assert payload["status"] == "applied"
    assert payload["bill_order_bid"] == "bill-preorder-downgrade-1"
    assert payload["product_bid"] == "bill-product-plan-monthly"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-preorder-downgrade"
        ).one()
        order = BillingOrder.query.filter_by(
            bill_order_bid="bill-preorder-downgrade-1"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid=subscription.creator_bid
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-preorder-downgrade-1"
        ).one()
        grant_entry = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-preorder-downgrade-1"
        ).one()
        referral_grant_entry = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-referral-downgrade-1"
        ).one()
        expire_entry = CreditLedgerEntry.query.filter_by(
            creator_bid=subscription.creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_bid="bill-preorder-downgrade-1",
        ).one()

        assert subscription.product_bid == "bill-product-plan-monthly"
        assert subscription.next_product_bid == ""
        assert "preorder_order_bid" not in subscription.metadata_json
        assert subscription.current_period_start_at == current_cycle_end
        assert subscription.current_period_end_at == next_cycle_end
        assert order.metadata_json["preorder_state"] == "effective_applied"
        assert order.metadata_json["renewal_cycle_start_at"] == (
            current_cycle_end.isoformat()
        )
        assert order.metadata_json["renewal_cycle_end_at"] == (
            next_cycle_end.isoformat()
        )
        assert order.metadata_json["preorder_effective_at_source"] == "cycle_boundary"
        assert bucket.source_bid == "bill-preorder-downgrade-1"
        assert bucket.available_credits == Decimal("1005.0000000000")
        assert bucket.reserved_credits == Decimal("0")
        assert wallet.available_credits == Decimal("1005.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert grant_entry.metadata_json["bucket_credit_state"] == "available"
        assert referral_grant_entry.metadata_json["bucket_credit_state"] == "available"
        assert grant_entry.consumable_from == current_cycle_end
        assert grant_entry.expires_at == next_cycle_end
        assert referral_grant_entry.consumable_from == current_cycle_end
        assert referral_grant_entry.expires_at == next_cycle_end
        assert grant_entry.balance_after == Decimal("5.0000000000")
        assert referral_grant_entry.balance_after == Decimal("1005.0000000000")
        assert expire_entry.amount == Decimal("-3.0000000000")
    assert staged_notifications == [
        ("creator-renewal-1", "bill-preorder-downgrade-1", False, False),
    ]
    assert enqueued_notifications == ["notif-preorder-release"]


def test_run_billing_same_plan_preorder_starts_new_cycle_at_boundary(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = now_utc() - timedelta(days=35)
    current_cycle_end = now_utc() - timedelta(minutes=1)
    next_cycle_end = self_managed_cycle_end_after_boundary(current_cycle_end)

    with billing_renewal_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="sub-preorder-same-plan",
            creator_bid="creator-renewal-same-plan",
            product_bid="bill-product-plan-monthly",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            provider_subscription_id="",
            provider_customer_id="customer-sub-preorder-same-plan",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
            cancel_at_period_end=0,
            next_product_bid="bill-product-plan-monthly",
            metadata_json={"preorder_order_bid": "bill-preorder-same-plan-1"},
            created_at=current_cycle_start,
            updated_at=current_cycle_start,
        )
        order = BillingOrder(
            bill_order_bid="bill-preorder-same-plan-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid="bill-product-plan-monthly",
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=990,
            paid_amount=990,
            payment_provider="pingxx",
            channel="alipay_qr",
            provider_reference_id="ch_preorder_same_plan_1",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_end - timedelta(days=5),
            metadata_json={
                "checkout_type": "subscription_preorder",
                "preorder_state": "pending_effective",
                "provider_reference_type": "charge",
                "current_product_bid": "bill-product-plan-monthly",
                "target_product_bid": "bill-product-plan-monthly",
                "preorder_effective_at": current_cycle_end.isoformat(),
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        event = create_renewal_event(
            "renewal-preorder-same-plan-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            scheduled_at=current_cycle_end,
        )
        wallet = create_credit_wallet(
            subscription.creator_bid,
            available_credits="3.0000000000",
            lifetime_granted_credits="10.0000000000",
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.add(wallet)
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-preorder-same-plan-1",
                wallet_bid=wallet.wallet_bid,
                creator_bid=subscription.creator_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-current-cycle-same-plan",
                priority=20,
                original_credits=Decimal("10.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("5.0000000000"),
                consumed_credits=Decimal("7.0000000000"),
                expired_credits=Decimal("0"),
                effective_from=current_cycle_start,
                effective_to=current_cycle_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={"bill_order_bid": "bill-current-cycle-same-plan"},
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-preorder-same-plan-1",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-preorder-same-plan-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-preorder-same-plan-1",
                idempotency_key="grant:bill-preorder-same-plan-1",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("3.0000000000"),
                expires_at=next_cycle_end,
                consumable_from=current_cycle_end,
                metadata_json={
                    "bill_order_bid": "bill-preorder-same-plan-1",
                    "subscription_bid": "sub-preorder-same-plan",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "pingxx",
                    "grant_reason": "subscription_renewal",
                    "bucket_credit_state": "reserved",
                    "reserved_until": current_cycle_end.isoformat(),
                },
                created_at=current_cycle_end - timedelta(days=5),
                updated_at=current_cycle_end - timedelta(days=5),
            )
        )
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-preorder-same-plan-1",
    )

    assert payload["status"] == "applied"
    assert payload["bill_order_bid"] == "bill-preorder-same-plan-1"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-preorder-same-plan"
        ).one()
        order = BillingOrder.query.filter_by(
            bill_order_bid="bill-preorder-same-plan-1"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid=subscription.creator_bid
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-preorder-same-plan-1"
        ).one()
        grant_entry = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-preorder-same-plan-1"
        ).one()

        assert subscription.product_bid == "bill-product-plan-monthly"
        assert subscription.next_product_bid == ""
        assert "preorder_order_bid" not in subscription.metadata_json
        assert subscription.current_period_start_at == current_cycle_end
        assert subscription.current_period_end_at == next_cycle_end
        assert order.metadata_json["preorder_state"] == "effective_applied"
        assert bucket.source_bid == "bill-preorder-same-plan-1"
        assert bucket.available_credits == Decimal("5.0000000000")
        assert bucket.reserved_credits == Decimal("0")
        assert wallet.available_credits == Decimal("5.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert grant_entry.metadata_json["bucket_credit_state"] == "available"
        assert grant_entry.consumable_from == current_cycle_end
        assert grant_entry.expires_at == next_cycle_end


def test_ensure_subscription_renewal_order_preserves_preorder_metadata(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = now_utc() - timedelta(days=30)
    current_cycle_end = now_utc() + timedelta(days=1)
    next_cycle_end = self_managed_cycle_end_after_boundary(current_cycle_end)

    with billing_renewal_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="sub-preorder-preserve",
            creator_bid="creator-renewal-1",
            product_bid="bill-product-plan-monthly-pro",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            provider_subscription_id="",
            provider_customer_id="customer-sub-preorder-preserve",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
            cancel_at_period_end=0,
            next_product_bid="bill-product-plan-monthly",
            metadata_json={"preorder_order_bid": "bill-preorder-preserve"},
            created_at=current_cycle_start,
            updated_at=current_cycle_start,
        )
        preorder_order = BillingOrder(
            bill_order_bid="bill-preorder-preserve",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid="bill-product-plan-monthly",
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=990,
            paid_amount=990,
            payment_provider="alipay",
            channel="alipay_qr",
            provider_reference_id="alipay_preorder_preserve",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_start + timedelta(days=1),
            metadata_json={
                "checkout_type": "subscription_preorder",
                "preorder_state": "pending_effective",
                "provider_reference_type": "charge",
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        dao.db.session.add(subscription)
        dao.db.session.add(preorder_order)
        dao.db.session.commit()

        ensured_order = ensure_subscription_renewal_order(
            billing_renewal_app,
            subscription,
            renewal_event_bid="renewal-preorder-preserve",
            scheduled_at=current_cycle_end,
        )
        dao.db.session.commit()

        assert ensured_order is not None
        assert ensured_order.bill_order_bid == "bill-preorder-preserve"
        assert ensured_order.payment_provider == "alipay"
        assert ensured_order.payable_amount == 990
        assert ensured_order.metadata_json["checkout_type"] == ("subscription_preorder")
        assert ensured_order.metadata_json["preorder_state"] == "pending_effective"
        assert ensured_order.metadata_json["renewal_event_bid"] == (
            "renewal-preorder-preserve"
        )
