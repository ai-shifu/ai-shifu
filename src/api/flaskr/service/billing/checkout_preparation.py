"""Subscription and top-up checkout preparation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.dao import db, uow
from flaskr.dao.uow import (
    unit_of_work,
)
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .campaigns import resolve_applied_billing_campaign
from .checkout_orders import (
    _expire_pending_billing_order_if_due,
    _hydrate_legacy_billing_order_expires_at,
    _is_billing_order_expired,
    _is_same_subscription_checkout_target,
    _load_active_pending_subscription_orders,
    _mark_billing_order_invalidated,
    _resolve_billing_order_expires_at,
)
from .checkout_pricing import (
    _build_campaign_provider_discount_order_metadata,
    _build_provider_price_order_metadata,
    _resolve_checkout_payable_amount,
    _resolve_required_stripe_provider_price_mapping,
    _resolve_stripe_campaign_provider_discount,
)
from .checkout_provider import (
    _build_provider_checkout_request,
    _complete_zero_amount_subscription_checkout,
    _ProviderCheckoutRequest,
)
from .checkout_reopen import (
    _ManualPaymentNeedsClosureError,
    _prepare_pending_order_for_replacement,
)
from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
)
from .models import (
    BillingOrder,
    BillingProduct,
    BillingProductProviderPrice,
    BillingSubscription,
)
from .paid_side_effects import (
    dispatch_billing_paid_order_side_effects as _dispatch_billing_paid_order_side_effects,
)
from .payment_policy import is_manual_payment_provider, manual_payments_are_compatible
from .preorders import (
    CHECKOUT_ACTION_PREORDER,
    CHECKOUT_ACTION_UPGRADE_IMMEDIATE,
)
from .preorders import (
    build_preorder_order_metadata as _build_preorder_order_metadata,
)
from .preorders import (
    load_active_preorder_order as _load_active_preorder_order,
)
from .preorders import (
    resolve_plan_tier as _resolve_plan_tier,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .queries import (
    calculate_self_managed_billing_cycle_end as _calculate_self_managed_billing_cycle_end,
)
from .queries import (
    calculate_self_managed_billing_cycle_end_after_boundary as _calculate_self_managed_billing_cycle_end_after_boundary,
)
from .queries import (
    load_primary_active_subscription as _load_primary_active_subscription,
)
from .subscriptions import (
    load_billing_product_by_bid as _load_billing_product_by_bid,
)
from .subscriptions import (
    load_subscription_by_bid as _load_subscription_by_bid,
)

if TYPE_CHECKING:
    from datetime import datetime
    from types import ModuleType

    from flask import Flask

    from .campaigns import AppliedBillingCampaignResult
    from .dtos import (
        BillingCheckoutResultDTO,
    )
    from .models import BillingCampaignProviderDiscount


def _checkout_facade() -> ModuleType:
    """Resolve collaborators through ``checkout`` so its patch points stay live."""
    from . import checkout

    return checkout


@dataclass(frozen=True)
class _ReopenExistingOrder:
    """Hand the caller back to the reopen flow, which owns its own steps."""

    bill_order_bid: str
    product_bid: str
    requested_channel: str


def _prepare_subscription_checkout(
    app: Flask,
    *,
    normalized_creator_bid: str,
    product_bid: str,
    checkout_action: str,
    payment_provider: str,
    channel: str,
) -> BillingCheckoutResultDTO | _ProviderCheckoutRequest | _ReopenExistingOrder:
    """Create the pending subscription order and describe the provider call."""
    with unit_of_work():
        now = now_utc()
        product = _load_catalog_product(product_bid, BILLING_PRODUCT_TYPE_PLAN)
        provider_price_mapping: BillingProductProviderPrice | None = None
        if payment_provider == "stripe":
            channel = "checkout_session"
            provider_price_mapping = _resolve_required_stripe_provider_price_mapping(
                app,
                product=product,
            )

        current_subscription = _load_primary_active_subscription(
            normalized_creator_bid,
            as_of=now_utc(),
        )
        if current_subscription is not None:
            current_subscription = _checkout_facade()._lock_subscription_for_checkout(
                current_subscription
            )
        subscription, order_type, order_metadata, prepaid_offset_amount = (
            _resolve_subscription_checkout_target(
                app,
                current_subscription=current_subscription,
                normalized_creator_bid=normalized_creator_bid,
                product=product,
                checkout_action=checkout_action,
                payment_provider=payment_provider,
            )
        )

        applied_campaign, campaign_provider_discount = (
            _resolve_subscription_checkout_campaign(
                product,
                order_type=order_type,
                checkout_action=checkout_action,
                provider_price_mapping=provider_price_mapping,
            )
        )

        pending_orders = _load_active_pending_subscription_orders(
            normalized_creator_bid
        )
        payable_amount = _resolve_checkout_payable_amount(
            product=product,
            applied_campaign=applied_campaign,
            provider_price_mapping=provider_price_mapping,
            campaign_provider_discount=campaign_provider_discount,
            prepaid_offset_amount=prepaid_offset_amount,
        )
        currency = (
            provider_price_mapping.currency.upper()
            if provider_price_mapping
            else product.currency
        )
        reusable_order, duplicate_reusable_orders, conflicting_pending_orders = (
            _classify_pending_subscription_orders(
                app,
                pending_orders,
                now=now,
                product_bid=product.product_bid,
                order_type=order_type,
                payment_provider=payment_provider,
                channel=channel,
                currency=currency,
                payable_amount=payable_amount,
                checkout_metadata=order_metadata,
                provider_price_bid=(
                    provider_price_mapping.provider_price_bid
                    if provider_price_mapping is not None
                    else ""
                ),
                campaign_bid=applied_campaign.campaign_bid if applied_campaign else "",
                campaign_provider_discount_bid=(
                    campaign_provider_discount.campaign_provider_discount_bid
                    if campaign_provider_discount is not None
                    else ""
                ),
            )
        )

        _cancel_replaced_pending_orders(
            app,
            duplicate_reusable_orders,
            now=now,
            replaced_by_bill_order_bid=reusable_order.bill_order_bid
            if reusable_order is not None
            else "",
        )

        if reusable_order is not None:
            return _reopen_reusable_subscription_order(
                app,
                reusable_order,
                subscription=subscription,
                had_current_subscription=current_subscription is not None,
                normalized_creator_bid=normalized_creator_bid,
                conflicting_pending_orders=conflicting_pending_orders,
                now=now,
                product_bid=product.product_bid,
                channel=channel,
            )

        db.session.add(subscription)
        db.session.flush()

        order = _build_subscription_checkout_order(
            app,
            normalized_creator_bid=normalized_creator_bid,
            subscription=subscription,
            product=product,
            order_type=order_type,
            order_metadata=order_metadata,
            provider_price_mapping=provider_price_mapping,
            applied_campaign=applied_campaign,
            campaign_provider_discount=campaign_provider_discount,
            payable_amount=payable_amount,
            payment_provider=payment_provider,
            channel=channel,
            now=now,
        )
        _cancel_replaced_pending_orders(
            app,
            conflicting_pending_orders,
            now=now,
            replaced_by_bill_order_bid=order.bill_order_bid,
        )
        db.session.add(order)
        db.session.flush()

        return _finish_new_subscription_checkout_order(
            app,
            order,
            normalized_creator_bid=normalized_creator_bid,
            product=product,
            payment_provider=payment_provider,
            channel=channel,
            provider_price_mapping=provider_price_mapping,
            campaign_provider_discount=campaign_provider_discount,
            payable_amount=payable_amount,
        )


def _resolve_subscription_checkout_campaign(
    product: BillingProduct,
    *,
    order_type: int,
    checkout_action: str,
    provider_price_mapping: BillingProductProviderPrice | None,
) -> tuple[AppliedBillingCampaignResult | None, BillingCampaignProviderDiscount | None]:
    """Resolve the campaign (none for preorder renewals) and its Stripe discount."""
    is_preorder_renewal = (
        checkout_action == CHECKOUT_ACTION_PREORDER
        and order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
    )
    resolved_campaign = (
        resolve_applied_billing_campaign(
            product,
            order_type=order_type,
        )
        if not is_preorder_renewal
        else None
    )
    applied_campaign = resolved_campaign
    campaign_provider_discount = _resolve_stripe_campaign_provider_discount(
        applied_campaign=applied_campaign,
        product=product,
        provider_price_mapping=provider_price_mapping,
    )
    return applied_campaign, campaign_provider_discount


def _finish_new_subscription_checkout_order(
    app: Flask,
    order: BillingOrder,
    *,
    normalized_creator_bid: str,
    product: BillingProduct,
    payment_provider: str,
    channel: str,
    provider_price_mapping: BillingProductProviderPrice | None,
    campaign_provider_discount: BillingCampaignProviderDiscount | None,
    payable_amount: int,
) -> BillingCheckoutResultDTO | _ProviderCheckoutRequest:
    """Complete a free order in this transaction or describe the provider call."""
    requires_stripe_subscription_checkout = bool(
        payment_provider == "stripe" and campaign_provider_discount is not None
    )
    if payable_amount == 0 and not requires_stripe_subscription_checkout:
        checkout_result, paid_order_side_effects = (
            _complete_zero_amount_subscription_checkout(app, order)
        )
        # Paid-order side effects (credit notifications, SMS, Feishu)
        # dispatch only once this transaction is durable.
        uow.on_commit(
            lambda: _dispatch_billing_paid_order_side_effects(
                app, paid_order_side_effects
            )
        )
        return checkout_result

    return _build_provider_checkout_request(
        app,
        creator_bid=normalized_creator_bid,
        order=order,
        product=product,
        payment_provider=payment_provider,
        payment_mode="subscription",
        channel=channel,
        provider_price_mapping=provider_price_mapping,
    )


def _resolve_subscription_checkout_target(
    app: Flask,
    *,
    current_subscription: BillingSubscription | None,
    normalized_creator_bid: str,
    product: BillingProduct,
    checkout_action: str,
    payment_provider: str,
) -> tuple[BillingSubscription, int, dict[str, object], int]:
    """Pick the subscription row, order type, metadata, and prepaid offset."""
    prepaid_offset_amount = 0
    if current_subscription is None:
        subscription = BillingSubscription(
            subscription_bid=generate_id(app),
            creator_bid=normalized_creator_bid,
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
            billing_provider=payment_provider,
            provider_subscription_id="",
            provider_customer_id="",
            cancel_at_period_end=0,
            next_product_bid="",
            metadata_json={"checkout_started": True},
        )
        order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_START
        order_metadata = {"checkout_type": "subscription"}
    else:
        subscription = current_subscription
        current_product = _load_billing_product_by_bid(subscription.product_bid)
        active_preorder_order = _load_active_preorder_order(
            subscription.subscription_bid
        )
        if checkout_action == CHECKOUT_ACTION_PREORDER:
            order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
            order_metadata = _prepare_subscription_preorder_checkout_metadata(
                subscription=subscription,
                current_product=current_product,
                target_product=product,
                active_preorder_order=active_preorder_order,
                payment_provider=payment_provider,
            )
        elif checkout_action == CHECKOUT_ACTION_UPGRADE_IMMEDIATE:
            order_metadata, prepaid_offset_amount = (
                _prepare_immediate_upgrade_checkout_metadata(
                    subscription=subscription,
                    current_product=current_product,
                    target_product=product,
                    active_preorder_order=active_preorder_order,
                    payment_provider=payment_provider,
                )
            )
            order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
        else:
            raise_error("server.order.orderStatusError")
        subscription.updated_at = now_utc()
    return subscription, order_type, order_metadata, prepaid_offset_amount


def _prepare_immediate_upgrade_checkout_metadata(
    *,
    subscription: BillingSubscription,
    current_product: BillingProduct | None,
    target_product: BillingProduct,
    active_preorder_order: BillingOrder | None,
    payment_provider: str,
) -> tuple[dict[str, object], int]:
    """Validate an immediate upgrade and build its order metadata and offset."""
    product = target_product
    if (
        current_product is not None
        and manual_payments_are_compatible(
            subscription.billing_provider, payment_provider
        )
        and current_product.currency != product.currency
    ):
        raise_error("server.billing.subscriptionPreorderProviderUnsupported")
    paid_preorder_order = (
        active_preorder_order
        if active_preorder_order is not None
        and int(active_preorder_order.status or 0) == BILLING_ORDER_STATUS_PAID
        else None
    )
    if paid_preorder_order is not None:
        subscription_provider = str(subscription.billing_provider or "").strip().lower()
        preorder_provider = (
            str(paid_preorder_order.payment_provider or "").strip().lower()
        )
        if (
            not manual_payments_are_compatible(
                subscription_provider, payment_provider, preorder_provider
            )
            or paid_preorder_order.currency != product.currency
            or paid_preorder_order.creator_bid != subscription.creator_bid
            or paid_preorder_order.subscription_bid != subscription.subscription_bid
        ):
            raise_error("server.billing.subscriptionPreorderProviderUnsupported")
    prepaid_offset_amount = _validate_immediate_upgrade_checkout(
        current_product=current_product,
        target_product=product,
        active_preorder_order=paid_preorder_order,
    )
    replaced_preorder_order = paid_preorder_order
    subscription.metadata_json = _normalize_json_object(
        {
            **(
                subscription.metadata_json
                if isinstance(subscription.metadata_json, dict)
                else {}
            ),
            "checkout_started": True,
        }
    ).to_metadata_json()
    order_metadata = {
        "checkout_type": "subscription",
        "effective_mode": "immediate",
        "current_product_bid": (
            current_product.product_bid if current_product is not None else None
        ),
        "target_product_bid": product.product_bid,
        "prepaid_offset_amount": prepaid_offset_amount,
        "preorder_order_bid": (
            replaced_preorder_order.bill_order_bid
            if replaced_preorder_order is not None
            else None
        ),
    }
    return order_metadata, prepaid_offset_amount


def _classify_pending_subscription_orders(
    app: Flask,
    pending_orders: list[BillingOrder],
    *,
    now: datetime,
    product_bid: str,
    order_type: int,
    payment_provider: str,
    channel: str,
    currency: str,
    payable_amount: int,
    checkout_metadata: dict[str, object],
    provider_price_bid: str,
    campaign_bid: str,
    campaign_provider_discount_bid: str,
) -> tuple[BillingOrder | None, list[BillingOrder], list[BillingOrder]]:
    """Split pending orders into one reusable order, duplicates, and conflicts."""
    reusable_order: BillingOrder | None = None
    duplicate_reusable_orders: list[BillingOrder] = []
    conflicting_pending_orders: list[BillingOrder] = []
    for pending_order in pending_orders:
        if pending_order.status != BILLING_ORDER_STATUS_PENDING:
            _prepare_pending_order_for_replacement(app, pending_order)
            continue
        if _hydrate_legacy_billing_order_expires_at(pending_order):
            db.session.add(pending_order)
        if (
            _is_billing_order_expired(pending_order, now=now)
            and is_manual_payment_provider(pending_order.payment_provider)
            and pending_order.provider_reference_id
        ):
            raise _ManualPaymentNeedsClosureError(pending_order.bill_order_bid)
        if _expire_pending_billing_order_if_due(pending_order, now=now):
            db.session.add(pending_order)
            continue
        if _is_same_subscription_checkout_target(
            pending_order,
            product_bid=product_bid,
            order_type=order_type,
            payment_provider=payment_provider,
            channel=channel,
            currency=currency,
            payable_amount=payable_amount,
            checkout_metadata=checkout_metadata,
            provider_price_bid=provider_price_bid,
            campaign_bid=campaign_bid,
            campaign_provider_discount_bid=campaign_provider_discount_bid,
        ):
            if reusable_order is None:
                reusable_order = pending_order
            else:
                duplicate_reusable_orders.append(pending_order)
            continue
        conflicting_pending_orders.append(pending_order)
    return reusable_order, duplicate_reusable_orders, conflicting_pending_orders


def _cancel_replaced_pending_orders(
    app: Flask,
    orders: list[BillingOrder],
    *,
    now: datetime,
    replaced_by_bill_order_bid: str,
) -> None:
    """Close each order at its provider, then cancel it as replaced."""
    for replaced_order in orders:
        _prepare_pending_order_for_replacement(app, replaced_order)
        _mark_billing_order_invalidated(
            replaced_order,
            target_status=BILLING_ORDER_STATUS_CANCELED,
            reason="replaced_by_new_package",
            invalidated_at=now,
            replaced_by_bill_order_bid=replaced_by_bill_order_bid,
        )
        db.session.add(replaced_order)


def _reopen_reusable_subscription_order(
    app: Flask,
    reusable_order: BillingOrder,
    *,
    subscription: BillingSubscription,
    had_current_subscription: bool,
    normalized_creator_bid: str,
    conflicting_pending_orders: list[BillingOrder],
    now: datetime,
    product_bid: str,
    channel: str,
) -> _ReopenExistingOrder:
    """Keep the matching pending order and hand it to the reopen flow."""
    if not had_current_subscription:
        original_subscription = _load_subscription_by_bid(
            reusable_order.subscription_bid
        )
        if (
            original_subscription is None
            or original_subscription.creator_bid != normalized_creator_bid
        ):
            raise_error("server.order.orderStatusError")
        subscription = original_subscription
    _cancel_replaced_pending_orders(
        app,
        conflicting_pending_orders,
        now=now,
        replaced_by_bill_order_bid=reusable_order.bill_order_bid,
    )

    if subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT:
        subscription.billing_provider = reusable_order.payment_provider
        subscription.updated_at = now

    db.session.add(subscription)
    db.session.flush()
    # The reopen flow owns its own units of work, so it has to run
    # after this one commits.
    return _ReopenExistingOrder(
        bill_order_bid=reusable_order.bill_order_bid,
        product_bid=product_bid,
        requested_channel=channel,
    )


def _build_subscription_checkout_order(
    app: Flask,
    *,
    normalized_creator_bid: str,
    subscription: BillingSubscription,
    product: BillingProduct,
    order_type: int,
    order_metadata: dict[str, object],
    provider_price_mapping: BillingProductProviderPrice | None,
    applied_campaign: AppliedBillingCampaignResult | None,
    campaign_provider_discount: BillingCampaignProviderDiscount | None,
    payable_amount: int,
    payment_provider: str,
    channel: str,
    now: datetime,
) -> BillingOrder:
    """Build the new pending subscription order with its checkout metadata."""
    order_metadata_payload = {**order_metadata}
    if provider_price_mapping is not None:
        order_metadata_payload.update(
            _build_provider_price_order_metadata(provider_price_mapping)
        )
    if applied_campaign is not None:
        order_metadata_payload["campaign"] = (
            applied_campaign.to_catalog_payload() or None
        )
    if campaign_provider_discount is not None:
        order_metadata_payload.update(
            _build_campaign_provider_discount_order_metadata(campaign_provider_discount)
        )
    normalized_order_metadata = _normalize_json_object(
        order_metadata_payload
    ).to_metadata_json()

    return BillingOrder(
        bill_order_bid=generate_id(app),
        creator_bid=normalized_creator_bid,
        order_type=order_type,
        product_bid=product.product_bid,
        subscription_bid=subscription.subscription_bid,
        currency=(
            provider_price_mapping.currency.upper()
            if provider_price_mapping is not None
            else product.currency
        ),
        payable_amount=payable_amount,
        paid_amount=0,
        payment_provider=payment_provider,
        channel=channel,
        provider_reference_id="",
        status=BILLING_ORDER_STATUS_PENDING,
        expires_at=_resolve_billing_order_expires_at(now=now),
        metadata_json=normalized_order_metadata,
        campaign_bid=applied_campaign.campaign_bid if applied_campaign else "",
        campaign_benefit_type=(
            applied_campaign.benefit_type_code if applied_campaign else 0
        ),
        campaign_discount_amount=(
            applied_campaign.discount_amount if applied_campaign else 0
        ),
        campaign_bonus_credit_amount=(
            applied_campaign.bonus_credit_amount if applied_campaign else 0
        ),
    )


def _prepare_topup_checkout(
    app: Flask,
    *,
    normalized_creator_bid: str,
    product_bid: str,
    payment_provider: str,
    channel: str,
) -> _ProviderCheckoutRequest:
    """Create the pending top-up order and describe the provider call."""
    with unit_of_work():
        product = _load_catalog_product(product_bid, BILLING_PRODUCT_TYPE_TOPUP)
        provider_price_mapping: BillingProductProviderPrice | None = None
        if payment_provider == "stripe":
            channel = "checkout_session"
            provider_price_mapping = _resolve_required_stripe_provider_price_mapping(
                app,
                product=product,
            )
        if (
            _checkout_facade()._load_effective_topup_subscription(
                normalized_creator_bid
            )
            is None
        ):
            raise_error("server.billing.subscriptionInactive")
        resolved_campaign = resolve_applied_billing_campaign(
            product,
            order_type=BILLING_ORDER_TYPE_TOPUP,
        )
        applied_campaign = resolved_campaign
        campaign_provider_discount = _resolve_stripe_campaign_provider_discount(
            applied_campaign=applied_campaign,
            product=product,
            provider_price_mapping=provider_price_mapping,
        )
        order_metadata_payload: dict[str, object] = {
            "checkout_type": "topup",
            "campaign": (
                applied_campaign.to_catalog_payload()
                if applied_campaign is not None
                else None
            ),
        }
        if provider_price_mapping is not None:
            order_metadata_payload.update(
                _build_provider_price_order_metadata(provider_price_mapping)
            )
        if campaign_provider_discount is not None:
            order_metadata_payload.update(
                _build_campaign_provider_discount_order_metadata(
                    campaign_provider_discount
                )
            )
        order = BillingOrder(
            bill_order_bid=generate_id(app),
            creator_bid=normalized_creator_bid,
            order_type=BILLING_ORDER_TYPE_TOPUP,
            product_bid=product.product_bid,
            subscription_bid="",
            currency=(
                provider_price_mapping.currency.upper()
                if provider_price_mapping is not None
                else product.currency
            ),
            payable_amount=_resolve_checkout_payable_amount(
                product=product,
                applied_campaign=applied_campaign,
                provider_price_mapping=provider_price_mapping,
                campaign_provider_discount=campaign_provider_discount,
            ),
            paid_amount=0,
            payment_provider=payment_provider,
            channel=channel,
            provider_reference_id="",
            status=BILLING_ORDER_STATUS_PENDING,
            # The row is committed before the provider call, so it needs a
            # deadline: a provider failure would otherwise leave it pending
            # forever, with nothing to time it out.
            expires_at=_resolve_billing_order_expires_at(),
            metadata_json=_normalize_json_object(
                order_metadata_payload
            ).to_metadata_json(),
            campaign_bid=applied_campaign.campaign_bid if applied_campaign else "",
            campaign_benefit_type=(
                applied_campaign.benefit_type_code if applied_campaign else 0
            ),
            campaign_discount_amount=(
                applied_campaign.discount_amount if applied_campaign else 0
            ),
            campaign_bonus_credit_amount=(
                applied_campaign.bonus_credit_amount if applied_campaign else 0
            ),
        )
        db.session.add(order)
        db.session.flush()

        return _build_provider_checkout_request(
            app,
            creator_bid=normalized_creator_bid,
            order=order,
            product=product,
            payment_provider=payment_provider,
            payment_mode="one_time",
            channel=channel,
            provider_price_mapping=provider_price_mapping,
        )


def _lock_subscription_for_checkout(
    subscription: BillingSubscription,
) -> BillingSubscription:
    normalized_subscription_bid = _normalize_bid(subscription.subscription_bid)
    if not normalized_subscription_bid:
        return subscription
    locked_subscription = (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.subscription_bid == normalized_subscription_bid,
        )
        .with_for_update()
        .order_by(BillingSubscription.id.desc())
        .first()
    )
    return locked_subscription or subscription


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
    if payment_provider == "stripe":
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
    )


def _is_trial_product(product: BillingProduct) -> bool:
    metadata = product.metadata_json if isinstance(product.metadata_json, dict) else {}
    return str(
        product.product_code or ""
    ).strip() == BILLING_TRIAL_PRODUCT_CODE or bool(
        metadata.get(BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG)
    )


def _load_catalog_product(product_bid: str, expected_type: int) -> BillingProduct:
    if not product_bid:
        raise_param_error("product_bid")
    product = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == product_bid,
            BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )
    if product is None or product.product_type != expected_type:
        raise_error("server.order.orderNotFound")
    if _is_trial_product(product):
        raise_error("server.order.orderNotFound")
    return product


def _load_owned_subscription(
    creator_bid: str,
    subscription_bid: str,
) -> BillingSubscription:
    query = BillingSubscription.query.filter(
        BillingSubscription.deleted == 0,
        BillingSubscription.creator_bid == creator_bid,
    )
    if subscription_bid:
        query = query.filter(BillingSubscription.subscription_bid == subscription_bid)
    subscription = query.order_by(BillingSubscription.created_at.desc()).first()
    if subscription is None:
        raise_error("server.order.orderNotFound")
    return subscription
