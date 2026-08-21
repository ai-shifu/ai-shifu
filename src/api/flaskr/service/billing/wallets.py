"""Wallet bucket snapshot helpers for creator billing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_error
from flaskr.util.datetime import NAIVE_DATETIME_MIN, now_utc, to_utc_iso
from flaskr.util.uuid import generate_id
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import ObjectDeletedError

from .bucket_categories import (
    build_wallet_bucket_runtime_sort_key,
    load_billing_order_type_by_bid,
    resolve_credit_bucket_priority,
    resolve_runtime_credit_bucket_category,
    resolve_wallet_bucket_runtime_category,
    wallet_bucket_requires_active_subscription,
)
from .consts import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_CANCELED,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .dtos import BillingLedgerAdjustResultDTO, BillingWalletRefDTO
from .models import (
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .primitives import credit_decimal_to_number as _credit_decimal_to_number
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .queries import load_primary_active_subscription

if TYPE_CHECKING:
    from flask import Flask

_ZERO = Decimal(0)
_PRESERVED_BUCKET_STATUSES = {
    CREDIT_BUCKET_STATUS_CANCELED,
    CREDIT_BUCKET_STATUS_EXPIRED,
}
_SINGLE_BUCKET_CATEGORIES = {
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
}


@dataclass(slots=True, frozen=True)
class WalletSnapshotRecord:
    """Record wallet snapshot details."""

    wallet_bid: str
    creator_bid: str
    available_credits: int | float
    reserved_credits: int | float
    previous_available_credits: int | float
    previous_reserved_credits: int | float
    available_credits_delta: int | float
    reserved_credits_delta: int | float
    changed: bool

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "wallet_bid": self.wallet_bid,
            "creator_bid": self.creator_bid,
            "available_credits": self.available_credits,
            "reserved_credits": self.reserved_credits,
            "previous_available_credits": self.previous_available_credits,
            "previous_reserved_credits": self.previous_reserved_credits,
            "available_credits_delta": self.available_credits_delta,
            "reserved_credits_delta": self.reserved_credits_delta,
            "changed": self.changed,
        }

    def __getitem__(self, key: str) -> Any:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class WalletSnapshotRebuildResult:
    """Capture the rebuild outcome for wallet snapshot."""

    status: str
    creator_bid: str | None
    wallet_bid: str | None
    wallet_count: int
    changed_wallet_count: int = 0
    dry_run: bool = False
    wallets: list[WalletSnapshotRecord] = field(default_factory=list)

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "wallet_bid": self.wallet_bid,
            "wallet_count": self.wallet_count,
            "changed_wallet_count": self.changed_wallet_count,
            "dry_run": self.dry_run,
            "wallets": [wallet.to_payload() for wallet in self.wallets],
        }

    def __getitem__(self, key: str) -> Any:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class RefundReturnCreditsResult:
    """Capture credits returned while refunding a billing order."""

    status: str
    creator_bid: str | None
    source_bid: str | None
    amount: int | float = 0
    wallet_bucket_bid: str | None = None
    ledger_bid: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "source_bid": self.source_bid,
            "amount": self.amount,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "ledger_bid": self.ledger_bid,
        }

    def __getitem__(self, key: str) -> Any:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class WalletExpirationResult:
    """Capture credits expired from a wallet."""

    status: str
    creator_bid: str | None
    bucket_count: int
    expired_credits: int | float

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "bucket_count": self.bucket_count,
            "expired_credits": self.expired_credits,
        }

    def __getitem__(self, key: str) -> Any:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class ExpireLedgerBucketDriftRecord:
    """Record expire ledger bucket drift details."""

    wallet_bucket_bid: str
    wallet_bid: str
    creator_bid: str
    previous_available_credits: int | float
    available_credits: int | float
    previous_expired_credits: int | float
    expired_credits: int | float
    previous_status: int
    status: int
    expire_ledger_count: int
    expire_ledger_amount: int | float
    repair_action: str
    repair_reason: str
    changed: bool

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "wallet_bid": self.wallet_bid,
            "creator_bid": self.creator_bid,
            "previous_available_credits": self.previous_available_credits,
            "available_credits": self.available_credits,
            "previous_expired_credits": self.previous_expired_credits,
            "expired_credits": self.expired_credits,
            "previous_status": self.previous_status,
            "status": self.status,
            "expire_ledger_count": self.expire_ledger_count,
            "expire_ledger_amount": self.expire_ledger_amount,
            "repair_action": self.repair_action,
            "repair_reason": self.repair_reason,
            "changed": self.changed,
        }


@dataclass(slots=True, frozen=True)
class ExpireLedgerBucketDriftRepairResult:
    """Capture the repair outcome for expire ledger bucket drift."""

    status: str
    creator_bid: str | None
    wallet_bucket_bid: str | None
    bucket_count: int
    repaired_bucket_count: int
    manual_review_count: int
    dry_run: bool
    buckets: list[ExpireLedgerBucketDriftRecord] = field(default_factory=list)

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "bucket_count": self.bucket_count,
            "repaired_bucket_count": self.repaired_bucket_count,
            "manual_review_count": self.manual_review_count,
            "dry_run": self.dry_run,
            "buckets": [bucket.to_payload() for bucket in self.buckets],
        }

    def __getitem__(self, key: str) -> Any:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class ExpiredCreditPackBucketRestoreRecord:
    """Record expired credit pack bucket restore details."""

    bill_order_bid: str
    creator_bid: str | None
    wallet_bid: str | None
    wallet_bucket_bid: str | None
    previous_available_credits: int | float
    available_credits: int | float
    previous_expired_credits: int | float
    expired_credits: int | float
    previous_status: int | None
    status: int | None
    restored_credits: int | float
    repair_action: str
    repair_reason: str
    changed: bool
    ledger_bid: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "bill_order_bid": self.bill_order_bid,
            "creator_bid": self.creator_bid,
            "wallet_bid": self.wallet_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "previous_available_credits": self.previous_available_credits,
            "available_credits": self.available_credits,
            "previous_expired_credits": self.previous_expired_credits,
            "expired_credits": self.expired_credits,
            "previous_status": self.previous_status,
            "status": self.status,
            "restored_credits": self.restored_credits,
            "repair_action": self.repair_action,
            "repair_reason": self.repair_reason,
            "changed": self.changed,
            "ledger_bid": self.ledger_bid,
        }


@dataclass(slots=True, frozen=True)
class ExpiredCreditPackBucketRestoreResult:
    """Capture credits restored from an expired credit-pack bucket."""

    status: str
    bill_order_bids: list[str]
    order_count: int
    repaired_bucket_count: int
    manual_review_count: int
    noop_count: int
    dry_run: bool
    buckets: list[ExpiredCreditPackBucketRestoreRecord] = field(default_factory=list)

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "bill_order_bids": list(self.bill_order_bids),
            "order_count": self.order_count,
            "repaired_bucket_count": self.repaired_bucket_count,
            "manual_review_count": self.manual_review_count,
            "noop_count": self.noop_count,
            "dry_run": self.dry_run,
            "buckets": [bucket.to_payload() for bucket in self.buckets],
        }

    def __getitem__(self, key: str) -> Any:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class ManualCreditGrantResult:
    """Capture the outcome of manual credit grant."""

    status: str
    creator_bid: str | None
    amount: int | float = 0
    wallet_bid: str | None = None
    wallet_bucket_bid: str | None = None
    ledger_bid: str | None = None
    expires_at: datetime | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "amount": self.amount,
            "wallet_bid": self.wallet_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "ledger_bid": self.ledger_bid,
            "expires_at": self.expires_at,
            "metadata_json": self.metadata_json,
        }

    def __getitem__(self, key: str) -> Any:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class ReservedGrantRepairRecord:
    """Record reserved grant repair details."""

    creator_bid: str
    bill_order_bid: str
    subscription_bid: str | None
    grant_ledger_bid: str
    wallet_bucket_bid: str | None
    consumable_from: datetime | None
    paid_at: datetime | None
    renewal_event_bids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "creator_bid": self.creator_bid,
            "bill_order_bid": self.bill_order_bid,
            "subscription_bid": self.subscription_bid,
            "grant_ledger_bid": self.grant_ledger_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "consumable_from": to_utc_iso(self.consumable_from),
            "paid_at": to_utc_iso(self.paid_at),
            "renewal_event_bids": list(self.renewal_event_bids),
        }

    def __getitem__(self, key: str) -> Any:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class RenewalStateDriftRepairResult:
    """Capture the repair outcome for renewal state drift."""

    status: str
    creator_bid: str | None
    creator_count: int
    stale_subscription_count: int
    stale_bucket_count: int
    updated_subscription_count: int
    expired_bucket_count: int
    expired_credits: int | float
    dry_run: bool
    overdue_reserved_grant_count: int = 0
    activatable_creator_count: int = 0
    activated_reserved_order_count: int = 0
    activated_creator_count: int = 0
    protected_creator_count: int = 0
    manual_review_creator_count: int = 0
    creator_bids: list[str] = field(default_factory=list)
    activatable_creator_bids: list[str] = field(default_factory=list)
    activated_creator_bids: list[str] = field(default_factory=list)
    protected_creator_bids: list[str] = field(default_factory=list)
    manual_review_creator_bids: list[str] = field(default_factory=list)
    overdue_reserved_grants: list[ReservedGrantRepairRecord] = field(
        default_factory=list
    )

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "creator_count": self.creator_count,
            "stale_subscription_count": self.stale_subscription_count,
            "stale_bucket_count": self.stale_bucket_count,
            "updated_subscription_count": self.updated_subscription_count,
            "expired_bucket_count": self.expired_bucket_count,
            "expired_credits": self.expired_credits,
            "dry_run": self.dry_run,
            "overdue_reserved_grant_count": self.overdue_reserved_grant_count,
            "activatable_creator_count": self.activatable_creator_count,
            "activated_reserved_order_count": self.activated_reserved_order_count,
            "activated_creator_count": self.activated_creator_count,
            "protected_creator_count": self.protected_creator_count,
            "manual_review_creator_count": self.manual_review_creator_count,
            "creator_bids": list(self.creator_bids),
            "activatable_creator_bids": list(self.activatable_creator_bids),
            "activated_creator_bids": list(self.activated_creator_bids),
            "protected_creator_bids": list(self.protected_creator_bids),
            "manual_review_creator_bids": list(self.manual_review_creator_bids),
            "overdue_reserved_grants": [
                record.to_payload() for record in self.overdue_reserved_grants
            ],
        }

    def __getitem__(self, key: str) -> Any:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


def _normalize_bid(value: object) -> str:
    return str(value or "").strip()


def _normalize_optional_metadata_bid(value: object) -> str:
    normalized = _normalize_bid(value)
    return "" if normalized.lower() == "null" else normalized


def _normalize_json_dict(payload: object) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _json_extract_text(column: Any, path: str) -> Any:
    bind = db.session.get_bind()
    dialect_name = bind.dialect.name.lower() if bind is not None else ""
    extracted = func.json_extract(column, path)
    if dialect_name == "mysql":
        return func.json_unquote(extracted)
    return extracted


def _sql_null_if_empty_or_json_null(value: Any) -> Any:
    text = func.trim(func.coalesce(value, ""))
    return case(
        (func.lower(text) == "null", None),
        (text == "", None),
        else_=text,
    )


def _extract_order_bid_from_renewal_event(event: BillingRenewalEvent) -> str:
    payload = _normalize_json_dict(event.payload_json)
    return _normalize_bid(payload.get("bill_order_bid"))


def _collect_overdue_reserved_order_bids(
    *, repaired_at: datetime, creator_bid: str
) -> set[str]:
    return {
        _normalize_bid(record.bill_order_bid)
        for record in _load_overdue_reserved_paid_order_records(
            repaired_at=repaired_at,
            creator_bid=creator_bid,
        )
        if _normalize_bid(record.bill_order_bid)
    }


def _load_overdue_reserved_paid_order_records(
    *,
    repaired_at: datetime,
    creator_bid: str = "",
    creator_bids: set[str] | None = None,
) -> list[ReservedGrantRepairRecord]:
    query = CreditLedgerEntry.query.filter(
        CreditLedgerEntry.deleted == 0,
        CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        CreditLedgerEntry.consumable_from.isnot(None),
        CreditLedgerEntry.consumable_from <= repaired_at,
    ).order_by(CreditLedgerEntry.consumable_from.asc(), CreditLedgerEntry.id.asc())
    normalized_creator_bid = _normalize_bid(creator_bid)
    if normalized_creator_bid:
        query = query.filter(CreditLedgerEntry.creator_bid == normalized_creator_bid)
    elif creator_bids is not None:
        if not creator_bids:
            return []
        query = query.filter(CreditLedgerEntry.creator_bid.in_(sorted(creator_bids)))

    ledgers = query.all()
    eligible_ledgers: list[tuple[CreditLedgerEntry, str, str, str]] = []
    missing_state_bucket_bids: set[str] = set()
    for ledger in ledgers:
        metadata = _normalize_json_dict(ledger.metadata_json)
        state = _normalize_bucket_credit_state(metadata.get("bucket_credit_state"))
        if state == "available":
            continue
        bill_order_bid = _extract_ledger_bill_order_bid(ledger, metadata)
        if not bill_order_bid:
            continue
        wallet_bucket_bid = _normalize_bid(ledger.wallet_bucket_bid)
        if not state and wallet_bucket_bid:
            missing_state_bucket_bids.add(wallet_bucket_bid)
        eligible_ledgers.append((ledger, bill_order_bid, state, wallet_bucket_bid))

    reserved_buckets_by_bid = _load_reserved_buckets_by_bid(missing_state_bucket_bids)
    candidate_ledgers: list[tuple[CreditLedgerEntry, str]] = []
    candidate_order_bids: set[str] = set()
    candidate_creator_bids: set[str] = set()
    for ledger, bill_order_bid, state, wallet_bucket_bid in eligible_ledgers:
        if not state:
            bucket = reserved_buckets_by_bid.get(wallet_bucket_bid)
            if bucket is None or not _bucket_matches_order_bid(bucket, bill_order_bid):
                continue
        candidate_ledgers.append((ledger, bill_order_bid))
        candidate_order_bids.add(bill_order_bid)
        candidate_creator_bids.add(_normalize_bid(ledger.creator_bid))

    if not candidate_ledgers:
        return []

    orders = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.bill_order_bid.in_(sorted(candidate_order_bids)),
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
        )
        .order_by(BillingOrder.id.asc())
        .all()
    )
    orders_by_bid = {
        _normalize_bid(order.bill_order_bid): order
        for order in orders
        if _normalize_bid(order.bill_order_bid)
    }
    if not orders_by_bid:
        return []

    renewal_events_by_order_bid: dict[str, list[str]] = {}
    if candidate_creator_bids:
        event_rows = (
            BillingRenewalEvent.query.filter(
                BillingRenewalEvent.deleted == 0,
                BillingRenewalEvent.creator_bid.in_(sorted(candidate_creator_bids)),
                BillingRenewalEvent.status.notin_(
                    [
                        BILLING_RENEWAL_EVENT_STATUS_CANCELED,
                        BILLING_RENEWAL_EVENT_STATUS_FAILED,
                    ]
                ),
            )
            .order_by(
                BillingRenewalEvent.scheduled_at.asc(), BillingRenewalEvent.id.asc()
            )
            .all()
        )
        for event in event_rows:
            bill_order_bid = _extract_order_bid_from_renewal_event(event)
            if not bill_order_bid or bill_order_bid not in orders_by_bid:
                continue
            renewal_event_bid = _normalize_bid(event.renewal_event_bid)
            if not renewal_event_bid:
                continue
            renewal_events_by_order_bid.setdefault(bill_order_bid, []).append(
                renewal_event_bid
            )

    records: list[ReservedGrantRepairRecord] = []
    for ledger, bill_order_bid in candidate_ledgers:
        order = orders_by_bid.get(bill_order_bid)
        if order is None:
            continue
        records.append(
            ReservedGrantRepairRecord(
                creator_bid=_normalize_bid(ledger.creator_bid),
                bill_order_bid=bill_order_bid,
                subscription_bid=_normalize_bid(order.subscription_bid) or None,
                grant_ledger_bid=_normalize_bid(ledger.ledger_bid),
                wallet_bucket_bid=_normalize_bid(ledger.wallet_bucket_bid) or None,
                consumable_from=ledger.consumable_from,
                paid_at=order.paid_at,
                renewal_event_bids=renewal_events_by_order_bid.get(bill_order_bid, []),
            )
        )
    return records


def _normalize_bucket_credit_state(value: Any) -> str:
    state = str(value or "").strip().lower()
    return "" if state == "null" else state


def _extract_ledger_bill_order_bid(
    ledger: CreditLedgerEntry, metadata: dict[str, Any] | None = None
) -> str:
    normalized_metadata = _normalize_json_dict(metadata or ledger.metadata_json)
    return _normalize_optional_metadata_bid(
        normalized_metadata.get("bill_order_bid")
    ) or _normalize_optional_metadata_bid(ledger.source_bid)


def _load_reserved_buckets_by_bid(
    wallet_bucket_bids: set[str],
) -> dict[str, CreditWalletBucket]:
    normalized_bids = sorted({_normalize_bid(bid) for bid in wallet_bucket_bids if bid})
    if not normalized_bids:
        return {}
    buckets = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.wallet_bucket_bid.in_(normalized_bids),
        )
        .order_by(CreditWalletBucket.id.desc())
        .all()
    )
    reserved_buckets_by_bid: dict[str, CreditWalletBucket] = {}
    for bucket in buckets:
        wallet_bucket_bid = _normalize_bid(bucket.wallet_bucket_bid)
        if (
            wallet_bucket_bid
            and wallet_bucket_bid not in reserved_buckets_by_bid
            and _to_decimal(bucket.reserved_credits) > _ZERO
        ):
            reserved_buckets_by_bid[wallet_bucket_bid] = bucket
    return reserved_buckets_by_bid


def _bucket_matches_order_bid(bucket: CreditWalletBucket, bill_order_bid: str) -> bool:
    normalized_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_order_bid:
        return False
    metadata = _normalize_json_dict(bucket.metadata_json)
    bucket_order_bids = {
        _normalize_optional_metadata_bid(bucket.source_bid),
        _normalize_optional_metadata_bid(metadata.get("bill_order_bid")),
        _normalize_optional_metadata_bid(metadata.get("billing_order_bid")),
    }
    return normalized_order_bid in bucket_order_bids


def _load_overdue_reserved_paid_order_creator_bids(
    *,
    repaired_at: datetime,
    creator_bid: str = "",
    limit: int | None = None,
) -> list[str]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_limit = int(limit) if limit is not None and int(limit) > 0 else None
    bill_order_bid_expr = func.coalesce(
        _sql_null_if_empty_or_json_null(
            _json_extract_text(CreditLedgerEntry.metadata_json, "$.bill_order_bid")
        ),
        _sql_null_if_empty_or_json_null(CreditLedgerEntry.source_bid),
    )
    bucket_source_order_bid_expr = _sql_null_if_empty_or_json_null(
        CreditWalletBucket.source_bid
    )
    bucket_bill_order_bid_expr = _sql_null_if_empty_or_json_null(
        _json_extract_text(CreditWalletBucket.metadata_json, "$.bill_order_bid")
    )
    bucket_billing_order_bid_expr = _sql_null_if_empty_or_json_null(
        _json_extract_text(CreditWalletBucket.metadata_json, "$.billing_order_bid")
    )
    state_expr = func.lower(
        func.trim(
            func.coalesce(
                _json_extract_text(
                    CreditLedgerEntry.metadata_json, "$.bucket_credit_state"
                ),
                "",
            )
        )
    )
    query = (
        db.session.query(CreditLedgerEntry.creator_bid)
        .join(
            BillingOrder,
            BillingOrder.bill_order_bid == bill_order_bid_expr,
        )
        .outerjoin(
            CreditWalletBucket,
            (
                (CreditWalletBucket.deleted == 0)
                & (CreditLedgerEntry.wallet_bucket_bid != "")
                & (CreditWalletBucket.wallet_bucket_bid != "")
                & (
                    CreditWalletBucket.wallet_bucket_bid
                    == CreditLedgerEntry.wallet_bucket_bid
                )
            ),
        )
        .filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CreditLedgerEntry.consumable_from.isnot(None),
            CreditLedgerEntry.consumable_from <= repaired_at,
            state_expr != "available",
            or_(
                ~state_expr.in_(["", "null"]),
                (
                    (CreditWalletBucket.reserved_credits > _ZERO)
                    & (
                        (bucket_source_order_bid_expr == bill_order_bid_expr)
                        | (bucket_bill_order_bid_expr == bill_order_bid_expr)
                        | (bucket_billing_order_bid_expr == bill_order_bid_expr)
                    )
                ),
            ),
            BillingOrder.deleted == 0,
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
        )
    )
    if normalized_creator_bid:
        query = query.filter(CreditLedgerEntry.creator_bid == normalized_creator_bid)
    query = query.distinct().order_by(CreditLedgerEntry.creator_bid.asc())
    if normalized_limit is not None:
        query = query.limit(normalized_limit)
    return [_normalize_bid(row[0]) for row in query.all() if _normalize_bid(row[0])]


def _build_legacy_expire_ledger_idempotency_key(wallet_bucket_bid: str) -> str:
    return f"expire:{str(wallet_bucket_bid or '').strip()}"


def _build_expire_ledger_idempotency_key(
    wallet_bucket_bid: str,
    *,
    effective_to: datetime | None,
) -> str:
    normalized_bucket_bid = str(wallet_bucket_bid or "").strip()
    if effective_to is None:
        return _build_legacy_expire_ledger_idempotency_key(normalized_bucket_bid)
    return (
        f"{_build_legacy_expire_ledger_idempotency_key(normalized_bucket_bid)}:"
        f"{effective_to.strftime('%Y%m%d%H%M%S')}"
    )


def _is_matching_expire_ledger_for_bucket(
    ledger: CreditLedgerEntry,
    bucket: CreditWalletBucket,
) -> bool:
    normalized_bucket_bid = str(bucket.wallet_bucket_bid or "").strip()
    normalized_creator_bid = str(bucket.creator_bid or "").strip()
    if str(ledger.wallet_bucket_bid or "").strip() != normalized_bucket_bid:
        return False
    if str(ledger.creator_bid or "").strip() != normalized_creator_bid:
        return False

    cycle_key = _build_expire_ledger_idempotency_key(
        normalized_bucket_bid,
        effective_to=bucket.effective_to,
    )
    if ledger.idempotency_key == cycle_key:
        return True

    legacy_key = _build_legacy_expire_ledger_idempotency_key(normalized_bucket_bid)
    return (
        ledger.idempotency_key == legacy_key
        and ledger.expires_at == bucket.effective_to
    )


def calculate_credit_wallet_snapshot_values(
    wallet: CreditWallet,
    *,
    snapshot_at: datetime | None = None,
) -> tuple[Decimal, Decimal]:
    """Calculate wallet balances without mutating the ORM wallet row."""
    resolved_snapshot_at = snapshot_at or now_utc()
    rows = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.wallet_bid == wallet.wallet_bid,
        )
        .order_by(CreditWalletBucket.id.asc())
        .all()
    )
    has_active_subscription = (
        load_primary_active_subscription(
            wallet.creator_bid,
            as_of=resolved_snapshot_at,
        )
        is not None
    )
    current_consumable_rows = [
        row
        for row in rows
        if int(row.status or 0) == CREDIT_BUCKET_STATUS_ACTIVE
        and _to_decimal(row.available_credits) > _ZERO
        and (row.effective_from is None or row.effective_from <= resolved_snapshot_at)
        and (row.effective_to is None or row.effective_to > resolved_snapshot_at)
        and (
            has_active_subscription
            or not wallet_bucket_requires_active_subscription(
                row,
                load_order_type=load_billing_order_type_by_bid,
            )
        )
    ]
    available_credits = sum(
        (_to_decimal(row.available_credits) for row in current_consumable_rows),
        start=_ZERO,
    )
    reserved_credits = sum(
        (_to_decimal(row.reserved_credits) for row in rows),
        start=_ZERO,
    )
    return (
        _quantize_credit_amount(available_credits),
        _quantize_credit_amount(reserved_credits),
    )


def refresh_credit_wallet_snapshot(
    wallet: CreditWallet,
    *,
    snapshot_at: datetime | None = None,
) -> CreditWallet:
    """Rebuild wallet balances from the current bucket snapshot table."""
    available_credits, reserved_credits = calculate_credit_wallet_snapshot_values(
        wallet,
        snapshot_at=snapshot_at,
    )
    wallet.available_credits = available_credits
    wallet.reserved_credits = reserved_credits
    return wallet


def persist_credit_wallet_snapshot(
    wallet: CreditWallet,
    *,
    available_credits: Decimal | Any,
    reserved_credits: Decimal | Any,
    lifetime_granted_credits: Decimal | Any | None = None,
    lifetime_consumed_credits: Decimal | Any | None = None,
    last_settled_usage_id: int | None = None,
    updated_at: datetime | None = None,
) -> CreditWallet:
    """Persist a wallet snapshot with optimistic version checking."""
    if wallet.id is None:
        db.session.flush()
    expected_version = int(wallet.version or 0)
    next_version = expected_version + 1
    values: dict[str, Any] = {
        "available_credits": _quantize_credit_amount(available_credits),
        "reserved_credits": _quantize_credit_amount(reserved_credits),
        "version": next_version,
        "updated_at": updated_at or now_utc(),
    }
    if lifetime_granted_credits is not None:
        values["lifetime_granted_credits"] = _quantize_credit_amount(
            lifetime_granted_credits
        )
    if lifetime_consumed_credits is not None:
        values["lifetime_consumed_credits"] = _quantize_credit_amount(
            lifetime_consumed_credits
        )
    if last_settled_usage_id is not None:
        values["last_settled_usage_id"] = int(last_settled_usage_id)

    updated_rows = CreditWallet.query.filter(
        CreditWallet.deleted == 0,
        CreditWallet.id == wallet.id,
        CreditWallet.version == expected_version,
    ).update(values, synchronize_session=False)
    if updated_rows != 1:
        message = "credit_wallet_version_conflict"
        raise RuntimeError(message)

    wallet.available_credits = values["available_credits"]
    wallet.reserved_credits = values["reserved_credits"]
    wallet.version = next_version
    wallet.updated_at = values["updated_at"]
    if lifetime_granted_credits is not None:
        wallet.lifetime_granted_credits = values["lifetime_granted_credits"]
    if lifetime_consumed_credits is not None:
        wallet.lifetime_consumed_credits = values["lifetime_consumed_credits"]
    if last_settled_usage_id is not None:
        wallet.last_settled_usage_id = values["last_settled_usage_id"]
    return wallet


def resolve_bucket_source_type_for_category(bucket_category: int | None) -> int:
    normalized_category = resolve_runtime_credit_bucket_category(
        bucket_category=bucket_category
    )
    if normalized_category == CREDIT_BUCKET_CATEGORY_TOPUP:
        return CREDIT_SOURCE_TYPE_TOPUP
    return CREDIT_SOURCE_TYPE_SUBSCRIPTION


def load_primary_credit_bucket_by_category(
    creator_bid: str,
    *,
    bucket_category: int,
) -> CreditWalletBucket | None:
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_category = resolve_runtime_credit_bucket_category(
        bucket_category=bucket_category
    )
    if (
        not normalized_creator_bid
        or normalized_category not in _SINGLE_BUCKET_CATEGORIES
    ):
        return None

    rows = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid == normalized_creator_bid,
        )
        .order_by(
            CreditWalletBucket.created_at.asc(),
            CreditWalletBucket.id.asc(),
        )
        .all()
    )
    candidates = [
        row
        for row in rows
        if int(row.source_type or 0) != CREDIT_SOURCE_TYPE_MANUAL
        and resolve_wallet_bucket_runtime_category(
            row,
            load_order_type=load_billing_order_type_by_bid,
        )
        == normalized_category
    ]
    if not candidates:
        return None

    def _sort_key(row: CreditWalletBucket) -> tuple[int, int, datetime, int]:
        current_status = int(row.status or 0)
        if current_status in (
            CREDIT_BUCKET_STATUS_ACTIVE,
            CREDIT_BUCKET_STATUS_EXHAUSTED,
        ):
            status_rank = 0
        elif current_status == CREDIT_BUCKET_STATUS_EXPIRED:
            status_rank = 1
        else:
            status_rank = 2
        has_balance_rank = (
            0
            if (
                _to_decimal(row.available_credits) > _ZERO
                or _to_decimal(row.reserved_credits) > _ZERO
            )
            else 1
        )
        return (
            status_rank,
            has_balance_rank,
            row.created_at or NAIVE_DATETIME_MIN,
            int(row.id or 0),
        )

    candidates.sort(key=_sort_key)
    return candidates[0]


def load_or_create_credit_bucket_by_category(
    app: Flask,
    *,
    wallet: CreditWallet,
    creator_bid: str,
    bucket_category: int,
    source_bid: str,
    metadata: dict[str, Any] | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> CreditWalletBucket:
    normalized_category = resolve_runtime_credit_bucket_category(
        bucket_category=bucket_category
    )
    bucket = load_primary_credit_bucket_by_category(
        creator_bid,
        bucket_category=normalized_category,
    )
    if bucket is not None:
        return bucket

    bucket = CreditWalletBucket(
        wallet_bucket_bid=generate_id(app),
        wallet_bid=wallet.wallet_bid,
        creator_bid=str(creator_bid or "").strip(),
        bucket_category=normalized_category,
        source_type=resolve_bucket_source_type_for_category(normalized_category),
        source_bid=str(source_bid or "").strip(),
        priority=resolve_credit_bucket_priority(normalized_category),
        original_credits=_ZERO,
        available_credits=_ZERO,
        reserved_credits=_ZERO,
        consumed_credits=_ZERO,
        expired_credits=_ZERO,
        effective_from=effective_from,
        effective_to=effective_to,
        status=CREDIT_BUCKET_STATUS_EXHAUSTED,
        metadata_json=dict(metadata or {}),
    )
    db.session.add(bucket)
    return bucket


def rebuild_credit_wallet_snapshots(
    app: Flask,
    *,
    creator_bid: str = "",
    wallet_bid: str = "",
    dry_run: bool = False,
) -> WalletSnapshotRebuildResult:
    """Rebuild wallet snapshots from bucket rows for one or many creators."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_wallet_bid = str(wallet_bid or "").strip()
    with app.app_context():
        query = CreditWallet.query.filter(CreditWallet.deleted == 0)
        if normalized_creator_bid:
            query = query.filter(CreditWallet.creator_bid == normalized_creator_bid)
        if normalized_wallet_bid:
            query = query.filter(CreditWallet.wallet_bid == normalized_wallet_bid)
        wallets = query.order_by(CreditWallet.id.asc()).all()
        if not wallets:
            return WalletSnapshotRebuildResult(
                status="noop",
                creator_bid=normalized_creator_bid or None,
                wallet_bid=normalized_wallet_bid or None,
                wallet_count=0,
                changed_wallet_count=0,
                dry_run=dry_run,
                wallets=[],
            )

        rebuilt_at = now_utc()
        payload_wallets: list[WalletSnapshotRecord] = []
        changed_wallet_count = 0
        for wallet in wallets:
            previous_available = _quantize_credit_amount(wallet.available_credits)
            previous_reserved = _quantize_credit_amount(wallet.reserved_credits)
            next_available, next_reserved = calculate_credit_wallet_snapshot_values(
                wallet,
                snapshot_at=rebuilt_at,
            )
            available_delta = _quantize_credit_amount(
                next_available - previous_available
            )
            reserved_delta = _quantize_credit_amount(next_reserved - previous_reserved)
            changed = available_delta != _ZERO or reserved_delta != _ZERO
            if changed:
                changed_wallet_count += 1
            if not dry_run:
                persist_credit_wallet_snapshot(
                    wallet,
                    available_credits=next_available,
                    reserved_credits=next_reserved,
                    updated_at=rebuilt_at,
                )
            payload_wallets.append(
                WalletSnapshotRecord(
                    wallet_bid=wallet.wallet_bid,
                    creator_bid=wallet.creator_bid,
                    available_credits=_credit_decimal_to_number(next_available),
                    reserved_credits=_credit_decimal_to_number(next_reserved),
                    previous_available_credits=_credit_decimal_to_number(
                        previous_available
                    ),
                    previous_reserved_credits=_credit_decimal_to_number(
                        previous_reserved
                    ),
                    available_credits_delta=_credit_decimal_to_number(available_delta),
                    reserved_credits_delta=_credit_decimal_to_number(reserved_delta),
                    changed=changed,
                )
            )

        if not dry_run:
            db.session.commit()
        return WalletSnapshotRebuildResult(
            status="dry_run" if dry_run else "rebuilt",
            creator_bid=normalized_creator_bid or None,
            wallet_bid=normalized_wallet_bid or None,
            wallet_count=len(payload_wallets),
            changed_wallet_count=changed_wallet_count,
            dry_run=dry_run,
            wallets=payload_wallets,
        )


def repair_renewal_state_drift(
    app: Flask,
    *,
    creator_bid: str = "",
    repair_before: datetime | None = None,
    limit: int | None = None,
    dry_run: bool = True,
) -> RenewalStateDriftRepairResult:
    """Repair creators whose subscription or bucket state stayed past cycle end."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_limit = int(limit) if limit is not None and int(limit) > 0 else None
    repaired_at = repair_before or now_utc()

    with app.app_context():
        stale_subscription_query = BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            BillingSubscription.current_period_end_at.isnot(None),
            BillingSubscription.current_period_end_at <= repaired_at,
        )
        stale_bucket_query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
            CreditWalletBucket.effective_to.isnot(None),
            CreditWalletBucket.effective_to <= repaired_at,
            CreditWalletBucket.available_credits > _ZERO,
        )
        if normalized_creator_bid:
            stale_subscription_query = stale_subscription_query.filter(
                BillingSubscription.creator_bid == normalized_creator_bid
            )
            stale_bucket_query = stale_bucket_query.filter(
                CreditWalletBucket.creator_bid == normalized_creator_bid
            )

        stale_subscriptions = stale_subscription_query.order_by(
            BillingSubscription.current_period_end_at.asc(),
            BillingSubscription.created_at.asc(),
            BillingSubscription.id.asc(),
        ).all()
        stale_buckets = stale_bucket_query.order_by(
            CreditWalletBucket.effective_to.asc(),
            CreditWalletBucket.created_at.asc(),
            CreditWalletBucket.id.asc(),
        ).all()
        creator_bids: list[str] = []
        seen_creator_bids: set[str] = set()
        for row in stale_subscriptions:
            candidate = str(row.creator_bid or "").strip()
            if candidate and candidate not in seen_creator_bids:
                seen_creator_bids.add(candidate)
                creator_bids.append(candidate)
        for row in stale_buckets:
            candidate = str(row.creator_bid or "").strip()
            if candidate and candidate not in seen_creator_bids:
                seen_creator_bids.add(candidate)
                creator_bids.append(candidate)
        remaining_limit = None
        if normalized_limit is not None:
            remaining_limit = max(normalized_limit - len(creator_bids), 0)
        overdue_reserved_creator_bids: list[str] = []
        if remaining_limit is None or remaining_limit > 0:
            overdue_reserved_creator_bids = (
                _load_overdue_reserved_paid_order_creator_bids(
                    repaired_at=repaired_at,
                    creator_bid=normalized_creator_bid,
                    limit=remaining_limit,
                )
            )
        for candidate in overdue_reserved_creator_bids:
            if candidate and candidate not in seen_creator_bids:
                seen_creator_bids.add(candidate)
                creator_bids.append(candidate)
        if normalized_limit is not None:
            creator_bids = creator_bids[:normalized_limit]

        if not creator_bids:
            return RenewalStateDriftRepairResult(
                status="noop",
                creator_bid=normalized_creator_bid or None,
                creator_count=0,
                stale_subscription_count=0,
                stale_bucket_count=0,
                updated_subscription_count=0,
                expired_bucket_count=0,
                expired_credits=0,
                dry_run=dry_run,
                overdue_reserved_grant_count=0,
                activatable_creator_count=0,
                activated_reserved_order_count=0,
                activated_creator_count=0,
                protected_creator_count=0,
                manual_review_creator_count=0,
                creator_bids=[],
                activatable_creator_bids=[],
                activated_creator_bids=[],
                protected_creator_bids=[],
                manual_review_creator_bids=[],
                overdue_reserved_grants=[],
            )

        scoped_creator_bids = set(creator_bids)
        overdue_reserved_grants = _load_overdue_reserved_paid_order_records(
            repaired_at=repaired_at,
            creator_bid=normalized_creator_bid,
            creator_bids=scoped_creator_bids,
        )
        scoped_stale_subscription_count = sum(
            1
            for row in stale_subscriptions
            if str(row.creator_bid or "").strip() in scoped_creator_bids
        )
        scoped_stale_bucket_count = sum(
            1
            for row in stale_buckets
            if str(row.creator_bid or "").strip() in scoped_creator_bids
        )
        scoped_overdue_reserved_grants = [
            record
            for record in overdue_reserved_grants
            if _normalize_bid(record.creator_bid) in scoped_creator_bids
        ]
        overdue_reserved_order_bids_by_creator: dict[str, list[str]] = {}
        for record in scoped_overdue_reserved_grants:
            overdue_reserved_order_bids_by_creator.setdefault(
                _normalize_bid(record.creator_bid), []
            ).append(record.bill_order_bid)

        expired_bucket_count = 0
        expired_credits = 0.0
        updated_subscription_count = 0
        activated_reserved_order_count = 0
        activatable_creator_bids: list[str] = []
        activated_creator_bids: list[str] = []
        protected_creator_bids: list[str] = []
        manual_review_creator_bids: list[str] = []
        candidate_orders_by_creator: dict[str, list[BillingOrder]] = {}

        from .reserved_renewal_activation import (
            IncompleteReservedGrantActivationError,
            validate_reserved_renewal_cycle_activation,
        )

        # Local import avoids a circular dependency with subscriptions.py.
        from .subscriptions import grant_paid_order_credits

        for target_creator_bid in creator_bids:
            candidate_order_bids = sorted(
                {
                    order_bid
                    for order_bid in overdue_reserved_order_bids_by_creator.get(
                        target_creator_bid, []
                    )
                    if _normalize_bid(order_bid)
                }
            )
            if not candidate_order_bids:
                continue
            candidate_orders = (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.creator_bid == target_creator_bid,
                    BillingOrder.bill_order_bid.in_(candidate_order_bids),
                    BillingOrder.status == BILLING_ORDER_STATUS_PAID,
                )
                .order_by(
                    BillingOrder.paid_at.asc(),
                    BillingOrder.created_at.asc(),
                    BillingOrder.id.asc(),
                )
                .all()
            )
            candidate_orders_by_creator[target_creator_bid] = candidate_orders
            try:
                for order in candidate_orders:
                    validate_reserved_renewal_cycle_activation(order)
            except IncompleteReservedGrantActivationError:
                manual_review_creator_bids.append(target_creator_bid)
                protected_creator_bids.append(target_creator_bid)
                continue
            if candidate_orders:
                activatable_creator_bids.append(target_creator_bid)

        if not dry_run:
            for target_creator_bid in creator_bids:
                candidate_orders = candidate_orders_by_creator.get(
                    target_creator_bid, []
                )
                if target_creator_bid in set(manual_review_creator_bids):
                    continue
                if candidate_orders:
                    reserved_order_bids_before = _collect_overdue_reserved_order_bids(
                        repaired_at=repaired_at,
                        creator_bid=target_creator_bid,
                    )
                    try:
                        with unit_of_work():
                            for order in candidate_orders:
                                grant_paid_order_credits(app, order)
                    except IncompleteReservedGrantActivationError:
                        protected_creator_bids.append(target_creator_bid)
                        manual_review_creator_bids.append(target_creator_bid)
                        continue
                    reserved_order_bids_after = _collect_overdue_reserved_order_bids(
                        repaired_at=repaired_at,
                        creator_bid=target_creator_bid,
                    )
                    activated_order_bids = (
                        reserved_order_bids_before - reserved_order_bids_after
                    )
                    if activated_order_bids:
                        activated_reserved_order_count += len(activated_order_bids)
                        activated_creator_bids.append(target_creator_bid)

                remaining_reserved_records = _load_overdue_reserved_paid_order_records(
                    repaired_at=repaired_at,
                    creator_bid=target_creator_bid,
                )
                if remaining_reserved_records:
                    protected_creator_bids.append(target_creator_bid)
                    continue

                expiration_payload = expire_credit_wallet_buckets(
                    app,
                    creator_bid=target_creator_bid,
                    expire_before=repaired_at,
                )
                expired_bucket_count += int(expiration_payload.bucket_count or 0)
                expired_credits += float(expiration_payload.expired_credits or 0)

            protected_creator_bid_set = set(protected_creator_bids)
            changed_subscriptions = (
                BillingSubscription.query.filter(
                    BillingSubscription.deleted == 0,
                    BillingSubscription.creator_bid.in_(creator_bids),
                    BillingSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                    BillingSubscription.current_period_end_at.isnot(None),
                    BillingSubscription.current_period_end_at <= repaired_at,
                )
                .order_by(BillingSubscription.id.asc())
                .all()
            )
            if changed_subscriptions:
                with unit_of_work():
                    for subscription in changed_subscriptions:
                        if (
                            _normalize_bid(subscription.creator_bid)
                            in protected_creator_bid_set
                        ):
                            continue
                        subscription.status = BILLING_SUBSCRIPTION_STATUS_EXPIRED
                        subscription.updated_at = repaired_at
                        db.session.add(subscription)
                        updated_subscription_count += 1

        return RenewalStateDriftRepairResult(
            status="dry_run" if dry_run else "repaired",
            creator_bid=normalized_creator_bid or None,
            creator_count=len(creator_bids),
            stale_subscription_count=scoped_stale_subscription_count,
            stale_bucket_count=scoped_stale_bucket_count,
            updated_subscription_count=updated_subscription_count,
            expired_bucket_count=expired_bucket_count,
            expired_credits=expired_credits,
            dry_run=dry_run,
            overdue_reserved_grant_count=len(scoped_overdue_reserved_grants),
            activatable_creator_count=len(sorted(set(activatable_creator_bids))),
            activated_reserved_order_count=activated_reserved_order_count,
            activated_creator_count=len(sorted(set(activated_creator_bids))),
            protected_creator_count=len(sorted(set(protected_creator_bids))),
            manual_review_creator_count=len(sorted(set(manual_review_creator_bids))),
            creator_bids=creator_bids,
            activatable_creator_bids=sorted(set(activatable_creator_bids)),
            activated_creator_bids=sorted(set(activated_creator_bids)),
            protected_creator_bids=sorted(set(protected_creator_bids)),
            manual_review_creator_bids=sorted(set(manual_review_creator_bids)),
            overdue_reserved_grants=scoped_overdue_reserved_grants,
        )


def repair_credit_bucket_runtime_statuses(
    app: Flask,
    *,
    creator_bid: str = "",
    wallet_bucket_bid: str = "",
) -> dict[str, Any]:
    """Repair buckets whose runtime status no longer matches their live balance."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_wallet_bucket_bid = str(wallet_bucket_bid or "").strip()
    repaired_at = now_utc()
    with app.app_context():
        query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_EXPIRED,
        )
        if normalized_creator_bid:
            query = query.filter(
                CreditWalletBucket.creator_bid == normalized_creator_bid
            )
        if normalized_wallet_bucket_bid:
            query = query.filter(
                CreditWalletBucket.wallet_bucket_bid == normalized_wallet_bucket_bid
            )
        rows = query.order_by(
            CreditWalletBucket.created_at.asc(),
            CreditWalletBucket.id.asc(),
        ).all()

        buckets = [
            row
            for row in rows
            if (
                _to_decimal(row.available_credits) > _ZERO
                or _to_decimal(row.reserved_credits) > _ZERO
            )
            and (row.effective_to is None or row.effective_to > repaired_at)
        ]
        if not buckets:
            return {
                "status": "noop",
                "creator_bid": normalized_creator_bid or None,
                "wallet_bucket_bid": normalized_wallet_bucket_bid or None,
                "repaired_bucket_count": 0,
                "repaired_bucket_bids": [],
            }

        wallets: dict[str, CreditWallet] = {}
        repaired_bucket_bids: list[str] = []
        for bucket in buckets:
            bucket.status = CREDIT_BUCKET_STATUS_EXHAUSTED
            sync_credit_bucket_status(bucket)
            bucket.updated_at = repaired_at
            db.session.add(bucket)
            repaired_bucket_bids.append(bucket.wallet_bucket_bid)

            wallet = wallets.get(bucket.wallet_bid)
            if wallet is None:
                wallet = _load_credit_wallet_by_wallet_bid(bucket.wallet_bid)
                if wallet is not None:
                    wallets[bucket.wallet_bid] = wallet

        for wallet in wallets.values():
            refresh_credit_wallet_snapshot(wallet)
            persist_credit_wallet_snapshot(
                wallet,
                available_credits=wallet.available_credits,
                reserved_credits=wallet.reserved_credits,
                updated_at=repaired_at,
            )

        db.session.commit()
        return {
            "status": "repaired",
            "creator_bid": normalized_creator_bid or None,
            "wallet_bucket_bid": normalized_wallet_bucket_bid or None,
            "repaired_bucket_count": len(repaired_bucket_bids),
            "repaired_bucket_bids": repaired_bucket_bids,
        }


def grant_refund_return_credits(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | Any,
    refund_bid: str,
    metadata: dict[str, Any] | None = None,
    effective_from: datetime | None = None,
) -> RefundReturnCreditsResult:
    """Grant refunded credits back as a new subscription/topup bucket."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_refund_bid = str(refund_bid or "").strip()
    normalized_amount = _quantize_credit_amount(amount)
    if (
        not normalized_creator_bid
        or not normalized_refund_bid
        or normalized_amount <= _ZERO
    ):
        return RefundReturnCreditsResult(
            status="noop",
            creator_bid=normalized_creator_bid or None,
            source_bid=normalized_refund_bid or None,
            amount=_credit_decimal_to_number(normalized_amount),
        )

    with app.app_context():
        idempotency_key = f"refund_return:{normalized_refund_bid}"
        existing_entry = (
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.creator_bid == normalized_creator_bid,
                CreditLedgerEntry.idempotency_key == idempotency_key,
            )
            .order_by(CreditLedgerEntry.id.desc())
            .first()
        )
        if existing_entry is not None:
            return RefundReturnCreditsResult(
                status="already_granted",
                creator_bid=normalized_creator_bid,
                source_bid=normalized_refund_bid,
                wallet_bucket_bid=existing_entry.wallet_bucket_bid,
                ledger_bid=existing_entry.ledger_bid,
            )

        wallet = _load_or_create_credit_wallet(app, normalized_creator_bid)
        now = effective_from or now_utc()
        bucket_category = resolve_runtime_credit_bucket_category(
            source_type=CREDIT_SOURCE_TYPE_REFUND,
            source_bid=normalized_refund_bid,
            metadata=metadata,
            load_order_type=load_billing_order_type_by_bid,
        )
        resolved_effective_to = None
        if bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP:
            from .subscriptions import load_effective_topup_subscription

            subscription = load_effective_topup_subscription(
                normalized_creator_bid,
                as_of=now,
            )
            if subscription is not None:
                resolved_effective_to = subscription.current_period_end_at

        bucket = load_or_create_credit_bucket_by_category(
            app,
            wallet=wallet,
            creator_bid=normalized_creator_bid,
            bucket_category=bucket_category,
            source_bid=normalized_refund_bid,
            metadata={
                "refund_return": True,
                **(metadata or {}),
            },
            effective_from=now,
            effective_to=resolved_effective_to,
        )
        current_available = _to_decimal(bucket.available_credits)
        current_original = _to_decimal(bucket.original_credits)
        current_reserved = _to_decimal(bucket.reserved_credits)
        bucket.wallet_bid = wallet.wallet_bid
        bucket.bucket_category = bucket_category
        bucket.source_type = resolve_bucket_source_type_for_category(bucket_category)
        bucket.source_bid = normalized_refund_bid
        bucket.priority = resolve_credit_bucket_priority(bucket_category)
        bucket.original_credits = _quantize_credit_amount(
            current_original + normalized_amount
        )
        bucket.available_credits = _quantize_credit_amount(
            current_available + normalized_amount
        )
        bucket.reserved_credits = _quantize_credit_amount(current_reserved)
        if current_available > _ZERO or current_reserved > _ZERO:
            if bucket.effective_from is None or bucket.effective_from > now:
                bucket.effective_from = now
        else:
            bucket.effective_from = now
        if resolved_effective_to is not None:
            bucket.effective_to = resolved_effective_to
        bucket.metadata_json = {
            **(bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}),
            "refund_return": True,
            **(metadata or {}),
        }
        bucket.updated_at = now
        sync_credit_bucket_status(bucket)
        db.session.add(bucket)
        refresh_credit_wallet_snapshot(wallet, snapshot_at=now)
        ledger_entry = CreditLedgerEntry(
            ledger_bid=generate_id(app),
            creator_bid=normalized_creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_REFUND,
            source_type=CREDIT_SOURCE_TYPE_REFUND,
            source_bid=normalized_refund_bid,
            idempotency_key=idempotency_key,
            amount=normalized_amount,
            balance_after=_quantize_credit_amount(wallet.available_credits),
            expires_at=None,
            consumable_from=now,
            metadata_json={
                "refund_return": True,
                **(metadata or {}),
            },
        )
        persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            updated_at=now,
        )
        db.session.add(ledger_entry)
        db.session.commit()
        return RefundReturnCreditsResult(
            status="granted",
            creator_bid=normalized_creator_bid,
            source_bid=normalized_refund_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            ledger_bid=ledger_entry.ledger_bid,
        )


def adjust_credit_wallet_balance(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | Any,
    note: str = "",
    operator_user_bid: str = "",
) -> BillingLedgerAdjustResultDTO:
    """Apply a manual admin ledger adjustment through credit buckets."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_amount = _quantize_credit_amount(amount)
    normalized_note = str(note or "").strip()
    normalized_operator_user_bid = str(operator_user_bid or "").strip()
    if not normalized_creator_bid or normalized_amount == _ZERO:
        return BillingLedgerAdjustResultDTO(
            status="noop",
            creator_bid=normalized_creator_bid or None,
            amount=_credit_decimal_to_number(normalized_amount),
        )

    with app.app_context():
        wallet = _load_or_create_credit_wallet(app, normalized_creator_bid)
        adjustment_bid = generate_id(app)
        adjusted_at = now_utc()
        metadata = {
            "adjustment_bid": adjustment_bid,
            "note": normalized_note,
            "operator_user_bid": normalized_operator_user_bid,
        }

        if normalized_amount > _ZERO:
            bucket = CreditWalletBucket(
                wallet_bucket_bid=generate_id(app),
                wallet_bid=wallet.wallet_bid,
                creator_bid=normalized_creator_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid=adjustment_bid,
                priority=resolve_credit_bucket_priority(
                    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
                ),
                original_credits=normalized_amount,
                available_credits=normalized_amount,
                reserved_credits=_ZERO,
                consumed_credits=_ZERO,
                expired_credits=_ZERO,
                effective_from=adjusted_at,
                effective_to=None,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    **metadata,
                    "direction": "credit",
                },
            )
            db.session.add(bucket)
            sync_credit_bucket_status(bucket)
            refresh_credit_wallet_snapshot(wallet)
            ledger_entry = CreditLedgerEntry(
                ledger_bid=generate_id(app),
                creator_bid=normalized_creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid=adjustment_bid,
                idempotency_key=f"adjustment:{adjustment_bid}:{bucket.wallet_bucket_bid}",
                amount=normalized_amount,
                balance_after=_quantize_credit_amount(wallet.available_credits),
                expires_at=None,
                consumable_from=adjusted_at,
                metadata_json={
                    **metadata,
                    "direction": "credit",
                },
            )
            persist_credit_wallet_snapshot(
                wallet,
                available_credits=wallet.available_credits,
                reserved_credits=wallet.reserved_credits,
                updated_at=adjusted_at,
            )
            db.session.add(ledger_entry)
            db.session.commit()
            return BillingLedgerAdjustResultDTO(
                status="adjusted",
                adjustment_bid=adjustment_bid,
                creator_bid=normalized_creator_bid,
                amount=_credit_decimal_to_number(normalized_amount),
                wallet=BillingWalletRefDTO(
                    wallet_bid=wallet.wallet_bid,
                    available_credits=_credit_decimal_to_number(
                        wallet.available_credits
                    ),
                    reserved_credits=_credit_decimal_to_number(wallet.reserved_credits),
                ),
                wallet_bucket_bids=[bucket.wallet_bucket_bid],
                ledger_bids=[ledger_entry.ledger_bid],
            )

        remaining = normalized_amount.copy_abs()
        buckets = _load_adjustable_credit_buckets(
            normalized_creator_bid,
            adjustment_at=adjusted_at,
        )
        total_available = sum(
            (_to_decimal(bucket.available_credits) for bucket in buckets),
            start=_ZERO,
        )
        if total_available < remaining:
            raise_error("server.billing.creditInsufficient")

        wallet_bucket_bids: list[str] = []
        ledger_bids: list[str] = []
        for bucket in buckets:
            if remaining <= _ZERO:
                break
            available = _to_decimal(bucket.available_credits)
            if available <= _ZERO:
                continue

            adjusted_amount = _quantize_credit_amount(min(available, remaining))
            bucket.available_credits = _quantize_credit_amount(
                available - adjusted_amount
            )
            bucket.consumed_credits = _quantize_credit_amount(
                _to_decimal(bucket.consumed_credits) + adjusted_amount
            )
            sync_credit_bucket_status(bucket)
            db.session.add(bucket)
            refresh_credit_wallet_snapshot(wallet)
            ledger_entry = CreditLedgerEntry(
                ledger_bid=generate_id(app),
                creator_bid=normalized_creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid=adjustment_bid,
                idempotency_key=f"adjustment:{adjustment_bid}:{bucket.wallet_bucket_bid}",
                amount=-adjusted_amount,
                balance_after=_quantize_credit_amount(wallet.available_credits),
                expires_at=bucket.effective_to,
                consumable_from=bucket.effective_from,
                metadata_json={
                    **metadata,
                    "direction": "debit",
                },
            )
            persist_credit_wallet_snapshot(
                wallet,
                available_credits=wallet.available_credits,
                reserved_credits=wallet.reserved_credits,
                updated_at=adjusted_at,
            )
            db.session.add(ledger_entry)
            wallet_bucket_bids.append(bucket.wallet_bucket_bid)
            ledger_bids.append(ledger_entry.ledger_bid)
            remaining -= adjusted_amount

        db.session.commit()
        return BillingLedgerAdjustResultDTO(
            status="adjusted",
            adjustment_bid=adjustment_bid,
            creator_bid=normalized_creator_bid,
            amount=_credit_decimal_to_number(normalized_amount),
            wallet=BillingWalletRefDTO(
                wallet_bid=wallet.wallet_bid,
                available_credits=_credit_decimal_to_number(wallet.available_credits),
                reserved_credits=_credit_decimal_to_number(wallet.reserved_credits),
            ),
            wallet_bucket_bids=wallet_bucket_bids,
            ledger_bids=ledger_bids,
        )


def grant_manual_credit_wallet_balance(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | Any,
    source_bid: str = "",
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    ledger_metadata: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> ManualCreditGrantResult:
    """Create a dedicated manual-grant bucket and matching ledger row."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_amount = _quantize_credit_amount(amount)
    normalized_source_bid = str(source_bid or "").strip()
    normalized_idempotency_key = str(idempotency_key or "").strip()
    if not normalized_creator_bid or normalized_amount <= _ZERO:
        return ManualCreditGrantResult(
            status="noop",
            creator_bid=normalized_creator_bid or None,
            amount=_credit_decimal_to_number(normalized_amount),
        )
    if not normalized_source_bid and not normalized_idempotency_key:
        return ManualCreditGrantResult(
            status="error_missing_idempotency",
            creator_bid=normalized_creator_bid,
            amount=_credit_decimal_to_number(normalized_amount),
        )

    with app.app_context():
        granted_at = effective_from or now_utc()
        wallet = _load_or_create_credit_wallet(app, normalized_creator_bid)
        grant_bid = normalized_source_bid or generate_id(app)
        ledger_key = normalized_idempotency_key or f"manual_grant:{grant_bid}"

        existing_result = _load_existing_manual_credit_grant_result(
            creator_bid=normalized_creator_bid,
            ledger_key=ledger_key,
        )
        if existing_result is not None:
            return existing_result

        normalized_metadata = dict(metadata or {})
        normalized_ledger_metadata = {
            **normalized_metadata,
            **dict(ledger_metadata or {}),
        }
        bucket = CreditWalletBucket(
            wallet_bucket_bid=generate_id(app),
            wallet_bid=wallet.wallet_bid,
            creator_bid=normalized_creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=grant_bid,
            priority=resolve_credit_bucket_priority(
                CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            ),
            original_credits=normalized_amount,
            available_credits=normalized_amount,
            reserved_credits=_ZERO,
            consumed_credits=_ZERO,
            expired_credits=_ZERO,
            effective_from=granted_at,
            effective_to=effective_to,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json=normalized_metadata,
        )
        db.session.add(bucket)
        sync_credit_bucket_status(bucket)

        refresh_credit_wallet_snapshot(wallet)
        balance_after = _quantize_credit_amount(wallet.available_credits)
        next_lifetime_granted = _quantize_credit_amount(
            _to_decimal(wallet.lifetime_granted_credits) + normalized_amount
        )
        ledger_entry = CreditLedgerEntry(
            ledger_bid=generate_id(app),
            creator_bid=normalized_creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=grant_bid,
            idempotency_key=ledger_key,
            amount=normalized_amount,
            balance_after=balance_after,
            expires_at=effective_to,
            consumable_from=granted_at,
            metadata_json=normalized_ledger_metadata,
        )
        wallet.available_credits = balance_after
        persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            lifetime_granted_credits=next_lifetime_granted,
            updated_at=granted_at,
        )
        db.session.add(ledger_entry)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing_result = _load_existing_manual_credit_grant_result(
                creator_bid=normalized_creator_bid,
                ledger_key=ledger_key,
            )
            if existing_result is not None:
                return existing_result
            raise
        return ManualCreditGrantResult(
            status="granted",
            creator_bid=normalized_creator_bid,
            amount=_credit_decimal_to_number(normalized_amount),
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            ledger_bid=ledger_entry.ledger_bid,
            expires_at=effective_to,
            metadata_json=normalized_ledger_metadata,
        )


def _build_manual_credit_grant_result_from_entry(
    entry: CreditLedgerEntry,
) -> ManualCreditGrantResult:
    metadata = dict(entry.metadata_json or {})
    return ManualCreditGrantResult(
        status="noop_existing",
        creator_bid=str(entry.creator_bid or "").strip() or None,
        amount=_credit_decimal_to_number(_to_decimal(entry.amount)),
        wallet_bid=str(entry.wallet_bid or "").strip() or None,
        wallet_bucket_bid=str(entry.wallet_bucket_bid or "").strip() or None,
        ledger_bid=str(entry.ledger_bid or "").strip() or None,
        expires_at=entry.expires_at,
        metadata_json=metadata,
    )


def _load_existing_manual_credit_grant_result(
    *,
    creator_bid: str,
    ledger_key: str,
) -> ManualCreditGrantResult | None:
    existing_entry = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == creator_bid,
            CreditLedgerEntry.idempotency_key == ledger_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if existing_entry is None:
        return None
    return _build_manual_credit_grant_result_from_entry(existing_entry)


def expire_credit_wallet_buckets(
    app: Flask,
    *,
    creator_bid: str = "",
    expire_before: datetime | None = None,
) -> WalletExpirationResult:
    """Expire currently active buckets whose effective window has ended."""
    normalized_creator_bid = str(creator_bid or "").strip()
    cutoff = expire_before or now_utc()
    with app.app_context():
        result = _expire_credit_wallet_buckets_in_session(
            app,
            creator_bid=normalized_creator_bid,
            expire_before=cutoff,
        )
        db.session.commit()
        return result


def repair_expire_ledger_bucket_drift(
    app: Flask,
    *,
    creator_bid: str = "",
    wallet_bucket_bid: str = "",
    repair_before: datetime | None = None,
    limit: int | None = None,
    dry_run: bool = True,
) -> ExpireLedgerBucketDriftRepairResult:
    """Close buckets whose expire ledger exists but bucket state stayed live.

    This intentionally does not write another expire ledger. The target shape is
    an active, already-ended bucket with remaining available credits and an
    existing expire ledger for the same bucket cycle. Writing a second ledger
    would duplicate audit entries, so the repair only synchronizes the bucket
    projection and wallet snapshot.
    """
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_wallet_bucket_bid = str(wallet_bucket_bid or "").strip()
    normalized_limit = int(limit) if limit is not None and int(limit) > 0 else None
    repaired_at = repair_before or now_utc()

    with app.app_context():
        query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
            CreditWalletBucket.effective_to.isnot(None),
            CreditWalletBucket.effective_to <= repaired_at,
            CreditWalletBucket.available_credits > _ZERO,
        )
        if normalized_creator_bid:
            query = query.filter(
                CreditWalletBucket.creator_bid == normalized_creator_bid
            )
        if normalized_wallet_bucket_bid:
            query = query.filter(
                CreditWalletBucket.wallet_bucket_bid == normalized_wallet_bucket_bid
            )

        candidate_buckets = query.order_by(
            CreditWalletBucket.effective_to.asc(),
            CreditWalletBucket.created_at.asc(),
            CreditWalletBucket.id.asc(),
        )
        if normalized_limit is not None:
            candidate_buckets = candidate_buckets.limit(normalized_limit)
        candidate_buckets = candidate_buckets.all()
        records: list[ExpireLedgerBucketDriftRecord] = []
        changed_wallets: dict[str, CreditWallet] = {}
        expire_ledgers_by_bucket: dict[str, list[CreditLedgerEntry]] = {}

        if candidate_buckets:
            bucket_bids = [bucket.wallet_bucket_bid for bucket in candidate_buckets]
            ledger_rows = CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                CreditLedgerEntry.wallet_bucket_bid.in_(bucket_bids),
            ).all()
            for ledger in ledger_rows:
                expire_ledgers_by_bucket.setdefault(
                    ledger.wallet_bucket_bid, []
                ).append(ledger)

        for bucket in candidate_buckets:
            if _is_credit_pack_runtime_bucket(bucket):
                continue
            bucket_ledgers = sorted(
                (
                    ledger
                    for ledger in expire_ledgers_by_bucket.get(
                        bucket.wallet_bucket_bid, []
                    )
                    if ledger.creator_bid == bucket.creator_bid
                ),
                key=lambda ledger: int(ledger.id or 0),
            )
            if not bucket_ledgers:
                continue
            expire_ledgers = [
                ledger
                for ledger in bucket_ledgers
                if _is_matching_expire_ledger_for_bucket(ledger, bucket)
            ]

            previous_available = _quantize_credit_amount(bucket.available_credits)
            previous_expired = _quantize_credit_amount(bucket.expired_credits)
            previous_status = int(bucket.status or 0)
            expire_ledger_amount = _quantize_credit_amount(
                sum(
                    (_to_decimal(ledger.amount) for ledger in bucket_ledgers),
                    start=_ZERO,
                )
            )
            ledger_expired_amount = _quantize_credit_amount(
                sum(
                    (abs(_to_decimal(ledger.amount)) for ledger in bucket_ledgers),
                    start=_ZERO,
                )
            )
            next_available = _ZERO
            next_expired = max(
                previous_expired,
                ledger_expired_amount
                if ledger_expired_amount > _ZERO
                else _quantize_credit_amount(previous_expired + previous_available),
            )
            next_status = (
                CREDIT_BUCKET_STATUS_EXHAUSTED
                if _to_decimal(bucket.reserved_credits) > _ZERO
                else CREDIT_BUCKET_STATUS_EXPIRED
            )
            has_cycle_match = bool(expire_ledgers)
            has_amount_evidence = ledger_expired_amount == previous_available
            has_expiry_evidence = all(
                ledger.expires_at == bucket.effective_to for ledger in expire_ledgers
            )
            can_repair = has_cycle_match and has_amount_evidence and has_expiry_evidence
            repair_action = "repair" if can_repair else "manual_review"
            if not has_cycle_match:
                repair_reason = "expire_ledger_expiry_mismatch"
            elif not has_amount_evidence:
                repair_reason = "expire_ledger_amount_mismatch"
            elif not has_expiry_evidence:
                repair_reason = "expire_ledger_expiry_mismatch"
            else:
                repair_reason = "expire_ledger_matches_bucket_balance_and_expiry"
            changed = can_repair and (
                previous_available != next_available
                or previous_expired != next_expired
                or previous_status != next_status
            )
            records.append(
                ExpireLedgerBucketDriftRecord(
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    wallet_bid=bucket.wallet_bid,
                    creator_bid=bucket.creator_bid,
                    previous_available_credits=_credit_decimal_to_number(
                        previous_available
                    ),
                    available_credits=_credit_decimal_to_number(next_available),
                    previous_expired_credits=_credit_decimal_to_number(
                        previous_expired
                    ),
                    expired_credits=_credit_decimal_to_number(next_expired),
                    previous_status=previous_status,
                    status=next_status,
                    expire_ledger_count=len(bucket_ledgers),
                    expire_ledger_amount=_credit_decimal_to_number(
                        expire_ledger_amount
                    ),
                    repair_action=repair_action,
                    repair_reason=repair_reason,
                    changed=changed,
                )
            )

            if dry_run or not changed:
                continue

            bucket.available_credits = next_available
            bucket.expired_credits = next_expired
            bucket.status = next_status
            bucket.updated_at = repaired_at
            db.session.add(bucket)

            wallet = changed_wallets.get(bucket.wallet_bid)
            if wallet is None:
                wallet = _load_credit_wallet_by_wallet_bid(bucket.wallet_bid)
                if wallet is not None:
                    changed_wallets[bucket.wallet_bid] = wallet

        if not dry_run:
            with unit_of_work():
                db.session.flush()
                for wallet in changed_wallets.values():
                    refresh_credit_wallet_snapshot(wallet, snapshot_at=repaired_at)
                    persist_credit_wallet_snapshot(
                        wallet,
                        available_credits=wallet.available_credits,
                        reserved_credits=wallet.reserved_credits,
                        updated_at=repaired_at,
                    )

        repaired_bucket_count = sum(1 for record in records if record.changed)
        manual_review_count = sum(
            1 for record in records if record.repair_action == "manual_review"
        )
        return ExpireLedgerBucketDriftRepairResult(
            status=(
                "dry_run"
                if dry_run
                else "repaired"
                if repaired_bucket_count
                else "manual_review"
                if manual_review_count
                else "noop"
            ),
            creator_bid=normalized_creator_bid or None,
            wallet_bucket_bid=normalized_wallet_bucket_bid or None,
            bucket_count=len(records),
            repaired_bucket_count=repaired_bucket_count,
            manual_review_count=manual_review_count,
            dry_run=dry_run,
            buckets=records,
        )


def restore_wrongly_expired_credit_pack_buckets(
    app: Flask,
    *,
    bill_order_bids: list[str] | tuple[str, ...],
    dry_run: bool = True,
) -> ExpiredCreditPackBucketRestoreResult:
    """Restore explicitly scoped credit pack buckets expired before this fix."""
    normalized_order_bids = list(
        dict.fromkeys(_normalize_bid(bid) for bid in bill_order_bids)
    )
    normalized_order_bids = [bid for bid in normalized_order_bids if bid]
    if not normalized_order_bids:
        return ExpiredCreditPackBucketRestoreResult(
            status="noop",
            bill_order_bids=[],
            order_count=0,
            repaired_bucket_count=0,
            manual_review_count=0,
            noop_count=0,
            dry_run=dry_run,
        )

    repaired_at = now_utc()
    with app.app_context():
        if dry_run:
            records = _build_expired_credit_pack_restore_records(
                app,
                bill_order_bids=normalized_order_bids,
                repaired_at=repaired_at,
                dry_run=True,
            )
        else:
            with unit_of_work():
                records = _build_expired_credit_pack_restore_records(
                    app,
                    bill_order_bids=normalized_order_bids,
                    repaired_at=repaired_at,
                    dry_run=False,
                )

        repaired_count = sum(1 for record in records if record.changed)
        manual_review_count = sum(
            1 for record in records if record.repair_action == "manual_review"
        )
        noop_count = sum(1 for record in records if record.repair_action == "noop")
        return ExpiredCreditPackBucketRestoreResult(
            status=(
                "dry_run"
                if dry_run
                else "partial_repaired"
                if repaired_count and manual_review_count
                else "repaired"
                if repaired_count
                else "manual_review"
                if manual_review_count
                else "noop"
            ),
            bill_order_bids=normalized_order_bids,
            order_count=len(normalized_order_bids),
            repaired_bucket_count=repaired_count,
            manual_review_count=manual_review_count,
            noop_count=noop_count,
            dry_run=dry_run,
            buckets=records,
        )


def _build_expired_credit_pack_restore_records(
    app: Flask,
    *,
    bill_order_bids: list[str],
    repaired_at: datetime,
    dry_run: bool,
) -> list[ExpiredCreditPackBucketRestoreRecord]:
    records: list[ExpiredCreditPackBucketRestoreRecord] = []
    orders = {
        order.bill_order_bid: order
        for order in BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.bill_order_bid.in_(bill_order_bids),
        ).all()
    }

    for bill_order_bid in bill_order_bids:
        order = orders.get(bill_order_bid)
        if order is None:
            records.append(
                _build_expired_credit_pack_restore_record(
                    bill_order_bid=bill_order_bid,
                    repair_action="manual_review",
                    repair_reason="billing_order_not_found",
                )
            )
            continue
        if (
            int(order.order_type or 0) != BILLING_ORDER_TYPE_TOPUP
            or int(order.status or 0) != BILLING_ORDER_STATUS_PAID
            or order.paid_at is None
        ):
            records.append(
                _build_expired_credit_pack_restore_record(
                    bill_order_bid=bill_order_bid,
                    creator_bid=order.creator_bid,
                    repair_action="manual_review",
                    repair_reason="billing_order_is_not_paid_topup",
                )
            )
            continue

        buckets = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid == order.creator_bid,
            CreditWalletBucket.source_bid == bill_order_bid,
        ).all()
        runtime_buckets = [
            bucket for bucket in buckets if _is_credit_pack_runtime_bucket(bucket)
        ]
        if len(runtime_buckets) != 1:
            records.append(
                _build_expired_credit_pack_restore_record(
                    bill_order_bid=bill_order_bid,
                    creator_bid=order.creator_bid,
                    repair_action="manual_review",
                    repair_reason=(
                        "credit_pack_bucket_not_found"
                        if not runtime_buckets
                        else "multiple_credit_pack_buckets_found"
                    ),
                )
            )
            continue

        bucket = runtime_buckets[0]
        existing_repair = _load_existing_expired_credit_pack_restore_ledger(
            creator_bid=bucket.creator_bid,
            bill_order_bid=bill_order_bid,
        )
        if existing_repair is not None:
            records.append(
                _build_expired_credit_pack_restore_record(
                    bill_order_bid=bill_order_bid,
                    creator_bid=bucket.creator_bid,
                    wallet_bid=bucket.wallet_bid,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    previous_available_credits=bucket.available_credits,
                    available_credits=bucket.available_credits,
                    previous_expired_credits=bucket.expired_credits,
                    expired_credits=bucket.expired_credits,
                    previous_status=bucket.status,
                    status=bucket.status,
                    restored_credits=existing_repair.amount,
                    repair_action="noop",
                    repair_reason="already_repaired",
                    ledger_bid=existing_repair.ledger_bid,
                )
            )
            continue

        previous_available = _quantize_credit_amount(bucket.available_credits)
        previous_expired = _quantize_credit_amount(bucket.expired_credits)
        previous_status = int(bucket.status or 0)
        restore_amount = previous_expired
        next_available = _quantize_credit_amount(previous_available + restore_amount)
        next_expired = _ZERO
        can_repair, repair_reason, expire_ledgers = (
            _validate_expired_credit_pack_restore_candidate(
                bucket,
                restore_amount=restore_amount,
            )
        )
        record = _build_expired_credit_pack_restore_record(
            bill_order_bid=bill_order_bid,
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            previous_available_credits=previous_available,
            available_credits=next_available if can_repair else previous_available,
            previous_expired_credits=previous_expired,
            expired_credits=next_expired if can_repair else previous_expired,
            previous_status=previous_status,
            status=CREDIT_BUCKET_STATUS_ACTIVE if can_repair else previous_status,
            restored_credits=restore_amount if can_repair else _ZERO,
            repair_action="repair" if can_repair else "manual_review",
            repair_reason=repair_reason,
            changed=can_repair,
        )
        records.append(record)

        if dry_run or not can_repair:
            continue

        bucket.available_credits = next_available
        bucket.expired_credits = next_expired
        bucket.status = CREDIT_BUCKET_STATUS_ACTIVE
        bucket.updated_at = repaired_at
        db.session.add(bucket)
        db.session.flush()

        wallet = _load_credit_wallet_by_wallet_bid(bucket.wallet_bid)
        if wallet is None:
            message = "credit_pack_restore_wallet_missing"
            raise RuntimeError(message)
        available_credits, reserved_credits = calculate_credit_wallet_snapshot_values(
            wallet,
            snapshot_at=repaired_at,
        )
        ledger = CreditLedgerEntry(
            ledger_bid=generate_id(app),
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=bill_order_bid,
            idempotency_key=_build_expired_credit_pack_restore_idempotency_key(
                bill_order_bid
            ),
            amount=restore_amount,
            balance_after=available_credits,
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={
                "repair_reason": "restore_wrongly_expired_credit_pack_bucket",
                "bill_order_bid": bill_order_bid,
                "wallet_bucket_bid": bucket.wallet_bucket_bid,
                "restored_expired_credits": _credit_decimal_to_number(restore_amount),
                "previous_status": previous_status,
                "previous_available_credits": _credit_decimal_to_number(
                    previous_available
                ),
                "previous_expired_credits": _credit_decimal_to_number(previous_expired),
                "expire_ledger_bids": [ledger.ledger_bid for ledger in expire_ledgers],
                "repaired_at": to_utc_iso(repaired_at),
            },
        )
        if (
            _quantize_credit_amount(wallet.available_credits) != available_credits
            or _quantize_credit_amount(wallet.reserved_credits) != reserved_credits
        ):
            persist_credit_wallet_snapshot(
                wallet,
                available_credits=available_credits,
                reserved_credits=reserved_credits,
                updated_at=repaired_at,
            )
        db.session.add(ledger)
        records[-1] = _build_expired_credit_pack_restore_record(
            bill_order_bid=bill_order_bid,
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            previous_available_credits=previous_available,
            available_credits=next_available,
            previous_expired_credits=previous_expired,
            expired_credits=next_expired,
            previous_status=previous_status,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            restored_credits=restore_amount,
            repair_action="repair",
            repair_reason=repair_reason,
            changed=True,
            ledger_bid=ledger.ledger_bid,
        )

    return records


def _build_expired_credit_pack_restore_record(
    *,
    bill_order_bid: str,
    creator_bid: str | None = None,
    wallet_bid: str | None = None,
    wallet_bucket_bid: str | None = None,
    previous_available_credits: Decimal | Any = _ZERO,
    available_credits: Decimal | Any = _ZERO,
    previous_expired_credits: Decimal | Any = _ZERO,
    expired_credits: Decimal | Any = _ZERO,
    previous_status: int | None = None,
    status: int | None = None,
    restored_credits: Decimal | Any = _ZERO,
    repair_action: str,
    repair_reason: str,
    changed: bool = False,
    ledger_bid: str | None = None,
) -> ExpiredCreditPackBucketRestoreRecord:
    return ExpiredCreditPackBucketRestoreRecord(
        bill_order_bid=bill_order_bid,
        creator_bid=creator_bid,
        wallet_bid=wallet_bid,
        wallet_bucket_bid=wallet_bucket_bid,
        previous_available_credits=_credit_decimal_to_number(
            _quantize_credit_amount(previous_available_credits)
        ),
        available_credits=_credit_decimal_to_number(
            _quantize_credit_amount(available_credits)
        ),
        previous_expired_credits=_credit_decimal_to_number(
            _quantize_credit_amount(previous_expired_credits)
        ),
        expired_credits=_credit_decimal_to_number(
            _quantize_credit_amount(expired_credits)
        ),
        previous_status=previous_status,
        status=status,
        restored_credits=_credit_decimal_to_number(
            _quantize_credit_amount(restored_credits)
        ),
        repair_action=repair_action,
        repair_reason=repair_reason,
        changed=changed,
        ledger_bid=ledger_bid,
    )


def _validate_expired_credit_pack_restore_candidate(
    bucket: CreditWalletBucket,
    *,
    restore_amount: Decimal,
) -> tuple[bool, str, list[CreditLedgerEntry]]:
    if int(bucket.status or 0) != CREDIT_BUCKET_STATUS_EXPIRED:
        return False, "bucket_is_not_expired", []
    if restore_amount <= _ZERO:
        return False, "bucket_has_no_expired_credits", []
    if _to_decimal(bucket.reserved_credits) != _ZERO:
        return False, "bucket_has_reserved_credits", []
    if _to_decimal(bucket.available_credits) != _ZERO:
        return False, "bucket_has_available_credits", []

    expected_remaining = _quantize_credit_amount(
        _to_decimal(bucket.original_credits)
        - _to_decimal(bucket.consumed_credits)
        - _to_decimal(bucket.reserved_credits)
        - _to_decimal(bucket.available_credits)
    )
    if expected_remaining != restore_amount:
        return False, "bucket_balance_shape_mismatch", []

    expire_ledgers = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == bucket.creator_bid,
            CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        )
        .order_by(CreditLedgerEntry.id.asc())
        .all()
    )
    matching_ledgers = [
        ledger
        for ledger in expire_ledgers
        if _is_matching_expire_ledger_for_bucket(ledger, bucket)
    ]
    if not matching_ledgers:
        return False, "matching_expire_ledger_not_found", expire_ledgers
    expired_amount = _quantize_credit_amount(
        sum((abs(_to_decimal(ledger.amount)) for ledger in matching_ledgers), _ZERO)
    )
    if expired_amount != restore_amount:
        return False, "expire_ledger_amount_mismatch", matching_ledgers
    return True, "expired_credit_pack_bucket_matches_expire_ledger", matching_ledgers


def _load_existing_expired_credit_pack_restore_ledger(
    *,
    creator_bid: str,
    bill_order_bid: str,
) -> CreditLedgerEntry | None:
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == creator_bid,
            CreditLedgerEntry.idempotency_key
            == _build_expired_credit_pack_restore_idempotency_key(bill_order_bid),
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )


def _build_expired_credit_pack_restore_idempotency_key(bill_order_bid: str) -> str:
    return f"restore_expired_topup:{_normalize_bid(bill_order_bid)}"


def _expire_credit_wallet_buckets_in_session(
    app: Flask,
    *,
    creator_bid: str = "",
    expire_before: datetime | None = None,
) -> WalletExpirationResult:
    """Expire eligible buckets inside the current transaction without committing."""
    normalized_creator_bid = str(creator_bid or "").strip()
    cutoff = expire_before or now_utc()
    query = CreditWalletBucket.query.filter(
        CreditWalletBucket.deleted == 0,
        CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
        CreditWalletBucket.effective_to.isnot(None),
        CreditWalletBucket.effective_to <= cutoff,
    )
    if normalized_creator_bid:
        query = query.filter(CreditWalletBucket.creator_bid == normalized_creator_bid)
    buckets = query.order_by(
        CreditWalletBucket.effective_to.asc(),
        CreditWalletBucket.created_at.asc(),
        CreditWalletBucket.id.asc(),
    ).all()
    if not buckets:
        return WalletExpirationResult(
            status="noop",
            creator_bid=normalized_creator_bid or None,
            bucket_count=0,
            expired_credits=0,
        )

    wallets: dict[str, CreditWallet] = {}
    frozen_credit_pack_wallet_bids: set[str] = set()
    expired_total = _ZERO
    expired_count = 0
    for bucket in buckets:
        try:
            db.session.refresh(bucket)
        except ObjectDeletedError:
            continue
        if (
            int(bucket.deleted or 0) != 0
            or int(bucket.status or 0) != CREDIT_BUCKET_STATUS_ACTIVE
            or not str(bucket.wallet_bid or "").strip()
            or bucket.effective_to is None
            or bucket.effective_to > cutoff
        ):
            continue
        if _is_credit_pack_runtime_bucket(bucket):
            frozen_credit_pack_wallet_bids.add(bucket.wallet_bid)
            continue

        available = _to_decimal(bucket.available_credits)
        if available <= _ZERO:
            _sync_empty_available_bucket_status_if_unchanged(
                bucket,
                available=available,
                mutation_at=now_utc(),
            )
            continue

        wallet = wallets.get(bucket.wallet_bid)
        if wallet is None:
            wallet = _load_credit_wallet_by_wallet_bid(bucket.wallet_bid)
            if wallet is None:
                continue
            wallets[bucket.wallet_bid] = wallet

        # Expire each bucket inside its own savepoint and flush the cycle-scoped
        # expire ledger row here. A concurrent transaction (another expire
        # event, the beat scan, or referral grant) may have already expired this
        # same bucket cycle; its committed ledger row then trips the
        # (creator_bid, idempotency_key) unique key. Catching it here rolls back
        # only this bucket's changes and skips it, instead of surfacing later
        # from a query-invoked autoflush and aborting the whole expiration
        # batch. Autoflush stays enabled so the snapshot recompute below still
        # sees the pending bucket update.
        try:
            with db.session.begin_nested():
                if not _expire_bucket_available_credits_if_unchanged(
                    bucket,
                    available=available,
                    mutation_at=now_utc(),
                ):
                    continue

                refresh_credit_wallet_snapshot(
                    wallet,
                    snapshot_at=cutoff - timedelta(microseconds=1),
                )
                ledger_entry = CreditLedgerEntry(
                    ledger_bid=generate_id(app),
                    creator_bid=bucket.creator_bid,
                    wallet_bid=wallet.wallet_bid,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                    source_type=bucket.source_type,
                    source_bid=bucket.source_bid,
                    idempotency_key=_build_expire_ledger_idempotency_key(
                        bucket.wallet_bucket_bid,
                        effective_to=bucket.effective_to,
                    ),
                    amount=-available,
                    balance_after=_quantize_credit_amount(wallet.available_credits),
                    expires_at=bucket.effective_to,
                    consumable_from=bucket.effective_from,
                    metadata_json={
                        "expired_bucket_bid": bucket.wallet_bucket_bid,
                        "expired_at": cutoff.isoformat(),
                    },
                )
                persist_credit_wallet_snapshot(
                    wallet,
                    available_credits=wallet.available_credits,
                    reserved_credits=wallet.reserved_credits,
                    updated_at=cutoff,
                )
                db.session.add(ledger_entry)
                db.session.flush()
        except (IntegrityError, RuntimeError) as exc:
            # IntegrityError: another transaction already wrote this bucket's
            # "expire:" ledger row. RuntimeError("credit_wallet_version_conflict"):
            # another transaction updated the wallet concurrently
            # (persist_credit_wallet_snapshot's optimistic version check). Either
            # way the begin_nested savepoint already rolled back this bucket's
            # changes, so reload the wallet (its in-memory version/balances are
            # stale) and skip the bucket; a later scan retries it. Do NOT call
            # db.session.rollback() here -- that would discard buckets already
            # expired earlier in this batch; the savepoint rollback is enough.
            # Any other RuntimeError is unexpected -> re-raise.
            if (
                isinstance(exc, RuntimeError)
                and str(exc) != "credit_wallet_version_conflict"
            ):
                raise
            db.session.refresh(wallet)
            continue
        expired_total += available
        expired_count += 1

    _refresh_frozen_credit_pack_wallet_snapshots(
        frozen_credit_pack_wallet_bids,
        wallets=wallets,
        snapshot_at=cutoff,
    )

    return WalletExpirationResult(
        status="expired" if expired_count else "noop",
        creator_bid=normalized_creator_bid or None,
        bucket_count=expired_count,
        expired_credits=_credit_decimal_to_number(expired_total),
    )


def _refresh_frozen_credit_pack_wallet_snapshots(
    wallet_bids: set[str],
    *,
    wallets: dict[str, CreditWallet],
    snapshot_at: datetime,
) -> None:
    for wallet_bid in sorted(wallet_bids):
        wallet = wallets.get(wallet_bid)
        if wallet is None:
            wallet = _load_credit_wallet_by_wallet_bid(wallet_bid)
            if wallet is None:
                continue
            wallets[wallet_bid] = wallet

        if (
            load_primary_active_subscription(wallet.creator_bid, as_of=snapshot_at)
            is not None
        ):
            continue

        try:
            with db.session.begin_nested():
                available_credits, reserved_credits = (
                    calculate_credit_wallet_snapshot_values(
                        wallet,
                        snapshot_at=snapshot_at,
                    )
                )
                if (
                    _quantize_credit_amount(wallet.available_credits)
                    == available_credits
                    and _quantize_credit_amount(wallet.reserved_credits)
                    == reserved_credits
                ):
                    continue
                persist_credit_wallet_snapshot(
                    wallet,
                    available_credits=available_credits,
                    reserved_credits=reserved_credits,
                    updated_at=snapshot_at,
                )
        except RuntimeError as exc:
            if str(exc) != "credit_wallet_version_conflict":
                raise
            db.session.refresh(wallet)


def _is_credit_pack_runtime_bucket(bucket: CreditWalletBucket) -> bool:
    """Return whether a bucket represents non-expiring credit pack ownership."""
    return (
        resolve_wallet_bucket_runtime_category(
            bucket,
            load_order_type=load_billing_order_type_by_bid,
        )
        == CREDIT_BUCKET_CATEGORY_TOPUP
    )


def _expire_bucket_available_credits_if_unchanged(
    bucket: CreditWalletBucket,
    *,
    available: Decimal,
    mutation_at: datetime,
) -> bool:
    """Expire a bucket only if its refreshed balance/window still match."""
    if bucket.id is None or bucket.effective_to is None:
        return False

    expected_available = _quantize_credit_amount(available)
    expected_expired = _quantize_credit_amount(bucket.expired_credits)
    expected_reserved = _quantize_credit_amount(bucket.reserved_credits)
    next_expired = _quantize_credit_amount(expected_expired + expected_available)
    next_status = (
        CREDIT_BUCKET_STATUS_EXHAUSTED
        if expected_reserved > _ZERO
        else CREDIT_BUCKET_STATUS_EXPIRED
    )
    updated_rows = CreditWalletBucket.query.filter(
        CreditWalletBucket.deleted == 0,
        CreditWalletBucket.id == bucket.id,
        CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
        CreditWalletBucket.effective_to == bucket.effective_to,
        CreditWalletBucket.available_credits == expected_available,
        CreditWalletBucket.expired_credits == expected_expired,
        CreditWalletBucket.reserved_credits == expected_reserved,
    ).update(
        {
            "available_credits": _ZERO,
            "expired_credits": next_expired,
            "status": next_status,
            "updated_at": mutation_at,
        },
        synchronize_session=False,
    )
    if updated_rows != 1:
        db.session.expire(bucket)
        return False

    bucket.available_credits = _ZERO
    bucket.expired_credits = next_expired
    bucket.status = next_status
    bucket.updated_at = mutation_at
    return True


def _sync_empty_available_bucket_status_if_unchanged(
    bucket: CreditWalletBucket,
    *,
    available: Decimal,
    mutation_at: datetime,
) -> bool:
    """Mark an ended empty bucket exhausted only if it stayed empty."""
    if bucket.id is None or bucket.effective_to is None:
        return False

    expected_available = _quantize_credit_amount(available)
    expected_expired = _quantize_credit_amount(bucket.expired_credits)
    expected_reserved = _quantize_credit_amount(bucket.reserved_credits)
    updated_rows = CreditWalletBucket.query.filter(
        CreditWalletBucket.deleted == 0,
        CreditWalletBucket.id == bucket.id,
        CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
        CreditWalletBucket.effective_to == bucket.effective_to,
        CreditWalletBucket.available_credits == expected_available,
        CreditWalletBucket.expired_credits == expected_expired,
        CreditWalletBucket.reserved_credits == expected_reserved,
    ).update(
        {
            "available_credits": _ZERO,
            "status": CREDIT_BUCKET_STATUS_EXHAUSTED,
            "updated_at": mutation_at,
        },
        synchronize_session=False,
    )
    if updated_rows != 1:
        db.session.expire(bucket)
        return False

    bucket.available_credits = _ZERO
    bucket.status = CREDIT_BUCKET_STATUS_EXHAUSTED
    bucket.updated_at = mutation_at
    return True


def sync_credit_bucket_status(bucket: CreditWalletBucket) -> int:
    """Normalize mutable bucket status from its current remaining balance."""
    current_status = int(bucket.status or 0)
    if current_status in _PRESERVED_BUCKET_STATUSES:
        return current_status
    if _to_decimal(bucket.available_credits) <= _ZERO:
        bucket.available_credits = _ZERO
        bucket.status = CREDIT_BUCKET_STATUS_EXHAUSTED
        return CREDIT_BUCKET_STATUS_EXHAUSTED
    bucket.status = CREDIT_BUCKET_STATUS_ACTIVE
    return CREDIT_BUCKET_STATUS_ACTIVE


def _load_adjustable_credit_buckets(
    creator_bid: str,
    *,
    adjustment_at: datetime,
) -> list[CreditWalletBucket]:
    rows = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid == str(creator_bid or "").strip(),
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
        )
        .order_by(
            CreditWalletBucket.priority.asc(),
            CreditWalletBucket.id.asc(),
        )
        .all()
    )
    eligible = [
        row
        for row in rows
        if _to_decimal(row.available_credits) > _ZERO
        and (row.effective_from is None or row.effective_from <= adjustment_at)
        and (row.effective_to is None or row.effective_to > adjustment_at)
    ]
    eligible.sort(
        key=lambda row: build_wallet_bucket_runtime_sort_key(
            row,
            load_order_type=load_billing_order_type_by_bid,
        )
    )
    return eligible


def _load_credit_wallet_by_wallet_bid(wallet_bid: str) -> CreditWallet | None:
    return (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.wallet_bid == str(wallet_bid or "").strip(),
        )
        .order_by(CreditWallet.id.desc())
        .first()
    )


def _load_or_create_credit_wallet(app: Flask, creator_bid: str) -> CreditWallet:
    normalized_creator_bid = str(creator_bid or "").strip()
    wallet = (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid == normalized_creator_bid,
        )
        .order_by(CreditWallet.id.desc())
        .first()
    )
    if wallet is not None:
        return wallet

    wallet = CreditWallet(
        wallet_bid=generate_id(app),
        creator_bid=normalized_creator_bid,
        available_credits=Decimal(0),
        reserved_credits=Decimal(0),
        lifetime_granted_credits=Decimal(0),
        lifetime_consumed_credits=Decimal(0),
        last_settled_usage_id=0,
        version=0,
    )
    db.session.add(wallet)
    db.session.flush()
    return wallet
