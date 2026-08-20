"""Provide renewal execution test helpers support for service billing tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_INTERVAL_MONTH,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
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
from flaskr.service.billing.queries import (
    calculate_self_managed_billing_cycle_end,
    calculate_self_managed_billing_cycle_end_after_boundary,
)
from flaskr.util.datetime import now_utc

__all__ = [
    "add_paid_renewal_with_reserved_grant",
    "create_credit_bucket",
    "create_credit_wallet",
    "create_renewal_event",
    "create_renewal_subscription",
    "self_managed_cycle_end",
    "self_managed_cycle_end_after_boundary",
]


def self_managed_cycle_end(
    cycle_start_at: datetime,
    *,
    interval: int = BILLING_INTERVAL_MONTH,
    interval_count: int = 1,
) -> datetime:
    cycle_end_at = calculate_self_managed_billing_cycle_end(
        BillingProduct(
            billing_interval=interval,
            billing_interval_count=interval_count,
        ),
        cycle_start_at=cycle_start_at,
    )
    assert cycle_end_at is not None
    return cycle_end_at


def self_managed_cycle_end_after_boundary(
    cycle_boundary_at: datetime,
    *,
    interval: int = BILLING_INTERVAL_MONTH,
    interval_count: int = 1,
) -> datetime:
    cycle_end_at = calculate_self_managed_billing_cycle_end_after_boundary(
        BillingProduct(
            billing_interval=interval,
            billing_interval_count=interval_count,
        ),
        cycle_boundary_at=cycle_boundary_at,
    )
    assert cycle_end_at is not None
    return cycle_end_at


def create_renewal_subscription(
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
    now = now_utc()
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


def create_renewal_event(
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
        scheduled_at=scheduled_at or (now_utc() - timedelta(minutes=1)),
        status=status,
        attempt_count=0,
        last_error="",
        payload_json={"source": "pytest"},
        processed_at=None,
    )


def create_credit_wallet(
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
        reserved_credits=Decimal(0),
        lifetime_granted_credits=Decimal(lifetime_granted_credits or available_credits),
        lifetime_consumed_credits=Decimal(lifetime_consumed_credits),
        last_settled_usage_id=0,
        version=0,
    )


def create_credit_bucket(
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
        reserved_credits=Decimal(0),
        consumed_credits=Decimal(0),
        expired_credits=normalized_expired_credits,
        effective_from=effective_from,
        effective_to=effective_to,
        status=status,
        metadata_json={},
        created_at=created_at,
        updated_at=created_at,
    )


def add_paid_renewal_with_reserved_grant(
    *,
    suffix: str,
    current_cycle_start: datetime,
    current_cycle_end: datetime,
    next_cycle_end: datetime,
    scheduled_at: datetime,
    paid_at: datetime,
) -> tuple[str, str, str, str, str]:
    subscription_bid = f"sub-scheduled-paid-{suffix}"
    order_bid = f"bill-scheduled-paid-{suffix}"
    event_bid = f"renewal-scheduled-paid-{suffix}"
    bucket_bid = f"bucket-scheduled-paid-{suffix}"
    ledger_bid = f"ledger-scheduled-paid-{suffix}"
    creator_bid = "creator-renewal-1"

    subscription = BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        product_bid="bill-product-plan-monthly",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        billing_provider="pingxx",
        provider_subscription_id="",
        provider_customer_id=f"customer-{subscription_bid}",
        current_period_start_at=current_cycle_start,
        current_period_end_at=current_cycle_end,
        cancel_at_period_end=0,
        next_product_bid="",
        metadata_json={},
        created_at=current_cycle_start,
        updated_at=current_cycle_start,
    )
    order = BillingOrder(
        bill_order_bid=order_bid,
        creator_bid=creator_bid,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        product_bid=subscription.product_bid,
        subscription_bid=subscription.subscription_bid,
        currency="CNY",
        payable_amount=9900,
        paid_amount=9900,
        payment_provider="pingxx",
        channel="alipay_qr",
        provider_reference_id=f"ch_{suffix}",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=paid_at,
        metadata_json={
            "provider_reference_type": "charge",
            "renewal_cycle_start_at": current_cycle_end.isoformat(),
            "renewal_cycle_end_at": next_cycle_end.isoformat(),
        },
    )
    event = create_renewal_event(
        event_bid,
        subscription.subscription_bid,
        subscription.creator_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        scheduled_at=scheduled_at,
    )
    wallet = create_credit_wallet(
        subscription.creator_bid,
        available_credits="3.0000000000",
        lifetime_granted_credits="8.0000000000",
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=bucket_bid,
        wallet_bid=wallet.wallet_bid,
        creator_bid=subscription.creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid=f"bill-current-{suffix}",
        priority=20,
        original_credits=Decimal("8.0000000000"),
        available_credits=Decimal("3.0000000000"),
        reserved_credits=Decimal("5.0000000000"),
        consumed_credits=Decimal(0),
        expired_credits=Decimal(0),
        effective_from=current_cycle_start,
        effective_to=current_cycle_end,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json={"bill_order_bid": f"bill-current-{suffix}"},
        created_at=current_cycle_start,
        updated_at=current_cycle_start,
    )
    grant_entry = CreditLedgerEntry(
        ledger_bid=ledger_bid,
        creator_bid=subscription.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid=order.bill_order_bid,
        idempotency_key=f"grant:{order.bill_order_bid}",
        amount=Decimal("5.0000000000"),
        balance_after=Decimal("3.0000000000"),
        expires_at=next_cycle_end,
        consumable_from=current_cycle_end,
        metadata_json={
            "bill_order_bid": order.bill_order_bid,
            "subscription_bid": subscription.subscription_bid,
            "product_bid": subscription.product_bid,
            "payment_provider": "pingxx",
            "grant_reason": "subscription_renewal",
            "bucket_credit_state": "reserved",
            "reserved_until": current_cycle_end.isoformat(),
        },
        created_at=paid_at,
        updated_at=paid_at,
    )
    dao.db.session.add_all([subscription, order, event, wallet, bucket, grant_entry])
    return subscription_bid, order_bid, event_bid, bucket_bid, ledger_bid
