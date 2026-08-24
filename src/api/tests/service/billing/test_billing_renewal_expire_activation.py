"""Verify billing renewal expire activation behavior."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.renewal import (
    run_billing_renewal_event,
)
from flaskr.util.datetime import now_utc, to_utc_iso

from tests.service.billing.renewal_execution_test_helpers import (
    create_credit_bucket,
    create_credit_wallet,
    create_renewal_event,
    self_managed_cycle_end_after_boundary,
)

if TYPE_CHECKING:
    from flask import Flask

pytest_plugins = ["tests.service.billing.renewal_execution_app_fixture"]


def test_expire_event_activates_paid_pingxx_renewal_instead_of_expiring(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = now_utc() - timedelta(days=30)
    current_cycle_end = now_utc() - timedelta(minutes=1)
    next_cycle_end = self_managed_cycle_end_after_boundary(current_cycle_end)

    with billing_renewal_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="sub-pingxx-expire-paid",
            creator_bid="creator-renewal-1",
            product_bid="bill-product-plan-monthly",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            provider_subscription_id="",
            provider_customer_id="customer-sub-pingxx-expire-paid",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
            cancel_at_period_end=0,
            next_product_bid="",
            metadata_json={},
            created_at=current_cycle_start,
            updated_at=current_cycle_start,
        )
        order = BillingOrder(
            bill_order_bid="bill-pingxx-expire-paid-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=9900,
            payment_provider="pingxx",
            channel="alipay_qr",
            provider_reference_id="ch_pingxx_expire_paid_1",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_end - timedelta(days=5),
            metadata_json={
                "provider_reference_type": "charge",
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        event = create_renewal_event(
            "renewal-expire-paid-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=current_cycle_end,
        )
        wallet = create_credit_wallet(
            subscription.creator_bid,
            available_credits="6.0000000000",
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.add(wallet)
        dao.db.session.add(
            create_credit_bucket(
                wallet.wallet_bid,
                subscription.creator_bid,
                "bucket-pingxx-expire-paid-1",
                available_credits="4.0000000000",
                source_bid="order-topup-pingxx-expire-paid-1",
                source_type=CREDIT_SOURCE_TYPE_TOPUP,
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                effective_from=current_cycle_start,
                effective_to=current_cycle_end,
                created_at=current_cycle_start,
            )
        )
        dao.db.session.add(
            create_credit_bucket(
                wallet.wallet_bid,
                subscription.creator_bid,
                "bucket-pingxx-expire-paid-bonus-1",
                available_credits="2.0000000000",
                source_bid="order-topup-pingxx-expire-paid-1",
                source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                effective_from=current_cycle_start,
                effective_to=current_cycle_end,
                created_at=current_cycle_start + timedelta(seconds=1),
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-pingxx-expire-paid-1",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-pingxx-expire-paid-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_TOPUP,
                source_bid="order-topup-pingxx-expire-paid-1",
                idempotency_key="grant:order-topup-pingxx-expire-paid-1",
                amount=Decimal("4.0000000000"),
                balance_after=Decimal("4.0000000000"),
                expires_at=current_cycle_end,
                consumable_from=current_cycle_start,
                metadata_json={},
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-pingxx-expire-paid-bonus-1",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-pingxx-expire-paid-bonus-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
                source_bid="order-topup-pingxx-expire-paid-1",
                idempotency_key="grant:campaign_bonus:order-topup-pingxx-expire-paid-1",
                amount=Decimal("2.0000000000"),
                balance_after=Decimal("6.0000000000"),
                expires_at=current_cycle_end,
                consumable_from=current_cycle_start,
                metadata_json={"grant_reason": "campaign_bonus"},
                created_at=current_cycle_start + timedelta(seconds=1),
                updated_at=current_cycle_start + timedelta(seconds=1),
            )
        )
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-expire-paid-1",
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "active"
    assert payload["bill_order_bid"] == "bill-pingxx-expire-paid-1"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-pingxx-expire-paid"
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-pingxx-expire-paid-1"
        ).one()
        bonus_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-pingxx-expire-paid-bonus-1"
        ).one()
        grant_entry = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-pingxx-expire-paid-1"
        ).one()
        bonus_grant_entry = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-pingxx-expire-paid-bonus-1"
        ).one()
        wallet = CreditWallet.query.filter_by(
            wallet_bid=f"wallet-{subscription.creator_bid}"
        ).one()
        expire_entries = CreditLedgerEntry.query.filter_by(
            creator_bid=subscription.creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert subscription.current_period_start_at == current_cycle_end
        assert subscription.current_period_end_at == next_cycle_end
        assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
        assert bucket.available_credits == Decimal("4.0000000000")
        assert bucket.effective_to == next_cycle_end
        assert grant_entry.expires_at == next_cycle_end
        assert bonus_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
        assert bonus_bucket.available_credits == Decimal("2.0000000000")
        assert bonus_bucket.effective_to == next_cycle_end
        assert bonus_grant_entry.expires_at == next_cycle_end
        assert wallet.available_credits == Decimal("6.0000000000")
        assert expire_entries == []


def test_expire_event_releases_reserved_subscription_renewal_on_same_bucket(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = now_utc() - timedelta(days=30)
    current_cycle_end = now_utc() - timedelta(minutes=1)
    next_cycle_end = self_managed_cycle_end_after_boundary(current_cycle_end)

    with billing_renewal_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="sub-pingxx-expire-reserved",
            creator_bid="creator-renewal-1",
            product_bid="bill-product-plan-monthly",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            provider_subscription_id="",
            provider_customer_id="customer-sub-pingxx-expire-reserved",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
            cancel_at_period_end=0,
            next_product_bid="",
            metadata_json={},
            created_at=current_cycle_start,
            updated_at=current_cycle_start,
        )
        order = BillingOrder(
            bill_order_bid="bill-pingxx-expire-reserved-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=9900,
            payment_provider="pingxx",
            channel="alipay_qr",
            provider_reference_id="ch_pingxx_expire_reserved_1",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_end - timedelta(days=5),
            metadata_json={
                "provider_reference_type": "charge",
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        event = create_renewal_event(
            "renewal-expire-reserved-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=current_cycle_end,
        )
        wallet = create_credit_wallet(
            subscription.creator_bid,
            available_credits="3.0000000000",
            lifetime_granted_credits="8.0000000000",
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.add(wallet)
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-pingxx-expire-reserved-1",
                wallet_bid=wallet.wallet_bid,
                creator_bid=subscription.creator_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-start-expire-reserved-1",
                priority=20,
                original_credits=Decimal("8.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("5.0000000000"),
                consumed_credits=Decimal(0),
                expired_credits=Decimal(0),
                effective_from=current_cycle_start,
                effective_to=current_cycle_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-start-expire-reserved-1",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-pingxx-expire-reserved-1",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-pingxx-expire-reserved-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-pingxx-expire-reserved-1",
                idempotency_key="grant:bill-pingxx-expire-reserved-1",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("3.0000000000"),
                expires_at=next_cycle_end,
                consumable_from=current_cycle_end,
                metadata_json={
                    "bill_order_bid": "bill-pingxx-expire-reserved-1",
                    "subscription_bid": "sub-pingxx-expire-reserved",
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
        renewal_event_bid="renewal-expire-reserved-1",
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "active"
    assert payload["bill_order_bid"] == "bill-pingxx-expire-reserved-1"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-pingxx-expire-reserved"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid=subscription.creator_bid
        ).one()
        subscription_buckets = CreditWalletBucket.query.filter_by(
            creator_bid=subscription.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        ).all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-pingxx-expire-reserved-1"
        ).one()
        grant_entry = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-pingxx-expire-reserved-1"
        ).one()
        expire_entry = CreditLedgerEntry.query.filter_by(
            creator_bid=subscription.creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_bid="bill-pingxx-expire-reserved-1",
        ).one()

        assert len(subscription_buckets) == 1
        assert subscription.current_period_start_at == current_cycle_end
        assert subscription.current_period_end_at == next_cycle_end
        assert bucket.source_bid == "bill-pingxx-expire-reserved-1"
        assert bucket.available_credits == Decimal("5.0000000000")
        assert bucket.reserved_credits == Decimal(0)
        assert bucket.expired_credits == Decimal("3.0000000000")
        assert bucket.effective_from == current_cycle_end
        assert bucket.effective_to == next_cycle_end
        assert wallet.available_credits == Decimal("5.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert grant_entry.consumable_from == current_cycle_end
        assert grant_entry.expires_at == next_cycle_end
        assert grant_entry.metadata_json["bucket_credit_state"] == "available"
        assert "activated_at" in grant_entry.metadata_json
        assert expire_entry.wallet_bucket_bid == bucket.wallet_bucket_bid
        assert expire_entry.amount == Decimal("-3.0000000000")


def test_expire_event_allows_shared_bucket_after_activated_grant_was_consumed(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = now_utc() - timedelta(days=30)
    current_cycle_end = now_utc() - timedelta(minutes=1)
    next_cycle_end = self_managed_cycle_end_after_boundary(current_cycle_end)

    with billing_renewal_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="sub-shared-bucket-consumed",
            creator_bid="creator-shared-bucket-consumed",
            product_bid="bill-product-plan-monthly",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            provider_subscription_id="",
            provider_customer_id="customer-shared-bucket-consumed",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
            cancel_at_period_end=0,
            next_product_bid="",
            metadata_json={},
            created_at=current_cycle_start,
            updated_at=current_cycle_start,
        )
        activated_order = BillingOrder(
            bill_order_bid="bill-shared-bucket-consumed-activated",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=9900,
            payment_provider="pingxx",
            channel="alipay_qr",
            provider_reference_id="ch_shared_bucket_consumed_activated",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_end - timedelta(days=6),
            metadata_json={
                "provider_reference_type": "charge",
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        reserved_order = BillingOrder(
            bill_order_bid="bill-shared-bucket-consumed-reserved",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=9900,
            payment_provider="pingxx",
            channel="alipay_qr",
            provider_reference_id="ch_shared_bucket_consumed_reserved",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_end - timedelta(days=5),
            metadata_json={
                "provider_reference_type": "charge",
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        event = create_renewal_event(
            "renewal-shared-bucket-consumed",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=current_cycle_end,
        )
        wallet = create_credit_wallet(
            subscription.creator_bid,
            available_credits="2.0000000000",
            lifetime_granted_credits="10.0000000000",
            lifetime_consumed_credits="3.0000000000",
        )
        wallet.reserved_credits = Decimal("5.0000000000")
        dao.db.session.add_all(
            [subscription, activated_order, reserved_order, event, wallet]
        )
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-shared-bucket-consumed",
                wallet_bid=wallet.wallet_bid,
                creator_bid=subscription.creator_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=activated_order.bill_order_bid,
                priority=20,
                original_credits=Decimal("10.0000000000"),
                available_credits=Decimal("2.0000000000"),
                reserved_credits=Decimal("5.0000000000"),
                consumed_credits=Decimal("3.0000000000"),
                expired_credits=Decimal(0),
                effective_from=current_cycle_end,
                effective_to=next_cycle_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": activated_order.bill_order_bid,
                },
                created_at=current_cycle_end - timedelta(days=6),
                updated_at=current_cycle_end - timedelta(days=6),
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-shared-bucket-consumed-activated",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-shared-bucket-consumed",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=activated_order.bill_order_bid,
                idempotency_key=f"grant:{activated_order.bill_order_bid}",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("5.0000000000"),
                expires_at=next_cycle_end,
                consumable_from=current_cycle_end,
                metadata_json={
                    "bill_order_bid": activated_order.bill_order_bid,
                    "subscription_bid": subscription.subscription_bid,
                    "product_bid": subscription.product_bid,
                    "payment_provider": "pingxx",
                    "grant_reason": "subscription_renewal",
                    "bucket_credit_state": "available",
                    "activated_at": (current_cycle_end - timedelta(days=6)).isoformat(),
                },
                created_at=current_cycle_end - timedelta(days=6),
                updated_at=current_cycle_end - timedelta(days=6),
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-shared-bucket-consumed-reserved",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-shared-bucket-consumed",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=reserved_order.bill_order_bid,
                idempotency_key=f"grant:{reserved_order.bill_order_bid}",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("2.0000000000"),
                expires_at=next_cycle_end,
                consumable_from=current_cycle_end,
                metadata_json={
                    "bill_order_bid": reserved_order.bill_order_bid,
                    "subscription_bid": subscription.subscription_bid,
                    "product_bid": subscription.product_bid,
                    "payment_provider": "pingxx",
                    "grant_reason": "subscription_renewal",
                    "bucket_credit_state": "reserved",
                    "reserved_until": current_cycle_end.isoformat(),
                },
                created_at=current_cycle_end - timedelta(days=5),
                updated_at=current_cycle_end - timedelta(days=5),
            )
        )
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-shared-bucket-consumed",
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "active"

    with billing_renewal_app.app_context():
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-shared-bucket-consumed"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-shared-bucket-consumed"
        ).one()
        reserved_grant = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-shared-bucket-consumed-reserved"
        ).one()
        activated_grant = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-shared-bucket-consumed-activated"
        ).one()

        assert bucket.available_credits == Decimal("7.0000000000")
        assert bucket.reserved_credits == Decimal(0)
        assert bucket.consumed_credits == Decimal("3.0000000000")
        assert wallet.available_credits == Decimal("7.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert activated_grant.metadata_json["bucket_credit_state"] == "available"
        assert reserved_grant.metadata_json["bucket_credit_state"] == "available"


def test_expire_event_fails_when_reserved_renewal_activation_is_incomplete(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = now_utc() - timedelta(days=30)
    current_cycle_end = now_utc() - timedelta(minutes=1)
    next_cycle_end = self_managed_cycle_end_after_boundary(current_cycle_end)

    with billing_renewal_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="sub-pingxx-expire-reserved-fail",
            creator_bid="creator-renewal-1",
            product_bid="bill-product-plan-monthly",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            provider_subscription_id="",
            provider_customer_id="customer-sub-pingxx-expire-reserved-fail",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
            cancel_at_period_end=0,
            next_product_bid="",
            metadata_json={},
            created_at=current_cycle_start,
            updated_at=current_cycle_start,
        )
        order = BillingOrder(
            bill_order_bid="bill-pingxx-expire-reserved-fail-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=9900,
            payment_provider="pingxx",
            channel="alipay_qr",
            provider_reference_id="ch_pingxx_expire_reserved_fail_1",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_end - timedelta(days=5),
            metadata_json={
                "provider_reference_type": "charge",
                "renewal_cycle_start_at": to_utc_iso(current_cycle_end),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        event = create_renewal_event(
            "renewal-expire-reserved-fail-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=current_cycle_end,
        )
        wallet = create_credit_wallet(
            subscription.creator_bid,
            available_credits="3.0000000000",
            lifetime_granted_credits="8.0000000000",
        )
        wallet.reserved_credits = Decimal("4.0000000000")
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.add(wallet)
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-pingxx-expire-reserved-fail-1",
                wallet_bid=wallet.wallet_bid,
                creator_bid=subscription.creator_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-start-expire-reserved-fail-1",
                priority=20,
                original_credits=Decimal("8.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("4.0000000000"),
                consumed_credits=Decimal(0),
                expired_credits=Decimal(0),
                effective_from=current_cycle_start,
                effective_to=current_cycle_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-start-expire-reserved-fail-1",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-pingxx-expire-reserved-fail-1",
                creator_bid=subscription.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-pingxx-expire-reserved-fail-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-pingxx-expire-reserved-fail-1",
                idempotency_key="grant:bill-pingxx-expire-reserved-fail-1",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("3.0000000000"),
                expires_at=next_cycle_end,
                consumable_from=current_cycle_end,
                metadata_json={
                    "bill_order_bid": "bill-pingxx-expire-reserved-fail-1",
                    "subscription_bid": "sub-pingxx-expire-reserved-fail",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "pingxx",
                    "grant_reason": "subscription_renewal",
                    "bucket_credit_state": "reserved",
                    "reserved_until": to_utc_iso(current_cycle_end),
                },
                created_at=current_cycle_end - timedelta(days=5),
                updated_at=current_cycle_end - timedelta(days=5),
            )
        )
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-expire-reserved-fail-1",
    )

    assert payload["status"] == "failed"
    assert payload["bill_order_bid"] == "bill-pingxx-expire-reserved-fail-1"
    assert payload["event_status"] == "failed"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-pingxx-expire-reserved-fail"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid=subscription.creator_bid
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-pingxx-expire-reserved-fail-1"
        ).one()
        grant_entry = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-pingxx-expire-reserved-fail-1"
        ).one()
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-expire-reserved-fail-1"
        ).one()
        expire_entries = CreditLedgerEntry.query.filter_by(
            creator_bid=subscription.creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert subscription.current_period_start_at == current_cycle_start
        assert subscription.current_period_end_at == current_cycle_end
        assert wallet.available_credits == Decimal("3.0000000000")
        assert wallet.reserved_credits == Decimal("4.0000000000")
        assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
        assert bucket.available_credits == Decimal("3.0000000000")
        assert bucket.reserved_credits == Decimal("4.0000000000")
        assert bucket.effective_to == current_cycle_end
        assert grant_entry.metadata_json["bucket_credit_state"] == "reserved"
        assert grant_entry.expires_at == next_cycle_end
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_FAILED
        assert event.last_error == "paid_renewal_activation_failed"
        assert expire_entries == []
