"""Usage settlement helpers for creator billing."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.common.cache_provider import cache as cache_provider
from flaskr.dao import db
from flaskr.service.metering.models import BillUsageRecord
from flaskr.util.uuid import generate_id

from .charges import (
    build_usage_entry_metadata,
    build_usage_metric_charges,
)
from .consts import (
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_USAGE,
)
from .models import CreditLedgerEntry, CreditWallet, CreditWalletBucket
from .ownership import resolve_usage_creator_bid
from .wallets import (
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)

_ZERO = Decimal("0")
_DECIMAL_QUANT = Decimal("0.0000000001")
_SETTLEMENT_LOCK_TIMEOUT_SECONDS = 60
_SETTLEMENT_LOCK_BLOCKING_TIMEOUT_SECONDS = 60


def settle_bill_usage(
    app: Flask,
    *,
    usage_bid: str = "",
    usage_id: int | None = None,
) -> dict[str, Any]:
    """Settle a single metering usage record into credit ledger consumption."""

    normalized_usage_bid = str(usage_bid or "").strip()
    with app.app_context():
        usage = _load_usage_record(usage_bid=normalized_usage_bid, usage_id=usage_id)
        if usage is None:
            return {
                "status": "not_found",
                "usage_bid": normalized_usage_bid or None,
                "usage_id": usage_id,
            }

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
                return {
                    "status": "already_settled",
                    "usage_bid": usage.usage_bid,
                    "creator_bid": creator_bid,
                    "entry_count": len(existing_entries),
                }

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
                return {
                    "status": "noop",
                    "usage_bid": usage.usage_bid,
                    "creator_bid": creator_bid,
                    "entry_count": 0,
                    "consumed_credits": 0,
                }

            wallet = _load_credit_wallet(creator_bid)
            if wallet is None:
                return {
                    "status": "insufficient",
                    "usage_bid": usage.usage_bid,
                    "creator_bid": creator_bid,
                    "entry_count": 0,
                    "consumed_credits": _decimal_to_number(
                        sum(
                            (
                                _to_decimal(item["consumed_credits"])
                                for item in metric_charges
                            ),
                            start=_ZERO,
                        )
                    ),
                }

            buckets = _load_consumable_buckets(creator_bid, settlement_at=settlement_at)
            total_required = sum(
                (_to_decimal(item["consumed_credits"]) for item in metric_charges),
                start=_ZERO,
            )
            total_available = sum(
                (_to_decimal(bucket.available_credits) for bucket in buckets),
                start=_ZERO,
            )
            if total_required <= _ZERO:
                return {
                    "status": "noop",
                    "usage_bid": usage.usage_bid,
                    "creator_bid": creator_bid,
                    "entry_count": 0,
                    "consumed_credits": 0,
                }
            if total_available < total_required:
                return {
                    "status": "insufficient",
                    "usage_bid": usage.usage_bid,
                    "creator_bid": creator_bid,
                    "entry_count": 0,
                    "consumed_credits": _decimal_to_number(total_required),
                }

            balance_after = total_available
            entry_count = 0
            total_consumed = _ZERO
            for charge in metric_charges:
                remaining = _to_decimal(charge["consumed_credits"])
                for bucket in buckets:
                    bucket_available = _to_decimal(bucket.available_credits)
                    if remaining <= _ZERO:
                        break
                    if bucket_available <= _ZERO:
                        continue

                    consumed = min(bucket_available, remaining)
                    balance_after -= consumed
                    remaining -= consumed
                    total_consumed += consumed
                    bucket.available_credits = bucket_available - consumed
                    bucket.consumed_credits = (
                        _to_decimal(bucket.consumed_credits) + consumed
                    )
                    sync_credit_bucket_status(bucket)
                    db.session.add(bucket)

                    ledger_entry = CreditLedgerEntry(
                        ledger_bid=generate_id(app),
                        creator_bid=creator_bid,
                        wallet_bid=wallet.wallet_bid,
                        wallet_bucket_bid=bucket.wallet_bucket_bid,
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                        source_type=CREDIT_SOURCE_TYPE_USAGE,
                        source_bid=usage.usage_bid,
                        idempotency_key=(
                            f"usage:{usage.usage_bid}:{charge['billing_metric']}:"
                            f"{bucket.wallet_bucket_bid}:consume"
                        ),
                        amount=-consumed,
                        balance_after=balance_after,
                        expires_at=bucket.effective_to,
                        consumable_from=bucket.effective_from,
                        metadata_json=build_usage_entry_metadata(
                            usage=usage,
                            charge=charge,
                            consumed=consumed,
                        ),
                    )
                    db.session.add(ledger_entry)
                    entry_count += 1

                if remaining <= _ZERO:
                    continue
                db.session.rollback()
                return {
                    "status": "insufficient",
                    "usage_bid": usage.usage_bid,
                    "creator_bid": creator_bid,
                    "entry_count": 0,
                    "consumed_credits": _decimal_to_number(total_required),
                }

            refresh_credit_wallet_snapshot(wallet)
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
            return {
                "status": "settled",
                "usage_bid": usage.usage_bid,
                "creator_bid": creator_bid,
                "entry_count": entry_count,
                "consumed_credits": _decimal_to_number(total_consumed),
            }


def replay_bill_usage_settlement(
    app: Flask,
    *,
    creator_bid: str = "",
    usage_bid: str = "",
    usage_id: int | None = None,
) -> dict[str, Any]:
    """Replay a usage settlement safely without duplicating credit consumption."""

    requested_creator_bid = str(creator_bid or "").strip() or None
    normalized_usage_bid = str(usage_bid or "").strip()
    with app.app_context():
        usage = _load_usage_record(usage_bid=normalized_usage_bid, usage_id=usage_id)
        if usage is None:
            return {
                "status": "not_found",
                "usage_bid": normalized_usage_bid or None,
                "usage_id": usage_id,
                "requested_creator_bid": requested_creator_bid,
                "replay": True,
            }

        resolved_creator_bid = str(resolve_usage_creator_bid(app, usage) or "").strip()
        if (
            requested_creator_bid is not None
            and resolved_creator_bid
            and requested_creator_bid != resolved_creator_bid
        ):
            return {
                "status": "creator_mismatch",
                "usage_bid": usage.usage_bid,
                "usage_id": int(usage.id or 0),
                "creator_bid": resolved_creator_bid,
                "requested_creator_bid": requested_creator_bid,
                "replay": True,
            }

    payload = settle_bill_usage(
        app,
        usage_bid=normalized_usage_bid,
        usage_id=usage_id,
    )
    payload["requested_creator_bid"] = requested_creator_bid
    payload["replay"] = True
    return payload


def backfill_bill_usage_settlement(
    app: Flask,
    *,
    creator_bid: str = "",
    usage_bid: str = "",
    usage_id_start: int | None = None,
    usage_id_end: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
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
        payload["backfill"] = True
        return payload

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
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = replay_bill_usage_settlement(
            app,
            creator_bid=normalized_creator_bid,
            usage_bid=row.usage_bid,
            usage_id=int(row.id or 0),
        )
        status = str(payload.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        items.append(
            {
                "usage_bid": row.usage_bid,
                "usage_id": int(row.id or 0),
                "status": status,
                "creator_bid": payload.get("creator_bid"),
                "requested_creator_bid": payload.get("requested_creator_bid"),
            }
        )

    return {
        "status": "completed" if items else "noop",
        "creator_bid": normalized_creator_bid or None,
        "usage_id_start": usage_id_start,
        "usage_id_end": usage_id_end,
        "limit": normalized_limit,
        "processed_count": len(items),
        "status_counts": status_counts,
        "items": items,
        "backfill": True,
    }


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


def _build_skip_result(usage: BillUsageRecord, *, reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": reason,
        "usage_bid": usage.usage_bid,
    }


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
        .order_by(CreditWalletBucket.priority.asc(), CreditWalletBucket.id.asc())
        .all()
    )
    eligible = [
        row
        for row in rows
        if _to_decimal(row.available_credits) > _ZERO
        and (row.effective_from is None or row.effective_from <= settlement_at)
        and (row.effective_to is None or row.effective_to > settlement_at)
    ]
    eligible.sort(
        key=lambda row: (
            int(row.priority or 0),
            row.effective_to is None,
            row.effective_to or datetime.max,
            row.created_at or datetime.min,
            int(row.id or 0),
        )
    )
    return eligible


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _decimal_to_number(value: Decimal | Any) -> int | float:
    decimal_value = _to_decimal(value)
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return float(decimal_value)
