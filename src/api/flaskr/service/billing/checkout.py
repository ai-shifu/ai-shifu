"""Checkout, refund, sync, and reconciliation flows for billing orders."""

from __future__ import annotations

from contextlib import contextmanager, suppress
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flaskr.common import cache_provider
from flaskr.common.public_urls import build_payment_result_url
from flaskr.dao import db, uow
from flaskr.dao.uow import (
    app_context_scope,
    require_transaction_owner,
    unit_of_work,
)
from flaskr.i18n import _ as translate
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.native_payment_status import (
    NATIVE_PAYMENT_STATE_CANCELED,
    NATIVE_PAYMENT_STATE_FAILED,
    NATIVE_PAYMENT_STATE_PAID,
    reported_payment_currency_matches,
    resolve_native_payment_state,
)
from flaskr.service.order.payment_channel_resolution import resolve_payment_channel
from flaskr.service.order.payment_providers import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentRefundRequest,
    PaymentRefundResult,
    PaymentRequest,
    checkout_options,
    describe_query,
    get_payment_provider,
    payment_definition,
)
from flaskr.service.order.payment_providers.api import (
    CheckoutTerms,
    PaymentEvent,
    PaymentFacts,
    PaymentQueryTerms,
    SubscriptionFacts,
    creation_action,
    legacy_native_amount,
    resolve_payment_option_hint,
    saved_checkout_is_payable,
    saved_query_state,
    saved_refund_controls_state,
)
from flaskr.service.order.raw_snapshots import (
    billing_native_snapshot_query,
    native_snapshot_model,
)
from flaskr.service.user.repository import load_user_aggregate
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .campaign_provider_discounts import (
    load_current_campaign_provider_discount,
)
from .campaigns import resolve_applied_billing_campaign
from .checkout_policy import (
    _is_trial_product,
    _prepare_subscription_preorder_checkout_metadata,
    validate_upgrade_terms,
)
from .consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_INTERVAL_LABELS,
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_INIT,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_LABELS,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PENDING_ORDER_TIMEOUT_DELTA,
    BILLING_PENDING_ORDER_TIMEOUT_MINUTES,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)
from .dtos import (
    BillingCheckoutResultDTO,
    BillingOrderSyncResultDTO,
    BillingRefundResultDTO,
)
from .models import (
    BillingCampaignProviderDiscount,
    BillingOrder,
    BillingProduct,
    BillingProductProviderPrice,
    BillingSubscription,
    CreditWallet,
)
from .paid_side_effects import (
    BillingPaidOrderSideEffects,
)
from .paid_side_effects import (
    dispatch_billing_paid_order_side_effects as _dispatch_billing_paid_order_side_effects,
)
from .paid_side_effects import (
    stage_billing_paid_order_side_effects as _stage_billing_paid_order_side_effects,
)
from .payment_policy import (
    is_manual_payment_provider,
    is_provider_managed_payment_provider,
    supports_plan_checkout,
)
from .preorders import (
    CHECKOUT_ACTION_PREORDER,
    CHECKOUT_ACTION_UPGRADE_IMMEDIATE,
    PREORDER_CHECKOUT_TYPE,
)
from .preorders import (
    load_active_preorder_order as _load_active_preorder_order,
)
from .preorders import (
    normalize_checkout_action as _normalize_checkout_action,
)
from .primitives import coerce_datetime
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import to_decimal as _to_decimal
from .provider_compat import (
    _build_native_provider_options,
    _build_pingxx_provider_options,
    _is_unbound_unpaid_stripe_checkout,
    _load_billing_order_for_pingxx_event,
    _load_billing_order_for_stripe_event,
    _load_billing_subscription_for_stripe_event,
    _validate_stripe_checkout_evidence,
)
from .provider_price_mappings import (
    ProviderPriceMappingError,
    ProviderPriceRuntimeScope,
    get_current_active_provider_price_mapping,
    serialize_provider_price_mapping,
)
from .provider_recovery import (
    reconcile_checkout_before_replacement,
    stored_checkout_action,
    stored_checkout_reference,
    uses_generic_payment_recovery,
)
from .provider_snapshots import (
    _persist_billing_native_raw_snapshot,
    _persist_billing_pingxx_raw_snapshot,
    _persist_billing_raw_snapshot_from_checkout,
    _persist_billing_stripe_raw_snapshot,
    persist_query,
    persist_refund,
    refund_metadata,
)
from .provider_state import (
    BillingOrderProviderUpdateResult,
    apply_subscription_contract,
    contract_can_activate,
    contract_renewal_order_status,
    paid_upgrade_can_rebind_contract,
)
from .provider_state import (
    apply_billing_order_provider_update as _apply_billing_order_provider_update,
)
from .provider_state import (
    merge_provider_metadata as _merge_provider_metadata,
)
from .queries import (
    load_primary_active_subscription as _load_primary_active_subscription,
)
from .queries import normalize_payment_provider_hint as _normalize_payment_provider_hint
from .subscriptions import (
    load_billing_product_by_bid as _load_billing_product_by_bid,
)
from .subscriptions import (
    load_effective_topup_subscription as _load_effective_topup_subscription,
)
from .subscriptions import (
    load_subscription_by_bid as _load_subscription_by_bid,
)
from .subscriptions import (
    sync_subscription_lifecycle_events as _sync_subscription_lifecycle_events,
)
from .wallets import persist_credit_wallet_snapshot, refresh_credit_wallet_snapshot

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from flask import Flask


_RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS = {
    BILLING_ORDER_STATUS_INIT: 0,
    BILLING_ORDER_STATUS_PENDING: 0,
    BILLING_ORDER_STATUS_PAID: 1,
    BILLING_ORDER_STATUS_REFUNDED: 2,
    BILLING_ORDER_STATUS_CANCELED: 3,
    BILLING_ORDER_STATUS_TIMEOUT: 3,
    BILLING_ORDER_STATUS_FAILED: 4,
}

_BILLING_STATUS_BY_NATIVE_STATE = {
    NATIVE_PAYMENT_STATE_PAID: BILLING_ORDER_STATUS_PAID,
    NATIVE_PAYMENT_STATE_CANCELED: BILLING_ORDER_STATUS_CANCELED,
    NATIVE_PAYMENT_STATE_FAILED: BILLING_ORDER_STATUS_FAILED,
}

_CHECKOUT_PLAN_SUBJECT_PREFIX_KEYS = {
    "day": "module.billing.checkout.subject.plan.day",
    "month": "module.billing.checkout.subject.plan.month",
    "year": "module.billing.checkout.subject.plan.year",
}

_SUBSCRIPTION_CHECKOUT_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
}


@dataclass(slots=True, frozen=True)
class ProviderReferenceReconcileResult:
    """Capture the result of reconciling a provider reference."""

    status: str
    creator_bid: str | None
    bill_order_bid: str | None
    provider_reference_id: str | None
    payment_provider: str | None

    def to_task_payload(self) -> dict[str, Any]:
        """Serialize this result for task processing."""
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "bill_order_bid": self.bill_order_bid,
            "provider_reference_id": self.provider_reference_id,
            "payment_provider": self.payment_provider,
        }

    def __getitem__(self, key: str) -> object:
        """Return a task-payload field by key."""
        return self.to_task_payload()[key]


def _resolve_billing_order_expires_at(
    *,
    now: datetime | None = None,
) -> datetime:
    return (now or now_utc()) + BILLING_PENDING_ORDER_TIMEOUT_DELTA


def _resolve_effective_billing_order_expires_at(
    order: BillingOrder,
) -> datetime | None:
    if order.expires_at is not None:
        return order.expires_at
    if not _is_subscription_checkout_order(order):
        return None
    if order.created_at is None:
        return None
    return order.created_at + BILLING_PENDING_ORDER_TIMEOUT_DELTA


def _hydrate_legacy_billing_order_expires_at(
    order: BillingOrder,
) -> bool:
    if order.expires_at is not None:
        return False
    resolved = _resolve_effective_billing_order_expires_at(order)
    if resolved is None:
        return False
    order.expires_at = resolved
    return True


def _calculate_billing_order_expires_in_seconds(
    order: BillingOrder,
    *,
    now: datetime | None = None,
) -> int | None:
    resolved_expires_at = _resolve_effective_billing_order_expires_at(order)
    if resolved_expires_at is None:
        return None
    remaining = int((resolved_expires_at - (now or now_utc())).total_seconds())
    return max(0, remaining)


def _is_subscription_checkout_order(order: BillingOrder) -> bool:
    return int(order.order_type or 0) in _SUBSCRIPTION_CHECKOUT_ORDER_TYPES


def _is_same_subscription_checkout_target(
    order: BillingOrder,
    *,
    product_bid: str,
    order_type: int,
    payment_provider: str,
    channel: str,
    currency: str,
    payable_amount: int,
    checkout_metadata: dict[str, object],
    provider_price_bid: str = "",
    campaign_bid: str = "",
    campaign_provider_discount_bid: str = "",
) -> bool:
    if _normalize_bid(order.product_bid) != _normalize_bid(product_bid) or int(
        order.order_type or 0
    ) != int(order_type or 0):
        return False
    if (
        _normalize_bid(order.payment_provider) != _normalize_bid(payment_provider)
        or _normalize_bid(order.channel) != _normalize_bid(channel)
        or order.currency != currency
        or int(order.payable_amount or 0) != payable_amount
    ):
        return False
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    for key in (
        "checkout_type",
        "preorder_order_bid",
        "prepaid_offset_amount",
        "current_product_bid",
        "target_product_bid",
        "preorder_effective_at",
        "renewal_cycle_start_at",
        "renewal_cycle_end_at",
    ):
        if metadata.get(key) != checkout_metadata.get(key):
            return False
    if _normalize_bid(order.campaign_bid) != _normalize_bid(campaign_bid):
        return False
    if _normalize_bid(metadata.get("campaign_provider_discount_bid")) != _normalize_bid(
        campaign_provider_discount_bid
    ):
        return False
    normalized_provider_price_bid = _normalize_bid(provider_price_bid)
    if not normalized_provider_price_bid:
        return True
    return (
        _normalize_bid(metadata.get("provider_price_bid"))
        == normalized_provider_price_bid
    )


def _is_managed_pending_subscription_checkout_order(order: BillingOrder) -> bool:
    if int(order.status or 0) != BILLING_ORDER_STATUS_PENDING:
        return False
    if not _is_subscription_checkout_order(order):
        return False
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    return str(metadata.get("checkout_type") or "").strip() != PREORDER_CHECKOUT_TYPE


def _is_billing_order_expired(
    order: BillingOrder,
    *,
    now: datetime | None = None,
) -> bool:
    resolved_expires_at = _resolve_effective_billing_order_expires_at(order)
    if resolved_expires_at is None:
        return False
    return resolved_expires_at <= (now or now_utc())


def _mark_billing_order_invalidated(
    order: BillingOrder,
    *,
    target_status: int,
    reason: str,
    invalidated_at: datetime | None = None,
    replaced_by_bill_order_bid: str = "",
) -> None:
    now = invalidated_at or now_utc()
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    metadata["invalidated_reason"] = reason
    metadata["invalidated_at"] = now.isoformat()
    if replaced_by_bill_order_bid:
        metadata["replaced_by_bill_order_bid"] = replaced_by_bill_order_bid
    order.metadata_json = _normalize_json_object(metadata).to_metadata_json()
    order.status = target_status
    order.updated_at = now
    order.failed_at = order.failed_at or now
    order.failure_code = reason
    if target_status == BILLING_ORDER_STATUS_TIMEOUT:
        order.failure_message = f"Billing order expired after {BILLING_PENDING_ORDER_TIMEOUT_MINUTES} minutes"
    elif target_status == BILLING_ORDER_STATUS_CANCELED:
        order.failure_message = "Billing order invalidated by a newer package checkout"


def _expire_pending_billing_order_if_due(
    order: BillingOrder,
    *,
    now: datetime | None = None,
) -> bool:
    # Any order carrying an explicit deadline can time out; orders without
    # one keep the legacy subscription-only behaviour through
    # _resolve_effective_billing_order_expires_at.
    if int(order.status or 0) != BILLING_ORDER_STATUS_PENDING or not (
        _is_billing_order_expired(order, now=now)
    ):
        return False
    _mark_billing_order_invalidated(
        order,
        target_status=BILLING_ORDER_STATUS_TIMEOUT,
        reason="timeout",
        invalidated_at=now,
    )
    return True


def _build_subscription_checkout_lock_key(app: Flask, creator_bid: str) -> str:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu") or "ai-shifu").rstrip(
        ":"
    )
    return f"{prefix}:billing:subscription-checkout:{creator_bid}"


@contextmanager
def _subscription_checkout_lock(app: Flask, creator_bid: str) -> Iterator[None]:
    """Serialize subscription checkout per creator to avoid duplicate pending orders without taking row locks on the pending-order query itself."""
    lock = cache_provider.cache.lock(
        _build_subscription_checkout_lock_key(app, creator_bid),
        timeout=30,
        blocking_timeout=10,
    )
    acquired = bool(lock.acquire(blocking=True))
    if not acquired:
        raise_error("server.billing.subscriptionCheckoutBusy")
    try:
        yield
    finally:
        with suppress(Exception):
            lock.release()


_CREDIT_LEDGER_LOCK_TIMEOUT_SECONDS = 60
_CREDIT_LEDGER_LOCK_BLOCKING_TIMEOUT_SECONDS = 60


def _build_credit_ledger_lock_key(app: Flask, creator_bid: str) -> str:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu") or "ai-shifu").rstrip(
        ":"
    )
    scope = str(creator_bid or "").strip() or "unknown"
    return f"{prefix}:billing:credit-ledger:{scope}"


@contextmanager
def _credit_ledger_lock(app: Flask, creator_bid: str) -> Iterator[None]:
    """Serialize credit-ledger writes for a creator.

    Concurrent order syncs for the same creator (timeout scan vs renewal
    reconcile vs manual sync) otherwise both pass the ``existing_entry`` grant
    pre-check and then trip the ``(creator_bid, idempotency_key)`` unique key at
    commit, and contend on the same ``bill_orders`` row (seen in production as
    ``Lock wait timeout``). Serializing per creator lets the second caller re-run
    the pre-check inside the lock, find the first caller's committed grant, and
    take the idempotent repair path instead. Mirrors ``_usage_settlement_lock``
    in ``settlement.py``: on lock-backend failure it degrades to running without
    the lock rather than blocking the sync.
    """
    lock = cache_provider.cache.lock(
        _build_credit_ledger_lock_key(app, creator_bid),
        timeout=_CREDIT_LEDGER_LOCK_TIMEOUT_SECONDS,
        blocking_timeout=_CREDIT_LEDGER_LOCK_BLOCKING_TIMEOUT_SECONDS,
    )
    acquired = False
    try:
        if lock is not None:
            acquired = bool(lock.acquire(blocking=True))
    except Exception as exc:
        # Lock-backend failure (e.g. Redis outage): degrade to running without
        # the lock rather than crashing the order sync. The grant idempotency
        # pre-check and unique key still guard correctness.
        app.logger.warning(
            "credit-ledger lock acquire failed; running without lock: %s", exc
        )
    if lock is not None and not acquired:
        # Blocking timeout elapsed under contention: acquire() returned False.
        # Log so this fail-open path is observable rather than silent.
        app.logger.warning(
            "credit-ledger lock not acquired within timeout for %s; "
            "running without lock",
            _build_credit_ledger_lock_key(app, creator_bid),
        )
    try:
        yield
    finally:
        if acquired and lock is not None:
            try:
                lock.release()
            except Exception as exc:
                app.logger.warning("credit-ledger lock release failed: %s", exc)


def _load_active_pending_subscription_orders(
    creator_bid: str,
) -> list[BillingOrder]:
    orders = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == creator_bid,
            BillingOrder.status.in_(
                (
                    BILLING_ORDER_STATUS_PENDING,
                    BILLING_ORDER_STATUS_TIMEOUT,
                    BILLING_ORDER_STATUS_FAILED,
                )
            ),
            BillingOrder.order_type.in_(_SUBSCRIPTION_CHECKOUT_ORDER_TYPES),
        )
        .order_by(BillingOrder.id.desc())
        .all()
    )
    return [
        order
        for order in orders
        if _is_managed_pending_subscription_checkout_order(order)
        or (
            (uses_generic_payment_recovery(order.payment_provider))
            and order.provider_reference_id
        )
    ]


def create_billing_subscription_checkout(
    app: Flask,
    creator_bid: str,
    payload: dict[str, object],
) -> BillingCheckoutResultDTO:
    """Create a subscription checkout order for the current creator."""
    # Prepare and commit, call the provider, finalize: nested, neither unit of
    # work would commit, so an outer rollback could orphan the charge.
    require_transaction_owner("billing subscription checkout")
    normalized_creator_bid = _normalize_bid(creator_bid)
    product_bid = _normalize_bid(payload.get("product_bid"))
    checkout_action = _normalize_checkout_action(payload.get("action"))
    payment_provider, channel = _resolve_billing_payment_channel(
        payload,
        default_pingxx_channel="alipay_qr",
    )

    # The lock spans both steps: the order row is created and committed under
    # it, and only then is the provider called with no transaction open.
    with (
        app_context_scope(app),
        _subscription_checkout_lock(app, normalized_creator_bid),
    ):
        closed_order_bids: set[str] = set()
        while True:
            try:
                prepared = _prepare_subscription_checkout(
                    app,
                    normalized_creator_bid=normalized_creator_bid,
                    product_bid=product_bid,
                    checkout_action=checkout_action,
                    payment_provider=payment_provider,
                    channel=channel,
                )
                break
            except _ManualPaymentNeedsClosureError as pending:
                if pending.bill_order_bid in closed_order_bids:
                    raise_error("server.order.orderStatusError")
                closed_order_bids.add(pending.bill_order_bid)
                _close_manual_payment_before_replacement(
                    app,
                    normalized_creator_bid,
                    pending.bill_order_bid,
                )
        if isinstance(prepared, _ReopenExistingOrder):
            prepared = _prepare_existing_billing_order_checkout(
                app,
                creator_bid=normalized_creator_bid,
                bill_order_bid=prepared.bill_order_bid,
                product_bid=prepared.product_bid,
                requested_channel=prepared.requested_channel,
            )
        if isinstance(prepared, BillingCheckoutResultDTO):
            return prepared
        return _run_provider_checkout(app, prepared)


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
        if not supports_plan_checkout(payment_provider):
            raise_error("server.pay.payChannelNotSupport")
        provider_price_mapping: BillingProductProviderPrice | None = None
        if payment_definition(payment_provider).capabilities.catalog:
            channel = payment_definition(payment_provider).default_channel
            provider_price_mapping = _resolve_required_provider_price_mapping(
                app,
                product=product,
                provider=payment_provider,
            )

        current_subscription = _load_primary_active_subscription(
            normalized_creator_bid,
            as_of=now_utc(),
        )
        if current_subscription is not None:
            current_subscription = _lock_subscription_for_checkout(current_subscription)
        prepaid_offset_amount = 0
        replaced_preorder_order = None
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
                prepaid_offset_amount, paid_preorder_order = validate_upgrade_terms(
                    subscription=subscription,
                    current_product=current_product,
                    target_product=product,
                    active_preorder_order=active_preorder_order,
                    payment_provider=payment_provider,
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
                order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
                order_metadata = {
                    "checkout_type": "subscription",
                    "effective_mode": "immediate",
                    "current_product_bid": (
                        current_product.product_bid
                        if current_product is not None
                        else None
                    ),
                    "target_product_bid": product.product_bid,
                    "prepaid_offset_amount": prepaid_offset_amount,
                    "preorder_order_bid": (
                        replaced_preorder_order.bill_order_bid
                        if replaced_preorder_order is not None
                        else None
                    ),
                }
            else:
                raise_error("server.order.orderStatusError")
            subscription.updated_at = now_utc()

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
        campaign_provider_discount = _resolve_campaign_provider_discount(
            applied_campaign=applied_campaign,
            product=product,
            provider_price_mapping=provider_price_mapping,
        )

        pending_orders = _load_active_pending_subscription_orders(
            normalized_creator_bid
        )
        expected_campaign_provider_discount_bid = (
            campaign_provider_discount.campaign_provider_discount_bid
            if campaign_provider_discount is not None
            else ""
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
                and (uses_generic_payment_recovery(pending_order.payment_provider))
                and pending_order.provider_reference_id
            ):
                raise _ManualPaymentNeedsClosureError(pending_order.bill_order_bid)
            if _expire_pending_billing_order_if_due(pending_order, now=now):
                db.session.add(pending_order)
                continue
            if _is_same_subscription_checkout_target(
                pending_order,
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
                campaign_provider_discount_bid=expected_campaign_provider_discount_bid,
            ):
                if reusable_order is None:
                    reusable_order = pending_order
                else:
                    duplicate_reusable_orders.append(pending_order)
                continue
            conflicting_pending_orders.append(pending_order)

        for duplicate_order in duplicate_reusable_orders:
            _prepare_pending_order_for_replacement(app, duplicate_order)
            _mark_billing_order_invalidated(
                duplicate_order,
                target_status=BILLING_ORDER_STATUS_CANCELED,
                reason="replaced_by_new_package",
                invalidated_at=now,
                replaced_by_bill_order_bid=reusable_order.bill_order_bid
                if reusable_order is not None
                else "",
            )
            db.session.add(duplicate_order)

        if reusable_order is not None:
            if current_subscription is None:
                original_subscription = _load_subscription_by_bid(
                    reusable_order.subscription_bid
                )
                if (
                    original_subscription is None
                    or original_subscription.creator_bid != normalized_creator_bid
                ):
                    raise_error("server.order.orderStatusError")
                subscription = original_subscription
            for conflicting_order in conflicting_pending_orders:
                _prepare_pending_order_for_replacement(app, conflicting_order)
                _mark_billing_order_invalidated(
                    conflicting_order,
                    target_status=BILLING_ORDER_STATUS_CANCELED,
                    reason="replaced_by_new_package",
                    invalidated_at=now,
                    replaced_by_bill_order_bid=reusable_order.bill_order_bid,
                )
                db.session.add(conflicting_order)

            if subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT:
                subscription.billing_provider = reusable_order.payment_provider
                subscription.updated_at = now

            db.session.add(subscription)
            db.session.flush()
            # The reopen flow owns its own units of work, so it has to run
            # after this one commits.
            return _ReopenExistingOrder(
                bill_order_bid=reusable_order.bill_order_bid,
                product_bid=product.product_bid,
                requested_channel=channel,
            )

        db.session.add(subscription)
        db.session.flush()

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
                _build_campaign_provider_discount_order_metadata(
                    campaign_provider_discount
                )
            )
        order_metadata = _normalize_json_object(
            order_metadata_payload
        ).to_metadata_json()

        order = BillingOrder(
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
            metadata_json=order_metadata,
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
        for conflicting_order in conflicting_pending_orders:
            _prepare_pending_order_for_replacement(app, conflicting_order)
            _mark_billing_order_invalidated(
                conflicting_order,
                target_status=BILLING_ORDER_STATUS_CANCELED,
                reason="replaced_by_new_package",
                invalidated_at=now,
                replaced_by_bill_order_bid=order.bill_order_bid,
            )
            db.session.add(conflicting_order)
        db.session.add(order)
        db.session.flush()

        requires_provider_subscription_checkout = bool(
            payment_definition(payment_provider).capabilities.subscription_create
            and campaign_provider_discount is not None
        )
        if payable_amount == 0 and not requires_provider_subscription_checkout:
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


def create_billing_topup_checkout(
    app: Flask,
    creator_bid: str,
    payload: dict[str, object],
) -> BillingCheckoutResultDTO:
    """Create a one-time topup checkout order for the current creator."""
    require_transaction_owner("billing top-up checkout")
    normalized_creator_bid = _normalize_bid(creator_bid)
    product_bid = _normalize_bid(payload.get("product_bid"))
    payment_provider, channel = _resolve_billing_payment_channel(
        payload,
        default_pingxx_channel="alipay_qr",
    )

    with app_context_scope(app):
        prepared = _prepare_topup_checkout(
            app,
            normalized_creator_bid=normalized_creator_bid,
            product_bid=product_bid,
            payment_provider=payment_provider,
            channel=channel,
        )
        return _run_provider_checkout(app, prepared)


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
        if payment_definition(payment_provider).capabilities.catalog:
            channel = payment_definition(payment_provider).default_channel
            provider_price_mapping = _resolve_required_provider_price_mapping(
                app,
                product=product,
                provider=payment_provider,
            )
        if _load_effective_topup_subscription(normalized_creator_bid) is None:
            raise_error("server.billing.subscriptionInactive")
        resolved_campaign = resolve_applied_billing_campaign(
            product,
            order_type=BILLING_ORDER_TYPE_TOPUP,
        )
        applied_campaign = resolved_campaign
        campaign_provider_discount = _resolve_campaign_provider_discount(
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


def create_billing_order_checkout(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
    payload: dict[str, object],
) -> BillingCheckoutResultDTO:
    """Reopen a pending billing payment while preserving each attempt's identity."""
    # An expiry detected below is committed in its own unit of work before the
    # error is raised; nested, that write would roll back with the caller.
    require_transaction_owner("billing order checkout", app)
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    requested_channel = _normalize_bid(payload.get("channel"))

    with (
        app_context_scope(app),
        _subscription_checkout_lock(app, normalized_creator_bid),
    ):
        now = now_utc()
        # Step 1 - load and validate; an expiry detected here must be durable
        # before the caller sees the error, so it gets its own unit of work.
        with unit_of_work():
            order = (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.creator_bid == normalized_creator_bid,
                    BillingOrder.bill_order_bid == normalized_order_bid,
                )
                .order_by(BillingOrder.id.desc())
                .first()
            )
            if order is None:
                raise_error("server.order.orderNotFound")
            if _hydrate_legacy_billing_order_expires_at(order):
                db.session.add(order)
            if order.status != BILLING_ORDER_STATUS_PENDING:
                raise_error("server.order.orderStatusError")
            expired = _expire_pending_billing_order_if_due(order, now=now)
            if expired:
                db.session.add(order)
        if expired:
            raise_error("server.order.orderPayExpired")

        # Step 2 - reopen the provider checkout for the still-pending order;
        # the reopen flow owns its own units of work around the provider call.
        prepared = _prepare_existing_billing_order_checkout(
            app,
            creator_bid=normalized_creator_bid,
            bill_order_bid=order.bill_order_bid,
            product_bid=order.product_bid,
            requested_channel=requested_channel,
        )
        if isinstance(prepared, BillingCheckoutResultDTO):
            return prepared
        return _run_provider_checkout(app, prepared)


def _load_billing_order_by_bid(
    bill_order_bid: str, *, for_update: bool = False
) -> BillingOrder | None:
    query = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.bill_order_bid == bill_order_bid,
    ).order_by(BillingOrder.id.desc())
    if for_update:
        query = query.with_for_update().populate_existing()
    return query.first()


def _load_reopen_targets(
    bill_order_bid: str, product_bid: str
) -> tuple[BillingOrder, BillingProduct]:
    order = _load_billing_order_by_bid(bill_order_bid)
    if order is None:
        raise_error("server.order.orderNotFound")
    # A webhook or a sync can settle the order between the two units of work
    # of the reopen flow; a settled order must not be reopened.
    if int(order.status or 0) != BILLING_ORDER_STATUS_PENDING:
        raise_error("server.order.orderStatusError")
    product = _load_billing_product_by_bid(product_bid)
    if product is None:
        raise_error("server.order.orderNotFound")
    return order, product


def _prepare_existing_billing_order_checkout(
    app: Flask,
    *,
    creator_bid: str,
    bill_order_bid: str,
    product_bid: str,
    requested_channel: str = "",
) -> BillingCheckoutResultDTO | _ProviderCheckoutRequest:
    """Reopen a pending order: read, reconcile at the provider, build the request.

    Provider reconciliation runs between persistence steps. A saved native QR
    is reusable only while the provider confirms that its trade is payable.
    """
    pending_hosted_reference = ""
    saved_manual_checkout: BillingCheckoutResultDTO | None = None
    manual_attempt_needs_replacement = False
    with unit_of_work():
        order, product = _load_reopen_targets(bill_order_bid, product_bid)
        if (
            uses_generic_payment_recovery(order.payment_provider)
            and order.provider_reference_id
        ):
            metadata = (
                order.metadata_json if isinstance(order.metadata_json, dict) else {}
            )
            extra = metadata.get("provider_extra") or {}
            if (not requested_channel or requested_channel == order.channel) and (
                extra.get("credential")
                or extra.get("jsapi_params")
                or metadata.get("payment_action")
            ):
                response = _build_checkout_response_payload(
                    order,
                    payment_provider=order.payment_provider,
                    payment_mode=_resolve_billing_order_payment_mode(order),
                    status="pending",
                    reused_existing_order=True,
                )
                response["payment_payload"] = _build_manual_payment_payload(
                    order.provider_reference_id,
                    metadata.get("checkout") or {},
                    extra,
                )
                response["payment_action"] = metadata.get(
                    "payment_action"
                ) or creation_action(
                    order.payment_provider,
                    order.channel,
                    PaymentCreationResult(
                        order.provider_reference_id,
                        metadata.get("checkout") or {},
                        extra=extra,
                    ),
                )
                saved_manual_checkout = BillingCheckoutResultDTO(**response)
            manual_attempt_needs_replacement = True
        if payment_definition(order.payment_provider).capabilities.catalog:
            provider_price_mapping = _resolve_required_provider_price_mapping(
                app,
                product=product,
                provider=order.payment_provider,
            )
            order_metadata = (
                order.metadata_json if isinstance(order.metadata_json, dict) else {}
            )
            if not _stored_provider_price_snapshot_matches_mapping(
                order,
                provider_price_mapping,
                metadata=order_metadata,
            ):
                raise_error("server.order.orderStatusError")
            stored_checkout_result = _build_stored_checkout_result(app, order)
            if stored_checkout_result is not None:
                return stored_checkout_result
            pending_hosted_reference = stored_checkout_reference(order)

    if saved_manual_checkout is not None:
        if (
            is_manual_payment_provider(saved_manual_checkout.provider)
            and not payment_definition(
                saved_manual_checkout.provider
            ).capabilities.poll_provider
        ):
            return saved_manual_checkout
        sync_billing_order(app, creator_bid, bill_order_bid, {})
        with unit_of_work():
            order = _load_billing_order_by_bid(bill_order_bid)
            if order is None or order.status == BILLING_ORDER_STATUS_PAID:
                raise_error("server.order.orderStatusError")
            metadata = (
                order.metadata_json if isinstance(order.metadata_json, dict) else {}
            )
            if order.status == BILLING_ORDER_STATUS_PENDING and (
                saved_checkout_is_payable(order.payment_provider, metadata)
                # A contract-only query need not report an open payment.
                # Reusing the same action creates or cancels no payment.
                or (
                    is_provider_managed_payment_provider(order.payment_provider)
                    and saved_manual_checkout.payment_action is not None
                    and saved_manual_checkout.payment_action.type
                    in {"redirect", "sdk_confirm"}
                    and (order.expires_at is None or order.expires_at > now_utc())
                )
            ):
                return saved_manual_checkout

    if manual_attempt_needs_replacement:
        _close_manual_payment_before_replacement(app, creator_bid, bill_order_bid)
        with unit_of_work():
            old_order = _load_billing_order_by_bid(bill_order_bid)
            if old_order is None or old_order.status != BILLING_ORDER_STATUS_CANCELED:
                raise_error("server.order.orderStatusError")
            old_metadata = (
                old_order.metadata_json
                if isinstance(old_order.metadata_json, dict)
                else {}
            )
            metadata = dict(old_metadata)
            for key in (
                "checkout",
                "provider_extra",
                "latest_provider_payload",
                "latest_event_time",
                "latest_source",
                "latest_event_type",
                "invalidated_reason",
                "invalidated_at",
            ):
                metadata.pop(key, None)
            metadata["replaces_bill_order_bid"] = old_order.bill_order_bid
            replacement = BillingOrder(
                bill_order_bid=generate_id(app),
                creator_bid=old_order.creator_bid,
                order_type=old_order.order_type,
                product_bid=old_order.product_bid,
                subscription_bid=old_order.subscription_bid,
                currency=old_order.currency,
                payable_amount=old_order.payable_amount,
                paid_amount=0,
                payment_provider=old_order.payment_provider,
                channel=requested_channel or old_order.channel,
                provider_reference_id="",
                status=BILLING_ORDER_STATUS_PENDING,
                expires_at=_resolve_billing_order_expires_at(now=now_utc()),
                metadata_json=metadata,
                campaign_bid=old_order.campaign_bid,
                campaign_benefit_type=old_order.campaign_benefit_type,
                campaign_discount_amount=old_order.campaign_discount_amount,
                campaign_bonus_credit_amount=old_order.campaign_bonus_credit_amount,
            )
            old_order.metadata_json = {
                **old_metadata,
                "replaced_by_bill_order_bid": replacement.bill_order_bid,
            }
            db.session.add(replacement)
            db.session.flush()
            bill_order_bid = replacement.bill_order_bid

    if pending_hosted_reference:
        reconcile_checkout_before_replacement(
            app,
            provider_name=order.payment_provider,
            bill_order_bid=bill_order_bid,
            reference=pending_hosted_reference,
            client=get_payment_provider(order.payment_provider),
        )

    with unit_of_work():
        order, product = _load_reopen_targets(bill_order_bid, product_bid)
        provider_price_mapping = (
            _resolve_required_provider_price_mapping(
                app, product=product, provider=order.payment_provider
            )
            if payment_definition(order.payment_provider).capabilities.catalog
            else None
        )
        order.channel = (
            requested_channel or _normalize_bid(order.channel) or "alipay_qr"
        )
        return _build_provider_checkout_request(
            app,
            creator_bid=creator_bid,
            order=order,
            product=product,
            payment_provider=order.payment_provider,
            payment_mode=_resolve_billing_order_payment_mode(order),
            channel=order.channel,
            reused_existing_order=True,
            provider_price_mapping=provider_price_mapping,
        )


class _ManualPaymentNeedsClosureError(Exception):
    """Move provider I/O out of the checkout preparation transaction."""

    def __init__(self, bill_order_bid: str) -> None:
        super().__init__(bill_order_bid)
        self.bill_order_bid = bill_order_bid


def _record_confirmed_manual_payment_closure(order: BillingOrder) -> bool:
    """Persist closure confirmed by the latest provider reconciliation."""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    payload = metadata.get("latest_provider_payload") or {}
    closed = (
        metadata.get(
            "latest_payment_state", saved_query_state(order.payment_provider, payload)
        )
        == "canceled"
    )
    if not closed:
        return False
    # A timeout cannot become canceled through the generic status guard.
    order.status = BILLING_ORDER_STATUS_CANCELED
    order.updated_at = now_utc()
    db.session.add(order)
    return True


def _close_manual_payment_before_replacement(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
) -> None:
    """Reconcile, close, and confirm an old attempt before allowing a new one."""
    sync_billing_order(app, creator_bid, bill_order_bid, {})
    with unit_of_work():
        order = _load_billing_order_by_bid(bill_order_bid)
        if order is None or order.creator_bid != creator_bid:
            raise_error("server.order.orderNotFound")
        if order.status == BILLING_ORDER_STATUS_PAID:
            # Payment has already been applied durably; re-evaluate the plan on retry.
            raise_error("server.order.orderStatusError")
        if order.status == BILLING_ORDER_STATUS_CANCELED:
            return
        if _record_confirmed_manual_payment_closure(order):
            return
        provider_name = order.payment_provider
        reference = order.provider_reference_id
        reference_type = (
            payment_definition(provider_name).close_reference_type
            or _resolve_billing_order_provider_reference_type(order)
            or "payment"
        )
    if not payment_definition(provider_name).capabilities.close:
        raise_error("server.order.orderStatusError")
    result = get_payment_provider(provider_name).cancel_payment(
        provider_reference=reference,
        reference_type=reference_type,
        app=app,
    )
    if not result.is_closed:
        raise_error("server.order.orderStatusError")
    if not payment_definition(provider_name).capabilities.query:
        with unit_of_work():
            order = _load_billing_order_by_bid(bill_order_bid, for_update=True)
            if (
                order is None
                or order.creator_bid != creator_bid
                or order.payment_provider != provider_name
                or order.provider_reference_id != reference
                or order.status
                in {BILLING_ORDER_STATUS_PAID, BILLING_ORDER_STATUS_REFUNDED}
            ):
                raise_error("server.order.orderStatusError")
            metadata = (
                order.metadata_json if isinstance(order.metadata_json, dict) else {}
            )
            order.metadata_json = {
                **metadata,
                "latest_payment_state": "canceled",
                "latest_provider_payload": result.raw_response,
            }
            _record_confirmed_manual_payment_closure(order)
            persist_query(
                order,
                PaymentNotificationResult(
                    reference,
                    "manual_close",
                    result.raw_response,
                    facts=PaymentFacts(
                        state="canceled",
                        provider_reference=reference,
                        raw_status=result.status,
                        source="query",
                    ),
                ),
            )
        return
    sync_billing_order(app, creator_bid, bill_order_bid, {})
    with unit_of_work():
        order = _load_billing_order_by_bid(bill_order_bid)
        if (
            order is None
            or order.creator_bid != creator_bid
            or order.status == BILLING_ORDER_STATUS_PAID
        ):
            raise_error("server.order.orderStatusError")
        if not _record_confirmed_manual_payment_closure(order):
            raise_error("server.order.orderStatusError")


def _prepare_pending_order_for_replacement(app: Flask, order: BillingOrder) -> None:
    """Expire the stale provider session of an order about to be replaced.

    This one deliberately stays inside the caller's transaction: the session
    has to be expired at the provider BEFORE the order is canceled locally.
    Deferring it past the commit would leave a payable Stripe session pointing
    at an order that no longer accepts payment.
    """
    if (
        uses_generic_payment_recovery(order.payment_provider)
        and order.provider_reference_id
    ):
        raise _ManualPaymentNeedsClosureError(order.bill_order_bid)
    reconcile_checkout_before_replacement(
        app,
        provider_name=order.payment_provider,
        bill_order_bid=order.bill_order_bid,
        reference=stored_checkout_reference(order),
        client=get_payment_provider(order.payment_provider),
    )


def _build_stored_checkout_result(
    app: Flask, order: BillingOrder
) -> BillingCheckoutResultDTO | None:
    action = stored_checkout_action(app, order)
    if action is None or action.type != "redirect" or not action.url:
        return None
    response = _build_checkout_response_payload(
        order,
        payment_provider=order.payment_provider,
        payment_mode=_resolve_billing_order_payment_mode(order),
        status="pending",
        reused_existing_order=True,
    )
    response.update(
        payment_action=action,
        redirect_url=action.url,
        checkout_session_id=action.session_id,
    )
    return BillingCheckoutResultDTO(**response)


@dataclass(slots=True)
class _PreparedBillingRefund:
    """Detached original request and any durably received provider response."""

    creator_bid: str
    order_bid: str
    provider_name: str
    provider_reference: str
    paid_amount: int
    request: PaymentRefundRequest
    response: PaymentRefundResult | None = None


def _load_refund_order(
    creator_bid: str, order_bid: str, *, for_update: bool = False
) -> BillingOrder:
    query = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.creator_bid == creator_bid,
        BillingOrder.bill_order_bid == order_bid,
    ).order_by(BillingOrder.id.desc())
    if for_update:
        query = query.with_for_update().populate_existing()
    order = query.first()
    if order is None:
        raise_error("server.order.orderNotFound")
    return order


def _refund_admission(order: BillingOrder) -> BillingRefundResultDTO | None:
    if not payment_definition(order.payment_provider).capabilities.refund:
        return BillingRefundResultDTO(
            bill_order_bid=order.bill_order_bid,
            provider=order.payment_provider,
            status="unsupported",
        )
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    operation = metadata.get("refund_operation") or {}
    recoverable = isinstance(operation, dict) and operation.get("status") in {
        "prepared",
        "provider_completed",
        "awaiting_confirmation",
    }
    if order.status == BILLING_ORDER_STATUS_REFUNDED and not recoverable:
        return BillingRefundResultDTO(
            bill_order_bid=order.bill_order_bid,
            provider=order.payment_provider,
            status="refunded",
            refund_reference_id=metadata.get("refund_reference_id") or None,
        )
    if order.status not in {BILLING_ORDER_STATUS_PAID, BILLING_ORDER_STATUS_REFUNDED}:
        raise_error("server.order.orderStatusError")
    return None


@contextmanager
def _billing_refund_lock(
    app: Flask, order_bid: str
) -> Iterator[cache_provider.RenewableLockLease]:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu") or "ai-shifu").rstrip(
        ":"
    )
    lock = cache_provider.cache.lock(
        f"{prefix}:billing:refund:{order_bid}",
        timeout=60,
        blocking_timeout=60,
        thread_local=False,
    )
    if not lock or not lock.acquire(blocking=True):
        raise_error("server.order.orderStatusError")
    lease = cache_provider.RenewableLockLease(lock)
    try:
        yield lease
    finally:
        lease.release_checked()


def _prepare_billing_refund(
    app: Flask,
    creator_bid: str,
    order_bid: str,
    *,
    amount: int | None,
    reason: str,
    lease: cache_provider.RenewableLockLease,
) -> _PreparedBillingRefund | BillingRefundResultDTO:
    with unit_of_work():
        order = _load_refund_order(creator_bid, order_bid, for_update=True)
        terminal = _refund_admission(order)
        if terminal is not None:
            return terminal
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        stored = metadata.get("refund_operation") or {}
        operation = dict(stored) if isinstance(stored, dict) else {}
        if operation.get("status") == "provider_failed":
            # A definite rejection may be retried as a new operation; uncertain
            # transport outcomes always retain the original request and key.
            history = list(metadata.get("refund_operation_history") or [])
            metadata = {**metadata, "refund_operation_history": [*history, operation]}
            operation = {}
        if operation:
            try:
                request = PaymentRefundRequest(**operation["request"])
                response = (
                    PaymentRefundResult(**operation["response"])
                    if operation.get("response")
                    else None
                )
            except (KeyError, TypeError, ValueError):
                raise_error("server.order.orderStatusError")
            if (
                operation.get("provider") != order.payment_provider
                or operation.get("provider_reference") != order.provider_reference_id
                or operation.get("paid_amount") != int(order.paid_amount or 0)
            ):
                raise_error("server.order.orderStatusError")
            if (
                request.order_bid != order.bill_order_bid
                or not request.metadata.get("idempotency_key")
                or request.metadata["idempotency_key"]
                != operation.get("idempotency_key")
            ):
                raise_error("server.order.orderStatusError")
            if (
                response is None
                and order.status == BILLING_ORDER_STATUS_PAID
                and (request.amount != amount or (request.reason or "") != reason)
            ):
                raise_error("server.order.orderStatusError")
        else:
            key = f"billing-refund:{order.bill_order_bid}:{generate_id(app)}"
            request = PaymentRefundRequest(
                order_bid=order.bill_order_bid,
                amount=amount,
                reason=reason or None,
                metadata={**refund_metadata(order), "idempotency_key": key},
            )
            response = None
            operation = {
                "idempotency_key": key,
                "status": "prepared",
                "provider": order.payment_provider,
                "provider_reference": order.provider_reference_id,
                "paid_amount": int(order.paid_amount or 0),
                "request": asdict(request),
            }
        if response is None and order.status == BILLING_ORDER_STATUS_REFUNDED:
            # A verified refund callback may win before the response is saved.
            response = PaymentRefundResult(
                metadata.get("refund_reference_id") or "",
                metadata.get("latest_provider_payload") or {},
                "succeeded",
            )
            operation.update(status="provider_completed", response=asdict(response))
        order.metadata_json = {**metadata, "refund_operation": operation}
        db.session.add(order)
        lease.check_owned()
        return _PreparedBillingRefund(
            creator_bid,
            order_bid,
            order.payment_provider,
            order.provider_reference_id,
            int(order.paid_amount or 0),
            request,
            response,
        )


def _store_billing_refund_response(
    prepared: _PreparedBillingRefund, result: PaymentRefundResult
) -> PaymentRefundResult:
    """Keep the receipt durable even if subsequent storage or wallet work fails."""
    with unit_of_work():
        order = _load_refund_order(
            prepared.creator_bid, prepared.order_bid, for_update=True
        )
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        operation = dict(metadata.get("refund_operation") or {})
        if (
            operation.get("idempotency_key")
            != prepared.request.metadata["idempotency_key"]
        ):
            raise_error("server.order.orderStatusError")
        if operation.get("response"):
            stored = PaymentRefundResult(**operation["response"])
            merged = stored.merge_receipt(result)
            if merged != stored:
                operation.setdefault("initial_response", asdict(stored))
                operation["response"] = asdict(merged)
                if str(stored.status or "").lower() not in {
                    "succeeded",
                    "failed",
                    "canceled",
                }:
                    operation["status"] = (
                        "provider_completed"
                        if merged.status == "succeeded"
                        else "provider_failed"
                        if merged.status in {"failed", "canceled"}
                        else operation["status"]
                    )
                order.metadata_json = {
                    **metadata,
                    "refund_operation": operation,
                    "refund_reference_id": merged.provider_reference,
                }
            return merged
        status = str(result.status or "").lower()
        operation.update(
            status="provider_failed"
            if status in {"failed", "canceled"}
            else "provider_completed"
            if status == "succeeded"
            else "awaiting_confirmation",
            response=asdict(result),
        )
        order.metadata_json = {**metadata, "refund_operation": operation}
        db.session.add(order)
        return result


def refund_billing_order(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
    payload: dict[str, object],
) -> BillingRefundResultDTO:
    """Prepare durably, call the provider, retain its receipt, then settle locally."""
    require_transaction_owner("billing refund", app)
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    refund_reason = _normalize_bid(payload.get("reason"))
    refund_amount_value = payload.get("amount")
    refund_amount = None
    if refund_amount_value not in (None, ""):
        refund_amount = int(refund_amount_value)

    with app_context_scope(app):
        with unit_of_work(discard=True):
            terminal = _refund_admission(
                _load_refund_order(normalized_creator_bid, normalized_order_bid)
            )
            if terminal is not None:
                return terminal
        try:
            with _billing_refund_lock(app, normalized_order_bid) as lease:
                prepared = _prepare_billing_refund(
                    app,
                    normalized_creator_bid,
                    normalized_order_bid,
                    amount=refund_amount,
                    reason=refund_reason,
                    lease=lease,
                )
                if isinstance(prepared, BillingRefundResultDTO):
                    return prepared
                refund_result = prepared.response
                if refund_result is None:
                    lease.check_owned()
                    refund_result = get_payment_provider(
                        prepared.provider_name
                    ).refund_payment(
                        request=prepared.request,
                        app=app,
                    )
                    refund_result = _store_billing_refund_response(
                        prepared, refund_result
                    )
                lease.check_owned()
                if str(refund_result.status or "").lower() in {"failed", "canceled"}:
                    raise_error("server.order.orderRefundError")
                if str(refund_result.status or "").lower() != "succeeded":
                    return BillingRefundResultDTO(
                        bill_order_bid=prepared.order_bid,
                        provider=prepared.provider_name,
                        status=refund_result.status or "pending",
                        refund_reference_id=refund_result.provider_reference or None,
                    )
                return _finalize_billing_refund(app, prepared, refund_result, lease)
        except cache_provider.CacheLockOwnershipError:
            raise_error("server.order.orderStatusError")


def _finalize_billing_refund(
    app: Flask,
    prepared: _PreparedBillingRefund,
    refund_result: PaymentRefundResult,
    lease: cache_provider.RenewableLockLease,
) -> BillingRefundResultDTO:
    normalized_creator_bid = prepared.creator_bid
    with _credit_ledger_lock(app, normalized_creator_bid), unit_of_work():
        order = _load_refund_order(
            prepared.creator_bid, prepared.order_bid, for_update=True
        )
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        operation = dict(metadata.get("refund_operation") or {})
        if (
            operation.get("idempotency_key")
            != prepared.request.metadata["idempotency_key"]
            or order.payment_provider != prepared.provider_name
            or order.provider_reference_id != prepared.provider_reference
            or int(order.paid_amount or 0) != prepared.paid_amount
            or order.status
            not in {BILLING_ORDER_STATUS_PAID, BILLING_ORDER_STATUS_REFUNDED}
        ):
            raise_error("server.order.orderStatusError")

        apply_successful_billing_refund(app, order, refund_result)
        persist_refund(order, refund_result)
        lease.check_owned()
        return BillingRefundResultDTO(
            bill_order_bid=order.bill_order_bid,
            provider=order.payment_provider,
            status="refunded",
            refund_reference_id=refund_result.provider_reference,
        )


def apply_billing_refund_evidence(
    app: Flask, order: BillingOrder, event: PaymentEvent, payload: dict
) -> None:
    """Advance a prepared refund only from verified, associated refund evidence."""
    if event.kind != "refund" or not event.refund_status:
        return
    metadata = dict(order.metadata_json or {})
    operation = dict(metadata.get("refund_operation") or {})
    if not operation or operation.get("status") == "completed":
        return
    if metadata.get("refund_operation_history") and not event.refund_reference:
        return
    if (
        operation.get("provider") != order.payment_provider
        or operation.get("provider_reference") != order.provider_reference_id
    ):
        return
    if event.refund_reference and any(
        event.refund_reference == (old.get("response") or {}).get("provider_reference")
        for old in metadata.get("refund_operation_history") or []
    ):
        return
    previous = operation.get("response") or {}
    reference = event.refund_reference or previous.get("provider_reference") or ""
    if (
        previous.get("provider_reference")
        and reference != previous["provider_reference"]
    ):
        return
    status = event.refund_status.lower()
    if status not in {"pending", "requires_action", "succeeded", "failed", "canceled"}:
        return
    if operation.get("status") == "provider_failed" and status in {
        "pending",
        "requires_action",
    }:
        return
    result = PaymentRefundResult(reference, payload, status)
    if previous and "initial_response" not in operation:
        operation["initial_response"] = previous
    operation["response"] = asdict(result)
    operation["status"] = (
        "provider_failed"
        if status in {"failed", "canceled"}
        else "provider_completed"
        if status == "succeeded"
        else "awaiting_confirmation"
    )
    order.metadata_json = {**metadata, "refund_operation": operation}
    if status == "succeeded":
        apply_successful_billing_refund(app, order, result)


def apply_successful_billing_refund(
    app: Flask, order: BillingOrder, refund_result: PaymentRefundResult
) -> None:
    """Settle a confirmed refund locally in the caller's locked transaction."""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    operation = dict(metadata.get("refund_operation") or {})
    if operation.get("status") == "completed":
        return
    now = now_utc()
    order.status = BILLING_ORDER_STATUS_REFUNDED
    order.refunded_at = order.refunded_at or now
    order.updated_at = now
    merged_order_metadata = _merge_provider_metadata(
        existing=order.metadata_json,
        provider=order.payment_provider,
        source="api_refund",
        event_type="refund_payment",
        payload=refund_result.raw_response,
        event_time=None,
    )
    merged_order_metadata["refund_reference_id"] = refund_result.provider_reference
    merged_order_metadata["refund_status"] = refund_result.status
    order.metadata_json = _normalize_json_object(
        merged_order_metadata
    ).to_metadata_json()
    db.session.add(order)

    if order.subscription_bid:
        subscription = (
            BillingSubscription.query.filter(
                BillingSubscription.subscription_bid == order.subscription_bid,
                BillingSubscription.deleted == 0,
            )
            .with_for_update()
            .populate_existing()
            .first()
        )
        if subscription is not None:
            subscription.cancel_at_period_end = 1
            subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
            subscription.updated_at = now
            merged_subscription_metadata = _merge_provider_metadata(
                existing=subscription.metadata_json,
                provider=order.payment_provider,
                source="api_refund",
                event_type="refund_payment",
                payload=refund_result.raw_response,
                event_time=None,
            )
            subscription.metadata_json = _normalize_json_object(
                merged_subscription_metadata
            ).to_metadata_json()
            _sync_subscription_lifecycle_events(app, subscription)
            db.session.add(subscription)

            wallet = (
                CreditWallet.query.filter(
                    CreditWallet.deleted == 0,
                    CreditWallet.creator_bid == order.creator_bid,
                )
                .order_by(CreditWallet.id.desc())
                .with_for_update()
                .populate_existing()
                .first()
            )
            if wallet is not None:
                refresh_credit_wallet_snapshot(wallet, snapshot_at=now)
                persist_credit_wallet_snapshot(
                    wallet,
                    available_credits=wallet.available_credits,
                    reserved_credits=wallet.reserved_credits,
                    updated_at=now,
                )

    operation["status"] = "completed"
    operation["response"] = asdict(refund_result)
    order.metadata_json = {**order.metadata_json, "refund_operation": operation}


@dataclass(frozen=True, slots=True)
class _PreparedBillingQuery:
    """Detached evidence binding and versions captured before provider I/O."""

    terms: PaymentQueryTerms
    provider: str
    query: bool
    identity: tuple[object, ...]
    revision: tuple[object, ...]
    subscription_revision: tuple[object, ...] | None


def _billing_query_identity(order: BillingOrder) -> tuple[object, ...]:
    return (
        order.bill_order_bid,
        order.creator_bid,
        order.payment_provider,
        order.provider_reference_id,
        order.product_bid,
        order.subscription_bid,
        order.payable_amount,
        order.currency,
        _resolve_billing_order_provider_reference_type(order),
        _resolve_billing_order_reference_kind(order),
    )


def _billing_query_revision(order: BillingOrder) -> tuple[object, ...]:
    return (
        order.status,
        order.paid_amount,
        order.updated_at,
        order.expires_at,
        deepcopy(order.metadata_json),
    )


def _billing_query_subscription_revision(
    subscription_bid: str, *, for_update: bool = False
) -> tuple[object, ...] | None:
    if not subscription_bid:
        return None
    query = BillingSubscription.query.filter(
        BillingSubscription.deleted == 0,
        BillingSubscription.subscription_bid == subscription_bid,
    ).order_by(BillingSubscription.id.desc())
    if for_update:
        query = query.with_for_update().populate_existing()
    subscription = query.first()
    if subscription is None:
        return None
    return (
        subscription.status,
        subscription.billing_provider,
        subscription.provider_subscription_id,
        subscription.current_period_start_at,
        subscription.current_period_end_at,
        subscription.cancel_at_period_end,
        subscription.updated_at,
        deepcopy(subscription.metadata_json),
    )


def _prepare_billing_query(
    creator_bid: str, order_bid: str, session_id: str
) -> _PreparedBillingQuery:
    with unit_of_work(discard=True):
        order = _load_billing_order_by_bid(order_bid)
        if order is None or order.creator_bid != creator_bid:
            raise_error("server.order.orderNotFound")
        definition = payment_definition(order.payment_provider)
        reference = _normalize_bid(order.provider_reference_id)
        if (
            session_id
            and definition.capabilities.billing_mode == "provider_managed"
            and session_id != reference
        ):
            raise_error("server.order.orderStatusError")
        if (
            definition.capabilities.query
            and not reference
            and definition.capabilities.billing_mode == "provider_managed"
        ):
            raise_error("server.order.orderNotFound")
        terms = PaymentQueryTerms(
            reference,
            _resolve_billing_order_provider_reference_type(order),
            order.bill_order_bid,
            order.creator_bid,
            order.product_bid,
            reference_kind=_resolve_billing_order_reference_kind(order),
        )
        return _PreparedBillingQuery(
            terms,
            order.payment_provider,
            definition.capabilities.query and bool(reference),
            _billing_query_identity(order),
            _billing_query_revision(order),
            _billing_query_subscription_revision(order.subscription_bid),
        )


def sync_billing_order(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
    payload: dict[str, object],
) -> BillingOrderSyncResultDTO:
    """Query without a transaction, then apply evidence to its current attempt."""
    require_transaction_owner("billing order sync", app)
    return _sync_billing_order_phases(app, creator_bid, bill_order_bid, payload)[0]


def _sync_billing_order_phases(
    app: Flask, creator_bid: str, bill_order_bid: str, payload: dict[str, object]
) -> tuple[BillingOrderSyncResultDTO, BillingOrderProviderUpdateResult]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    session_id = _normalize_bid(payload.get("session_id"))

    with app_context_scope(app):
        prepared = _prepare_billing_query(
            normalized_creator_bid, normalized_order_bid, session_id
        )
        result = None
        if prepared.query:
            result = get_payment_provider(prepared.provider).sync_reference(
                provider_reference=prepared.terms.reference,
                reference_type=prepared.terms.reference_type,
                app=app,
            )
        # Grants and local transitions retain the established creator lock; the
        # network call holds neither that lock nor an open database transaction.
        with _credit_ledger_lock(app, normalized_creator_bid), unit_of_work():
            order = _load_billing_order_by_bid(normalized_order_bid, for_update=True)
            if order is None or order.creator_bid != normalized_creator_bid:
                raise_error("server.order.orderNotFound")
            if _billing_query_identity(order) != prepared.identity:
                raise_error("server.order.orderStatusError")
            current_subscription = _billing_query_subscription_revision(
                order.subscription_bid, for_update=True
            )
            if (
                _billing_query_revision(order) != prepared.revision
                or current_subscription != prepared.subscription_revision
            ):
                # A callback or management action committed during I/O. Its
                # current state wins over the older query, including metadata.
                order_update = BillingOrderProviderUpdateResult(
                    previous_status=int(order.status or 0)
                )
            else:
                order_update = _sync_provider_order(
                    app, order, session_id=session_id, result=result
                )
            if (
                int(order.status or 0) == BILLING_ORDER_STATUS_PENDING
                and _hydrate_legacy_billing_order_expires_at(order)
            ):
                db.session.add(order)
            if _expire_pending_billing_order_if_due(order):
                db.session.add(order)
            order_update.stage_after_state_changes(app, order)
            db.session.add(order)
            uow.on_commit(lambda: order_update.dispatch_after_commit(app))
            return _build_billing_order_sync_result(order), order_update


def reconcile_billing_provider_reference(
    app: Flask,
    *,
    creator_bid: str = "",
    payment_provider: str = "",
    provider_reference_id: str = "",
    bill_order_bid: str = "",
    session_id: str = "",
) -> ProviderReferenceReconcileResult:
    """Reconcile a provider reference back into one billing order state."""
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_payment_provider = _normalize_bid(payment_provider)
    normalized_provider_reference_id = _normalize_bid(provider_reference_id)
    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    normalized_session_id = _normalize_bid(session_id)

    with app.app_context():
        query = BillingOrder.query.filter(BillingOrder.deleted == 0)
        if normalized_creator_bid:
            query = query.filter(BillingOrder.creator_bid == normalized_creator_bid)
        if normalized_bill_order_bid:
            query = query.filter(
                BillingOrder.bill_order_bid == normalized_bill_order_bid
            )
        elif normalized_provider_reference_id:
            query = query.filter(
                BillingOrder.provider_reference_id == normalized_provider_reference_id
            )
        else:
            return ProviderReferenceReconcileResult(
                status="order_not_found",
                creator_bid=normalized_creator_bid or None,
                bill_order_bid=normalized_bill_order_bid or None,
                provider_reference_id=normalized_provider_reference_id or None,
                payment_provider=normalized_payment_provider or None,
            )
        if normalized_payment_provider:
            query = query.filter(
                BillingOrder.payment_provider == normalized_payment_provider
            )
        order = query.order_by(BillingOrder.id.desc()).first()
        if order is None:
            return ProviderReferenceReconcileResult(
                status="order_not_found",
                creator_bid=normalized_creator_bid or None,
                bill_order_bid=normalized_bill_order_bid or None,
                provider_reference_id=normalized_provider_reference_id or None,
                payment_provider=normalized_payment_provider or None,
            )

    sync_payload: dict[str, Any] = {}
    if (
        payment_definition(order.payment_provider).operation_reference_type("query")
        == "checkout_session"
    ):
        resolved_session_id = normalized_session_id or normalized_provider_reference_id
        if resolved_session_id:
            sync_payload["session_id"] = resolved_session_id

    payload = sync_billing_order(
        app,
        order.creator_bid,
        order.bill_order_bid,
        sync_payload,
    )
    return ProviderReferenceReconcileResult(
        status=payload.status,
        creator_bid=order.creator_bid,
        bill_order_bid=order.bill_order_bid,
        provider_reference_id=(
            normalized_provider_reference_id or order.provider_reference_id or None
        ),
        payment_provider=order.payment_provider,
    )


def _build_billing_order_sync_result(
    order: BillingOrder,
) -> BillingOrderSyncResultDTO:
    status_label = {
        BILLING_ORDER_STATUS_PENDING: "pending",
        BILLING_ORDER_STATUS_PAID: "paid",
        BILLING_ORDER_STATUS_FAILED: "failed",
        BILLING_ORDER_STATUS_CANCELED: "canceled",
        BILLING_ORDER_STATUS_TIMEOUT: "timeout",
        BILLING_ORDER_STATUS_REFUNDED: "refunded",
    }.get(int(order.status or 0))
    if not status_label:
        raise_error("server.order.orderStatusError")
    return BillingOrderSyncResultDTO(
        bill_order_bid=order.bill_order_bid,
        status=status_label,
        expires_at=order.expires_at,
        expires_in_seconds=_calculate_billing_order_expires_in_seconds(order),
    )


def _resolve_billing_payment_channel(
    payload: dict[str, object],
    *,
    default_pingxx_channel: str,
) -> tuple[str, str]:
    if payload.get("payment_option"):
        provider, channel = resolve_payment_option_hint(
            payload["payment_option"], biz_domain="billing"
        )
        return resolve_payment_channel(
            payment_channel_hint=provider,
            channel_hint=channel,
            stored_channel=None,
            default_pingxx_channel=default_pingxx_channel,
        )
    return resolve_payment_channel(
        payment_channel_hint=_normalize_payment_provider_hint(
            payload.get("payment_provider")
        )
        or None,
        channel_hint=_normalize_bid(payload.get("channel")) or None,
        stored_channel=None,
        default_pingxx_channel=default_pingxx_channel,
    )


def _resolve_required_provider_price_mapping(
    app: Flask,
    *,
    product: BillingProduct,
    provider: str,
    scope: ProviderPriceRuntimeScope | None = None,
) -> BillingProductProviderPrice:
    try:
        mapping = get_current_active_provider_price_mapping(
            app,
            product_bid=product.product_bid,
            provider=provider,
            scope=scope,
        )
    except ProviderPriceMappingError:
        raise_error("server.pay.payChannelNotSupport")
    if mapping is None:
        raise_error("server.pay.payChannelNotSupport")
    return mapping


def _build_provider_price_order_metadata(
    mapping: BillingProductProviderPrice,
) -> dict[str, object]:
    return {
        "provider_price_bid": mapping.provider_price_bid,
        "provider_account_id": mapping.provider_account_id,
        "provider_product_id": mapping.provider_product_id,
        "provider_price_id": mapping.provider_price_id,
        "provider_price_livemode": bool(mapping.livemode),
        "provider_price_currency": mapping.currency,
        "provider_price_unit_amount": int(mapping.unit_amount or 0),
        "provider_price_mapping": serialize_provider_price_mapping(mapping),
    }


def _build_campaign_provider_discount_order_metadata(
    row: BillingCampaignProviderDiscount,
) -> dict[str, object]:
    return {
        "campaign_provider_discount_bid": row.campaign_provider_discount_bid,
        "campaign_provider_discount": {
            "campaign_provider_discount_bid": row.campaign_provider_discount_bid,
            "campaign_bid": row.campaign_bid,
            "product_bid": row.product_bid,
            "product_provider_price_bid": row.product_provider_price_bid,
            "provider": row.provider,
            "provider_account_id": row.provider_account_id,
            "provider_product_id": row.provider_product_id,
            "provider_price_id": row.provider_price_id,
            "provider_coupon_id": row.provider_coupon_id,
            "livemode": bool(row.livemode),
            "list_price_amount": int(row.list_price_amount or 0),
            "campaign_price_amount": int(row.campaign_price_amount or 0),
            "discount_amount": int(row.discount_amount or 0),
            "discount_percent": str(row.discount_percent or 0),
            "currency": row.currency,
            "duration": row.duration,
        },
    }


def _resolve_campaign_provider_discount(
    *,
    applied_campaign: object | None,
    product: BillingProduct,
    provider_price_mapping: BillingProductProviderPrice | None,
) -> BillingCampaignProviderDiscount | None:
    if (
        provider_price_mapping is None
        or applied_campaign is None
        or not _campaign_affects_charge_amount(applied_campaign)
    ):
        return None
    row = load_current_campaign_provider_discount(
        campaign_bid=str(getattr(applied_campaign, "campaign_bid", "") or ""),
        product_bid=product.product_bid,
        provider_price_mapping=provider_price_mapping,
    )
    if row is None:
        raise_error("server.pay.payChannelNotSupport")
    return row


def _resolve_checkout_payable_amount(
    *,
    product: BillingProduct,
    applied_campaign: object | None,
    provider_price_mapping: BillingProductProviderPrice | None,
    campaign_provider_discount: BillingCampaignProviderDiscount | None,
    prepaid_offset_amount: int = 0,
) -> int:
    if (
        applied_campaign is not None
        and getattr(applied_campaign, "campaign_bid", "")
        and (provider_price_mapping is None or campaign_provider_discount is not None)
    ):
        base_amount = (
            int(campaign_provider_discount.campaign_price_amount or 0)
            if campaign_provider_discount is not None
            else int(getattr(applied_campaign, "campaign_price_amount", 0) or 0)
        )
    elif provider_price_mapping is not None:
        base_amount = int(provider_price_mapping.unit_amount or 0)
    else:
        base_amount = int(product.price_amount or 0)
    return max(0, base_amount - int(prepaid_offset_amount or 0))


def _stored_provider_price_snapshot_matches_mapping(
    order: BillingOrder,
    mapping: BillingProductProviderPrice,
    *,
    metadata: dict[str, object] | None = None,
) -> bool:
    order_metadata = metadata or (
        order.metadata_json if isinstance(order.metadata_json, dict) else {}
    )
    snapshot_keys = {
        "provider_price_bid",
        "provider_account_id",
        "provider_product_id",
        "provider_price_id",
        "provider_price_livemode",
        "provider_price_currency",
        "provider_price_unit_amount",
    }
    has_snapshot = any(
        order_metadata.get(key) not in {None, ""} for key in snapshot_keys
    )
    if not has_snapshot:
        return str(order.currency or "").strip().upper() == str(
            mapping.currency or ""
        ).strip().upper() and int(order.payable_amount or 0) == int(
            mapping.unit_amount or 0
        )

    expected = {
        "provider_price_bid": mapping.provider_price_bid,
        "provider_account_id": mapping.provider_account_id,
        "provider_product_id": mapping.provider_product_id,
        "provider_price_id": mapping.provider_price_id,
        "provider_price_livemode": bool(mapping.livemode),
        "provider_price_currency": str(mapping.currency or "").strip().upper(),
        "provider_price_unit_amount": int(mapping.unit_amount or 0),
    }
    return (
        _normalize_bid(order_metadata.get("provider_price_bid"))
        == _normalize_bid(expected["provider_price_bid"])
        and _normalize_bid(order_metadata.get("provider_account_id"))
        == _normalize_bid(expected["provider_account_id"])
        and _normalize_bid(order_metadata.get("provider_product_id"))
        == _normalize_bid(expected["provider_product_id"])
        and _normalize_bid(order_metadata.get("provider_price_id"))
        == _normalize_bid(expected["provider_price_id"])
        and bool(order_metadata.get("provider_price_livemode"))
        == bool(expected["provider_price_livemode"])
        and str(order_metadata.get("provider_price_currency") or "").strip().upper()
        == expected["provider_price_currency"]
        and int(order_metadata.get("provider_price_unit_amount") or 0)
        == expected["provider_price_unit_amount"]
    )


def _campaign_affects_charge_amount(campaign: object) -> bool:
    return bool(
        getattr(campaign, "campaign_bid", "")
        and int(getattr(campaign, "benefit_type_code", 0) or 0)
        == BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT
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


@dataclass(frozen=True)
class _ProviderCheckoutRequest:
    """Everything the provider call and the write-back need.

    Built while the order row is still being created, carried across the
    provider call as plain values so no ORM instance has to survive it.
    """

    bill_order_bid: str
    payment_request: PaymentRequest
    subject: str
    payment_provider: str
    payment_mode: str
    reused_existing_order: bool
    provider_price_metadata: dict[str, object]


def _build_provider_checkout_request(
    app: Flask,
    *,
    creator_bid: str,
    order: BillingOrder,
    product: BillingProduct,
    payment_provider: str,
    payment_mode: str,
    channel: str,
    reused_existing_order: bool = False,
    provider_price_mapping: BillingProductProviderPrice | None = None,
) -> _ProviderCheckoutRequest:
    """Describe the provider call; performs no provider I/O and no writes."""
    product_name = _resolve_checkout_product_name(product)
    subject = product_name
    metadata = {
        "bill_order_bid": order.bill_order_bid,
        "creator_bid": creator_bid,
        "product_bid": product.product_bid,
    }
    order_metadata = (
        order.metadata_json if isinstance(order.metadata_json, dict) else {}
    )
    provider_price_bid = _normalize_bid(order_metadata.get("provider_price_bid"))
    if provider_price_bid:
        metadata["provider_price_bid"] = provider_price_bid
    campaign_discount_payload = order_metadata.get("campaign_provider_discount")
    provider_coupon_id = ""
    if isinstance(campaign_discount_payload, dict):
        provider_coupon_id = _normalize_bid(
            campaign_discount_payload.get("provider_coupon_id")
        )
        if provider_coupon_id:
            metadata["campaign_provider_discount_bid"] = _normalize_bid(
                campaign_discount_payload.get("campaign_provider_discount_bid")
            )
    capabilities = payment_definition(payment_provider).capabilities
    if capabilities.catalog:
        if provider_price_mapping is None:
            provider_price_mapping = _resolve_required_provider_price_mapping(
                app, product=product, provider=payment_provider
            )
        if not _stored_provider_price_snapshot_matches_mapping(
            order, provider_price_mapping, metadata=order_metadata
        ):
            raise_error("server.order.orderStatusError")
    route = next(
        (
            item
            for item in payment_definition(payment_provider).routes
            if item.channel == channel
        ),
        None,
    )
    open_id = ""
    if route and route.requires_open_id:
        user = load_user_aggregate(creator_bid)
        open_id = str(user.wechat_open_id or "").strip() if user else ""
    provider_options = checkout_options(
        payment_provider,
        CheckoutTerms(
            order_reference=order.bill_order_bid,
            product_reference=product.product_bid,
            amount=int(order.payable_amount or 0),
            currency=order.currency.lower(),
            payment_mode="subscription"
            if payment_mode == "subscription"
            else "payment",
            channel=channel,
            metadata=metadata,
            price_reference=provider_price_mapping.provider_price_id
            if provider_price_mapping
            else "",
            price_amount=int(provider_price_mapping.unit_amount or 0)
            if provider_price_mapping
            else None,
            discount_reference=provider_coupon_id,
            open_id=open_id,
            success_url=_inject_billing_query(
                build_payment_result_url(
                    payment_definition(payment_provider).billing_result_path
                ),
                order.bill_order_bid,
            )
            if route and route.action == "redirect"
            else "",
            cancel_url=_inject_billing_query(
                build_payment_result_url(
                    payment_definition(payment_provider).billing_result_path,
                    canceled=True,
                ),
                order.bill_order_bid,
            )
            if route and route.action == "redirect"
            else "",
        ),
    )

    payment_request = PaymentRequest(
        order_bid=order.bill_order_bid,
        user_bid=creator_bid,
        shifu_bid="",
        amount=int(order.payable_amount or 0),
        channel=channel,
        currency=order.currency.lower(),
        subject=subject,
        body=subject,
        client_ip="127.0.0.1",
        extra=provider_options,
        biz_domain="billing",
        payment_mode=payment_mode,
    )
    return _ProviderCheckoutRequest(
        bill_order_bid=order.bill_order_bid,
        payment_request=payment_request,
        subject=subject,
        payment_provider=payment_provider,
        payment_mode=payment_mode,
        reused_existing_order=reused_existing_order,
        provider_price_metadata=(
            _build_provider_price_order_metadata(provider_price_mapping)
            if provider_price_mapping is not None
            else {}
        ),
    )


def _call_payment_provider(
    app: Flask, request: _ProviderCheckoutRequest
) -> PaymentCreationResult:
    """Create the charge at the provider. Runs with NO transaction open.

    The order row is already durable at this point, so a provider callback or
    a reconcile that resolves the order by its bid always finds it, and a
    failure here leaves a pending order the caller can retry instead of a
    charge with no local row.
    """
    if request.payment_mode == "subscription" and not supports_plan_checkout(
        request.payment_provider
    ):
        raise_error("server.pay.payChannelNotSupport")
    provider = get_payment_provider(request.payment_provider)
    if (
        request.payment_mode == "subscription"
        and payment_definition(
            request.payment_provider
        ).capabilities.subscription_create
    ):
        return provider.create_subscription(
            request=request.payment_request,
            app=app,
        )
    return provider.create_payment(
        request=request.payment_request,
        app=app,
    )


def _build_manual_payment_payload(
    provider_reference: str,
    raw_response: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Keep persisted-credential reuse and new checkout responses identical."""
    return _normalize_json_object(
        {
            "provider_reference_id": provider_reference,
            "credential": extra.get("credential"),
            "mode": extra.get("mode"),
            "prepay_id": extra.get("prepay_id"),
            "jsapi_params": extra.get("jsapi_params"),
            "raw_response": raw_response,
        }
    ).to_metadata_json()


def _persist_provider_checkout(
    order: BillingOrder,
    result: PaymentCreationResult,
    request: _ProviderCheckoutRequest,
) -> BillingCheckoutResultDTO:
    """Write the provider outcome back to the order and build the response."""
    payment_provider = request.payment_provider
    payment_mode = request.payment_mode
    subject = request.subject
    reused_existing_order = request.reused_existing_order

    order.provider_reference_id = str(result.provider_reference or "")
    order.metadata_json = _normalize_json_object(
        {
            **(
                dict(order.metadata_json)
                if isinstance(order.metadata_json, dict)
                else {}
            ),
            **request.provider_price_metadata,
            "provider": payment_provider,
            "payment_mode": payment_mode,
            "checkout": result.raw_response,
            "provider_extra": result.extra,
            "payment_action": creation_action(
                payment_provider, order.channel, result
            ).to_dict(),
        }
    ).to_metadata_json()
    db.session.add(order)
    _persist_billing_raw_snapshot_from_checkout(
        order,
        result,
        subject=subject,
        body=subject,
    )

    response = _build_checkout_response_payload(
        order,
        payment_provider=payment_provider,
        payment_mode=payment_mode,
        status="pending",
        reused_existing_order=reused_existing_order,
    )
    response["payment_action"] = creation_action(
        payment_provider, order.channel, result
    )
    if (
        payment_definition(payment_provider).capabilities.billing_mode
        == "provider_managed"
    ):
        redirect_url = response["payment_action"].url or ""
        if redirect_url:
            response["redirect_url"] = redirect_url
        if result.checkout_session_id:
            response["checkout_session_id"] = result.checkout_session_id
    else:
        response["payment_payload"] = _build_manual_payment_payload(
            result.provider_reference,
            result.raw_response,
            result.extra,
        )
    return BillingCheckoutResultDTO(**response)


def _run_provider_checkout(
    app: Flask, request: _ProviderCheckoutRequest
) -> BillingCheckoutResultDTO:
    """Call the provider outside any transaction, then persist in a new one."""
    result = _call_payment_provider(app, request)
    with unit_of_work():
        order = _load_billing_order_by_bid(request.bill_order_bid, for_update=True)
        if order is None:
            raise_error("server.order.orderNotFound")
        bound_reference = _normalize_bid(order.provider_reference_id)
        reported_reference = _normalize_bid(result.provider_reference)
        conflicting_reference = bool(
            bound_reference
            and reported_reference
            and bound_reference != reported_reference
        )
        if (
            int(order.status or 0) == BILLING_ORDER_STATUS_PENDING
            and not conflicting_reference
        ):
            if bound_reference and not reported_reference:
                result = replace(result, provider_reference=bound_reference)
            return _persist_provider_checkout(order, result, request)

        if bound_reference and not reported_reference:
            result = replace(result, provider_reference=bound_reference)
        same_attempt = bool(bound_reference and not conflicting_reference)
        # A callback settled the order or bound a different pending payment
        # while creation was in flight. Retain the response independently of
        # that current binding. The receipt is written here and
        # committed by this block; the error is raised only afterwards, so it
        # cannot take the snapshot down with it.
        _persist_billing_raw_snapshot_from_checkout(
            order,
            result,
            subject=request.subject,
            body=request.subject,
            raw_snapshot_status=_RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS.get(
                int(order.status) if same_attempt else BILLING_ORDER_STATUS_PENDING, 0
            ),
            independent=bool(bound_reference),
        )
        settled_status = int(order.status or 0)

    app.logger.warning(
        "Billing order %s has status %s or a conflicting reference while its %s charge %s was being "
        "created; receipt kept for reconciliation",
        request.bill_order_bid,
        settled_status,
        request.payment_provider,
        result.provider_reference,
    )
    raise_error("server.order.orderStatusError")
    return None


def _complete_zero_amount_subscription_checkout(
    app: Flask,
    order: BillingOrder,
) -> tuple[BillingCheckoutResultDTO, BillingPaidOrderSideEffects]:
    now = now_utc()
    previous_status = int(order.status or 0)
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    metadata.update(
        _normalize_json_object(
            {
                "provider": order.payment_provider,
                "payment_mode": "subscription",
                "zero_amount_offset": True,
                "checkout": {"status": "paid_without_provider_charge"},
            }
        )
    )
    order.status = BILLING_ORDER_STATUS_PAID
    order.paid_at = order.paid_at or now
    order.paid_amount = 0
    order.provider_reference_id = (
        order.provider_reference_id or f"zero_amount:{order.bill_order_bid}"
    )
    order.metadata_json = _normalize_json_object(metadata).to_metadata_json()
    order.updated_at = now
    db.session.add(order)
    side_effects = _stage_billing_paid_order_side_effects(
        app,
        order,
        previous_status=previous_status,
    )

    return (
        BillingCheckoutResultDTO(
            **_build_checkout_response_payload(
                order,
                payment_provider=order.payment_provider,
                payment_mode="subscription",
                status="paid",
            )
        ),
        side_effects,
    )


def _build_checkout_response_payload(
    order: BillingOrder,
    *,
    payment_provider: str,
    payment_mode: str,
    status: str,
    reused_existing_order: bool = False,
) -> dict[str, object]:
    order_metadata = (
        order.metadata_json if isinstance(order.metadata_json, dict) else {}
    )
    return {
        "bill_order_bid": order.bill_order_bid,
        "provider": payment_provider,
        "payment_mode": payment_mode,
        "status": status,
        "reused_existing_order": reused_existing_order,
        "checkout_type": order_metadata.get("checkout_type") or None,
        "effective_mode": order_metadata.get("effective_mode")
        or (
            "cycle_end"
            if order_metadata.get("checkout_type") == PREORDER_CHECKOUT_TYPE
            else "immediate"
        ),
        "current_product_bid": order_metadata.get("current_product_bid") or None,
        "target_product_bid": order_metadata.get("target_product_bid")
        or order.product_bid,
        "preorder_order_bid": order_metadata.get("preorder_order_bid") or None,
        "prepaid_offset_amount": int(order_metadata.get("prepaid_offset_amount") or 0),
        "payable_amount": int(order.payable_amount or 0),
        "currency": str(order.currency or "CNY"),
        "expires_at": order.expires_at,
        "expires_in_seconds": _calculate_billing_order_expires_in_seconds(order),
        "campaign": order_metadata.get("campaign") or None,
    }


def _resolve_billing_order_payment_mode(order: BillingOrder) -> str:
    order_label = BILLING_ORDER_TYPE_LABELS.get(int(order.order_type or 0), "manual")
    if order_label.startswith("subscription_"):
        return "subscription"
    return "one_time"


def _resolve_checkout_product_name(product: BillingProduct) -> str:
    display_name_key = _normalize_bid(product.display_name_i18n_key)
    translated_name = ""
    if display_name_key:
        translated_name = str(translate(display_name_key) or "").strip()
        if translated_name == display_name_key:
            translated_name = ""
        translated_name = _interpolate_checkout_product_name(translated_name, product)
    product_name = (
        translated_name
        or str(product.product_code or product.product_bid or "").strip()
    )

    if product.product_type == BILLING_PRODUCT_TYPE_PLAN:
        interval_label = BILLING_INTERVAL_LABELS.get(product.billing_interval)
        if interval_label in {"day", "month", "year"}:
            subject_prefix_key = _CHECKOUT_PLAN_SUBJECT_PREFIX_KEYS.get(
                interval_label, ""
            )
            subject_prefix = str(translate(subject_prefix_key) or "").strip()
            if subject_prefix and subject_prefix != subject_prefix_key:
                return f"{subject_prefix}·{product_name}"
    return product_name


def _interpolate_checkout_product_name(
    translated_name: str,
    product: BillingProduct,
) -> str:
    if not translated_name:
        return ""
    return translated_name.replace(
        "{credits}",
        _format_checkout_credit_amount(product.credit_amount),
    )


def _format_checkout_credit_amount(amount: object) -> str:
    credit_amount = _to_decimal(amount)
    if credit_amount == credit_amount.to_integral_value():
        return str(int(credit_amount))
    return format(credit_amount.normalize(), "f").rstrip("0").rstrip(".")


def _inject_billing_query(url: str, bill_order_bid: str) -> str:
    if not url:
        return url
    parsed = urlsplit(url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items.setdefault("bill_order_bid", bill_order_bid)
    new_query = urlencode(query_items, doseq=True)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            new_query,
            parsed.fragment,
        )
    )


def _sync_stripe_order(
    app: Flask, order: BillingOrder, *, session_id: str
) -> BillingOrderProviderUpdateResult:
    """Compatibility alias for callers using the old integration-specific name."""
    return _sync_legacy_provider_order(app, order, session_id=session_id)


def _resolve_billing_order_provider_reference_type(order: BillingOrder) -> str:
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    reference_type = _normalize_bid(metadata.get("provider_reference_type")).lower()
    if reference_type:
        return reference_type
    if (
        is_provider_managed_payment_provider(order.payment_provider)
        and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
    ):
        return payment_definition(order.payment_provider).operation_reference_type(
            "renewal"
        )
    return payment_definition(order.payment_provider).operation_reference_type("query")


def _resolve_billing_order_reference_kind(
    order: BillingOrder,
) -> Literal["payment", "contract"]:
    """Read explicit identity semantics and preserve older subscription snapshots."""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    kind = metadata.get("provider_reference_kind")
    if kind == "payment":
        return "payment"
    if kind == "contract":
        return "contract"
    reference_type = _normalize_bid(metadata.get("provider_reference_type"))
    if reference_type == "subscription" or (
        is_provider_managed_payment_provider(order.payment_provider)
        and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        and (
            not reference_type
            or reference_type
            == payment_definition(order.payment_provider).operation_reference_type(
                "renewal"
            )
        )
    ):
        return "contract"
    return "payment"


def _sync_provider_order(
    app: Flask,
    order: BillingOrder,
    *,
    session_id: str = "",
    result: PaymentNotificationResult | None = None,
) -> BillingOrderProviderUpdateResult:
    """Apply queried evidence with no gateway-specific status or payload parsing."""
    provider_name = order.payment_provider
    definition = payment_definition(provider_name)
    reference = _normalize_bid(order.provider_reference_id)
    # A client hint can only identify the attempt already bound to this order.
    if (
        session_id
        and definition.capabilities.billing_mode == "provider_managed"
        and session_id != reference
    ):
        raise_error("server.order.orderStatusError")
    if not definition.capabilities.query:
        # No provider evidence means no state transition or repeated paid effects.
        return BillingOrderProviderUpdateResult(previous_status=int(order.status or 0))
    if not reference:
        if definition.capabilities.billing_mode == "provider_managed":
            raise_error("server.order.orderNotFound")
        return _apply_billing_order_provider_update(
            order,
            provider=provider_name,
            event_type="manual_sync",
            source="sync",
            payload={},
            provider_reference_id="",
            target_status=BILLING_ORDER_STATUS_PENDING,
        )
    reference_type = _resolve_billing_order_provider_reference_type(order)
    reference_kind = _resolve_billing_order_reference_kind(order)
    if result is None:
        message = "Billing query evidence must be fetched outside the unit of work"
        raise RuntimeError(message)
    event = describe_query(
        provider_name,
        result,
        PaymentQueryTerms(
            reference,
            reference_type,
            order.bill_order_bid,
            order.creator_bid,
            order.product_bid,
            reference_kind=reference_kind,
        ),
    )
    target = {
        "paid": BILLING_ORDER_STATUS_PAID,
        "pending": BILLING_ORDER_STATUS_PENDING,
        "canceled": BILLING_ORDER_STATUS_CANCELED,
        "failed": BILLING_ORDER_STATUS_FAILED,
        "refunded": BILLING_ORDER_STATUS_REFUNDED,
    }.get(event.payment.state)
    if event.contract is not None and reference_kind == "contract":
        target = contract_renewal_order_status(order, event.contract)
    managed_refund = saved_refund_controls_state(event, order.metadata_json)
    if managed_refund:
        target = None
    failure_code, failure_message = event.failure_code, event.failure_message
    if event.validate_paid_amount:
        if event.payment.order_amount is None:
            failure_code, failure_message = (
                "provider_amount_missing",
                "Stripe checkout paid amount is missing",
            )
        elif not event.payment.currency:
            failure_code, failure_message = (
                "provider_currency_missing",
                "Stripe checkout currency is missing",
            )
        elif event.payment.order_amount != int(order.payable_amount or 0):
            failure_code, failure_message = (
                "provider_amount_mismatch",
                "Stripe checkout paid amount does not match billing order",
            )
        elif (
            str(order.currency or "").strip().upper()
            and event.payment.currency.upper() != str(order.currency).strip().upper()
        ):
            failure_code, failure_message = (
                "provider_currency_mismatch",
                "Stripe checkout currency does not match billing order",
            )
        if failure_code:
            target = BILLING_ORDER_STATUS_FAILED
    if event.expired:
        target, failure_code, failure_message = (
            BILLING_ORDER_STATUS_TIMEOUT,
            "expired",
            "Stripe checkout session expired",
        )
    if event.validate_reported_amount:
        if not reported_payment_currency_matches(
            expected_currency=order.currency,
            reported_currency=event.payment.currency,
        ):
            message = "Billing native payment currency mismatch"
            raise RuntimeError(message)
        actual = legacy_native_amount(event.payment)
        if actual is not None and actual != int(order.payable_amount or 0):
            message = "Billing native payment amount mismatch"
            raise RuntimeError(message)
    update = _apply_billing_order_provider_update(
        order,
        provider=provider_name,
        event_type="manual_sync",
        source="sync",
        payload=result.provider_payload,
        provider_reference_id=event.updated_payment_reference or reference,
        target_status=target,
        failure_code=failure_code,
        failure_message=failure_message,
        payment_facts=event.payment,
        contract_facts=event.contract if event.authoritative_contract else None,
    )
    apply_billing_refund_evidence(app, order, event, result.provider_payload)
    projected_state = (
        ("refunded" if order.status == BILLING_ORDER_STATUS_REFUNDED else "paid")
        if managed_refund
        else event.payment.state
    )
    order.metadata_json = {
        **order.metadata_json,
        "latest_payment_state": projected_state,
    }
    persist_query(order, result)
    if order.subscription_bid:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None and event.contract is not None:
            apply_subscription_contract(
                app,
                subscription,
                provider=provider_name,
                event_type=event.contract_event_type or "subscription.sync",
                payload=result.provider_payload,
                facts=event.contract,
                source="sync",
                event_time=coerce_datetime(event.payment.event_time),
                allow_activation=contract_can_activate(order),
                confirmed=event.authoritative_contract,
                allow_rebinding=paid_upgrade_can_rebind_contract(order, update),
            )
        elif (
            subscription is not None
            and target == BILLING_ORDER_STATUS_PAID
            and update.applied
            and order.status == BILLING_ORDER_STATUS_PAID
            and is_provider_managed_payment_provider(provider_name)
            and not order.metadata_json.get("provider_period_start_at")
        ):
            apply_subscription_contract(
                app,
                subscription,
                provider=provider_name,
                event_type="manual_sync",
                payload=result.provider_payload,
                facts=event.checkout_contract
                or SubscriptionFacts(
                    provider_reference=event.contract_reference,
                    customer_reference=event.customer_reference,
                    status="active",
                ),
                source="sync",
                event_time=coerce_datetime(event.payment.event_time),
                confirmed=False,
                allow_rebinding=paid_upgrade_can_rebind_contract(order, update),
            )
    return update


def _sync_stripe_subscription_order(
    app: Flask, order: BillingOrder, *, subscription_id: str
) -> BillingOrderProviderUpdateResult:
    return _sync_legacy_provider_order(app, order, session_id=subscription_id)


def _sync_pingxx_order(
    app: Flask, order: BillingOrder
) -> BillingOrderProviderUpdateResult:
    return _sync_legacy_provider_order(app, order)


def _sync_native_order(
    app: Flask, order: BillingOrder
) -> BillingOrderProviderUpdateResult:
    return _sync_legacy_provider_order(app, order)


def _sync_legacy_provider_order(
    app: Flask, order: BillingOrder, *, session_id: str = ""
) -> BillingOrderProviderUpdateResult:
    """Keep old helper names while requiring owned phases before external I/O."""
    if (
        not order.provider_reference_id
        or not payment_definition(order.payment_provider).capabilities.query
    ):
        return _sync_provider_order(app, order, session_id=session_id)
    require_transaction_owner("billing order sync", app)
    return _sync_billing_order_phases(
        app, order.creator_bid, order.bill_order_bid, {"session_id": session_id}
    )[1]


def _resolve_native_billing_order_status(
    provider: str,
    payload: dict[str, object],
) -> int | None:
    return _BILLING_STATUS_BY_NATIVE_STATE.get(
        resolve_native_payment_state(provider, payload)
    )


def _load_billing_order_for_native_event(
    *,
    provider: str,
    provider_attempt_id: str,
    transaction_id: str = "",
) -> BillingOrder | None:
    query = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.payment_provider == provider,
    )
    if provider_attempt_id:
        order = (
            query.filter(
                BillingOrder.provider_reference_id == provider_attempt_id,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is not None:
            return order
        order = (
            query.filter(BillingOrder.bill_order_bid == provider_attempt_id)
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is not None:
            return order
    if transaction_id:
        native_model = native_snapshot_model(provider)
        snapshot = (
            billing_native_snapshot_query(provider)
            .filter(
                native_model.transaction_id == transaction_id,
            )
            .order_by(native_model.id.desc())
            .first()
        )
        if snapshot is not None and snapshot.bill_order_bid:
            return (
                query.filter(BillingOrder.bill_order_bid == snapshot.bill_order_bid)
                .order_by(BillingOrder.id.desc())
                .first()
            )
    return None


load_billing_order_for_stripe_event = _load_billing_order_for_stripe_event
load_billing_subscription_for_stripe_event = _load_billing_subscription_for_stripe_event
load_billing_order_for_pingxx_event = _load_billing_order_for_pingxx_event
load_billing_order_for_native_event = _load_billing_order_for_native_event
resolve_billing_order_provider_reference_type = (
    _resolve_billing_order_provider_reference_type
)
persist_billing_stripe_raw_snapshot = _persist_billing_stripe_raw_snapshot
persist_billing_pingxx_raw_snapshot = _persist_billing_pingxx_raw_snapshot
persist_billing_native_raw_snapshot = _persist_billing_native_raw_snapshot


def _reconcile_stored_stripe_checkout_before_replacement(
    app: Flask, *, bill_order_bid: str, checkout_session_id: str
) -> None:
    if checkout_session_id:
        reconcile_checkout_before_replacement(
            app,
            provider_name="stripe",
            bill_order_bid=bill_order_bid,
            reference=checkout_session_id,
            client=get_payment_provider("stripe"),
        )


# Preserve historical helper imports used by integrations and regression tests.
__all__ = [
    "_build_native_provider_options",
    "_build_pingxx_provider_options",
    "_is_unbound_unpaid_stripe_checkout",
    "_load_billing_order_for_pingxx_event",
    "_load_billing_order_for_stripe_event",
    "_load_billing_subscription_for_stripe_event",
    "_validate_stripe_checkout_evidence",
]
