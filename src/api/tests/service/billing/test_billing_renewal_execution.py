from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_INTERVAL_DAY,
    BILLING_MODE_RECURRING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_TRIAL_PRODUCT_BID,
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
from flaskr.service.billing.renewal import (
    claim_billing_renewal_event,
    run_billing_renewal_event,
)
from flaskr.service.billing.subscriptions import sync_subscription_lifecycle_events
from tests.common.fixtures.bill_products import build_bill_products


@pytest.fixture
def billing_renewal_app() -> Flask:
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
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _create_subscription(
    subscription_bid: str,
    *,
    creator_bid: str = "creator-renewal-1",
    product_bid: str = "bill-product-plan-monthly",
    next_product_bid: str = "",
    status: int = BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    current_period_end_at: datetime | None = None,
    billing_provider: str = "stripe",
    provider_subscription_id: str | None = None,
) -> BillingSubscription:
    now = datetime.now()
    return BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        product_bid=product_bid,
        status=status,
        billing_provider=billing_provider,
        provider_subscription_id=provider_subscription_id
        if provider_subscription_id is not None
        else (f"provider-{subscription_bid}" if billing_provider == "stripe" else ""),
        provider_customer_id=f"customer-{subscription_bid}",
        current_period_start_at=now - timedelta(days=29),
        current_period_end_at=current_period_end_at or (now + timedelta(days=1)),
        cancel_at_period_end=0,
        next_product_bid=next_product_bid,
        metadata_json={},
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=30),
    )


def _create_renewal_event(
    renewal_event_bid: str,
    subscription_bid: str,
    creator_bid: str,
    *,
    event_type: int,
    scheduled_at: datetime | None = None,
    status: int = BILLING_RENEWAL_EVENT_STATUS_PENDING,
) -> BillingRenewalEvent:
    return BillingRenewalEvent(
        renewal_event_bid=renewal_event_bid,
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        event_type=event_type,
        scheduled_at=scheduled_at or (datetime.now() - timedelta(minutes=1)),
        status=status,
        attempt_count=0,
        last_error="",
        payload_json={"source": "pytest"},
        processed_at=None,
    )


def _create_wallet(
    creator_bid: str,
    *,
    available_credits: str,
    wallet_bid: str = "",
    lifetime_granted_credits: str | None = None,
    lifetime_consumed_credits: str = "0",
) -> CreditWallet:
    normalized_available_credits = Decimal(available_credits)
    return CreditWallet(
        wallet_bid=wallet_bid or f"wallet-{creator_bid}",
        creator_bid=creator_bid,
        available_credits=normalized_available_credits,
        reserved_credits=Decimal("0"),
        lifetime_granted_credits=Decimal(lifetime_granted_credits or available_credits),
        lifetime_consumed_credits=Decimal(lifetime_consumed_credits),
        last_settled_usage_id=0,
        version=0,
    )


def _create_bucket(
    wallet_bid: str,
    creator_bid: str,
    bucket_bid: str,
    *,
    available_credits: str,
    source_bid: str,
    source_type: int,
    category: int,
    effective_from: datetime,
    effective_to: datetime,
    created_at: datetime,
    status: int = CREDIT_BUCKET_STATUS_ACTIVE,
    expired_credits: str = "0",
    original_credits: str | None = None,
) -> CreditWalletBucket:
    normalized_available_credits = Decimal(available_credits)
    normalized_expired_credits = Decimal(expired_credits)
    resolved_original_credits = Decimal(
        original_credits
        if original_credits is not None
        else str(normalized_available_credits + normalized_expired_credits)
    )
    return CreditWalletBucket(
        wallet_bucket_bid=bucket_bid,
        wallet_bid=wallet_bid,
        creator_bid=creator_bid,
        bucket_category=category,
        source_type=source_type,
        source_bid=source_bid,
        priority=20 if category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION else 30,
        original_credits=resolved_original_credits,
        available_credits=normalized_available_credits,
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=normalized_expired_credits,
        effective_from=effective_from,
        effective_to=effective_to,
        status=status,
        metadata_json={},
        created_at=created_at,
        updated_at=created_at,
    )


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
    period_end_at = datetime.now() - timedelta(minutes=1)
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
        assert len(ledger_entries) == 2
        assert [entry.wallet_bucket_bid for entry in ledger_entries] == [
            "bucket-expire-subscription-1",
            "bucket-expire-topup-1",
        ]
        assert [entry.amount for entry in ledger_entries] == [
            Decimal("-5.0000000000"),
            Decimal("-2.5000000000"),
        ]
        assert [entry.balance_after for entry in ledger_entries] == [
            Decimal("2.5000000000"),
            Decimal("0E-10"),
        ]
        assert (
            buckets["bucket-expire-subscription-1"].status
            == CREDIT_BUCKET_STATUS_EXPIRED
        )
        assert buckets["bucket-expire-topup-1"].status == CREDIT_BUCKET_STATUS_EXPIRED
        assert buckets["bucket-expire-subscription-1"].expired_credits == Decimal(
            "5.0000000000"
        )
        assert buckets["bucket-expire-topup-1"].expired_credits == Decimal(
            "2.5000000000"
        )
        assert buckets["bucket-expire-subscription-1"].available_credits == Decimal("0")
        assert buckets["bucket-expire-topup-1"].available_credits == Decimal("0")


def test_run_billing_renewal_event_does_not_duplicate_expire_ledger_when_replayed(
    billing_renewal_app: Flask,
) -> None:
    period_end_at = datetime.now() - timedelta(minutes=1)
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
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-trial-expire-1",
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            billing_provider="manual",
            provider_subscription_id="",
            current_period_end_at=datetime.now() - timedelta(minutes=1),
        )
        dao.db.session.add(subscription)
        dao.db.session.flush()
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
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_EXPIRED


def test_run_billing_renewal_event_applies_downgrade_and_reschedules_renewal(
    billing_renewal_app: Flask,
) -> None:
    next_period_end = datetime.now() + timedelta(days=30)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-downgrade-1",
            product_bid="bill-product-plan-yearly",
            next_product_bid="bill-product-plan-monthly",
            current_period_end_at=next_period_end,
        )
        event = _create_renewal_event(
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
        assert renewal_event.scheduled_at == next_period_end


def test_run_billing_renewal_event_releases_future_event_back_to_pending(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-future-1")
        event = _create_renewal_event(
            "renewal-future-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            scheduled_at=datetime.now() + timedelta(minutes=30),
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-future-1",
    )

    assert payload["status"] == "deferred_until_scheduled_at"
    assert payload["event_status"] == "pending"
    assert payload["attempt_count"] == 1

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-future-1"
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
        assert event.attempt_count == 1
        assert event.processed_at is None


def test_run_billing_renewal_event_queues_subscription_renewal_order(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.renewal.sync_billing_order",
        lambda app, creator_bid, bill_order_bid, payload: {
            "status": "pending",
            "creator_bid": creator_bid,
            "bill_order_bid": bill_order_bid,
        },
    )

    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-unsupported-1")
        subscription.provider_subscription_id = "sub_provider_unsupported_1"
        subscription_bid = subscription.subscription_bid
        event = _create_renewal_event(
            "renewal-unsupported-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-unsupported-1",
    )

    assert payload["status"] == "queued_for_reconcile"
    assert payload["event_status"] == "succeeded"
    assert payload["bill_order_bid"]

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-unsupported-1"
        ).one()
        order = BillingOrder.query.filter_by(
            bill_order_bid=payload["bill_order_bid"]
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        assert order.subscription_bid == subscription_bid
        assert order.provider_reference_id == "sub_provider_unsupported_1"
        assert order.metadata_json["provider_reference_type"] == "subscription"


def test_run_billing_renewal_event_queues_pingxx_order_without_provider_sync(
    billing_renewal_app: Flask,
) -> None:
    cycle_end = datetime.now() - timedelta(hours=1)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-pingxx-renewal-1",
            current_period_end_at=cycle_end,
            billing_provider="pingxx",
            provider_subscription_id="",
        )
        event = _create_renewal_event(
            "renewal-pingxx-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            scheduled_at=cycle_end - timedelta(days=7),
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-pingxx-1",
    )

    assert payload["status"] == "queued_for_reconcile"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid=payload["bill_order_bid"]
        ).one()
        assert order.payment_provider == "pingxx"
        assert order.provider_reference_id == ""
        assert order.metadata_json["provider_reference_type"] == "charge"
        assert order.metadata_json["renewal_cycle_start_at"] == cycle_end.isoformat()


def test_run_billing_renewal_event_writes_daily_cycle_metadata(
    billing_renewal_app: Flask,
) -> None:
    cycle_end = datetime.now() - timedelta(hours=1)
    expected_cycle_end = cycle_end + timedelta(days=7)

    with billing_renewal_app.app_context():
        dao.db.session.add(
            BillingProduct(
                product_bid="bill-product-plan-daily",
                product_code="creator-plan-daily",
                product_type=BILLING_PRODUCT_TYPE_PLAN,
                billing_mode=BILLING_MODE_RECURRING,
                billing_interval=BILLING_INTERVAL_DAY,
                billing_interval_count=7,
                display_name_i18n_key=(
                    "module.billing.catalog.plans.creatorMonthly.title"
                ),
                description_i18n_key=(
                    "module.billing.catalog.plans.creatorMonthly.description"
                ),
                currency="CNY",
                price_amount=390,
                credit_amount=3,
                allocation_interval=ALLOCATION_INTERVAL_PER_CYCLE,
                auto_renew_enabled=1,
                entitlement_payload=None,
                metadata_json=None,
                status=BILLING_PRODUCT_STATUS_ACTIVE,
                sort_order=15,
            )
        )
        subscription = _create_subscription(
            "sub-daily-renewal-1",
            product_bid="bill-product-plan-daily",
            current_period_end_at=cycle_end,
            billing_provider="pingxx",
            provider_subscription_id="",
        )
        event = _create_renewal_event(
            "renewal-daily-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            scheduled_at=cycle_end - timedelta(minutes=5),
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-daily-1",
    )

    assert payload["status"] == "queued_for_reconcile"

    with billing_renewal_app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid=payload["bill_order_bid"]
        ).one()
        assert order.metadata_json["renewal_cycle_start_at"] == cycle_end.isoformat()
        assert (
            order.metadata_json["renewal_cycle_end_at"]
            == expected_cycle_end.isoformat()
        )


def test_expire_event_activates_paid_pingxx_renewal_instead_of_expiring(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = datetime.now() - timedelta(days=30)
    current_cycle_end = datetime.now() - timedelta(minutes=1)
    next_cycle_end = current_cycle_end + timedelta(days=30)

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
        event = _create_renewal_event(
            "renewal-expire-paid-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=current_cycle_end,
        )
        wallet = _create_wallet(
            subscription.creator_bid,
            available_credits="4.0000000000",
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.add(wallet)
        dao.db.session.add(
            _create_bucket(
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
        grant_entry = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-pingxx-expire-paid-1"
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
        assert expire_entries == []


def test_expire_event_releases_reserved_subscription_renewal_on_same_bucket(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = datetime.now() - timedelta(days=30)
    current_cycle_end = datetime.now() - timedelta(minutes=1)
    next_cycle_end = current_cycle_end + timedelta(days=30)

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
        event = _create_renewal_event(
            "renewal-expire-reserved-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=current_cycle_end,
        )
        wallet = _create_wallet(
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
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
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
        assert bucket.reserved_credits == Decimal("0")
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


def test_run_billing_renewal_event_retries_latest_failed_renewal_order(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.renewal.sync_billing_order",
        lambda app, creator_bid, bill_order_bid, payload: {
            "status": "paid",
            "creator_bid": creator_bid,
            "bill_order_bid": bill_order_bid,
        },
    )

    cycle_start = datetime.now()
    cycle_end = cycle_start + timedelta(days=30)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-retry-1",
            current_period_end_at=cycle_start,
        )
        subscription.provider_subscription_id = "sub_provider_retry_1"
        renewal_order = BillingOrder(
            bill_order_bid="bill-renewal-retry-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=0,
            payment_provider="stripe",
            channel="subscription",
            provider_reference_id="sub_provider_retry_1",
            status=BILLING_ORDER_STATUS_FAILED,
            metadata_json={
                "provider_reference_type": "subscription",
                "renewal_cycle_start_at": cycle_start.isoformat(),
                "renewal_cycle_end_at": cycle_end.isoformat(),
            },
        )
        event = _create_renewal_event(
            "renewal-retry-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RETRY,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(renewal_order)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-retry-1",
    )

    assert payload["status"] == "applied"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-retry-1"
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
