from __future__ import annotations

from datetime import datetime, timedelta

from flaskr.service.billing.consts import BILLING_SUBSCRIPTION_STATUS_ACTIVE
from flaskr.service.billing.cycle_state_transitions import (
    resolve_effective_subscription_cycle_window,
    subscription_has_effective_cycle,
)
from flaskr.service.billing.models import BillingSubscription


def test_subscription_has_effective_cycle_uses_current_period_window() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-state",
        creator_bid="creator-cycle-state",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=current_at - timedelta(days=1),
        current_period_end_at=current_at + timedelta(days=1),
    )

    assert subscription_has_effective_cycle(subscription, as_of=current_at) is True

    subscription.current_period_end_at = current_at

    assert subscription_has_effective_cycle(subscription, as_of=current_at) is False
    assert subscription_has_effective_cycle(None, as_of=current_at) is False


def test_resolve_effective_subscription_cycle_window_returns_current_window() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    cycle_start = current_at
    cycle_end = current_at + timedelta(days=30)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-window",
        creator_bid="creator-cycle-window",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=cycle_start,
        current_period_end_at=cycle_end,
    )

    window = resolve_effective_subscription_cycle_window(
        subscription,
        as_of=current_at,
    )

    assert window is not None
    assert window.start_at == cycle_start
    assert window.end_at == cycle_end


def test_resolve_effective_subscription_cycle_window_rejects_invalid_windows() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-window-invalid",
        creator_bid="creator-cycle-window-invalid",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=current_at - timedelta(days=1),
        current_period_end_at=current_at + timedelta(days=1),
    )

    subscription.current_period_start_at = None
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at - timedelta(days=1)
    subscription.current_period_end_at = None
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at
    subscription.current_period_end_at = current_at
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at + timedelta(days=1)
    subscription.current_period_end_at = current_at
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at + timedelta(seconds=1)
    subscription.current_period_end_at = current_at + timedelta(days=1)
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at - timedelta(days=1)
    subscription.current_period_end_at = current_at
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )
