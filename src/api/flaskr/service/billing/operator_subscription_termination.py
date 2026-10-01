"""Terminate a paid subscription immediately from operator workflows."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.api import get_payment_provider
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_TERMINATING,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_HOLD,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from .models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .queries import load_primary_active_subscription
from .renewal_event_transitions import cancel_subscription_renewal_events
from .wallets import (
    load_primary_credit_bucket_by_category,
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)

if TYPE_CHECKING:
    from flask import Flask

_PAID_PLAN_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
}
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
    return (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == subscription.creator_bid,
            BillingOrder.subscription_bid == subscription.subscription_bid,
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
            BillingOrder.order_type.in_(_PAID_PLAN_ORDER_TYPES),
            BillingOrder.payment_provider != "manual",
        )
        .order_by(BillingOrder.id.asc())
        .with_for_update()
        .all()
    )


def _load_forfeitable_bucket(
    subscription: BillingSubscription,
) -> tuple[CreditWalletBucket | None, Decimal]:
    bucket = load_primary_credit_bucket_by_category(
        subscription.creator_bid,
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
    reserved = Decimal(str(bucket.reserved_credits or 0))
    if reserved > 0:
        holds = (
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.creator_bid == subscription.creator_bid,
                CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_HOLD,
            )
            .with_for_update()
            .all()
        )
        for hold in holds:
            capture_prefix = f"operation_reservation:{hold.ledger_bid}:capture:"
            release_key = f"operation_reservation:{hold.ledger_bid}:release"
            terminal = (
                CreditLedgerEntry.query.filter(
                    CreditLedgerEntry.deleted == 0,
                    CreditLedgerEntry.creator_bid == subscription.creator_bid,
                    db.or_(
                        CreditLedgerEntry.idempotency_key.startswith(capture_prefix),
                        CreditLedgerEntry.idempotency_key == release_key,
                    ),
                )
                .with_for_update()
                .first()
            )
            if terminal is None:
                raise_error("server.billing.creditDeductionOriginAmbiguous")
    forfeitable = Decimal(str(bucket.available_credits or 0)) + reserved
    if forfeitable <= 0:
        return bucket, Decimal(0)

    grants = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CreditLedgerEntry.amount > 0,
        )
        .order_by(CreditLedgerEntry.id.asc())
        .with_for_update()
        .all()
    )
    if not grants:
        raise_error("server.billing.creditDeductionOriginAmbiguous")
    order_bids = {str(item.source_bid or "").strip() for item in grants}
    paid_orders = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.bill_order_bid.in_(order_bids),
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
            BillingOrder.order_type.in_(_PAID_PLAN_ORDER_TYPES),
            BillingOrder.payment_provider != "manual",
            BillingOrder.subscription_bid == subscription.subscription_bid,
        )
        .with_for_update()
        .all()
    )
    if len(paid_orders) != len(order_bids):
        raise_error("server.billing.creditDeductionOriginAmbiguous")
    return bucket, forfeitable


def terminate_operator_paid_subscription(
    app: Flask,
    *,
    creator_bid: str,
    operator_user_bid: str,
    request_id: str,
    reason: str,
) -> dict[str, object]:
    """Immediately terminate the current paid plan and its paid plan credits."""
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
                else:
                    subscription = load_primary_active_subscription(
                        normalized_creator_bid, as_of=now_utc()
                    )
                if subscription is None:
                    raise_error("server.order.orderStatusError")
                if subscription.status != BILLING_SUBSCRIPTION_STATUS_TERMINATING:
                    db.session.refresh(subscription, with_for_update=True)
                provider_name = str(subscription.billing_provider or "").strip().lower()
                if provider_name == "manual":
                    raise_error("server.order.orderStatusError")
                if provider_name not in _LOCAL_PREPAID_PROVIDERS | {"stripe"}:
                    raise_error("server.order.orderStatusError")
                if not _load_paid_orders(subscription):
                    raise_error("server.order.orderStatusError")
                _load_forfeitable_bucket(subscription)
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

            bucket, forfeited = _load_forfeitable_bucket(subscription)
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


__all__ = ["terminate_operator_paid_subscription"]
