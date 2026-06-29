"""Operation-scoped credit reservations for async creator actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from flask import Flask
from sqlalchemy import or_

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW, BILL_USAGE_TYPE_TTS
from flaskr.service.metering.models import BillUsageRecord
from flaskr.util.uuid import generate_id

from . import primitives as billing_primitives
from .bucket_categories import (
    build_wallet_bucket_runtime_sort_key,
    load_billing_order_type_by_bid,
)
from .charges import build_metric_charge
from .consts import (
    BILLING_METRIC_TTS_REQUEST_COUNT,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_HOLD,
    CREDIT_LEDGER_ENTRY_TYPE_RELEASE,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_USAGE,
)
from .models import CreditLedgerEntry, CreditWallet, CreditWalletBucket
from .wallets import persist_credit_wallet_snapshot, sync_credit_bucket_status


_ZERO = Decimal("0")


@dataclass(slots=True, frozen=True)
class OperationCreditEstimate:
    consumed_credits: Decimal
    billing_metric: int = BILLING_METRIC_TTS_REQUEST_COUNT
    status: str = "rated"


@dataclass(slots=True, frozen=True)
class OperationCreditReservationResult:
    status: str
    reservation_bid: str
    creator_bid: str
    amount: Decimal
    wallet_bid: str = ""
    ledger_bid: str = ""
    wallet_bucket_bids: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class OperationCreditCaptureResult:
    status: str
    reservation_bid: str
    usage_bid: str
    ledger_bid: str
    amount: Decimal


@dataclass(slots=True, frozen=True)
class OperationCreditReleaseResult:
    status: str
    reservation_bid: str
    ledger_bid: str
    amount: Decimal


def estimate_voice_clone_operation_credits(app: Flask) -> OperationCreditEstimate:
    """Estimate MiniMax voice-clone cost using only configured active rates."""

    with app.app_context():
        now = datetime.now()
        usage = BillUsageRecord(
            usage_type=BILL_USAGE_TYPE_TTS,
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
            provider="minimax",
            model="voice_clone",
        )
        charge = build_metric_charge(
            usage,
            billing_metric=BILLING_METRIC_TTS_REQUEST_COUNT,
            raw_amount=1,
            settlement_at=now,
        )
        if charge is None:
            return OperationCreditEstimate(consumed_credits=_ZERO, status="no_rate")
        return OperationCreditEstimate(
            consumed_credits=billing_primitives.quantize_credit_amount(
                charge.consumed_credits
            ),
            billing_metric=int(charge.billing_metric),
            status="rated",
        )


def reserve_operation_credits(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal,
    operation_type: str,
    operation_bid: str,
    metadata: dict[str, Any] | None = None,
) -> OperationCreditReservationResult:
    normalized_creator_bid = _require_bid(creator_bid, "creator_bid")
    normalized_operation_type = _require_bid(operation_type, "operation_type")
    normalized_operation_bid = _require_bid(operation_bid, "operation_bid")
    normalized_amount = billing_primitives.quantize_credit_amount(amount)
    if normalized_amount <= _ZERO:
        return OperationCreditReservationResult(
            status="not_required",
            reservation_bid="",
            creator_bid=normalized_creator_bid,
            amount=_ZERO,
        )

    with app.app_context():
        idempotency_key = _reserve_idempotency_key(
            normalized_operation_type,
            normalized_operation_bid,
        )
        existing = _load_ledger_by_idempotency(normalized_creator_bid, idempotency_key)
        if existing is not None:
            return _reservation_result_from_hold(existing)

        wallet = _load_wallet(normalized_creator_bid, lock=True)
        buckets = _load_active_buckets(wallet, datetime.now(), lock=True)
        available = sum(
            (
                billing_primitives.to_decimal(bucket.available_credits)
                for bucket in buckets
            ),
            start=_ZERO,
        )
        if available < normalized_amount:
            raise_error("server.billing.creditInsufficient")

        remaining = normalized_amount
        bucket_breakdown: list[dict[str, Any]] = []
        for bucket in buckets:
            if remaining <= _ZERO:
                break
            bucket_available = billing_primitives.to_decimal(bucket.available_credits)
            if bucket_available <= _ZERO:
                continue
            take = min(bucket_available, remaining)
            bucket.available_credits = billing_primitives.quantize_credit_amount(
                bucket_available - take
            )
            bucket.reserved_credits = billing_primitives.quantize_credit_amount(
                billing_primitives.to_decimal(bucket.reserved_credits) + take
            )
            sync_credit_bucket_status(bucket)
            bucket_breakdown.append(
                {
                    "wallet_bucket_bid": bucket.wallet_bucket_bid,
                    "amount": _credit_to_string(take),
                }
            )
            remaining = billing_primitives.quantize_credit_amount(remaining - take)

        if remaining > _ZERO:
            raise_error("server.billing.creditInsufficient")

        wallet.available_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(wallet.available_credits) - normalized_amount
        )
        wallet.reserved_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(wallet.reserved_credits) + normalized_amount
        )
        persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            updated_at=datetime.now(),
        )

        ledger_bid = generate_id(app)
        ledger_metadata = {
            "operation_type": normalized_operation_type,
            "operation_bid": normalized_operation_bid,
            "bucket_breakdown": bucket_breakdown,
            "metadata": dict(metadata or {}),
        }
        ledger = CreditLedgerEntry(
            ledger_bid=ledger_bid,
            creator_bid=normalized_creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=(
                bucket_breakdown[0]["wallet_bucket_bid"] if bucket_breakdown else ""
            ),
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_HOLD,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=normalized_operation_bid,
            idempotency_key=idempotency_key,
            amount=normalized_amount,
            balance_after=wallet.available_credits,
            metadata_json=ledger_metadata,
        )
        db.session.add(ledger)
        db.session.commit()
        return OperationCreditReservationResult(
            status="reserved",
            reservation_bid=ledger_bid,
            creator_bid=normalized_creator_bid,
            amount=normalized_amount,
            wallet_bid=wallet.wallet_bid,
            ledger_bid=ledger_bid,
            wallet_bucket_bids=[item["wallet_bucket_bid"] for item in bucket_breakdown],
        )


def capture_reserved_operation_credits(
    app: Flask,
    *,
    reservation_bid: str,
    usage_bid: str,
    metadata: dict[str, Any] | None = None,
) -> OperationCreditCaptureResult:
    normalized_reservation_bid = _require_bid(reservation_bid, "reservation_bid")
    normalized_usage_bid = _require_bid(usage_bid, "usage_bid")

    with app.app_context():
        hold = _load_hold(normalized_reservation_bid)
        creator_bid = str(hold.creator_bid or "")
        idempotency_key = _capture_idempotency_key(
            normalized_reservation_bid,
            normalized_usage_bid,
        )
        existing = _load_ledger_by_idempotency(creator_bid, idempotency_key)
        if existing is not None:
            return OperationCreditCaptureResult(
                status="already_captured",
                reservation_bid=normalized_reservation_bid,
                usage_bid=normalized_usage_bid,
                ledger_bid=existing.ledger_bid,
                amount=billing_primitives.to_decimal(abs(existing.amount or 0)),
            )
        if _reservation_has_release(creator_bid, normalized_reservation_bid):
            return OperationCreditCaptureResult(
                status="already_released",
                reservation_bid=normalized_reservation_bid,
                usage_bid=normalized_usage_bid,
                ledger_bid="",
                amount=_ZERO,
            )

        wallet = _load_wallet(creator_bid, lock=True)
        amount = billing_primitives.quantize_credit_amount(hold.amount)
        _apply_capture_to_buckets(hold, amount, lock=True)

        wallet.reserved_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(wallet.reserved_credits) - amount
        )
        wallet.lifetime_consumed_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(wallet.lifetime_consumed_credits) + amount
        )
        persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            lifetime_consumed_credits=wallet.lifetime_consumed_credits,
            updated_at=datetime.now(),
        )

        ledger_bid = generate_id(app)
        ledger = CreditLedgerEntry(
            ledger_bid=ledger_bid,
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=hold.wallet_bucket_bid or "",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid=normalized_usage_bid,
            idempotency_key=idempotency_key,
            amount=-amount,
            balance_after=wallet.available_credits,
            metadata_json={
                "reservation_bid": normalized_reservation_bid,
                "usage_bid": normalized_usage_bid,
                "metadata": dict(metadata or {}),
                "bucket_breakdown": _bucket_breakdown_from_hold(hold),
            },
        )
        db.session.add(ledger)
        db.session.commit()
        return OperationCreditCaptureResult(
            status="captured",
            reservation_bid=normalized_reservation_bid,
            usage_bid=normalized_usage_bid,
            ledger_bid=ledger_bid,
            amount=amount,
        )


def release_reserved_operation_credits(
    app: Flask,
    *,
    reservation_bid: str,
    reason: str = "",
) -> OperationCreditReleaseResult:
    normalized_reservation_bid = _require_bid(reservation_bid, "reservation_bid")

    with app.app_context():
        hold = _load_hold(normalized_reservation_bid)
        creator_bid = str(hold.creator_bid or "")
        if _reservation_has_capture(creator_bid, normalized_reservation_bid):
            return OperationCreditReleaseResult(
                status="already_captured",
                reservation_bid=normalized_reservation_bid,
                ledger_bid="",
                amount=_ZERO,
            )
        idempotency_key = _release_idempotency_key(normalized_reservation_bid)
        existing = _load_ledger_by_idempotency(creator_bid, idempotency_key)
        if existing is not None:
            return OperationCreditReleaseResult(
                status="already_released",
                reservation_bid=normalized_reservation_bid,
                ledger_bid=existing.ledger_bid,
                amount=billing_primitives.to_decimal(existing.amount),
            )

        wallet = _load_wallet(creator_bid, lock=True)
        amount = billing_primitives.quantize_credit_amount(hold.amount)
        _apply_release_to_buckets(hold, amount, lock=True)

        wallet.available_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(wallet.available_credits) + amount
        )
        wallet.reserved_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(wallet.reserved_credits) - amount
        )
        persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            updated_at=datetime.now(),
        )

        ledger_bid = generate_id(app)
        ledger = CreditLedgerEntry(
            ledger_bid=ledger_bid,
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=hold.wallet_bucket_bid or "",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_RELEASE,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=normalized_reservation_bid,
            idempotency_key=idempotency_key,
            amount=amount,
            balance_after=wallet.available_credits,
            metadata_json={
                "reservation_bid": normalized_reservation_bid,
                "reason": str(reason or "").strip(),
                "bucket_breakdown": _bucket_breakdown_from_hold(hold),
            },
        )
        db.session.add(ledger)
        db.session.commit()
        return OperationCreditReleaseResult(
            status="released",
            reservation_bid=normalized_reservation_bid,
            ledger_bid=ledger_bid,
            amount=amount,
        )


def _require_bid(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise_param_error(f"{field_name} is required")
    return normalized


def _reserve_idempotency_key(operation_type: str, operation_bid: str) -> str:
    return f"operation:{operation_type}:{operation_bid}:reserve"


def _capture_idempotency_key(reservation_bid: str, usage_bid: str) -> str:
    return f"operation_reservation:{reservation_bid}:capture:{usage_bid}"


def _release_idempotency_key(reservation_bid: str) -> str:
    return f"operation_reservation:{reservation_bid}:release"


def _load_ledger_by_idempotency(
    creator_bid: str,
    idempotency_key: str,
) -> CreditLedgerEntry | None:
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == creator_bid,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )


def _load_wallet(creator_bid: str, *, lock: bool = False) -> CreditWallet:
    query = CreditWallet.query.filter(
        CreditWallet.deleted == 0,
        CreditWallet.creator_bid == creator_bid,
    )
    if lock:
        query = query.with_for_update()
    wallet = query.order_by(CreditWallet.id.desc()).first()
    if wallet is None:
        raise_error("server.billing.creditInsufficient")
    return wallet


def _load_hold(reservation_bid: str) -> CreditLedgerEntry:
    hold = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.ledger_bid == reservation_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_HOLD,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if hold is None:
        raise_param_error("reservation_bid is invalid")
    return hold


def _load_active_buckets(
    wallet: CreditWallet,
    operation_at: datetime,
    *,
    lock: bool = False,
) -> list[CreditWalletBucket]:
    query = CreditWalletBucket.query.filter(
        CreditWalletBucket.deleted == 0,
        CreditWalletBucket.wallet_bid == wallet.wallet_bid,
        CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
        CreditWalletBucket.effective_from <= operation_at,
        or_(
            CreditWalletBucket.effective_to.is_(None),
            CreditWalletBucket.effective_to > operation_at,
        ),
    )
    if lock:
        query = query.with_for_update()
    rows = query.order_by(
        CreditWalletBucket.priority.asc(), CreditWalletBucket.id.asc()
    ).all()
    candidates = [
        row
        for row in rows
        if billing_primitives.to_decimal(row.available_credits) > _ZERO
    ]
    candidates.sort(
        key=lambda row: build_wallet_bucket_runtime_sort_key(
            row,
            load_order_type=load_billing_order_type_by_bid,
        )
    )
    return candidates


def _reservation_result_from_hold(
    hold: CreditLedgerEntry,
) -> OperationCreditReservationResult:
    return OperationCreditReservationResult(
        status="already_reserved",
        reservation_bid=hold.ledger_bid,
        creator_bid=hold.creator_bid,
        amount=billing_primitives.to_decimal(hold.amount),
        wallet_bid=hold.wallet_bid or "",
        ledger_bid=hold.ledger_bid,
        wallet_bucket_bids=[
            item.get("wallet_bucket_bid", "")
            for item in _bucket_breakdown_from_hold(hold)
            if item.get("wallet_bucket_bid")
        ],
    )


def _bucket_breakdown_from_hold(hold: CreditLedgerEntry) -> list[dict[str, Any]]:
    metadata = hold.metadata_json if isinstance(hold.metadata_json, dict) else {}
    breakdown = metadata.get("bucket_breakdown")
    if isinstance(breakdown, list):
        return [item for item in breakdown if isinstance(item, dict)]
    if hold.wallet_bucket_bid:
        return [
            {
                "wallet_bucket_bid": hold.wallet_bucket_bid,
                "amount": _credit_to_string(hold.amount),
            }
        ]
    return []


def _reservation_has_capture(creator_bid: str, reservation_bid: str) -> bool:
    prefix = f"operation_reservation:{reservation_bid}:capture:"
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == creator_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CreditLedgerEntry.idempotency_key.startswith(prefix),
        ).first()
        is not None
    )


def _reservation_has_release(creator_bid: str, reservation_bid: str) -> bool:
    return (
        _load_ledger_by_idempotency(
            creator_bid,
            _release_idempotency_key(reservation_bid),
        )
        is not None
    )


def _apply_capture_to_buckets(
    hold: CreditLedgerEntry, amount: Decimal, *, lock: bool = False
) -> None:
    for bucket, item_amount in _iter_hold_buckets(hold, lock=lock):
        bucket.reserved_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(bucket.reserved_credits) - item_amount
        )
        bucket.consumed_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(bucket.consumed_credits) + item_amount
        )
        sync_credit_bucket_status(bucket)


def _apply_release_to_buckets(
    hold: CreditLedgerEntry, amount: Decimal, *, lock: bool = False
) -> None:
    for bucket, item_amount in _iter_hold_buckets(hold, lock=lock):
        bucket.available_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(bucket.available_credits) + item_amount
        )
        bucket.reserved_credits = billing_primitives.quantize_credit_amount(
            billing_primitives.to_decimal(bucket.reserved_credits) - item_amount
        )
        sync_credit_bucket_status(bucket)


def _iter_hold_buckets(
    hold: CreditLedgerEntry,
    *,
    lock: bool = False,
) -> list[tuple[CreditWalletBucket, Decimal]]:
    items = _bucket_breakdown_from_hold(hold)
    bucket_pairs: list[tuple[CreditWalletBucket, Decimal]] = []
    for item in items:
        wallet_bucket_bid = str(item.get("wallet_bucket_bid") or "").strip()
        if not wallet_bucket_bid:
            continue
        query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.wallet_bucket_bid == wallet_bucket_bid,
        )
        if lock:
            query = query.with_for_update()
        bucket = query.order_by(CreditWalletBucket.id.desc()).first()
        if bucket is None:
            continue
        item_amount = billing_primitives.quantize_credit_amount(item.get("amount", 0))
        if item_amount > _ZERO:
            bucket_pairs.append((bucket, item_amount))

    total = sum((amount for _, amount in bucket_pairs), start=_ZERO)
    expected = billing_primitives.quantize_credit_amount(hold.amount)
    if bucket_pairs and total == expected:
        return bucket_pairs

    if hold.wallet_bucket_bid:
        query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.wallet_bucket_bid == hold.wallet_bucket_bid,
        )
        if lock:
            query = query.with_for_update()
        fallback_bucket = query.order_by(CreditWalletBucket.id.desc()).first()
        if fallback_bucket is not None:
            return [(fallback_bucket, expected)]
    return []


def _credit_to_string(value: Any) -> str:
    return str(billing_primitives.quantize_credit_amount(value))
