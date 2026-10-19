"""Subscription cycle math, renewal deferral rules, and shared subscription lookups."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.util.datetime import NAIVE_DATETIME_MIN, to_utc_iso
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
)
from .cycle_transitions import (
    resolve_order_effective_from as _resolve_order_effective_from,
)
from .cycle_transitions import (
    resolve_order_effective_to as _resolve_order_effective_to,
)
from .models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditWallet,
)
from .payment_policy import MANUAL_PAYMENT_PROVIDERS, is_manual_payment_provider
from .preorders import (
    is_preorder_order as _is_preorder_order,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .queries import (
    calculate_billing_cycle_end as _calc_provider_cycle_end,
)
from .queries import (
    calculate_self_managed_billing_cycle_end as _calc_self_managed_cycle_end,
)
from .queries import (
    extract_order_metadata_datetime as _extract_order_metadata_datetime,
)
from .queries import (
    load_primary_active_subscription as _load_primary_active_subscription,
)
from .queries import (
    load_subscription_by_bid as _load_subscription_by_bid,
)
from .queries import (
    load_subscription_renewal_order_by_cycle as _load_subscription_renewal_order_by_cycle,
)
from .reserved_renewal_activation import (
    IncompleteReservedGrantActivationError,  # noqa: F401
    validate_reserved_renewal_cycle_activation,  # noqa: F401
)

if TYPE_CHECKING:
    from types import ModuleType

    from flask import Flask


def _subscriptions_facade() -> ModuleType:
    """Resolve collaborators through ``subscriptions`` so its patch points stay live."""
    from . import subscriptions

    return subscriptions


SELF_MANAGED_BILLING_PROVIDERS = {*MANUAL_PAYMENT_PROVIDERS, "manual"}


def is_self_managed_billing_provider(provider: str | None) -> bool:
    """Return whether self managed billing provider."""
    return _normalize_bid(provider).lower() in SELF_MANAGED_BILLING_PROVIDERS


def load_effective_topup_subscription(
    creator_bid: str,
    *,
    as_of: datetime | None = None,
) -> BillingSubscription | None:
    """Load effective topup subscription."""
    return _load_primary_active_subscription(creator_bid, as_of=as_of)


def _resolve_manual_renewal_scheduled_at(
    subscription: BillingSubscription,
) -> datetime | None:
    scheduled_at = subscription.current_period_end_at
    if scheduled_at is None:
        return None
    renewal_at = scheduled_at - timedelta(days=7)
    current_period_start_at = subscription.current_period_start_at
    if current_period_start_at is not None and current_period_start_at > renewal_at:
        return current_period_start_at
    return renewal_at


def _ensure_manual_renewal_applied_cycle(
    order: BillingOrder,
    product: BillingProduct,
) -> None:
    if (
        order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        or not is_manual_payment_provider(order.payment_provider)
        or order.paid_at is None
    ):
        return

    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    applied_cycle_start_at = _extract_order_metadata_datetime(
        metadata,
        "applied_cycle_start_at",
    )
    applied_cycle_end_at = _extract_order_metadata_datetime(
        metadata,
        "applied_cycle_end_at",
    )
    if applied_cycle_start_at is not None and applied_cycle_end_at is not None:
        return

    renewal_cycle_end_at = _extract_order_metadata_datetime(
        metadata,
        "renewal_cycle_end_at",
    )
    if renewal_cycle_end_at is None or order.paid_at < renewal_cycle_end_at:
        return

    shifted_cycle_start_at = order.paid_at
    shifted_cycle_end_at = _calculate_billing_cycle_end(
        product,
        cycle_start_at=shifted_cycle_start_at,
        payment_provider=order.payment_provider,
    )
    if shifted_cycle_end_at is None:
        return

    metadata.update(
        _normalize_json_object(
            {
                "applied_cycle_start_at": to_utc_iso(shifted_cycle_start_at),
                "applied_cycle_end_at": to_utc_iso(shifted_cycle_end_at),
            }
        )
    )
    order.metadata_json = metadata
    db.session.add(order)


def _calculate_billing_cycle_end(
    product: BillingProduct,
    *,
    cycle_start_at: datetime,
    payment_provider: str = "",
) -> datetime | None:
    provider = _normalize_bid(payment_provider)
    if is_self_managed_billing_provider(provider):
        return _calc_self_managed_cycle_end(
            product,
            cycle_start_at=cycle_start_at,
        )
    return _calc_provider_cycle_end(
        product,
        cycle_start_at=cycle_start_at,
    )


def _should_defer_manual_renewal_activation(order: BillingOrder) -> bool:
    if (
        order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        or not is_manual_payment_provider(order.payment_provider)
        or order.paid_at is None
    ):
        return False

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    if _extract_order_metadata_datetime(metadata, "applied_cycle_start_at") is not None:
        return False

    renewal_cycle_start_at = _extract_order_metadata_datetime(
        metadata,
        "renewal_cycle_start_at",
    )
    if renewal_cycle_start_at is None:
        return False
    return order.paid_at < renewal_cycle_start_at


def _is_referral_invitation_renewal(order: BillingOrder) -> bool:
    if order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        return False

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    checkout_type = str(metadata.get("checkout_type") or "").strip()
    return checkout_type == "referral_invitation_reward" or (
        metadata.get("referral_invitation_reward") is True
    )


def _is_deferred_compensation_bonus_renewal(order: BillingOrder) -> bool:
    if order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        return False

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    return str(metadata.get("checkout_type") or "").strip() == (
        "cache_overcharge_bonus_plan"
    )


def _is_paid_referral_invitation_renewal(order: BillingOrder) -> bool:
    return int(
        order.status or 0
    ) == BILLING_ORDER_STATUS_PAID and _is_referral_invitation_renewal(order)


def _should_defer_subscription_renewal_activation(
    order: BillingOrder,
    *,
    effective_from: datetime,
) -> bool:
    if (
        order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        or order.paid_at is None
    ):
        return False

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    if _extract_order_metadata_datetime(metadata, "applied_cycle_start_at") is not None:
        return False
    if effective_from <= _subscriptions_facade().now_utc():
        return False
    return (
        _should_defer_manual_renewal_activation(order)
        or _is_preorder_order(order)
        or _is_referral_invitation_renewal(order)
        or _is_deferred_compensation_bonus_renewal(order)
    )


def _has_paid_deferred_manual_renewal_at_boundary(
    subscription: BillingSubscription,
    *,
    boundary_at: datetime | None,
) -> bool:
    if boundary_at is None:
        return False
    order = _load_subscription_renewal_order_by_cycle(
        subscription.subscription_bid,
        cycle_start_at=boundary_at,
        statuses=(BILLING_ORDER_STATUS_PAID,),
    )
    if order is None:
        return False
    return _is_referral_invitation_renewal(
        order
    ) or _is_deferred_compensation_bonus_renewal(order)


def _is_same_product_preorder_renewal(order: BillingOrder) -> bool:
    if (
        order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        or not _is_preorder_order(order)
    ):
        return False

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    target_product_bid = _normalize_bid(
        metadata.get("target_product_bid")
        or metadata.get("preorder_target_product_bid")
        or metadata.get("product_bid")
        or order.product_bid,
    )
    current_product_bid = _normalize_bid(metadata.get("current_product_bid"))
    if not current_product_bid and order.subscription_bid:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            current_product_bid = _normalize_bid(subscription.product_bid)

    return bool(
        target_product_bid
        and current_product_bid
        and target_product_bid == current_product_bid
    )


def _is_stale_manual_cycle(
    order: BillingOrder,
    subscription: BillingSubscription,
    effective_from: datetime,
) -> bool:
    """Reject old payments while allowing repair of the current cycle order."""
    metadata = (
        subscription.metadata_json
        if isinstance(subscription.metadata_json, dict)
        else {}
    )
    # The order marker alone can survive a later provider-managed cycle.
    # Corroborate it with the provider and last activation timestamp so a
    # current-cycle replay can still repair a corrupted mutable period window.
    is_current_cycle_order = (
        metadata.get("active_cycle_order_bid") == order.bill_order_bid
        and _normalize_bid(subscription.billing_provider).lower()
        == _normalize_bid(order.payment_provider).lower()
        and subscription.last_renewed_at == effective_from
    )
    current_start = subscription.current_period_start_at
    if (
        not is_manual_payment_provider(order.payment_provider)
        or current_start is None
        or is_current_cycle_order
    ):
        return False
    if effective_from < current_start:
        return True
    if effective_from != current_start:
        return False
    # Stripe can take over without advancing the period boundary.
    if _normalize_bid(subscription.billing_provider).lower() == "stripe":
        return True

    active_order_bid = _normalize_bid(metadata.get("active_cycle_order_bid"))
    if not active_order_bid or active_order_bid == order.bill_order_bid:
        return False
    active_order = (
        BillingOrder.query.filter_by(
            bill_order_bid=active_order_bid,
            creator_bid=subscription.creator_bid,
            subscription_bid=subscription.subscription_bid,
            product_bid=subscription.product_bid,
            status=BILLING_ORDER_STATUS_PAID,
            deleted=0,
        )
        .populate_existing()
        .first()
    )
    if (
        active_order is None
        or _normalize_bid(active_order.payment_provider).lower()
        != _normalize_bid(subscription.billing_provider).lower()
        or _resolve_credit_bucket_effective_from(
            order=active_order,
            default_effective_from=active_order.paid_at
            or _subscriptions_facade().now_utc(),
        )
        != effective_from
    ):
        return False
    # Paid time orders same-boundary payments. Creation time and the database
    # row ID break ties without rejecting a legitimate later payment.
    return (
        active_order.paid_at or NAIVE_DATETIME_MIN,
        active_order.created_at or NAIVE_DATETIME_MIN,
        active_order.id or 0,
    ) > (
        order.paid_at or NAIVE_DATETIME_MIN,
        order.created_at or NAIVE_DATETIME_MIN,
        order.id or 0,
    )


def _should_reserve_subscription_renewal_grant(
    order: BillingOrder,
    *,
    effective_from: datetime,
) -> bool:
    return (
        order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        and effective_from > _subscriptions_facade().now_utc()
    )


def _load_billing_product_by_bid(product_bid: str) -> BillingProduct | None:
    normalized_product_bid = _normalize_bid(product_bid)
    if not normalized_product_bid:
        return None
    return (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == normalized_product_bid,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )


def _load_or_create_credit_wallet(app: Flask, creator_bid: str) -> CreditWallet:
    wallet = (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid == creator_bid,
        )
        .order_by(CreditWallet.id.desc())
        .first()
    )
    if wallet is not None:
        return wallet

    wallet = CreditWallet(
        wallet_bid=generate_id(app),
        creator_bid=creator_bid,
        available_credits=Decimal(0),
        reserved_credits=Decimal(0),
        lifetime_granted_credits=Decimal(0),
        lifetime_consumed_credits=Decimal(0),
        last_settled_usage_id=0,
        version=0,
    )
    db.session.add(wallet)
    db.session.flush()
    return wallet


def _resolve_credit_bucket_effective_to(
    *,
    order: BillingOrder,
    product: BillingProduct,
    effective_from: datetime,
) -> datetime | None:
    return _resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=_load_subscription_by_bid,
        resolve_topup_effective_to=lambda creator_bid, from_at: (
            _resolve_topup_bucket_effective_to(
                creator_bid=creator_bid,
                effective_from=from_at,
            )
        ),
        is_self_managed_order=_is_self_managed_billing_order,
        calculate_provider_cycle_end=lambda resolved_product, cycle_start_at: (
            _calc_provider_cycle_end(
                resolved_product,
                cycle_start_at=cycle_start_at,
            )
        ),
        calculate_self_managed_cycle_end=lambda resolved_product, cycle_start_at: (
            _calc_self_managed_cycle_end(
                resolved_product,
                cycle_start_at=cycle_start_at,
            )
        ),
    )


def _is_self_managed_billing_order(order: BillingOrder) -> bool:
    return is_self_managed_billing_provider(order.payment_provider)


def _resolve_topup_bucket_effective_to(
    *,
    creator_bid: str,
    effective_from: datetime,
) -> datetime | None:
    subscription = load_effective_topup_subscription(
        creator_bid,
        as_of=effective_from,
    )
    if subscription is None:
        return None
    return subscription.current_period_end_at


def _resolve_credit_bucket_effective_from(
    *,
    order: BillingOrder,
    default_effective_from: datetime,
) -> datetime:
    return _resolve_order_effective_from(
        order=order,
        default_effective_from=default_effective_from,
        load_subscription_by_bid=_load_subscription_by_bid,
    )
