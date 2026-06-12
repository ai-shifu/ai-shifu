"""Stable referral service entry points."""

from __future__ import annotations

from .admin import (
    get_operator_referral_detail,
    get_operator_referral_overview,
    list_operator_referrals,
    update_operator_referral_status,
)
from .campaign_admin import (
    create_operator_referral_campaign,
    get_operator_referral_campaign_detail,
    list_operator_referral_campaigns,
    update_operator_referral_campaign,
    update_operator_referral_campaign_status,
)
from .service import (
    InviteEventInput,
    build_invite_profile,
    process_referral_post_auth,
    record_invite_event,
    retry_pending_referral_rewards,
)

__all__ = [
    "InviteEventInput",
    "build_invite_profile",
    "create_operator_referral_campaign",
    "get_operator_referral_campaign_detail",
    "get_operator_referral_detail",
    "get_operator_referral_overview",
    "list_operator_referral_campaigns",
    "list_operator_referrals",
    "process_referral_post_auth",
    "record_invite_event",
    "retry_pending_referral_rewards",
    "update_operator_referral_campaign",
    "update_operator_referral_campaign_status",
    "update_operator_referral_status",
]
