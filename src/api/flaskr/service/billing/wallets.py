"""Wallet bucket snapshot helpers for creator billing."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.dao.uow import (
    app_context_scope,
    require_transaction_owner,
    unit_of_work,
)
from flaskr.util.datetime import NAIVE_DATETIME_MIN, now_utc
from flaskr.util.uuid import generate_id
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
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_CANCELED,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .primitives import credit_decimal_to_number as _credit_decimal_to_number
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .queries import load_primary_active_subscription

# Re-exported public API: result records, bucket rules, and repair flows now
# live in sibling modules, and the names below keep every historical
# ``wallets`` import path (including plugins) working.
# isort: split
from flaskr.service.common.models import (  # noqa: F401  # re-exported public API
    raise_error,
)
from flaskr.util.datetime import (  # noqa: F401  # re-exported public API
    to_utc_iso,
)

from .consts import (  # noqa: F401  # re-exported public API
    ACTIVE_SUBSCRIPTION_STATUSES,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
)
from .dtos import (  # noqa: F401  # re-exported public API
    BillingLedgerAdjustResultDTO,
    BillingWalletRefDTO,
)
from .models import (  # noqa: F401  # re-exported public API
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
)
from .wallet_adjustments import (  # noqa: F401  # re-exported public API
    _is_operator_manual_credit_bucket,
    _resolve_operator_package_bucket_origin,
    adjust_credit_wallet_balance,
    deduct_operator_credit_wallet_balance,
)
from .wallet_bucket_rules import (  # noqa: F401  # re-exported public API
    _build_expire_ledger_idempotency_key,
    _build_legacy_expire_ledger_idempotency_key,
    _is_credit_pack_runtime_bucket,
    _is_matching_expire_ledger_for_bucket,
    _load_credit_wallet_by_wallet_bid,
)
from .wallet_repairs import (  # noqa: F401  # re-exported public API
    repair_credit_bucket_runtime_statuses,
    repair_expire_ledger_bucket_drift,
    repair_renewal_state_drift,
    restore_wrongly_expired_credit_pack_buckets,
)
from .wallet_results import (  # noqa: F401  # re-exported public API
    ExpiredCreditPackBucketRestoreRecord,
    ExpiredCreditPackBucketRestoreResult,
    ExpireLedgerBucketDriftRecord,
    ExpireLedgerBucketDriftRepairResult,
    ManualCreditGrantResult,
    RefundReturnCreditsResult,
    RenewalStateDriftRepairResult,
    ReservedGrantRepairRecord,
    WalletExpirationResult,
    WalletSnapshotRebuildResult,
    WalletSnapshotRecord,
)

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
    available_credits: Decimal | object,
    reserved_credits: Decimal | object,
    lifetime_granted_credits: Decimal | object | None = None,
    lifetime_consumed_credits: Decimal | object | None = None,
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
    """Resolve bucket source type for category."""
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
    """Load primary credit bucket by category."""
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
    metadata: dict[str, object] | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> CreditWalletBucket:
    """Load or create credit bucket by category."""
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
    # A dry run stages nothing, so it must not own a transaction boundary at
    # all: a caller's pending work stays pending (neither committed nor
    # rolled back), exactly as before the migration.
    boundary = nullcontext() if dry_run else unit_of_work()
    with app_context_scope(app), boundary:
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

        return WalletSnapshotRebuildResult(
            status="dry_run" if dry_run else "rebuilt",
            creator_bid=normalized_creator_bid or None,
            wallet_bid=normalized_wallet_bid or None,
            wallet_count=len(payload_wallets),
            changed_wallet_count=changed_wallet_count,
            dry_run=dry_run,
            wallets=payload_wallets,
        )


def grant_refund_return_credits(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | object,
    refund_bid: str,
    metadata: dict[str, object] | None = None,
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

    with app_context_scope(app), unit_of_work():
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
        return RefundReturnCreditsResult(
            status="granted",
            creator_bid=normalized_creator_bid,
            source_bid=normalized_refund_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            ledger_bid=ledger_entry.ledger_bid,
        )


def grant_manual_credit_wallet_balance(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | object,
    source_bid: str = "",
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    metadata: dict[str, object] | None = None,
    ledger_metadata: dict[str, object] | None = None,
    idempotency_key: str = "",
) -> ManualCreditGrantResult:
    """Create a dedicated manual-grant bucket and matching ledger row."""
    # Idempotency depends on the IntegrityError reaching the handler below,
    # which only happens when this call owns the outermost unit of work.
    require_transaction_owner("manual credit grant", app)
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

    with app_context_scope(app):
        granted_at = effective_from or now_utc()
        grant_bid = normalized_source_bid or generate_id(app)
        ledger_key = normalized_idempotency_key or f"manual_grant:{grant_bid}"
        try:
            return _grant_manual_credit_wallet_balance_once(
                app,
                creator_bid=normalized_creator_bid,
                amount=normalized_amount,
                grant_bid=grant_bid,
                ledger_key=ledger_key,
                granted_at=granted_at,
                effective_to=effective_to,
                metadata=metadata,
                ledger_metadata=ledger_metadata,
            )
        except IntegrityError:
            # A concurrent grant with the same idempotency key won; the unit
            # of work rolled ours back, so answer with the winner's result.
            existing_result = _load_existing_manual_credit_grant_result(
                creator_bid=normalized_creator_bid,
                ledger_key=ledger_key,
            )
            if existing_result is not None:
                return existing_result
            raise


def _grant_manual_credit_wallet_balance_once(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal,
    grant_bid: str,
    ledger_key: str,
    granted_at: datetime,
    effective_to: datetime | None,
    metadata: dict[str, object] | None,
    ledger_metadata: dict[str, object] | None,
) -> ManualCreditGrantResult:
    normalized_creator_bid = creator_bid
    normalized_amount = amount
    with unit_of_work():
        wallet = _load_or_create_credit_wallet(app, normalized_creator_bid)

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
    with app_context_scope(app), unit_of_work():
        return _expire_credit_wallet_buckets_in_session(
            app,
            creator_bid=normalized_creator_bid,
            expire_before=cutoff,
        )


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
    for_update: bool = False,
) -> list[CreditWalletBucket]:
    query = CreditWalletBucket.query.filter(
        CreditWalletBucket.deleted == 0,
        CreditWalletBucket.creator_bid == str(creator_bid or "").strip(),
        CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
    ).order_by(
        CreditWalletBucket.priority.asc(),
        CreditWalletBucket.id.asc(),
    )
    if for_update:
        query = query.with_for_update()
    rows = query.all()
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
