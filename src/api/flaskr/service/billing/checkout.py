"""Checkout, refund, sync, and reconciliation flows for billing orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Flask

from flaskr.i18n import _ as translate
from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.config import get_config
from flaskr.service.order.models import PingxxOrder, StripeOrder
from flaskr.service.order.payment_channel_resolution import resolve_payment_channel
from flaskr.service.order.payment_providers import (
    PaymentCreationResult,
    PaymentRefundRequest,
    PaymentRequest,
    get_payment_provider,
)
from flaskr.service.order.raw_snapshots import (
    billing_pingxx_snapshot_query,
    billing_stripe_snapshot_query,
    upsert_billing_pingxx_snapshot,
    upsert_billing_stripe_snapshot,
)
from flaskr.service.user.repository import load_user_aggregate
from flaskr.util.uuid import generate_id

from .consts import (
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
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
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
from .models import BillingOrder, BillingProduct, BillingSubscription
from .provider_state import (
    BillingOrderProviderUpdateResult,
    apply_billing_order_provider_update as _apply_billing_order_provider_update,
    apply_billing_subscription_provider_update as _apply_billing_subscription_provider_update,
    apply_subscription_checkout_success as _apply_subscription_checkout_success,
    is_stripe_checkout_paid as _is_stripe_checkout_paid,
    merge_provider_metadata as _merge_provider_metadata,
    resolve_stripe_subscription_order_status as _resolve_stripe_subscription_order_status,
)
from .queries import (
    load_primary_active_subscription as _load_primary_active_subscription,
)
from .queries import normalize_payment_provider_hint as _normalize_payment_provider_hint
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import to_decimal as _to_decimal
from .subscriptions import (
    load_billing_product_by_bid as _load_billing_product_by_bid,
    load_effective_topup_subscription as _load_effective_topup_subscription,
    load_subscription_by_bid as _load_subscription_by_bid,
    sync_subscription_lifecycle_events as _sync_subscription_lifecycle_events,
)
from .wallets import grant_refund_return_credits

_RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS = {
    BILLING_ORDER_STATUS_INIT: 0,
    BILLING_ORDER_STATUS_PENDING: 0,
    BILLING_ORDER_STATUS_PAID: 1,
    BILLING_ORDER_STATUS_REFUNDED: 2,
    BILLING_ORDER_STATUS_CANCELED: 3,
    BILLING_ORDER_STATUS_TIMEOUT: 3,
    BILLING_ORDER_STATUS_FAILED: 4,
}

_CHECKOUT_PLAN_SUBJECT_PREFIX_KEYS = {
    "day": "module.billing.checkout.subject.plan.day",
    "month": "module.billing.checkout.subject.plan.month",
    "year": "module.billing.checkout.subject.plan.year",
}


@dataclass(slots=True, frozen=True)
class ProviderReferenceReconcileResult:
    status: str
    creator_bid: str | None
    bill_order_bid: str | None
    provider_reference_id: str | None
    payment_provider: str | None

    def to_task_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "bill_order_bid": self.bill_order_bid,
            "provider_reference_id": self.provider_reference_id,
            "payment_provider": self.payment_provider,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class StripeLineItemPayload:
    currency: str
    unit_amount: int
    product_name: str
    interval: str | None = None
    interval_count: int | None = None
    quantity: int = 1

    def to_provider_payload(self) -> dict[str, Any]:
        price_data: dict[str, Any] = {
            "currency": self.currency,
            "unit_amount": self.unit_amount,
            "product_data": {"name": self.product_name},
        }
        if self.interval is not None:
            price_data["recurring"] = {
                "interval": self.interval,
                "interval_count": self.interval_count or 1,
            }
        return {"price_data": price_data, "quantity": self.quantity}


@dataclass(slots=True, frozen=True)
class RefundProviderMetadata:
    bill_order_bid: str
    creator_bid: str
    payment_intent_id: str | None = None
    charge_id: str | None = None

    def to_provider_payload(self) -> dict[str, Any]:
        payload = {
            "bill_order_bid": self.bill_order_bid,
            "creator_bid": self.creator_bid,
        }
        if self.payment_intent_id:
            payload["payment_intent_id"] = self.payment_intent_id
        if self.charge_id:
            payload["charge_id"] = self.charge_id
        return payload


def create_billing_subscription_checkout(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
) -> BillingCheckoutResultDTO:
    """Create a subscription checkout order for the current creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    product_bid = _normalize_bid(payload.get("product_bid"))
    payment_provider, channel = _resolve_billing_payment_channel(
        payload,
        default_pingxx_channel="alipay_qr",
    )
    success_url = _normalize_bid(payload.get("success_url"))
    cancel_url = _normalize_bid(payload.get("cancel_url"))

    with app.app_context():
        product = _load_catalog_product(product_bid, BILLING_PRODUCT_TYPE_PLAN)
        _validate_plan_checkout_upgrade_only(
            creator_bid=normalized_creator_bid,
            target_product=product,
        )
        if payment_provider == "stripe":
            channel = "checkout_session"

        current_subscription = _load_primary_active_subscription(
            normalized_creator_bid,
            as_of=datetime.now(),
        )
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
        else:
            subscription = current_subscription
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
            subscription.updated_at = datetime.now()
            order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
        db.session.add(subscription)
        db.session.flush()

        order = BillingOrder(
            bill_order_bid=generate_id(app),
            creator_bid=normalized_creator_bid,
            order_type=order_type,
            product_bid=product.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency=product.currency,
            payable_amount=int(product.price_amount or 0),
            paid_amount=0,
            payment_provider=payment_provider,
            channel=channel,
            provider_reference_id="",
            status=BILLING_ORDER_STATUS_PENDING,
            metadata_json={"checkout_type": "subscription"},
        )
        db.session.add(order)
        db.session.flush()

        checkout_result = _create_provider_checkout(
            app,
            creator_bid=normalized_creator_bid,
            order=order,
            product=product,
            payment_provider=payment_provider,
            payment_mode="subscription",
            channel=channel,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        db.session.commit()
        return checkout_result


def create_billing_topup_checkout(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
) -> BillingCheckoutResultDTO:
    """Create a one-time topup checkout order for the current creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    product_bid = _normalize_bid(payload.get("product_bid"))
    payment_provider, channel = _resolve_billing_payment_channel(
        payload,
        default_pingxx_channel="alipay_qr",
    )
    success_url = _normalize_bid(payload.get("success_url"))
    cancel_url = _normalize_bid(payload.get("cancel_url"))

    with app.app_context():
        product = _load_catalog_product(product_bid, BILLING_PRODUCT_TYPE_TOPUP)
        if _load_effective_topup_subscription(normalized_creator_bid) is None:
            raise_error("server.billing.subscriptionInactive")
        order = BillingOrder(
            bill_order_bid=generate_id(app),
            creator_bid=normalized_creator_bid,
            order_type=BILLING_ORDER_TYPE_TOPUP,
            product_bid=product.product_bid,
            subscription_bid="",
            currency=product.currency,
            payable_amount=int(product.price_amount or 0),
            paid_amount=0,
            payment_provider=payment_provider,
            channel=channel,
            provider_reference_id="",
            status=BILLING_ORDER_STATUS_PENDING,
            metadata_json={"checkout_type": "topup"},
        )
        db.session.add(order)
        db.session.flush()

        checkout_result = _create_provider_checkout(
            app,
            creator_bid=normalized_creator_bid,
            order=order,
            product=product,
            payment_provider=payment_provider,
            payment_mode="one_time",
            channel=channel,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        db.session.commit()
        return checkout_result


def create_billing_order_checkout(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
    payload: dict[str, Any],
) -> BillingCheckoutResultDTO:
    """Create or refresh a Pingxx charge for one existing pending billing order."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    requested_channel = _normalize_bid(payload.get("channel"))

    with app.app_context():
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
        if order.payment_provider != "pingxx":
            raise_error("server.pay.payChannelNotSupport")
        if order.status != BILLING_ORDER_STATUS_PENDING:
            raise_error("server.order.orderStatusError")
        if order.order_type not in {
            BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        }:
            raise_error("server.order.orderStatusError")

        product = _load_billing_product_by_bid(order.product_bid)
        if product is None:
            raise_error("server.order.orderNotFound")

        order.channel = (
            requested_channel or _normalize_bid(order.channel) or "alipay_qr"
        )
        checkout_result = _create_provider_checkout(
            app,
            creator_bid=normalized_creator_bid,
            order=order,
            product=product,
            payment_provider="pingxx",
            payment_mode=_resolve_billing_order_payment_mode(order),
            channel=order.channel,
            success_url="",
            cancel_url="",
        )
        db.session.commit()
        return checkout_result


def refund_billing_order(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
    payload: dict[str, Any],
) -> BillingRefundResultDTO:
    """Refund a paid billing order through the shared provider adapter."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    refund_reason = _normalize_bid(payload.get("reason"))
    refund_amount_value = payload.get("amount")
    refund_amount = None
    if refund_amount_value not in (None, ""):
        refund_amount = int(refund_amount_value)

    with app.app_context():
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

        if order.payment_provider == "pingxx":
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
        product = (
            BillingProduct.query.filter(
                BillingProduct.deleted == 0,
                BillingProduct.product_bid == order.product_bid,
            )
            .order_by(BillingProduct.id.desc())
            .first()
        )
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

        now = datetime.now()
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
                subscription.metadata_json = _merge_provider_metadata(
                    existing=subscription.metadata_json,
                    provider=order.payment_provider,
                    source="api_refund",
                    event_type="refund_payment",
                    payload=refund_result.raw_response,
                    event_time=None,
                )
                _sync_subscription_lifecycle_events(app, subscription)
                db.session.add(subscription)

        refund_credit_amount = _to_decimal(product.credit_amount if product else 0)
        refund_reference_id = _normalize_bid(refund_result.provider_reference)
        if refund_credit_amount > 0 and refund_reference_id:
            grant_refund_return_credits(
                app,
                creator_bid=normalized_creator_bid,
                amount=refund_credit_amount,
                refund_bid=refund_reference_id,
                metadata={
                    "bill_order_bid": order.bill_order_bid,
                    "product_bid": order.product_bid,
                    "refund_reason": refund_reason,
                },
                effective_from=now,
            )

        db.session.commit()
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
    payload: dict[str, Any],
) -> BillingOrderSyncResultDTO:
    """Synchronize billing order payment status with the provider."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    session_id = _normalize_bid(payload.get("session_id"))

    with app.app_context():
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

        if order.payment_provider == "stripe":
            order_update = _sync_stripe_order(app, order, session_id=session_id)
        elif order.payment_provider == "pingxx":
            order_update = _sync_pingxx_order(app, order)
        else:
            raise_error("server.pay.payChannelNotSupport")

        order_update.stage_after_state_changes(app, order)

        db.session.add(order)
        db.session.commit()
        order_update.dispatch_after_commit(app)

        if order.status == BILLING_ORDER_STATUS_PAID:
            return BillingOrderSyncResultDTO(
                bill_order_bid=order.bill_order_bid,
                status="paid",
            )
        if order.status == BILLING_ORDER_STATUS_PENDING:
            return BillingOrderSyncResultDTO(
                bill_order_bid=order.bill_order_bid,
                status="pending",
            )
        raise_error("server.order.orderStatusError")


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


def _resolve_billing_payment_channel(
    payload: dict[str, Any],
    *,
    default_pingxx_channel: str,
) -> tuple[str, str]:
    return resolve_payment_channel(
        payment_channel_hint=_normalize_payment_provider_hint(
            payload.get("payment_provider")
        )
        or None,
        channel_hint=_normalize_bid(payload.get("channel")) or None,
        stored_channel=None,
        default_pingxx_channel=default_pingxx_channel,
    )


def _validate_plan_checkout_upgrade_only(
    *,
    creator_bid: str,
    target_product: BillingProduct,
) -> None:
    current_subscription = _load_primary_active_subscription(
        creator_bid,
        as_of=datetime.now(),
    )
    if current_subscription is None:
        return

    current_product = _load_billing_product_by_bid(current_subscription.product_bid)
    if (
        current_product is None
        or current_product.product_type != BILLING_PRODUCT_TYPE_PLAN
    ):
        return

    current_sort_order = int(current_product.sort_order or 0)
    target_sort_order = int(target_product.sort_order or 0)
    if target_sort_order <= current_sort_order:
        raise_error("server.billing.subscriptionUpgradeOnly")


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
    metadata = product.metadata_json if isinstance(product.metadata_json, dict) else {}
    if str(product.product_code or "").strip() == BILLING_TRIAL_PRODUCT_CODE or bool(
        metadata.get(BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG)
    ):
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


def _create_provider_checkout(
    app: Flask,
    *,
    creator_bid: str,
    order: BillingOrder,
    product: BillingProduct,
    payment_provider: str,
    payment_mode: str,
    channel: str,
    success_url: str,
    cancel_url: str,
) -> BillingCheckoutResultDTO:
    provider = get_payment_provider(payment_provider)
    product_name = _resolve_checkout_product_name(product)
    subject = product_name
    metadata = {
        "bill_order_bid": order.bill_order_bid,
        "creator_bid": creator_bid,
        "product_bid": product.product_bid,
    }
    provider_options: dict[str, Any] = {"metadata": metadata}

    if payment_provider == "stripe":
        provider_options["mode"] = "checkout_session"
        provider_options["success_url"] = _inject_billing_query(
            success_url or "",
            order.bill_order_bid,
        )
        provider_options["cancel_url"] = _inject_billing_query(
            cancel_url or success_url or "",
            order.bill_order_bid,
        )
        provider_options["session_params"] = {
            "mode": "subscription" if payment_mode == "subscription" else "payment",
        }
        if payment_mode == "subscription":
            provider_options["session_params"]["subscription_data"] = {
                "metadata": metadata
            }
        provider_options["line_items"] = [
            _build_stripe_line_item(
                product,
                product_name=product_name,
                payment_mode=payment_mode,
            ).to_provider_payload()
        ]
    else:
        provider_options.update(
            _build_pingxx_provider_options(
                creator_bid=creator_bid,
                product=product,
                channel=channel,
            )
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
    )
    if payment_mode == "subscription" and payment_provider == "stripe":
        result = provider.create_subscription(
            request=payment_request,
            app=app,
        )
    else:
        result = provider.create_payment(
            request=payment_request,
            app=app,
        )

    order.provider_reference_id = str(result.provider_reference or "")
    order.metadata_json = _normalize_json_object(
        {
            **(
                dict(order.metadata_json)
                if isinstance(order.metadata_json, dict)
                else {}
            ),
            "provider": payment_provider,
            "payment_mode": payment_mode,
            "checkout": result.raw_response,
            "provider_extra": result.extra,
        }
    ).to_metadata_json()
    db.session.add(order)
    _persist_billing_raw_snapshot_from_checkout(
        order,
        result,
        subject=subject,
        body=subject,
    )

    response: dict[str, Any] = {
        "bill_order_bid": order.bill_order_bid,
        "provider": payment_provider,
        "payment_mode": payment_mode,
        "status": "pending",
    }
    if payment_provider == "stripe":
        redirect_url = str(result.extra.get("url") or "")
        if redirect_url:
            response["redirect_url"] = redirect_url
        if result.checkout_session_id:
            response["checkout_session_id"] = result.checkout_session_id
    else:
        response["payment_payload"] = _normalize_json_object(
            {
                "provider_reference_id": result.provider_reference,
                "credential": result.extra.get("credential"),
                "raw_response": result.raw_response,
            }
        ).to_metadata_json()
    return BillingCheckoutResultDTO(**response)


def _build_pingxx_provider_options(
    *,
    creator_bid: str,
    product: BillingProduct,
    channel: str,
) -> dict[str, Any]:
    normalized_channel = _normalize_bid(channel)
    charge_extra: dict[str, Any]

    if normalized_channel == "wx_pub_qr":
        charge_extra = {"product_id": product.product_bid}
    elif normalized_channel == "alipay_qr":
        charge_extra = {}
    elif normalized_channel == "wx_pub":
        user = load_user_aggregate(creator_bid)
        charge_extra = {"open_id": user.wechat_open_id} if user else {}
    elif normalized_channel == "wx_wap":
        charge_extra = {}
    else:
        raise_error("server.pay.payChannelNotSupport")

    return {
        "app_id": str(get_config("PINGXX_APP_ID", "") or "").strip(),
        "charge_extra": charge_extra,
    }


def _persist_billing_raw_snapshot_from_checkout(
    order: BillingOrder,
    result: PaymentCreationResult,
    *,
    subject: str = "",
    body: str = "",
) -> None:
    if order.payment_provider == "stripe":
        _persist_billing_stripe_raw_snapshot(
            order,
            create_if_missing=True,
            metadata=result.extra.get("metadata") or {},
            checkout_session_id=result.checkout_session_id or result.provider_reference,
            checkout_object=result.raw_response or {},
            payment_intent_id=str(result.extra.get("payment_intent_id") or ""),
            payment_object=result.extra.get("payment_intent_object") or None,
            latest_charge_id=str(result.extra.get("latest_charge_id") or ""),
            receipt_url=str(result.extra.get("receipt_url") or ""),
            payment_method=str(result.extra.get("payment_method") or ""),
        )
        return

    if order.payment_provider == "pingxx":
        charge = result.raw_response or {}
        _persist_billing_pingxx_raw_snapshot(
            order,
            create_if_missing=True,
            charge_id=str(result.provider_reference or ""),
            charge_object=charge,
            transaction_no=str(charge.get("order_no") or ""),
            app_id=(
                str(charge.get("app", {}).get("id") or "")
                if isinstance(charge.get("app"), dict)
                else str(charge.get("app") or "")
            ),
            channel=str(charge.get("channel") or order.channel or ""),
            subject=str(charge.get("subject") or subject or ""),
            body=str(charge.get("body") or body or ""),
            client_ip=str(charge.get("client_ip") or ""),
            extra=charge.get("extra"),
        )


def _persist_billing_stripe_raw_snapshot(
    order: BillingOrder,
    *,
    create_if_missing: bool,
    metadata: Any | None = None,
    checkout_session_id: str = "",
    checkout_object: Any | None = None,
    payment_intent_id: str = "",
    payment_object: Any | None = None,
    latest_charge_id: str = "",
    receipt_url: str = "",
    payment_method: str = "",
) -> None:
    raw_status = _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS.get(
        int(order.status or BILLING_ORDER_STATUS_INIT), 0
    )
    existing = (
        billing_stripe_snapshot_query()
        .filter(StripeOrder.bill_order_bid == order.bill_order_bid)
        .order_by(StripeOrder.id.desc())
        .first()
    )
    if existing is None and not create_if_missing:
        return

    snapshot = upsert_billing_stripe_snapshot(
        bill_order_bid=order.bill_order_bid,
        creator_bid=order.creator_bid,
        amount=int(order.payable_amount or 0),
        currency=str(order.currency or "usd").lower(),
        raw_status=raw_status,
        metadata=metadata,
        checkout_session_id=checkout_session_id,
        checkout_object=checkout_object,
        payment_intent_id=payment_intent_id,
        payment_object=payment_object,
        latest_charge_id=latest_charge_id,
        receipt_url=receipt_url,
        payment_method=payment_method,
    )
    db.session.add(snapshot)


def _persist_billing_pingxx_raw_snapshot(
    order: BillingOrder,
    *,
    create_if_missing: bool,
    charge_id: str = "",
    charge_object: Any | None = None,
    transaction_no: str = "",
    app_id: str = "",
    channel: str = "",
    subject: str = "",
    body: str = "",
    client_ip: str = "",
    extra: Any | None = None,
) -> None:
    raw_status = _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS.get(
        int(order.status or BILLING_ORDER_STATUS_INIT), 0
    )
    existing = (
        billing_pingxx_snapshot_query()
        .filter(PingxxOrder.bill_order_bid == order.bill_order_bid)
        .order_by(PingxxOrder.id.desc())
        .first()
    )
    if existing is None and not create_if_missing:
        return

    snapshot = upsert_billing_pingxx_snapshot(
        bill_order_bid=order.bill_order_bid,
        creator_bid=order.creator_bid,
        amount=int(order.payable_amount or 0),
        currency=str(order.currency or "CNY"),
        raw_status=raw_status,
        charge_id=charge_id,
        charge_object=charge_object,
        transaction_no=transaction_no,
        app_id=app_id,
        channel=channel,
        subject=subject,
        body=body,
        client_ip=client_ip,
        extra=extra,
    )
    db.session.add(snapshot)


def _resolve_billing_order_payment_mode(order: BillingOrder) -> str:
    order_label = BILLING_ORDER_TYPE_LABELS.get(int(order.order_type or 0), "manual")
    if order_label.startswith("subscription_"):
        return "subscription"
    return "one_time"


def _build_stripe_line_item(
    product: BillingProduct,
    *,
    product_name: str,
    payment_mode: str,
) -> StripeLineItemPayload:
    interval: str | None = None
    interval_count: int | None = None
    if payment_mode == "subscription":
        interval = BILLING_INTERVAL_LABELS.get(product.billing_interval)
        if interval in {None, "none"}:
            raise_param_error("product_bid")
        interval_count = int(product.billing_interval_count or 1)
    return StripeLineItemPayload(
        currency=str(product.currency or "CNY").lower(),
        unit_amount=int(product.price_amount or 0),
        product_name=product_name,
        interval=interval,
        interval_count=interval_count,
        quantity=1,
    )


def _resolve_checkout_product_name(product: BillingProduct) -> str:
    display_name_key = _normalize_bid(product.display_name_i18n_key)
    translated_name = ""
    if display_name_key:
        translated_name = str(translate(display_name_key) or "").strip()
        if translated_name == display_name_key:
            translated_name = ""
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


def _build_refund_provider_metadata(order: BillingOrder) -> RefundProviderMetadata:
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    provider_extra = metadata.get("provider_extra", {}) or {}
    latest_provider_payload = metadata.get("latest_provider_payload", {}) or {}

    payment_intent_id = _normalize_bid(provider_extra.get("payment_intent_id"))
    charge_id = _normalize_bid(provider_extra.get("charge_id"))

    payment_intent_payload = latest_provider_payload.get("payment_intent", {}) or {}
    charge_payload = latest_provider_payload.get("charge", {}) or {}
    payment_intent_id = payment_intent_id or _normalize_bid(
        payment_intent_payload.get("id")
    )
    charge_id = charge_id or _normalize_bid(charge_payload.get("id"))
    charge_id = charge_id or _normalize_bid(payment_intent_payload.get("latest_charge"))

    return RefundProviderMetadata(
        bill_order_bid=order.bill_order_bid,
        creator_bid=order.creator_bid,
        payment_intent_id=payment_intent_id or None,
        charge_id=charge_id or None,
    )


def _sync_stripe_order(
    app: Flask,
    order: BillingOrder,
    *,
    session_id: str,
) -> BillingOrderProviderUpdateResult:
    reference_type = _resolve_billing_order_provider_reference_type(order)
    if reference_type == "subscription":
        resolved_subscription_id = session_id or order.provider_reference_id
        if not resolved_subscription_id:
            raise_error("server.order.orderNotFound")
        return _sync_stripe_subscription_order(
            app,
            order,
            subscription_id=resolved_subscription_id,
        )

    provider = get_payment_provider("stripe")
    resolved_session_id = session_id or order.provider_reference_id
    if not resolved_session_id:
        raise_error("server.order.orderNotFound")

    sync_result = provider.sync_reference(
        provider_reference=resolved_session_id,
        reference_type="checkout_session",
        app=app,
    )
    session = sync_result.provider_payload.get("checkout_session", {}) or {}
    intent = sync_result.provider_payload.get("payment_intent") or None
    target_status = BILLING_ORDER_STATUS_PENDING
    failure_code = ""
    failure_message = ""
    if _is_stripe_checkout_paid(session, intent):
        target_status = BILLING_ORDER_STATUS_PAID
    elif session.get("status") == "expired":
        target_status = BILLING_ORDER_STATUS_FAILED
        failure_code = "expired"
        failure_message = "Stripe checkout session expired"

    order_update = _apply_billing_order_provider_update(
        order,
        provider="stripe",
        event_type="manual_sync",
        source="sync",
        payload={
            "checkout_session": session,
            "payment_intent": intent or {},
        },
        provider_reference_id=str(session.get("id") or resolved_session_id),
        target_status=target_status,
        failure_code=failure_code,
        failure_message=failure_message,
    )
    receipt_url = ""
    charges = (intent or {}).get("charges", {}).get("data", []) if intent else []
    if charges:
        receipt_url = str(charges[0].get("receipt_url") or "")
    _persist_billing_stripe_raw_snapshot(
        order,
        create_if_missing=False,
        metadata=session.get("metadata") or (intent or {}).get("metadata") or None,
        checkout_session_id=str(session.get("id") or resolved_session_id),
        checkout_object=session,
        payment_intent_id=str((intent or {}).get("id") or ""),
        payment_object=intent,
        latest_charge_id=str((intent or {}).get("latest_charge") or ""),
        receipt_url=receipt_url,
        payment_method=str((intent or {}).get("payment_method") or ""),
    )
    if order.subscription_bid and target_status == BILLING_ORDER_STATUS_PAID:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            _apply_subscription_checkout_success(
                app,
                subscription,
                payload=session,
                provider="stripe",
                event_type="manual_sync",
                source="sync",
            )
    return order_update


def _resolve_billing_order_provider_reference_type(order: BillingOrder) -> str:
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    normalized_reference_type = _normalize_bid(
        metadata.get("provider_reference_type")
    ).lower()
    if normalized_reference_type:
        return normalized_reference_type
    if (
        order.payment_provider == "stripe"
        and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
    ):
        return "subscription"
    if order.payment_provider == "stripe":
        return "checkout_session"
    if order.payment_provider == "pingxx":
        return "charge"
    return ""


def _sync_stripe_subscription_order(
    app: Flask,
    order: BillingOrder,
    *,
    subscription_id: str,
) -> BillingOrderProviderUpdateResult:
    provider = get_payment_provider("stripe")
    sync_result = provider.sync_reference(
        provider_reference=subscription_id,
        reference_type="subscription",
        app=app,
    )
    subscription_payload = sync_result.provider_payload.get("subscription", {}) or {}
    target_status = _resolve_stripe_subscription_order_status(
        order, subscription_payload
    )
    failure_code = ""
    failure_message = ""
    if target_status == BILLING_ORDER_STATUS_FAILED:
        failure_code = str(subscription_payload.get("status") or "subscription_sync")
        failure_message = "Stripe subscription sync indicates renewal is not paid yet"

    order_update = _apply_billing_order_provider_update(
        order,
        provider="stripe",
        event_type="manual_sync",
        source="sync",
        payload=subscription_payload,
        provider_reference_id=str(subscription_payload.get("id") or subscription_id),
        target_status=target_status,
        failure_code=failure_code,
        failure_message=failure_message,
    )
    _persist_billing_stripe_raw_snapshot(
        order,
        create_if_missing=False,
        metadata=subscription_payload.get("metadata") or None,
    )
    if order.subscription_bid:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            _apply_billing_subscription_provider_update(
                app,
                subscription,
                provider="stripe",
                event_type="customer.subscription.updated",
                payload=subscription_payload,
                data_object=subscription_payload,
                source="sync",
            )
    return order_update


def _sync_pingxx_order(
    app: Flask,
    order: BillingOrder,
) -> BillingOrderProviderUpdateResult:
    provider = get_payment_provider("pingxx")
    if not order.provider_reference_id:
        raise_error("server.order.orderNotFound")

    sync_result = provider.sync_reference(
        provider_reference=order.provider_reference_id,
        reference_type="charge",
        app=app,
    )
    charge = sync_result.provider_payload.get("charge", {}) or {}
    target_status = BILLING_ORDER_STATUS_PENDING
    if charge.get("paid") or charge.get("time_paid"):
        target_status = BILLING_ORDER_STATUS_PAID

    order_update = _apply_billing_order_provider_update(
        order,
        provider="pingxx",
        event_type="manual_sync",
        source="sync",
        payload={"charge": charge},
        provider_reference_id=str(charge.get("id") or order.provider_reference_id),
        target_status=target_status,
    )
    _persist_billing_pingxx_raw_snapshot(
        order,
        create_if_missing=False,
        charge_id=str(charge.get("id") or order.provider_reference_id),
        charge_object=charge,
        transaction_no=str(charge.get("order_no") or ""),
        app_id=(
            str(charge.get("app", {}).get("id") or "")
            if isinstance(charge.get("app"), dict)
            else str(charge.get("app") or "")
        ),
        channel=str(charge.get("channel") or order.channel or ""),
        subject=str(charge.get("subject") or ""),
        body=str(charge.get("body") or ""),
        client_ip=str(charge.get("client_ip") or ""),
        extra=charge.get("extra"),
    )
    return order_update


def _load_billing_order_for_stripe_event(
    *,
    bill_order_bid: str,
    data_object: dict[str, Any],
) -> BillingOrder | None:
    query = BillingOrder.query.filter(BillingOrder.deleted == 0)
    if bill_order_bid:
        return (
            query.filter(BillingOrder.bill_order_bid == bill_order_bid)
            .order_by(BillingOrder.id.desc())
            .first()
        )

    provider_reference_id = _normalize_bid(data_object.get("id"))
    if provider_reference_id.startswith("cs_"):
        return (
            query.filter(
                BillingOrder.payment_provider == "stripe",
                BillingOrder.provider_reference_id == provider_reference_id,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
    return None


def _load_billing_subscription_for_stripe_event(
    *,
    order: BillingOrder | None,
    data_object: dict[str, Any],
    metadata: dict[str, Any],
) -> BillingSubscription | None:
    if order is not None and order.subscription_bid:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            return subscription

    subscription_bid = _normalize_bid(metadata.get("subscription_bid"))
    if subscription_bid:
        subscription = _load_subscription_by_bid(subscription_bid)
        if subscription is not None:
            return subscription

    provider_subscription_id = _normalize_bid(
        data_object.get("subscription")
        or (
            data_object.get("id")
            if str(data_object.get("id") or "").startswith("sub_")
            else ""
        )
    )
    if provider_subscription_id:
        return (
            BillingSubscription.query.filter(
                BillingSubscription.deleted == 0,
                BillingSubscription.billing_provider == "stripe",
                BillingSubscription.provider_subscription_id
                == provider_subscription_id,
            )
            .order_by(BillingSubscription.id.desc())
            .first()
        )
    return None


def _load_billing_order_for_pingxx_event(
    *,
    charge_id: str,
    order_no: str,
) -> BillingOrder | None:
    query = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.payment_provider == "pingxx",
    )
    if charge_id:
        order = (
            query.filter(BillingOrder.provider_reference_id == charge_id)
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is not None:
            return order
    if order_no:
        return (
            query.filter(BillingOrder.bill_order_bid == order_no)
            .order_by(BillingOrder.id.desc())
            .first()
        )
    return None


load_billing_order_for_stripe_event = _load_billing_order_for_stripe_event
load_billing_subscription_for_stripe_event = _load_billing_subscription_for_stripe_event
load_billing_order_for_pingxx_event = _load_billing_order_for_pingxx_event
resolve_billing_order_provider_reference_type = (
    _resolve_billing_order_provider_reference_type
)
persist_billing_stripe_raw_snapshot = _persist_billing_stripe_raw_snapshot
persist_billing_pingxx_raw_snapshot = _persist_billing_pingxx_raw_snapshot
