"""Renewal-event lifecycle sync for billing subscriptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .consts import (
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
)
from .payment_policy import is_manual_payment_provider
from .primitives import normalize_bid as _normalize_bid
from .renewal_event_transitions import (
    cancel_subscription_renewal_events as _cancel_subscription_renewal_events,
)
from .renewal_event_transitions import (
    upsert_subscription_renewal_event as _upsert_subscription_renewal_event,
)
from .reserved_renewal_activation import (
    IncompleteReservedGrantActivationError,  # noqa: F401
    validate_reserved_renewal_cycle_activation,  # noqa: F401
)
from .subscriptions_cycles import (
    _has_paid_deferred_manual_renewal_at_boundary,
    _load_billing_product_by_bid,
    _resolve_manual_renewal_scheduled_at,
)

if TYPE_CHECKING:
    from flask import Flask

    from .models import (
        BillingSubscription,
    )


def _sync_subscription_lifecycle_events(
    app: Flask,
    subscription: BillingSubscription,
) -> None:
    scheduled_at = subscription.current_period_end_at
    provider_name = _normalize_bid(subscription.billing_provider)
    product = _load_billing_product_by_bid(subscription.product_bid)

    if subscription.status in {
        BILLING_SUBSCRIPTION_STATUS_CANCELED,
        BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    }:
        subscription.grace_period_end_at = None
        _cancel_subscription_renewal_events(subscription.subscription_bid)
        return

    if subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE:
        grace_period_end_at = (
            subscription.grace_period_end_at
            or scheduled_at
            or subscription.current_period_start_at
        )
        subscription.grace_period_end_at = grace_period_end_at
        _cancel_subscription_renewal_events(
            subscription.subscription_bid,
            event_types=(
                BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
                BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
                BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            ),
        )
        if grace_period_end_at is not None:
            _upsert_subscription_renewal_event(
                app,
                subscription,
                event_type=BILLING_RENEWAL_EVENT_TYPE_RETRY,
                scheduled_at=grace_period_end_at,
            )
        return

    subscription.grace_period_end_at = None
    _cancel_subscription_renewal_events(
        subscription.subscription_bid,
        event_types=(BILLING_RENEWAL_EVENT_TYPE_RETRY,),
    )

    if scheduled_at is None:
        _cancel_subscription_renewal_events(subscription.subscription_bid)
        return

    if subscription.cancel_at_period_end or (
        subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
    ):
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            scheduled_at=scheduled_at,
        )
        _cancel_subscription_renewal_events(
            subscription.subscription_bid,
            event_types=(
                BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
                BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            ),
        )
        return

    _cancel_subscription_renewal_events(
        subscription.subscription_bid,
        event_types=(BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,),
    )

    if subscription.next_product_bid:
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            scheduled_at=scheduled_at,
        )
    else:
        _cancel_subscription_renewal_events(
            subscription.subscription_bid,
            event_types=(BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,),
        )

    if (
        subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        and product is not None
        and int(product.auto_renew_enabled or 0) == 1
    ):
        renewal_scheduled_at = scheduled_at
        if is_manual_payment_provider(provider_name):
            renewal_scheduled_at = _resolve_manual_renewal_scheduled_at(subscription)
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            scheduled_at=renewal_scheduled_at or scheduled_at,
        )
        if is_manual_payment_provider(
            provider_name
        ) or _has_paid_deferred_manual_renewal_at_boundary(
            subscription,
            boundary_at=scheduled_at,
        ):
            _upsert_subscription_renewal_event(
                app,
                subscription,
                event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
                scheduled_at=scheduled_at,
            )
        else:
            _cancel_subscription_renewal_events(
                subscription.subscription_bid,
                event_types=(BILLING_RENEWAL_EVENT_TYPE_EXPIRE,),
            )
        return

    if (
        subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        and product is not None
    ):
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=scheduled_at,
        )
        _cancel_subscription_renewal_events(
            subscription.subscription_bid,
            event_types=(BILLING_RENEWAL_EVENT_TYPE_RENEWAL,),
        )
        return

    _cancel_subscription_renewal_events(
        subscription.subscription_bid,
        event_types=(
            BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        ),
    )
