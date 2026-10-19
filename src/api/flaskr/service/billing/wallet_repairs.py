"""Offline repair helpers for creator wallet buckets and renewal state drift.

The repair entry points here are re-exported from ``wallets``. They reach the
shared wallet snapshot helpers through ``_wallet_core()`` so the import graph
stays acyclic and patches applied to ``wallets`` keep reaching these flows.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id

from .consts import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .primitives import credit_decimal_to_number as _credit_decimal_to_number
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .wallet_bucket_rules import (
    _is_credit_pack_runtime_bucket,
    _is_matching_expire_ledger_for_bucket,
    _load_credit_wallet_by_wallet_bid,
)
from .wallet_reserved_grants import (
    _collect_overdue_reserved_order_bids,
    _load_overdue_reserved_paid_order_creator_bids,
    _load_overdue_reserved_paid_order_records,
    _normalize_bid,
)
from .wallet_results import (
    ExpiredCreditPackBucketRestoreRecord,
    ExpiredCreditPackBucketRestoreResult,
    ExpireLedgerBucketDriftRecord,
    ExpireLedgerBucketDriftRepairResult,
    RenewalStateDriftRepairResult,
)

if TYPE_CHECKING:
    from datetime import datetime
    from types import ModuleType

    from flask import Flask

_ZERO = Decimal(0)


def _wallet_core() -> ModuleType:
    """Return the ``wallets`` module, resolved lazily to avoid an import cycle."""
    from . import wallets

    return wallets


def repair_renewal_state_drift(
    app: Flask,
    *,
    creator_bid: str = "",
    repair_before: datetime | None = None,
    limit: int | None = None,
    dry_run: bool = True,
) -> RenewalStateDriftRepairResult:
    """Repair creators whose subscription or bucket state stayed past cycle end."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_limit = int(limit) if limit is not None and int(limit) > 0 else None
    repaired_at = repair_before or now_utc()

    with app.app_context():
        stale_subscription_query = BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            BillingSubscription.current_period_end_at.isnot(None),
            BillingSubscription.current_period_end_at <= repaired_at,
        )
        stale_bucket_query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
            CreditWalletBucket.effective_to.isnot(None),
            CreditWalletBucket.effective_to <= repaired_at,
            CreditWalletBucket.available_credits > _ZERO,
        )
        if normalized_creator_bid:
            stale_subscription_query = stale_subscription_query.filter(
                BillingSubscription.creator_bid == normalized_creator_bid
            )
            stale_bucket_query = stale_bucket_query.filter(
                CreditWalletBucket.creator_bid == normalized_creator_bid
            )

        stale_subscriptions = stale_subscription_query.order_by(
            BillingSubscription.current_period_end_at.asc(),
            BillingSubscription.created_at.asc(),
            BillingSubscription.id.asc(),
        ).all()
        stale_buckets = stale_bucket_query.order_by(
            CreditWalletBucket.effective_to.asc(),
            CreditWalletBucket.created_at.asc(),
            CreditWalletBucket.id.asc(),
        ).all()
        creator_bids: list[str] = []
        seen_creator_bids: set[str] = set()
        for row in stale_subscriptions:
            candidate = str(row.creator_bid or "").strip()
            if candidate and candidate not in seen_creator_bids:
                seen_creator_bids.add(candidate)
                creator_bids.append(candidate)
        for row in stale_buckets:
            candidate = str(row.creator_bid or "").strip()
            if candidate and candidate not in seen_creator_bids:
                seen_creator_bids.add(candidate)
                creator_bids.append(candidate)
        remaining_limit = None
        if normalized_limit is not None:
            remaining_limit = max(normalized_limit - len(creator_bids), 0)
        overdue_reserved_creator_bids: list[str] = []
        if remaining_limit is None or remaining_limit > 0:
            overdue_reserved_creator_bids = (
                _load_overdue_reserved_paid_order_creator_bids(
                    repaired_at=repaired_at,
                    creator_bid=normalized_creator_bid,
                    limit=remaining_limit,
                )
            )
        for candidate in overdue_reserved_creator_bids:
            if candidate and candidate not in seen_creator_bids:
                seen_creator_bids.add(candidate)
                creator_bids.append(candidate)
        if normalized_limit is not None:
            creator_bids = creator_bids[:normalized_limit]

        if not creator_bids:
            return RenewalStateDriftRepairResult(
                status="noop",
                creator_bid=normalized_creator_bid or None,
                creator_count=0,
                stale_subscription_count=0,
                stale_bucket_count=0,
                updated_subscription_count=0,
                expired_bucket_count=0,
                expired_credits=0,
                dry_run=dry_run,
                overdue_reserved_grant_count=0,
                activatable_creator_count=0,
                activated_reserved_order_count=0,
                activated_creator_count=0,
                protected_creator_count=0,
                manual_review_creator_count=0,
                creator_bids=[],
                activatable_creator_bids=[],
                activated_creator_bids=[],
                protected_creator_bids=[],
                manual_review_creator_bids=[],
                overdue_reserved_grants=[],
            )

        scoped_creator_bids = set(creator_bids)
        overdue_reserved_grants = _load_overdue_reserved_paid_order_records(
            repaired_at=repaired_at,
            creator_bid=normalized_creator_bid,
            creator_bids=scoped_creator_bids,
        )
        scoped_stale_subscription_count = sum(
            1
            for row in stale_subscriptions
            if str(row.creator_bid or "").strip() in scoped_creator_bids
        )
        scoped_stale_bucket_count = sum(
            1
            for row in stale_buckets
            if str(row.creator_bid or "").strip() in scoped_creator_bids
        )
        scoped_overdue_reserved_grants = [
            record
            for record in overdue_reserved_grants
            if _normalize_bid(record.creator_bid) in scoped_creator_bids
        ]
        overdue_reserved_order_bids_by_creator: dict[str, list[str]] = {}
        for record in scoped_overdue_reserved_grants:
            overdue_reserved_order_bids_by_creator.setdefault(
                _normalize_bid(record.creator_bid), []
            ).append(record.bill_order_bid)

        expired_bucket_count = 0
        expired_credits = 0.0
        updated_subscription_count = 0
        activated_reserved_order_count = 0
        activatable_creator_bids: list[str] = []
        activated_creator_bids: list[str] = []
        protected_creator_bids: list[str] = []
        manual_review_creator_bids: list[str] = []
        candidate_orders_by_creator: dict[str, list[BillingOrder]] = {}

        from .reserved_renewal_activation import (
            IncompleteReservedGrantActivationError,
            validate_reserved_renewal_cycle_activation,
        )

        # Local import avoids a circular dependency with subscriptions.py.
        from .subscriptions import grant_paid_order_credits

        for target_creator_bid in creator_bids:
            candidate_order_bids = sorted(
                {
                    order_bid
                    for order_bid in overdue_reserved_order_bids_by_creator.get(
                        target_creator_bid, []
                    )
                    if _normalize_bid(order_bid)
                }
            )
            if not candidate_order_bids:
                continue
            candidate_orders = (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.creator_bid == target_creator_bid,
                    BillingOrder.bill_order_bid.in_(candidate_order_bids),
                    BillingOrder.status == BILLING_ORDER_STATUS_PAID,
                )
                .order_by(
                    BillingOrder.paid_at.asc(),
                    BillingOrder.created_at.asc(),
                    BillingOrder.id.asc(),
                )
                .all()
            )
            candidate_orders_by_creator[target_creator_bid] = candidate_orders
            try:
                for order in candidate_orders:
                    validate_reserved_renewal_cycle_activation(order)
            except IncompleteReservedGrantActivationError:
                manual_review_creator_bids.append(target_creator_bid)
                protected_creator_bids.append(target_creator_bid)
                continue
            if candidate_orders:
                activatable_creator_bids.append(target_creator_bid)

        if not dry_run:
            for target_creator_bid in creator_bids:
                candidate_orders = candidate_orders_by_creator.get(
                    target_creator_bid, []
                )
                if target_creator_bid in set(manual_review_creator_bids):
                    continue
                if candidate_orders:
                    reserved_order_bids_before = _collect_overdue_reserved_order_bids(
                        repaired_at=repaired_at,
                        creator_bid=target_creator_bid,
                    )
                    try:
                        with unit_of_work():
                            for order in candidate_orders:
                                grant_paid_order_credits(app, order)
                    except IncompleteReservedGrantActivationError:
                        protected_creator_bids.append(target_creator_bid)
                        manual_review_creator_bids.append(target_creator_bid)
                        continue
                    reserved_order_bids_after = _collect_overdue_reserved_order_bids(
                        repaired_at=repaired_at,
                        creator_bid=target_creator_bid,
                    )
                    activated_order_bids = (
                        reserved_order_bids_before - reserved_order_bids_after
                    )
                    if activated_order_bids:
                        activated_reserved_order_count += len(activated_order_bids)
                        activated_creator_bids.append(target_creator_bid)

                remaining_reserved_records = _load_overdue_reserved_paid_order_records(
                    repaired_at=repaired_at,
                    creator_bid=target_creator_bid,
                )
                if remaining_reserved_records:
                    protected_creator_bids.append(target_creator_bid)
                    continue

                expiration_payload = _wallet_core().expire_credit_wallet_buckets(
                    app,
                    creator_bid=target_creator_bid,
                    expire_before=repaired_at,
                )
                expired_bucket_count += int(expiration_payload.bucket_count or 0)
                expired_credits += float(expiration_payload.expired_credits or 0)

            protected_creator_bid_set = set(protected_creator_bids)
            changed_subscriptions = (
                BillingSubscription.query.filter(
                    BillingSubscription.deleted == 0,
                    BillingSubscription.creator_bid.in_(creator_bids),
                    BillingSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                    BillingSubscription.current_period_end_at.isnot(None),
                    BillingSubscription.current_period_end_at <= repaired_at,
                )
                .order_by(BillingSubscription.id.asc())
                .all()
            )
            if changed_subscriptions:
                with unit_of_work():
                    for subscription in changed_subscriptions:
                        if (
                            _normalize_bid(subscription.creator_bid)
                            in protected_creator_bid_set
                        ):
                            continue
                        subscription.status = BILLING_SUBSCRIPTION_STATUS_EXPIRED
                        subscription.updated_at = repaired_at
                        db.session.add(subscription)
                        updated_subscription_count += 1

        return RenewalStateDriftRepairResult(
            status="dry_run" if dry_run else "repaired",
            creator_bid=normalized_creator_bid or None,
            creator_count=len(creator_bids),
            stale_subscription_count=scoped_stale_subscription_count,
            stale_bucket_count=scoped_stale_bucket_count,
            updated_subscription_count=updated_subscription_count,
            expired_bucket_count=expired_bucket_count,
            expired_credits=expired_credits,
            dry_run=dry_run,
            overdue_reserved_grant_count=len(scoped_overdue_reserved_grants),
            activatable_creator_count=len(sorted(set(activatable_creator_bids))),
            activated_reserved_order_count=activated_reserved_order_count,
            activated_creator_count=len(sorted(set(activated_creator_bids))),
            protected_creator_count=len(sorted(set(protected_creator_bids))),
            manual_review_creator_count=len(sorted(set(manual_review_creator_bids))),
            creator_bids=creator_bids,
            activatable_creator_bids=sorted(set(activatable_creator_bids)),
            activated_creator_bids=sorted(set(activated_creator_bids)),
            protected_creator_bids=sorted(set(protected_creator_bids)),
            manual_review_creator_bids=sorted(set(manual_review_creator_bids)),
            overdue_reserved_grants=scoped_overdue_reserved_grants,
        )


def repair_credit_bucket_runtime_statuses(
    app: Flask,
    *,
    creator_bid: str = "",
    wallet_bucket_bid: str = "",
) -> dict[str, object]:
    """Repair buckets whose runtime status no longer matches their live balance."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_wallet_bucket_bid = str(wallet_bucket_bid or "").strip()
    repaired_at = now_utc()
    with app_context_scope(app), unit_of_work():
        query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_EXPIRED,
        )
        if normalized_creator_bid:
            query = query.filter(
                CreditWalletBucket.creator_bid == normalized_creator_bid
            )
        if normalized_wallet_bucket_bid:
            query = query.filter(
                CreditWalletBucket.wallet_bucket_bid == normalized_wallet_bucket_bid
            )
        rows = query.order_by(
            CreditWalletBucket.created_at.asc(),
            CreditWalletBucket.id.asc(),
        ).all()

        buckets = [
            row
            for row in rows
            if (
                _to_decimal(row.available_credits) > _ZERO
                or _to_decimal(row.reserved_credits) > _ZERO
            )
            and (row.effective_to is None or row.effective_to > repaired_at)
        ]
        if not buckets:
            return {
                "status": "noop",
                "creator_bid": normalized_creator_bid or None,
                "wallet_bucket_bid": normalized_wallet_bucket_bid or None,
                "repaired_bucket_count": 0,
                "repaired_bucket_bids": [],
            }

        wallets: dict[str, CreditWallet] = {}
        repaired_bucket_bids: list[str] = []
        for bucket in buckets:
            bucket.status = CREDIT_BUCKET_STATUS_EXHAUSTED
            _wallet_core().sync_credit_bucket_status(bucket)
            bucket.updated_at = repaired_at
            db.session.add(bucket)
            repaired_bucket_bids.append(bucket.wallet_bucket_bid)

            wallet = wallets.get(bucket.wallet_bid)
            if wallet is None:
                wallet = _load_credit_wallet_by_wallet_bid(bucket.wallet_bid)
                if wallet is not None:
                    wallets[bucket.wallet_bid] = wallet

        for wallet in wallets.values():
            _wallet_core().refresh_credit_wallet_snapshot(wallet)
            _wallet_core().persist_credit_wallet_snapshot(
                wallet,
                available_credits=wallet.available_credits,
                reserved_credits=wallet.reserved_credits,
                updated_at=repaired_at,
            )

        return {
            "status": "repaired",
            "creator_bid": normalized_creator_bid or None,
            "wallet_bucket_bid": normalized_wallet_bucket_bid or None,
            "repaired_bucket_count": len(repaired_bucket_bids),
            "repaired_bucket_bids": repaired_bucket_bids,
        }


def repair_expire_ledger_bucket_drift(
    app: Flask,
    *,
    creator_bid: str = "",
    wallet_bucket_bid: str = "",
    repair_before: datetime | None = None,
    limit: int | None = None,
    dry_run: bool = True,
) -> ExpireLedgerBucketDriftRepairResult:
    """Close buckets whose expire ledger exists but bucket state stayed live.

    This intentionally does not write another expire ledger. The target shape is
    an active, already-ended bucket with remaining available credits and an
    existing expire ledger for the same bucket cycle. Writing a second ledger
    would duplicate audit entries, so the repair only synchronizes the bucket
    projection and wallet snapshot.
    """
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_wallet_bucket_bid = str(wallet_bucket_bid or "").strip()
    normalized_limit = int(limit) if limit is not None and int(limit) > 0 else None
    repaired_at = repair_before or now_utc()

    with app.app_context():
        query = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
            CreditWalletBucket.effective_to.isnot(None),
            CreditWalletBucket.effective_to <= repaired_at,
            CreditWalletBucket.available_credits > _ZERO,
        )
        if normalized_creator_bid:
            query = query.filter(
                CreditWalletBucket.creator_bid == normalized_creator_bid
            )
        if normalized_wallet_bucket_bid:
            query = query.filter(
                CreditWalletBucket.wallet_bucket_bid == normalized_wallet_bucket_bid
            )

        candidate_buckets = query.order_by(
            CreditWalletBucket.effective_to.asc(),
            CreditWalletBucket.created_at.asc(),
            CreditWalletBucket.id.asc(),
        )
        if normalized_limit is not None:
            candidate_buckets = candidate_buckets.limit(normalized_limit)
        candidate_buckets = candidate_buckets.all()
        records: list[ExpireLedgerBucketDriftRecord] = []
        changed_wallets: dict[str, CreditWallet] = {}
        expire_ledgers_by_bucket: dict[str, list[CreditLedgerEntry]] = {}

        if candidate_buckets:
            bucket_bids = [bucket.wallet_bucket_bid for bucket in candidate_buckets]
            ledger_rows = CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                CreditLedgerEntry.wallet_bucket_bid.in_(bucket_bids),
            ).all()
            for ledger in ledger_rows:
                expire_ledgers_by_bucket.setdefault(
                    ledger.wallet_bucket_bid, []
                ).append(ledger)

        for bucket in candidate_buckets:
            if _is_credit_pack_runtime_bucket(bucket):
                continue
            bucket_ledgers = sorted(
                (
                    ledger
                    for ledger in expire_ledgers_by_bucket.get(
                        bucket.wallet_bucket_bid, []
                    )
                    if ledger.creator_bid == bucket.creator_bid
                ),
                key=lambda ledger: int(ledger.id or 0),
            )
            if not bucket_ledgers:
                continue
            expire_ledgers = [
                ledger
                for ledger in bucket_ledgers
                if _is_matching_expire_ledger_for_bucket(ledger, bucket)
            ]

            previous_available = _quantize_credit_amount(bucket.available_credits)
            previous_expired = _quantize_credit_amount(bucket.expired_credits)
            previous_status = int(bucket.status or 0)
            expire_ledger_amount = _quantize_credit_amount(
                sum(
                    (_to_decimal(ledger.amount) for ledger in bucket_ledgers),
                    start=_ZERO,
                )
            )
            ledger_expired_amount = _quantize_credit_amount(
                sum(
                    (abs(_to_decimal(ledger.amount)) for ledger in bucket_ledgers),
                    start=_ZERO,
                )
            )
            next_available = _ZERO
            next_expired = max(
                previous_expired,
                ledger_expired_amount
                if ledger_expired_amount > _ZERO
                else _quantize_credit_amount(previous_expired + previous_available),
            )
            next_status = (
                CREDIT_BUCKET_STATUS_EXHAUSTED
                if _to_decimal(bucket.reserved_credits) > _ZERO
                else CREDIT_BUCKET_STATUS_EXPIRED
            )
            has_cycle_match = bool(expire_ledgers)
            has_amount_evidence = ledger_expired_amount == previous_available
            has_expiry_evidence = all(
                ledger.expires_at == bucket.effective_to for ledger in expire_ledgers
            )
            can_repair = has_cycle_match and has_amount_evidence and has_expiry_evidence
            repair_action = "repair" if can_repair else "manual_review"
            if not has_cycle_match:
                repair_reason = "expire_ledger_expiry_mismatch"
            elif not has_amount_evidence:
                repair_reason = "expire_ledger_amount_mismatch"
            elif not has_expiry_evidence:
                repair_reason = "expire_ledger_expiry_mismatch"
            else:
                repair_reason = "expire_ledger_matches_bucket_balance_and_expiry"
            changed = can_repair and (
                previous_available != next_available
                or previous_expired != next_expired
                or previous_status != next_status
            )
            records.append(
                ExpireLedgerBucketDriftRecord(
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    wallet_bid=bucket.wallet_bid,
                    creator_bid=bucket.creator_bid,
                    previous_available_credits=_credit_decimal_to_number(
                        previous_available
                    ),
                    available_credits=_credit_decimal_to_number(next_available),
                    previous_expired_credits=_credit_decimal_to_number(
                        previous_expired
                    ),
                    expired_credits=_credit_decimal_to_number(next_expired),
                    previous_status=previous_status,
                    status=next_status,
                    expire_ledger_count=len(bucket_ledgers),
                    expire_ledger_amount=_credit_decimal_to_number(
                        expire_ledger_amount
                    ),
                    repair_action=repair_action,
                    repair_reason=repair_reason,
                    changed=changed,
                )
            )

            if dry_run or not changed:
                continue

            bucket.available_credits = next_available
            bucket.expired_credits = next_expired
            bucket.status = next_status
            bucket.updated_at = repaired_at
            db.session.add(bucket)

            wallet = changed_wallets.get(bucket.wallet_bid)
            if wallet is None:
                wallet = _load_credit_wallet_by_wallet_bid(bucket.wallet_bid)
                if wallet is not None:
                    changed_wallets[bucket.wallet_bid] = wallet

        if not dry_run:
            with unit_of_work():
                db.session.flush()
                for wallet in changed_wallets.values():
                    _wallet_core().refresh_credit_wallet_snapshot(
                        wallet, snapshot_at=repaired_at
                    )
                    _wallet_core().persist_credit_wallet_snapshot(
                        wallet,
                        available_credits=wallet.available_credits,
                        reserved_credits=wallet.reserved_credits,
                        updated_at=repaired_at,
                    )

        repaired_bucket_count = sum(1 for record in records if record.changed)
        manual_review_count = sum(
            1 for record in records if record.repair_action == "manual_review"
        )
        return ExpireLedgerBucketDriftRepairResult(
            status=(
                "dry_run"
                if dry_run
                else "repaired"
                if repaired_bucket_count
                else "manual_review"
                if manual_review_count
                else "noop"
            ),
            creator_bid=normalized_creator_bid or None,
            wallet_bucket_bid=normalized_wallet_bucket_bid or None,
            bucket_count=len(records),
            repaired_bucket_count=repaired_bucket_count,
            manual_review_count=manual_review_count,
            dry_run=dry_run,
            buckets=records,
        )


def restore_wrongly_expired_credit_pack_buckets(
    app: Flask,
    *,
    bill_order_bids: list[str] | tuple[str, ...],
    dry_run: bool = True,
) -> ExpiredCreditPackBucketRestoreResult:
    """Restore explicitly scoped credit pack buckets expired before this fix."""
    normalized_order_bids = list(
        dict.fromkeys(_normalize_bid(bid) for bid in bill_order_bids)
    )
    normalized_order_bids = [bid for bid in normalized_order_bids if bid]
    if not normalized_order_bids:
        return ExpiredCreditPackBucketRestoreResult(
            status="noop",
            bill_order_bids=[],
            order_count=0,
            repaired_bucket_count=0,
            manual_review_count=0,
            noop_count=0,
            dry_run=dry_run,
        )

    repaired_at = now_utc()
    with app.app_context():
        if dry_run:
            records = _build_expired_credit_pack_restore_records(
                app,
                bill_order_bids=normalized_order_bids,
                repaired_at=repaired_at,
                dry_run=True,
            )
        else:
            with unit_of_work():
                records = _build_expired_credit_pack_restore_records(
                    app,
                    bill_order_bids=normalized_order_bids,
                    repaired_at=repaired_at,
                    dry_run=False,
                )

        repaired_count = sum(1 for record in records if record.changed)
        manual_review_count = sum(
            1 for record in records if record.repair_action == "manual_review"
        )
        noop_count = sum(1 for record in records if record.repair_action == "noop")
        return ExpiredCreditPackBucketRestoreResult(
            status=(
                "dry_run"
                if dry_run
                else "partial_repaired"
                if repaired_count and manual_review_count
                else "repaired"
                if repaired_count
                else "manual_review"
                if manual_review_count
                else "noop"
            ),
            bill_order_bids=normalized_order_bids,
            order_count=len(normalized_order_bids),
            repaired_bucket_count=repaired_count,
            manual_review_count=manual_review_count,
            noop_count=noop_count,
            dry_run=dry_run,
            buckets=records,
        )


def _build_expired_credit_pack_restore_records(
    app: Flask,
    *,
    bill_order_bids: list[str],
    repaired_at: datetime,
    dry_run: bool,
) -> list[ExpiredCreditPackBucketRestoreRecord]:
    records: list[ExpiredCreditPackBucketRestoreRecord] = []
    orders = {
        order.bill_order_bid: order
        for order in BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.bill_order_bid.in_(bill_order_bids),
        ).all()
    }

    for bill_order_bid in bill_order_bids:
        order = orders.get(bill_order_bid)
        if order is None:
            records.append(
                _build_expired_credit_pack_restore_record(
                    bill_order_bid=bill_order_bid,
                    repair_action="manual_review",
                    repair_reason="billing_order_not_found",
                )
            )
            continue
        if (
            int(order.order_type or 0) != BILLING_ORDER_TYPE_TOPUP
            or int(order.status or 0) != BILLING_ORDER_STATUS_PAID
            or order.paid_at is None
        ):
            records.append(
                _build_expired_credit_pack_restore_record(
                    bill_order_bid=bill_order_bid,
                    creator_bid=order.creator_bid,
                    repair_action="manual_review",
                    repair_reason="billing_order_is_not_paid_topup",
                )
            )
            continue

        buckets = CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid == order.creator_bid,
            CreditWalletBucket.source_bid == bill_order_bid,
        ).all()
        runtime_buckets = [
            bucket for bucket in buckets if _is_credit_pack_runtime_bucket(bucket)
        ]
        if len(runtime_buckets) != 1:
            records.append(
                _build_expired_credit_pack_restore_record(
                    bill_order_bid=bill_order_bid,
                    creator_bid=order.creator_bid,
                    repair_action="manual_review",
                    repair_reason=(
                        "credit_pack_bucket_not_found"
                        if not runtime_buckets
                        else "multiple_credit_pack_buckets_found"
                    ),
                )
            )
            continue

        bucket = runtime_buckets[0]
        existing_repair = _load_existing_expired_credit_pack_restore_ledger(
            creator_bid=bucket.creator_bid,
            bill_order_bid=bill_order_bid,
        )
        if existing_repair is not None:
            records.append(
                _build_expired_credit_pack_restore_record(
                    bill_order_bid=bill_order_bid,
                    creator_bid=bucket.creator_bid,
                    wallet_bid=bucket.wallet_bid,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    previous_available_credits=bucket.available_credits,
                    available_credits=bucket.available_credits,
                    previous_expired_credits=bucket.expired_credits,
                    expired_credits=bucket.expired_credits,
                    previous_status=bucket.status,
                    status=bucket.status,
                    restored_credits=existing_repair.amount,
                    repair_action="noop",
                    repair_reason="already_repaired",
                    ledger_bid=existing_repair.ledger_bid,
                )
            )
            continue

        previous_available = _quantize_credit_amount(bucket.available_credits)
        previous_expired = _quantize_credit_amount(bucket.expired_credits)
        previous_status = int(bucket.status or 0)
        restore_amount = previous_expired
        next_available = _quantize_credit_amount(previous_available + restore_amount)
        next_expired = _ZERO
        can_repair, repair_reason, expire_ledgers = (
            _validate_expired_credit_pack_restore_candidate(
                bucket,
                restore_amount=restore_amount,
            )
        )
        record = _build_expired_credit_pack_restore_record(
            bill_order_bid=bill_order_bid,
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            previous_available_credits=previous_available,
            available_credits=next_available if can_repair else previous_available,
            previous_expired_credits=previous_expired,
            expired_credits=next_expired if can_repair else previous_expired,
            previous_status=previous_status,
            status=CREDIT_BUCKET_STATUS_ACTIVE if can_repair else previous_status,
            restored_credits=restore_amount if can_repair else _ZERO,
            repair_action="repair" if can_repair else "manual_review",
            repair_reason=repair_reason,
            changed=can_repair,
        )
        records.append(record)

        if dry_run or not can_repair:
            continue

        bucket.available_credits = next_available
        bucket.expired_credits = next_expired
        bucket.status = CREDIT_BUCKET_STATUS_ACTIVE
        bucket.updated_at = repaired_at
        db.session.add(bucket)
        db.session.flush()

        wallet = _load_credit_wallet_by_wallet_bid(bucket.wallet_bid)
        if wallet is None:
            message = "credit_pack_restore_wallet_missing"
            raise RuntimeError(message)
        available_credits, reserved_credits = (
            _wallet_core().calculate_credit_wallet_snapshot_values(
                wallet,
                snapshot_at=repaired_at,
            )
        )
        ledger = CreditLedgerEntry(
            ledger_bid=generate_id(app),
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=bill_order_bid,
            idempotency_key=_build_expired_credit_pack_restore_idempotency_key(
                bill_order_bid
            ),
            amount=restore_amount,
            balance_after=available_credits,
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={
                "repair_reason": "restore_wrongly_expired_credit_pack_bucket",
                "bill_order_bid": bill_order_bid,
                "wallet_bucket_bid": bucket.wallet_bucket_bid,
                "restored_expired_credits": _credit_decimal_to_number(restore_amount),
                "previous_status": previous_status,
                "previous_available_credits": _credit_decimal_to_number(
                    previous_available
                ),
                "previous_expired_credits": _credit_decimal_to_number(previous_expired),
                "expire_ledger_bids": [ledger.ledger_bid for ledger in expire_ledgers],
                "repaired_at": to_utc_iso(repaired_at),
            },
        )
        if (
            _quantize_credit_amount(wallet.available_credits) != available_credits
            or _quantize_credit_amount(wallet.reserved_credits) != reserved_credits
        ):
            _wallet_core().persist_credit_wallet_snapshot(
                wallet,
                available_credits=available_credits,
                reserved_credits=reserved_credits,
                updated_at=repaired_at,
            )
        db.session.add(ledger)
        records[-1] = _build_expired_credit_pack_restore_record(
            bill_order_bid=bill_order_bid,
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            previous_available_credits=previous_available,
            available_credits=next_available,
            previous_expired_credits=previous_expired,
            expired_credits=next_expired,
            previous_status=previous_status,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            restored_credits=restore_amount,
            repair_action="repair",
            repair_reason=repair_reason,
            changed=True,
            ledger_bid=ledger.ledger_bid,
        )

    return records


def _build_expired_credit_pack_restore_record(
    *,
    bill_order_bid: str,
    creator_bid: str | None = None,
    wallet_bid: str | None = None,
    wallet_bucket_bid: str | None = None,
    previous_available_credits: Decimal | object = _ZERO,
    available_credits: Decimal | object = _ZERO,
    previous_expired_credits: Decimal | object = _ZERO,
    expired_credits: Decimal | object = _ZERO,
    previous_status: int | None = None,
    status: int | None = None,
    restored_credits: Decimal | object = _ZERO,
    repair_action: str,
    repair_reason: str,
    changed: bool = False,
    ledger_bid: str | None = None,
) -> ExpiredCreditPackBucketRestoreRecord:
    return ExpiredCreditPackBucketRestoreRecord(
        bill_order_bid=bill_order_bid,
        creator_bid=creator_bid,
        wallet_bid=wallet_bid,
        wallet_bucket_bid=wallet_bucket_bid,
        previous_available_credits=_credit_decimal_to_number(
            _quantize_credit_amount(previous_available_credits)
        ),
        available_credits=_credit_decimal_to_number(
            _quantize_credit_amount(available_credits)
        ),
        previous_expired_credits=_credit_decimal_to_number(
            _quantize_credit_amount(previous_expired_credits)
        ),
        expired_credits=_credit_decimal_to_number(
            _quantize_credit_amount(expired_credits)
        ),
        previous_status=previous_status,
        status=status,
        restored_credits=_credit_decimal_to_number(
            _quantize_credit_amount(restored_credits)
        ),
        repair_action=repair_action,
        repair_reason=repair_reason,
        changed=changed,
        ledger_bid=ledger_bid,
    )


def _validate_expired_credit_pack_restore_candidate(
    bucket: CreditWalletBucket,
    *,
    restore_amount: Decimal,
) -> tuple[bool, str, list[CreditLedgerEntry]]:
    if int(bucket.status or 0) != CREDIT_BUCKET_STATUS_EXPIRED:
        return False, "bucket_is_not_expired", []
    if restore_amount <= _ZERO:
        return False, "bucket_has_no_expired_credits", []
    if _to_decimal(bucket.reserved_credits) != _ZERO:
        return False, "bucket_has_reserved_credits", []
    if _to_decimal(bucket.available_credits) != _ZERO:
        return False, "bucket_has_available_credits", []

    expected_remaining = _quantize_credit_amount(
        _to_decimal(bucket.original_credits)
        - _to_decimal(bucket.consumed_credits)
        - _to_decimal(bucket.reserved_credits)
        - _to_decimal(bucket.available_credits)
    )
    if expected_remaining != restore_amount:
        return False, "bucket_balance_shape_mismatch", []

    expire_ledgers = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == bucket.creator_bid,
            CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        )
        .order_by(CreditLedgerEntry.id.asc())
        .all()
    )
    matching_ledgers = [
        ledger
        for ledger in expire_ledgers
        if _is_matching_expire_ledger_for_bucket(ledger, bucket)
    ]
    if not matching_ledgers:
        return False, "matching_expire_ledger_not_found", expire_ledgers
    expired_amount = _quantize_credit_amount(
        sum((abs(_to_decimal(ledger.amount)) for ledger in matching_ledgers), _ZERO)
    )
    if expired_amount != restore_amount:
        return False, "expire_ledger_amount_mismatch", matching_ledgers
    return True, "expired_credit_pack_bucket_matches_expire_ledger", matching_ledgers


def _load_existing_expired_credit_pack_restore_ledger(
    *,
    creator_bid: str,
    bill_order_bid: str,
) -> CreditLedgerEntry | None:
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == creator_bid,
            CreditLedgerEntry.idempotency_key
            == _build_expired_credit_pack_restore_idempotency_key(bill_order_bid),
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )


def _build_expired_credit_pack_restore_idempotency_key(bill_order_bid: str) -> str:
    return f"restore_expired_topup:{_normalize_bid(bill_order_bid)}"
