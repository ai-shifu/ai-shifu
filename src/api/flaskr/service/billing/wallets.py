"""Wallet bucket snapshot helpers for creator billing."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

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
