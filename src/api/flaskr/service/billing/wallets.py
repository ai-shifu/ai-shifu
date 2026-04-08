"""Wallet bucket snapshot helpers for creator billing."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.util.uuid import generate_id

from .consts import (
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_CANCELED,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
)
from .models import CreditLedgerEntry, CreditWallet, CreditWalletBucket

_ZERO = Decimal("0")
_FREE_BUCKET_PRIORITY = 10
_PRESERVED_BUCKET_STATUSES = {
    CREDIT_BUCKET_STATUS_CANCELED,
    CREDIT_BUCKET_STATUS_EXPIRED,
}


def refresh_credit_wallet_snapshot(wallet: CreditWallet) -> CreditWallet:
    """Rebuild wallet balances from the current bucket snapshot table."""

    rows = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.wallet_bid == wallet.wallet_bid,
        )
        .order_by(CreditWalletBucket.id.asc())
        .all()
    )
    wallet.available_credits = sum(
        (_to_decimal(row.available_credits) for row in rows),
        start=_ZERO,
    )
    wallet.reserved_credits = sum(
        (_to_decimal(row.reserved_credits) for row in rows),
        start=_ZERO,
    )
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
        "available_credits": _to_decimal(available_credits),
        "reserved_credits": _to_decimal(reserved_credits),
        "version": next_version,
        "updated_at": updated_at or datetime.now(),
    }
    if lifetime_granted_credits is not None:
        values["lifetime_granted_credits"] = _to_decimal(lifetime_granted_credits)
    if lifetime_consumed_credits is not None:
        values["lifetime_consumed_credits"] = _to_decimal(lifetime_consumed_credits)
    if last_settled_usage_id is not None:
        values["last_settled_usage_id"] = int(last_settled_usage_id)

    updated_rows = CreditWallet.query.filter(
        CreditWallet.deleted == 0,
        CreditWallet.id == wallet.id,
        CreditWallet.version == expected_version,
    ).update(values, synchronize_session=False)
    if updated_rows != 1:
        raise RuntimeError("credit_wallet_version_conflict")

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


def rebuild_credit_wallet_snapshots(
    app: Flask,
    *,
    creator_bid: str = "",
    wallet_bid: str = "",
) -> dict[str, Any]:
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
            return {
                "status": "noop",
                "creator_bid": normalized_creator_bid or None,
                "wallet_bid": normalized_wallet_bid or None,
                "wallet_count": 0,
                "wallets": [],
            }

        rebuilt_at = datetime.now()
        payload_wallets: list[dict[str, Any]] = []
        for wallet in wallets:
            refresh_credit_wallet_snapshot(wallet)
            persist_credit_wallet_snapshot(
                wallet,
                available_credits=wallet.available_credits,
                reserved_credits=wallet.reserved_credits,
                updated_at=rebuilt_at,
            )
            payload_wallets.append(
                {
                    "wallet_bid": wallet.wallet_bid,
                    "creator_bid": wallet.creator_bid,
                    "available_credits": _decimal_to_number(wallet.available_credits),
                    "reserved_credits": _decimal_to_number(wallet.reserved_credits),
                }
            )

        db.session.commit()
        return {
            "status": "rebuilt",
            "creator_bid": normalized_creator_bid or None,
            "wallet_bid": normalized_wallet_bid or None,
            "wallet_count": len(payload_wallets),
            "wallets": payload_wallets,
        }


def grant_refund_return_credits(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | Any,
    refund_bid: str,
    metadata: dict[str, Any] | None = None,
    effective_from: datetime | None = None,
) -> dict[str, Any]:
    """Grant refunded credits back as a new free bucket."""

    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_refund_bid = str(refund_bid or "").strip()
    normalized_amount = _to_decimal(amount)
    if (
        not normalized_creator_bid
        or not normalized_refund_bid
        or normalized_amount <= _ZERO
    ):
        return {
            "status": "noop",
            "creator_bid": normalized_creator_bid or None,
            "source_bid": normalized_refund_bid or None,
            "amount": _decimal_to_number(normalized_amount),
        }

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
            return {
                "status": "already_granted",
                "creator_bid": normalized_creator_bid,
                "source_bid": normalized_refund_bid,
                "wallet_bucket_bid": existing_entry.wallet_bucket_bid,
                "ledger_bid": existing_entry.ledger_bid,
            }

        wallet = _load_or_create_credit_wallet(app, normalized_creator_bid)
        now = effective_from or datetime.now()
        bucket = CreditWalletBucket(
            wallet_bucket_bid=generate_id(app),
            wallet_bid=wallet.wallet_bid,
            creator_bid=normalized_creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
            source_type=CREDIT_SOURCE_TYPE_REFUND,
            source_bid=normalized_refund_bid,
            priority=_FREE_BUCKET_PRIORITY,
            original_credits=normalized_amount,
            available_credits=normalized_amount,
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=now,
            effective_to=None,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={
                "refund_return": True,
                **(metadata or {}),
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
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_REFUND,
            source_type=CREDIT_SOURCE_TYPE_REFUND,
            source_bid=normalized_refund_bid,
            idempotency_key=idempotency_key,
            amount=normalized_amount,
            balance_after=_to_decimal(wallet.available_credits),
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
        return {
            "status": "granted",
            "creator_bid": normalized_creator_bid,
            "source_bid": normalized_refund_bid,
            "wallet_bucket_bid": bucket.wallet_bucket_bid,
            "ledger_bid": ledger_entry.ledger_bid,
        }


def adjust_credit_wallet_balance(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | Any,
    note: str = "",
    operator_user_bid: str = "",
) -> dict[str, Any]:
    """Apply a manual admin ledger adjustment through credit buckets."""

    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_amount = _to_decimal(amount)
    normalized_note = str(note or "").strip()
    normalized_operator_user_bid = str(operator_user_bid or "").strip()
    if not normalized_creator_bid or normalized_amount == _ZERO:
        return {
            "status": "noop",
            "creator_bid": normalized_creator_bid or None,
            "amount": _decimal_to_number(normalized_amount),
        }

    with app.app_context():
        wallet = _load_or_create_credit_wallet(app, normalized_creator_bid)
        adjustment_bid = generate_id(app)
        adjusted_at = datetime.now()
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
                bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid=adjustment_bid,
                priority=_FREE_BUCKET_PRIORITY,
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
                balance_after=_to_decimal(wallet.available_credits),
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
            return {
                "status": "adjusted",
                "adjustment_bid": adjustment_bid,
                "creator_bid": normalized_creator_bid,
                "amount": _decimal_to_number(normalized_amount),
                "wallet": {
                    "wallet_bid": wallet.wallet_bid,
                    "available_credits": _decimal_to_number(wallet.available_credits),
                    "reserved_credits": _decimal_to_number(wallet.reserved_credits),
                },
                "wallet_bucket_bids": [bucket.wallet_bucket_bid],
                "ledger_bids": [ledger_entry.ledger_bid],
            }

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

            adjusted_amount = min(available, remaining)
            bucket.available_credits = available - adjusted_amount
            bucket.consumed_credits = (
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
                balance_after=_to_decimal(wallet.available_credits),
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
        return {
            "status": "adjusted",
            "adjustment_bid": adjustment_bid,
            "creator_bid": normalized_creator_bid,
            "amount": _decimal_to_number(normalized_amount),
            "wallet": {
                "wallet_bid": wallet.wallet_bid,
                "available_credits": _decimal_to_number(wallet.available_credits),
                "reserved_credits": _decimal_to_number(wallet.reserved_credits),
            },
            "wallet_bucket_bids": wallet_bucket_bids,
            "ledger_bids": ledger_bids,
        }


def expire_credit_wallet_buckets(
    app: Flask,
    *,
    creator_bid: str = "",
    expire_before: datetime | None = None,
) -> dict[str, Any]:
    """Expire currently active buckets whose effective window has ended."""

    normalized_creator_bid = str(creator_bid or "").strip()
    cutoff = expire_before or datetime.now()
    with app.app_context():
        query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
            CreditWalletBucket.effective_to.isnot(None),
            CreditWalletBucket.effective_to <= cutoff,
        )
        if normalized_creator_bid:
            query = query.filter(
                CreditWalletBucket.creator_bid == normalized_creator_bid
            )
        buckets = query.order_by(
            CreditWalletBucket.effective_to.asc(),
            CreditWalletBucket.created_at.asc(),
            CreditWalletBucket.id.asc(),
        ).all()
        if not buckets:
            return {
                "status": "noop",
                "creator_bid": normalized_creator_bid or None,
                "bucket_count": 0,
                "expired_credits": 0,
            }

        wallets: dict[str, CreditWallet] = {}
        expired_total = _ZERO
        expired_count = 0
        for bucket in buckets:
            available = _to_decimal(bucket.available_credits)
            if available <= _ZERO:
                sync_credit_bucket_status(bucket)
                db.session.add(bucket)
                continue

            wallet = wallets.get(bucket.wallet_bid)
            if wallet is None:
                wallet = _load_credit_wallet_by_wallet_bid(bucket.wallet_bid)
                if wallet is None:
                    continue
                wallets[bucket.wallet_bid] = wallet

            bucket.available_credits = _ZERO
            bucket.expired_credits = _to_decimal(bucket.expired_credits) + available
            bucket.status = CREDIT_BUCKET_STATUS_EXPIRED
            db.session.add(bucket)

            refresh_credit_wallet_snapshot(wallet)
            ledger_entry = CreditLedgerEntry(
                ledger_bid=generate_id(app),
                creator_bid=bucket.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                source_type=bucket.source_type,
                source_bid=bucket.source_bid,
                idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
                amount=-available,
                balance_after=_to_decimal(wallet.available_credits),
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
            expired_total += available
            expired_count += 1

        db.session.commit()
        return {
            "status": "expired" if expired_count else "noop",
            "creator_bid": normalized_creator_bid or None,
            "bucket_count": expired_count,
            "expired_credits": _decimal_to_number(expired_total),
        }


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
        available_credits=Decimal("0"),
        reserved_credits=Decimal("0"),
        lifetime_granted_credits=Decimal("0"),
        lifetime_consumed_credits=Decimal("0"),
        last_settled_usage_id=0,
        version=0,
    )
    db.session.add(wallet)
    db.session.flush()
    return wallet
