"""Wallet bucket snapshot helpers for creator billing."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import Any

from flask import Flask
from sqlalchemy.exc import IntegrityError

from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.util.uuid import generate_id

from .consts import (
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
from .bucket_categories import (
    build_wallet_bucket_runtime_sort_key,
    load_billing_order_type_by_bid,
    resolve_credit_bucket_priority,
    resolve_runtime_credit_bucket_category,
    resolve_wallet_bucket_runtime_category,
)
from .dtos import BillingLedgerAdjustResultDTO, BillingWalletRefDTO
from .models import CreditLedgerEntry, CreditWallet, CreditWalletBucket
from .primitives import credit_decimal_to_number as _credit_decimal_to_number
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal

_ZERO = Decimal("0")
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
    wallet_bid: str
    creator_bid: str
    available_credits: int | float
    reserved_credits: int | float

    def to_payload(self) -> dict[str, Any]:
        return {
            "wallet_bid": self.wallet_bid,
            "creator_bid": self.creator_bid,
            "available_credits": self.available_credits,
            "reserved_credits": self.reserved_credits,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class WalletSnapshotRebuildResult:
    status: str
    creator_bid: str | None
    wallet_bid: str | None
    wallet_count: int
    wallets: list[WalletSnapshotRecord] = field(default_factory=list)

    def to_task_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "wallet_bid": self.wallet_bid,
            "wallet_count": self.wallet_count,
            "wallets": [wallet.to_payload() for wallet in self.wallets],
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class RefundReturnCreditsResult:
    status: str
    creator_bid: str | None
    source_bid: str | None
    amount: int | float = 0
    wallet_bucket_bid: str | None = None
    ledger_bid: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "source_bid": self.source_bid,
            "amount": self.amount,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "ledger_bid": self.ledger_bid,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class WalletExpirationResult:
    status: str
    creator_bid: str | None
    bucket_count: int
    expired_credits: int | float

    def to_task_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "bucket_count": self.bucket_count,
            "expired_credits": self.expired_credits,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class ManualCreditGrantResult:
    status: str
    creator_bid: str | None
    amount: int | float = 0
    wallet_bid: str | None = None
    wallet_bucket_bid: str | None = None
    ledger_bid: str | None = None
    expires_at: datetime | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
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
        return self.to_payload()[key]


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
    wallet.available_credits = _quantize_credit_amount(wallet.available_credits)
    wallet.reserved_credits = _quantize_credit_amount(wallet.reserved_credits)
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
        "updated_at": updated_at or datetime.now(),
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
            row.created_at or datetime.min,
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
                wallets=[],
            )

        rebuilt_at = datetime.now()
        payload_wallets: list[WalletSnapshotRecord] = []
        for wallet in wallets:
            refresh_credit_wallet_snapshot(wallet)
            persist_credit_wallet_snapshot(
                wallet,
                available_credits=wallet.available_credits,
                reserved_credits=wallet.reserved_credits,
                updated_at=rebuilt_at,
            )
            payload_wallets.append(
                WalletSnapshotRecord(
                    wallet_bid=wallet.wallet_bid,
                    creator_bid=wallet.creator_bid,
                    available_credits=_credit_decimal_to_number(
                        wallet.available_credits
                    ),
                    reserved_credits=_credit_decimal_to_number(wallet.reserved_credits),
                )
            )

        db.session.commit()
        return WalletSnapshotRebuildResult(
            status="rebuilt",
            creator_bid=normalized_creator_bid or None,
            wallet_bid=normalized_wallet_bid or None,
            wallet_count=len(payload_wallets),
            wallets=payload_wallets,
        )


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
        now = effective_from or datetime.now()
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
        granted_at = effective_from or datetime.now()
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
            metadata_json=normalized_metadata,
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
            metadata_json=normalized_metadata,
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
    cutoff = expire_before or datetime.now()
    with app.app_context():
        result = _expire_credit_wallet_buckets_in_session(
            app,
            creator_bid=normalized_creator_bid,
            expire_before=cutoff,
        )
        db.session.commit()
        return result


def _expire_credit_wallet_buckets_in_session(
    app: Flask,
    *,
    creator_bid: str = "",
    expire_before: datetime | None = None,
) -> WalletExpirationResult:
    """Expire eligible buckets inside the current transaction without committing."""

    normalized_creator_bid = str(creator_bid or "").strip()
    cutoff = expire_before or datetime.now()
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
        bucket.expired_credits = _quantize_credit_amount(
            _to_decimal(bucket.expired_credits) + available
        )
        if _to_decimal(bucket.reserved_credits) > _ZERO:
            sync_credit_bucket_status(bucket)
        else:
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
        expired_total += available
        expired_count += 1

    return WalletExpirationResult(
        status="expired" if expired_count else "noop",
        creator_bid=normalized_creator_bid or None,
        bucket_count=expired_count,
        expired_credits=_credit_decimal_to_number(expired_total),
    )


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
