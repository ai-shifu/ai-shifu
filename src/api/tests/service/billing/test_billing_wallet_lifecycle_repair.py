from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.wallets import (
    _build_expire_ledger_idempotency_key,
    repair_credit_bucket_runtime_statuses,
    repair_expire_ledger_bucket_drift,
    repair_renewal_state_drift,
    restore_wrongly_expired_credit_pack_buckets,
)
from flaskr.util.datetime import to_utc_iso

from tests.service.billing.wallet_lifecycle_test_helpers import (
    create_monthly_plan_product,
)

if TYPE_CHECKING:
    from flask import Flask

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


def test_repair_credit_bucket_runtime_statuses_reactivates_live_expired_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    future_effective_to = datetime(2099, 6, 9, 23, 59, 59)
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-repair-runtime-1",
            creator_bid="creator-repair-runtime-1",
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("105.0000000000"),
            lifetime_consumed_credits=Decimal("9.8500000000"),
            last_settled_usage_id=0,
            version=0,
            created_at=datetime(2026, 5, 11, 14, 11, 8),
            updated_at=datetime(2026, 5, 11, 14, 11, 8),
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-repair-runtime-1",
            wallet_bid=wallet.wallet_bid,
            creator_bid="creator-repair-runtime-1",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="bill-repair-runtime-1",
            priority=20,
            original_credits=Decimal("105.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal("9.8500000000"),
            expired_credits=Decimal("90.1500000000"),
            effective_from=datetime(2026, 5, 11, 14, 11, 8),
            effective_to=future_effective_to,
            status=CREDIT_BUCKET_STATUS_EXPIRED,
            metadata_json={},
            created_at=datetime(2026, 5, 11, 14, 11, 8),
            updated_at=datetime(2026, 5, 11, 14, 11, 8),
        )
        dao.db.session.add(wallet)
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="subscription-repair-runtime-1",
                creator_bid="creator-repair-runtime-1",
                product_bid="bill-product-repair-runtime",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=datetime(2026, 5, 11, 0, 0, 0),
                current_period_end_at=future_effective_to,
            )
        )
        dao.db.session.add(bucket)
        dao.db.session.commit()

        payload = repair_credit_bucket_runtime_statuses(
            billing_wallet_lifecycle_app,
            creator_bid="creator-repair-runtime-1",
        )

        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-repair-runtime-1"
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-repair-runtime-1"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["repaired_bucket_count"] == 1
    assert payload["repaired_bucket_bids"] == ["bucket-repair-runtime-1"]
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert wallet.available_credits == Decimal("5.0000000000")


def test_repair_renewal_state_drift_dry_run_reports_stale_subscription_and_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-dry-run",
            creator_bid="creator-renewal-drift-dry-run",
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("3.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-drift-dry-run",
            creator_bid=wallet.creator_bid,
            product_bid="bill-product-renewal-drift",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 4, 7, 0, 0, 0),
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-dry-run",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-renewal-drift-dry-run",
            priority=20,
            original_credits=Decimal("3.0000000000"),
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, subscription, bucket])
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=True,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-dry-run"
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="subscription-renewal-drift-dry-run"
        ).one()

    assert payload["status"] == "dry_run"
    assert payload["creator_count"] == 1
    assert payload["stale_subscription_count"] == 1
    assert payload["stale_bucket_count"] == 1
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE


def test_repair_renewal_state_drift_expires_bucket_and_subscription(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-apply",
            creator_bid="creator-renewal-drift-apply",
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("3.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-drift-apply",
            creator_bid=wallet.creator_bid,
            product_bid="bill-product-renewal-drift",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 4, 7, 0, 0, 0),
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-apply",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-renewal-drift-apply",
            priority=20,
            original_credits=Decimal("3.0000000000"),
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, subscription, bucket])
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-apply"
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="subscription-renewal-drift-apply"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-renewal-drift-apply"
        ).one()
        ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-apply",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

    assert payload["status"] == "repaired"
    assert payload["creator_count"] == 1
    assert payload["stale_subscription_count"] == 1
    assert payload["stale_bucket_count"] == 1
    assert payload["updated_subscription_count"] == 1
    assert payload["expired_bucket_count"] == 1
    assert payload["expired_credits"] == 3.0
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == Decimal(0)
    assert bucket.expired_credits == Decimal("3.0000000000")
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_EXPIRED
    assert wallet.available_credits == Decimal("0E-10")
    assert len(ledgers) == 1


def test_repair_renewal_state_drift_dry_run_reports_overdue_reserved_paid_grant(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-protected"
    subscription_bid = "subscription-renewal-drift-protected-dry-run"
    order_bid = "order-renewal-drift-protected-dry-run"
    ledger_bid = "ledger-renewal-drift-protected-dry-run"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-protected-dry-run",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("2000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=wallet.creator_bid,
            product_bid="bill-product-renewal-drift-protected",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product = create_monthly_plan_product(subscription.product_bid)
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=wallet.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid="bill-product-renewal-drift-protected",
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-protected-dry-run",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-protected-dry-run",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-dry-run",
            priority=20,
            original_credits=Decimal("2000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-dry-run"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid=ledger_bid,
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": "subscription",
                "bucket_credit_state": "reserved",
                "reserved_until": boundary_at.isoformat(),
            },
        )
        event = BillingRenewalEvent(
            renewal_event_bid="renewal-event-protected-dry-run",
            subscription_bid=subscription.subscription_bid,
            creator_bid=wallet.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=boundary_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json={"bill_order_bid": order.bill_order_bid},
            processed_at=None,
        )
        dao.db.session.add_all(
            [wallet, subscription, product, order, bucket, ledger, event]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )
        dao.db.session.expire_all()
        wallet = CreditWallet.query.filter_by(creator_bid=creator_bid).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-protected-dry-run"
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(ledger_bid=ledger_bid).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=subscription_bid
        ).one()
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-event-protected-dry-run"
        ).one()

    assert payload["status"] == "dry_run"
    assert payload["creator_count"] == 1
    assert payload["stale_subscription_count"] == 1
    assert payload["stale_bucket_count"] == 1
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["activatable_creator_count"] == 1
    assert payload["activatable_creator_bids"] == [creator_bid]
    assert payload["activated_creator_count"] == 0
    assert payload["activated_creator_bids"] == []
    assert payload["protected_creator_count"] == 0
    assert payload["protected_creator_bids"] == []
    assert payload["overdue_reserved_grants"][0]["bill_order_bid"] == order_bid
    assert payload["overdue_reserved_grants"][0]["grant_ledger_bid"] == ledger_bid
    assert payload["overdue_reserved_grants"][0]["renewal_event_bids"] == [
        "renewal-event-protected-dry-run"
    ]
    assert (
        payload["overdue_reserved_grants"][0]["consumable_from"]
        == "2026-04-08T00:00:00Z"
    )
    assert payload["overdue_reserved_grants"][0]["paid_at"] == "2026-04-07T00:00:00Z"
    assert wallet.reserved_credits == Decimal("1000.0000000000")
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.effective_to == boundary_at
    assert bucket.reserved_credits == Decimal("1000.0000000000")
    assert ledger.metadata_json["bucket_credit_state"] == "reserved"
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert subscription.current_period_end_at == boundary_at
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING


def test_repair_renewal_state_drift_applies_overdue_reserved_paid_grant_before_expiry(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-protected-apply"
    subscription_bid = "subscription-renewal-drift-protected-apply"
    product_bid = "bill-product-renewal-drift-protected-apply"
    order_bid = "order-renewal-drift-protected-apply"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-protected-apply",
            creator_bid=creator_bid,
            available_credits=Decimal("1500.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("2500.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=wallet.creator_bid,
            product_bid=product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=datetime(2026, 3, 8, 0, 0, 0),
            last_failed_at=None,
            metadata_json={},
        )
        product = BillingProduct(
            product_bid=product_bid,
            product_code="repair-protected-monthly",
            product_type=1,
            display_name_i18n_key="billing.product.protected_monthly",
            description_i18n_key="billing.product.protected_monthly.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=wallet.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-protected-apply",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-protected-apply",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-apply",
            priority=20,
            original_credits=Decimal("2000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-apply"},
        )
        topup_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-topup-unfreeze",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-topup-unfreeze",
            priority=30,
            original_credits=Decimal("500.0000000000"),
            available_credits=Decimal("500.0000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at - timedelta(days=1),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-topup-unfreeze"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-protected-apply",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": "subscription",
                "bucket_credit_state": "reserved",
                "reserved_until": boundary_at.isoformat(),
            },
        )
        topup_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-topup-unfreeze",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=topup_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=topup_bucket.source_bid,
            idempotency_key=f"grant:{topup_bucket.source_bid}",
            amount=Decimal("500.0000000000"),
            balance_after=Decimal("1500.0000000000"),
            expires_at=topup_bucket.effective_to,
            consumable_from=topup_bucket.effective_from,
            metadata_json={
                "bill_order_bid": topup_bucket.source_bid,
                "grant_reason": "topup",
            },
        )
        event = BillingRenewalEvent(
            renewal_event_bid="renewal-event-protected-apply",
            subscription_bid=subscription.subscription_bid,
            creator_bid=wallet.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=boundary_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json={"bill_order_bid": order.bill_order_bid},
            processed_at=None,
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product,
                order,
                bucket,
                topup_bucket,
                ledger,
                topup_ledger,
                event,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )

        dao.db.session.expire_all()
        wallet = CreditWallet.query.filter_by(creator_bid=creator_bid).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-protected-apply"
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-renewal-drift-protected-apply"
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=subscription_bid
        ).one()
        topup_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-topup-unfreeze"
        ).one()
        topup_ledger = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-renewal-drift-topup-unfreeze"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["activatable_creator_count"] == 1
    assert payload["activatable_creator_bids"] == [creator_bid]
    assert payload["activated_reserved_order_count"] == 1
    assert payload["activated_creator_count"] == 1
    assert payload["activated_creator_bids"] == [creator_bid]
    assert payload["protected_creator_count"] == 0
    assert payload["protected_creator_bids"] == []
    assert payload["expired_bucket_count"] == 0
    assert payload["updated_subscription_count"] == 0
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert subscription.current_period_start_at == boundary_at
    assert subscription.current_period_end_at == next_cycle_end
    assert wallet.available_credits == Decimal("1500.0000000000")
    assert wallet.reserved_credits == Decimal("0E-10")
    assert bucket.source_bid == order_bid
    assert bucket.available_credits == Decimal("1000.0000000000")
    assert bucket.reserved_credits == Decimal("0E-10")
    assert bucket.effective_from == boundary_at
    assert bucket.effective_to == next_cycle_end
    assert topup_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert topup_bucket.available_credits == Decimal("500.0000000000")
    assert topup_bucket.expired_credits == Decimal(0)
    assert topup_bucket.effective_to == next_cycle_end
    assert topup_ledger.expires_at == next_cycle_end
    assert ledger.metadata_json["bucket_credit_state"] == "available"


def test_repair_renewal_state_drift_all_scope_includes_reserved_only_creator(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    repaired_at = datetime(2026, 4, 8, 0, 1, 0)
    creator_bid = "creator-renewal-drift-reserved-only"
    subscription_bid = "subscription-renewal-drift-reserved-only"
    order_bid = "order-renewal-drift-reserved-only"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-reserved-only",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-reserved-only",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
        )
        product = create_monthly_plan_product(subscription.product_bid)
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-reserved-only",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(datetime(2026, 4, 8, 0, 0, 0)),
                "renewal_cycle_end_at": to_utc_iso(datetime(2026, 5, 8, 0, 0, 0)),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-reserved-only",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-reserved-only",
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 5, 1, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-reserved-only"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-reserved-only",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=datetime(2026, 5, 8, 0, 0, 0),
            consumable_from=datetime(2026, 4, 8, 0, 0, 0),
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all([wallet, subscription, product, order, bucket, ledger])
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            repair_before=repaired_at,
            dry_run=True,
        )

    assert payload["status"] == "dry_run"
    assert payload["creator_count"] == 1
    assert payload["creator_bids"] == [creator_bid]
    assert payload["stale_subscription_count"] == 0
    assert payload["stale_bucket_count"] == 0
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["activatable_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_counts_only_successful_activations(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-activation-fails"
    subscription_bid = "subscription-renewal-drift-activation-fails"
    order_bid = "order-renewal-drift-activation-fails"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-activation-fails",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("2000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-activation-fails",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product = create_monthly_plan_product(subscription.product_bid)
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-activation-fails",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-activation-fails",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-activation-fails",
            priority=20,
            original_credits=Decimal("1500.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("500.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-activation-fails"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-activation-fails",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("500.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all([wallet, subscription, product, order, bucket, ledger])
        dao.db.session.commit()

        dry_payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )
        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(ledger)

    assert dry_payload["activatable_creator_bids"] == []
    assert dry_payload["protected_creator_bids"] == [creator_bid]
    assert dry_payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["activated_reserved_order_count"] == 0
    assert payload["activated_creator_count"] == 0
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert payload["activated_creator_bids"] == []
    assert payload["protected_creator_count"] == 1
    assert payload["protected_creator_bids"] == [creator_bid]
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert subscription.current_period_end_at == boundary_at
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("1000.0000000000")
    assert bucket.reserved_credits == Decimal("500.0000000000")
    assert ledger.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_blocks_cycle_when_subscription_grant_missing(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-missing-subscription-grant"
    subscription_bid = "subscription-renewal-drift-missing-subscription-grant"
    product_bid = "bill-product-renewal-drift-missing-subscription-grant"
    first_order_bid = "order-renewal-drift-missing-subscription-grant-1"
    missing_order_bid = "order-renewal-drift-missing-subscription-grant-2"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-missing-subscription-grant",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid=product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        first_order = BillingOrder(
            bill_order_bid=first_order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=first_order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        missing_order = BillingOrder(
            bill_order_bid=missing_order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=missing_order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 1, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-missing-subscription-grant",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=first_order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": first_order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-missing-subscription-grant",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=first_order_bid,
            idempotency_key=f"grant:{first_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": first_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(product_bid),
                first_order,
                missing_order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["activatable_creator_bids"] == []
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_blocks_unknown_subscription_grant_state(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-unknown-subscription-state"
    subscription_bid = "subscription-renewal-drift-unknown-subscription-state"
    order_bid = "order-renewal-drift-unknown-subscription-state"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-unknown-subscription-state",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-unknown-subscription-state",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-unknown-subscription-state",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-unknown-subscription-state",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "unknown",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        dry_payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )
        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(ledger)

    assert dry_payload["activatable_creator_bids"] == []
    assert dry_payload["protected_creator_bids"] == [creator_bid]
    assert dry_payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["activated_reserved_order_count"] == 0
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert subscription.current_period_end_at == boundary_at
    assert bucket.reserved_credits == Decimal("1000.0000000000")
    assert ledger.metadata_json["bucket_credit_state"] == "unknown"


def test_repair_renewal_state_drift_blocks_short_subscription_grant_amount(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-short-subscription-amount"
    subscription_bid = "subscription-renewal-drift-short-subscription-amount"
    order_bid = "order-renewal-drift-short-subscription-amount"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-short-subscription-amount",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1.0000000000"),
            lifetime_granted_credits=Decimal("1.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-short-subscription-amount",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-short-subscription-amount",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-short-subscription-amount",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        dry_payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )
        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(ledger)

    assert dry_payload["activatable_creator_bids"] == []
    assert dry_payload["protected_creator_bids"] == [creator_bid]
    assert dry_payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["activated_reserved_order_count"] == 0
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert subscription.current_period_end_at == boundary_at
    assert bucket.reserved_credits == Decimal("1.0000000000")
    assert ledger.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_ignores_legacy_missing_state_without_reserved(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    repaired_at = datetime(2026, 7, 28, 0, 0, 0)
    period_end = repaired_at + timedelta(days=30)
    creator_bid = "creator-renewal-drift-legacy-missing-state"
    subscription_bid = "subscription-renewal-drift-legacy-missing-state"
    order_bid = "order-renewal-drift-legacy-missing-state"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-legacy-missing-state",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-legacy-missing-state",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=repaired_at,
            current_period_end_at=period_end,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=repaired_at - timedelta(days=1),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(repaired_at - timedelta(days=1)),
                "renewal_cycle_end_at": to_utc_iso(period_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-legacy-missing-state",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal("1000.0000000000"),
            effective_from=repaired_at - timedelta(days=1),
            effective_to=period_end,
            status=CREDIT_BUCKET_STATUS_EXPIRED,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-legacy-missing-state",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=period_end,
            consumable_from=repaired_at - timedelta(days=1),
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "grant_reason": "subscription",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=repaired_at,
            dry_run=True,
        )

    assert payload["status"] == "noop"
    assert payload["overdue_reserved_grant_count"] == 0
    assert payload["protected_creator_bids"] == []
    assert payload["manual_review_creator_bids"] == []


def test_repair_renewal_state_drift_keeps_missing_state_with_matching_reserved_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-missing-state-matching-bucket"
    subscription_bid = "subscription-renewal-drift-missing-state-matching-bucket"
    order_bid = "order-renewal-drift-missing-state-matching-bucket"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-missing-state-matching-bucket",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-missing-state-matching-bucket",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=boundary_at,
            current_period_end_at=next_cycle_end,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=boundary_at - timedelta(days=1),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-missing-state-matching-bucket",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="",
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"billing_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-missing-state-matching-bucket",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "grant_reason": "subscription",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["creator_bids"] == [creator_bid]
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["overdue_reserved_grants"][0]["bill_order_bid"] == order_bid
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_keeps_missing_state_from_seeded_creator_scan(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-missing-state-seeded-scan"
    subscription_bid = "subscription-renewal-drift-missing-state-seeded-scan"
    order_bid = "order-renewal-drift-missing-state-seeded-scan"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-missing-state-seeded-scan",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-missing-state-seeded-scan",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=boundary_at - timedelta(days=1),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-missing-state-seeded-scan",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-missing-state-seeded-scan",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "grant_reason": "subscription",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["stale_subscription_count"] == 1
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["overdue_reserved_grants"][0]["bill_order_bid"] == order_bid
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_ignores_shared_bucket_legacy_missing_state(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    old_boundary_at = datetime(2026, 3, 8, 0, 0, 0)
    current_boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-shared-bucket-missing-state"
    subscription_bid = "subscription-renewal-drift-shared-bucket-missing-state"
    old_order_bid = "order-renewal-drift-shared-bucket-legacy"
    current_order_bid = "order-renewal-drift-shared-bucket-current"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-shared-bucket-missing-state",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("2000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-shared-bucket-missing-state",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=current_boundary_at,
            current_period_end_at=next_cycle_end,
        )
        old_order = BillingOrder(
            bill_order_bid=old_order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=old_order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=old_boundary_at - timedelta(days=1),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(old_boundary_at),
                "renewal_cycle_end_at": to_utc_iso(current_boundary_at),
            },
        )
        current_order = BillingOrder(
            bill_order_bid=current_order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=current_order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_boundary_at - timedelta(days=1),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(current_boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-shared-bucket-missing-state",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=current_order_bid,
            priority=20,
            original_credits=Decimal("2000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=current_boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": current_order_bid},
        )
        old_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-shared-bucket-legacy",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=old_order_bid,
            idempotency_key=f"grant:{old_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=current_boundary_at,
            consumable_from=old_boundary_at,
            metadata_json={
                "bill_order_bid": old_order_bid,
                "subscription_bid": subscription_bid,
                "grant_reason": "subscription",
            },
        )
        current_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-shared-bucket-current",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=current_order_bid,
            idempotency_key=f"grant:{current_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=current_boundary_at,
            metadata_json={
                "bill_order_bid": current_order_bid,
                "subscription_bid": subscription_bid,
                "grant_reason": "subscription",
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(subscription.product_bid),
                old_order,
                current_order,
                bucket,
                old_ledger,
                current_ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            repair_before=current_boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["creator_bids"] == [creator_bid]
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["overdue_reserved_grants"][0]["bill_order_bid"] == current_order_bid
    assert payload["activatable_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == []


def test_repair_renewal_state_drift_all_scope_falls_back_to_source_bid(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-source-bid-fallback"
    order_bid = "order-renewal-drift-source-bid-fallback"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-source-bid-fallback",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-drift-source-bid-fallback",
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-source-bid-fallback",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-source-bid-fallback",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-source-bid-fallback",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": "",
                "subscription_bid": subscription.subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["creator_bids"] == [creator_bid]
    assert payload["overdue_reserved_grants"][0]["bill_order_bid"] == order_bid
    assert payload["activatable_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_blocks_when_campaign_bonus_grant_missing(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-missing-campaign-grant"
    subscription_bid = "subscription-renewal-drift-missing-campaign-grant"
    order_bid = "order-renewal-drift-missing-campaign-grant"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-missing-campaign-grant",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-missing-campaign-grant",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            campaign_bid="campaign-renewal-drift-missing-campaign-grant",
            campaign_bonus_credit_amount=Decimal("100.0000000000"),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-missing-campaign-grant",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-missing-campaign-grant",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["activatable_creator_bids"] == []
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_blocks_same_order_when_bonus_only_would_succeed(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-bonus-only-success"
    subscription_bid = "subscription-renewal-drift-bonus-only-success"
    product_bid = "bill-product-renewal-drift-bonus-only-success"
    order_bid = "order-renewal-drift-bonus-only-success"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-bonus-only-success",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("600.0000000000"),
            lifetime_granted_credits=Decimal("1600.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid=product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product = BillingProduct(
            product_bid=product_bid,
            product_code="repair-bonus-only-success",
            product_type=1,
            display_name_i18n_key="billing.product.repair_bonus_only_success",
            description_i18n_key="billing.product.repair_bonus_only_success.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-bonus-only-success",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            campaign_bid="campaign-bonus-only-success",
            campaign_bonus_credit_amount=Decimal("100.0000000000"),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        subscription_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-bonus-only-success-subscription",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-bonus-only-success",
            priority=20,
            original_credits=Decimal("1500.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("500.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-bonus-only-success"},
        )
        bonus_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-bonus-only-success-bonus",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("100.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("100.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={
                "bill_order_bid": order_bid,
                "grant_reason": "campaign_bonus",
            },
        )
        subscription_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-bonus-only-success-subscription",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=subscription_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("500.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        bonus_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-bonus-only-success-bonus",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bonus_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            source_bid=order_bid,
            idempotency_key=f"grant:campaign_bonus:{order_bid}",
            amount=Decimal("100.0000000000"),
            balance_after=Decimal("500.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "campaign_bid": order.campaign_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product,
                order,
                subscription_bucket,
                bonus_bucket,
                subscription_ledger,
                bonus_ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(subscription_bucket)
        dao.db.session.refresh(bonus_bucket)
        dao.db.session.refresh(subscription_ledger)
        dao.db.session.refresh(bonus_ledger)

    assert payload["activated_reserved_order_count"] == 0
    assert payload["activated_creator_bids"] == []
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert subscription.current_period_end_at == boundary_at
    assert subscription_bucket.reserved_credits == Decimal("500.0000000000")
    assert bonus_bucket.reserved_credits == Decimal("100.0000000000")
    assert subscription_ledger.metadata_json["bucket_credit_state"] == "reserved"
    assert bonus_ledger.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_blocks_same_order_when_subscription_only_would_succeed(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-subscription-only-success"
    subscription_bid = "subscription-renewal-drift-subscription-only-success"
    product_bid = "bill-product-renewal-drift-subscription-only-success"
    order_bid = "order-renewal-drift-subscription-only-success"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-subscription-only-success",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1050.0000000000"),
            lifetime_granted_credits=Decimal("2050.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid=product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product = BillingProduct(
            product_bid=product_bid,
            product_code="repair-subscription-only-success",
            product_type=1,
            display_name_i18n_key="billing.product.repair_subscription_only_success",
            description_i18n_key="billing.product.repair_subscription_only_success.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-subscription-only-success",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            campaign_bid="campaign-subscription-only-success",
            campaign_bonus_credit_amount=Decimal("100.0000000000"),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        subscription_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-subscription-only-success-subscription",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-subscription-only-success",
            priority=20,
            original_credits=Decimal("2000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-subscription-only-success"},
        )
        bonus_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-subscription-only-success-bonus",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("100.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("50.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={
                "bill_order_bid": order_bid,
                "grant_reason": "campaign_bonus",
            },
        )
        subscription_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-subscription-only-success-subscription",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=subscription_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        bonus_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-subscription-only-success-bonus",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bonus_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            source_bid=order_bid,
            idempotency_key=f"grant:campaign_bonus:{order_bid}",
            amount=Decimal("100.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "campaign_bid": order.campaign_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product,
                order,
                subscription_bucket,
                bonus_bucket,
                subscription_ledger,
                bonus_ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(subscription_bucket)
        dao.db.session.refresh(bonus_bucket)
        dao.db.session.refresh(subscription_ledger)
        dao.db.session.refresh(bonus_ledger)

    assert payload["activated_reserved_order_count"] == 0
    assert payload["activated_creator_bids"] == []
    assert payload["protected_creator_bids"] == [creator_bid]
    assert subscription.current_period_end_at == boundary_at
    assert subscription_bucket.reserved_credits == Decimal("1000.0000000000")
    assert bonus_bucket.reserved_credits == Decimal("50.0000000000")
    assert subscription_ledger.metadata_json["bucket_credit_state"] == "reserved"
    assert bonus_ledger.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_blocks_multi_order_cycle_atomically(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-multi-order-blocked"
    subscription_bid = "subscription-renewal-drift-multi-order-blocked"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-multi-order-blocked",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("550.0000000000"),
            lifetime_granted_credits=Decimal("1550.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-multi-order-blocked-a",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product_a = BillingProduct(
            product_bid="bill-product-renewal-drift-multi-order-blocked-a",
            product_code="repair-multi-order-blocked-a",
            product_type=1,
            display_name_i18n_key="billing.product.repair_multi_order_blocked_a",
            description_i18n_key="billing.product.repair_multi_order_blocked_a.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("50.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        product_b = BillingProduct(
            product_bid="bill-product-renewal-drift-multi-order-blocked-b",
            product_code="repair-multi-order-blocked-b",
            product_type=1,
            display_name_i18n_key="billing.product.repair_multi_order_blocked_b",
            description_i18n_key="billing.product.repair_multi_order_blocked_b.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order_a = BillingOrder(
            bill_order_bid="order-renewal-drift-multi-order-blocked-a",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_a.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-multi-order-blocked-a",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        order_b = BillingOrder(
            bill_order_bid="order-renewal-drift-multi-order-blocked-b",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_b.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-multi-order-blocked-b",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 1, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket_a = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-multi-order-blocked-a",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-multi-order-blocked-a",
            priority=20,
            original_credits=Decimal("1050.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("50.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-multi-order-blocked-a"},
        )
        bucket_b = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-multi-order-blocked-b",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-multi-order-blocked-b",
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("500.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_b.bill_order_bid},
        )
        ledger_a = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-multi-order-blocked-a",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket_a.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_a.bill_order_bid,
            idempotency_key=f"grant:{order_a.bill_order_bid}",
            amount=Decimal("50.0000000000"),
            balance_after=Decimal("50.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_a.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        ledger_b = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-multi-order-blocked-b",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket_b.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_b.bill_order_bid,
            idempotency_key=f"grant:{order_b.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("50.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_b.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product_a,
                product_b,
                order_a,
                order_b,
                bucket_a,
                bucket_b,
                ledger_a,
                ledger_b,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket_a)
        dao.db.session.refresh(bucket_b)
        dao.db.session.refresh(ledger_a)
        dao.db.session.refresh(ledger_b)

    assert payload["activated_reserved_order_count"] == 0
    assert payload["protected_creator_bids"] == [creator_bid]
    assert subscription.current_period_end_at == boundary_at
    assert bucket_a.reserved_credits == Decimal("50.0000000000")
    assert bucket_b.reserved_credits == Decimal("500.0000000000")
    assert ledger_a.metadata_json["bucket_credit_state"] == "reserved"
    assert ledger_b.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_counts_all_activated_orders_in_shared_cycle(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-multi-order-success"
    subscription_bid = "subscription-renewal-drift-multi-order-success"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-multi-order-success",
            creator_bid=creator_bid,
            available_credits=Decimal(0),
            reserved_credits=Decimal("1050.0000000000"),
            lifetime_granted_credits=Decimal("1050.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-multi-order-success-a",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product_a = BillingProduct(
            product_bid="bill-product-renewal-drift-multi-order-success-a",
            product_code="repair-multi-order-success-a",
            product_type=1,
            display_name_i18n_key="billing.product.repair_multi_order_success_a",
            description_i18n_key="billing.product.repair_multi_order_success_a.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("50.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        product_b = BillingProduct(
            product_bid="bill-product-renewal-drift-multi-order-success-b",
            product_code="repair-multi-order-success-b",
            product_type=1,
            display_name_i18n_key="billing.product.repair_multi_order_success_b",
            description_i18n_key="billing.product.repair_multi_order_success_b.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order_a = BillingOrder(
            bill_order_bid="order-renewal-drift-multi-order-success-a",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_a.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-multi-order-success-a",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        order_b = BillingOrder(
            bill_order_bid="order-renewal-drift-multi-order-success-b",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_b.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-multi-order-success-b",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 1, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket_a = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-multi-order-success-a",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_a.bill_order_bid,
            priority=20,
            original_credits=Decimal("50.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("50.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_a.bill_order_bid},
        )
        bucket_b = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-multi-order-success-b",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_b.bill_order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal(0),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_b.bill_order_bid},
        )
        ledger_a = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-multi-order-success-a",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket_a.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_a.bill_order_bid,
            idempotency_key=f"grant:{order_a.bill_order_bid}",
            amount=Decimal("50.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_a.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        ledger_b = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-multi-order-success-b",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket_b.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_b.bill_order_bid,
            idempotency_key=f"grant:{order_b.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal(0),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_b.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product_a,
                product_b,
                order_a,
                order_b,
                bucket_a,
                bucket_b,
                ledger_a,
                ledger_b,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(wallet)
        dao.db.session.refresh(bucket_a)
        dao.db.session.refresh(bucket_b)
        dao.db.session.refresh(ledger_a)
        dao.db.session.refresh(ledger_b)

    assert payload["activated_reserved_order_count"] == 2
    assert payload["activated_creator_count"] == 1
    assert payload["activated_creator_bids"] == [creator_bid]
    assert payload["protected_creator_bids"] == []
    assert subscription.current_period_start_at == boundary_at
    assert subscription.current_period_end_at == next_cycle_end
    assert wallet.available_credits == Decimal("1050.0000000000")
    assert wallet.reserved_credits == Decimal("0E-10")
    assert bucket_a.available_credits == Decimal("50.0000000000")
    assert bucket_a.reserved_credits == Decimal("0E-10")
    assert bucket_b.available_credits == Decimal("1000.0000000000")
    assert bucket_b.reserved_credits == Decimal("0E-10")
    assert ledger_a.metadata_json["bucket_credit_state"] == "available"
    assert ledger_b.metadata_json["bucket_credit_state"] == "available"


def test_repair_expire_ledger_bucket_drift_dry_run_reports_without_writing(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-dry-run",
            creator_bid="creator-expire-ledger-drift-dry-run",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-dry-run",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-ledger-drift-dry-run",
            priority=20,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-dry-run",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=bucket.source_bid,
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal(0),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=True,
        )

        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-dry-run"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-dry-run"
        ).one()

    assert payload["status"] == "dry_run"
    assert payload["bucket_count"] == 1
    assert payload["repaired_bucket_count"] == 1
    assert payload["buckets"][0]["previous_available_credits"] == 2.5
    assert payload["buckets"][0]["available_credits"] == 0
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("2.5000000000")


def test_repair_expire_ledger_bucket_drift_applies_bucket_and_wallet_snapshot(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-apply",
            creator_bid="creator-expire-ledger-drift-apply",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-apply",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-ledger-drift-apply",
            priority=20,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-apply",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=bucket.source_bid,
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal(0),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-apply"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-apply"
        ).one()
        ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

    assert payload["status"] == "repaired"
    assert payload["bucket_count"] == 1
    assert payload["repaired_bucket_count"] == 1
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == Decimal(0)
    assert bucket.expired_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("0E-10")
    assert wallet.version == 1
    assert len(ledgers) == 1


def test_repair_expire_ledger_bucket_drift_accepts_cycle_scoped_expire_key(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-cycle-key",
            creator_bid="creator-expire-ledger-drift-cycle-key",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-cycle-key",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-ledger-drift-cycle-key",
            priority=20,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-cycle-key",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=bucket.source_bid,
            idempotency_key=_build_expire_ledger_idempotency_key(
                bucket.wallet_bucket_bid,
                effective_to=bucket.effective_to,
            ),
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal(0),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-cycle-key"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-cycle-key"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["bucket_count"] == 1
    assert payload["repaired_bucket_count"] == 1
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == Decimal(0)
    assert bucket.expired_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("0E-10")


def test_repair_expire_ledger_bucket_drift_keeps_existing_expired_amount(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-counted",
            creator_bid="creator-expire-ledger-drift-counted",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-counted",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-ledger-drift-counted",
            priority=20,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal("2.5000000000"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-counted",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=bucket.source_bid,
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal(0),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-counted"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["bucket_count"] == 1
    assert payload["buckets"][0]["previous_expired_credits"] == 2.5
    assert payload["buckets"][0]["expired_credits"] == 2.5
    assert bucket.available_credits == Decimal(0)
    assert bucket.expired_credits == Decimal("2.5000000000")


def test_repair_expire_ledger_bucket_drift_skips_reused_bucket_for_manual_review(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-reused",
            creator_bid="creator-expire-ledger-drift-reused",
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("15.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-reused",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-ledger-drift-reused-second-cycle",
            priority=20,
            original_credits=Decimal("15.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal("2.5000000000"),
            effective_from=datetime(2026, 5, 1, 0, 0, 0),
            effective_to=datetime(2026, 5, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-reused-old",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-ledger-drift-reused-first-cycle",
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal(0),
            expires_at=datetime(2026, 4, 7, 0, 0, 0),
            consumable_from=datetime(2026, 4, 1, 0, 0, 0),
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 5, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-reused"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-reused"
        ).one()

    assert payload["status"] == "manual_review"
    assert payload["bucket_count"] == 1
    assert payload["repaired_bucket_count"] == 0
    assert payload["manual_review_count"] == 1
    assert payload["buckets"][0]["repair_action"] == "manual_review"
    assert payload["buckets"][0]["repair_reason"] == "expire_ledger_expiry_mismatch"
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("5.0000000000")
    assert bucket.expired_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("5.0000000000")
    assert wallet.version == 0


def test_repair_expire_ledger_bucket_drift_sets_exhausted_for_reserved_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-reserved",
            creator_bid="creator-expire-ledger-drift-reserved",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("1.0000000000"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-reserved",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-ledger-drift-reserved",
            priority=20,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("1.0000000000"),
            consumed_credits=Decimal("6.5000000000"),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-reserved",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=bucket.source_bid,
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal(0),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-reserved"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-reserved"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["repaired_bucket_count"] == 1
    assert payload["manual_review_count"] == 0
    assert payload["buckets"][0]["repair_action"] == "repair"
    assert bucket.status == CREDIT_BUCKET_STATUS_EXHAUSTED
    assert bucket.available_credits == Decimal(0)
    assert bucket.reserved_credits == Decimal("1.0000000000")
    assert bucket.expired_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("0E-10")
    assert wallet.reserved_credits == Decimal("1.0000000000")


def test_repair_expire_ledger_bucket_drift_skips_credit_pack_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-topup-skip",
            creator_bid="creator-expire-ledger-drift-topup-skip",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-topup-skip",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-ledger-drift-topup-skip",
            priority=30,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-topup-skip",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=bucket.source_bid,
            idempotency_key=_build_expire_ledger_idempotency_key(
                bucket.wallet_bucket_bid,
                effective_to=bucket.effective_to,
            ),
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal(0),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-topup-skip"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-topup-skip"
        ).one()

    assert payload["status"] == "noop"
    assert payload["bucket_count"] == 0
    assert payload["repaired_bucket_count"] == 0
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("2.5000000000")
    assert bucket.expired_credits == Decimal(0)
    assert wallet.available_credits == Decimal("2.5000000000")
    assert wallet.version == 0


def test_restore_wrongly_expired_credit_pack_bucket_dry_run_does_not_write(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet, bucket = _seed_wrongly_expired_credit_pack_bucket(
            creator_bid="creator-restore-topup-dry-run",
            wallet_bid="wallet-restore-topup-dry-run",
            bucket_bid="bucket-restore-topup-dry-run",
            order_bid="order-restore-topup-dry-run",
            original=Decimal("250.0000000000"),
            consumed=Decimal(0),
            expired=Decimal("250.0000000000"),
        )

        payload = restore_wrongly_expired_credit_pack_buckets(
            billing_wallet_lifecycle_app,
            bill_order_bids=["order-restore-topup-dry-run"],
            dry_run=True,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid=bucket.wallet_bucket_bid
        ).one()
        adjustment_count = CreditLedgerEntry.query.filter_by(
            creator_bid=wallet.creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
        ).count()

    assert payload["status"] == "dry_run"
    assert payload["repaired_bucket_count"] == 1
    assert payload["buckets"][0]["repair_action"] == "repair"
    assert payload["buckets"][0]["restored_credits"] == 250
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == Decimal(0)
    assert bucket.expired_credits == Decimal("250.0000000000")
    assert adjustment_count == 0


def test_restore_wrongly_expired_credit_pack_bucket_restores_frozen_ownership(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet, bucket = _seed_wrongly_expired_credit_pack_bucket(
            creator_bid="creator-restore-topup-apply",
            wallet_bid="wallet-restore-topup-apply",
            bucket_bid="bucket-restore-topup-apply",
            order_bid="order-restore-topup-apply",
            original=Decimal("250.0000000000"),
            consumed=Decimal("136.8500000000"),
            expired=Decimal("113.1500000000"),
        )
        original_wallet_version = wallet.version

        payload = restore_wrongly_expired_credit_pack_buckets(
            billing_wallet_lifecycle_app,
            bill_order_bids=["order-restore-topup-apply"],
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid=bucket.wallet_bucket_bid
        ).one()
        wallet = CreditWallet.query.filter_by(wallet_bid=wallet.wallet_bid).one()
        adjustment = CreditLedgerEntry.query.filter_by(
            creator_bid=wallet.creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
        ).one()

    assert payload["status"] == "repaired"
    assert payload["repaired_bucket_count"] == 1
    assert payload["manual_review_count"] == 0
    assert payload["buckets"][0]["restored_credits"] == 113.15
    assert payload["buckets"][0]["ledger_bid"] == adjustment.ledger_bid
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("113.1500000000")
    assert bucket.consumed_credits == Decimal("136.8500000000")
    assert bucket.expired_credits == Decimal("0E-10")
    assert wallet.available_credits == Decimal("0E-10")
    assert wallet.version == original_wallet_version
    assert adjustment.amount == Decimal("113.1500000000")
    assert adjustment.balance_after == Decimal("0E-10")
    assert adjustment.metadata_json["repair_reason"] == (
        "restore_wrongly_expired_credit_pack_bucket"
    )


def test_restore_wrongly_expired_credit_pack_bucket_is_idempotent(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        _seed_wrongly_expired_credit_pack_bucket(
            creator_bid="creator-restore-topup-idempotent",
            wallet_bid="wallet-restore-topup-idempotent",
            bucket_bid="bucket-restore-topup-idempotent",
            order_bid="order-restore-topup-idempotent",
            original=Decimal("250.0000000000"),
            consumed=Decimal(0),
            expired=Decimal("250.0000000000"),
        )

        first_payload = restore_wrongly_expired_credit_pack_buckets(
            billing_wallet_lifecycle_app,
            bill_order_bids=["order-restore-topup-idempotent"],
            dry_run=False,
        )
        second_payload = restore_wrongly_expired_credit_pack_buckets(
            billing_wallet_lifecycle_app,
            bill_order_bids=["order-restore-topup-idempotent"],
            dry_run=False,
        )

        adjustment_count = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-restore-topup-idempotent",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
        ).count()

    assert first_payload["status"] == "repaired"
    assert second_payload["status"] == "noop"
    assert second_payload["noop_count"] == 1
    assert second_payload["buckets"][0]["repair_reason"] == "already_repaired"
    assert adjustment_count == 1


def test_restore_wrongly_expired_credit_pack_bucket_requires_matching_expire_ledger(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        _seed_wrongly_expired_credit_pack_bucket(
            creator_bid="creator-restore-topup-manual",
            wallet_bid="wallet-restore-topup-manual",
            bucket_bid="bucket-restore-topup-manual",
            order_bid="order-restore-topup-manual",
            original=Decimal("250.0000000000"),
            consumed=Decimal(0),
            expired=Decimal("250.0000000000"),
            expire_ledger_amount=Decimal("-1.0000000000"),
        )

        payload = restore_wrongly_expired_credit_pack_buckets(
            billing_wallet_lifecycle_app,
            bill_order_bids=["order-restore-topup-manual"],
            dry_run=False,
        )

        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-restore-topup-manual"
        ).one()
        adjustment_count = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-restore-topup-manual",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
        ).count()

    assert payload["status"] == "manual_review"
    assert payload["manual_review_count"] == 1
    assert payload["buckets"][0]["repair_reason"] == "expire_ledger_amount_mismatch"
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.expired_credits == Decimal("250.0000000000")
    assert adjustment_count == 0


def test_restore_wrongly_expired_credit_pack_bucket_reports_partial_repaired_status(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        _seed_wrongly_expired_credit_pack_bucket(
            creator_bid="creator-restore-topup-partial-repaired",
            wallet_bid="wallet-restore-topup-partial-repaired",
            bucket_bid="bucket-restore-topup-partial-repaired",
            order_bid="order-restore-topup-partial-repaired",
            original=Decimal("250.0000000000"),
            consumed=Decimal(0),
            expired=Decimal("250.0000000000"),
        )
        _seed_wrongly_expired_credit_pack_bucket(
            creator_bid="creator-restore-topup-partial-manual",
            wallet_bid="wallet-restore-topup-partial-manual",
            bucket_bid="bucket-restore-topup-partial-manual",
            order_bid="order-restore-topup-partial-manual",
            original=Decimal("250.0000000000"),
            consumed=Decimal(0),
            expired=Decimal("250.0000000000"),
            expire_ledger_amount=Decimal("-1.0000000000"),
        )

        payload = restore_wrongly_expired_credit_pack_buckets(
            billing_wallet_lifecycle_app,
            bill_order_bids=[
                "order-restore-topup-partial-repaired",
                "order-restore-topup-partial-manual",
            ],
            dry_run=False,
        )

    assert payload["status"] == "partial_repaired"
    assert payload["repaired_bucket_count"] == 1
    assert payload["manual_review_count"] == 1
    assert [bucket["repair_action"] for bucket in payload["buckets"]] == [
        "repair",
        "manual_review",
    ]


def _seed_wrongly_expired_credit_pack_bucket(
    *,
    creator_bid: str,
    wallet_bid: str,
    bucket_bid: str,
    order_bid: str,
    original: Decimal,
    consumed: Decimal,
    expired: Decimal,
    expire_ledger_amount: Decimal | None = None,
) -> tuple[CreditWallet, CreditWalletBucket]:
    effective_from = datetime(2026, 4, 1, 0, 0, 0)
    effective_to = datetime(2026, 4, 30, 0, 0, 0)
    wallet = CreditWallet(
        wallet_bid=wallet_bid,
        creator_bid=creator_bid,
        available_credits=Decimal(0),
        reserved_credits=Decimal(0),
        lifetime_granted_credits=original,
        lifetime_consumed_credits=consumed,
        last_settled_usage_id=0,
        version=0,
    )
    order = BillingOrder(
        bill_order_bid=order_bid,
        creator_bid=creator_bid,
        order_type=BILLING_ORDER_TYPE_TOPUP,
        product_bid=f"product-{order_bid}",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=datetime(2026, 4, 1, 0, 0, 0),
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=bucket_bid,
        wallet_bid=wallet_bid,
        creator_bid=creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
        source_bid=order_bid,
        priority=30,
        original_credits=original,
        available_credits=Decimal(0),
        reserved_credits=Decimal(0),
        consumed_credits=consumed,
        expired_credits=expired,
        effective_from=effective_from,
        effective_to=effective_to,
        status=CREDIT_BUCKET_STATUS_EXPIRED,
        metadata_json={},
    )
    expire_ledger = CreditLedgerEntry(
        ledger_bid=f"ledger-{order_bid}",
        creator_bid=creator_bid,
        wallet_bid=wallet_bid,
        wallet_bucket_bid=bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
        source_bid=order_bid,
        idempotency_key=_build_expire_ledger_idempotency_key(
            bucket_bid,
            effective_to=effective_to,
        ),
        amount=expire_ledger_amount if expire_ledger_amount is not None else -expired,
        balance_after=Decimal(0),
        expires_at=effective_to,
        consumable_from=effective_from,
        metadata_json={},
    )
    dao.db.session.add_all([wallet, order, bucket, expire_ledger])
    dao.db.session.commit()
    return wallet, bucket
