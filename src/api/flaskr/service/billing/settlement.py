"""Usage settlement helpers for creator billing."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.common.cache_provider import cache as cache_provider
from flaskr.dao import db
from flaskr.service.metering.models import BillUsageRecord
from flaskr.util.uuid import generate_id

from .charges import (
    UsageBucketBreakdownItem,
    UsageBucketMetricBreakdownItem,
    build_usage_entry_metadata,
    build_usage_metric_charges,
)
from .consts import (
    CREDIT_BUCKET_CATEGORY_LABELS,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_USAGE,
)
from .bucket_categories import (
    build_wallet_bucket_runtime_sort_key,
    load_billing_order_type_by_bid,
    wallet_bucket_requires_active_subscription,
)
from .models import CreditLedgerEntry, CreditWallet, CreditWalletBucket
from .ownership import resolve_usage_creator_bid
from .primitives import credit_decimal_to_number as _credit_decimal_to_number
from .primitives import decimal_to_number as _decimal_to_number
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .subscriptions import load_effective_topup_subscription
from .wallets import (
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)

_ZERO = Decimal("0")
_SETTLEMENT_LOCK_TIMEOUT_SECONDS = 60
_SETTLEMENT_LOCK_BLOCKING_TIMEOUT_SECONDS = 60


def _serialize_metadata_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


@dataclass(slots=True, frozen=True)
class SettlementResult:
    status: str
    usage_bid: str | None
    creator_bid: str | None = None
    usage_id: int | None = None
    entry_count: int = 0
    consumed_credits: int | float = 0
    reason: str | None = None
    requested_creator_bid: str | None = None
    replay: bool = False
    backfill: bool = False

    def to_task_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "usage_bid": self.usage_bid,
            "creator_bid": self.creator_bid,
            "usage_id": self.usage_id,
            "entry_count": self.entry_count,
            "consumed_credits": self.consumed_credits,
            "requested_creator_bid": self.requested_creator_bid,
            "replay": self.replay,
            "backfill": self.backfill,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class BackfillSettlementItem:
    usage_bid: str
    usage_id: int
    status: str
    creator_bid: str | None = None
    requested_creator_bid: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "usage_bid": self.usage_bid,
            "usage_id": self.usage_id,
            "status": self.status,
            "creator_bid": self.creator_bid,
            "requested_creator_bid": self.requested_creator_bid,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class BackfillSettlementResult:
    status: str
    creator_bid: str | None
    usage_id_start: int | None
    usage_id_end: int | None
    limit: int | None
    processed_count: int
    status_counts: dict[str, int] = field(default_factory=dict)
    items: list[BackfillSettlementItem] = field(default_factory=list)
    backfill: bool = True

    def to_task_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "usage_id_start": self.usage_id_start,
            "usage_id_end": self.usage_id_end,
            "limit": self.limit,
            "processed_count": self.processed_count,
            "status_counts": dict(self.status_counts),
            "items": [item.to_payload() for item in self.items],
            "backfill": self.backfill,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


def settle_bill_usage(
    app: Flask,
    *,
    usage_bid: str = "",
    usage_id: int | None = None,
) -> SettlementResult:
    """Settle a single metering usage record into credit ledger consumption."""

    normalized_usage_bid = str(usage_bid or "").strip()
    with app.app_context():
        usage = _load_usage_record(usage_bid=normalized_usage_bid, usage_id=usage_id)
        if usage is None:
            return SettlementResult(
                status="not_found",
                usage_bid=normalized_usage_bid or None,
                usage_id=usage_id,
            )

        if int(usage.record_level or 0) != 0:
            return _build_skip_result(usage, reason="segment_record")
        if int(usage.billable or 0) != 1:
            return _build_skip_result(usage, reason="non_billable")
        if int(usage.status or 0) != 0:
            return _build_skip_result(usage, reason="usage_failed")

        creator_bid = str(resolve_usage_creator_bid(app, usage) or "").strip()
        if not creator_bid:
            return _build_skip_result(usage, reason="creator_not_found")

        with _usage_settlement_lock(
            app,
            creator_bid=creator_bid,
            usage_bid=usage.usage_bid,
        ):
            existing_entries = (
                CreditLedgerEntry.query.filter(
                    CreditLedgerEntry.deleted == 0,
                    CreditLedgerEntry.creator_bid == creator_bid,
                    CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_USAGE,
                    CreditLedgerEntry.source_bid == usage.usage_bid,
                )
                .order_by(CreditLedgerEntry.id.desc())
                .all()
            )
            if existing_entries:
                return SettlementResult(
                    status="already_settled",
                    usage_bid=usage.usage_bid,
                    creator_bid=creator_bid,
                    entry_count=len(existing_entries),
                )

            settlement_at = usage.created_at or datetime.now()
            metric_charges = build_usage_metric_charges(
                usage,
                settlement_at=settlement_at,
            )
            if not metric_charges:
                wallet = _load_credit_wallet(creator_bid)
                if wallet is not None:
                    persist_credit_wallet_snapshot(
                        wallet,
                        available_credits=wallet.available_credits,
                        reserved_credits=wallet.reserved_credits,
                        last_settled_usage_id=max(
                            int(wallet.last_settled_usage_id or 0),
                            int(usage.id or 0),
                        ),
                        updated_at=datetime.now(),
                    )
                    db.session.commit()
                return SettlementResult(
                    status="noop",
                    usage_bid=usage.usage_bid,
                    creator_bid=creator_bid,
                    entry_count=0,
                    consumed_credits=0,
                )

            wallet = _load_credit_wallet(creator_bid)
            if wallet is None:
                return SettlementResult(
                    status="insufficient",
                    usage_bid=usage.usage_bid,
                    creator_bid=creator_bid,
                    entry_count=0,
                    consumed_credits=_decimal_to_number(
                        sum(
                            (charge.consumed_credits for charge in metric_charges),
                            start=_ZERO,
                        )
                    ),
                )

            buckets = _load_consumable_buckets(creator_bid, settlement_at=settlement_at)
            total_required = sum(
                (charge.consumed_credits for charge in metric_charges),
                start=_ZERO,
            )
            total_available = sum(
                (_to_decimal(bucket.available_credits) for bucket in buckets),
                start=_ZERO,
            )
            if total_available < total_required:
                return SettlementResult(
                    status="insufficient",
                    usage_bid=usage.usage_bid,
                    creator_bid=creator_bid,
                    entry_count=0,
                    consumed_credits=_credit_decimal_to_number(total_required),
                )

            balance_after = total_available
            entry_count = 0
            total_consumed = _ZERO
            bucket_breakdown_map: dict[str, dict[str, Any]] = {}
            for charge in metric_charges:
                remaining = charge.consumed_credits
                for bucket in buckets:
                    bucket_available = _to_decimal(bucket.available_credits)
                    if remaining <= _ZERO:
                        break
                    if bucket_available <= _ZERO:
                        continue

                    consumed = _quantize_credit_amount(min(bucket_available, remaining))
                    balance_after -= consumed
                    remaining -= consumed
                    total_consumed += consumed
                    bucket.available_credits = _quantize_credit_amount(
                        bucket_available - consumed
                    )
                    bucket.consumed_credits = _quantize_credit_amount(
                        _to_decimal(bucket.consumed_credits) + consumed
                    )
                    sync_credit_bucket_status(bucket)
                    db.session.add(bucket)
                    bucket_key = str(bucket.wallet_bucket_bid or "").strip()
                    metric_breakdown = bucket_breakdown_map.setdefault(
                        bucket_key,
                        {
                            "wallet_bucket_bid": bucket_key,
                            "bucket_category": CREDIT_BUCKET_CATEGORY_LABELS.get(
                                int(bucket.bucket_category or 0),
                                "subscription",
                            ),
                            "source_type": CREDIT_SOURCE_TYPE_LABELS.get(
                                int(bucket.source_type or 0),
                                "manual",
                            ),
                            "source_bid": str(bucket.source_bid or ""),
                            "consumed_credits": _ZERO,
                            "effective_from": bucket.effective_from,
                            "effective_to": bucket.effective_to,
                            "metric_breakdown": {},
                        },
                    )
                    metric_breakdown["consumed_credits"] += consumed
                    metric_items = metric_breakdown["metric_breakdown"]
                    metric_items[int(charge.billing_metric)] = {
                        "billing_metric": charge.metric_label,
                        "billing_metric_code": int(charge.billing_metric),
                        "consumed_credits": (
                            _to_decimal(
                                metric_items.get(int(charge.billing_metric), {}).get(
                                    "consumed_credits",
                                    _ZERO,
                                )
                            )
                            + consumed
                        ),
                    }

                if remaining <= _ZERO:
                    continue
                db.session.rollback()
                return SettlementResult(
                    status="insufficient",
                    usage_bid=usage.usage_bid,
                    creator_bid=creator_bid,
                    entry_count=0,
                    consumed_credits=_credit_decimal_to_number(total_required),
                )

            bucket_breakdown = [
                UsageBucketBreakdownItem(
                    wallet_bucket_bid=payload["wallet_bucket_bid"],
                    bucket_category=payload["bucket_category"],
                    source_type=payload["source_type"],
                    source_bid=payload["source_bid"],
                    consumed_credits=_to_decimal(payload["consumed_credits"]),
                    effective_from=_serialize_metadata_dt(payload["effective_from"]),
                    effective_to=_serialize_metadata_dt(payload["effective_to"]),
                    metric_breakdown=[
                        UsageBucketMetricBreakdownItem(
                            billing_metric=str(metric_payload["billing_metric"]),
                            billing_metric_code=int(
                                metric_payload["billing_metric_code"] or 0
                            ),
                            consumed_credits=_to_decimal(
                                metric_payload["consumed_credits"]
                            ),
                        )
                        for metric_payload in payload["metric_breakdown"].values()
                    ],
                )
                for payload in bucket_breakdown_map.values()
            ]
            primary_bucket_payload = (
                next(iter(bucket_breakdown_map.values()))
                if len(bucket_breakdown_map) == 1
                else None
            )

            refresh_credit_wallet_snapshot(wallet)
            ledger_entry = CreditLedgerEntry(
                ledger_bid=generate_id(app),
                creator_bid=creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=(
                    str(primary_bucket_payload["wallet_bucket_bid"])
                    if primary_bucket_payload is not None
                    else ""
                ),
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                source_type=CREDIT_SOURCE_TYPE_USAGE,
                source_bid=usage.usage_bid,
                idempotency_key=f"usage:{usage.usage_bid}:consume",
                amount=-total_consumed,
                balance_after=_to_decimal(wallet.available_credits),
                expires_at=(
                    primary_bucket_payload["effective_to"]
                    if primary_bucket_payload is not None
                    else None
                ),
                consumable_from=(
                    primary_bucket_payload["effective_from"]
                    if primary_bucket_payload is not None
                    else None
                ),
                metadata_json=build_usage_entry_metadata(
                    usage=usage,
                    charges=metric_charges,
                    bucket_breakdown=bucket_breakdown,
                ).to_metadata_json(),
            )
            db.session.add(ledger_entry)
            entry_count = 1
            persist_credit_wallet_snapshot(
                wallet,
                available_credits=wallet.available_credits,
                reserved_credits=wallet.reserved_credits,
                lifetime_consumed_credits=(
                    _to_decimal(wallet.lifetime_consumed_credits) + total_consumed
                ),
                last_settled_usage_id=max(
                    int(wallet.last_settled_usage_id or 0), int(usage.id or 0)
                ),
                updated_at=datetime.now(),
            )
            db.session.commit()
            return SettlementResult(
                status="settled",
                usage_bid=usage.usage_bid,
                creator_bid=creator_bid,
                entry_count=entry_count,
                consumed_credits=_credit_decimal_to_number(total_consumed),
            )


def replay_bill_usage_settlement(
    app: Flask,
    *,
    creator_bid: str = "",
    usage_bid: str = "",
    usage_id: int | None = None,
) -> SettlementResult:
    """Replay a usage settlement safely without duplicating credit consumption."""

    requested_creator_bid = str(creator_bid or "").strip() or None
    normalized_usage_bid = str(usage_bid or "").strip()
    with app.app_context():
        usage = _load_usage_record(usage_bid=normalized_usage_bid, usage_id=usage_id)
        if usage is None:
            return SettlementResult(
                status="not_found",
                usage_bid=normalized_usage_bid or None,
                usage_id=usage_id,
                requested_creator_bid=requested_creator_bid,
                replay=True,
            )

        resolved_creator_bid = str(resolve_usage_creator_bid(app, usage) or "").strip()
        if (
            requested_creator_bid is not None
            and resolved_creator_bid
            and requested_creator_bid != resolved_creator_bid
        ):
            return SettlementResult(
                status="creator_mismatch",
                usage_bid=usage.usage_bid,
                usage_id=int(usage.id or 0),
                creator_bid=resolved_creator_bid,
                requested_creator_bid=requested_creator_bid,
                replay=True,
            )

    payload = settle_bill_usage(
        app,
        usage_bid=normalized_usage_bid,
        usage_id=usage_id,
    )
    return SettlementResult(
        status=payload.status,
        usage_bid=payload.usage_bid,
        creator_bid=payload.creator_bid,
        usage_id=payload.usage_id,
        entry_count=payload.entry_count,
        consumed_credits=payload.consumed_credits,
        reason=payload.reason,
        requested_creator_bid=requested_creator_bid,
        replay=True,
    )


def backfill_bill_usage_settlement(
    app: Flask,
    *,
    creator_bid: str = "",
    usage_bid: str = "",
    usage_id_start: int | None = None,
    usage_id_end: int | None = None,
    limit: int | None = None,
) -> SettlementResult | BackfillSettlementResult:
    """Replay one or many usage settlements for offline repair/backfill."""

    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_usage_bid = str(usage_bid or "").strip()
    normalized_limit = max(int(limit or 0), 0) or None

    if normalized_usage_bid:
        payload = replay_bill_usage_settlement(
            app,
            creator_bid=normalized_creator_bid,
            usage_bid=normalized_usage_bid,
        )
        return SettlementResult(
            status=payload.status,
            usage_bid=payload.usage_bid,
            creator_bid=payload.creator_bid,
            usage_id=payload.usage_id,
            entry_count=payload.entry_count,
            consumed_credits=payload.consumed_credits,
            reason=payload.reason,
            requested_creator_bid=payload.requested_creator_bid,
            replay=payload.replay,
            backfill=True,
        )

    with app.app_context():
        query = BillUsageRecord.query.filter(BillUsageRecord.deleted == 0).order_by(
            BillUsageRecord.id.asc()
        )
        if usage_id_start is not None:
            query = query.filter(BillUsageRecord.id >= int(usage_id_start))
        if usage_id_end is not None:
            query = query.filter(BillUsageRecord.id <= int(usage_id_end))
        if normalized_limit is not None:
            query = query.limit(normalized_limit)
        rows = query.all()

    status_counts: dict[str, int] = {}
    items: list[BackfillSettlementItem] = []
    for row in rows:
        payload = replay_bill_usage_settlement(
            app,
            creator_bid=normalized_creator_bid,
            usage_bid=row.usage_bid,
            usage_id=int(row.id or 0),
        )
        status = str(payload.status or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        items.append(
            BackfillSettlementItem(
                usage_bid=row.usage_bid,
                usage_id=int(row.id or 0),
                status=status,
                creator_bid=payload.creator_bid,
                requested_creator_bid=payload.requested_creator_bid,
            )
        )

    return BackfillSettlementResult(
        status="completed" if items else "noop",
        creator_bid=normalized_creator_bid or None,
        usage_id_start=usage_id_start,
        usage_id_end=usage_id_end,
        limit=normalized_limit,
        processed_count=len(items),
        status_counts=status_counts,
        items=items,
        backfill=True,
    )


@contextmanager
def _usage_settlement_lock(app: Flask, *, creator_bid: str, usage_bid: str):
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_usage_bid = str(usage_bid or "").strip()
    lock_scope = normalized_creator_bid or f"usage:{normalized_usage_bid}"
    prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
    lock_key = f"{prefix}:billing:settle_usage:{lock_scope}"
    lock = cache_provider.lock(
        lock_key,
        timeout=_SETTLEMENT_LOCK_TIMEOUT_SECONDS,
        blocking_timeout=_SETTLEMENT_LOCK_BLOCKING_TIMEOUT_SECONDS,
    )
    acquired = bool(lock.acquire(blocking=True)) if lock is not None else False
    try:
        yield
    finally:
        if acquired and lock is not None:
            try:
                lock.release()
            except Exception:
                pass


def _load_usage_record(
    *, usage_bid: str, usage_id: int | None
) -> BillUsageRecord | None:
    query = BillUsageRecord.query.filter(BillUsageRecord.deleted == 0)
    if usage_bid:
        return (
            query.filter(BillUsageRecord.usage_bid == usage_bid)
            .order_by(BillUsageRecord.id.desc())
            .first()
        )
    if usage_id is None:
        return None
    return (
        query.filter(BillUsageRecord.id == int(usage_id))
        .order_by(BillUsageRecord.id.desc())
        .first()
    )


def _build_skip_result(usage: BillUsageRecord, *, reason: str) -> SettlementResult:
    return SettlementResult(
        status="skipped",
        reason=reason,
        usage_bid=usage.usage_bid,
    )


def _load_credit_wallet(creator_bid: str) -> CreditWallet | None:
    return (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid == creator_bid,
        )
        .order_by(CreditWallet.id.desc())
        .first()
    )


def _load_consumable_buckets(
    creator_bid: str,
    *,
    settlement_at: datetime,
) -> list[CreditWalletBucket]:
    rows = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid == creator_bid,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
        )
        .order_by(CreditWalletBucket.id.asc())
        .all()
    )
    eligible = [
        row
        for row in rows
        if _to_decimal(row.available_credits) > _ZERO
        and (row.effective_from is None or row.effective_from <= settlement_at)
        and (row.effective_to is None or row.effective_to > settlement_at)
    ]
    has_active_subscription = (
        load_effective_topup_subscription(creator_bid, as_of=settlement_at) is not None
    )
    eligible = [
        row
        for row in eligible
        if has_active_subscription
        or not wallet_bucket_requires_active_subscription(
            row,
            load_order_type=load_billing_order_type_by_bid,
        )
    ]
    eligible.sort(
        key=lambda row: build_wallet_bucket_runtime_sort_key(
            row,
            load_order_type=load_billing_order_type_by_bid,
        )
    )
    return eligible
