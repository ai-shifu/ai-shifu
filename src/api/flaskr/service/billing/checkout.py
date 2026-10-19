"""Checkout, refund, sync, and reconciliation flows for billing orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flaskr.common import (
    cache_provider,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.common.public_urls import (
    build_stripe_billing_result_url,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.dao import db, uow
from flaskr.dao.uow import (
    app_context_scope,
    require_transaction_owner,
    unit_of_work,
)
from flaskr.i18n import (
    _ as translate,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.service.common.models import (  # noqa: F401 - re-exported for import compatibility
    raise_error,
    raise_param_error,
)
from flaskr.service.common.native_payment_status import (  # noqa: F401 - re-exported for import compatibility
    NATIVE_PAYMENT_STATE_CANCELED,
    NATIVE_PAYMENT_STATE_FAILED,
    NATIVE_PAYMENT_STATE_PAID,
    extract_native_trade_payload,
    extract_native_trade_status,
    is_native_payment_payable,
    resolve_native_payment_state,
)
from flaskr.service.config import (
    get_config,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.service.order.models import (  # noqa: F401 - re-exported for import compatibility
    PingxxOrder,
    StripeOrder,
)
from flaskr.service.order.payment_channel_resolution import (
    resolve_payment_channel,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.service.order.payment_providers import (  # noqa: F401 - re-exported for import compatibility
    PaymentCreationResult,
    PaymentRefundRequest,
    PaymentRequest,
    get_payment_provider,
)
from flaskr.service.order.raw_snapshots import (  # noqa: F401 - re-exported for import compatibility
    billing_native_snapshot_query,
    billing_pingxx_snapshot_query,
    billing_stripe_snapshot_query,
    native_snapshot_model,
    upsert_billing_pingxx_snapshot,
    upsert_billing_stripe_snapshot,
    upsert_native_snapshot,
)
from flaskr.service.user.repository import (
    load_user_aggregate,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import (
    generate_id,  # noqa: F401 - re-exported for import compatibility
)

from .campaign_provider_discounts import (  # noqa: F401 - re-exported for import compatibility
    load_current_stripe_campaign_provider_discount,
)
from .campaigns import (
    resolve_applied_billing_campaign,  # noqa: F401 - re-exported for import compatibility
)
from .checkout_orders import (  # noqa: F401 - re-exported for import compatibility
    _build_billing_order_sync_result,
    _credit_ledger_lock,
    _expire_pending_billing_order_if_due,
    _hydrate_legacy_billing_order_expires_at,
    _is_same_subscription_checkout_target,
    _resolve_billing_payment_channel,
    _subscription_checkout_lock,
)
from .checkout_preparation import (  # noqa: F401 - re-exported for import compatibility
    _load_catalog_product,
    _lock_subscription_for_checkout,
    _prepare_subscription_checkout,
    _prepare_subscription_preorder_checkout_metadata,
    _prepare_topup_checkout,
    _ReopenExistingOrder,
    _validate_immediate_upgrade_checkout,
)
from .checkout_provider import (  # noqa: F401 - re-exported for import compatibility
    _build_native_provider_options,
    _build_pingxx_provider_options,
    _complete_zero_amount_subscription_checkout,
    _run_provider_checkout,
)
from .checkout_reopen import (  # noqa: F401 - re-exported for import compatibility
    _close_manual_payment_before_replacement,
    _ManualPaymentNeedsClosureError,
    _prepare_existing_billing_order_checkout,
    _reconcile_stored_stripe_checkout_before_replacement,
)
from .checkout_snapshots import (
    _persist_billing_native_raw_snapshot,
    _persist_billing_pingxx_raw_snapshot,
    _persist_billing_stripe_raw_snapshot,
)
from .checkout_sync import (  # noqa: F401 - re-exported for import compatibility
    RefundProviderMetadata,
    _build_refund_provider_metadata,
    _load_billing_order_for_native_event,
    _load_billing_order_for_pingxx_event,
    _load_billing_order_for_stripe_event,
    _load_billing_subscription_for_stripe_event,
    _resolve_billing_order_provider_reference_type,
    _sync_native_order,
    _sync_pingxx_order,
    _sync_stripe_order,
    _validate_stripe_checkout_evidence,
)
from .consts import (  # noqa: F401 - re-exported for import compatibility
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
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
)
from .dtos import (
    BillingCheckoutResultDTO,
    BillingOrderSyncResultDTO,
    BillingRefundResultDTO,
)
from .models import (  # noqa: F401 - re-exported for import compatibility
    BillingCampaignProviderDiscount,
    BillingOrder,
    BillingProduct,
    BillingProductProviderPrice,
    BillingSubscription,
    CreditWallet,
)
from .paid_side_effects import (  # noqa: F401 - re-exported for import compatibility
    BillingPaidOrderSideEffects,
)
from .payment_policy import (  # noqa: F401 - re-exported for import compatibility
    is_manual_payment_provider,
    manual_payments_are_compatible,
)
from .preorders import (  # noqa: F401 - re-exported for import compatibility
    CHECKOUT_ACTION_PREORDER,
    CHECKOUT_ACTION_UPGRADE_IMMEDIATE,
    PREORDER_CHECKOUT_TYPE,
)
from .preorders import (
    normalize_checkout_action as _normalize_checkout_action,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .provider_price_mappings import (  # noqa: F401 - re-exported for import compatibility
    ProviderPriceMappingError,
    ProviderPriceRuntimeScope,
    get_current_stripe_active_provider_price_mapping,
    serialize_provider_price_mapping,
)
from .provider_state import (  # noqa: F401 - re-exported for import compatibility
    BillingOrderProviderUpdateResult,
)
from .provider_state import (
    merge_provider_metadata as _merge_provider_metadata,
)
from .subscriptions import (  # noqa: F401 - re-exported for import compatibility
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
    from flask import Flask


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


def refund_billing_order(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
    payload: dict[str, object],
) -> BillingRefundResultDTO:
    """Refund a paid billing order through the shared provider adapter."""
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    refund_reason = _normalize_bid(payload.get("reason"))
    refund_amount_value = payload.get("amount")
    refund_amount = None
    if refund_amount_value not in (None, ""):
        refund_amount = int(refund_amount_value)

    with app_context_scope(app), unit_of_work():
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

        if order.payment_provider in {"pingxx", "alipay", "wechatpay"}:
            return BillingRefundResultDTO(
                bill_order_bid=order.bill_order_bid,
                provider=order.payment_provider,
                status="unsupported",
            )

        if order.status == BILLING_ORDER_STATUS_REFUNDED:
            return BillingRefundResultDTO(
                bill_order_bid=order.bill_order_bid,
                provider=order.payment_provider,
                status="refunded",
            )

        if order.status != BILLING_ORDER_STATUS_PAID:
            raise_error("server.order.orderStatusError")

        provider = get_payment_provider(order.payment_provider)
        refund_result = provider.refund_payment(
            request=PaymentRefundRequest(
                order_bid=order.bill_order_bid,
                amount=refund_amount,
                reason=refund_reason or None,
                metadata=_build_refund_provider_metadata(order).to_provider_payload(),
            ),
            app=app,
        )
        if str(refund_result.status or "").lower() in {"failed", "canceled"}:
            raise_error("server.order.orderRefundError")

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
        _persist_billing_stripe_raw_snapshot(
            order,
            create_if_missing=False,
            metadata={
                "last_refund_id": refund_result.provider_reference,
                "refund_status": refund_result.status,
            },
            payment_object=refund_result.raw_response,
        )

        if order.subscription_bid:
            subscription = _load_subscription_by_bid(order.subscription_bid)
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
                        CreditWallet.creator_bid == normalized_creator_bid,
                    )
                    .order_by(CreditWallet.id.desc())
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

        return BillingRefundResultDTO(
            bill_order_bid=order.bill_order_bid,
            provider=order.payment_provider,
            status="refunded",
            refund_reference_id=refund_result.provider_reference,
        )


def sync_billing_order(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
    payload: dict[str, object],
) -> BillingOrderSyncResultDTO:
    """Synchronize billing order payment status with the provider."""
    # Non-idempotent provider calls plus a grant idempotency pre-check that
    # must see committed state; renewal deliberately calls this outside its
    # own units of work (see the NOTE in _sync_billing_renewal_order).
    require_transaction_owner("billing order sync", app)
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    session_id = _normalize_bid(payload.get("session_id"))

    # Hold a per-creator lock across the whole read-modify-commit so the grant
    # idempotency pre-check and the commit run in one critical section (see
    # _credit_ledger_lock).
    with (
        app_context_scope(app),
        _credit_ledger_lock(app, normalized_creator_bid),
        unit_of_work(),
    ):
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

        if int(order.status or 0) == BILLING_ORDER_STATUS_PENDING and (
            _hydrate_legacy_billing_order_expires_at(order)
        ):
            db.session.add(order)

        if order.payment_provider == "stripe":
            order_update = _sync_stripe_order(app, order, session_id=session_id)
        elif order.payment_provider == "pingxx":
            order_update = _sync_pingxx_order(app, order)
        elif order.payment_provider in {"alipay", "wechatpay"}:
            order_update = _sync_native_order(app, order)
        else:
            raise_error("server.pay.payChannelNotSupport")

        # Applies to every order that is still pending and past its deadline,
        # so a top-up whose provider call failed (no provider reference, so the
        # sync leaves it pending) stops being picked up by every later scan.
        if _expire_pending_billing_order_if_due(order):
            db.session.add(order)

        order_update.stage_after_state_changes(app, order)

        db.session.add(order)
        uow.on_commit(lambda: order_update.dispatch_after_commit(app))
        return _build_billing_order_sync_result(order)


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
    if order.payment_provider == "stripe":
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
