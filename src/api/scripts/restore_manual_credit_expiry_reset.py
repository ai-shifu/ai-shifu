"""Restore manual credits shortened by the 2026 cache bonus subscription."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import NoReturn

from billing_cache_compensation_common import dump_json, ensure_api_root_on_path

ensure_api_root_on_path()
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")

from app import create_app  # noqa: E402
from flaskr.service.billing.consts import (  # noqa: E402
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.manual_credit_grants import (  # noqa: E402
    MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
    grant_manual_credits_with_expiry,
)
from flaskr.service.billing.models import (  # noqa: E402
    BillingOrder,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.billing.queries import add_years  # noqa: E402
from flaskr.util.datetime import now_utc, to_utc_iso  # noqa: E402

DEFAULT_CAMPAIGN_ID = "manual-credit-expiry-reset-20260929"
DEFAULT_OPERATOR_USER_BID = "manual-credit-expiry-reset-script"
REPAIR_CHANNEL = "manual_credit_expiry_reset_repair"


@dataclass(frozen=True, slots=True)
class LaterManualGrant:
    """Describe a later manual grant that an operator must reconcile."""

    ledger_bid: str
    amount: Decimal
    grant_source: str


@dataclass(frozen=True, slots=True)
class RecoveryCandidate:
    """Describe one independently evidenced manual-credit recovery."""

    creator_bid: str
    source_wallet_bucket_bid: str
    amount: Decimal
    intended_expires_at: datetime
    source_expire_ledger_bid: str
    later_manual_grants: tuple[LaterManualGrant, ...]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or restore manual credits whose one-year expiry was shortened "
            "by the 2026 cache-overcharge bonus subscription."
        )
    )
    parser.add_argument(
        "--wallet-bucket-bid",
        action="append",
        required=True,
        help="Expired source bucket to validate and restore. Repeat for each bucket.",
    )
    parser.add_argument("--campaign-id", default=DEFAULT_CAMPAIGN_ID)
    parser.add_argument("--operator-user-bid", default=DEFAULT_OPERATOR_USER_BID)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist recovery grants; default is dry-run.",
    )
    return parser


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _fail(code: str, wallet_bucket_bid: str = "") -> NoReturn:
    message = f"{code}:{wallet_bucket_bid}" if wallet_bucket_bid else code
    raise ValueError(message)


def _load_candidate(wallet_bucket_bid: str) -> RecoveryCandidate:
    bucket = CreditWalletBucket.query.filter(
        CreditWalletBucket.deleted == 0,
        CreditWalletBucket.wallet_bucket_bid == wallet_bucket_bid,
    ).one_or_none()
    if bucket is None:
        _fail("bucket_not_found", wallet_bucket_bid)
    if int(bucket.source_type or 0) != CREDIT_SOURCE_TYPE_MANUAL:
        _fail("not_manual_credit", wallet_bucket_bid)
    if int(bucket.status or 0) != CREDIT_BUCKET_STATUS_EXPIRED:
        _fail("bucket_not_expired", wallet_bucket_bid)

    grant = CreditLedgerEntry.query.filter(
        CreditLedgerEntry.deleted == 0,
        CreditLedgerEntry.wallet_bucket_bid == wallet_bucket_bid,
        CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_MANUAL,
    ).one_or_none()
    if grant is None:
        _fail("manual_grant_not_found", wallet_bucket_bid)
    metadata = _json_object(grant.metadata_json)
    if metadata.get("grant_type") != "manual_grant":
        _fail("invalid_grant_type", wallet_bucket_bid)
    if metadata.get("validity_preset") != "1y":
        _fail("unsupported_original_validity", wallet_bucket_bid)
    if grant.consumable_from is None or grant.expires_at is None:
        _fail("missing_grant_window", wallet_bucket_bid)
    intended_expires_at = add_years(grant.consumable_from, 1)
    if grant.expires_at >= intended_expires_at:
        _fail("not_recoverable_window", wallet_bucket_bid)

    expire_entries = CreditLedgerEntry.query.filter(
        CreditLedgerEntry.deleted == 0,
        CreditLedgerEntry.wallet_bucket_bid == wallet_bucket_bid,
        CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    ).all()
    if len(expire_entries) != 1:
        _fail("unexpected_expire_entries", wallet_bucket_bid)
    expire_entry = expire_entries[0]
    amount = -Decimal(expire_entry.amount or 0)
    if amount <= 0 or amount != Decimal(bucket.expired_credits or 0):
        _fail("expire_amount_mismatch", wallet_bucket_bid)

    matching_orders = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.creator_bid == bucket.creator_bid,
        BillingOrder.created_at >= grant.updated_at - timedelta(seconds=2),
        BillingOrder.created_at <= grant.updated_at + timedelta(seconds=2),
    ).all()
    matched = False
    for order in matching_orders:
        order_metadata = _json_object(order.metadata_json)
        if order_metadata.get("cache_overcharge_bonus_plan") is True and str(
            order_metadata.get("applied_cycle_end_at") or ""
        ).startswith(grant.expires_at.isoformat()):
            matched = True
            break
    if not matched:
        _fail("cache_bonus_transition_not_found", wallet_bucket_bid)

    later_manual_grants = tuple(
        LaterManualGrant(
            ledger_bid=str(entry.ledger_bid or ""),
            amount=Decimal(entry.amount or 0),
            grant_source=str(
                _json_object(entry.metadata_json).get("grant_source") or ""
            ),
        )
        for entry in CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == bucket.creator_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_MANUAL,
            CreditLedgerEntry.created_at >= expire_entry.created_at,
        ).all()
    )

    return RecoveryCandidate(
        creator_bid=str(bucket.creator_bid or ""),
        source_wallet_bucket_bid=wallet_bucket_bid,
        amount=amount,
        intended_expires_at=intended_expires_at,
        source_expire_ledger_bid=str(expire_entry.ledger_bid or ""),
        later_manual_grants=later_manual_grants,
    )


def _request_id(campaign_id: str, candidate: RecoveryCandidate) -> str:
    return f"{campaign_id}:{candidate.source_wallet_bucket_bid}"


def _existing_recovery(request_id: str) -> CreditLedgerEntry | None:
    return CreditLedgerEntry.query.filter(
        CreditLedgerEntry.deleted == 0,
        CreditLedgerEntry.idempotency_key == f"operator_manual_grant:{request_id}",
    ).one_or_none()


def _recovery_provenance(
    campaign_id: str, candidate: RecoveryCandidate
) -> dict[str, object]:
    return {
        "recovery_campaign_id": campaign_id,
        "source_wallet_bucket_bid": candidate.source_wallet_bucket_bid,
        "source_expire_ledger_bid": candidate.source_expire_ledger_bid,
    }


def _validate_existing_recovery(
    existing: CreditLedgerEntry,
    *,
    campaign_id: str,
    candidate: RecoveryCandidate,
) -> None:
    metadata = _json_object(existing.metadata_json)
    expected_provenance = _recovery_provenance(campaign_id, candidate)
    if (
        existing.creator_bid != candidate.creator_bid
        or Decimal(existing.amount or 0) != candidate.amount
        or existing.expires_at != candidate.intended_expires_at
        or any(metadata.get(key) != value for key, value in expected_provenance.items())
    ):
        _fail("existing_recovery_mismatch", candidate.source_wallet_bucket_bid)


def _unexpected_compensation_bids(
    candidate: RecoveryCandidate,
    *,
    existing: CreditLedgerEntry | None,
) -> set[str]:
    expected_ledger_bid = str(existing.ledger_bid or "") if existing is not None else ""
    return {
        grant.ledger_bid
        for grant in candidate.later_manual_grants
        if grant.grant_source == MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION
        and grant.ledger_bid != expected_ledger_bid
    }


def _later_manual_grants_payload(
    candidate: RecoveryCandidate,
) -> list[dict[str, str]]:
    return [
        {
            "ledger_bid": grant.ledger_bid,
            "amount": format(grant.amount, "f"),
            "grant_source": grant.grant_source,
        }
        for grant in candidate.later_manual_grants
    ]


def main() -> int:
    """Validate targets, then optionally create exact-expiry recovery grants."""
    args = _build_parser().parse_args()
    bucket_bids = list(
        dict.fromkeys(str(value).strip() for value in args.wallet_bucket_bid)
    )
    if any(not value for value in bucket_bids):
        _fail("wallet_bucket_bid_required")
    app = create_app()
    results: list[dict[str, object]] = []
    with app.app_context():
        now = now_utc()
        candidates = [_load_candidate(value) for value in bucket_bids]
        existing_by_bucket: dict[str, CreditLedgerEntry | None] = {}
        blockers_by_bucket: dict[str, set[str]] = {}
        for candidate in candidates:
            request_id = _request_id(args.campaign_id, candidate)
            existing = _existing_recovery(request_id)
            if existing is not None:
                _validate_existing_recovery(
                    existing,
                    campaign_id=args.campaign_id,
                    candidate=candidate,
                )
            existing_by_bucket[candidate.source_wallet_bucket_bid] = existing
            blockers_by_bucket[candidate.source_wallet_bucket_bid] = (
                _unexpected_compensation_bids(candidate, existing=existing)
            )
        if args.apply:
            for candidate in candidates:
                if blockers_by_bucket[candidate.source_wallet_bucket_bid]:
                    _fail(
                        "possible_prior_compensation",
                        candidate.source_wallet_bucket_bid,
                    )
                if (
                    existing_by_bucket[candidate.source_wallet_bucket_bid] is None
                    and candidate.intended_expires_at <= now
                ):
                    _fail("not_recoverable_window", candidate.source_wallet_bucket_bid)

        for candidate in candidates:
            request_id = _request_id(args.campaign_id, candidate)
            existing = existing_by_bucket[candidate.source_wallet_bucket_bid]
            blockers = blockers_by_bucket[candidate.source_wallet_bucket_bid]
            if existing is not None:
                status = (
                    "existing_match" if not blockers else "blocked_prior_compensation"
                )
                ledger_bid = existing.ledger_bid
            elif blockers:
                status = "blocked_prior_compensation"
                ledger_bid = ""
            elif candidate.intended_expires_at <= now:
                _fail("not_recoverable_window", candidate.source_wallet_bucket_bid)
            elif not args.apply:
                status = "eligible"
                ledger_bid = ""
            else:
                grant = grant_manual_credits_with_expiry(
                    app,
                    user_bid=candidate.creator_bid,
                    operator_user_bid=args.operator_user_bid,
                    request_id=request_id,
                    amount=str(candidate.amount),
                    grant_source=MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
                    expires_at=candidate.intended_expires_at,
                    display_name="Manual credit validity restoration",
                    note="Restore credits after an incorrect expiry reset",
                    grant_channel=REPAIR_CHANNEL,
                    audit_metadata=_recovery_provenance(args.campaign_id, candidate),
                )
                ledger_bid = grant.ledger_bid
                status = grant.status
            results.append(
                {
                    "status": status,
                    "creator_bid": candidate.creator_bid,
                    "source_wallet_bucket_bid": candidate.source_wallet_bucket_bid,
                    "amount": format(candidate.amount, "f"),
                    "expires_at": to_utc_iso(candidate.intended_expires_at),
                    "recovery_ledger_bid": ledger_bid,
                    "later_manual_grants": _later_manual_grants_payload(candidate),
                }
            )
    dump_json(
        {
            "status": "applied" if args.apply else "dry_run",
            "dry_run": not args.apply,
            "candidate_count": len(results),
            "total_amount": format(
                sum((Decimal(item["amount"]) for item in results), Decimal(0)), "f"
            ),
            "results": results,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
