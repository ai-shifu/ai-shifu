"""Read-only diagnostics for billing credit invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from .bucket_categories import load_billing_order_type_by_bid
from .bucket_categories import resolve_wallet_bucket_runtime_category
from .bucket_categories import wallet_bucket_requires_active_subscription
from .consts import (
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
)
from .models import (
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .primitives import (
    coerce_datetime,
    normalize_json_object,
    quantize_credit_amount,
    to_decimal,
)
from .queries import load_primary_active_subscription
from .wallets import calculate_credit_wallet_snapshot_values
from flaskr.util.datetime import now_utc, to_utc_iso

_ZERO = Decimal("0")


@dataclass(slots=True, frozen=True)
class CreditAuditIssue:
    code: str
    severity: str
    creator_bid: str
    wallet_bid: str = ""
    wallet_bucket_bid: str = ""
    ledger_bid: str = ""
    subscription_bid: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "creator_bid": self.creator_bid,
        }
        if self.wallet_bid:
            payload["wallet_bid"] = self.wallet_bid
        if self.wallet_bucket_bid:
            payload["wallet_bucket_bid"] = self.wallet_bucket_bid
        if self.ledger_bid:
            payload["ledger_bid"] = self.ledger_bid
        if self.subscription_bid:
            payload["subscription_bid"] = self.subscription_bid
        if self.message:
            payload["message"] = self.message
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(slots=True, frozen=True)
class CreditAuditReport:
    status: str
    creator_bid: str | None
    as_of: datetime
    checked_wallet_count: int
    checked_bucket_count: int
    checked_ledger_count: int
    issue_count: int
    returned_issue_count: int
    total_issue_count: int
    truncated: bool
    issues: list[CreditAuditIssue]

    def to_payload(self) -> dict[str, Any]:
        counts_by_code: dict[str, int] = {}
        for issue in self.issues:
            counts_by_code[issue.code] = counts_by_code.get(issue.code, 0) + 1
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "as_of": to_utc_iso(self.as_of),
            "checked_wallet_count": self.checked_wallet_count,
            "checked_bucket_count": self.checked_bucket_count,
            "checked_ledger_count": self.checked_ledger_count,
            "issue_count": self.issue_count,
            "returned_issue_count": self.returned_issue_count,
            "total_issue_count": self.total_issue_count,
            "truncated": self.truncated,
            "counts_by_code": counts_by_code,
            "issues": [issue.to_payload() for issue in self.issues],
        }


def audit_credit_state(
    *,
    creator_bid: str = "",
    as_of: datetime | str | None = None,
    limit: int | None = None,
) -> CreditAuditReport:
    """Audit credit wallet, bucket, ledger, and subscription invariants.

    The audit is intentionally read-only. It reports drift candidates for
    operators or follow-up repair tools, but never mutates billing state.
    """

    normalized_creator_bid = str(creator_bid or "").strip()
    if as_of is None:
        audit_at = now_utc()
    else:
        audit_at = coerce_datetime(as_of)
        if audit_at is None:
            raise ValueError(f"Unable to parse as_of value: {as_of!r}")
    resolved_limit = int(limit or 0)
    issues: list[CreditAuditIssue] = []

    wallets = _load_wallets(normalized_creator_bid, limit=resolved_limit)
    buckets = _load_buckets(
        creator_bid=normalized_creator_bid,
        limit=resolved_limit,
    )
    ledgers = _load_ledgers(
        creator_bid=normalized_creator_bid,
        limit=resolved_limit,
    )
    expire_ledgers = _load_expire_ledgers_for_buckets(
        bucket_bids={bucket.wallet_bucket_bid for bucket in buckets}
    )
    checked_ledger_bids = {ledger.ledger_bid for ledger in [*ledgers, *expire_ledgers]}

    expire_ledgers_by_bucket: dict[str, list[CreditLedgerEntry]] = {}
    for ledger in expire_ledgers:
        expire_ledgers_by_bucket.setdefault(ledger.wallet_bucket_bid, []).append(ledger)

    for wallet in wallets:
        issues.extend(_audit_wallet_snapshot(wallet, as_of=audit_at))

    for bucket in buckets:
        issues.extend(_audit_bucket_balance(bucket))
        issues.extend(
            _audit_expired_bucket_projection(
                bucket,
                expire_ledgers=expire_ledgers_by_bucket.get(
                    bucket.wallet_bucket_bid, []
                ),
            )
        )

    for ledger in ledgers:
        if int(ledger.entry_type or 0) == CREDIT_LEDGER_ENTRY_TYPE_GRANT:
            issues.extend(_audit_overdue_reserved_grant(ledger, as_of=audit_at))

    issues.extend(
        _audit_subscription_bucket_windows(
            normalized_creator_bid,
            buckets=buckets,
            as_of=audit_at,
            limit=resolved_limit,
        )
    )
    issues = _dedupe_issues(issues)
    total_issue_count = len(issues)
    truncated = resolved_limit > 0 and total_issue_count > resolved_limit
    if resolved_limit > 0:
        issues = issues[:resolved_limit]
    returned_issue_count = len(issues)

    return CreditAuditReport(
        status="ok" if total_issue_count == 0 else "issues_found",
        creator_bid=normalized_creator_bid or None,
        as_of=audit_at,
        checked_wallet_count=len(wallets),
        checked_bucket_count=len(buckets),
        checked_ledger_count=len(checked_ledger_bids),
        issue_count=total_issue_count,
        returned_issue_count=returned_issue_count,
        total_issue_count=total_issue_count,
        truncated=truncated,
        issues=issues,
    )


def _load_wallets(creator_bid: str, *, limit: int) -> list[CreditWallet]:
    query = CreditWallet.query.filter(CreditWallet.deleted == 0)
    if creator_bid:
        query = query.filter(CreditWallet.creator_bid == creator_bid)
    query = query.order_by(CreditWallet.id.asc())
    if limit > 0:
        query = query.limit(limit)
    return query.all()


def _load_buckets(
    *,
    creator_bid: str,
    limit: int,
) -> list[CreditWalletBucket]:
    query = CreditWalletBucket.query.filter(CreditWalletBucket.deleted == 0)
    if creator_bid:
        query = query.filter(CreditWalletBucket.creator_bid == creator_bid)
    query = query.order_by(CreditWalletBucket.id.asc())
    if limit > 0:
        query = query.limit(limit)
    return query.all()


def _load_ledgers(
    *,
    creator_bid: str,
    limit: int,
) -> list[CreditLedgerEntry]:
    query = CreditLedgerEntry.query.filter(CreditLedgerEntry.deleted == 0)
    if creator_bid:
        query = query.filter(CreditLedgerEntry.creator_bid == creator_bid)
    query = query.order_by(CreditLedgerEntry.id.asc())
    if limit > 0:
        query = query.limit(limit)
    return query.all()


def _load_expire_ledgers_for_buckets(
    *,
    bucket_bids: set[str],
) -> list[CreditLedgerEntry]:
    normalized_bucket_bids = {str(bid or "").strip() for bid in bucket_bids}
    normalized_bucket_bids.discard("")
    if not normalized_bucket_bids:
        return []
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            CreditLedgerEntry.wallet_bucket_bid.in_(normalized_bucket_bids),
        )
        .order_by(CreditLedgerEntry.id.asc())
        .all()
    )


def _audit_wallet_snapshot(
    wallet: CreditWallet,
    *,
    as_of: datetime,
) -> list[CreditAuditIssue]:
    expected_available, expected_reserved = calculate_credit_wallet_snapshot_values(
        wallet,
        snapshot_at=as_of,
    )
    actual_available = quantize_credit_amount(to_decimal(wallet.available_credits))
    actual_reserved = quantize_credit_amount(to_decimal(wallet.reserved_credits))
    if actual_available == expected_available and actual_reserved == expected_reserved:
        return []
    return [
        CreditAuditIssue(
            code="wallet_snapshot_mismatch",
            severity="error",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            message="Wallet snapshot does not match current bucket projection.",
            details={
                "actual_available_credits": str(actual_available),
                "expected_available_credits": str(expected_available),
                "actual_reserved_credits": str(actual_reserved),
                "expected_reserved_credits": str(expected_reserved),
            },
        )
    ]


def _audit_bucket_balance(bucket: CreditWalletBucket) -> list[CreditAuditIssue]:
    original = quantize_credit_amount(to_decimal(bucket.original_credits))
    projected = quantize_credit_amount(
        to_decimal(bucket.available_credits)
        + to_decimal(bucket.reserved_credits)
        + to_decimal(bucket.consumed_credits)
        + to_decimal(bucket.expired_credits)
    )
    if original == projected:
        return []
    return [
        CreditAuditIssue(
            code="bucket_balance_mismatch",
            severity="error",
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            message="Bucket credit amounts do not add up to original credits.",
            details={
                "original_credits": str(original),
                "projected_credits": str(projected),
                "available_credits": str(
                    quantize_credit_amount(to_decimal(bucket.available_credits))
                ),
                "reserved_credits": str(
                    quantize_credit_amount(to_decimal(bucket.reserved_credits))
                ),
                "consumed_credits": str(
                    quantize_credit_amount(to_decimal(bucket.consumed_credits))
                ),
                "expired_credits": str(
                    quantize_credit_amount(to_decimal(bucket.expired_credits))
                ),
            },
        )
    ]


def _audit_expired_bucket_projection(
    bucket: CreditWalletBucket,
    *,
    expire_ledgers: list[CreditLedgerEntry],
) -> list[CreditAuditIssue]:
    if int(bucket.status or 0) != CREDIT_BUCKET_STATUS_EXPIRED:
        return []
    expired = quantize_credit_amount(to_decimal(bucket.expired_credits))
    if expired <= _ZERO:
        return []
    ledger_expired = quantize_credit_amount(
        sum((abs(to_decimal(ledger.amount)) for ledger in expire_ledgers), _ZERO)
    )
    if ledger_expired == expired:
        return []
    return [
        CreditAuditIssue(
            code="expire_ledger_bucket_mismatch",
            severity="error",
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            message="Expired bucket projection does not match expire ledger amount/window.",
            details={
                "bucket_expired_credits": str(expired),
                "expire_ledger_credits": str(ledger_expired),
                "expire_ledger_count": len(expire_ledgers),
                "bucket_effective_to": to_utc_iso(bucket.effective_to),
            },
        )
    ]


def _audit_overdue_reserved_grant(
    ledger: CreditLedgerEntry,
    *,
    as_of: datetime,
) -> list[CreditAuditIssue]:
    metadata = normalize_json_object(ledger.metadata_json)
    state = str(metadata.get("bucket_credit_state") or "").strip().lower()
    if state != "reserved":
        return []
    consumable_from = coerce_datetime(ledger.consumable_from)
    if consumable_from is None or consumable_from > as_of:
        return []
    return [
        CreditAuditIssue(
            code="overdue_reserved_grant",
            severity="error",
            creator_bid=ledger.creator_bid,
            wallet_bid=ledger.wallet_bid,
            wallet_bucket_bid=ledger.wallet_bucket_bid,
            ledger_bid=ledger.ledger_bid,
            message="Reserved grant is past consumable_from and still not activated.",
            details={
                "amount": str(quantize_credit_amount(to_decimal(ledger.amount))),
                "consumable_from": to_utc_iso(consumable_from),
                "expires_at": to_utc_iso(ledger.expires_at),
            },
        )
    ]


def _audit_subscription_bucket_windows(
    creator_bid: str,
    *,
    buckets: list[CreditWalletBucket],
    as_of: datetime,
    limit: int,
) -> list[CreditAuditIssue]:
    issues: list[CreditAuditIssue] = []
    primary_by_creator: dict[str, BillingSubscription | None] = {}
    checked = 0
    for bucket in buckets:
        if limit > 0 and checked >= limit:
            break
        if creator_bid and bucket.creator_bid != creator_bid:
            continue
        if int(bucket.status or 0) != CREDIT_BUCKET_STATUS_ACTIVE:
            continue
        if (
            resolve_wallet_bucket_runtime_category(
                bucket,
                load_order_type=load_billing_order_type_by_bid,
            )
            != CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            or not wallet_bucket_requires_active_subscription(
                bucket,
                load_order_type=load_billing_order_type_by_bid,
            )
        ):
            continue
        checked += 1
        if bucket.creator_bid not in primary_by_creator:
            primary_by_creator[bucket.creator_bid] = load_primary_active_subscription(
                bucket.creator_bid,
                as_of=as_of,
            )
        subscription = primary_by_creator[bucket.creator_bid]
        if (
            subscription is None
            or bucket.effective_to == subscription.current_period_end_at
        ):
            continue
        issues.append(
            CreditAuditIssue(
                code="subscription_bucket_window_mismatch",
                severity="warning",
                creator_bid=bucket.creator_bid,
                wallet_bid=bucket.wallet_bid,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                subscription_bid=subscription.subscription_bid,
                message="Active plan credit bucket window differs from primary subscription period end.",
                details={
                    "bucket_effective_to": to_utc_iso(bucket.effective_to),
                    "subscription_current_period_end_at": to_utc_iso(
                        subscription.current_period_end_at
                    ),
                },
            )
        )
    return issues


def _dedupe_issues(issues: list[CreditAuditIssue]) -> list[CreditAuditIssue]:
    seen: set[tuple[str, str, str, str, str]] = set()
    deduped: list[CreditAuditIssue] = []
    for issue in issues:
        key = (
            issue.code,
            issue.creator_bid,
            issue.wallet_bid,
            issue.wallet_bucket_bid,
            issue.ledger_bid,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped
