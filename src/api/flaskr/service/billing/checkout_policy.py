"""Shared checkout eligibility and presentation of the existing business rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flaskr.service.common.models import AppError, raise_error
from flaskr.util.datetime import now_utc

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
)
from .payment_policy import (
    is_provider_managed_payment_provider,
    manual_payments_are_compatible,
    supports_plan_checkout,
)
from .preorders import build_preorder_order_metadata as _build_preorder_order_metadata
from .preorders import resolve_plan_tier as _resolve_plan_tier
from .primitives import normalize_bid as _normalize_bid
from .queries import (
    calculate_self_managed_billing_cycle_end as _calculate_self_managed_billing_cycle_end,
)
from .queries import (
    calculate_self_managed_billing_cycle_end_after_boundary as _calculate_self_managed_billing_cycle_end_after_boundary,
)

if TYPE_CHECKING:
    from flaskr.service.order.payment_providers.api import PaymentOption

    from .models import BillingOrder, BillingProduct, BillingSubscription


@dataclass(frozen=True, slots=True)
class CheckoutOperation:
    """Server-owned action eligibility; the browser only renders and submits it."""

    action: str
    label_key: str
    available: bool
    option_ids: list[str] = field(default_factory=list)
    tooltip_key: str | None = None
    tone: str = "primary"


def validate_upgrade_terms(
    *,
    subscription: BillingSubscription,
    current_product: BillingProduct | None,
    target_product: BillingProduct,
    active_preorder_order: BillingOrder | None,
    payment_provider: str,
) -> tuple[int, BillingOrder | None]:
    """Use the same identity, currency and paid-preorder checks for reads and writes."""
    if (
        current_product is not None
        and manual_payments_are_compatible(
            subscription.billing_provider, payment_provider
        )
        and current_product.currency != target_product.currency
    ):
        raise_error("server.billing.subscriptionPreorderProviderUnsupported")
    paid_preorder = (
        active_preorder_order
        if active_preorder_order is not None
        and active_preorder_order.status == BILLING_ORDER_STATUS_PAID
        else None
    )
    if paid_preorder is not None and (
        not manual_payments_are_compatible(
            subscription.billing_provider,
            payment_provider,
            paid_preorder.payment_provider,
        )
        or paid_preorder.currency != target_product.currency
        or paid_preorder.creator_bid != subscription.creator_bid
        or paid_preorder.subscription_bid != subscription.subscription_bid
    ):
        raise_error("server.billing.subscriptionPreorderProviderUnsupported")
    return _validate_immediate_upgrade_checkout(
        current_product=current_product,
        target_product=target_product,
        active_preorder_order=paid_preorder,
    ), paid_preorder


def describe_plan_checkout(
    *,
    product: BillingProduct,
    current_product: BillingProduct | None,
    subscription: BillingSubscription | None,
    active_preorder: BillingOrder | None,
    options: list[PaymentOption],
) -> CheckoutOperation:
    """Describe the action using existing validators without writes or provider I/O."""
    prefix = "module.billing.package.actions."
    options = [item for item in options if supports_plan_checkout(item.provider)]
    if subscription is None:
        return CheckoutOperation(
            "subscribe",
            prefix + "subscribeNow",
            bool(options),
            [item.id for item in options],
        )
    current_tier, target_tier = (
        _resolve_plan_tier(current_product),
        _resolve_plan_tier(product),
    )
    higher = (
        current_tier is not None
        and target_tier is not None
        and target_tier > current_tier
    )
    same = subscription.product_bid == product.product_bid
    if active_preorder is not None and (
        active_preorder.product_bid == product.product_bid or not higher
    ):
        return CheckoutOperation(
            "preorder",
            prefix
            + (
                "currentSubscription"
                if same and active_preorder.product_bid != product.product_bid
                else "preorderScheduled"
                if active_preorder.product_bid == product.product_bid
                else "preorderLocked"
            ),
            available=False,
            tooltip_key=prefix + "preorderLockedTooltip",
            tone="current" if same else "muted",
        )
    action = "upgrade_immediate" if higher else "preorder"
    label = (
        "upgradeNow" if higher else "preorderRenewal" if same else "preorderDowngrade"
    )
    eligible = []
    source = options
    # Existing hosted contracts stay with their integration; a new checkout
    # option must never silently migrate their automatic billing agreement.
    if is_provider_managed_payment_provider(subscription.billing_provider):
        source = [
            item for item in options if item.provider == subscription.billing_provider
        ]
    for option in source:
        try:
            if higher:
                validate_upgrade_terms(
                    subscription=subscription,
                    current_product=current_product,
                    target_product=product,
                    active_preorder_order=active_preorder,
                    payment_provider=option.provider,
                )
            else:
                _prepare_subscription_preorder_checkout_metadata(
                    subscription=subscription,
                    current_product=current_product,
                    target_product=product,
                    active_preorder_order=active_preorder,
                    payment_provider=option.provider,
                )
        except AppError:
            continue
        eligible.append(option)
    eligible.sort(key=lambda item: item.provider != subscription.billing_provider)
    return CheckoutOperation(
        action,
        prefix + label,
        bool(eligible),
        [item.id for item in eligible],
        tooltip_key=None if eligible else prefix + "preorderProviderUnsupportedTooltip",
        tone="primary" if eligible else "muted",
    )


def _validate_immediate_upgrade_checkout(
    *,
    current_product: BillingProduct | None,
    target_product: BillingProduct,
    active_preorder_order: BillingOrder | None,
) -> int:
    current_tier = _resolve_plan_tier(current_product)
    target_tier = _resolve_plan_tier(target_product)
    if current_tier is None or target_tier is None:
        raise_error("server.order.orderStatusError")
    if target_tier <= current_tier:
        raise_error("server.billing.subscriptionUpgradeOnly")
    if active_preorder_order is None:
        return 0
    if int(active_preorder_order.status or 0) != BILLING_ORDER_STATUS_PAID:
        return 0
    prepaid_amount = int(active_preorder_order.paid_amount or 0)
    if prepaid_amount <= 0:
        return 0
    if int(target_product.price_amount or 0) <= prepaid_amount:
        raise_error("server.billing.subscriptionUpgradeAmountInvalid")
    return prepaid_amount


def _assert_same_plan_preorder_within_single_cycle(
    *,
    subscription: BillingSubscription,
    current_product: BillingProduct | None,
    target_product: BillingProduct,
) -> None:
    if current_product is None:
        return
    if _normalize_bid(current_product.product_bid) != _normalize_bid(
        target_product.product_bid
    ):
        return
    current_period_end_at = subscription.current_period_end_at
    if current_period_end_at is None:
        return

    max_single_prepaid_end = _calculate_self_managed_billing_cycle_end(
        target_product,
        cycle_start_at=now_utc(),
    )
    if (
        max_single_prepaid_end is not None
        and current_period_end_at > max_single_prepaid_end
    ):
        raise_error("server.billing.subscriptionPreorderAlreadyExists")


def _prepare_subscription_preorder_checkout_metadata(
    *,
    subscription: BillingSubscription,
    current_product: BillingProduct | None,
    target_product: BillingProduct,
    active_preorder_order: BillingOrder | None,
    payment_provider: str,
) -> dict[str, object]:
    if is_provider_managed_payment_provider(payment_provider):
        raise_error("server.billing.subscriptionPreorderProviderUnsupported")
    subscription_provider = str(subscription.billing_provider or "").strip().lower()
    if not manual_payments_are_compatible(subscription_provider, payment_provider) or (
        current_product is not None
        and current_product.currency != target_product.currency
    ):
        raise_error("server.billing.subscriptionPreorderProviderUnsupported")
    if active_preorder_order is not None:
        raise_error("server.billing.subscriptionPreorderAlreadyExists")
    if current_product is None or _is_trial_product(current_product):
        raise_error("server.billing.subscriptionPreorderUnavailable")
    _assert_same_plan_preorder_within_single_cycle(
        subscription=subscription,
        current_product=current_product,
        target_product=target_product,
    )

    current_tier = _resolve_plan_tier(current_product)
    target_tier = _resolve_plan_tier(target_product)
    if current_tier is None or target_tier is None:
        raise_error("server.order.orderStatusError")
    if target_tier > current_tier:
        raise_error("server.billing.subscriptionPreorderTargetInvalid")

    cycle_start_at = subscription.current_period_end_at
    if cycle_start_at is None:
        raise_error("server.order.orderStatusError")
    cycle_end_at = _calculate_self_managed_billing_cycle_end_after_boundary(
        target_product,
        cycle_boundary_at=cycle_start_at,
    )
    if cycle_end_at is None:
        raise_error("server.order.orderStatusError")

    return _build_preorder_order_metadata(
        subscription=subscription,
        current_product=current_product,
        target_product=target_product,
        effective_at=cycle_start_at,
        cycle_end_at=cycle_end_at,
        payment_provider=payment_provider,
    )


def _is_trial_product(product: BillingProduct) -> bool:
    metadata = product.metadata_json if isinstance(product.metadata_json, dict) else {}
    return str(
        product.product_code or ""
    ).strip() == BILLING_TRIAL_PRODUCT_CODE or bool(
        metadata.get(BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG)
    )
