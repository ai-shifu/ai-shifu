"""Referral DTO helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(slots=True, frozen=True)
class InviteProfileDTO:
    campaign_bid: str
    campaign_code: str
    invite_code: str
    invite_url: str
    reward_product_code: str
    reward_cycle_count: int
    reward_credit_amount: Decimal | None
    reward_credit_validity_days: int | None
    reward_cap_scope: str
    reward_cap_count: int | None
    reward_granted_count: int
    reward_remaining_count: int | None
    reward_queue_summary: dict[str, int] = field(default_factory=dict)
    reward_queue: list[dict[str, Any]] = field(default_factory=list)
    rules_copy_i18n_key: str = ""
    available: bool = True

    @classmethod
    def unavailable(cls) -> "InviteProfileDTO":
        return cls(
            campaign_bid="",
            campaign_code="",
            invite_code="",
            invite_url="",
            reward_product_code="",
            reward_cycle_count=0,
            reward_credit_amount=None,
            reward_credit_validity_days=None,
            reward_cap_scope="",
            reward_cap_count=None,
            reward_granted_count=0,
            reward_remaining_count=None,
            available=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "campaign_bid": self.campaign_bid,
            "campaign_code": self.campaign_code,
            "invite_code": self.invite_code,
            "invite_url": self.invite_url,
            "reward_product_code": self.reward_product_code,
            "reward_cycle_count": self.reward_cycle_count,
            "reward_credit_amount": (
                str(self.reward_credit_amount)
                if self.reward_credit_amount is not None
                else None
            ),
            "reward_credit_validity_days": self.reward_credit_validity_days,
            "reward_cap_scope": self.reward_cap_scope,
            "reward_cap_count": self.reward_cap_count,
            "reward_granted_count": self.reward_granted_count,
            "reward_remaining_count": self.reward_remaining_count,
            "reward_queue_summary": dict(self.reward_queue_summary),
            "reward_queue": [dict(item) for item in self.reward_queue],
            "rules_copy_i18n_key": self.rules_copy_i18n_key,
        }


@dataclass(slots=True, frozen=True)
class InvitePreviewDTO:
    recognized: bool
    invite_code: str = ""
    inviter_mobile_masked: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recognized": self.recognized,
            "invite_code": self.invite_code,
            "inviter_mobile_masked": self.inviter_mobile_masked,
        }
