"""Shared bucket identity rules used by wallet expiration and repair flows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .bucket_categories import (
    load_billing_order_type_by_bid,
    resolve_wallet_bucket_runtime_category,
)
from .consts import CREDIT_BUCKET_CATEGORY_TOPUP
from .models import CreditLedgerEntry, CreditWallet, CreditWalletBucket

if TYPE_CHECKING:
    from datetime import datetime


def _build_legacy_expire_ledger_idempotency_key(wallet_bucket_bid: str) -> str:
    return f"expire:{str(wallet_bucket_bid or '').strip()}"


def _build_expire_ledger_idempotency_key(
    wallet_bucket_bid: str,
    *,
    effective_to: datetime | None,
) -> str:
    normalized_bucket_bid = str(wallet_bucket_bid or "").strip()
    if effective_to is None:
        return _build_legacy_expire_ledger_idempotency_key(normalized_bucket_bid)
    return (
        f"{_build_legacy_expire_ledger_idempotency_key(normalized_bucket_bid)}:"
        f"{effective_to.strftime('%Y%m%d%H%M%S')}"
    )


def _is_matching_expire_ledger_for_bucket(
    ledger: CreditLedgerEntry,
    bucket: CreditWalletBucket,
) -> bool:
    normalized_bucket_bid = str(bucket.wallet_bucket_bid or "").strip()
    normalized_creator_bid = str(bucket.creator_bid or "").strip()
    if str(ledger.wallet_bucket_bid or "").strip() != normalized_bucket_bid:
        return False
    if str(ledger.creator_bid or "").strip() != normalized_creator_bid:
        return False

    cycle_key = _build_expire_ledger_idempotency_key(
        normalized_bucket_bid,
        effective_to=bucket.effective_to,
    )
    if ledger.idempotency_key == cycle_key:
        return True

    legacy_key = _build_legacy_expire_ledger_idempotency_key(normalized_bucket_bid)
    return (
        ledger.idempotency_key == legacy_key
        and ledger.expires_at == bucket.effective_to
    )


def _is_credit_pack_runtime_bucket(bucket: CreditWalletBucket) -> bool:
    """Return whether a bucket represents non-expiring credit pack ownership."""
    return (
        resolve_wallet_bucket_runtime_category(
            bucket,
            load_order_type=load_billing_order_type_by_bid,
        )
        == CREDIT_BUCKET_CATEGORY_TOPUP
    )


def _load_credit_wallet_by_wallet_bid(wallet_bid: str) -> CreditWallet | None:
    return (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.wallet_bid == str(wallet_bid or "").strip(),
        )
        .order_by(CreditWallet.id.desc())
        .first()
    )
