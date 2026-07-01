"""Operator read models for referral invitation rewards."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import Flask
from sqlalchemy import or_

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.datetime import now_utc

from .consts import (
    REFERRAL_ABNORMAL_STATUS_CONFIRMED_ABNORMAL,
    REFERRAL_ABNORMAL_STATUS_NORMAL,
    REFERRAL_ABNORMAL_STATUS_REVIEWING,
    REFERRAL_INVITE_EVENT_CODE_ENTERED,
    REFERRAL_INVITE_EVENT_LINK_CLICKED,
    REFERRAL_INVITE_EVENT_REGISTRATION_PAGE_VIEWED,
    REFERRAL_INVITE_EVENT_REGISTRATION_SUBMITTED,
    REFERRAL_INVITE_EVENT_TYPES,
    REFERRAL_RELATION_STATUS_ABNORMAL_REVIEWING,
    REFERRAL_RELATION_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_FROZEN,
)
from .models import (
    ReferralCampaign,
    ReferralInviteCode,
    ReferralInviteEvent,
    ReferralInviteRelation,
    ReferralInviteReward,
)
from .campaign_admin import _load_campaign_or_404
from .reward_queue import build_referral_reward_queue

DEFAULT_PAGE_INDEX = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

ABNORMAL_STATUS_BY_LABEL = {
    "normal": REFERRAL_ABNORMAL_STATUS_NORMAL,
    "reviewing": REFERRAL_ABNORMAL_STATUS_REVIEWING,
    "confirmed_abnormal": REFERRAL_ABNORMAL_STATUS_CONFIRMED_ABNORMAL,
}

RELATION_STATUS_BY_LABEL = {
    "abnormal_reviewing": REFERRAL_RELATION_STATUS_ABNORMAL_REVIEWING,
    "canceled": REFERRAL_RELATION_STATUS_CANCELED,
}

REWARD_STATUS_BY_LABEL = {
    "frozen": REFERRAL_REWARD_STATUS_FROZEN,
    "canceled": REFERRAL_REWARD_STATUS_CANCELED,
}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_page(page_index: int, page_size: int) -> tuple[int, int]:
    try:
        safe_page_index = max(int(page_index or DEFAULT_PAGE_INDEX), 1)
    except (TypeError, ValueError):
        safe_page_index = DEFAULT_PAGE_INDEX
    try:
        safe_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    except (TypeError, ValueError):
        safe_page_size = DEFAULT_PAGE_SIZE
    return safe_page_index, min(safe_page_size, MAX_PAGE_SIZE)


def _serialize_dt(value: datetime | None) -> str | None:
    # Match the API fmt sink (flaskr/route/common.py): stored values are UTC;
    # treat naive as UTC and emit ISO 8601 with a 'Z' suffix so the frontend
    # can convert to the viewer's timezone via formatAdminUtcDateTime().
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _user_bid_or_identifier_filter(column: Any, value: str) -> Any:
    normalized = _normalize_text(value)
    matching_user_bids = db.session.query(UserEntity.user_bid).filter(
        UserEntity.deleted == 0,
        UserEntity.user_identify == normalized,
    )
    return or_(column == normalized, column.in_(matching_user_bids))


def _user_contact_map(user_bids: set[str]) -> dict[str, dict[str, str]]:
    if not user_bids:
        return {}
    rows = UserEntity.query.filter(
        UserEntity.deleted == 0,
        UserEntity.user_bid.in_(sorted(user_bids)),
    ).all()
    return {
        row.user_bid: {
            "user_bid": row.user_bid,
            "nickname": row.nickname or "",
            "identifier": row.user_identify or "",
        }
        for row in rows
    }


def _latest_reward_map(
    relation_bids: list[str],
) -> dict[str, ReferralInviteReward]:
    if not relation_bids:
        return {}
    rows = (
        ReferralInviteReward.query.filter(
            ReferralInviteReward.deleted == 0,
            ReferralInviteReward.relation_bid.in_(relation_bids),
        )
        .order_by(ReferralInviteReward.id.desc())
        .all()
    )
    result: dict[str, ReferralInviteReward] = {}
    for row in rows:
        result.setdefault(row.relation_bid, row)
    return result


def _campaign_map(campaign_bids: set[str]) -> dict[str, ReferralCampaign]:
    if not campaign_bids:
        return {}
    rows = ReferralCampaign.query.filter(
        ReferralCampaign.deleted == 0,
        ReferralCampaign.campaign_bid.in_(sorted(campaign_bids)),
    ).all()
    return {row.campaign_bid: row for row in rows}


def _serialize_relation(
    relation: ReferralInviteRelation,
    *,
    reward: ReferralInviteReward | None,
    users: dict[str, dict[str, str]],
    campaigns: dict[str, ReferralCampaign],
) -> dict[str, Any]:
    campaign = campaigns.get(relation.campaign_bid)
    return {
        "relation_bid": relation.relation_bid,
        "campaign_bid": relation.campaign_bid,
        "campaign_code": campaign.campaign_code if campaign is not None else "",
        "campaign_name": campaign.campaign_name if campaign is not None else "",
        "reward_rule_bid": relation.reward_rule_bid,
        "invite_code": relation.invite_code,
        "inviter_user_bid": relation.inviter_user_bid,
        "inviter": users.get(relation.inviter_user_bid, {}),
        "invitee_user_bid": relation.invitee_user_bid,
        "invitee": users.get(relation.invitee_user_bid, {}),
        "invitee_mobile_snapshot": relation.invitee_mobile_snapshot,
        "bound_at": _serialize_dt(relation.bound_at),
        "registration_source": relation.registration_source,
        "reward_eligible": bool(relation.reward_eligible),
        "relation_status": relation.relation_status,
        "abnormal_status": relation.abnormal_status,
        "metadata": relation.metadata_json or {},
        "reward": _serialize_reward(reward),
        "created_at": _serialize_dt(relation.created_at),
        "updated_at": _serialize_dt(relation.updated_at),
    }


def _serialize_reward(reward: ReferralInviteReward | None) -> dict[str, Any] | None:
    if reward is None:
        return None
    return {
        "reward_bid": reward.reward_bid,
        "reward_status": reward.reward_status,
        "reward_target": reward.reward_target,
        "reward_type": reward.reward_type,
        "reward_product_code": reward.reward_product_code,
        "reward_cycle_count": reward.reward_cycle_count,
        "reward_credit_amount": _serialize_decimal(reward.reward_credit_amount),
        "reward_credit_validity_days": reward.reward_credit_validity_days,
        "reward_cap_scope": reward.reward_cap_scope,
        "reward_cap_count": reward.reward_cap_count,
        "reward_timing_policy": reward.reward_timing_policy,
        "rule_snapshot": reward.rule_snapshot or {},
        "billing_artifacts": reward.billing_artifacts or {},
        "operator_note": reward.operator_note,
        "effective_at": _serialize_dt(reward.effective_at),
        "expires_at": _serialize_dt(reward.expires_at),
        "created_at": _serialize_dt(reward.created_at),
        "updated_at": _serialize_dt(reward.updated_at),
    }


def list_operator_referrals(
    app: Flask,
    *,
    page_index: int,
    page_size: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        safe_page_index, safe_page_size = _normalize_page(page_index, page_size)
        query = ReferralInviteRelation.query.filter(ReferralInviteRelation.deleted == 0)
        for field in ("campaign_bid", "invite_code"):
            value = _normalize_text(filters.get(field))
            if value:
                query = query.filter(getattr(ReferralInviteRelation, field) == value)
        for field in ("inviter_user_bid", "invitee_user_bid"):
            value = _normalize_text(filters.get(field))
            if value:
                query = query.filter(
                    _user_bid_or_identifier_filter(
                        getattr(ReferralInviteRelation, field),
                        value,
                    )
                )
        for field in ("relation_status", "abnormal_status"):
            value = _normalize_text(filters.get(field))
            if value:
                try:
                    query = query.filter(
                        getattr(ReferralInviteRelation, field) == int(value)
                    )
                except ValueError:
                    raise_param_error(field)
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        if start_time is not None:
            query = query.filter(ReferralInviteRelation.bound_at >= start_time)
        if end_time is not None:
            query = query.filter(ReferralInviteRelation.bound_at <= end_time)

        total = query.count()
        rows = (
            query.order_by(
                ReferralInviteRelation.bound_at.desc(),
                ReferralInviteRelation.id.desc(),
            )
            .offset((safe_page_index - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        relation_bids = [row.relation_bid for row in rows]
        rewards = _latest_reward_map(relation_bids)
        user_bids = {
            bid
            for row in rows
            for bid in (row.inviter_user_bid, row.invitee_user_bid)
            if bid
        }
        users = _user_contact_map(user_bids)
        campaigns = _campaign_map(
            {row.campaign_bid for row in rows if row.campaign_bid}
        )
        return {
            "items": [
                _serialize_relation(
                    row,
                    reward=rewards.get(row.relation_bid),
                    users=users,
                    campaigns=campaigns,
                )
                for row in rows
            ],
            "page_index": safe_page_index,
            "page_size": safe_page_size,
            "total": total,
            "page_count": _page_count(total, safe_page_size),
        }


def list_operator_referral_campaign_invitations(
    app: Flask,
    *,
    campaign_bid: str,
    page_index: int,
    page_size: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        normalized_campaign_bid = _normalize_text(campaign_bid)
        _load_campaign_or_404(normalized_campaign_bid)
        safe_page_index, safe_page_size = _normalize_page(page_index, page_size)
        query = ReferralInviteCode.query.filter(
            ReferralInviteCode.deleted == 0,
            ReferralInviteCode.campaign_bid == normalized_campaign_bid,
        )
        inviter_value = _normalize_text(filters.get("inviter_user_bid"))
        if inviter_value:
            query = query.filter(
                _user_bid_or_identifier_filter(
                    ReferralInviteCode.inviter_user_bid,
                    inviter_value,
                )
            )
        invite_code = _normalize_text(filters.get("invite_code"))
        if invite_code:
            query = query.filter(ReferralInviteCode.invite_code == invite_code)
        status = _normalize_text(filters.get("status"))
        if status:
            try:
                query = query.filter(ReferralInviteCode.status == int(status))
            except ValueError:
                raise_param_error("status")
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        if start_time is not None:
            query = query.filter(ReferralInviteCode.generated_at >= start_time)
        if end_time is not None:
            query = query.filter(ReferralInviteCode.generated_at <= end_time)

        total = query.count()
        rows = (
            query.order_by(
                ReferralInviteCode.generated_at.desc(),
                ReferralInviteCode.id.desc(),
            )
            .offset((safe_page_index - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        invite_codes = [row.invite_code for row in rows if row.invite_code]
        event_stats = _invite_event_stats_by_code(
            campaign_bid=normalized_campaign_bid,
            invite_codes=invite_codes,
        )
        relation_counts = _relation_counts_by_code(
            campaign_bid=normalized_campaign_bid,
            invite_codes=invite_codes,
        )
        users = _user_contact_map(
            {row.inviter_user_bid for row in rows if row.inviter_user_bid}
        )
        return {
            "items": [
                _serialize_invitation(
                    row,
                    users=users,
                    event_stats=event_stats.get(row.invite_code, {}),
                    relation_count=relation_counts.get(row.invite_code, 0),
                )
                for row in rows
            ],
            "page_index": safe_page_index,
            "page_size": safe_page_size,
            "total": total,
            "page_count": _page_count(total, safe_page_size),
        }


def get_operator_referral_detail(app: Flask, *, relation_bid: str) -> dict[str, Any]:
    with app.app_context():
        relation = (
            ReferralInviteRelation.query.filter(
                ReferralInviteRelation.deleted == 0,
                ReferralInviteRelation.relation_bid == _normalize_text(relation_bid),
            )
            .order_by(ReferralInviteRelation.id.desc())
            .first()
        )
        if relation is None:
            raise_error("server.referral.relationNotFound")
        rewards = _latest_reward_map([relation.relation_bid])
        users = _user_contact_map(
            {relation.inviter_user_bid, relation.invitee_user_bid}
        )
        campaigns = _campaign_map({relation.campaign_bid})
        payload = _serialize_relation(
            relation,
            reward=rewards.get(relation.relation_bid),
            users=users,
            campaigns=campaigns,
        )
        payload["reward_queue"] = build_referral_reward_queue(
            relation.inviter_user_bid,
            include_billing_artifacts=True,
            include_invitee_user_bid=True,
        )
        return payload


def get_operator_referral_overview(app: Flask) -> dict[str, int]:
    with app.app_context():
        total_relations = ReferralInviteRelation.query.filter(
            ReferralInviteRelation.deleted == 0
        ).count()
        abnormal_relations = ReferralInviteRelation.query.filter(
            ReferralInviteRelation.deleted == 0,
            ReferralInviteRelation.abnormal_status != REFERRAL_ABNORMAL_STATUS_NORMAL,
        ).count()
        generated_rewards = ReferralInviteReward.query.filter(
            ReferralInviteReward.deleted == 0,
            ReferralInviteReward.reward_status.notin_(
                [REFERRAL_REWARD_STATUS_CANCELED]
            ),
        ).count()
        return {
            "total_relations": int(total_relations or 0),
            "abnormal_relations": int(abnormal_relations or 0),
            "generated_rewards": int(generated_rewards or 0),
        }


def update_operator_referral_status(
    app: Flask,
    *,
    relation_bid: str,
    operator_user_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        relation = (
            ReferralInviteRelation.query.filter(
                ReferralInviteRelation.deleted == 0,
                ReferralInviteRelation.relation_bid == _normalize_text(relation_bid),
            )
            .order_by(ReferralInviteRelation.id.desc())
            .first()
        )
        if relation is None:
            raise_error("server.referral.relationNotFound")
        reward = _latest_reward_map([relation.relation_bid]).get(relation.relation_bid)

        relation_status = _normalize_text(payload.get("relation_status"))
        abnormal_status = _normalize_text(payload.get("abnormal_status"))
        reward_status = _normalize_text(payload.get("reward_status"))
        note = _normalize_text(payload.get("operator_note"))

        if relation_status:
            if relation_status not in RELATION_STATUS_BY_LABEL:
                raise_param_error("relation_status")
            relation.relation_status = RELATION_STATUS_BY_LABEL[relation_status]
        if abnormal_status:
            if abnormal_status not in ABNORMAL_STATUS_BY_LABEL:
                raise_param_error("abnormal_status")
            relation.abnormal_status = ABNORMAL_STATUS_BY_LABEL[abnormal_status]
        if reward_status:
            if reward_status not in REWARD_STATUS_BY_LABEL:
                raise_param_error("reward_status")
            if reward is None:
                raise_error("server.referral.rewardNotFound")
            reward.reward_status = REWARD_STATUS_BY_LABEL[reward_status]
        if note:
            metadata = (
                relation.metadata_json
                if isinstance(relation.metadata_json, dict)
                else {}
            )
            metadata["operator_note"] = note
            metadata["operator_user_bid"] = _normalize_text(operator_user_bid)
            metadata["operator_updated_at"] = _serialize_dt(now_utc())
            relation.metadata_json = metadata
            if reward is not None:
                reward.operator_note = note

        db.session.add(relation)
        if reward is not None:
            db.session.add(reward)
        db.session.commit()
        return get_operator_referral_detail(app, relation_bid=relation.relation_bid)


def _page_count(total: int, page_size: int) -> int:
    return ((total + page_size - 1) // page_size) if total else 0


def _invite_event_stats_by_code(
    *,
    campaign_bid: str,
    invite_codes: list[str],
) -> dict[str, dict[str, Any]]:
    if not invite_codes:
        return {}
    rows = (
        db.session.query(
            ReferralInviteEvent.invite_code,
            ReferralInviteEvent.event_type,
            db.func.count(ReferralInviteEvent.id),
            db.func.max(ReferralInviteEvent.created_at),
        )
        .filter(
            ReferralInviteEvent.campaign_bid == campaign_bid,
            ReferralInviteEvent.invite_code.in_(invite_codes),
        )
        .group_by(ReferralInviteEvent.invite_code, ReferralInviteEvent.event_type)
        .all()
    )
    result: dict[str, dict[str, Any]] = {}
    for invite_code, event_type, count, latest_at in rows:
        stats = result.setdefault(
            invite_code,
            {
                "event_counts": {
                    event_type: 0 for event_type in REFERRAL_INVITE_EVENT_TYPES
                },
                "total_event_count": 0,
                "latest_event_at": None,
            },
        )
        stats["event_counts"][event_type] = int(count or 0)
        stats["total_event_count"] = int(stats["total_event_count"]) + int(count or 0)
        current_latest = stats.get("latest_event_at")
        if current_latest is None or (
            latest_at is not None and latest_at > current_latest
        ):
            stats["latest_event_at"] = latest_at
    return result


def _relation_counts_by_code(
    *,
    campaign_bid: str,
    invite_codes: list[str],
) -> dict[str, int]:
    if not invite_codes:
        return {}
    rows = (
        db.session.query(
            ReferralInviteRelation.invite_code,
            db.func.count(ReferralInviteRelation.id),
        )
        .filter(
            ReferralInviteRelation.deleted == 0,
            ReferralInviteRelation.campaign_bid == campaign_bid,
            ReferralInviteRelation.invite_code.in_(invite_codes),
            ReferralInviteRelation.relation_status.notin_(
                [
                    REFERRAL_RELATION_STATUS_ABNORMAL_REVIEWING,
                    REFERRAL_RELATION_STATUS_CANCELED,
                ]
            ),
        )
        .group_by(ReferralInviteRelation.invite_code)
        .all()
    )
    return {invite_code: int(count or 0) for invite_code, count in rows}


def _serialize_invitation(
    invitation: ReferralInviteCode,
    *,
    users: dict[str, dict[str, str]],
    event_stats: dict[str, Any],
    relation_count: int,
) -> dict[str, Any]:
    event_counts = {
        event_type: 0
        for event_type in (
            REFERRAL_INVITE_EVENT_LINK_CLICKED,
            REFERRAL_INVITE_EVENT_REGISTRATION_PAGE_VIEWED,
            REFERRAL_INVITE_EVENT_CODE_ENTERED,
            REFERRAL_INVITE_EVENT_REGISTRATION_SUBMITTED,
        )
    }
    event_counts.update(event_stats.get("event_counts") or {})
    return {
        "invite_code_bid": invitation.invite_code_bid,
        "campaign_bid": invitation.campaign_bid,
        "invite_code": invitation.invite_code,
        "inviter_user_bid": invitation.inviter_user_bid,
        "inviter": users.get(invitation.inviter_user_bid, {}),
        "status": int(invitation.status or 0),
        "generated_at": _serialize_dt(invitation.generated_at),
        "event_counts": event_counts,
        "link_clicked_count": event_counts[REFERRAL_INVITE_EVENT_LINK_CLICKED],
        "registration_page_viewed_count": event_counts[
            REFERRAL_INVITE_EVENT_REGISTRATION_PAGE_VIEWED
        ],
        "code_entered_count": event_counts[REFERRAL_INVITE_EVENT_CODE_ENTERED],
        "registration_submitted_count": event_counts[
            REFERRAL_INVITE_EVENT_REGISTRATION_SUBMITTED
        ],
        "total_event_count": int(event_stats.get("total_event_count") or 0),
        "successful_relation_count": relation_count,
        "latest_event_at": _serialize_dt(event_stats.get("latest_event_at")),
    }
