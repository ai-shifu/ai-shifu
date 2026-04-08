"""Read-model helpers for the creator billing service."""

from __future__ import annotations

import calendar
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Flask
from sqlalchemy import case

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.order.payment_providers import (
    PaymentNotificationResult,
    PaymentRefundRequest,
    PaymentRequest,
    get_payment_provider,
)
from flaskr.util.timezone import serialize_with_app_timezone
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILLING_INTERVAL_LABELS,
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_LABELS,
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
    BILLING_PRODUCT_TYPE_LABELS,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_CATEGORY_LABELS,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_LABELS,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_LABELS,
)
from .models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .wallets import (
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)

DEFAULT_PAGE_INDEX = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

_USAGE_SCENE_LABELS = {
    BILL_USAGE_SCENE_DEBUG: "debug",
    BILL_USAGE_SCENE_PREVIEW: "preview",
    BILL_USAGE_SCENE_PROD: "production",
}

_ACTIVE_SUBSCRIPTION_STATUSES = (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)

_SUBSCRIPTION_STATUS_SORT = {
    BILLING_SUBSCRIPTION_STATUS_ACTIVE: 1,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE: 2,
    BILLING_SUBSCRIPTION_STATUS_PAUSED: 3,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED: 4,
    BILLING_SUBSCRIPTION_STATUS_DRAFT: 5,
    BILLING_SUBSCRIPTION_STATUS_CANCELED: 6,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED: 7,
}

_STRIPE_SUCCESS_EVENT_TYPES = {
    "payment_intent.succeeded",
    "checkout.session.completed",
}

_STRIPE_FAIL_EVENT_TYPES = {
    "payment_intent.payment_failed",
}

_STRIPE_REFUND_EVENT_TYPES = {
    "charge.refunded",
    "refund.created",
}

_STRIPE_CANCEL_EVENT_TYPES = {
    "payment_intent.canceled",
}

_STRIPE_SUBSCRIPTION_EVENT_TYPES = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}

_STRIPE_SUBSCRIPTION_STATUS_MAP = {
    "active": BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    "trialing": BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    "past_due": BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    "unpaid": BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    "paused": BILLING_SUBSCRIPTION_STATUS_PAUSED,
    "canceled": BILLING_SUBSCRIPTION_STATUS_CANCELED,
    "incomplete_expired": BILLING_SUBSCRIPTION_STATUS_EXPIRED,
}

_BUCKET_PRIORITY_BY_CATEGORY = {
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION: 20,
    CREDIT_BUCKET_CATEGORY_TOPUP: 30,
}

_MANAGED_RENEWAL_EVENT_TYPES = (
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
)

_PENDING_RENEWAL_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
)


def build_billing_route_bootstrap(path_prefix: str) -> dict[str, Any]:
    """Return the billing route manifest defined by the design doc."""

    creator_routes = [
        {"method": "GET", "path": f"{path_prefix}/catalog"},
        {"method": "GET", "path": f"{path_prefix}/overview"},
        {"method": "GET", "path": f"{path_prefix}/wallet-buckets"},
        {"method": "GET", "path": f"{path_prefix}/ledger"},
        {"method": "GET", "path": f"{path_prefix}/orders"},
        {"method": "GET", "path": f"{path_prefix}/orders/{{billing_order_bid}}"},
        {
            "method": "POST",
            "path": f"{path_prefix}/orders/{{billing_order_bid}}/sync",
        },
        {"method": "POST", "path": f"{path_prefix}/subscriptions/checkout"},
        {"method": "POST", "path": f"{path_prefix}/subscriptions/cancel"},
        {"method": "POST", "path": f"{path_prefix}/subscriptions/resume"},
        {"method": "POST", "path": f"{path_prefix}/topups/checkout"},
    ]
    admin_routes = [
        {"method": "GET", "path": "/api/admin/billing/subscriptions"},
        {"method": "GET", "path": "/api/admin/billing/orders"},
        {"method": "POST", "path": "/api/admin/billing/ledger/adjust"},
    ]
    return {
        "service": "billing",
        "status": "bootstrap",
        "path_prefix": path_prefix,
        "creator_routes": creator_routes,
        "admin_routes": admin_routes,
        "notes": [
            "Registered via plugin route loading from flaskr/service.",
            "Keeps creator billing separate from legacy /order tables and routes.",
            "Stripe/Pingxx provider callbacks are reused from legacy webhook endpoints.",
        ],
    }


def build_billing_catalog(app: Flask) -> dict[str, list[dict[str, Any]]]:
    """Return plan and topup catalog projections."""

    with app.app_context():
        rows = (
            BillingProduct.query.filter(
                BillingProduct.deleted == 0,
                BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
                BillingProduct.product_type.in_(
                    [BILLING_PRODUCT_TYPE_PLAN, BILLING_PRODUCT_TYPE_TOPUP]
                ),
            )
            .order_by(BillingProduct.sort_order.asc(), BillingProduct.id.asc())
            .all()
        )

        plans: list[dict[str, Any]] = []
        topups: list[dict[str, Any]] = []
        for row in rows:
            payload = _serialize_product(row)
            if payload["product_type"] == "plan":
                plans.append(payload)
            elif payload["product_type"] == "topup":
                topups.append(payload)

        return {"plans": plans, "topups": topups}


def build_billing_overview(
    app: Flask,
    creator_bid: str,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Return the wallet snapshot, current subscription, and alerts."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        wallet = (
            CreditWallet.query.filter(
                CreditWallet.deleted == 0,
                CreditWallet.creator_bid == normalized_creator_bid,
            )
            .order_by(CreditWallet.id.desc())
            .first()
        )
        subscription = _load_current_subscription(normalized_creator_bid)

        wallet_payload = _serialize_wallet(wallet)
        subscription_payload = _serialize_subscription(
            app, subscription, timezone_name=timezone_name
        )
        return {
            "creator_bid": normalized_creator_bid,
            "wallet": wallet_payload,
            "subscription": subscription_payload,
            "billing_alerts": _build_billing_alerts(wallet_payload, subscription),
        }


def build_billing_wallet_buckets(
    app: Flask,
    creator_bid: str,
    *,
    timezone_name: str | None = None,
) -> list[dict[str, Any]]:
    """Return wallet bucket projections sorted by actual consumption order."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        rows = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.creator_bid == normalized_creator_bid,
            )
            .order_by(
                CreditWalletBucket.priority.asc(),
                case((CreditWalletBucket.effective_to.is_(None), 1), else_=0).asc(),
                CreditWalletBucket.effective_to.asc(),
                CreditWalletBucket.created_at.asc(),
                CreditWalletBucket.id.asc(),
            )
            .all()
        )
        return [
            _serialize_wallet_bucket(app, row, timezone_name=timezone_name)
            for row in rows
        ]


def build_billing_ledger_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Return paginated credit ledger entries for a creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    with app.app_context():
        query = CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == normalized_creator_bid,
        ).order_by(CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc())
        return _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_ledger_entry(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )


def build_billing_orders_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Return paginated billing orders for a creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    with app.app_context():
        query = BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == normalized_creator_bid,
        ).order_by(BillingOrder.created_at.desc(), BillingOrder.id.desc())
        return _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_order_summary(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )


def build_billing_order_detail(
    app: Flask,
    creator_bid: str,
    billing_order_bid: str,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Return a single billing order detail for the current creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(billing_order_bid)
    with app.app_context():
        row = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.creator_bid == normalized_creator_bid,
                BillingOrder.billing_order_bid == normalized_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if row is None:
            raise_error("server.order.orderNotFound")

        payload = _serialize_order_summary(app, row, timezone_name=timezone_name)
        payload["metadata"] = _normalize_json_value(row.metadata_json)
        payload["failure_code"] = str(row.failure_code or "")
        payload["refunded_at"] = _serialize_dt(
            app, row.refunded_at, timezone_name=timezone_name
        )
        payload["failed_at"] = _serialize_dt(
            app, row.failed_at, timezone_name=timezone_name
        )
        return payload


def create_billing_subscription_checkout(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create a subscription checkout order for the current creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    product_bid = _normalize_bid(payload.get("product_bid"))
    payment_provider = _normalize_payment_provider(payload.get("payment_provider"))
    channel = _normalize_bid(payload.get("channel")) or "checkout_session"
    success_url = _normalize_bid(payload.get("success_url"))
    cancel_url = _normalize_bid(payload.get("cancel_url"))

    with app.app_context():
        product = _load_catalog_product(product_bid, BILLING_PRODUCT_TYPE_PLAN)
        if payment_provider == "pingxx":
            order = BillingOrder(
                billing_order_bid=generate_id(app),
                creator_bid=normalized_creator_bid,
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                product_bid=product.product_bid,
                subscription_bid="",
                currency=product.currency,
                payable_amount=int(product.price_amount or 0),
                paid_amount=0,
                payment_provider=payment_provider,
                channel=channel,
                provider_reference_id="",
                status=BILLING_ORDER_STATUS_FAILED,
                failure_code="unsupported",
                failure_message="Pingxx subscription checkout is unsupported",
                metadata_json={"reason": "unsupported_subscription_provider"},
            )
            db.session.add(order)
            db.session.commit()
            return {
                "billing_order_bid": order.billing_order_bid,
                "provider": payment_provider,
                "payment_mode": "subscription",
                "status": "unsupported",
            }

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
        db.session.add(subscription)
        db.session.flush()

        order = BillingOrder(
            billing_order_bid=generate_id(app),
            creator_bid=normalized_creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
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
) -> dict[str, Any]:
    """Create a one-time topup checkout order for the current creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    product_bid = _normalize_bid(payload.get("product_bid"))
    payment_provider = _normalize_payment_provider(payload.get("payment_provider"))
    default_channel = (
        "checkout_session" if payment_provider == "stripe" else "alipay_qr"
    )
    channel = _normalize_bid(payload.get("channel")) or default_channel
    success_url = _normalize_bid(payload.get("success_url"))
    cancel_url = _normalize_bid(payload.get("cancel_url"))

    with app.app_context():
        product = _load_catalog_product(product_bid, BILLING_PRODUCT_TYPE_TOPUP)
        order = BillingOrder(
            billing_order_bid=generate_id(app),
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


def cancel_billing_subscription(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Mark the current subscription to cancel at period end."""

    with app.app_context():
        subscription = _load_owned_subscription(
            _normalize_bid(creator_bid),
            _normalize_bid(payload.get("subscription_bid")),
        )
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
            )
        subscription.cancel_at_period_end = 1
        subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        subscription.updated_at = datetime.now()
        _sync_subscription_lifecycle_events(app, subscription)
        db.session.add(subscription)
        db.session.commit()
        return _serialize_subscription(app, subscription)


def resume_billing_subscription(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Resume a cancel-scheduled subscription."""

    with app.app_context():
        subscription = _load_owned_subscription(
            _normalize_bid(creator_bid),
            _normalize_bid(payload.get("subscription_bid")),
        )
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
            )
        subscription.cancel_at_period_end = 0
        subscription.status = BILLING_SUBSCRIPTION_STATUS_ACTIVE
        subscription.updated_at = datetime.now()
        _sync_subscription_lifecycle_events(app, subscription)
        db.session.add(subscription)
        db.session.commit()
        return _serialize_subscription(app, subscription)


def refund_billing_order(
    app: Flask,
    creator_bid: str,
    billing_order_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Refund a paid billing order through the shared provider adapter."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(billing_order_bid)
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
                BillingOrder.billing_order_bid == normalized_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is None:
            raise_error("server.order.orderNotFound")

        if order.payment_provider == "pingxx":
            return {
                "billing_order_bid": order.billing_order_bid,
                "provider": order.payment_provider,
                "status": "unsupported",
            }

        if order.status == BILLING_ORDER_STATUS_REFUNDED:
            return {
                "billing_order_bid": order.billing_order_bid,
                "provider": order.payment_provider,
                "status": "refunded",
            }

        if order.status != BILLING_ORDER_STATUS_PAID:
            raise_error("server.order.orderStatusError")

        provider = get_payment_provider(order.payment_provider)
        refund_result = provider.refund_payment(
            request=PaymentRefundRequest(
                order_bid=order.billing_order_bid,
                amount=refund_amount,
                reason=refund_reason or None,
                metadata=_build_refund_provider_metadata(order),
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
        order.metadata_json = _normalize_json_value(merged_order_metadata)
        db.session.add(order)

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

        db.session.commit()
        return {
            "billing_order_bid": order.billing_order_bid,
            "provider": order.payment_provider,
            "status": "refunded",
            "refund_reference_id": refund_result.provider_reference,
        }


def sync_billing_order(
    app: Flask,
    creator_bid: str,
    billing_order_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Synchronize billing order payment status with the provider."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(billing_order_bid)
    session_id = _normalize_bid(payload.get("session_id"))

    with app.app_context():
        order = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.creator_bid == normalized_creator_bid,
                BillingOrder.billing_order_bid == normalized_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is None:
            raise_error("server.order.orderNotFound")

        if order.payment_provider == "stripe":
            _sync_stripe_order(app, order, session_id=session_id)
        elif order.payment_provider == "pingxx":
            _sync_pingxx_order(app, order)
        else:
            raise_error("server.pay.payChannelNotSupport")

        if order.status == BILLING_ORDER_STATUS_PAID:
            _grant_paid_order_credits(app, order)

        db.session.add(order)
        db.session.commit()

        if order.status == BILLING_ORDER_STATUS_PAID:
            return {"billing_order_bid": order.billing_order_bid, "status": "paid"}
        if order.status == BILLING_ORDER_STATUS_PENDING:
            return {
                "billing_order_bid": order.billing_order_bid,
                "status": "pending",
            }
        raise_error("server.order.orderStatusError")


def handle_billing_stripe_webhook(
    app: Flask,
    raw_body: bytes,
    sig_header: str,
) -> tuple[dict[str, Any], int]:
    """Handle Stripe billing webhooks using the shared provider verifier."""

    provider = get_payment_provider("stripe")
    try:
        notification: PaymentNotificationResult = provider.verify_webhook(
            headers={"Stripe-Signature": sig_header},
            raw_body=raw_body,
            app=app,
        )
    except Exception as exc:  # pragma: no cover - verified via route tests
        app.logger.exception("Stripe billing webhook verification failed: %s", exc)
        return {"status": "error", "message": str(exc)}, 400

    return apply_billing_stripe_notification(app, notification)


def apply_billing_stripe_notification(
    app: Flask,
    notification: PaymentNotificationResult,
) -> tuple[dict[str, Any], int]:
    """Apply a normalized Stripe notification to billing state."""

    event = notification.provider_payload or {}
    event_type = str(notification.status or event.get("type") or "")
    data_object = event.get("data", {}).get("object", {}) or {}
    metadata = data_object.get("metadata", {}) or {}
    billing_order_bid = _normalize_bid(
        metadata.get("billing_order_bid")
        or notification.order_bid
        or metadata.get("order_bid")
    )

    with app.app_context():
        order = _load_billing_order_for_stripe_event(
            billing_order_bid=billing_order_bid,
            data_object=data_object,
        )
        subscription = _load_billing_subscription_for_stripe_event(
            order=order,
            data_object=data_object,
            metadata=metadata,
        )
        if order is None and subscription is not None:
            order = _load_latest_billing_order_by_subscription(
                subscription.subscription_bid
            )

        if order is None and subscription is None:
            app.logger.warning(
                "Billing Stripe webhook ignored. event_type=%s billing_order_bid=%s",
                event_type,
                billing_order_bid,
            )
            return (
                {
                    "status": "ignored",
                    "event_type": event_type,
                    "billing_order_bid": billing_order_bid or None,
                },
                202,
            )

        response_status = "acknowledged"
        if order is not None:
            target_status = _map_stripe_order_status(event_type)
            applied = _apply_billing_order_provider_update(
                order,
                provider="stripe",
                event_type=event_type,
                source="webhook",
                payload=event,
                provider_reference_id=_extract_stripe_provider_reference(
                    order=order,
                    event_type=event_type,
                    data_object=data_object,
                ),
                target_status=target_status,
                failure_code=_extract_stripe_failure_code(data_object),
                failure_message=_extract_stripe_failure_message(data_object),
            )
            if target_status == BILLING_ORDER_STATUS_PAID:
                response_status = "paid"
            elif target_status == BILLING_ORDER_STATUS_FAILED:
                response_status = "failed" if applied else "acknowledged"
            elif target_status == BILLING_ORDER_STATUS_REFUNDED:
                response_status = "refunded" if applied else "acknowledged"
            elif target_status == BILLING_ORDER_STATUS_CANCELED:
                response_status = "canceled" if applied else "acknowledged"

        if subscription is not None:
            if event_type in _STRIPE_SUBSCRIPTION_EVENT_TYPES:
                _apply_billing_subscription_provider_update(
                    app,
                    subscription,
                    provider="stripe",
                    event_type=event_type,
                    payload=event,
                    data_object=data_object,
                )
            elif _map_stripe_order_status(event_type) == BILLING_ORDER_STATUS_PAID:
                _apply_subscription_checkout_success(
                    app,
                    subscription,
                    payload={
                        **data_object,
                        "created": event.get("created"),
                    },
                    provider="stripe",
                    event_type=event_type,
                )
            elif _map_stripe_order_status(event_type) == BILLING_ORDER_STATUS_FAILED:
                _apply_subscription_checkout_failure(
                    app,
                    subscription,
                    provider="stripe",
                    event_type=event_type,
                    payload=event,
                )

        if order is not None and order.status == BILLING_ORDER_STATUS_PAID:
            _grant_paid_order_credits(app, order)

        db.session.commit()
        return (
            {
                "status": response_status,
                "event_type": event_type,
                "billing_order_bid": order.billing_order_bid if order else None,
                "subscription_bid": (
                    subscription.subscription_bid if subscription else None
                ),
            },
            200,
        )


def handle_billing_pingxx_webhook(
    app: Flask,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Handle Pingxx billing callbacks using the shared billing state machine."""

    event_type = str((payload or {}).get("type", "") or "")
    charge = (payload or {}).get("data", {}).get("object", {}) or {}
    charge_id = _normalize_bid(charge.get("id"))
    order_no = _normalize_bid(charge.get("order_no"))

    with app.app_context():
        order = _load_billing_order_for_pingxx_event(
            charge_id=charge_id,
            order_no=order_no,
        )
        if order is None:
            return (
                {
                    "status": "not_billing",
                    "matched": False,
                    "event_type": event_type or None,
                    "charge_id": charge_id or None,
                    "order_no": order_no or None,
                },
                202,
            )

        target_status = None
        if event_type == "charge.succeeded":
            target_status = BILLING_ORDER_STATUS_PAID

        _apply_billing_order_provider_update(
            order,
            provider="pingxx",
            event_type=event_type,
            source="webhook",
            payload=payload,
            provider_reference_id=charge_id or order.provider_reference_id,
            target_status=target_status,
        )
        if order.status == BILLING_ORDER_STATUS_PAID:
            _grant_paid_order_credits(app, order)
        db.session.commit()
        return (
            {
                "status": "paid"
                if target_status == BILLING_ORDER_STATUS_PAID
                else "acknowledged",
                "matched": True,
                "event_type": event_type or None,
                "billing_order_bid": order.billing_order_bid,
            },
            200,
        )


def normalize_pagination(page_index: int, page_size: int) -> tuple[int, int]:
    """Normalize list pagination parameters to the shared admin defaults."""

    try:
        safe_page_index = max(int(page_index or DEFAULT_PAGE_INDEX), 1)
    except (TypeError, ValueError):
        safe_page_index = DEFAULT_PAGE_INDEX
    try:
        safe_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    except (TypeError, ValueError):
        safe_page_size = DEFAULT_PAGE_SIZE
    return safe_page_index, min(safe_page_size, MAX_PAGE_SIZE)


def _normalize_payment_provider(value: Any) -> str:
    provider = str(value or "").strip().lower()
    if provider not in {"stripe", "pingxx"}:
        raise_error("server.pay.payChannelNotSupport")
    return provider


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
) -> dict[str, Any]:
    provider = get_payment_provider(payment_provider)
    subject = product.product_code or product.product_bid
    metadata = {
        "billing_order_bid": order.billing_order_bid,
        "creator_bid": creator_bid,
        "product_bid": product.product_bid,
    }
    provider_options: dict[str, Any] = {"metadata": metadata}

    if payment_provider == "stripe":
        provider_options["mode"] = "checkout_session"
        provider_options["success_url"] = _inject_billing_query(
            success_url or "",
            order.billing_order_bid,
        )
        provider_options["cancel_url"] = _inject_billing_query(
            cancel_url or success_url or "",
            order.billing_order_bid,
        )
        provider_options["session_params"] = {
            "mode": "subscription" if payment_mode == "subscription" else "payment",
        }
        if payment_mode == "subscription":
            provider_options["session_params"]["subscription_data"] = {
                "metadata": metadata
            }
        provider_options["line_items"] = [
            _build_stripe_line_item(product, payment_mode=payment_mode)
        ]
    else:
        provider_options["charge_extra"] = {}

    payment_request = PaymentRequest(
        order_bid=order.billing_order_bid,
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
    if payment_mode == "subscription":
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
    order.metadata_json = _normalize_json_value(
        {
            "provider": payment_provider,
            "payment_mode": payment_mode,
            "checkout": result.raw_response,
            "provider_extra": result.extra,
        }
    )
    db.session.add(order)

    response: dict[str, Any] = {
        "billing_order_bid": order.billing_order_bid,
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
        response["payment_payload"] = _normalize_json_value(
            {
                "provider_reference_id": result.provider_reference,
                "credential": result.extra.get("credential"),
                "raw_response": result.raw_response,
            }
        )
    return response


def _build_stripe_line_item(
    product: BillingProduct,
    *,
    payment_mode: str,
) -> dict[str, Any]:
    price_data: dict[str, Any] = {
        "currency": str(product.currency or "CNY").lower(),
        "unit_amount": int(product.price_amount or 0),
        "product_data": {"name": product.product_code or product.product_bid},
    }
    if payment_mode == "subscription":
        interval = BILLING_INTERVAL_LABELS.get(product.billing_interval, "month")
        price_data["recurring"] = {
            "interval": interval,
            "interval_count": int(product.billing_interval_count or 1),
        }
    return {"price_data": price_data, "quantity": 1}


def _inject_billing_query(url: str, billing_order_bid: str) -> str:
    if not url:
        return url
    parsed = urlsplit(url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items.setdefault("billing_order_bid", billing_order_bid)
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


def _build_refund_provider_metadata(order: BillingOrder) -> dict[str, Any]:
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    provider_extra = metadata.get("provider_extra", {}) or {}
    latest_provider_payload = metadata.get("latest_provider_payload", {}) or {}

    refund_metadata: dict[str, Any] = {
        "billing_order_bid": order.billing_order_bid,
        "creator_bid": order.creator_bid,
    }
    payment_intent_id = _normalize_bid(provider_extra.get("payment_intent_id"))
    charge_id = _normalize_bid(provider_extra.get("charge_id"))

    payment_intent_payload = latest_provider_payload.get("payment_intent", {}) or {}
    charge_payload = latest_provider_payload.get("charge", {}) or {}
    payment_intent_id = payment_intent_id or _normalize_bid(
        payment_intent_payload.get("id")
    )
    charge_id = charge_id or _normalize_bid(charge_payload.get("id"))
    charge_id = charge_id or _normalize_bid(payment_intent_payload.get("latest_charge"))

    if payment_intent_id:
        refund_metadata["payment_intent_id"] = payment_intent_id
    if charge_id:
        refund_metadata["charge_id"] = charge_id
    return refund_metadata


def _sync_stripe_order(
    app: Flask,
    order: BillingOrder,
    *,
    session_id: str,
) -> None:
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

    _apply_billing_order_provider_update(
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


def _sync_pingxx_order(app: Flask, order: BillingOrder) -> None:
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

    _apply_billing_order_provider_update(
        order,
        provider="pingxx",
        event_type="manual_sync",
        source="sync",
        payload={"charge": charge},
        provider_reference_id=str(charge.get("id") or order.provider_reference_id),
        target_status=target_status,
    )


def _load_billing_order_for_stripe_event(
    *,
    billing_order_bid: str,
    data_object: dict[str, Any],
) -> BillingOrder | None:
    query = BillingOrder.query.filter(BillingOrder.deleted == 0)
    if billing_order_bid:
        return (
            query.filter(BillingOrder.billing_order_bid == billing_order_bid)
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
            query.filter(BillingOrder.billing_order_bid == order_no)
            .order_by(BillingOrder.id.desc())
            .first()
        )
    return None


def _load_subscription_by_bid(subscription_bid: str) -> BillingSubscription | None:
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    if not normalized_subscription_bid:
        return None
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.subscription_bid == normalized_subscription_bid,
        )
        .order_by(BillingSubscription.id.desc())
        .first()
    )


def _load_latest_billing_order_by_subscription(
    subscription_bid: str,
) -> BillingOrder | None:
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    if not normalized_subscription_bid:
        return None
    return (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.subscription_bid == normalized_subscription_bid,
        )
        .order_by(BillingOrder.created_at.desc(), BillingOrder.id.desc())
        .first()
    )


def _grant_paid_order_credits(app: Flask, order: BillingOrder) -> bool:
    grant_context = _resolve_credit_grant_context(order)
    if grant_context is None:
        return False

    product = _load_billing_product_by_bid(order.product_bid)
    if product is None:
        return False

    amount = _to_decimal(product.credit_amount)
    if amount <= 0:
        return False

    idempotency_key = f"grant:{order.billing_order_bid}"
    existing_entry = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if existing_entry is not None:
        return False

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    effective_from = _resolve_credit_bucket_effective_from(
        order=order,
        default_effective_from=order.paid_at or datetime.now(),
    )
    effective_to = _resolve_credit_bucket_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
    )

    bucket = CreditWalletBucket(
        wallet_bucket_bid=generate_id(app),
        wallet_bid=wallet.wallet_bid,
        creator_bid=order.creator_bid,
        bucket_category=grant_context["bucket_category"],
        source_type=grant_context["source_type"],
        source_bid=order.billing_order_bid,
        priority=grant_context["priority"],
        original_credits=amount,
        available_credits=amount,
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=effective_from,
        effective_to=effective_to,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json=_normalize_json_value(
            {
                "billing_order_bid": order.billing_order_bid,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
            }
        ),
    )

    db.session.add(bucket)
    sync_credit_bucket_status(bucket)
    refresh_credit_wallet_snapshot(wallet)
    balance_after = _to_decimal(wallet.available_credits)
    next_lifetime_granted = _to_decimal(wallet.lifetime_granted_credits) + amount
    ledger_entry = CreditLedgerEntry(
        ledger_bid=generate_id(app),
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=grant_context["source_type"],
        source_bid=order.billing_order_bid,
        idempotency_key=idempotency_key,
        amount=amount,
        balance_after=balance_after,
        expires_at=effective_to,
        consumable_from=effective_from,
        metadata_json=_normalize_json_value(
            {
                "billing_order_bid": order.billing_order_bid,
                "subscription_bid": order.subscription_bid or None,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": grant_context["grant_reason"],
            }
        ),
    )

    wallet.available_credits = balance_after
    persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        lifetime_granted_credits=next_lifetime_granted,
        updated_at=datetime.now(),
    )
    db.session.add(ledger_entry)

    if order.subscription_bid:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            if order.order_type in {
                BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            }:
                if order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
                    renewed_product_bid = (
                        _normalize_bid(subscription.next_product_bid)
                        or order.product_bid
                    )
                    subscription.product_bid = renewed_product_bid
                    subscription.next_product_bid = ""
                else:
                    subscription.product_bid = order.product_bid
                    subscription.next_product_bid = ""
                subscription.status = (
                    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
                    if subscription.cancel_at_period_end
                    else BILLING_SUBSCRIPTION_STATUS_ACTIVE
                )
                subscription.current_period_start_at = effective_from
                subscription.current_period_end_at = effective_to
                subscription.last_renewed_at = effective_from
            else:
                subscription.current_period_start_at = (
                    subscription.current_period_start_at or effective_from
                )
                subscription.current_period_end_at = (
                    subscription.current_period_end_at or effective_to
                )
            subscription.updated_at = datetime.now()
            _sync_subscription_lifecycle_events(app, subscription)
            db.session.add(subscription)

    return True


def _resolve_credit_grant_context(order: BillingOrder) -> dict[str, Any] | None:
    if order.order_type in {
        BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
        BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    }:
        return {
            "source_type": CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            "bucket_category": CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            "priority": _BUCKET_PRIORITY_BY_CATEGORY[
                CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            ],
            "grant_reason": "subscription",
        }
    if order.order_type == BILLING_ORDER_TYPE_TOPUP:
        return {
            "source_type": CREDIT_SOURCE_TYPE_TOPUP,
            "bucket_category": CREDIT_BUCKET_CATEGORY_TOPUP,
            "priority": _BUCKET_PRIORITY_BY_CATEGORY[CREDIT_BUCKET_CATEGORY_TOPUP],
            "grant_reason": "topup",
        }
    return None


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
        available_credits=Decimal("0"),
        reserved_credits=Decimal("0"),
        lifetime_granted_credits=Decimal("0"),
        lifetime_consumed_credits=Decimal("0"),
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
    if (
        order.subscription_bid
        and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START
    ):
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None and subscription.current_period_end_at is not None:
            return subscription.current_period_end_at

    interval = int(product.billing_interval or 0)
    interval_count = max(int(product.billing_interval_count or 0), 0)
    if interval_count <= 0:
        return None
    if interval == BILLING_INTERVAL_MONTH:
        return _add_months(effective_from, interval_count)
    if interval == BILLING_INTERVAL_YEAR:
        return _add_years(effective_from, interval_count)
    return None


def _resolve_credit_bucket_effective_from(
    *,
    order: BillingOrder,
    default_effective_from: datetime,
) -> datetime:
    if order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        return default_effective_from
    subscription = _load_subscription_by_bid(order.subscription_bid)
    if (
        subscription is None
        or subscription.current_period_end_at is None
        or subscription.current_period_end_at <= default_effective_from
    ):
        return default_effective_from
    return subscription.current_period_end_at


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _add_years(value: datetime, years: int) -> datetime:
    year = value.year + years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def _sync_subscription_lifecycle_events(
    app: Flask,
    subscription: BillingSubscription,
) -> None:
    scheduled_at = subscription.current_period_end_at
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
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            scheduled_at=scheduled_at,
        )
        return

    _cancel_subscription_renewal_events(
        subscription.subscription_bid,
        event_types=(BILLING_RENEWAL_EVENT_TYPE_RENEWAL,),
    )


def _upsert_subscription_renewal_event(
    app: Flask,
    subscription: BillingSubscription,
    *,
    event_type: int,
    scheduled_at: datetime,
) -> None:
    payload = _normalize_json_value(
        {
            "subscription_bid": subscription.subscription_bid,
            "creator_bid": subscription.creator_bid,
            "product_bid": subscription.product_bid,
            "next_product_bid": _normalize_bid(subscription.next_product_bid) or None,
            "status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                subscription.status,
                "draft",
            ),
            "cancel_at_period_end": bool(subscription.cancel_at_period_end),
        }
    )
    event = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription.subscription_bid,
            BillingRenewalEvent.event_type == event_type,
            BillingRenewalEvent.scheduled_at == scheduled_at,
        )
        .order_by(BillingRenewalEvent.id.desc())
        .first()
    )
    if event is None:
        event = BillingRenewalEvent(
            renewal_event_bid=generate_id(app),
            subscription_bid=subscription.subscription_bid,
            creator_bid=subscription.creator_bid,
            event_type=event_type,
            scheduled_at=scheduled_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json=payload,
            processed_at=None,
        )
    else:
        event.creator_bid = subscription.creator_bid
        event.status = BILLING_RENEWAL_EVENT_STATUS_PENDING
        event.last_error = ""
        event.payload_json = payload
        event.processed_at = None
        event.updated_at = datetime.now()

    db.session.add(event)
    _cancel_stale_subscription_renewal_events(
        subscription.subscription_bid,
        event_type=event_type,
        keep_scheduled_at=scheduled_at,
    )


def _cancel_stale_subscription_renewal_events(
    subscription_bid: str,
    *,
    event_type: int,
    keep_scheduled_at: datetime,
) -> None:
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription_bid,
            BillingRenewalEvent.event_type == event_type,
            BillingRenewalEvent.status.in_(_PENDING_RENEWAL_EVENT_STATUSES),
            BillingRenewalEvent.scheduled_at != keep_scheduled_at,
        )
        .order_by(BillingRenewalEvent.id.desc())
        .all()
    )
    now = datetime.now()
    for row in rows:
        row.status = BILLING_RENEWAL_EVENT_STATUS_CANCELED
        row.processed_at = now
        row.updated_at = now
        db.session.add(row)


def _cancel_subscription_renewal_events(
    subscription_bid: str,
    *,
    event_types: tuple[int, ...] = _MANAGED_RENEWAL_EVENT_TYPES,
) -> None:
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription_bid,
            BillingRenewalEvent.event_type.in_(event_types),
            BillingRenewalEvent.status.in_(_PENDING_RENEWAL_EVENT_STATUSES),
        )
        .order_by(BillingRenewalEvent.id.desc())
        .all()
    )
    now = datetime.now()
    for row in rows:
        row.status = BILLING_RENEWAL_EVENT_STATUS_CANCELED
        row.processed_at = now
        row.updated_at = now
        db.session.add(row)


def _apply_billing_order_provider_update(
    order: BillingOrder,
    *,
    provider: str,
    event_type: str,
    source: str,
    payload: dict[str, Any],
    provider_reference_id: str,
    target_status: int | None,
    failure_code: str = "",
    failure_message: str = "",
) -> bool:
    event_time = _extract_provider_event_time(payload)
    if provider_reference_id:
        order.provider_reference_id = provider_reference_id
    order.metadata_json = _merge_provider_metadata(
        existing=order.metadata_json,
        provider=provider,
        source=source,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
    )

    if not _can_transition_billing_order_status(
        current_status=int(order.status or 0),
        target_status=target_status,
        source=source,
    ):
        return False

    now = event_time or datetime.now()
    order.status = int(target_status or order.status or 0)
    order.updated_at = datetime.now()
    if target_status == BILLING_ORDER_STATUS_PENDING:
        return True
    if target_status == BILLING_ORDER_STATUS_PAID:
        order.paid_amount = int(order.payable_amount or 0)
        order.paid_at = order.paid_at or now
        order.failed_at = None
        order.failure_code = ""
        order.failure_message = ""
        return True
    if target_status == BILLING_ORDER_STATUS_FAILED:
        order.failed_at = order.failed_at or now
        order.failure_code = failure_code or order.failure_code
        order.failure_message = failure_message or order.failure_message
        return True
    if target_status == BILLING_ORDER_STATUS_REFUNDED:
        order.refunded_at = order.refunded_at or now
        return True
    if target_status in {
        BILLING_ORDER_STATUS_CANCELED,
        BILLING_ORDER_STATUS_TIMEOUT,
    }:
        order.failed_at = order.failed_at or now
        return True
    return True


def _can_transition_billing_order_status(
    *,
    current_status: int,
    target_status: int | None,
    source: str,
) -> bool:
    if target_status is None or current_status == target_status:
        return False
    if current_status == BILLING_ORDER_STATUS_REFUNDED:
        return False
    if current_status == BILLING_ORDER_STATUS_PAID:
        return target_status == BILLING_ORDER_STATUS_REFUNDED
    if current_status in {
        BILLING_ORDER_STATUS_CANCELED,
        BILLING_ORDER_STATUS_TIMEOUT,
    }:
        return False
    if current_status == BILLING_ORDER_STATUS_FAILED:
        return source == "sync" and target_status == BILLING_ORDER_STATUS_PAID
    return True


def _map_stripe_order_status(event_type: str) -> int | None:
    if event_type in _STRIPE_SUCCESS_EVENT_TYPES:
        return BILLING_ORDER_STATUS_PAID
    if event_type in _STRIPE_FAIL_EVENT_TYPES:
        return BILLING_ORDER_STATUS_FAILED
    if event_type in _STRIPE_REFUND_EVENT_TYPES:
        return BILLING_ORDER_STATUS_REFUNDED
    if event_type in _STRIPE_CANCEL_EVENT_TYPES:
        return BILLING_ORDER_STATUS_CANCELED
    return None


def _extract_stripe_provider_reference(
    *,
    order: BillingOrder,
    event_type: str,
    data_object: dict[str, Any],
) -> str:
    reference = _normalize_bid(data_object.get("id"))
    if event_type == "checkout.session.completed" and reference.startswith("cs_"):
        return reference
    return order.provider_reference_id


def _extract_stripe_failure_code(data_object: dict[str, Any]) -> str:
    error_info = data_object.get("last_payment_error", {}) or {}
    return str(error_info.get("code") or "")


def _extract_stripe_failure_message(data_object: dict[str, Any]) -> str:
    error_info = data_object.get("last_payment_error", {}) or {}
    return str(error_info.get("message") or "")


def _apply_billing_subscription_provider_update(
    app: Flask,
    subscription: BillingSubscription,
    *,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    data_object: dict[str, Any],
    source: str = "webhook",
) -> bool:
    event_time = _extract_provider_event_time(payload)
    if not _should_apply_subscription_event(subscription, event_time):
        return False

    _record_subscription_provider_event(
        subscription,
        provider=provider,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
        source=source,
    )
    subscription.billing_provider = provider
    provider_subscription_id = _normalize_bid(data_object.get("id"))
    if provider_subscription_id.startswith("sub_"):
        subscription.provider_subscription_id = provider_subscription_id
    customer_id = _normalize_bid(data_object.get("customer"))
    if customer_id:
        subscription.provider_customer_id = customer_id

    status = str(data_object.get("status") or "").strip().lower()
    mapped_status = _STRIPE_SUBSCRIPTION_STATUS_MAP.get(status)
    if status == "active" and int(data_object.get("cancel_at_period_end") or 0) == 1:
        mapped_status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
    if event_type == "customer.subscription.deleted":
        mapped_status = BILLING_SUBSCRIPTION_STATUS_CANCELED
    if mapped_status is not None:
        subscription.status = mapped_status

    subscription.cancel_at_period_end = (
        1 if data_object.get("cancel_at_period_end") else 0
    )
    subscription.billing_anchor_at = (
        _coerce_datetime(data_object.get("billing_cycle_anchor"))
        or subscription.billing_anchor_at
    )
    subscription.current_period_start_at = (
        _coerce_datetime(data_object.get("current_period_start"))
        or subscription.current_period_start_at
    )
    subscription.current_period_end_at = (
        _coerce_datetime(data_object.get("current_period_end"))
        or subscription.current_period_end_at
    )

    now = event_time or datetime.now()
    if mapped_status in {
        BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    }:
        subscription.last_renewed_at = now
    if mapped_status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE:
        subscription.last_failed_at = now
    subscription.updated_at = datetime.now()
    _sync_subscription_lifecycle_events(app, subscription)
    return True


def _apply_subscription_checkout_success(
    app: Flask,
    subscription: BillingSubscription,
    *,
    payload: dict[str, Any],
    provider: str,
    event_type: str,
    source: str = "webhook",
) -> bool:
    event_time = _extract_provider_event_time(payload)
    if not _should_apply_subscription_event(subscription, event_time):
        return False

    _record_subscription_provider_event(
        subscription,
        provider=provider,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
        source=source,
    )
    subscription.billing_provider = provider
    provider_subscription_id = _normalize_bid(
        payload.get("subscription")
        or (
            payload.get("id") if str(payload.get("id") or "").startswith("sub_") else ""
        )
    )
    if provider_subscription_id:
        subscription.provider_subscription_id = provider_subscription_id
    customer_id = _normalize_bid(payload.get("customer"))
    if customer_id:
        subscription.provider_customer_id = customer_id
    subscription.cancel_at_period_end = 1 if payload.get("cancel_at_period_end") else 0
    subscription.status = (
        BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        if subscription.cancel_at_period_end
        else BILLING_SUBSCRIPTION_STATUS_ACTIVE
    )
    now = event_time or datetime.now()
    subscription.last_renewed_at = now
    subscription.updated_at = datetime.now()
    _sync_subscription_lifecycle_events(app, subscription)
    return True


def _apply_subscription_checkout_failure(
    app: Flask,
    subscription: BillingSubscription,
    *,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    source: str = "webhook",
) -> bool:
    event_time = _extract_provider_event_time(payload)
    if not _should_apply_subscription_event(subscription, event_time):
        return False

    _record_subscription_provider_event(
        subscription,
        provider=provider,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
        source=source,
    )
    subscription.billing_provider = provider
    subscription.status = BILLING_SUBSCRIPTION_STATUS_PAST_DUE
    subscription.last_failed_at = event_time or datetime.now()
    subscription.updated_at = datetime.now()
    _sync_subscription_lifecycle_events(app, subscription)
    return True


def _should_apply_subscription_event(
    subscription: BillingSubscription,
    event_time: datetime | None,
) -> bool:
    if event_time is None:
        return True
    metadata = (
        subscription.metadata_json
        if isinstance(subscription.metadata_json, dict)
        else {}
    )
    latest_event_time = _coerce_datetime(metadata.get("latest_event_time"))
    if latest_event_time is None:
        return True
    return event_time >= latest_event_time


def _record_subscription_provider_event(
    subscription: BillingSubscription,
    *,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    event_time: datetime | None,
    source: str,
) -> None:
    subscription.metadata_json = _merge_provider_metadata(
        existing=subscription.metadata_json,
        provider=provider,
        source=source,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
    )


def _merge_provider_metadata(
    *,
    existing: Any,
    provider: str,
    source: str,
    event_type: str,
    payload: dict[str, Any],
    event_time: datetime | None,
) -> dict[str, Any]:
    metadata = dict(existing) if isinstance(existing, dict) else {}
    metadata["provider"] = provider
    metadata["latest_source"] = source
    metadata["latest_event_type"] = event_type
    metadata["latest_provider_payload"] = _normalize_json_value(payload)
    if event_time is not None:
        metadata["latest_event_time"] = event_time.isoformat()
    return _normalize_json_value(metadata)


def _extract_provider_event_time(payload: Any) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key in ("created", "time_paid"):
        value = _coerce_datetime(payload.get(key))
        if value is not None:
            return value
    data_object = payload.get("data", {}).get("object", {}) or {}
    for key in ("created", "time_paid", "current_period_end", "current_period_start"):
        value = _coerce_datetime(data_object.get(key))
        if value is not None:
            return value
    checkout_session = payload.get("checkout_session", {}) or {}
    for key in ("created",):
        value = _coerce_datetime(checkout_session.get(key))
        if value is not None:
            return value
    charge = payload.get("charge", {}) or {}
    for key in ("time_paid", "created"):
        value = _coerce_datetime(charge.get(key))
        if value is not None:
            return value
    return None


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return datetime.fromtimestamp(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text))
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _is_stripe_checkout_paid(
    session: dict[str, Any],
    intent: dict[str, Any] | None,
) -> bool:
    if session.get("payment_status") == "paid":
        return True
    if session.get("status") == "complete" and not session.get("payment_status"):
        return True
    if intent and intent.get("status") == "succeeded":
        return True
    return False


def _normalize_bid(value: Any) -> str:
    return str(value or "").strip()


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def _decimal_to_number(value: Any) -> int | float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        if value == value.to_integral():
            return int(value)
        return float(value)
    if isinstance(value, (int, float)):
        return value
    try:
        normalized = Decimal(str(value))
    except Exception:
        return 0
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(normalized)


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_to_number(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        payload = {str(key): _normalize_json_value(item) for key, item in value.items()}
        usage_scene = payload.get("usage_scene")
        if isinstance(usage_scene, (int, str)):
            payload["usage_scene"] = _USAGE_SCENE_LABELS.get(
                _safe_int(usage_scene),
                str(usage_scene),
            )
        return payload
    return value


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _serialize_dt(
    app: Flask,
    value: datetime | None,
    *,
    timezone_name: str | None = None,
) -> str | None:
    return serialize_with_app_timezone(app, value, timezone_name)


def _serialize_product(row: BillingProduct) -> dict[str, Any]:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    badge = metadata.get("badge")
    highlights = metadata.get("highlights")
    payload: dict[str, Any] = {
        "product_bid": row.product_bid,
        "product_code": row.product_code,
        "product_type": BILLING_PRODUCT_TYPE_LABELS.get(row.product_type, ""),
        "display_name": row.display_name_i18n_key,
        "description": row.description_i18n_key,
        "currency": row.currency,
        "price_amount": int(row.price_amount or 0),
        "credit_amount": _decimal_to_number(row.credit_amount),
    }
    if isinstance(highlights, list) and highlights:
        payload["highlights"] = [
            str(item) for item in highlights if str(item or "").strip()
        ]
    if badge:
        payload["status_badge_key"] = f"module.billing.catalog.badges.{badge}"
    if row.product_type == BILLING_PRODUCT_TYPE_PLAN:
        payload["billing_interval"] = BILLING_INTERVAL_LABELS.get(
            row.billing_interval,
            "month",
        )
        payload["billing_interval_count"] = int(row.billing_interval_count or 0)
        payload["auto_renew_enabled"] = bool(row.auto_renew_enabled)
    return payload


def _serialize_wallet(wallet: CreditWallet | None) -> dict[str, Any]:
    if wallet is None:
        return {
            "available_credits": 0,
            "reserved_credits": 0,
            "lifetime_granted_credits": 0,
            "lifetime_consumed_credits": 0,
        }
    return {
        "available_credits": _decimal_to_number(wallet.available_credits),
        "reserved_credits": _decimal_to_number(wallet.reserved_credits),
        "lifetime_granted_credits": _decimal_to_number(wallet.lifetime_granted_credits),
        "lifetime_consumed_credits": _decimal_to_number(
            wallet.lifetime_consumed_credits
        ),
    }


def _load_current_subscription(creator_bid: str) -> BillingSubscription | None:
    prioritized = (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
            BillingSubscription.status.in_(_ACTIVE_SUBSCRIPTION_STATUSES),
        )
        .order_by(
            case(
                *[
                    (BillingSubscription.status == status, rank)
                    for status, rank in _SUBSCRIPTION_STATUS_SORT.items()
                ],
                else_=99,
            ),
            BillingSubscription.current_period_end_at.desc(),
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        )
        .first()
    )
    if prioritized is not None:
        return prioritized
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
        )
        .order_by(BillingSubscription.created_at.desc(), BillingSubscription.id.desc())
        .first()
    )


def _load_product_code_map(product_bids: list[str]) -> dict[str, str]:
    normalized_bids = [bid for bid in product_bids if bid]
    if not normalized_bids:
        return {}
    rows = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid.in_(normalized_bids),
        )
        .order_by(BillingProduct.id.desc())
        .all()
    )
    return {row.product_bid: row.product_code for row in rows}


def _serialize_subscription(
    app: Flask,
    row: BillingSubscription | None,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    product_codes = _load_product_code_map([row.product_bid])
    next_product_bid = _normalize_bid(row.next_product_bid)
    return {
        "subscription_bid": row.subscription_bid,
        "product_bid": row.product_bid,
        "product_code": product_codes.get(row.product_bid, ""),
        "status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(row.status, "draft"),
        "billing_provider": str(row.billing_provider or ""),
        "current_period_start_at": _serialize_dt(
            app,
            row.current_period_start_at,
            timezone_name=timezone_name,
        ),
        "current_period_end_at": _serialize_dt(
            app,
            row.current_period_end_at,
            timezone_name=timezone_name,
        ),
        "grace_period_end_at": _serialize_dt(
            app,
            row.grace_period_end_at,
            timezone_name=timezone_name,
        ),
        "cancel_at_period_end": bool(row.cancel_at_period_end),
        "next_product_bid": next_product_bid or None,
        "last_renewed_at": _serialize_dt(
            app,
            row.last_renewed_at,
            timezone_name=timezone_name,
        ),
        "last_failed_at": _serialize_dt(
            app,
            row.last_failed_at,
            timezone_name=timezone_name,
        ),
    }


def _build_billing_alerts(
    wallet_payload: dict[str, Any],
    subscription: BillingSubscription | None,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    available_credits = float(wallet_payload.get("available_credits") or 0)

    if available_credits <= 0:
        alerts.append(
            {
                "code": "low_balance",
                "severity": "warning",
                "message_key": "module.billing.alerts.lowBalance",
                "message_params": {
                    "available_credits": wallet_payload.get("available_credits", 0)
                },
                "action_type": "checkout_topup",
                "action_payload": {},
            }
        )

    if subscription is None:
        return alerts

    if subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE:
        alerts.append(
            {
                "code": "subscription_past_due",
                "severity": "error",
                "message_key": "module.billing.alerts.subscriptionPastDue",
                "action_type": "open_orders",
                "action_payload": {
                    "subscription_bid": subscription.subscription_bid,
                },
            }
        )

    if subscription.cancel_at_period_end:
        alerts.append(
            {
                "code": "subscription_cancel_scheduled",
                "severity": "info",
                "message_key": "module.billing.alerts.cancelScheduled",
                "action_type": "resume_subscription",
                "action_payload": {
                    "subscription_bid": subscription.subscription_bid,
                },
            }
        )

    return alerts


def _serialize_wallet_bucket(
    app: Flask,
    row: CreditWalletBucket,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    return {
        "wallet_bucket_bid": row.wallet_bucket_bid,
        "category": CREDIT_BUCKET_CATEGORY_LABELS.get(row.bucket_category, "free"),
        "source_type": CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        "source_bid": row.source_bid,
        "available_credits": _decimal_to_number(row.available_credits),
        "effective_from": _serialize_dt(
            app,
            row.effective_from,
            timezone_name=timezone_name,
        )
        or "",
        "effective_to": _serialize_dt(
            app,
            row.effective_to,
            timezone_name=timezone_name,
        ),
        "priority": int(row.priority or 0),
        "status": CREDIT_BUCKET_STATUS_LABELS.get(row.status, "active"),
    }


def _serialize_ledger_entry(
    app: Flask,
    row: CreditLedgerEntry,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    return {
        "ledger_bid": row.ledger_bid,
        "wallet_bucket_bid": row.wallet_bucket_bid,
        "entry_type": CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant"),
        "source_type": CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        "source_bid": row.source_bid,
        "idempotency_key": row.idempotency_key,
        "amount": _decimal_to_number(row.amount),
        "balance_after": _decimal_to_number(row.balance_after),
        "expires_at": _serialize_dt(app, row.expires_at, timezone_name=timezone_name),
        "consumable_from": _serialize_dt(
            app,
            row.consumable_from,
            timezone_name=timezone_name,
        ),
        "metadata": _normalize_json_value(row.metadata_json) or {},
        "created_at": _serialize_dt(app, row.created_at, timezone_name=timezone_name)
        or "",
    }


def _serialize_order_summary(
    app: Flask,
    row: BillingOrder,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    subscription_bid = _normalize_bid(row.subscription_bid)
    payment_mode = "subscription"
    if row.order_type not in BILLING_ORDER_TYPE_LABELS:
        payment_mode = "one_time"
    elif not BILLING_ORDER_TYPE_LABELS[row.order_type].startswith("subscription_"):
        payment_mode = "one_time"

    return {
        "billing_order_bid": row.billing_order_bid,
        "creator_bid": row.creator_bid,
        "product_bid": row.product_bid,
        "subscription_bid": subscription_bid or None,
        "order_type": BILLING_ORDER_TYPE_LABELS.get(row.order_type, "manual"),
        "status": BILLING_ORDER_STATUS_LABELS.get(row.status, "init"),
        "payment_provider": str(row.payment_provider or ""),
        "payment_mode": payment_mode,
        "payable_amount": int(row.payable_amount or 0),
        "paid_amount": int(row.paid_amount or 0),
        "currency": row.currency,
        "provider_reference_id": str(row.provider_reference_id or ""),
        "failure_message": str(row.failure_message or ""),
        "created_at": _serialize_dt(app, row.created_at, timezone_name=timezone_name)
        or "",
        "paid_at": _serialize_dt(app, row.paid_at, timezone_name=timezone_name),
    }


def _build_page_payload(
    query, *, page_index: int, page_size: int, serializer
) -> dict[str, Any]:
    total = query.order_by(None).count()
    if total == 0:
        return {
            "items": [],
            "page": page_index,
            "page_count": 0,
            "page_size": page_size,
            "total": 0,
        }

    page_count = (total + page_size - 1) // page_size
    resolved_page = min(page_index, max(page_count, 1))
    offset = (resolved_page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()
    return {
        "items": [serializer(row) for row in rows],
        "page": resolved_page,
        "page_count": page_count,
        "page_size": page_size,
        "total": total,
    }
