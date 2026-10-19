"""Subscription activation for paid orders and bucket transition expiry."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
)
from .cycle_state_transitions import (
    apply_paid_subscription_cycle_state as _apply_paid_subscription_cycle_state,
)
from .models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .payment_policy import is_manual_payment_provider
from .preorders import (
    PREORDER_STATE_PENDING_EFFECTIVE,
)
from .preorders import (
    clear_subscription_preorder_metadata as _clear_subscription_preorder_metadata,
)
from .preorders import (
    is_preorder_order as _is_preorder_order,
)
from .preorders import (
    mark_preorder_effective_applied as _mark_preorder_effective_applied,
)
from .preorders import (
    mark_subscription_preorder_pending as _mark_subscription_preorder_pending,
)
from .preorders import (
    preorder_state as _preorder_state,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .queries import (
    load_subscription_by_bid as _load_subscription_by_bid,
)
from .reserved_renewal_activation import (
    IncompleteReservedGrantActivationError,  # noqa: F401
    ReservedActivationTarget,
    validate_reserved_renewal_cycle_activation,  # noqa: F401
)
from .reserved_renewal_activation import (
    activate_reserved_renewal_grants_for_cycle as _activate_reserved_renewal_grants_for_cycle,
)
from .reserved_renewal_activation import (
    sync_activated_reserved_renewal_ledger_balances as _sync_activated_reserved_renewal_ledger_balances,
)
from .subscriptions_cycles import (
    _ensure_manual_renewal_applied_cycle,
    _is_stale_manual_cycle,
    _load_billing_product_by_bid,
    _load_or_create_credit_wallet,
    _resolve_credit_bucket_effective_from,
    _resolve_credit_bucket_effective_to,
    _should_defer_subscription_renewal_activation,
)
from .subscriptions_lifecycle import (
    _sync_subscription_lifecycle_events,
)
from .wallets import (
    refresh_credit_wallet_snapshot,
    resolve_bucket_source_type_for_category,
    sync_credit_bucket_status,
)

if TYPE_CHECKING:
    from types import ModuleType

    from flask import Flask


def _subscriptions_facade() -> ModuleType:
    """Resolve collaborators through ``subscriptions`` so its patch points stay live."""
    from . import subscriptions

    return subscriptions


def _activate_subscription_for_paid_order(
    app: Flask,
    order: BillingOrder,
    *,
    subscription: BillingSubscription | None = None,
    force: bool = False,
) -> bool:
    if not order.subscription_bid:
        return False

    if (
        _is_preorder_order(order)
        and _preorder_state(order) != PREORDER_STATE_PENDING_EFFECTIVE
    ):
        return False

    product = _load_billing_product_by_bid(order.product_bid)
    if product is None:
        return False
    _ensure_manual_renewal_applied_cycle(order, product)

    subscription = subscription or _load_subscription_by_bid(order.subscription_bid)
    if subscription is None:
        return False

    effective_from = _resolve_credit_bucket_effective_from(
        order=order,
        default_effective_from=order.paid_at or _subscriptions_facade().now_utc(),
    )
    effective_to = _resolve_credit_bucket_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
    )

    if (
        order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        and not force
        and _should_defer_subscription_renewal_activation(
            order,
            effective_from=effective_from,
        )
    ):
        if _is_preorder_order(order):
            _mark_subscription_preorder_pending(subscription, order)
        _sync_subscription_lifecycle_events(app, subscription)
        db.session.add(subscription)
        return False

    # A replay of an older paid order must not replace a newer effective cycle.
    if _is_stale_manual_cycle(order, subscription, effective_from):
        return False

    activated_reserved_targets: tuple[ReservedActivationTarget, ...] = ()
    if order.order_type in {
        BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
        BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    }:
        if order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
            activated_reserved_targets = _activate_reserved_renewal_grants_for_cycle(
                app,
                order=order,
                effective_from=effective_from,
                effective_to=effective_to,
                expire_bucket_balance_for_transition=(
                    _expire_credit_bucket_balance_for_transition
                ),
            )
        _apply_paid_subscription_cycle_state(
            subscription,
            creator_bid=order.creator_bid,
            order_type=order.order_type,
            order_product_bid=order.product_bid,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        if is_manual_payment_provider(order.payment_provider):
            subscription.billing_provider = _normalize_bid(
                order.payment_provider
            ).lower()
            order_metadata = (
                order.metadata_json if isinstance(order.metadata_json, dict) else {}
            )
            subscription.metadata_json = {
                **(
                    subscription.metadata_json
                    if isinstance(subscription.metadata_json, dict)
                    else {}
                ),
                **{
                    key: order_metadata[key]
                    for key in (
                        "provider",
                        "latest_source",
                        "latest_event_type",
                        "latest_event_time",
                        "latest_provider_payload",
                    )
                    if key in order_metadata
                },
                "active_cycle_order_bid": order.bill_order_bid,
            }
        else:
            # A provider-managed paid cycle supersedes the manual repair marker.
            metadata = (
                dict(subscription.metadata_json)
                if isinstance(subscription.metadata_json, dict)
                else {}
            )
            metadata.pop("active_cycle_order_bid", None)
            subscription.metadata_json = metadata
        if order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
            wallet = _load_or_create_credit_wallet(app, order.creator_bid)
            refresh_credit_wallet_snapshot(wallet, snapshot_at=effective_from)
            _subscriptions_facade().persist_credit_wallet_snapshot(
                wallet,
                available_credits=wallet.available_credits,
                reserved_credits=wallet.reserved_credits,
                updated_at=_subscriptions_facade().now_utc(),
            )
            _sync_activated_reserved_renewal_ledger_balances(
                targets=activated_reserved_targets,
                final_balance_after=wallet.available_credits,
            )
        if _is_preorder_order(order):
            _mark_preorder_effective_applied(order)
            _clear_subscription_preorder_metadata(subscription)
            db.session.add(order)
    else:
        subscription.current_period_start_at = (
            subscription.current_period_start_at or effective_from
        )
        subscription.current_period_end_at = (
            subscription.current_period_end_at or effective_to
        )

    subscription.updated_at = _subscriptions_facade().now_utc()
    _sync_subscription_lifecycle_events(app, subscription)
    db.session.add(subscription)
    return True


def _expire_credit_bucket_balance_for_transition(
    app: Flask,
    *,
    wallet: CreditWallet,
    bucket: CreditWalletBucket,
    order: BillingOrder,
    transition_at: datetime,
) -> Decimal:
    available = _to_decimal(bucket.available_credits)
    if available <= 0:
        return Decimal(0)

    idempotency_key = f"cycle_expire:{order.bill_order_bid}"
    existing_entry = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if existing_entry is not None:
        return Decimal(0)

    previous_effective_to = bucket.effective_to
    bucket.available_credits = Decimal(0)
    bucket.expired_credits = _quantize_credit_amount(
        _to_decimal(bucket.expired_credits) + available
    )
    sync_credit_bucket_status(bucket)
    db.session.add(bucket)

    refresh_credit_wallet_snapshot(
        wallet,
        snapshot_at=transition_at - timedelta(microseconds=1),
    )
    ledger_entry = CreditLedgerEntry(
        ledger_bid=generate_id(app),
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        source_type=resolve_bucket_source_type_for_category(bucket.bucket_category),
        source_bid=order.bill_order_bid,
        idempotency_key=idempotency_key,
        amount=-available,
        balance_after=_quantize_credit_amount(wallet.available_credits),
        expires_at=previous_effective_to,
        consumable_from=bucket.effective_from,
        metadata_json={
            "expired_bucket_bid": bucket.wallet_bucket_bid,
            "transition_order_bid": order.bill_order_bid,
            "transition_at": transition_at.isoformat(),
            "reason": "subscription_cycle_transition",
        },
    )
    db.session.add(ledger_entry)
    return available
