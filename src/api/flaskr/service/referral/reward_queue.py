"""Referral reward queue read model helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flaskr.service.billing.consts import CREDIT_LEDGER_ENTRY_TYPE_GRANT
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWalletBucket,
)

from .consts import (
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_SKIPPED_CAP,
)
from .models import ReferralInviteRelation, ReferralInviteReward

REWARD_QUEUE_EXCLUDED_STATUSES = {
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_SKIPPED_CAP,
}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _serialize_dt(value: datetime | None) -> str | None:
    # Match the API fmt sink: stored values are UTC; treat naive as UTC and emit
    # ISO 8601 with a 'Z' suffix so the frontend can convert to the viewer's tz.
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
    include_billing_artifacts: bool,
    include_invitee_user_bid: bool,
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
    item: dict[str, Any] = {
        "queue_index": queue_index,
        "reward_bid": reward.reward_bid,
        "relation_bid": reward.relation_bid,
        "invitee_mobile_snapshot": (
            relation.invitee_mobile_snapshot if relation is not None else ""
        ),
        "reward_status": reward.reward_status,
        "reward_credit_amount": _serialize_decimal(reward.reward_credit_amount),
        "reward_product_code": reward.reward_product_code,
        "ledger_credit_state": _ledger_credit_state(ledger, bucket),
        "effective_at": _serialize_dt(effective_at),
        "expires_at": _serialize_dt(expires_at),
        "created_at": _serialize_dt(reward.created_at),
    }
    if include_invitee_user_bid:
        item["invitee_user_bid"] = reward.invitee_user_bid
    if include_billing_artifacts:
        item.update(
            {
                "bill_order_bid": bill_order_bid,
                "subscription_bid": subscription_bid,
                "wallet_bucket_bid": wallet_bucket_bid,
                "ledger_bid": ledger_bid,
            }
        )
    return item


def build_referral_reward_queue(
    inviter_user_bid: str,
    *,
    include_billing_artifacts: bool,
    include_invitee_user_bid: bool,
) -> list[dict[str, Any]]:
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
            include_billing_artifacts=include_billing_artifacts,
            include_invitee_user_bid=include_invitee_user_bid,
        )
        for index, reward in enumerate(sorted_rewards, start=1)
    ]
