"""Terminate a paid subscription immediately from operator workflows."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.datetime import NAIVE_DATETIME_MIN, now_utc
from flaskr.util.uuid import generate_id
from sqlalchemy import case, or_

from .consts import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_MANUAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_TERMINATING,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from .models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .preorders import load_active_preorder_order
from .renewal_event_transitions import cancel_subscription_renewal_events
from .wallets import (
    load_primary_credit_bucket_by_category,
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from flask import Flask

_PAID_PLAN_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
}
_MANUAL_PLAN_ORDER_TYPES = _PAID_PLAN_ORDER_TYPES | {BILLING_ORDER_TYPE_MANUAL}
_LOCAL_PREPAID_PROVIDERS = {"pingxx", "alipay", "wechatpay"}
_OPERATION_METADATA_KEY = "operator_paid_subscription_termination"


def _credit_to_string(value: object) -> str:
    normalized = Decimal(str(value or 0)).normalize()
    return format(normalized, "f")


def _metadata(subscription: BillingSubscription) -> dict[str, Any]:
    return (
        dict(subscription.metadata_json)
        if isinstance(subscription.metadata_json, dict)
        else {}
    )


def is_operator_terminable_plan_order(order: BillingOrder) -> bool:
    """Return whether an order proves a paid or operator-granted plan."""
    provider_name = str(order.payment_provider or "").strip().lower()
    if provider_name != "manual":
        return int(order.order_type or 0) in _PAID_PLAN_ORDER_TYPES
    if int(order.order_type or 0) not in _MANUAL_PLAN_ORDER_TYPES:
        return False
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    if metadata.get("referral_invitation_reward") is True:
        return False
    checkout_type = str(metadata.get("checkout_type") or "").strip().lower()
    return checkout_type not in {"referral_invitation_reward", "trial_bootstrap"}


def load_operator_termination_subscription_bid_map(
    creator_bids: Sequence[str],
    *,
    as_of: datetime,
) -> dict[str, str]:
    """Resolve the subscription that an operator termination would affect."""
    normalized_creator_bids = [
        str(creator_bid or "").strip()
        for creator_bid in creator_bids
        if str(creator_bid or "").strip()
    ]
    if not normalized_creator_bids:
        return {}

    product_sort_order = case(
        (BillingProduct.sort_order.is_(None), -1),
        else_=BillingProduct.sort_order,
    )
    active_rows = (
        db.session.query(
            BillingSubscription.creator_bid,
            BillingSubscription.subscription_bid,
            BillingSubscription.current_period_end_at,
            product_sort_order.label("product_sort_order"),
            BillingSubscription.created_at,
            BillingSubscription.id,
        )
        .outerjoin(
            BillingProduct,
            (BillingProduct.product_bid == BillingSubscription.product_bid)
            & (BillingProduct.deleted == 0),
        )
        .filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid.in_(normalized_creator_bids),
            BillingSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            or_(
                BillingSubscription.current_period_start_at.is_(None),
                BillingSubscription.current_period_start_at <= as_of,
            ),
            BillingSubscription.current_period_end_at.isnot(None),
            BillingSubscription.current_period_end_at > as_of,
        )
        .all()
    )
    best_active: dict[str, tuple[tuple, str]] = {}
    active_subscription_bids: set[str] = set()
    for row in active_rows:
        active_subscription_bids.add(str(row.subscription_bid or "").strip())
        sort_key = (
            row.product_sort_order if row.product_sort_order is not None else -1,
            row.current_period_end_at,
            row.created_at or NAIVE_DATETIME_MIN,
            row.id,
        )
        current = best_active.get(row.creator_bid)
        if current is None or sort_key > current[0]:
            best_active[row.creator_bid] = (sort_key, row.subscription_bid)

    selected = {
        creator_bid: subscription_bid
        for creator_bid, (_, subscription_bid) in best_active.items()
    }

    if active_subscription_bids:
        credit_backed_rows = (
            db.session.query(
                BillingOrder,
                CreditLedgerEntry.created_at.label("grant_created_at"),
                CreditLedgerEntry.id.label("grant_id"),
            )
            .join(
                CreditLedgerEntry,
                (CreditLedgerEntry.source_bid == BillingOrder.bill_order_bid)
                & (CreditLedgerEntry.deleted == 0)
                & (CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT)
                & (CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION)
                & (CreditLedgerEntry.amount > 0),
            )
            .join(
                CreditWalletBucket,
                (
                    CreditWalletBucket.wallet_bucket_bid
                    == CreditLedgerEntry.wallet_bucket_bid
                )
                & (CreditWalletBucket.deleted == 0)
                & (
                    CreditWalletBucket.bucket_category
                    == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
                )
                & (CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE)
                & (CreditWalletBucket.available_credits > 0),
            )
            .filter(
                BillingOrder.deleted == 0,
                BillingOrder.creator_bid.in_(normalized_creator_bids),
                BillingOrder.subscription_bid.in_(active_subscription_bids),
                BillingOrder.status == BILLING_ORDER_STATUS_PAID,
                BillingOrder.order_type.in_(_MANUAL_PLAN_ORDER_TYPES),
                or_(
                    CreditLedgerEntry.consumable_from.is_(None),
                    CreditLedgerEntry.consumable_from <= as_of,
                ),
                or_(
                    CreditLedgerEntry.expires_at.is_(None),
                    CreditLedgerEntry.expires_at > as_of,
                ),
            )
            .order_by(
                BillingOrder.creator_bid.asc(),
                CreditLedgerEntry.created_at.desc(),
                CreditLedgerEntry.id.desc(),
            )
            .all()
        )
        seen_credit_backed: set[str] = set()
        for order, _grant_created_at, _grant_id in credit_backed_rows:
            creator_bid = str(order.creator_bid or "").strip()
            if creator_bid in seen_credit_backed:
                continue
            if is_operator_terminable_plan_order(order):
                selected[creator_bid] = str(order.subscription_bid or "").strip()
                seen_credit_backed.add(creator_bid)

    pending_rows = (
        db.session.query(
            BillingSubscription.creator_bid,
            BillingSubscription.subscription_bid,
        )
        .filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid.in_(normalized_creator_bids),
            BillingSubscription.status == BILLING_SUBSCRIPTION_STATUS_TERMINATING,
        )
        .order_by(BillingSubscription.creator_bid.asc(), BillingSubscription.id.desc())
        .all()
    )
    seen_pending: set[str] = set()
    for creator_bid, subscription_bid in pending_rows:
        if creator_bid not in seen_pending:
            selected[creator_bid] = subscription_bid
            seen_pending.add(creator_bid)
    return selected


def _load_replay_subscription(
    creator_bid: str, request_id: str
) -> BillingSubscription | None:
    rows = (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
        )
        .order_by(BillingSubscription.id.desc())
        .all()
    )
    for row in rows:
        operation = _metadata(row).get(_OPERATION_METADATA_KEY)
        if isinstance(operation, dict) and operation.get("request_id") == request_id:
            return row
    return None


def _load_pending_subscription(creator_bid: str) -> BillingSubscription | None:
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
            BillingSubscription.status == BILLING_SUBSCRIPTION_STATUS_TERMINATING,
        )
        .order_by(BillingSubscription.id.desc())
        .first()
    )


def _load_paid_orders(subscription: BillingSubscription) -> list[BillingOrder]:
    rows = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == subscription.creator_bid,
            BillingOrder.subscription_bid == subscription.subscription_bid,
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
            BillingOrder.order_type.in_(_MANUAL_PLAN_ORDER_TYPES),
        )
        .order_by(BillingOrder.id.asc())
        .with_for_update()
        .all()
    )
    return [row for row in rows if is_operator_terminable_plan_order(row)]


def _load_forfeitable_bucket(
    creator_bid: str,
) -> tuple[CreditWalletBucket | None, Decimal]:
    bucket = load_primary_credit_bucket_by_category(
        creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    )
    if bucket is None:
        return None, Decimal(0)
    bucket = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.id == bucket.id,
        )
        .with_for_update()
        .one()
    )
    # Reserved balance can belong to an in-flight usage hold or a future reward.
    # Until deferred rewards can be moved to an independent bucket, do not
    # terminate a plan whose shared subscription bucket contains any hold.
    if Decimal(str(bucket.reserved_credits or 0)) > 0:
        raise_error("server.billing.creditDeductionOriginAmbiguous")
    forfeitable = Decimal(str(bucket.available_credits or 0))
    return bucket, forfeitable


def terminate_operator_paid_subscription(
    app: Flask,
    *,
    creator_bid: str,
    operator_user_bid: str,
    request_id: str,
    reason: str,
) -> dict[str, object]:
    """Immediately terminate the current paid plan and its active plan bucket."""
    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_operator_bid = str(operator_user_bid or "").strip()
    normalized_request_id = str(request_id or "").strip()
    normalized_reason = str(reason or "").strip()
    if not normalized_creator_bid:
        raise_param_error("user_bid")
    if not normalized_operator_bid:
        raise_param_error("operator_user_bid")
    if not normalized_request_id:
        raise_param_error("request_id")
    if not normalized_reason or len(normalized_reason) > 255:
        raise_param_error("reason")

    with app_context_scope(app):
        with unit_of_work():
            subscription = _load_replay_subscription(
                normalized_creator_bid, normalized_request_id
            )
            if subscription is not None:
                db.session.refresh(subscription, with_for_update=True)
                operation = _metadata(subscription).get(_OPERATION_METADATA_KEY, {})
                if (
                    subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
                    and isinstance(operation, dict)
                    and operation.get("status") == "terminated"
                ):
                    return {
                        "status": "terminated",
                        "user_bid": normalized_creator_bid,
                        "subscription_bid": subscription.subscription_bid,
                        "provider": subscription.billing_provider,
                        "forfeited_credits": _credit_to_string(
                            operation.get("forfeited_credits") or "0"
                        ),
                        "replayed": True,
                    }
            else:
                subscription = _load_pending_subscription(normalized_creator_bid)
                if subscription is not None:
                    db.session.refresh(subscription, with_for_update=True)
                    pending_operation = _metadata(subscription).get(
                        _OPERATION_METADATA_KEY
                    )
                    if (
                        not isinstance(pending_operation, dict)
                        or not str(pending_operation.get("request_id") or "").strip()
                    ):
                        raise_error("server.order.orderStatusError")
                    normalized_request_id = str(pending_operation["request_id"]).strip()
                    normalized_operator_bid = str(
                        pending_operation.get("operator_user_bid")
                        or normalized_operator_bid
                    ).strip()
                    normalized_reason = str(
                        pending_operation.get("reason") or normalized_reason
                    ).strip()
                else:
                    target_bid = load_operator_termination_subscription_bid_map(
                        [normalized_creator_bid], as_of=now_utc()
                    ).get(normalized_creator_bid)
                    subscription = (
                        BillingSubscription.query.filter(
                            BillingSubscription.deleted == 0,
                            BillingSubscription.creator_bid == normalized_creator_bid,
                            BillingSubscription.subscription_bid == target_bid,
                        )
                        .with_for_update()
                        .first()
                        if target_bid
                        else None
                    )
                if subscription is None:
                    raise_error("server.order.orderStatusError")
                if subscription.status != BILLING_SUBSCRIPTION_STATUS_TERMINATING:
                    db.session.refresh(subscription, with_for_update=True)
                provider_name = str(subscription.billing_provider or "").strip().lower()
                if provider_name not in _LOCAL_PREPAID_PROVIDERS | {
                    "manual",
                    "stripe",
                }:
                    raise_error("server.order.orderStatusError")
                if (
                    provider_name == "stripe"
                    and not str(subscription.provider_subscription_id or "").strip()
                ):
                    raise_error("server.order.orderStatusError")
                if (
                    load_active_preorder_order(subscription.subscription_bid)
                    is not None
                ):
                    raise_error("server.order.orderStatusError")
                paid_orders = _load_paid_orders(subscription)
                if not paid_orders:
                    raise_error("server.order.orderStatusError")
                bucket, _ = _load_forfeitable_bucket(subscription.creator_bid)
                if subscription.status != BILLING_SUBSCRIPTION_STATUS_TERMINATING:
                    prepared_at = now_utc()
                    metadata = _metadata(subscription)
                    metadata[_OPERATION_METADATA_KEY] = {
                        "request_id": normalized_request_id,
                        "status": "prepared",
                        "operator_user_bid": normalized_operator_bid,
                        "reason": normalized_reason,
                        "previous_status": int(subscription.status or 0),
                        "prepared_at": prepared_at.isoformat(),
                        "paid_order_bids": [row.bill_order_bid for row in paid_orders],
                        "bucket_bid": bucket.wallet_bucket_bid if bucket else "",
                        "bucket_updated_at": (
                            bucket.updated_at.isoformat()
                            if bucket is not None and bucket.updated_at is not None
                            else ""
                        ),
                    }
                    subscription.metadata_json = metadata
                    subscription.status = BILLING_SUBSCRIPTION_STATUS_TERMINATING
                    subscription.cancel_at_period_end = 1
                    subscription.updated_at = prepared_at
                    cancel_subscription_renewal_events(subscription.subscription_bid)
                    db.session.add(subscription)

            subscription_bid = subscription.subscription_bid
            provider_name = str(subscription.billing_provider or "").strip().lower()
            provider_subscription_id = str(
                subscription.provider_subscription_id or ""
            ).strip()

        provider_payload: dict[str, object] = {}
        if provider_name == "stripe":
            # Import the stable provider boundary only when provider I/O is needed.
            # Importing it while billing.api is initializing creates a cycle through
            # order -> learn -> tts -> billing.api.
            from flaskr.service.order.api import get_payment_provider

            if not provider_subscription_id:
                raise_error("server.order.orderStatusError")
            provider_result = get_payment_provider("stripe").terminate_subscription(
                subscription_bid=subscription_bid,
                provider_subscription_id=provider_subscription_id,
                app=app,
            )
            if str(provider_result.status or "").strip().lower() != "canceled":
                raise_error("server.order.orderStatusError")
            provider_payload = provider_result.raw_response

        with unit_of_work():
            subscription = (
                BillingSubscription.query.filter(
                    BillingSubscription.deleted == 0,
                    BillingSubscription.subscription_bid == subscription_bid,
                    BillingSubscription.creator_bid == normalized_creator_bid,
                )
                .with_for_update()
                .one()
            )
            operation = _metadata(subscription).get(_OPERATION_METADATA_KEY)
            if (
                not isinstance(operation, dict)
                or operation.get("request_id") != normalized_request_id
            ):
                raise_error("server.order.orderStatusError")

            paid_orders = _load_paid_orders(subscription)
            if [row.bill_order_bid for row in paid_orders] != list(
                operation.get("paid_order_bids") or []
            ):
                raise_error("server.order.orderStatusError")

            bucket, forfeited = _load_forfeitable_bucket(subscription.creator_bid)
            if (bucket.wallet_bucket_bid if bucket else "") != str(
                operation.get("bucket_bid") or ""
            ) or (
                bucket is not None
                and bucket.updated_at is not None
                and bucket.updated_at.isoformat()
                != str(operation.get("bucket_updated_at") or "")
            ):
                operation["bucket_bid"] = bucket.wallet_bucket_bid if bucket else ""
                operation["bucket_updated_at"] = (
                    bucket.updated_at.isoformat()
                    if bucket is not None and bucket.updated_at is not None
                    else ""
                )
                metadata = _metadata(subscription)
                metadata[_OPERATION_METADATA_KEY] = operation
                subscription.metadata_json = metadata
            terminated_at = now_utc()
            wallet = (
                CreditWallet.query.filter(
                    CreditWallet.deleted == 0,
                    CreditWallet.creator_bid == normalized_creator_bid,
                )
                .with_for_update()
                .first()
            )
            ledger_bid = ""
            ledger_entry: CreditLedgerEntry | None = None
            if bucket is not None and forfeited > 0:
                bucket.available_credits = Decimal(0)
                bucket.reserved_credits = Decimal(0)
                bucket.expired_credits = (
                    Decimal(str(bucket.expired_credits or 0)) + forfeited
                )
                bucket.effective_to = terminated_at
                bucket.metadata_json = {
                    **(
                        bucket.metadata_json
                        if isinstance(bucket.metadata_json, dict)
                        else {}
                    ),
                    "operator_terminated_subscription_bid": subscription.subscription_bid,
                }
                sync_credit_bucket_status(bucket)
                ledger_bid = generate_id(app)
                ledger_entry = CreditLedgerEntry(
                    ledger_bid=ledger_bid,
                    creator_bid=normalized_creator_bid,
                    wallet_bid=bucket.wallet_bid,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid=subscription.subscription_bid,
                    idempotency_key=(
                        f"operator_subscription_termination:{normalized_request_id}"
                    ),
                    amount=-forfeited,
                    balance_after=Decimal(0),
                    expires_at=terminated_at,
                    consumable_from=bucket.effective_from,
                    metadata_json={
                        "operation": "operator_subscription_termination",
                        "operator_user_bid": normalized_operator_bid,
                        "reason": normalized_reason,
                    },
                )
                db.session.add(ledger_entry)
            subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
            subscription.cancel_at_period_end = 1
            subscription.current_period_end_at = terminated_at
            subscription.grace_period_end_at = None
            subscription.next_product_bid = ""
            metadata = _metadata(subscription)
            operation = dict(metadata.get(_OPERATION_METADATA_KEY) or {})
            operation.update(
                {
                    "status": "terminated",
                    "terminated_at": terminated_at.isoformat(),
                    "forfeited_credits": _credit_to_string(forfeited),
                    "ledger_bid": ledger_bid,
                    "provider_payload": provider_payload,
                }
            )
            metadata[_OPERATION_METADATA_KEY] = operation
            subscription.metadata_json = metadata
            subscription.updated_at = terminated_at
            cancel_subscription_renewal_events(subscription.subscription_bid)
            db.session.add(subscription)
            if wallet is not None:
                refresh_credit_wallet_snapshot(wallet, snapshot_at=terminated_at)
                if ledger_entry is not None:
                    ledger_entry.balance_after = wallet.available_credits
                persist_credit_wallet_snapshot(
                    wallet,
                    available_credits=wallet.available_credits,
                    reserved_credits=wallet.reserved_credits,
                    updated_at=terminated_at,
                )
            return {
                "status": "terminated",
                "user_bid": normalized_creator_bid,
                "subscription_bid": subscription.subscription_bid,
                "provider": provider_name,
                "forfeited_credits": _credit_to_string(forfeited),
                "ledger_bid": ledger_bid,
                "replayed": False,
            }


__all__ = [
    "is_operator_terminable_plan_order",
    "terminate_operator_paid_subscription",
]
