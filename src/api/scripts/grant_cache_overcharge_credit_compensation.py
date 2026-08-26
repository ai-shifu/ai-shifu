"""Grant LLM cache overcharge credit compensation from a reference sheet."""

from __future__ import annotations

import argparse
import os
from decimal import Decimal

from billing_cache_compensation_common import (
    DEFAULT_CAMPAIGN_ID,
    DEFAULT_INPUT_PATH,
    DEFAULT_OPERATOR_USER_BID,
    DEFAULT_SHEET_NAME,
    add_mismatch,
    dump_json,
    ensure_api_root_on_path,
    filter_rows_by_user_bid,
    load_reference_rows,
    row_to_payload,
)

ensure_api_root_on_path()
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")

from app import create_app  # noqa: E402
from flaskr.dao import db  # noqa: E402
from flaskr.service.billing.manual_credit_grants import (  # noqa: E402
    MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
    MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
    grant_manual_credits_to_user,
)
from flaskr.service.billing.models import CreditLedgerEntry  # noqa: E402
from flaskr.service.billing.queries import (  # noqa: E402
    load_primary_active_subscription,
)
from flaskr.service.user.repository import load_user_aggregate  # noqa: E402
from flaskr.util.datetime import now_utc, to_utc_iso  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply LLM cache overcharge credit compensation. "
            "Only users with an active subscription at runtime are eligible."
        ),
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH, help="xlsx/csv input")
    parser.add_argument("--sheet", default=DEFAULT_SHEET_NAME, help="xlsx sheet name")
    parser.add_argument(
        "--user-bid",
        action="append",
        default=[],
        help="Limit to one user bid. Can be passed multiple times.",
    )
    parser.add_argument(
        "--campaign-id",
        default=DEFAULT_CAMPAIGN_ID,
        help="Stable idempotency namespace for this compensation batch.",
    )
    parser.add_argument(
        "--operator-user-bid",
        default=DEFAULT_OPERATOR_USER_BID,
        help="Operator user bid written to audit metadata.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist grants. Defaults to dry-run.",
    )
    return parser


def main() -> int:
    """Run the compensation grant script."""
    args = _build_parser().parse_args()
    rows = filter_rows_by_user_bid(
        load_reference_rows(args.input, sheet_name=args.sheet),
        args.user_bid,
    )
    app = create_app()
    now = now_utc()

    results: list[dict[str, object]] = []
    with app.app_context():
        for row in rows:
            base = row_to_payload(row)
            aggregate = load_user_aggregate(row.user_bid)
            if aggregate is None:
                results.append(
                    {**base, "status": "skipped", "reason": "user_not_found"}
                )
                continue
            if row.amount <= Decimal(0):
                results.append(
                    {**base, "status": "skipped", "reason": "non_positive_amount"}
                )
                continue
            subscription = load_primary_active_subscription(row.user_bid, as_of=now)
            if subscription is None:
                results.append(
                    {
                        **base,
                        "status": "skipped",
                        "reason": "inactive_subscription",
                    }
                )
                continue

            request_id = f"{args.campaign_id}:credit:{row.user_bid}"
            existing_ledger = _load_existing_credit_grant(request_id)
            if existing_ledger is not None:
                mismatch = _compare_existing_credit_grant(
                    existing_ledger,
                    row=row,
                    request_id=request_id,
                )
                if mismatch:
                    results.append(
                        {
                            **base,
                            "status": "existing_mismatch",
                            "request_id": request_id,
                            "ledger_bid": existing_ledger.ledger_bid,
                            "mismatch": mismatch,
                        }
                    )
                    continue
                results.append(
                    {
                        **base,
                        "status": "existing_match",
                        "request_id": request_id,
                        "wallet_bucket_bid": existing_ledger.wallet_bucket_bid,
                        "ledger_bid": existing_ledger.ledger_bid,
                        "expires_at": existing_ledger.expires_at,
                    }
                )
                continue
            if not args.apply:
                results.append(
                    {
                        **base,
                        "status": "eligible",
                        "request_id": request_id,
                        "subscription_bid": subscription.subscription_bid,
                        "current_period_end_at": subscription.current_period_end_at,
                    }
                )
                continue

            grant_result = grant_manual_credits_to_user(
                app,
                user_bid=row.user_bid,
                operator_user_bid=args.operator_user_bid,
                request_id=request_id,
                amount=str(row.amount),
                grant_source=MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
                validity_preset=MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
                display_name="LLM cache overcharge compensation",
                note="LLM cache overcharge compensation",
                grant_channel="cache_overcharge_compensation_script",
            )
            _write_compensation_grant_metadata(
                ledger_bid=grant_result.ledger_bid,
                campaign_id=args.campaign_id,
                request_id=request_id,
                row=row,
                subscription=subscription,
            )
            results.append(
                {
                    **base,
                    "status": grant_result.status,
                    "request_id": request_id,
                    "wallet_bucket_bid": grant_result.wallet_bucket_bid,
                    "ledger_bid": grant_result.ledger_bid,
                    "expires_at": grant_result.expires_at,
                }
            )

    dump_json(
        {
            "status": "applied" if args.apply else "dry_run",
            "dry_run": not args.apply,
            "input": args.input,
            "sheet": args.sheet,
            "candidate_count": len(rows),
            "eligible_count": sum(
                1 for item in results if item["status"] == "eligible"
            ),
            "applied_count": sum(
                1 for item in results if item["status"] in {"granted", "noop_existing"}
            ),
            "existing_count": sum(
                1 for item in results if item["status"] == "existing_match"
            ),
            "mismatch_count": sum(
                1 for item in results if item["status"] == "existing_mismatch"
            ),
            "skipped_count": sum(1 for item in results if item["status"] == "skipped"),
            "results": results,
        }
    )
    if any(item["status"] == "existing_mismatch" for item in results):
        return 2
    return 0


def _load_existing_credit_grant(request_id: str) -> CreditLedgerEntry | None:
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.idempotency_key == f"operator_manual_grant:{request_id}",
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )


def _compare_existing_credit_grant(
    ledger: CreditLedgerEntry,
    *,
    row: object,
    request_id: str,
) -> dict[str, object]:
    mismatch: dict[str, object] = {}
    expected_key = f"operator_manual_grant:{request_id}"
    metadata = ledger.metadata_json if isinstance(ledger.metadata_json, dict) else {}

    add_mismatch(
        mismatch,
        "creator_bid",
        expected=row.user_bid,
        actual=ledger.creator_bid,
    )
    add_mismatch(
        mismatch,
        "amount",
        expected=row.amount,
        actual=ledger.amount,
    )
    add_mismatch(
        mismatch,
        "idempotency_key",
        expected=expected_key,
        actual=ledger.idempotency_key,
    )
    add_mismatch(
        mismatch,
        "grant_source",
        expected=MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
        actual=metadata.get("grant_source"),
    )
    add_mismatch(
        mismatch,
        "validity_preset",
        expected=MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
        actual=metadata.get("validity_preset"),
    )
    expected_expires_at = (
        metadata.get("compensation_period_end_at") or ledger.expires_at
    )
    add_mismatch(
        mismatch,
        "expires_at",
        expected=expected_expires_at,
        actual=ledger.expires_at,
    )
    return mismatch


def _write_compensation_grant_metadata(
    *,
    ledger_bid: str,
    campaign_id: str,
    request_id: str,
    row: object,
    subscription: object,
) -> None:
    if not ledger_bid:
        return
    ledger = CreditLedgerEntry.query.filter(
        CreditLedgerEntry.deleted == 0,
        CreditLedgerEntry.ledger_bid == ledger_bid,
    ).first()
    if ledger is None:
        return
    metadata = (
        dict(ledger.metadata_json) if isinstance(ledger.metadata_json, dict) else {}
    )
    metadata.update(
        {
            "compensation_campaign_id": campaign_id,
            "compensation_request_id": request_id,
            "compensation_input_amount": format(row.amount, "f"),
            "compensation_subscription_bid": str(
                getattr(subscription, "subscription_bid", "") or ""
            ).strip(),
            "compensation_period_end_at": to_utc_iso(
                subscription.current_period_end_at
            ),
        }
    )
    ledger.metadata_json = metadata
    db.session.add(ledger)
    db.session.commit()


if __name__ == "__main__":
    raise SystemExit(main())
