from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from flaskr.service.billing.consts import (
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
)
from flaskr.service.billing.cycle_transitions import (
    resolve_order_effective_from,
    resolve_order_effective_to,
)


def _raise_unexpected_call(*_args, **_kwargs):
    raise AssertionError("unexpected callback call")


def test_resolve_order_effective_from_prefers_order_cycle_metadata() -> None:
    default_effective_from = datetime(2026, 7, 1, 0, 0, 0)
    cycle_start_at = datetime(2026, 7, 31, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        subscription_bid="subscription-cycle",
        metadata_json={"renewal_cycle_start_at": cycle_start_at.isoformat()},
    )

    effective_from = resolve_order_effective_from(
        order=order,
        default_effective_from=default_effective_from,
        load_subscription_by_bid=lambda _: None,
    )

    assert effective_from == cycle_start_at


def test_resolve_order_effective_from_ignores_metadata_for_non_renewal_orders() -> None:
    default_effective_from = datetime(2026, 7, 1, 0, 0, 0)
    cycle_start_at = datetime(2026, 7, 31, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        subscription_bid="subscription-cycle",
        metadata_json={"renewal_cycle_start_at": cycle_start_at.isoformat()},
    )

    effective_from = resolve_order_effective_from(
        order=order,
        default_effective_from=default_effective_from,
        load_subscription_by_bid=_raise_unexpected_call,
    )

    assert effective_from == default_effective_from


def test_resolve_order_effective_from_uses_subscription_boundary_for_early_renewal() -> (
    None
):
    default_effective_from = datetime(2026, 7, 1, 0, 0, 0)
    subscription_boundary = datetime(2026, 7, 31, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        subscription_bid="subscription-cycle",
        metadata_json={},
    )
    subscription = SimpleNamespace(current_period_end_at=subscription_boundary)

    effective_from = resolve_order_effective_from(
        order=order,
        default_effective_from=default_effective_from,
        load_subscription_by_bid=lambda _: subscription,
    )

    assert effective_from == subscription_boundary


def test_resolve_order_effective_from_falls_back_when_subscription_boundary_unusable() -> (
    None
):
    default_effective_from = datetime(2026, 7, 1, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        subscription_bid="subscription-cycle",
        metadata_json={},
    )

    assert (
        resolve_order_effective_from(
            order=order,
            default_effective_from=default_effective_from,
            load_subscription_by_bid=lambda _: None,
        )
        == default_effective_from
    )
    assert (
        resolve_order_effective_from(
            order=order,
            default_effective_from=default_effective_from,
            load_subscription_by_bid=lambda _: SimpleNamespace(
                current_period_end_at=None
            ),
        )
        == default_effective_from
    )
    assert (
        resolve_order_effective_from(
            order=order,
            default_effective_from=default_effective_from,
            load_subscription_by_bid=lambda _: SimpleNamespace(
                current_period_end_at=default_effective_from
            ),
        )
        == default_effective_from
    )


def test_resolve_order_effective_to_uses_topup_subscription_window() -> None:
    effective_from = datetime(2026, 7, 1, 0, 0, 0)
    effective_to = datetime(2026, 7, 31, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_TOPUP,
        creator_bid="creator-cycle",
        subscription_bid="",
        metadata_json={},
    )
    product = SimpleNamespace(
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
    )

    resolved = resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=lambda _: None,
        resolve_topup_effective_to=lambda creator_bid, from_at: effective_to,
        is_self_managed_order=lambda _: False,
        calculate_provider_cycle_end=lambda _, cycle_start_at: None,
        calculate_self_managed_cycle_end=lambda _, cycle_start_at: None,
    )

    assert resolved == effective_to


def test_resolve_order_effective_to_prefers_order_cycle_metadata() -> None:
    effective_from = datetime(2026, 7, 1, 0, 0, 0)
    metadata_effective_to = datetime(2026, 7, 31, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        creator_bid="creator-cycle",
        subscription_bid="subscription-cycle",
        metadata_json={"renewal_cycle_end_at": metadata_effective_to.isoformat()},
    )
    product = SimpleNamespace(
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
    )

    resolved = resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=_raise_unexpected_call,
        resolve_topup_effective_to=_raise_unexpected_call,
        is_self_managed_order=lambda _: False,
        calculate_provider_cycle_end=_raise_unexpected_call,
        calculate_self_managed_cycle_end=_raise_unexpected_call,
    )

    assert resolved == metadata_effective_to


def test_resolve_order_effective_to_prefers_existing_subscription_start_window() -> (
    None
):
    effective_from = datetime(2026, 7, 1, 0, 0, 0)
    effective_to = datetime(2026, 7, 31, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        creator_bid="creator-cycle",
        subscription_bid="subscription-cycle",
        metadata_json={},
    )
    product = SimpleNamespace(
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
    )
    subscription = SimpleNamespace(
        current_period_start_at=effective_from,
        current_period_end_at=effective_to,
    )

    resolved = resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=lambda _: subscription,
        resolve_topup_effective_to=lambda creator_bid, from_at: None,
        is_self_managed_order=lambda _: False,
        calculate_provider_cycle_end=lambda _, cycle_start_at: None,
        calculate_self_managed_cycle_end=lambda _, cycle_start_at: None,
    )

    assert resolved == effective_to


def test_resolve_order_effective_to_ignores_invalid_subscription_start_window() -> None:
    effective_from = datetime(2026, 7, 1, 0, 0, 0)
    calculated_effective_to = datetime(2026, 8, 1, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        creator_bid="creator-cycle",
        subscription_bid="subscription-cycle",
        metadata_json={},
    )
    product = SimpleNamespace(
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
    )
    subscription = SimpleNamespace(
        current_period_start_at=effective_from,
        current_period_end_at=effective_from,
    )

    resolved = resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=lambda _: subscription,
        resolve_topup_effective_to=lambda creator_bid, from_at: None,
        is_self_managed_order=lambda _: False,
        calculate_provider_cycle_end=lambda _, cycle_start_at: calculated_effective_to,
        calculate_self_managed_cycle_end=_raise_unexpected_call,
    )

    assert resolved == calculated_effective_to


def test_resolve_order_effective_to_uses_provider_cycle_calculator() -> None:
    effective_from = datetime(2026, 7, 1, 0, 0, 0)
    effective_to = datetime(2026, 8, 1, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        creator_bid="creator-cycle",
        subscription_bid="subscription-cycle",
        metadata_json={},
    )
    product = SimpleNamespace(
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
    )

    resolved = resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=lambda _: None,
        resolve_topup_effective_to=lambda creator_bid, from_at: None,
        is_self_managed_order=lambda _: False,
        calculate_provider_cycle_end=lambda _, cycle_start_at: effective_to,
        calculate_self_managed_cycle_end=lambda _, cycle_start_at: None,
    )

    assert resolved == effective_to


def test_resolve_order_effective_to_returns_none_for_invalid_interval_count() -> None:
    effective_from = datetime(2026, 7, 1, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        creator_bid="creator-cycle",
        subscription_bid="subscription-cycle",
        metadata_json={},
    )
    product = SimpleNamespace(
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=0,
    )

    resolved = resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=lambda _: None,
        resolve_topup_effective_to=_raise_unexpected_call,
        is_self_managed_order=_raise_unexpected_call,
        calculate_provider_cycle_end=_raise_unexpected_call,
        calculate_self_managed_cycle_end=_raise_unexpected_call,
    )

    assert resolved is None


def test_resolve_order_effective_to_uses_day_interval_without_provider_calculator() -> (
    None
):
    effective_from = datetime(2026, 7, 1, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        creator_bid="creator-cycle",
        subscription_bid="subscription-cycle",
        metadata_json={},
    )
    product = SimpleNamespace(
        billing_interval=BILLING_INTERVAL_DAY,
        billing_interval_count=14,
    )

    resolved = resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=lambda _: None,
        resolve_topup_effective_to=_raise_unexpected_call,
        is_self_managed_order=lambda _: False,
        calculate_provider_cycle_end=_raise_unexpected_call,
        calculate_self_managed_cycle_end=_raise_unexpected_call,
    )

    assert resolved == datetime(2026, 7, 15, 0, 0, 0)


@pytest.mark.parametrize(
    "billing_interval",
    [BILLING_INTERVAL_DAY, BILLING_INTERVAL_MONTH, BILLING_INTERVAL_YEAR],
    ids=("day", "month", "year"),
)
def test_resolve_order_effective_to_uses_self_managed_calculator(
    billing_interval: int,
) -> None:
    effective_from = datetime(2026, 7, 1, 0, 0, 0)
    effective_to = datetime(2026, 8, 1, 0, 0, 0)
    order = SimpleNamespace(
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        creator_bid="creator-cycle",
        subscription_bid="subscription-cycle",
        metadata_json={},
    )
    product = SimpleNamespace(
        billing_interval=billing_interval,
        billing_interval_count=1,
    )

    resolved = resolve_order_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
        load_subscription_by_bid=lambda _: None,
        resolve_topup_effective_to=_raise_unexpected_call,
        is_self_managed_order=lambda _: True,
        calculate_provider_cycle_end=_raise_unexpected_call,
        calculate_self_managed_cycle_end=lambda _, cycle_start_at: effective_to,
    )

    assert resolved == effective_to
