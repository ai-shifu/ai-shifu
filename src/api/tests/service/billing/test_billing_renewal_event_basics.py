from __future__ import annotations


from datetime import timedelta
from decimal import Decimal

from flask import Flask

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_TRIAL_PRODUCT_BID,
)
from flaskr.service.billing.models import (
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.renewal import (
    claim_billing_renewal_event,
    run_billing_renewal_event,
)
from flaskr.service.billing.primitives import normalize_mysql_datetime
from flaskr.service.billing.subscriptions import (
    sync_subscription_lifecycle_events,
)
from flaskr.util.datetime import now_utc


from tests.service.billing.renewal_execution_test_helpers import (
    _create_bucket,
    _create_renewal_event,
    _create_subscription,
    _create_wallet,
)


pytest_plugins = ["tests.service.billing.renewal_execution_app_fixture"]


def test_claim_billing_renewal_event_persists_processing_state(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-claim-1")
        event = _create_renewal_event(
            "renewal-claim-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = claim_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-claim-1",
    )

    assert payload["status"] == "claimed"
    assert payload["event_status"] == "processing"
    assert payload["attempt_count"] == 1

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-claim-1"
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
        assert event.attempt_count == 1


def test_run_billing_renewal_event_applies_cancel_effective(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-cancel-1")
        subscription.cancel_at_period_end = 1
        event = _create_renewal_event(
            "renewal-cancel-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-cancel-1",
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "canceled"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-cancel-1"
        ).one()
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-cancel-1"
        ).one()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        assert event.processed_at is not None


def test_run_billing_renewal_event_applies_expire(
    billing_renewal_app: Flask,
) -> None:
    period_end_at = now_utc() - timedelta(minutes=1)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-expire-1",
            current_period_end_at=period_end_at,
        )
        wallet = _create_wallet(
            subscription.creator_bid,
            available_credits="7.5000000000",
        )
        event = _create_renewal_event(
            "renewal-expire-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=period_end_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                _create_bucket(
                    wallet.wallet_bid,
                    subscription.creator_bid,
                    "bucket-expire-subscription-1",
                    available_credits="5.0000000000",
                    source_bid=subscription.subscription_bid,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    effective_from=period_end_at - timedelta(days=30),
                    effective_to=period_end_at,
                    created_at=period_end_at - timedelta(days=30),
                ),
                _create_bucket(
                    wallet.wallet_bid,
                    subscription.creator_bid,
                    "bucket-expire-topup-1",
                    available_credits="2.5000000000",
                    source_bid="order-topup-expire-1",
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    effective_from=period_end_at - timedelta(days=2),
                    effective_to=period_end_at,
                    created_at=period_end_at - timedelta(days=2),
                ),
            ]
        )
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-expire-1",
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "expired"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-expire-1"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid=subscription.creator_bid
        ).one()
        buckets = {
            bucket.wallet_bucket_bid: bucket
            for bucket in CreditWalletBucket.query.filter_by(
                creator_bid=subscription.creator_bid
            )
            .order_by(CreditWalletBucket.id.asc())
            .all()
        }
        ledger_entries = (
            CreditLedgerEntry.query.filter_by(
                creator_bid=subscription.creator_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )

        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_EXPIRED
        assert wallet.available_credits == Decimal("0E-10")
        assert len(ledger_entries) == 1
        assert [entry.wallet_bucket_bid for entry in ledger_entries] == [
            "bucket-expire-subscription-1",
        ]
        assert [entry.amount for entry in ledger_entries] == [
            Decimal("-5.0000000000"),
        ]
        assert [entry.balance_after for entry in ledger_entries] == [
            Decimal("2.5000000000"),
        ]
        assert (
            buckets["bucket-expire-subscription-1"].status
            == CREDIT_BUCKET_STATUS_EXPIRED
        )
        assert buckets["bucket-expire-topup-1"].status == CREDIT_BUCKET_STATUS_ACTIVE
        assert buckets["bucket-expire-subscription-1"].expired_credits == Decimal(
            "5.0000000000"
        )
        assert buckets["bucket-expire-topup-1"].expired_credits == Decimal("0")
        assert buckets["bucket-expire-subscription-1"].available_credits == Decimal("0")
        assert buckets["bucket-expire-topup-1"].available_credits == Decimal(
            "2.5000000000"
        )


def test_run_billing_renewal_event_does_not_duplicate_expire_ledger_when_replayed(
    billing_renewal_app: Flask,
) -> None:
    period_end_at = now_utc() - timedelta(minutes=1)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-expire-replay-1",
            current_period_end_at=period_end_at,
        )
        wallet = _create_wallet(
            subscription.creator_bid,
            available_credits="3.0000000000",
        )
        event = _create_renewal_event(
            "renewal-expire-replay-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=period_end_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(wallet)
        dao.db.session.add(
            _create_bucket(
                wallet.wallet_bid,
                subscription.creator_bid,
                "bucket-expire-replay-1",
                available_credits="3.0000000000",
                source_bid=subscription.subscription_bid,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                effective_from=period_end_at - timedelta(days=30),
                effective_to=period_end_at,
                created_at=period_end_at - timedelta(days=30),
            )
        )
        dao.db.session.add(event)
        dao.db.session.commit()

    first_payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-expire-replay-1",
    )
    second_payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-expire-replay-1",
    )

    assert first_payload["status"] == "applied"
    assert second_payload["status"] == "already_processed"
    assert second_payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        ledger_entries = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-renewal-1",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()
        assert len(ledger_entries) == 1


def test_manual_trial_subscription_schedules_and_applies_expire(
    billing_renewal_app: Flask,
) -> None:
    period_end_at = normalize_mysql_datetime(now_utc() - timedelta(minutes=1))
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-trial-expire-1",
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            billing_provider="manual",
            provider_subscription_id="",
            current_period_end_at=period_end_at,
        )
        wallet = _create_wallet(
            subscription.creator_bid,
            available_credits="100.0000000000",
        )
        dao.db.session.add(subscription)
        dao.db.session.add(wallet)
        dao.db.session.flush()
        dao.db.session.add(
            _create_bucket(
                wallet.wallet_bid,
                subscription.creator_bid,
                "bucket-trial-expire-1",
                available_credits="100.0000000000",
                source_bid=subscription.subscription_bid,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                effective_from=period_end_at - timedelta(days=15),
                effective_to=period_end_at,
                created_at=period_end_at - timedelta(days=15),
            )
        )
        sync_subscription_lifecycle_events(billing_renewal_app, subscription)
        dao.db.session.commit()

        event = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        ).one()
        renewal_event_bid = event.renewal_event_bid
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid=renewal_event_bid,
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "expired"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-trial-expire-1"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid=subscription.creator_bid
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-trial-expire-1"
        ).one()
        ledger_entry = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-trial-expire-1",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).one()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_EXPIRED
        assert wallet.available_credits == Decimal("0E-10")
        assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
        assert bucket.available_credits == Decimal("0")
        assert bucket.expired_credits == Decimal("100.0000000000")
        assert ledger_entry.amount == Decimal("-100.0000000000")


def test_trial_expire_event_sync_reuses_second_precision_scheduled_at(
    billing_renewal_app: Flask,
) -> None:
    period_end_at = (now_utc() + timedelta(days=15)).replace(microsecond=654321)
    stored_period_end_at = normalize_mysql_datetime(period_end_at)
    assert stored_period_end_at == period_end_at.replace(microsecond=0) + timedelta(
        seconds=1
    )
    assert normalize_mysql_datetime(
        period_end_at.replace(microsecond=499999)
    ) == period_end_at.replace(microsecond=0)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-trial-expire-precision",
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            billing_provider="manual",
            provider_subscription_id="",
            current_period_end_at=period_end_at,
        )
        stale_event = _create_renewal_event(
            "renewal-trial-expire-precision",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=stored_period_end_at,
            status=BILLING_RENEWAL_EVENT_STATUS_CANCELED,
        )
        stale_event.processed_at = subscription.current_period_start_at
        dao.db.session.add(subscription)
        dao.db.session.add(stale_event)
        dao.db.session.commit()

        sync_subscription_lifecycle_events(billing_renewal_app, subscription)
        dao.db.session.commit()

        events = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        ).all()
        assert len(events) == 1
        assert events[0].renewal_event_bid == "renewal-trial-expire-precision"
        assert events[0].scheduled_at == stored_period_end_at
        assert events[0].status == BILLING_RENEWAL_EVENT_STATUS_PENDING
        assert events[0].processed_at is None
