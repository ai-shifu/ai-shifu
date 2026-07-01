"""Referral campaign runtime helpers."""

from __future__ import annotations

import hashlib
import secrets
import string
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, has_app_context, has_request_context, request
from sqlalchemy import func

from flaskr.util.datetime import now_utc
from sqlalchemy.exc import IntegrityError

from flaskr.common.config import get_config as get_common_config
from flaskr.dao import db
from flaskr.service.billing.api import (
    ReferralPlanRewardRequest,
    grant_referral_plan_reward as _grant_referral_plan_reward_request,
)
from flaskr.service.user.models import UserInfo
from flaskr.util.uuid import generate_id

from .consts import (
    REFERRAL_CAMPAIGN_STATUS_ACTIVE,
    REFERRAL_INVITE_CODE_STATUS_ACTIVE,
    REFERRAL_INVITE_EVENT_TYPES,
    REFERRAL_RELATION_STATUS_REGISTERED,
    REFERRAL_RELATION_STATUS_REWARD_GENERATED,
    REFERRAL_RELATION_STATUS_REWARD_SKIPPED_CAP,
    REFERRAL_REWARD_CAP_SCOPE_NONE,
    REFERRAL_REWARD_CAP_SCOPE_PER_CAMPAIGN,
    REFERRAL_REWARD_CAP_SCOPE_PER_INVITER,
    REFERRAL_REWARD_GRANTED_STATUSES,
    REFERRAL_REWARD_STATUS_GENERATED,
    REFERRAL_REWARD_STATUS_SKIPPED_CAP,
    REFERRAL_RULE_STATUS_ACTIVE,
    REFERRAL_TRIGGER_INVITED_REGISTRATION,
)
from .dtos import InvitePreviewDTO, InviteProfileDTO
from .models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteCode,
    ReferralInviteEvent,
    ReferralInviteRelation,
    ReferralInviteReward,
)
from .reward_queue import build_referral_reward_queue


_INVITE_CODE_ALPHABET = string.ascii_uppercase + string.digits
_INVITE_CODE_LENGTH = 8


@dataclass(slots=True, frozen=True)
class InviteEventInput:
    event_type: str
    invite_code: str = ""
    landing_path: str = ""
    session_id: str = ""
    entry_source: str = ""
    client_ip: str = ""
    user_agent: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class InviteEventResult:
    success: bool
    session_id: str
    recognized: bool


@dataclass(slots=True, frozen=True)
class ReferralPostAuthResult:
    created_relation: bool = False
    created_reward: bool = False
    relation_bid: str = ""
    reward_bid: str = ""
    skipped_reason: str = ""


def hash_referral_context(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_referral_post_auth_fields(
    payload: dict[str, Any],
    *,
    client_ip: object = "",
    user_agent: object = "",
) -> dict[str, str]:
    return {
        "invite_code": str(payload.get("invite_code") or "").strip(),
        "referral_session_id": str(payload.get("referral_session_id") or "").strip(),
        "referral_entry_source": str(
            payload.get("referral_entry_source") or ""
        ).strip(),
        "client_ip_hash": hash_referral_context(client_ip),
        "user_agent_hash": hash_referral_context(user_agent),
    }


def _with_app_context(app: Flask):
    return app.app_context() if not has_app_context() else _NullContext()


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, *_exc):
        return False


def _feature_flag_enabled(feature_flag_key: str) -> bool:
    normalized_key = str(feature_flag_key or "").strip()
    if not normalized_key:
        return True
    raw_value = get_common_config(normalized_key, "")
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _within_window(
    *,
    starts_at: datetime | None,
    ends_at: datetime | None,
    now: datetime,
) -> bool:
    if starts_at is not None and starts_at > now:
        return False
    if ends_at is not None and ends_at <= now:
        return False
    return True


def _campaign_runtime_enabled(campaign: ReferralCampaign, *, now: datetime) -> bool:
    return (
        int(campaign.campaign_status or 0) == REFERRAL_CAMPAIGN_STATUS_ACTIVE
        and _within_window(
            starts_at=campaign.starts_at, ends_at=campaign.ends_at, now=now
        )
        and _feature_flag_enabled(str(campaign.feature_flag_key or ""))
    )


def load_active_campaign(*, now: datetime | None = None) -> ReferralCampaign | None:
    resolved_now = now or now_utc()
    candidates = (
        ReferralCampaign.query.filter(
            ReferralCampaign.deleted == 0,
            ReferralCampaign.campaign_status == REFERRAL_CAMPAIGN_STATUS_ACTIVE,
            (
                ReferralCampaign.starts_at.is_(None)
                | (ReferralCampaign.starts_at <= resolved_now)
            ),
            (
                ReferralCampaign.ends_at.is_(None)
                | (ReferralCampaign.ends_at > resolved_now)
            ),
        )
        .order_by(ReferralCampaign.starts_at.desc(), ReferralCampaign.id.desc())
        .all()
    )
    for campaign in candidates:
        if _feature_flag_enabled(str(campaign.feature_flag_key or "")):
            return campaign
    return None


def load_campaign_by_bid(
    campaign_bid: str,
    *,
    now: datetime | None = None,
) -> ReferralCampaign | None:
    campaign = (
        ReferralCampaign.query.filter(
            ReferralCampaign.deleted == 0,
            ReferralCampaign.campaign_bid == str(campaign_bid or "").strip(),
        )
        .order_by(ReferralCampaign.id.desc())
        .first()
    )
    if campaign is None:
        return None
    if not _campaign_runtime_enabled(campaign, now=now or now_utc()):
        return None
    return campaign


def select_reward_rule(
    campaign: ReferralCampaign,
    *,
    trigger_event: str = REFERRAL_TRIGGER_INVITED_REGISTRATION,
    now: datetime | None = None,
) -> ReferralCampaignRewardRule | None:
    resolved_now = now or now_utc()
    candidates = (
        ReferralCampaignRewardRule.query.filter(
            ReferralCampaignRewardRule.deleted == 0,
            ReferralCampaignRewardRule.campaign_bid == campaign.campaign_bid,
            ReferralCampaignRewardRule.rule_status == REFERRAL_RULE_STATUS_ACTIVE,
            ReferralCampaignRewardRule.trigger_event == trigger_event,
            (
                ReferralCampaignRewardRule.starts_at.is_(None)
                | (ReferralCampaignRewardRule.starts_at <= resolved_now)
            ),
            (
                ReferralCampaignRewardRule.ends_at.is_(None)
                | (ReferralCampaignRewardRule.ends_at > resolved_now)
            ),
        )
        .order_by(
            ReferralCampaignRewardRule.priority.desc(),
            ReferralCampaignRewardRule.id.desc(),
        )
        .all()
    )
    return candidates[0] if candidates else None


def _generate_invite_code() -> str:
    return "".join(
        secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(_INVITE_CODE_LENGTH)
    )


def _load_active_invite_code(
    *,
    campaign_bid: str,
    inviter_user_bid: str,
) -> ReferralInviteCode | None:
    return (
        ReferralInviteCode.query.filter(
            ReferralInviteCode.deleted == 0,
            ReferralInviteCode.campaign_bid == campaign_bid,
            ReferralInviteCode.inviter_user_bid == inviter_user_bid,
            ReferralInviteCode.status == REFERRAL_INVITE_CODE_STATUS_ACTIVE,
        )
        .order_by(ReferralInviteCode.id.desc())
        .first()
    )


def _create_invite_code_with_retry(
    app: Flask,
    *,
    campaign_bid: str,
    inviter_user_bid: str,
) -> ReferralInviteCode:
    for _attempt in range(5):
        invite_code = ReferralInviteCode(
            invite_code_bid=generate_id(app),
            campaign_bid=campaign_bid,
            inviter_user_bid=inviter_user_bid,
            invite_code=_generate_invite_code(),
            status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
            generated_at=now_utc(),
        )
        db.session.add(invite_code)
        try:
            db.session.flush()
            return invite_code
        except IntegrityError:
            db.session.rollback()
            existing = _load_active_invite_code(
                campaign_bid=campaign_bid,
                inviter_user_bid=inviter_user_bid,
            )
            if existing is not None:
                return existing
    raise RuntimeError("unable to generate referral invite code")


def _reward_count_for_rule(
    *,
    campaign_bid: str,
    reward_rule_bid: str,
    inviter_user_bid: str,
    cap_scope: str,
) -> int:
    query = ReferralInviteReward.query.filter(
        ReferralInviteReward.deleted == 0,
        ReferralInviteReward.campaign_bid == campaign_bid,
        ReferralInviteReward.reward_rule_bid == reward_rule_bid,
        ReferralInviteReward.reward_status.in_(REFERRAL_REWARD_GRANTED_STATUSES),
    )
    if cap_scope == REFERRAL_REWARD_CAP_SCOPE_PER_INVITER:
        query = query.filter(ReferralInviteReward.inviter_user_bid == inviter_user_bid)
    elif cap_scope == REFERRAL_REWARD_CAP_SCOPE_PER_CAMPAIGN:
        pass
    elif cap_scope == REFERRAL_REWARD_CAP_SCOPE_NONE:
        return 0
    else:
        query = query.filter(ReferralInviteReward.inviter_user_bid == inviter_user_bid)
    return int(query.with_entities(func.count(ReferralInviteReward.id)).scalar() or 0)


def _build_invite_url(campaign: ReferralCampaign, invite_code: str) -> str:
    template = (
        str(campaign.invite_route_template or "").strip() or "/invite/{invite_code}"
    )
    path = template.replace("{invite_code}", invite_code)
    if "{invite_code}" in path:
        path = f"/invite/{invite_code}"
    origin = _resolve_public_origin()
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{origin}{normalized_path}"


def _resolve_public_origin() -> str:
    configured_origin = _normalize_origin(str(get_common_config("HOST_URL", "") or ""))
    if configured_origin:
        return configured_origin
    if has_request_context():
        origin = str(request.headers.get("Origin") or "").split(",", 1)[0].strip()
        if origin and origin.lower() != "null":
            normalized_origin = _normalize_origin(origin)
            if normalized_origin:
                return normalized_origin
        return _normalize_origin(f"{request.scheme}://{request.host}")
    raise RuntimeError("HOST_URL must be configured to build referral invite URLs")


def _normalize_origin(value: str) -> str:
    raw_value = str(value or "").strip().rstrip("/")
    if not raw_value:
        return ""
    parsed = urlsplit(raw_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("HOST_URL must include http(s) scheme and host")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError(
            "HOST_URL must be an origin without path, query, or fragment"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def mask_identifier_snapshot(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    if "@" in raw_value:
        local_part, domain = raw_value.split("@", 1)
        if not domain:
            return "****"
        if len(local_part) > 2:
            masked_local = f"{local_part[:2]}****{local_part[-1:]}"
        elif local_part:
            masked_local = f"{local_part[0]}****"
        else:
            masked_local = "****"
        return f"{masked_local}@{domain}"
    digits = "".join(ch for ch in raw_value if ch.isdigit())
    if digits.startswith("0086") and len(digits) == 15:
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    return "****"


def _mask_reward_queue_mobile_snapshots(
    reward_queue: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    masked_queue: list[dict[str, Any]] = []
    for item in reward_queue:
        next_item = dict(item)
        next_item["invitee_mobile_snapshot"] = mask_identifier_snapshot(
            str(next_item.get("invitee_mobile_snapshot") or "")
        )
        masked_queue.append(next_item)
    return masked_queue


def build_invite_profile(app: Flask, *, inviter_user_bid: str) -> InviteProfileDTO:
    with _with_app_context(app):
        normalized_inviter = str(inviter_user_bid or "").strip()
        if not normalized_inviter:
            raise ValueError("inviter_user_bid is required")
        campaign = load_active_campaign()
        if campaign is None:
            return InviteProfileDTO.unavailable()
        rule = select_reward_rule(campaign)
        if rule is None:
            return InviteProfileDTO.unavailable()

        invite_code = _load_active_invite_code(
            campaign_bid=campaign.campaign_bid,
            inviter_user_bid=normalized_inviter,
        )
        if invite_code is None:
            invite_code = _create_invite_code_with_retry(
                app,
                campaign_bid=campaign.campaign_bid,
                inviter_user_bid=normalized_inviter,
            )
            db.session.commit()

        granted_count = _reward_count_for_rule(
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            inviter_user_bid=normalized_inviter,
            cap_scope=rule.reward_cap_scope,
        )
        cap_count = rule.reward_cap_count
        remaining = None
        if cap_count is not None:
            remaining = max(int(cap_count or 0) - granted_count, 0)

        reward_queue = build_referral_reward_queue(
            normalized_inviter,
            include_billing_artifacts=False,
            include_invitee_user_bid=False,
        )

        return InviteProfileDTO(
            campaign_bid=campaign.campaign_bid,
            campaign_code=campaign.campaign_code,
            invite_code=invite_code.invite_code,
            invite_url=_build_invite_url(campaign, invite_code.invite_code),
            reward_product_code=rule.reward_product_code,
            reward_cycle_count=rule.reward_cycle_count,
            reward_credit_amount=rule.reward_credit_amount,
            reward_credit_validity_days=rule.reward_credit_validity_days,
            reward_cap_scope=rule.reward_cap_scope,
            reward_cap_count=cap_count,
            reward_granted_count=granted_count,
            reward_remaining_count=remaining,
            reward_queue_summary=_reward_queue_summary(normalized_inviter),
            reward_queue=_mask_reward_queue_mobile_snapshots(reward_queue),
            rules_copy_i18n_key=campaign.rules_copy_i18n_key,
        )


def build_invite_preview(app: Flask, *, invite_code: str) -> InvitePreviewDTO:
    with _with_app_context(app):
        normalized_code = str(invite_code or "").strip().upper()
        if not normalized_code:
            return InvitePreviewDTO(recognized=False)
        code = _load_invite_code(normalized_code)
        if code is None or load_campaign_by_bid(code.campaign_bid) is None:
            return InvitePreviewDTO(recognized=False)
        return InvitePreviewDTO(
            recognized=True,
            invite_code=code.invite_code,
            inviter_mobile_masked=mask_identifier_snapshot(
                _load_invitee_mobile_snapshot(code.inviter_user_bid)
            ),
        )


def _reward_queue_summary(inviter_user_bid: str) -> dict[str, int]:
    rows = (
        ReferralInviteReward.query.filter(
            ReferralInviteReward.deleted == 0,
            ReferralInviteReward.inviter_user_bid == inviter_user_bid,
        )
        .with_entities(
            ReferralInviteReward.reward_status,
            func.count(ReferralInviteReward.id),
        )
        .group_by(ReferralInviteReward.reward_status)
        .all()
    )
    return {str(status): int(count or 0) for status, count in rows}


def _load_invite_code(invite_code: str) -> ReferralInviteCode | None:
    return (
        ReferralInviteCode.query.filter(
            ReferralInviteCode.deleted == 0,
            ReferralInviteCode.invite_code == str(invite_code or "").strip().upper(),
            ReferralInviteCode.status == REFERRAL_INVITE_CODE_STATUS_ACTIVE,
        )
        .order_by(ReferralInviteCode.id.desc())
        .first()
    )


def record_invite_event(app: Flask, payload: InviteEventInput) -> InviteEventResult:
    with _with_app_context(app):
        event_type = str(payload.event_type or "").strip()
        if event_type not in REFERRAL_INVITE_EVENT_TYPES:
            raise ValueError("unsupported referral invite event type")
        normalized_code = str(payload.invite_code or "").strip().upper()
        invite_code = _load_invite_code(normalized_code) if normalized_code else None
        campaign_bid = ""
        inviter_user_bid = ""
        recognized = False
        if invite_code is not None:
            campaign = load_campaign_by_bid(invite_code.campaign_bid)
            if campaign is not None:
                campaign_bid = campaign.campaign_bid
                inviter_user_bid = invite_code.inviter_user_bid
                recognized = True
        session_id = str(payload.session_id or "").strip() or generate_id(app)
        metadata = dict(payload.metadata or {})
        if payload.entry_source:
            metadata["entry_source"] = str(payload.entry_source).strip()
        metadata["recognized"] = recognized

        db.session.add(
            ReferralInviteEvent(
                event_bid=generate_id(app),
                campaign_bid=campaign_bid,
                event_type=event_type,
                invite_code=normalized_code if recognized else "",
                inviter_user_bid=inviter_user_bid,
                session_id=session_id,
                client_ip_hash=hash_referral_context(payload.client_ip),
                user_agent_hash=hash_referral_context(payload.user_agent),
                landing_path=str(payload.landing_path or "").strip()[:512],
                metadata_json=metadata,
            )
        )
        db.session.commit()
        return InviteEventResult(
            success=True,
            session_id=session_id,
            recognized=recognized,
        )


def _load_invitee_mobile_snapshot(user_bid: str) -> str:
    user = (
        UserInfo.query.filter(
            UserInfo.deleted == 0,
            UserInfo.user_bid == str(user_bid or "").strip(),
        )
        .order_by(UserInfo.id.desc())
        .first()
    )
    return str(user.user_identify or "").strip() if user is not None else ""


def _existing_relation_for_invitee(
    invitee_user_bid: str,
) -> ReferralInviteRelation | None:
    return (
        ReferralInviteRelation.query.filter(
            ReferralInviteRelation.deleted == 0,
            ReferralInviteRelation.invitee_user_bid
            == str(invitee_user_bid or "").strip(),
        )
        .order_by(ReferralInviteRelation.id.desc())
        .first()
    )


def _cap_reached(
    *,
    rule: ReferralCampaignRewardRule,
    inviter_user_bid: str,
    campaign_bid: str,
) -> bool:
    if rule.reward_cap_scope == REFERRAL_REWARD_CAP_SCOPE_NONE:
        return False
    cap_count = rule.reward_cap_count
    if cap_count is None or int(cap_count or 0) <= 0:
        return False
    reward_count = _reward_count_for_rule(
        campaign_bid=campaign_bid,
        reward_rule_bid=rule.reward_rule_bid,
        inviter_user_bid=inviter_user_bid,
        cap_scope=rule.reward_cap_scope,
    )
    return reward_count >= int(cap_count)


def _build_reward_from_relation(
    app: Flask,
    *,
    relation: ReferralInviteRelation,
    rule: ReferralCampaignRewardRule,
    reward_status: int,
) -> ReferralInviteReward:
    return ReferralInviteReward(
        reward_bid=generate_id(app),
        campaign_bid=relation.campaign_bid,
        reward_rule_bid=rule.reward_rule_bid,
        relation_bid=relation.relation_bid,
        inviter_user_bid=relation.inviter_user_bid,
        invitee_user_bid=relation.invitee_user_bid,
        reward_status=reward_status,
        reward_target=rule.reward_target,
        reward_type=rule.reward_type,
        reward_product_code=rule.reward_product_code,
        reward_cycle_count=rule.reward_cycle_count,
        reward_credit_amount=rule.reward_credit_amount,
        reward_credit_validity_days=rule.reward_credit_validity_days,
        reward_cap_scope=rule.reward_cap_scope,
        reward_cap_count=rule.reward_cap_count,
        reward_timing_policy=rule.reward_timing_policy,
        rule_snapshot=rule.to_snapshot(),
    )


def grant_referral_plan_reward(
    app: Flask,
    *,
    reward: ReferralInviteReward,
) -> dict[str, Any]:
    request = ReferralPlanRewardRequest(
        reward_bid=reward.reward_bid,
        inviter_user_bid=reward.inviter_user_bid,
        campaign_bid=reward.campaign_bid,
        reward_rule_bid=reward.reward_rule_bid,
        product_code=reward.reward_product_code,
        cycle_count=reward.reward_cycle_count,
        credit_amount=(
            Decimal(str(reward.reward_credit_amount))
            if reward.reward_credit_amount is not None
            else None
        ),
        credit_validity_days=reward.reward_credit_validity_days,
        timing_policy=reward.reward_timing_policy,
        rule_snapshot=reward.rule_snapshot or {},
    )
    result = _grant_referral_plan_reward_request(app, request=request)
    return result.to_dict()


def _reward_has_billing_order(reward: ReferralInviteReward) -> bool:
    artifacts = (
        reward.billing_artifacts if isinstance(reward.billing_artifacts, dict) else {}
    )
    return bool(str(artifacts.get("bill_order_bid") or "").strip())


def _mark_reward_grant_succeeded(
    *,
    relation_bid: str,
    reward_bid: str,
    billing_artifacts: dict[str, Any],
) -> None:
    relation = ReferralInviteRelation.query.filter(
        ReferralInviteRelation.deleted == 0,
        ReferralInviteRelation.relation_bid == relation_bid,
    ).one()
    reward = ReferralInviteReward.query.filter(
        ReferralInviteReward.deleted == 0,
        ReferralInviteReward.reward_bid == reward_bid,
    ).one()
    reward.billing_artifacts = dict(billing_artifacts or {})
    relation.relation_status = REFERRAL_RELATION_STATUS_REWARD_GENERATED
    db.session.add_all([relation, reward])
    db.session.commit()


def _mark_reward_grant_failed(
    *,
    reward_bid: str,
    error: Exception,
) -> None:
    reward = ReferralInviteReward.query.filter(
        ReferralInviteReward.deleted == 0,
        ReferralInviteReward.reward_bid == reward_bid,
    ).one()
    artifacts = (
        reward.billing_artifacts if isinstance(reward.billing_artifacts, dict) else {}
    )
    reward.billing_artifacts = {
        **artifacts,
        "grant_error": str(error)[:500],
        "last_failed_at": now_utc().isoformat() + "Z",
    }
    db.session.add(reward)
    db.session.commit()


def retry_pending_referral_rewards(
    app: Flask,
    *,
    limit: int = 100,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Retry generated referral rewards that do not yet have billing artifacts."""

    with _with_app_context(app):
        safe_limit = max(min(int(limit or 100), 500), 1)
        rewards = (
            ReferralInviteReward.query.filter(
                ReferralInviteReward.deleted == 0,
                ReferralInviteReward.reward_status == REFERRAL_REWARD_STATUS_GENERATED,
            )
            .order_by(ReferralInviteReward.id.asc())
            .limit(safe_limit)
            .all()
        )
        results: list[dict[str, Any]] = []
        for reward in rewards:
            if _reward_has_billing_order(reward):
                continue
            relation = ReferralInviteRelation.query.filter(
                ReferralInviteRelation.deleted == 0,
                ReferralInviteRelation.relation_bid == reward.relation_bid,
            ).first()
            if relation is None:
                results.append(
                    {
                        "reward_bid": reward.reward_bid,
                        "relation_bid": reward.relation_bid,
                        "action": "skipped_missing_relation",
                    }
                )
                continue
            if dry_run:
                results.append(
                    {
                        "reward_bid": reward.reward_bid,
                        "relation_bid": reward.relation_bid,
                        "action": "would_retry",
                    }
                )
                continue
            try:
                billing_artifacts = grant_referral_plan_reward(app, reward=reward)
                _mark_reward_grant_succeeded(
                    relation_bid=relation.relation_bid,
                    reward_bid=reward.reward_bid,
                    billing_artifacts=billing_artifacts,
                )
                results.append(
                    {
                        "reward_bid": reward.reward_bid,
                        "relation_bid": relation.relation_bid,
                        "action": "retried",
                        "bill_order_bid": billing_artifacts.get("bill_order_bid", ""),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - repair must continue per row.
                db.session.rollback()
                _mark_reward_grant_failed(reward_bid=reward.reward_bid, error=exc)
                results.append(
                    {
                        "reward_bid": reward.reward_bid,
                        "relation_bid": relation.relation_bid,
                        "action": "failed",
                        "error": str(exc)[:500],
                    }
                )
        return results


def process_referral_post_auth(
    app: Flask,
    context: Any,
) -> ReferralPostAuthResult:
    with _with_app_context(app):
        if not context.created_new_user:
            return ReferralPostAuthResult()
        normalized_code = str(context.invite_code or "").strip().upper()
        if not normalized_code:
            return ReferralPostAuthResult()
        invite_code = _load_invite_code(normalized_code)
        if invite_code is None:
            return ReferralPostAuthResult(skipped_reason="invite_code_not_found")
        if invite_code.inviter_user_bid == context.user_id:
            return ReferralPostAuthResult(skipped_reason="self_invite")
        campaign = load_campaign_by_bid(invite_code.campaign_bid)
        if campaign is None:
            return ReferralPostAuthResult(skipped_reason="campaign_not_active")
        rule = select_reward_rule(campaign)
        if rule is None:
            return ReferralPostAuthResult(skipped_reason="reward_rule_not_active")
        existing_relation = _existing_relation_for_invitee(context.user_id)
        if existing_relation is not None:
            existing_reward = (
                ReferralInviteReward.query.filter(
                    ReferralInviteReward.deleted == 0,
                    ReferralInviteReward.relation_bid == existing_relation.relation_bid,
                )
                .order_by(ReferralInviteReward.id.desc())
                .first()
            )
            return ReferralPostAuthResult(
                created_relation=False,
                created_reward=False,
                relation_bid=existing_relation.relation_bid,
                reward_bid=existing_reward.reward_bid if existing_reward else "",
            )

        now = now_utc()
        relation = ReferralInviteRelation(
            relation_bid=generate_id(app),
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            invite_code=invite_code.invite_code,
            inviter_user_bid=invite_code.inviter_user_bid,
            invitee_user_bid=context.user_id,
            invitee_mobile_snapshot=_load_invitee_mobile_snapshot(context.user_id),
            bound_at=now,
            registration_source="phone" if context.source == "sms" else context.source,
            reward_eligible=1,
            relation_status=REFERRAL_RELATION_STATUS_REGISTERED,
            metadata_json={
                "referral_session_id": context.referral_session_id or "",
                "referral_entry_source": context.referral_entry_source or "",
                "client_ip_hash": context.client_ip_hash or "",
                "user_agent_hash": context.user_agent_hash or "",
            },
        )
        db.session.add(relation)
        db.session.flush()

        if _cap_reached(
            rule=rule,
            inviter_user_bid=invite_code.inviter_user_bid,
            campaign_bid=campaign.campaign_bid,
        ):
            relation.relation_status = REFERRAL_RELATION_STATUS_REWARD_SKIPPED_CAP
            reward = _build_reward_from_relation(
                app,
                relation=relation,
                rule=rule,
                reward_status=REFERRAL_REWARD_STATUS_SKIPPED_CAP,
            )
            db.session.add(reward)
            db.session.commit()
            return ReferralPostAuthResult(
                created_relation=True,
                created_reward=True,
                relation_bid=relation.relation_bid,
                reward_bid=reward.reward_bid,
                skipped_reason="cap_reached",
            )

        reward = _build_reward_from_relation(
            app,
            relation=relation,
            rule=rule,
            reward_status=REFERRAL_REWARD_STATUS_GENERATED,
        )
        db.session.add(reward)
        db.session.flush()
        db.session.commit()
        try:
            billing_artifacts = grant_referral_plan_reward(app, reward=reward)
            _mark_reward_grant_succeeded(
                relation_bid=relation.relation_bid,
                reward_bid=reward.reward_bid,
                billing_artifacts=billing_artifacts,
            )
        except Exception as exc:  # noqa: BLE001 - referral grant is best-effort.
            db.session.rollback()
            _mark_reward_grant_failed(reward_bid=reward.reward_bid, error=exc)
            return ReferralPostAuthResult(
                created_relation=True,
                created_reward=True,
                relation_bid=relation.relation_bid,
                reward_bid=reward.reward_bid,
                skipped_reason="billing_grant_failed",
            )
        return ReferralPostAuthResult(
            created_relation=True,
            created_reward=True,
            relation_bid=relation.relation_bid,
            reward_bid=reward.reward_bid,
        )
