"""Wallet bucket snapshot helpers for creator billing."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Any

from flaskr.dao import db

from .consts import (
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_CANCELED,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
)
from .models import CreditWallet, CreditWalletBucket

_ZERO = Decimal("0")
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


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))
