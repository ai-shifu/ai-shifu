"""Manual admin adjustments and operator deductions on creator credit wallets.

The entry points here are re-exported from ``wallets``. They reach the shared
wallet snapshot helpers (and ``now_utc``) through ``_wallet_core()`` so the
import graph stays acyclic and patches applied to ``wallets`` keep reaching
these flows.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import raise_error
from flaskr.util.uuid import generate_id

from .bucket_categories import (
    load_billing_order_type_by_bid,
    resolve_credit_bucket_priority,
    wallet_bucket_requires_active_subscription,
)
from .consts import (
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .dtos import BillingLedgerAdjustResultDTO, BillingWalletRefDTO
from .models import CreditLedgerEntry, CreditWallet, CreditWalletBucket
from .primitives import credit_decimal_to_number as _credit_decimal_to_number
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .queries import load_primary_active_subscription

if TYPE_CHECKING:
    from datetime import datetime
    from types import ModuleType

    from flask import Flask

_ZERO = Decimal(0)


def _wallet_core() -> ModuleType:
    """Return the ``wallets`` module, resolved lazily to avoid an import cycle."""
    from . import wallets

    return wallets


def _wallet_ref(wallet: CreditWallet) -> BillingWalletRefDTO:
    return BillingWalletRefDTO(
        wallet_bid=wallet.wallet_bid,
        available_credits=_credit_decimal_to_number(wallet.available_credits),
        reserved_credits=_credit_decimal_to_number(wallet.reserved_credits),
    )


def adjust_credit_wallet_balance(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | object,
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

    core = _wallet_core()
    with app_context_scope(app), unit_of_work():
        wallet = core._load_or_create_credit_wallet(app, normalized_creator_bid)
        adjustment_bid = generate_id(app)
        adjusted_at = core.now_utc()
        metadata = {
            "adjustment_bid": adjustment_bid,
            "note": normalized_note,
            "operator_user_bid": normalized_operator_user_bid,
        }

        if normalized_amount > _ZERO:
            return _apply_credit_wallet_credit_adjustment(
                app,
                wallet=wallet,
                creator_bid=normalized_creator_bid,
                amount=normalized_amount,
                adjustment_bid=adjustment_bid,
                adjusted_at=adjusted_at,
                metadata=metadata,
            )

        wallet_bucket_bids, ledger_bids = _apply_credit_wallet_debit_adjustment(
            app,
            wallet=wallet,
            creator_bid=normalized_creator_bid,
            remaining=normalized_amount.copy_abs(),
            adjustment_bid=adjustment_bid,
            adjusted_at=adjusted_at,
            metadata=metadata,
        )

        return BillingLedgerAdjustResultDTO(
            status="adjusted",
            adjustment_bid=adjustment_bid,
            creator_bid=normalized_creator_bid,
            amount=_credit_decimal_to_number(normalized_amount),
            wallet=_wallet_ref(wallet),
            wallet_bucket_bids=wallet_bucket_bids,
            ledger_bids=ledger_bids,
        )


def _apply_credit_wallet_credit_adjustment(
    app: Flask,
    *,
    wallet: CreditWallet,
    creator_bid: str,
    amount: Decimal,
    adjustment_bid: str,
    adjusted_at: datetime,
    metadata: dict[str, str],
) -> BillingLedgerAdjustResultDTO:
    """Add a new manual bucket for a positive adjustment (caller owns the UoW)."""
    core = _wallet_core()
    bucket = CreditWalletBucket(
        wallet_bucket_bid=generate_id(app),
        wallet_bid=wallet.wallet_bid,
        creator_bid=creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        source_bid=adjustment_bid,
        priority=resolve_credit_bucket_priority(CREDIT_BUCKET_CATEGORY_SUBSCRIPTION),
        original_credits=amount,
        available_credits=amount,
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
    core.sync_credit_bucket_status(bucket)
    core.refresh_credit_wallet_snapshot(wallet)
    ledger_entry = CreditLedgerEntry(
        ledger_bid=generate_id(app),
        creator_bid=creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        source_bid=adjustment_bid,
        idempotency_key=f"adjustment:{adjustment_bid}:{bucket.wallet_bucket_bid}",
        amount=amount,
        balance_after=_quantize_credit_amount(wallet.available_credits),
        expires_at=None,
        consumable_from=adjusted_at,
        metadata_json={
            **metadata,
            "direction": "credit",
        },
    )
    core.persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        updated_at=adjusted_at,
    )
    db.session.add(ledger_entry)
    return BillingLedgerAdjustResultDTO(
        status="adjusted",
        adjustment_bid=adjustment_bid,
        creator_bid=creator_bid,
        amount=_credit_decimal_to_number(amount),
        wallet=_wallet_ref(wallet),
        wallet_bucket_bids=[bucket.wallet_bucket_bid],
        ledger_bids=[ledger_entry.ledger_bid],
    )


def _apply_credit_wallet_debit_adjustment(
    app: Flask,
    *,
    wallet: CreditWallet,
    creator_bid: str,
    remaining: Decimal,
    adjustment_bid: str,
    adjusted_at: datetime,
    metadata: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Debit adjustable buckets for a negative adjustment (caller owns the UoW)."""
    core = _wallet_core()
    buckets = core._load_adjustable_credit_buckets(
        creator_bid,
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
        bucket.available_credits = _quantize_credit_amount(available - adjusted_amount)
        bucket.consumed_credits = _quantize_credit_amount(
            _to_decimal(bucket.consumed_credits) + adjusted_amount
        )
        core.sync_credit_bucket_status(bucket)
        db.session.add(bucket)
        core.refresh_credit_wallet_snapshot(wallet)
        ledger_entry = CreditLedgerEntry(
            ledger_bid=generate_id(app),
            creator_bid=creator_bid,
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
        core.persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            updated_at=adjusted_at,
        )
        db.session.add(ledger_entry)
        wallet_bucket_bids.append(bucket.wallet_bucket_bid)
        ledger_bids.append(ledger_entry.ledger_bid)
        remaining -= adjusted_amount
    return wallet_bucket_bids, ledger_bids


def deduct_operator_credit_wallet_balance(
    app: Flask,
    *,
    creator_bid: str,
    amount: Decimal | object,
    request_id: str,
    reason: str,
    note: str = "",
    operator_user_bid: str = "",
) -> BillingLedgerAdjustResultDTO:
    """Deduct paid credits before manual grants with request-level idempotency."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_amount = _quantize_credit_amount(amount)
    normalized_request_id = str(request_id or "").strip()
    normalized_reason = str(reason or "").strip()
    normalized_note = str(note or "").strip()
    normalized_operator_user_bid = str(operator_user_bid or "").strip()
    if (
        not normalized_creator_bid
        or not normalized_request_id
        or len(normalized_request_id) > 36
        or normalized_amount <= _ZERO
        or not normalized_reason
    ):
        return BillingLedgerAdjustResultDTO(
            status="noop",
            creator_bid=normalized_creator_bid or None,
            amount=_credit_decimal_to_number(-normalized_amount),
        )

    core = _wallet_core()
    with app_context_scope(app), unit_of_work():
        wallet = core._load_or_create_credit_wallet(app, normalized_creator_bid)
        db.session.refresh(wallet, with_for_update=True)
        existing_result = _load_existing_operator_deduction_result(
            wallet=wallet,
            creator_bid=normalized_creator_bid,
            request_id=normalized_request_id,
            amount=normalized_amount,
            reason=normalized_reason,
            note=normalized_note,
        )
        if existing_result is not None:
            return existing_result

        paid_buckets, manual_buckets = _partition_operator_deduction_buckets(
            normalized_creator_bid
        )

        ordered_buckets = [*paid_buckets, *manual_buckets]
        total_available = sum(
            (_to_decimal(bucket.available_credits) for bucket in ordered_buckets),
            start=_ZERO,
        )
        if total_available < normalized_amount:
            raise_error("server.billing.creditDeductionInsufficient")

        deducted_at = core.now_utc()
        wallet_bucket_bids, ledger_bids = _apply_operator_deduction(
            app,
            wallet=wallet,
            ordered_buckets=ordered_buckets,
            manual_buckets=manual_buckets,
            creator_bid=normalized_creator_bid,
            amount=normalized_amount,
            request_id=normalized_request_id,
            reason=normalized_reason,
            note=normalized_note,
            operator_user_bid=normalized_operator_user_bid,
            deducted_at=deducted_at,
        )

        core.persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            updated_at=deducted_at,
        )
        return BillingLedgerAdjustResultDTO(
            status="deducted",
            adjustment_bid=normalized_request_id,
            creator_bid=normalized_creator_bid,
            amount=_credit_decimal_to_number(-normalized_amount),
            wallet=_wallet_ref(wallet),
            wallet_bucket_bids=wallet_bucket_bids,
            ledger_bids=ledger_bids,
        )


def _load_existing_operator_deduction_result(
    *,
    wallet: CreditWallet,
    creator_bid: str,
    request_id: str,
    amount: Decimal,
    reason: str,
    note: str,
) -> BillingLedgerAdjustResultDTO | None:
    """Replay an earlier deduction with the same request id, or reject a conflict."""
    existing_entries = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == creator_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_MANUAL,
            CreditLedgerEntry.source_bid == request_id,
        )
        .order_by(CreditLedgerEntry.id.asc())
        .with_for_update()
        .all()
    )
    if not existing_entries:
        return None
    original_metadata = existing_entries[0].metadata_json or {}
    original_amount = _quantize_credit_amount(
        original_metadata.get("requested_amount", 0)
    )
    if (
        original_metadata.get("operation") != "operator_credit_deduction"
        or original_amount != amount
        or str(original_metadata.get("reason") or "") != reason
        or str(original_metadata.get("note") or "") != note
    ):
        raise_error("server.billing.creditDeductionRequestConflict")
    return BillingLedgerAdjustResultDTO(
        status="noop_existing",
        adjustment_bid=request_id,
        creator_bid=creator_bid,
        amount=_credit_decimal_to_number(-original_amount),
        wallet=_wallet_ref(wallet),
        wallet_bucket_bids=[entry.wallet_bucket_bid for entry in existing_entries],
        ledger_bids=[entry.ledger_bid for entry in existing_entries],
    )


def _partition_operator_deduction_buckets(
    creator_bid: str,
) -> tuple[list[CreditWalletBucket], list[CreditWalletBucket]]:
    """Lock eligible buckets and split them into paid-first and manual groups."""
    core = _wallet_core()
    eligible = core._load_adjustable_credit_buckets(
        creator_bid,
        adjustment_at=core.now_utc(),
        for_update=True,
    )
    paid_buckets: list[CreditWalletBucket] = []
    manual_buckets: list[CreditWalletBucket] = []
    has_active_subscription = (
        load_primary_active_subscription(
            creator_bid,
            as_of=core.now_utc(),
        )
        is not None
    )
    for bucket in eligible:
        metadata = (
            bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}
        )
        if metadata.get("refund_return") is True:
            has_non_refund_grant = (
                CreditLedgerEntry.query.filter(
                    CreditLedgerEntry.deleted == 0,
                    CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
                    CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    CreditLedgerEntry.amount > _ZERO,
                )
                .with_for_update()
                .first()
                is not None
            )
            if has_non_refund_grant:
                raise_error("server.billing.creditDeductionOriginAmbiguous")
            continue
        if not has_active_subscription and wallet_bucket_requires_active_subscription(
            bucket,
            load_order_type=load_billing_order_type_by_bid,
        ):
            continue
        if _is_operator_manual_credit_bucket(bucket):
            manual_buckets.append(bucket)
        elif int(bucket.source_type or 0) in {
            CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            CREDIT_SOURCE_TYPE_TOPUP,
        }:
            package_origin = _resolve_operator_package_bucket_origin(bucket)
            if package_origin == "ambiguous":
                raise_error("server.billing.creditDeductionOriginAmbiguous")
            if package_origin == "manual":
                manual_buckets.append(bucket)
            else:
                paid_buckets.append(bucket)
    return paid_buckets, manual_buckets


def _apply_operator_deduction(
    app: Flask,
    *,
    wallet: CreditWallet,
    ordered_buckets: list[CreditWalletBucket],
    manual_buckets: list[CreditWalletBucket],
    creator_bid: str,
    amount: Decimal,
    request_id: str,
    reason: str,
    note: str,
    operator_user_bid: str,
    deducted_at: datetime,
) -> tuple[list[str], list[str]]:
    """Debit buckets in order and stage one ledger entry per touched bucket."""
    core = _wallet_core()
    remaining = amount
    wallet_bucket_bids: list[str] = []
    ledger_bids: list[str] = []
    for bucket in ordered_buckets:
        if remaining <= _ZERO:
            break
        available = _to_decimal(bucket.available_credits)
        if available <= _ZERO:
            continue
        deducted_amount = _quantize_credit_amount(min(available, remaining))
        bucket.available_credits = _quantize_credit_amount(available - deducted_amount)
        bucket.consumed_credits = _quantize_credit_amount(
            _to_decimal(bucket.consumed_credits) + deducted_amount
        )
        core.sync_credit_bucket_status(bucket)
        db.session.add(bucket)
        core.refresh_credit_wallet_snapshot(wallet, snapshot_at=deducted_at)
        ledger_entry = CreditLedgerEntry(
            ledger_bid=generate_id(app),
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=request_id,
            idempotency_key=(
                f"operator_credit_deduction:{request_id}"
                if not ledger_bids
                else f"operator_credit_deduction:{request_id}:{bucket.wallet_bucket_bid}"
            ),
            amount=-deducted_amount,
            balance_after=_quantize_credit_amount(wallet.available_credits),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={
                "operation": "operator_credit_deduction",
                "direction": "debit",
                "request_id": request_id,
                "requested_amount": str(amount),
                "reason": reason,
                "note": note,
                "operator_user_bid": operator_user_bid,
                "credit_origin": ("manual" if bucket in manual_buckets else "paid"),
            },
        )
        db.session.add(ledger_entry)
        wallet_bucket_bids.append(bucket.wallet_bucket_bid)
        ledger_bids.append(ledger_entry.ledger_bid)
        remaining = _quantize_credit_amount(remaining - deducted_amount)
    return wallet_bucket_bids, ledger_bids


def _is_operator_manual_credit_bucket(bucket: CreditWalletBucket) -> bool:
    if int(bucket.source_type or 0) != CREDIT_SOURCE_TYPE_MANUAL:
        return False
    metadata = bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}
    return (
        str(metadata.get("grant_source") or "").strip().lower() != "reward"
        and str(metadata.get("grant_type") or "").strip().lower() != "referral_reward"
    )


def _resolve_operator_package_bucket_origin(bucket: CreditWalletBucket) -> str:
    grant_entries = CreditLedgerEntry.query.filter(
        CreditLedgerEntry.deleted == 0,
        CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
        CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        CreditLedgerEntry.amount > _ZERO,
    ).all()
    providers = {
        str((entry.metadata_json or {}).get("payment_provider") or "").strip().lower()
        for entry in grant_entries
        if isinstance(entry.metadata_json, dict)
        and str((entry.metadata_json or {}).get("payment_provider") or "").strip()
    }
    has_manual = "manual" in providers
    has_paid = any(provider != "manual" for provider in providers)
    if has_manual and has_paid:
        return "ambiguous"
    if has_manual:
        return "manual"
    if has_paid:
        return "paid"

    metadata = bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}
    provider = str(metadata.get("payment_provider") or "").strip().lower()
    if provider == "manual":
        return "manual"
    if provider:
        return "paid"
    return "ambiguous"
