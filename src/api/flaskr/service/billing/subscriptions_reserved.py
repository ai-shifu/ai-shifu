"""Voiding reserved grants and absorbing preorders replaced by upgrades."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
)
from .models import (
    BillingOrder,
    CreditWalletBucket,
)
from .preorders import (
    PREORDER_STATE_ABSORBED_BY_UPGRADE,
    PREORDER_STATE_PENDING_EFFECTIVE,
)
from .preorders import (
    clear_subscription_preorder_metadata as _clear_subscription_preorder_metadata,
)
from .preorders import (
    is_preorder_order as _is_preorder_order,
)
from .preorders import (
    mark_preorder_absorbed_by_upgrade as _mark_preorder_absorbed_by_upgrade,
)
from .preorders import (
    preorder_state as _preorder_state,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .queries import (
    load_subscription_by_bid as _load_subscription_by_bid,
)
from .reserved_renewal_activation import (
    IncompleteReservedGrantActivationError,  # noqa: F401
    validate_reserved_renewal_cycle_activation,  # noqa: F401
)
from .reserved_renewal_activation import (
    load_campaign_bonus_ledger_entry_for_order as _load_campaign_bonus_ledger_entry_for_order,
)
from .reserved_renewal_activation import (
    load_grant_ledger_entry_for_order as _load_grant_ledger_entry_for_order,
)
from .subscriptions_cycles import (
    _load_or_create_credit_wallet,
)
from .wallets import (
    load_primary_credit_bucket_by_category,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)

if TYPE_CHECKING:
    from types import ModuleType

    from flask import Flask


def _subscriptions_facade() -> ModuleType:
    """Resolve collaborators through ``subscriptions`` so its patch points stay live."""
    from . import subscriptions

    return subscriptions


def _void_reserved_subscription_grant_for_order(
    app: Flask,
    order: BillingOrder,
    *,
    absorbed_by_bill_order_bid: str,
) -> bool:
    grant_entry = _load_grant_ledger_entry_for_order(order)
    if grant_entry is None:
        return False

    metadata = _normalize_json_object(grant_entry.metadata_json)
    if str(metadata.get("bucket_credit_state") or "").strip().lower() != "reserved":
        return False

    bucket = None
    if _normalize_bid(grant_entry.wallet_bucket_bid):
        bucket = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.wallet_bucket_bid == grant_entry.wallet_bucket_bid,
            )
            .order_by(CreditWalletBucket.id.desc())
            .first()
        )
    if bucket is None:
        bucket = load_primary_credit_bucket_by_category(
            order.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        )
    if bucket is None:
        return False

    now = _subscriptions_facade().now_utc()
    release_amount = min(
        _to_decimal(grant_entry.amount),
        _to_decimal(bucket.reserved_credits),
    )
    if release_amount > 0:
        bucket.reserved_credits = _quantize_credit_amount(
            _to_decimal(bucket.reserved_credits) - release_amount
        )
        bucket.original_credits = _quantize_credit_amount(
            max(Decimal(0), _to_decimal(bucket.original_credits) - release_amount)
        )
        bucket.metadata_json = {
            **(bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}),
            "absorbed_preorder_order_bid": order.bill_order_bid,
            "absorbed_by_bill_order_bid": absorbed_by_bill_order_bid,
            "absorbed_at": now.isoformat(),
        }
        bucket.updated_at = now
        sync_credit_bucket_status(bucket)
        db.session.add(bucket)

    metadata["bucket_credit_state"] = "absorbed"
    metadata["absorbed_by_bill_order_bid"] = absorbed_by_bill_order_bid
    metadata["absorbed_at"] = now.isoformat()
    grant_entry.metadata_json = metadata.to_metadata_json()
    grant_entry.updated_at = now
    db.session.add(grant_entry)

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    refresh_credit_wallet_snapshot(wallet)
    _subscriptions_facade().persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        updated_at=now,
    )
    grant_entry.balance_after = _quantize_credit_amount(wallet.available_credits)
    return True


def _void_reserved_campaign_bonus_grant_for_order(
    app: Flask,
    order: BillingOrder,
    *,
    absorbed_by_bill_order_bid: str,
) -> bool:
    grant_entry = _load_campaign_bonus_ledger_entry_for_order(order)
    if grant_entry is None:
        return False

    metadata = _normalize_json_object(grant_entry.metadata_json)
    if str(metadata.get("bucket_credit_state") or "").strip().lower() != "reserved":
        return False
    if not _normalize_bid(grant_entry.wallet_bucket_bid):
        return False

    bucket = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.wallet_bucket_bid == grant_entry.wallet_bucket_bid,
        )
        .order_by(CreditWalletBucket.id.desc())
        .first()
    )
    if bucket is None:
        return False

    now = _subscriptions_facade().now_utc()
    release_amount = min(
        _to_decimal(grant_entry.amount),
        _to_decimal(bucket.reserved_credits),
    )
    if release_amount > 0:
        bucket.reserved_credits = _quantize_credit_amount(
            _to_decimal(bucket.reserved_credits) - release_amount
        )
        bucket.original_credits = _quantize_credit_amount(
            max(Decimal(0), _to_decimal(bucket.original_credits) - release_amount)
        )
        bucket.updated_at = now
        sync_credit_bucket_status(bucket)
        db.session.add(bucket)

    metadata["bucket_credit_state"] = "absorbed"
    metadata["absorbed_by_bill_order_bid"] = absorbed_by_bill_order_bid
    metadata["absorbed_at"] = now.isoformat()
    grant_entry.metadata_json = metadata.to_metadata_json()
    grant_entry.updated_at = now
    db.session.add(grant_entry)

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    refresh_credit_wallet_snapshot(wallet)
    _subscriptions_facade().persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        updated_at=now,
    )
    grant_entry.balance_after = _quantize_credit_amount(wallet.available_credits)
    return True


def _load_preorder_replaced_by_paid_upgrade(
    upgrade_order: BillingOrder,
) -> BillingOrder | None:
    if (
        int(upgrade_order.status or 0) != BILLING_ORDER_STATUS_PAID
        or int(upgrade_order.order_type or 0) != BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
    ):
        return None

    metadata = (
        upgrade_order.metadata_json
        if isinstance(upgrade_order.metadata_json, dict)
        else {}
    )
    preorder_order_bid = _normalize_bid(metadata.get("preorder_order_bid"))
    if not preorder_order_bid:
        return None

    preorder_order = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == upgrade_order.creator_bid,
            BillingOrder.subscription_bid == upgrade_order.subscription_bid,
            BillingOrder.bill_order_bid == preorder_order_bid,
        )
        .order_by(BillingOrder.id.desc())
        .populate_existing()
        .with_for_update()
        .first()
    )
    if preorder_order is None or not _is_preorder_order(preorder_order):
        return None

    preorder_metadata = (
        preorder_order.metadata_json
        if isinstance(preorder_order.metadata_json, dict)
        else {}
    )
    absorbed_by = _normalize_bid(preorder_metadata.get("absorbed_by_bill_order_bid"))
    if absorbed_by and absorbed_by != upgrade_order.bill_order_bid:
        return None

    state = _preorder_state(preorder_order)
    if state not in {
        PREORDER_STATE_PENDING_EFFECTIVE,
        PREORDER_STATE_ABSORBED_BY_UPGRADE,
    }:
        return None
    if int(preorder_order.status or 0) != BILLING_ORDER_STATUS_PAID:
        return None
    return preorder_order


def _absorb_preorder_replaced_by_paid_upgrade(
    app: Flask,
    order: BillingOrder,
) -> bool:
    preorder_order = _load_preorder_replaced_by_paid_upgrade(order)
    if preorder_order is None:
        return False

    preorder_metadata = (
        preorder_order.metadata_json
        if isinstance(preorder_order.metadata_json, dict)
        else {}
    )
    already_absorbed_by_order = (
        _preorder_state(preorder_order) == PREORDER_STATE_ABSORBED_BY_UPGRADE
        and _normalize_bid(preorder_metadata.get("absorbed_by_bill_order_bid"))
        == order.bill_order_bid
    )
    if not already_absorbed_by_order:
        _mark_preorder_absorbed_by_upgrade(
            preorder_order,
            upgrade_order_bid=order.bill_order_bid,
        )
    _void_reserved_subscription_grant_for_order(
        app,
        preorder_order,
        absorbed_by_bill_order_bid=order.bill_order_bid,
    )
    _void_reserved_campaign_bonus_grant_for_order(
        app,
        preorder_order,
        absorbed_by_bill_order_bid=order.bill_order_bid,
    )

    subscription = _load_subscription_by_bid(order.subscription_bid)
    if subscription is not None:
        _clear_subscription_preorder_metadata(subscription)
        subscription.next_product_bid = ""
        subscription.updated_at = _subscriptions_facade().now_utc()
        db.session.add(subscription)
    db.session.add(preorder_order)
    return True
