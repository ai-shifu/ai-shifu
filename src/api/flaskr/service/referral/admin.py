"""Operator read models for referral invitation rewards."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.billing.consts import CREDIT_LEDGER_ENTRY_TYPE_GRANT
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.user.models import UserInfo as UserEntity

from .consts import (
    REFERRAL_ABNORMAL_STATUS_CONFIRMED_ABNORMAL,
    REFERRAL_ABNORMAL_STATUS_NORMAL,
    REFERRAL_ABNORMAL_STATUS_REVIEWING,
    REFERRAL_RELATION_STATUS_ABNORMAL_REVIEWING,
    REFERRAL_RELATION_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_FROZEN,
    REFERRAL_REWARD_STATUS_SKIPPED_CAP,
)
from .models import ReferralCampaign, ReferralInviteRelation, ReferralInviteReward

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

REWARD_QUEUE_EXCLUDED_STATUSES = {
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_SKIPPED_CAP,
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
    return value.isoformat() if value is not None else None


def _serialize_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _normalize_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_metadata_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    normalized = _normalize_text(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _billing_artifact_bid(reward: ReferralInviteReward, key: str) -> str:
    return _normalize_text(_normalize_dict(reward.billing_artifacts).get(key))


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


def _reward_queue_relations_map(
    relation_bids: set[str],
) -> dict[str, ReferralInviteRelation]:
    if not relation_bids:
        return {}
    rows = ReferralInviteRelation.query.filter(
        ReferralInviteRelation.deleted == 0,
        ReferralInviteRelation.relation_bid.in_(sorted(relation_bids)),
    ).all()
    return {row.relation_bid: row for row in rows}


def _reward_queue_order_map(order_bids: set[str]) -> dict[str, BillingOrder]:
    if not order_bids:
        return {}
    rows = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.bill_order_bid.in_(sorted(order_bids)),
    ).all()
    return {row.bill_order_bid: row for row in rows}


def _reward_queue_ledger_map(order_bids: set[str]) -> dict[str, CreditLedgerEntry]:
    if not order_bids:
        return {}
    rows = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.source_bid.in_(sorted(order_bids)),
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        )
        .order_by(CreditLedgerEntry.source_bid.asc(), CreditLedgerEntry.id.desc())
        .all()
    )
    result: dict[str, CreditLedgerEntry] = {}
    for row in rows:
        result.setdefault(row.source_bid, row)
    return result


def _reward_queue_bucket_map(order_bids: set[str]) -> dict[str, CreditWalletBucket]:
    if not order_bids:
        return {}
    rows = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.source_bid.in_(sorted(order_bids)),
        )
        .order_by(CreditWalletBucket.source_bid.asc(), CreditWalletBucket.id.desc())
        .all()
    )
    result: dict[str, CreditWalletBucket] = {}
    for row in rows:
        result.setdefault(row.source_bid, row)
    return result


def _reward_order_cycle_datetime(
    order: BillingOrder | None,
    key: str,
) -> datetime | None:
    if order is None:
        return None
    return _parse_metadata_datetime(_normalize_dict(order.metadata_json).get(key))


def _reward_queue_effective_at(
    reward: ReferralInviteReward,
    order: BillingOrder | None,
    ledger: CreditLedgerEntry | None,
) -> datetime | None:
    return (
        reward.effective_at
        or _reward_order_cycle_datetime(order, "renewal_cycle_start_at")
        or _reward_order_cycle_datetime(order, "applied_cycle_start_at")
        or (ledger.consumable_from if ledger is not None else None)
    )


def _reward_queue_expires_at(
    reward: ReferralInviteReward,
    order: BillingOrder | None,
    ledger: CreditLedgerEntry | None,
) -> datetime | None:
    return (
        reward.expires_at
        or _reward_order_cycle_datetime(order, "renewal_cycle_end_at")
        or _reward_order_cycle_datetime(order, "applied_cycle_end_at")
        or (ledger.expires_at if ledger is not None else None)
    )


def _ledger_credit_state(
    ledger: CreditLedgerEntry | None,
    bucket: CreditWalletBucket | None,
) -> str:
    if ledger is not None:
        state = _normalize_text(
            _normalize_dict(ledger.metadata_json).get("bucket_credit_state")
        )
        if state:
            return state
    if bucket is not None:
        if Decimal(str(bucket.reserved_credits or 0)) > 0:
            return "reserved"
        if Decimal(str(bucket.available_credits or 0)) > 0:
            return "available"
    return ""


def _serialize_reward_queue_item(
    reward: ReferralInviteReward,
    *,
    queue_index: int,
    relation: ReferralInviteRelation | None,
    order: BillingOrder | None,
    ledger: CreditLedgerEntry | None,
    bucket: CreditWalletBucket | None,
) -> dict[str, Any]:
    bill_order_bid = _billing_artifact_bid(reward, "bill_order_bid")
    if not bill_order_bid and order is not None:
        bill_order_bid = _normalize_text(order.bill_order_bid)
    subscription_bid = _billing_artifact_bid(reward, "billing_subscription_bid")
    if not subscription_bid and order is not None:
        subscription_bid = _normalize_text(order.subscription_bid)
    wallet_bucket_bid = _billing_artifact_bid(reward, "wallet_bucket_bid")
    if not wallet_bucket_bid and bucket is not None:
        wallet_bucket_bid = _normalize_text(bucket.wallet_bucket_bid)
    ledger_bid = _billing_artifact_bid(reward, "ledger_bid")
    if not ledger_bid and ledger is not None:
        ledger_bid = _normalize_text(ledger.ledger_bid)
    effective_at = _reward_queue_effective_at(reward, order, ledger)
    expires_at = _reward_queue_expires_at(reward, order, ledger)

    return {
        "queue_index": queue_index,
        "reward_bid": reward.reward_bid,
        "relation_bid": reward.relation_bid,
        "invitee_user_bid": reward.invitee_user_bid,
        "invitee_mobile_snapshot": (
            relation.invitee_mobile_snapshot if relation is not None else ""
        ),
        "reward_status": reward.reward_status,
        "reward_credit_amount": _serialize_decimal(reward.reward_credit_amount),
        "reward_product_code": reward.reward_product_code,
        "bill_order_bid": bill_order_bid,
        "subscription_bid": subscription_bid,
        "wallet_bucket_bid": wallet_bucket_bid,
        "ledger_bid": ledger_bid,
        "ledger_credit_state": _ledger_credit_state(ledger, bucket),
        "effective_at": _serialize_dt(effective_at),
        "expires_at": _serialize_dt(expires_at),
        "created_at": _serialize_dt(reward.created_at),
    }


def _build_reward_queue(inviter_user_bid: str) -> list[dict[str, Any]]:
    normalized_inviter = _normalize_text(inviter_user_bid)
    if not normalized_inviter:
        return []
    rewards = (
        ReferralInviteReward.query.filter(
            ReferralInviteReward.deleted == 0,
            ReferralInviteReward.inviter_user_bid == normalized_inviter,
            ReferralInviteReward.reward_status.notin_(REWARD_QUEUE_EXCLUDED_STATUSES),
        )
        .order_by(ReferralInviteReward.created_at.asc(), ReferralInviteReward.id.asc())
        .all()
    )
    relation_bids = {_normalize_text(reward.relation_bid) for reward in rewards}
    order_bids = {
        _billing_artifact_bid(reward, "bill_order_bid")
        for reward in rewards
        if _billing_artifact_bid(reward, "bill_order_bid")
    }
    relations = _reward_queue_relations_map(relation_bids)
    orders = _reward_queue_order_map(order_bids)
    ledgers = _reward_queue_ledger_map(order_bids)
    buckets = _reward_queue_bucket_map(order_bids)

    def sort_key(reward: ReferralInviteReward) -> tuple[datetime, datetime, int]:
        order_bid = _billing_artifact_bid(reward, "bill_order_bid")
        ledger = ledgers.get(order_bid)
        effective_at = _reward_queue_effective_at(
            reward,
            orders.get(order_bid),
            ledger,
        )
        return (
            effective_at or datetime.max,
            reward.created_at or datetime.max,
            int(reward.id or 0),
        )

    sorted_rewards = sorted(rewards, key=sort_key)
    return [
        _serialize_reward_queue_item(
            reward,
            queue_index=index,
            relation=relations.get(reward.relation_bid),
            order=orders.get(_billing_artifact_bid(reward, "bill_order_bid")),
            ledger=ledgers.get(_billing_artifact_bid(reward, "bill_order_bid")),
            bucket=buckets.get(_billing_artifact_bid(reward, "bill_order_bid")),
        )
        for index, reward in enumerate(sorted_rewards, start=1)
    ]


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
        payload["reward_queue"] = _build_reward_queue(relation.inviter_user_bid)
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
            metadata["operator_updated_at"] = datetime.now().isoformat()
            relation.metadata_json = metadata
            if reward is not None:
                reward.operator_note = note

        db.session.add(relation)
        if reward is not None:
            db.session.add(reward)
        db.session.commit()
        return get_operator_referral_detail(app, relation_bid=relation.relation_bid)
