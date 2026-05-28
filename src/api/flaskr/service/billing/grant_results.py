"""Shared result payloads for operator credit grants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class ManualCreditGrantResult:
    """Resolved state for one manual credit grant request."""

    status: str
    user_bid: str
    amount: int | float
    grant_source: str
    validity_preset: str
    expires_at: datetime | None
    wallet_bucket_bid: str
    ledger_bid: str
    display_name: str = ""
    note: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "user_bid": self.user_bid,
            "amount": self.amount,
            "grant_source": self.grant_source,
            "validity_preset": self.validity_preset,
            "expires_at": self.expires_at,
            "display_name": self.display_name,
            "note": self.note,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "ledger_bid": self.ledger_bid,
            "metadata_json": self.metadata_json,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class ReferralRewardSummary:
    available_credits: int | float
    expires_at: datetime | None
    wallet_bucket_bid: str = ""
    grant_count: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "available_credits": self.available_credits,
            "expires_at": self.expires_at,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "grant_count": self.grant_count,
        }
