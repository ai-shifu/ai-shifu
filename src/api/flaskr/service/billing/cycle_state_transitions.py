"""State-transition helpers for billing cycle side effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.util.datetime import now_utc

from .bucket_categories import (
    load_billing_order_type_by_bid,
    resolve_wallet_bucket_runtime_category,
)
from .consts import (
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
)
from .models import BillingSubscription, CreditLedgerEntry, CreditWalletBucket
from .primitives import normalize_bid as _normalize_bid

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class SubscriptionCycleWindow:
    """Describe the window used by subscription cycle."""

    start_at: datetime
    end_at: datetime


def resolve_effective_subscription_cycle_window(
    subscription: BillingSubscription | None,
    *,
    as_of: datetime,
) -> SubscriptionCycleWindow | None:
    """Return the time-valid current cycle window, without business advancement rules.

    "Effective" only means start <= as_of < end. This helper does not validate
    subscription status, parse order metadata, or decide whether a cycle may advance.
    """
    if subscription is None:
        return None

    start_at = subscription.current_period_start_at
    end_at = subscription.current_period_end_at
    if start_at is None or end_at is None:
        return None
    if start_at > as_of or end_at <= as_of:
        return None
    return SubscriptionCycleWindow(start_at=start_at, end_at=end_at)


def subscription_has_effective_cycle(
    subscription: BillingSubscription | None,
    *,
    as_of: datetime,
) -> bool:
    return (
        resolve_effective_subscription_cycle_window(subscription, as_of=as_of)
        is not None
    )


def realign_active_topup_bucket_effective_to(
    *,
    creator_bid: str,
    effective_from: datetime,
    effective_to: datetime | None,
) -> None:
    realign_active_credit_bucket_effective_to(
        creator_bid=creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        effective_from=effective_from,
        effective_to=effective_to,
        include_effective_to_boundary=True,
    )


def apply_paid_subscription_cycle_state(
    subscription: BillingSubscription,
    *,
    creator_bid: str,
    order_type: int,
    order_product_bid: str,
    effective_from: datetime,
    effective_to: datetime | None,
) -> None:
    if order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        subscription.product_bid = (
            _normalize_bid(subscription.next_product_bid) or order_product_bid
        )
        subscription.next_product_bid = ""
    else:
        subscription.product_bid = order_product_bid
        subscription.next_product_bid = ""

    subscription.status = (
        BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        if subscription.cancel_at_period_end
        else BILLING_SUBSCRIPTION_STATUS_ACTIVE
    )
    subscription.current_period_start_at = effective_from
    subscription.current_period_end_at = effective_to
    subscription.last_renewed_at = effective_from
    realign_active_topup_bucket_effective_to(
        creator_bid=creator_bid,
        effective_from=effective_from,
        effective_to=effective_to,
    )


def realign_active_credit_bucket_effective_to(
    *,
    creator_bid: str,
    bucket_category: int,
    effective_from: datetime,
    effective_to: datetime | None,
    include_effective_to_boundary: bool,
) -> None:
    if effective_to is None:
        return

    buckets = load_active_credit_buckets_by_runtime_category(
        creator_bid,
        bucket_category=bucket_category,
    )
    if not buckets:
        return

    current_at = now_utc()
    for bucket in buckets:
        if bucket.effective_from is not None and bucket.effective_from > effective_from:
            continue
        if bucket.effective_to is not None and (
            not include_effective_to_boundary and bucket.effective_to <= effective_from
        ):
            continue
        if bucket.effective_to != effective_to:
            bucket.effective_to = effective_to
            bucket.updated_at = current_at
            db.session.add(bucket)

        grant_entry_filters = [
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        ]
        if not include_effective_to_boundary:
            grant_entry_filters.append(
                (
                    CreditLedgerEntry.expires_at.is_(None)
                    | (CreditLedgerEntry.expires_at >= effective_from)
                ),
            )
        grant_entries = (
            CreditLedgerEntry.query.filter(*grant_entry_filters)
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )
        for entry in grant_entries:
            entry.expires_at = effective_to
            entry.updated_at = current_at
            db.session.add(entry)


def load_active_credit_buckets_by_runtime_category(
    creator_bid: str,
    *,
    bucket_category: int,
) -> list[CreditWalletBucket]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return []

    rows = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid == normalized_creator_bid,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
            CreditWalletBucket.available_credits > 0,
        )
        .order_by(CreditWalletBucket.created_at.asc(), CreditWalletBucket.id.asc())
        .all()
    )
    return [
        row
        for row in rows
        if resolve_wallet_bucket_runtime_category(
            row,
            load_order_type=load_billing_order_type_by_bid,
        )
        == bucket_category
    ]
