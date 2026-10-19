"""Result records returned by creator wallet snapshot, grant, and repair helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from flaskr.util.datetime import to_utc_iso

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(slots=True, frozen=True)
class WalletSnapshotRecord:
    """Record wallet snapshot details."""

    wallet_bid: str
    creator_bid: str
    available_credits: int | float
    reserved_credits: int | float
    previous_available_credits: int | float
    previous_reserved_credits: int | float
    available_credits_delta: int | float
    reserved_credits_delta: int | float
    changed: bool

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "wallet_bid": self.wallet_bid,
            "creator_bid": self.creator_bid,
            "available_credits": self.available_credits,
            "reserved_credits": self.reserved_credits,
            "previous_available_credits": self.previous_available_credits,
            "previous_reserved_credits": self.previous_reserved_credits,
            "available_credits_delta": self.available_credits_delta,
            "reserved_credits_delta": self.reserved_credits_delta,
            "changed": self.changed,
        }

    def __getitem__(self, key: str) -> object:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class WalletSnapshotRebuildResult:
    """Capture the rebuild outcome for wallet snapshot."""

    status: str
    creator_bid: str | None
    wallet_bid: str | None
    wallet_count: int
    changed_wallet_count: int = 0
    dry_run: bool = False
    wallets: list[WalletSnapshotRecord] = field(default_factory=list)

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "wallet_bid": self.wallet_bid,
            "wallet_count": self.wallet_count,
            "changed_wallet_count": self.changed_wallet_count,
            "dry_run": self.dry_run,
            "wallets": [wallet.to_payload() for wallet in self.wallets],
        }

    def __getitem__(self, key: str) -> object:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class RefundReturnCreditsResult:
    """Capture credits returned while refunding a billing order."""

    status: str
    creator_bid: str | None
    source_bid: str | None
    amount: int | float = 0
    wallet_bucket_bid: str | None = None
    ledger_bid: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "source_bid": self.source_bid,
            "amount": self.amount,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "ledger_bid": self.ledger_bid,
        }

    def __getitem__(self, key: str) -> object:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class WalletExpirationResult:
    """Capture credits expired from a wallet."""

    status: str
    creator_bid: str | None
    bucket_count: int
    expired_credits: int | float

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "bucket_count": self.bucket_count,
            "expired_credits": self.expired_credits,
        }

    def __getitem__(self, key: str) -> object:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class ExpireLedgerBucketDriftRecord:
    """Record expire ledger bucket drift details."""

    wallet_bucket_bid: str
    wallet_bid: str
    creator_bid: str
    previous_available_credits: int | float
    available_credits: int | float
    previous_expired_credits: int | float
    expired_credits: int | float
    previous_status: int
    status: int
    expire_ledger_count: int
    expire_ledger_amount: int | float
    repair_action: str
    repair_reason: str
    changed: bool

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "wallet_bid": self.wallet_bid,
            "creator_bid": self.creator_bid,
            "previous_available_credits": self.previous_available_credits,
            "available_credits": self.available_credits,
            "previous_expired_credits": self.previous_expired_credits,
            "expired_credits": self.expired_credits,
            "previous_status": self.previous_status,
            "status": self.status,
            "expire_ledger_count": self.expire_ledger_count,
            "expire_ledger_amount": self.expire_ledger_amount,
            "repair_action": self.repair_action,
            "repair_reason": self.repair_reason,
            "changed": self.changed,
        }


@dataclass(slots=True, frozen=True)
class ExpireLedgerBucketDriftRepairResult:
    """Capture the repair outcome for expire ledger bucket drift."""

    status: str
    creator_bid: str | None
    wallet_bucket_bid: str | None
    bucket_count: int
    repaired_bucket_count: int
    manual_review_count: int
    dry_run: bool
    buckets: list[ExpireLedgerBucketDriftRecord] = field(default_factory=list)

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "bucket_count": self.bucket_count,
            "repaired_bucket_count": self.repaired_bucket_count,
            "manual_review_count": self.manual_review_count,
            "dry_run": self.dry_run,
            "buckets": [bucket.to_payload() for bucket in self.buckets],
        }

    def __getitem__(self, key: str) -> object:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class ExpiredCreditPackBucketRestoreRecord:
    """Record expired credit pack bucket restore details."""

    bill_order_bid: str
    creator_bid: str | None
    wallet_bid: str | None
    wallet_bucket_bid: str | None
    previous_available_credits: int | float
    available_credits: int | float
    previous_expired_credits: int | float
    expired_credits: int | float
    previous_status: int | None
    status: int | None
    restored_credits: int | float
    repair_action: str
    repair_reason: str
    changed: bool
    ledger_bid: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "bill_order_bid": self.bill_order_bid,
            "creator_bid": self.creator_bid,
            "wallet_bid": self.wallet_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "previous_available_credits": self.previous_available_credits,
            "available_credits": self.available_credits,
            "previous_expired_credits": self.previous_expired_credits,
            "expired_credits": self.expired_credits,
            "previous_status": self.previous_status,
            "status": self.status,
            "restored_credits": self.restored_credits,
            "repair_action": self.repair_action,
            "repair_reason": self.repair_reason,
            "changed": self.changed,
            "ledger_bid": self.ledger_bid,
        }


@dataclass(slots=True, frozen=True)
class ExpiredCreditPackBucketRestoreResult:
    """Capture credits restored from an expired credit-pack bucket."""

    status: str
    bill_order_bids: list[str]
    order_count: int
    repaired_bucket_count: int
    manual_review_count: int
    noop_count: int
    dry_run: bool
    buckets: list[ExpiredCreditPackBucketRestoreRecord] = field(default_factory=list)

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "bill_order_bids": list(self.bill_order_bids),
            "order_count": self.order_count,
            "repaired_bucket_count": self.repaired_bucket_count,
            "manual_review_count": self.manual_review_count,
            "noop_count": self.noop_count,
            "dry_run": self.dry_run,
            "buckets": [bucket.to_payload() for bucket in self.buckets],
        }

    def __getitem__(self, key: str) -> object:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class ManualCreditGrantResult:
    """Capture the outcome of manual credit grant."""

    status: str
    creator_bid: str | None
    amount: int | float = 0
    wallet_bid: str | None = None
    wallet_bucket_bid: str | None = None
    ledger_bid: str | None = None
    expires_at: datetime | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "amount": self.amount,
            "wallet_bid": self.wallet_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "ledger_bid": self.ledger_bid,
            "expires_at": self.expires_at,
            "metadata_json": self.metadata_json,
        }

    def __getitem__(self, key: str) -> object:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class ReservedGrantRepairRecord:
    """Record reserved grant repair details."""

    creator_bid: str
    bill_order_bid: str
    subscription_bid: str | None
    grant_ledger_bid: str
    wallet_bucket_bid: str | None
    consumable_from: datetime | None
    paid_at: datetime | None
    renewal_event_bids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Serialize this result as an API payload."""
        return {
            "creator_bid": self.creator_bid,
            "bill_order_bid": self.bill_order_bid,
            "subscription_bid": self.subscription_bid,
            "grant_ledger_bid": self.grant_ledger_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "consumable_from": to_utc_iso(self.consumable_from),
            "paid_at": to_utc_iso(self.paid_at),
            "renewal_event_bids": list(self.renewal_event_bids),
        }

    def __getitem__(self, key: str) -> object:
        """Return a serialized payload field by key."""
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class RenewalStateDriftRepairResult:
    """Capture the repair outcome for renewal state drift."""

    status: str
    creator_bid: str | None
    creator_count: int
    stale_subscription_count: int
    stale_bucket_count: int
    updated_subscription_count: int
    expired_bucket_count: int
    expired_credits: int | float
    dry_run: bool
    overdue_reserved_grant_count: int = 0
    activatable_creator_count: int = 0
    activated_reserved_order_count: int = 0
    activated_creator_count: int = 0
    protected_creator_count: int = 0
    manual_review_creator_count: int = 0
    creator_bids: list[str] = field(default_factory=list)
    activatable_creator_bids: list[str] = field(default_factory=list)
    activated_creator_bids: list[str] = field(default_factory=list)
    protected_creator_bids: list[str] = field(default_factory=list)
    manual_review_creator_bids: list[str] = field(default_factory=list)
    overdue_reserved_grants: list[ReservedGrantRepairRecord] = field(
        default_factory=list
    )

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "creator_count": self.creator_count,
            "stale_subscription_count": self.stale_subscription_count,
            "stale_bucket_count": self.stale_bucket_count,
            "updated_subscription_count": self.updated_subscription_count,
            "expired_bucket_count": self.expired_bucket_count,
            "expired_credits": self.expired_credits,
            "dry_run": self.dry_run,
            "overdue_reserved_grant_count": self.overdue_reserved_grant_count,
            "activatable_creator_count": self.activatable_creator_count,
            "activated_reserved_order_count": self.activated_reserved_order_count,
            "activated_creator_count": self.activated_creator_count,
            "protected_creator_count": self.protected_creator_count,
            "manual_review_creator_count": self.manual_review_creator_count,
            "creator_bids": list(self.creator_bids),
            "activatable_creator_bids": list(self.activatable_creator_bids),
            "activated_creator_bids": list(self.activated_creator_bids),
            "protected_creator_bids": list(self.protected_creator_bids),
            "manual_review_creator_bids": list(self.manual_review_creator_bids),
            "overdue_reserved_grants": [
                record.to_payload() for record in self.overdue_reserved_grants
            ],
        }

    def __getitem__(self, key: str) -> object:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]
