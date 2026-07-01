"""Operator read models for referral invitation rewards."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.datetime import now_utc

from .consts import (
    REFERRAL_ABNORMAL_STATUS_CONFIRMED_ABNORMAL,
    REFERRAL_ABNORMAL_STATUS_NORMAL,
    REFERRAL_ABNORMAL_STATUS_REVIEWING,
    REFERRAL_RELATION_STATUS_ABNORMAL_REVIEWING,
    REFERRAL_RELATION_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_FROZEN,
)
from .models import ReferralCampaign, ReferralInviteRelation, ReferralInviteReward
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
        for field in (
            "campaign_bid",
            "inviter_user_bid",
            "invitee_user_bid",
            "invite_code",
        ):
            value = _normalize_text(filters.get(field))
            if value:
                query = query.filter(getattr(ReferralInviteRelation, field) == value)
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
