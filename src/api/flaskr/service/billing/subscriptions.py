"""Subscription lifecycle, renewal orchestration, and credit grants."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - tests patch subscriptions.datetime
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import raise_error
from flaskr.service.order.payment_providers import get_payment_provider
from flaskr.util.datetime import (  # noqa: F401 - re-exported for import compatibility
    NAIVE_DATETIME_MIN,
    now_utc,
    to_utc_iso,
)
from flaskr.util.uuid import generate_id

from .bucket_categories import (  # noqa: F401 - re-exported for import compatibility
    resolve_bucket_category_from_order_type,
    resolve_credit_bucket_priority,
)
from .consts import (  # noqa: F401 - re-exported for import compatibility
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
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
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_CANCELED,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .models import (  # noqa: F401 - re-exported for import compatibility
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .payment_policy import (  # noqa: F401 - re-exported for import compatibility
    MANUAL_PAYMENT_PROVIDERS,
    is_manual_payment_provider,
)
from .preorders import (  # noqa: F401 - re-exported for import compatibility
    PREORDER_STATE_ABSORBED_BY_UPGRADE,
    PREORDER_STATE_PENDING_EFFECTIVE,
)
from .preorders import (
    is_preorder_order as _is_preorder_order,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import normalize_json_value as _normalize_json_value
from .queries import (
    calculate_self_managed_billing_cycle_end_after_boundary as _calc_self_managed_cycle_end_after_boundary,
)
from .queries import (
    load_latest_subscription_renewal_order as _load_latest_subscription_renewal_order,
)
from .queries import (
    load_subscription_by_bid as _load_subscription_by_bid,
)
from .queries import (
    load_subscription_renewal_order_by_cycle as _load_subscription_renewal_order_by_cycle,
)
from .reserved_renewal_activation import (  # noqa: F401 - re-exported for import compatibility
    IncompleteReservedGrantActivationError,
    ReservedActivationTarget,
    validate_reserved_renewal_cycle_activation,
)
from .serializers import serialize_subscription as _serialize_subscription
from .subscriptions_activation import (  # noqa: F401 - re-exported for import compatibility
    _activate_subscription_for_paid_order,
    _expire_credit_bucket_balance_for_transition,
)
from .subscriptions_cycles import (  # noqa: F401 - re-exported for import compatibility
    SELF_MANAGED_BILLING_PROVIDERS,
    _calculate_billing_cycle_end,
    _is_paid_referral_invitation_renewal,
    _is_stale_manual_cycle,
    _load_billing_product_by_bid,
    _load_or_create_credit_wallet,
    _should_defer_manual_renewal_activation,
    _should_defer_subscription_renewal_activation,
    is_self_managed_billing_provider,
    load_effective_topup_subscription,
)
from .subscriptions_grants import (  # noqa: F401 - re-exported for import compatibility
    CreditGrantContext,
    _grant_paid_order_credits,
    _repair_existing_paid_order_grant_bucket,
)
from .subscriptions_lifecycle import (
    _sync_subscription_lifecycle_events,
)
from .subscriptions_repairs import (  # noqa: F401 - re-exported for import compatibility
    SubscriptionCycleRepairRecord,
    SubscriptionCycleRepairResult,
    TopupExpiryRepairRecord,
    TopupExpiryRepairResult,
    repair_subscription_cycle_mismatches,
    repair_topup_grant_expiries,
)
from .subscriptions_reserved import (  # noqa: F401 - re-exported for import compatibility
    _void_reserved_campaign_bonus_grant_for_order,
    _void_reserved_subscription_grant_for_order,
)
from .value_objects import JsonObjectMap
from .wallets import (  # noqa: F401 - re-exported for import compatibility
    load_or_create_credit_bucket_by_category,
    load_primary_credit_bucket_by_category,
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    resolve_bucket_source_type_for_category,
    sync_credit_bucket_status,
)

if TYPE_CHECKING:
    from flask import Flask

    from .dtos import BillingSubscriptionDTO


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


def _merge_provider_metadata(
    *,
    existing: object,
    provider: str,
    source: str,
    event_type: str,
    payload: dict[str, object],
    event_time: datetime | None,
) -> JsonObjectMap:
    if isinstance(existing, JsonObjectMap):
        metadata = existing.copy()
    elif isinstance(existing, dict):
        metadata = JsonObjectMap(values=dict(existing))
    else:
        metadata = JsonObjectMap()
    metadata["provider"] = provider
    metadata["latest_source"] = source
    metadata["latest_event_type"] = event_type
    metadata["latest_provider_payload"] = _normalize_json_value(payload)
    if event_time is not None:
        metadata["latest_event_time"] = event_time.isoformat()
    return _normalize_json_object(metadata)


def cancel_billing_subscription(
    app: Flask,
    creator_bid: str,
    payload: dict[str, object],
) -> BillingSubscriptionDTO:
    """Mark the current subscription to cancel at period end."""
    with app_context_scope(app), unit_of_work():
        subscription = _load_owned_subscription(
            _normalize_bid(creator_bid),
            _normalize_bid(payload.get("subscription_bid")),
        )
        if _normalize_bid(subscription.billing_provider) == "manual":
            raise_error("server.order.orderStatusError")
        if subscription.status not in (
            BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
            BILLING_SUBSCRIPTION_STATUS_PAUSED,
            BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
        ):
            raise_error("server.order.orderStatusError")
        if subscription.provider_subscription_id:
            provider = get_payment_provider(subscription.billing_provider)
            provider_result = provider.cancel_subscription(
                subscription_bid=subscription.subscription_bid,
                provider_subscription_id=subscription.provider_subscription_id,
                app=app,
            )
            subscription.metadata_json = _merge_provider_metadata(
                existing=subscription.metadata_json,
                provider=subscription.billing_provider,
                source="api_cancel",
                event_type="cancel_subscription",
                payload=provider_result.raw_response,
                event_time=None,
            ).to_metadata_json()
        subscription.cancel_at_period_end = 1
        subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        subscription.updated_at = now_utc()
        _sync_subscription_lifecycle_events(app, subscription)
        db.session.add(subscription)
        return _serialize_subscription(app, subscription)


def resume_billing_subscription(
    app: Flask,
    creator_bid: str,
    payload: dict[str, object],
) -> BillingSubscriptionDTO:
    """Resume a cancel-scheduled subscription."""
    with app_context_scope(app), unit_of_work():
        subscription = _load_owned_subscription(
            _normalize_bid(creator_bid),
            _normalize_bid(payload.get("subscription_bid")),
        )
        if _normalize_bid(subscription.billing_provider) == "manual":
            raise_error("server.order.orderStatusError")
        if subscription.status not in (
            BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
            BILLING_SUBSCRIPTION_STATUS_PAUSED,
        ):
            raise_error("server.order.orderStatusError")
        if subscription.provider_subscription_id:
            provider = get_payment_provider(subscription.billing_provider)
            provider_result = provider.resume_subscription(
                subscription_bid=subscription.subscription_bid,
                provider_subscription_id=subscription.provider_subscription_id,
                app=app,
            )
            subscription.metadata_json = _merge_provider_metadata(
                existing=subscription.metadata_json,
                provider=subscription.billing_provider,
                source="api_resume",
                event_type="resume_subscription",
                payload=provider_result.raw_response,
                event_time=None,
            ).to_metadata_json()
        subscription.cancel_at_period_end = 0
        subscription.status = BILLING_SUBSCRIPTION_STATUS_ACTIVE
        subscription.updated_at = now_utc()
        _sync_subscription_lifecycle_events(app, subscription)
        db.session.add(subscription)
        return _serialize_subscription(app, subscription)


def ensure_subscription_renewal_order(
    app: Flask,
    subscription: BillingSubscription,
    *,
    renewal_event_bid: str = "",
    scheduled_at: datetime | None = None,
) -> BillingOrder | None:
    """Ensure subscription renewal order."""
    cycle_start_at = scheduled_at or subscription.current_period_end_at
    provider_name = _normalize_bid(subscription.billing_provider).lower()
    if (
        is_manual_payment_provider(provider_name)
        and subscription.current_period_end_at is not None
    ):
        cycle_start_at = subscription.current_period_end_at
    if cycle_start_at is None:
        return None

    provider_reference_id = _normalize_bid(subscription.provider_subscription_id)
    if provider_name != "stripe" and not is_manual_payment_provider(provider_name):
        return None
    if provider_name == "stripe" and not provider_reference_id:
        return None

    product_bid = _normalize_bid(subscription.next_product_bid) or _normalize_bid(
        subscription.product_bid
    )
    product = _load_billing_product_by_bid(product_bid)
    if product is None:
        return None

    if is_self_managed_billing_provider(provider_name):
        cycle_end_at = _calc_self_managed_cycle_end_after_boundary(
            product,
            cycle_boundary_at=cycle_start_at,
        )
    else:
        cycle_end_at = _calculate_billing_cycle_end(
            product,
            cycle_start_at=cycle_start_at,
            payment_provider=provider_name,
        )
    if cycle_end_at is None:
        return None

    order = _load_subscription_renewal_order_by_cycle(
        subscription.subscription_bid,
        cycle_start_at=cycle_start_at,
        cycle_end_at=cycle_end_at,
    )
    if order is not None and (
        _is_paid_referral_invitation_renewal(order)
        or _is_preorder_order(order)
        or _normalize_bid(order.payment_provider).lower() != provider_name
        or order.status != BILLING_ORDER_STATUS_PENDING
        or (
            is_manual_payment_provider(order.payment_provider)
            and order.provider_reference_id
        )
    ):
        metadata = (
            dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
        )
        metadata["renewal_event_bid"] = _normalize_bid(renewal_event_bid) or None
        order.metadata_json = _normalize_json_object(metadata).to_metadata_json()
        db.session.add(order)
        db.session.flush()
        return order

    metadata = (
        dict(order.metadata_json)
        if order and isinstance(order.metadata_json, dict)
        else {}
    )
    metadata.update(
        _normalize_json_object(
            {
                "checkout_type": "subscription_renewal",
                "provider_reference_type": (
                    "subscription" if provider_name == "stripe" else "charge"
                ),
                "renewal_event_bid": _normalize_bid(renewal_event_bid) or None,
                "renewal_cycle_start_at": to_utc_iso(cycle_start_at),
                "renewal_cycle_end_at": to_utc_iso(cycle_end_at),
                "subscription_bid": subscription.subscription_bid,
                "product_bid": product.product_bid,
            }
        )
    )

    if order is None:
        order = BillingOrder(
            bill_order_bid=generate_id(app),
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency=product.currency,
            payable_amount=int(product.price_amount or 0),
            paid_amount=0,
            payment_provider=provider_name,
            channel=(
                "subscription"
                if provider_name == "stripe"
                else "wx_pub_qr"
                if provider_name == "wechatpay"
                else "alipay_qr"
            ),
            provider_reference_id=provider_reference_id
            if provider_name == "stripe"
            else "",
            status=BILLING_ORDER_STATUS_PENDING,
            metadata_json=metadata,
        )

    else:
        # An unissued manual order can refresh its price. Pending Stripe
        # subscription-reference rows also follow the same current contract;
        # terminal orders and cross-provider identities are preserved above.
        order.creator_bid = subscription.creator_bid
        order.product_bid = product.product_bid
        order.currency = product.currency
        order.payable_amount = int(product.price_amount or 0)
        order.payment_provider = provider_name
        order.channel = order.channel or (
            "subscription"
            if provider_name == "stripe"
            else "wx_pub_qr"
            if provider_name == "wechatpay"
            else "alipay_qr"
        )
        if provider_name == "stripe":
            order.provider_reference_id = provider_reference_id
        order.metadata_json = metadata

    db.session.add(order)
    db.session.flush()
    return order


activate_subscription_for_paid_order = _activate_subscription_for_paid_order
grant_paid_order_credits = _grant_paid_order_credits
load_subscription_by_bid = _load_subscription_by_bid
load_latest_subscription_renewal_order = _load_latest_subscription_renewal_order
load_subscription_renewal_order_by_cycle = _load_subscription_renewal_order_by_cycle
load_billing_product_by_bid = _load_billing_product_by_bid
load_or_create_credit_wallet = _load_or_create_credit_wallet
sync_subscription_lifecycle_events = _sync_subscription_lifecycle_events
merge_provider_metadata = _merge_provider_metadata
is_paid_referral_invitation_renewal = _is_paid_referral_invitation_renewal
void_reserved_subscription_grant_for_order = _void_reserved_subscription_grant_for_order
void_reserved_preorder_grant = _void_reserved_subscription_grant_for_order
