"""Shared credit state mutation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.util.datetime import now_utc

from .consts import CREDIT_BUCKET_STATUS_EXHAUSTED, CREDIT_BUCKET_STATUS_EXPIRED
from .primitives import normalize_json_object, quantize_credit_amount, to_decimal
from .wallets import sync_credit_bucket_status

if TYPE_CHECKING:
    from datetime import datetime

    from .models import CreditLedgerEntry, CreditWalletBucket


@dataclass(slots=True, frozen=True)
class CreditMutationResult:
    """Capture wallet and ledger changes from one credit mutation."""

    mutation_type: str
    completed: bool
    status: str
    ledger_bid: str | None = None
    wallet_bucket_bid: str | None = None
    expected_amount: Decimal = Decimal(0)
    moved_amount: Decimal = Decimal(0)
    failure_reason: str | None = None


def reserved_grant_state(grant_entry: CreditLedgerEntry) -> str:
    metadata = normalize_json_object(grant_entry.metadata_json)
    return str(metadata.get("bucket_credit_state") or "").strip().lower()


def activate_reserved_grant_credit(
    *,
    grant_entry: CreditLedgerEntry | None,
    bucket: CreditWalletBucket | None,
    effective_from: datetime,
    effective_to: datetime | None,
    now: datetime | None = None,
) -> CreditMutationResult:
    """Move a reserved grant amount from bucket reserved credits to available."""
    mutation_type = "reserved_grant_activate"
    if grant_entry is None:
        return CreditMutationResult(
            mutation_type=mutation_type,
            completed=False,
            status="skipped",
            failure_reason="missing_ledger",
        )
    if bucket is None:
        return CreditMutationResult(
            mutation_type=mutation_type,
            completed=False,
            status="skipped",
            ledger_bid=grant_entry.ledger_bid,
            failure_reason="missing_bucket",
        )

    metadata = normalize_json_object(grant_entry.metadata_json)
    state = str(metadata.get("bucket_credit_state") or "").strip().lower()
    if state != "reserved":
        return CreditMutationResult(
            mutation_type=mutation_type,
            completed=False,
            status="skipped",
            ledger_bid=grant_entry.ledger_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            failure_reason=f"invalid_state:{state or 'missing'}",
        )

    grant_amount = quantize_credit_amount(to_decimal(grant_entry.amount))
    reserved_credits = quantize_credit_amount(to_decimal(bucket.reserved_credits))
    if grant_amount <= 0:
        return CreditMutationResult(
            mutation_type=mutation_type,
            completed=False,
            status="skipped",
            ledger_bid=grant_entry.ledger_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            expected_amount=grant_amount,
            failure_reason="invalid_amount",
        )
    if reserved_credits < grant_amount:
        return CreditMutationResult(
            mutation_type=mutation_type,
            completed=False,
            status="skipped",
            ledger_bid=grant_entry.ledger_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            expected_amount=grant_amount,
            failure_reason="insufficient_reserved",
        )

    mutation_time = now or now_utc()
    bucket.reserved_credits = quantize_credit_amount(
        to_decimal(bucket.reserved_credits) - grant_amount
    )
    bucket.available_credits = quantize_credit_amount(
        to_decimal(bucket.available_credits) + grant_amount
    )
    bucket.effective_from = effective_from
    bucket.effective_to = effective_to
    bucket.updated_at = mutation_time
    if int(bucket.status or 0) == CREDIT_BUCKET_STATUS_EXPIRED:
        bucket.status = CREDIT_BUCKET_STATUS_EXHAUSTED
    sync_credit_bucket_status(bucket)
    db.session.add(bucket)

    metadata["bucket_credit_state"] = "available"
    metadata["activated_at"] = mutation_time.isoformat()
    grant_entry.expires_at = effective_to
    grant_entry.consumable_from = effective_from
    grant_entry.metadata_json = metadata.to_metadata_json()
    grant_entry.updated_at = mutation_time
    db.session.add(grant_entry)

    return CreditMutationResult(
        mutation_type=mutation_type,
        completed=True,
        status="activated",
        ledger_bid=grant_entry.ledger_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        expected_amount=grant_amount,
        moved_amount=grant_amount,
    )
