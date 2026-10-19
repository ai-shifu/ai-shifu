"""Repair jobs for top-up grant expiries and subscription cycle drift."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.util.datetime import NAIVE_DATETIME_MIN

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import to_decimal as _to_decimal
from .reserved_renewal_activation import (
    IncompleteReservedGrantActivationError,  # noqa: F401
    validate_reserved_renewal_cycle_activation,  # noqa: F401
)
from .subscriptions_cycles import (
    _load_billing_product_by_bid,
    _resolve_credit_bucket_effective_from,
    _resolve_credit_bucket_effective_to,
)
from .subscriptions_lifecycle import (
    _sync_subscription_lifecycle_events,
)
from .wallets import (
    load_primary_credit_bucket_by_category,
)

if TYPE_CHECKING:
    from datetime import datetime
    from types import ModuleType

    from flask import Flask


def _subscriptions_facade() -> ModuleType:
    """Resolve collaborators through ``subscriptions`` so its patch points stay live."""
    from . import subscriptions

    return subscriptions


@dataclass(slots=True, frozen=True)
class TopupExpiryRepairRecord:
    """Record topup expiry repair details."""

    wallet_bucket_bid: str
    bill_order_bid: str | None
    previous_effective_to: datetime | None
    effective_to: datetime
    ledger_bids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        """Serialize this result as an API payload."""
        return {
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "bill_order_bid": self.bill_order_bid,
            "previous_effective_to": self.previous_effective_to,
            "effective_to": self.effective_to,
            "ledger_bids": list(self.ledger_bids),
        }


@dataclass(slots=True, frozen=True)
class TopupExpiryRepairResult:
    """Capture the repair outcome for topup expiry."""

    status: str
    creator_bid: str | None
    inspected_bucket_count: int
    repaired_bucket_count: int
    repaired_ledger_count: int
    repaired_records: list[TopupExpiryRepairRecord] = field(default_factory=list)
    skipped_bucket_bids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        """Serialize this result as an API payload."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "inspected_bucket_count": self.inspected_bucket_count,
            "repaired_bucket_count": self.repaired_bucket_count,
            "repaired_ledger_count": self.repaired_ledger_count,
            "repaired_records": [item.to_payload() for item in self.repaired_records],
            "skipped_bucket_bids": list(self.skipped_bucket_bids),
        }

    def __getitem__(self, key: str) -> object:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class SubscriptionCycleRepairRecord:
    """Record subscription cycle repair details."""

    subscription_bid: str
    creator_bid: str
    bill_order_bid: str | None
    wallet_bucket_bid: str | None
    previous_current_period_start_at: datetime | None
    previous_current_period_end_at: datetime | None
    current_period_start_at: datetime
    current_period_end_at: datetime
    reason: str

    def to_payload(self) -> dict[str, object]:
        """Serialize this result as an API payload."""
        return {
            "subscription_bid": self.subscription_bid,
            "creator_bid": self.creator_bid,
            "bill_order_bid": self.bill_order_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "previous_current_period_start_at": self.previous_current_period_start_at,
            "previous_current_period_end_at": self.previous_current_period_end_at,
            "current_period_start_at": self.current_period_start_at,
            "current_period_end_at": self.current_period_end_at,
            "reason": self.reason,
        }


@dataclass(slots=True, frozen=True)
class SubscriptionCycleRepairResult:
    """Capture the repair outcome for subscription cycle."""

    status: str
    creator_bid: str | None
    subscription_bid: str | None
    inspected_subscription_count: int
    repaired_subscription_count: int
    repaired_records: list[SubscriptionCycleRepairRecord] = field(default_factory=list)
    skipped_subscription_bids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        """Serialize this result as an API payload."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "subscription_bid": self.subscription_bid,
            "inspected_subscription_count": self.inspected_subscription_count,
            "repaired_subscription_count": self.repaired_subscription_count,
            "repaired_records": [item.to_payload() for item in self.repaired_records],
            "skipped_subscription_bids": list(self.skipped_subscription_bids),
        }

    def __getitem__(self, key: str) -> object:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class _SubscriptionCycleEvidence:
    effective_from: datetime | None
    effective_to: datetime | None
    bill_order_bid: str | None
    wallet_bucket_bid: str | None
    reason: str
    is_current_window: bool = False


def _load_topup_expiry_subscription_for_bucket(
    creator_bid: str,
    *,
    bucket_effective_from: datetime,
    bucket_effective_to: datetime | None,
) -> BillingSubscription | None:
    rows = BillingSubscription.query.filter(
        BillingSubscription.deleted == 0,
        BillingSubscription.creator_bid == creator_bid,
        BillingSubscription.status.in_(
            (
                BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
                BILLING_SUBSCRIPTION_STATUS_PAUSED,
                BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
            )
        ),
        BillingSubscription.current_period_end_at.isnot(None),
        BillingSubscription.current_period_end_at > bucket_effective_from,
    )
    if bucket_effective_to is not None:
        rows = rows.filter(
            (BillingSubscription.current_period_start_at.is_(None))
            | (BillingSubscription.current_period_start_at <= bucket_effective_to)
        )

    subscriptions = rows.order_by(
        BillingSubscription.created_at.asc(),
        BillingSubscription.id.asc(),
    ).all()
    if not subscriptions:
        return None

    def _sort_key(
        row: BillingSubscription,
    ) -> tuple[int, datetime, datetime, datetime, int]:
        product = _load_billing_product_by_bid(row.product_bid)
        product_sort_order = int(product.sort_order) if product is not None else -1
        return (
            product_sort_order,
            row.current_period_start_at or NAIVE_DATETIME_MIN,
            row.current_period_end_at or NAIVE_DATETIME_MIN,
            row.created_at or NAIVE_DATETIME_MIN,
            int(row.id or 0),
        )

    return max(subscriptions, key=_sort_key)


def repair_topup_grant_expiries(
    app: Flask,
    *,
    creator_bid: str,
) -> TopupExpiryRepairResult:
    """Repair topup grant expiries."""
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return TopupExpiryRepairResult(
            status="noop",
            creator_bid=None,
            inspected_bucket_count=0,
            repaired_bucket_count=0,
            repaired_ledger_count=0,
        )

    with app_context_scope(app), unit_of_work():
        buckets = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.creator_bid == normalized_creator_bid,
                CreditWalletBucket.source_type == CREDIT_SOURCE_TYPE_TOPUP,
            )
            .order_by(
                CreditWalletBucket.created_at.asc(),
                CreditWalletBucket.id.asc(),
            )
            .all()
        )
        if not buckets:
            return TopupExpiryRepairResult(
                status="noop",
                creator_bid=normalized_creator_bid,
                inspected_bucket_count=0,
                repaired_bucket_count=0,
                repaired_ledger_count=0,
            )

        repaired_at = _subscriptions_facade().now_utc()
        repaired_records: list[TopupExpiryRepairRecord] = []
        skipped_bucket_bids: list[str] = []
        repaired_ledger_count = 0

        for bucket in buckets:
            available = _to_decimal(bucket.available_credits)
            if available <= 0:
                skipped_bucket_bids.append(bucket.wallet_bucket_bid)
                continue

            reference_effective_from = bucket.effective_from or (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.creator_bid == normalized_creator_bid,
                    BillingOrder.bill_order_bid == _normalize_bid(bucket.source_bid),
                    BillingOrder.order_type == BILLING_ORDER_TYPE_TOPUP,
                )
                .order_by(BillingOrder.id.desc())
                .with_entities(BillingOrder.paid_at)
                .scalar()
            )
            if reference_effective_from is None:
                skipped_bucket_bids.append(bucket.wallet_bucket_bid)
                continue

            candidate_subscription = _load_topup_expiry_subscription_for_bucket(
                normalized_creator_bid,
                bucket_effective_from=reference_effective_from,
                bucket_effective_to=bucket.effective_to,
            )
            if (
                candidate_subscription is None
                or candidate_subscription.current_period_end_at is None
            ):
                skipped_bucket_bids.append(bucket.wallet_bucket_bid)
                continue

            order = (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.creator_bid == normalized_creator_bid,
                    BillingOrder.bill_order_bid == _normalize_bid(bucket.source_bid),
                    BillingOrder.order_type == BILLING_ORDER_TYPE_TOPUP,
                )
                .order_by(BillingOrder.id.desc())
                .first()
            )
            expected_effective_to = candidate_subscription.current_period_end_at

            grant_entries = (
                CreditLedgerEntry.query.filter(
                    CreditLedgerEntry.deleted == 0,
                    CreditLedgerEntry.creator_bid == normalized_creator_bid,
                    CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
                    CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                )
                .order_by(
                    CreditLedgerEntry.created_at.asc(), CreditLedgerEntry.id.asc()
                )
                .all()
            )

            previous_effective_to = bucket.effective_to
            updated_ledger_bids: list[str] = []
            if previous_effective_to != expected_effective_to:
                bucket.effective_to = expected_effective_to
                bucket.updated_at = repaired_at
                db.session.add(bucket)

            for entry in grant_entries:
                if entry.expires_at == expected_effective_to:
                    continue
                entry.expires_at = expected_effective_to
                entry.updated_at = repaired_at
                db.session.add(entry)
                updated_ledger_bids.append(entry.ledger_bid)

            if (
                previous_effective_to == expected_effective_to
                and not updated_ledger_bids
            ):
                continue

            repaired_ledger_count += len(updated_ledger_bids)
            repaired_records.append(
                TopupExpiryRepairRecord(
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    bill_order_bid=order.bill_order_bid if order is not None else None,
                    previous_effective_to=previous_effective_to,
                    effective_to=expected_effective_to,
                    ledger_bids=tuple(updated_ledger_bids),
                )
            )

        return TopupExpiryRepairResult(
            status="repaired" if repaired_records else "noop",
            creator_bid=normalized_creator_bid,
            inspected_bucket_count=len(buckets),
            repaired_bucket_count=len(repaired_records),
            repaired_ledger_count=repaired_ledger_count,
            repaired_records=repaired_records,
            skipped_bucket_bids=skipped_bucket_bids,
        )


def repair_subscription_cycle_mismatches(
    app: Flask,
    *,
    creator_bid: str = "",
    subscription_bid: str = "",
) -> SubscriptionCycleRepairResult:
    """Repair subscription cycle mismatches."""
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_subscription_bid = _normalize_bid(subscription_bid)

    with app_context_scope(app), unit_of_work():
        query = BillingSubscription.query.filter(BillingSubscription.deleted == 0)
        if normalized_creator_bid:
            query = query.filter(
                BillingSubscription.creator_bid == normalized_creator_bid
            )
        if normalized_subscription_bid:
            query = query.filter(
                BillingSubscription.subscription_bid == normalized_subscription_bid
            )
        subscriptions = query.order_by(
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        ).all()
        repaired_at = _subscriptions_facade().now_utc()
        repaired_records: list[SubscriptionCycleRepairRecord] = []
        skipped_subscription_bids: list[str] = []

        for subscription in subscriptions:
            evidence = _select_subscription_cycle_repair_evidence(
                subscription,
                as_of=repaired_at,
            )
            if (
                evidence is None
                or evidence.effective_from is None
                or evidence.effective_to is None
            ):
                skipped_subscription_bids.append(subscription.subscription_bid)
                continue

            current_start_at = subscription.current_period_start_at
            current_end_at = subscription.current_period_end_at
            matches_evidence = (
                current_start_at == evidence.effective_from
                and current_end_at == evidence.effective_to
            )
            is_future_dated = (
                current_start_at is not None and current_start_at > repaired_at
            )
            is_missing_window = current_start_at is None or current_end_at is None
            is_invalid_window = (
                current_start_at is not None
                and current_end_at is not None
                and current_end_at <= current_start_at
            )
            mismatched_current_window = (
                evidence.is_current_window and not matches_evidence
            )
            if not (
                is_missing_window
                or is_invalid_window
                or is_future_dated
                or mismatched_current_window
            ):
                skipped_subscription_bids.append(subscription.subscription_bid)
                continue

            subscription.current_period_start_at = evidence.effective_from
            subscription.current_period_end_at = evidence.effective_to
            if evidence.effective_to > repaired_at:
                subscription.status = (
                    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
                    if subscription.cancel_at_period_end
                    else BILLING_SUBSCRIPTION_STATUS_ACTIVE
                )
            subscription.last_renewed_at = evidence.effective_from
            subscription.updated_at = repaired_at
            _sync_subscription_lifecycle_events(app, subscription)
            db.session.add(subscription)
            repaired_records.append(
                SubscriptionCycleRepairRecord(
                    subscription_bid=subscription.subscription_bid,
                    creator_bid=subscription.creator_bid,
                    bill_order_bid=evidence.bill_order_bid,
                    wallet_bucket_bid=evidence.wallet_bucket_bid,
                    previous_current_period_start_at=current_start_at,
                    previous_current_period_end_at=current_end_at,
                    current_period_start_at=evidence.effective_from,
                    current_period_end_at=evidence.effective_to,
                    reason=evidence.reason,
                )
            )

        return SubscriptionCycleRepairResult(
            status="repaired" if repaired_records else "noop",
            creator_bid=normalized_creator_bid or None,
            subscription_bid=normalized_subscription_bid or None,
            inspected_subscription_count=len(subscriptions),
            repaired_subscription_count=len(repaired_records),
            repaired_records=repaired_records,
            skipped_subscription_bids=skipped_subscription_bids,
        )


def _select_subscription_cycle_repair_evidence(
    subscription: BillingSubscription,
    *,
    as_of: datetime,
) -> _SubscriptionCycleEvidence | None:
    paid_orders = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == subscription.creator_bid,
            BillingOrder.subscription_bid == subscription.subscription_bid,
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
            BillingOrder.order_type.in_(
                (
                    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                )
            ),
        )
        .order_by(
            BillingOrder.paid_at.desc(),
            BillingOrder.created_at.desc(),
            BillingOrder.id.desc(),
        )
        .all()
    )
    if not paid_orders:
        return None

    bucket = load_primary_credit_bucket_by_category(
        subscription.creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    )
    if bucket is not None:
        if (
            int(bucket.status or 0)
            in (
                CREDIT_BUCKET_STATUS_ACTIVE,
                CREDIT_BUCKET_STATUS_EXHAUSTED,
            )
            and (bucket.effective_from is None or bucket.effective_from <= as_of)
            and (bucket.effective_to is None or bucket.effective_to > as_of)
        ):
            return _SubscriptionCycleEvidence(
                effective_from=bucket.effective_from,
                effective_to=bucket.effective_to,
                bill_order_bid=bucket.source_bid or None,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                reason="current_subscription_bucket",
                is_current_window=True,
            )
        return _SubscriptionCycleEvidence(
            effective_from=bucket.effective_from,
            effective_to=bucket.effective_to,
            bill_order_bid=bucket.source_bid or None,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            reason="latest_subscription_bucket",
            is_current_window=False,
        )

    latest_paid_order = paid_orders[0]
    product = _load_billing_product_by_bid(latest_paid_order.product_bid)
    if product is None:
        return None
    default_effective_from = (
        latest_paid_order.paid_at or latest_paid_order.created_at or as_of
    )
    effective_from = _resolve_credit_bucket_effective_from(
        order=latest_paid_order,
        default_effective_from=default_effective_from,
    )
    effective_to = _resolve_credit_bucket_effective_to(
        order=latest_paid_order,
        product=product,
        effective_from=effective_from,
    )
    return _SubscriptionCycleEvidence(
        effective_from=effective_from,
        effective_to=effective_to,
        bill_order_bid=latest_paid_order.bill_order_bid,
        wallet_bucket_bid=None,
        reason="latest_paid_subscription_order",
        is_current_window=(effective_from is None or effective_from <= as_of)
        and (effective_to is None or effective_to > as_of),
    )
