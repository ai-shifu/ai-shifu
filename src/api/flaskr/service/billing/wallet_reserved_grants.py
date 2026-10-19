"""Read-only loaders for paid orders whose reserved grants are overdue."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from sqlalchemy import case, func, or_

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
)
from .models import (
    BillingOrder,
    BillingRenewalEvent,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from .primitives import to_decimal as _to_decimal
from .wallet_results import ReservedGrantRepairRecord

if TYPE_CHECKING:
    from datetime import datetime

_ZERO = Decimal(0)


def _normalize_bid(value: object) -> str:
    return str(value or "").strip()


def _normalize_optional_metadata_bid(value: object) -> str:
    normalized = _normalize_bid(value)
    return "" if normalized.lower() == "null" else normalized


def _normalize_json_dict(payload: object) -> dict[str, object]:
    return payload if isinstance(payload, dict) else {}


def _json_extract_text(column: object, path: str) -> object:
    bind = db.session.get_bind()
    dialect_name = bind.dialect.name.lower() if bind is not None else ""
    extracted = func.json_extract(column, path)
    if dialect_name == "mysql":
        return func.json_unquote(extracted)
    return extracted


def _sql_null_if_empty_or_json_null(value: object) -> object:
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


def _normalize_bucket_credit_state(value: object) -> str:
    state = str(value or "").strip().lower()
    return "" if state == "null" else state


def _extract_ledger_bill_order_bid(
    ledger: CreditLedgerEntry, metadata: dict[str, object] | None = None
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
