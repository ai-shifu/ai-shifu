"""Manual operator/admin billing plan grant helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flask import Flask
from redis.exceptions import LockError

from flaskr.common.cache_provider import cache as redis
from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)
from .models import BillingOrder, BillingProduct, BillingSubscription
from .primitives import normalize_bid as _normalize_bid
from .queries import (
    calculate_self_managed_billing_cycle_end as _calculate_self_managed_billing_cycle_end,
    load_primary_active_subscription as _load_primary_active_subscription,
)
from .subscriptions import grant_paid_order_credits

_NOTIFICATION_EXTENSION_KEY = "admin_manual_plan_grant"
_NOTIFICATION_STATUS_TEMPLATE_PENDING = "template_pending"
_MANUAL_PROVIDER_NAME = "manual"


@dataclass(slots=True, frozen=True)
class ManualPlanGrantResult:
    """Resolved state for one manual plan grant request."""

    user_bid: str
    product_bid: str
    product_code: str
    subscription_bid: str
    bill_order_bid: str
    current_period_start_at: datetime | None
    current_period_end_at: datetime | None
    notification_status: str
    reused_existing_request: bool = False


def _load_active_plan_product(*, product_bid: str) -> BillingProduct | None:
    normalized_product_bid = _normalize_bid(product_bid)
    if not normalized_product_bid:
        return None
    return (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == normalized_product_bid,
            BillingProduct.product_type == BILLING_PRODUCT_TYPE_PLAN,
            BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )


def _load_plan_product_by_bid(product_bid: str) -> BillingProduct | None:
    normalized_product_bid = _normalize_bid(product_bid)
    if not normalized_product_bid:
        return None
    return (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == normalized_product_bid,
            BillingProduct.product_type == BILLING_PRODUCT_TYPE_PLAN,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )


def _load_existing_manual_grant_order(
    *,
    user_bid: str,
    request_id: str,
) -> BillingOrder | None:
    idempotency_reference = _build_manual_grant_provider_reference(request_id)
    return (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == user_bid,
            BillingOrder.payment_provider == _MANUAL_PROVIDER_NAME,
            BillingOrder.provider_reference_id == idempotency_reference,
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
        )
        .order_by(BillingOrder.id.desc())
        .first()
    )


def _build_manual_grant_provider_reference(request_id: str) -> str:
    return f"admin-plan-grant:{request_id}"


def _build_manual_grant_lock_key(*, user_bid: str, request_id: str) -> str:
    return f"billing:manual-plan-grant:{user_bid}:{request_id}"


def _build_notification_extension_payload(
    *,
    requested_at: datetime,
    operator_user_bid: str,
    grant_channel: str,
) -> dict[str, Any]:
    return {
        "status": _NOTIFICATION_STATUS_TEMPLATE_PENDING,
        "requested_at": requested_at.isoformat(),
        "updated_at": requested_at.isoformat(),
        "operator_user_bid": operator_user_bid,
        "grant_channel": grant_channel,
    }


def _ensure_notification_extension_metadata(
    order: BillingOrder,
    *,
    requested_at: datetime,
    operator_user_bid: str,
    grant_channel: str,
) -> str:
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    extensions = metadata.get("notification_extensions")
    if not isinstance(extensions, dict):
        extensions = {}
    if not isinstance(extensions.get(_NOTIFICATION_EXTENSION_KEY), dict):
        extensions[_NOTIFICATION_EXTENSION_KEY] = _build_notification_extension_payload(
            requested_at=requested_at,
            operator_user_bid=operator_user_bid,
            grant_channel=grant_channel,
        )
    metadata["notification_extensions"] = extensions
    order.metadata_json = metadata
    return str(
        extensions[_NOTIFICATION_EXTENSION_KEY].get("status")
        or _NOTIFICATION_STATUS_TEMPLATE_PENDING
    ).strip()


def _resolve_manual_plan_cycle_end(
    *,
    product: BillingProduct,
    granted_at: datetime,
) -> datetime:
    cycle_end_at = _calculate_self_managed_billing_cycle_end(
        product,
        cycle_start_at=granted_at,
    )
    if cycle_end_at is None or cycle_end_at <= granted_at:
        raise_error("server.common.systemError")
    return cycle_end_at


def grant_manual_plan_to_user(
    app: Flask,
    *,
    user_bid: str,
    product_bid: str,
    operator_user_bid: str,
    request_id: str,
    note: str = "",
    grant_channel: str = "operator_user_management",
) -> ManualPlanGrantResult:
    """Grant one active billing plan to one user via a manual paid order."""

    with app.app_context():
        normalized_user_bid = _normalize_bid(user_bid)
        normalized_product_bid = _normalize_bid(product_bid)
        normalized_operator_user_bid = _normalize_bid(operator_user_bid)
        normalized_request_id = _normalize_bid(request_id)
        normalized_note = str(note or "").strip()

        if not normalized_user_bid:
            raise_param_error("user_bid")
        if not normalized_product_bid:
            raise_param_error("product_bid")
        if not normalized_operator_user_bid:
            raise_param_error("operator_user_bid")
        if not normalized_request_id:
            raise_param_error("request_id")
        if len(normalized_note) > 255:
            raise_param_error("note")

        grant_lock = redis.lock(
            _build_manual_grant_lock_key(
                user_bid=normalized_user_bid,
                request_id=normalized_request_id,
            ),
            timeout=30,
            blocking_timeout=5,
        )
        if not grant_lock.acquire(blocking=True):
            raise_error("server.common.systemError")

        try:
            existing_order = _load_existing_manual_grant_order(
                user_bid=normalized_user_bid,
                request_id=normalized_request_id,
            )
            now = datetime.now()
            if existing_order is not None:
                grant_paid_order_credits(app, existing_order)
                notification_status = _ensure_notification_extension_metadata(
                    existing_order,
                    requested_at=now,
                    operator_user_bid=normalized_operator_user_bid,
                    grant_channel=grant_channel,
                )
                db.session.add(existing_order)
                db.session.commit()
                subscription = (
                    BillingSubscription.query.filter(
                        BillingSubscription.deleted == 0,
                        BillingSubscription.subscription_bid
                        == existing_order.subscription_bid,
                    )
                    .order_by(BillingSubscription.id.desc())
                    .first()
                )
                existing_product = _load_plan_product_by_bid(
                    str(existing_order.product_bid or "").strip()
                )
                return ManualPlanGrantResult(
                    user_bid=normalized_user_bid,
                    product_bid=str(existing_order.product_bid or "").strip(),
                    product_code=(
                        str(existing_product.product_code or "").strip()
                        if existing_product is not None
                        else ""
                    ),
                    subscription_bid=str(existing_order.subscription_bid or "").strip(),
                    bill_order_bid=str(existing_order.bill_order_bid or "").strip(),
                    current_period_start_at=(
                        subscription.current_period_start_at
                        if subscription is not None
                        else None
                    ),
                    current_period_end_at=(
                        subscription.current_period_end_at
                        if subscription is not None
                        else None
                    ),
                    notification_status=notification_status,
                    reused_existing_request=True,
                )

            product = _load_active_plan_product(product_bid=normalized_product_bid)
            if product is None:
                raise_param_error("product_bid")

            existing_subscription = _load_primary_active_subscription(
                normalized_user_bid,
                as_of=now,
            )
            order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_START
            if existing_subscription is not None:
                existing_product_bid = _normalize_bid(existing_subscription.product_bid)
                if existing_product_bid == product.product_bid:
                    raise_error("server.billing.adminPlanGrantAlreadyActive")
                if (
                    _normalize_bid(existing_subscription.billing_provider)
                    != _MANUAL_PROVIDER_NAME
                ):
                    raise_error("server.billing.adminPlanGrantProviderManagedConflict")
                current_product = _load_plan_product_by_bid(existing_product_bid)
                if current_product is None:
                    raise_error("server.common.systemError")
                if int(product.sort_order or 0) <= int(current_product.sort_order or 0):
                    raise_error("server.billing.subscriptionUpgradeOnly")
                order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE

            granted_at = datetime.now()
            cycle_end_at = _resolve_manual_plan_cycle_end(
                product=product,
                granted_at=granted_at,
            )

            subscription_metadata = {
                "admin_manual_plan_grant": True,
                "grant_channel": grant_channel,
                "operator_user_bid": normalized_operator_user_bid,
                "request_id": normalized_request_id,
            }
            if normalized_note:
                subscription_metadata["note"] = normalized_note

            if existing_subscription is None:
                subscription = BillingSubscription(
                    subscription_bid=generate_id(app),
                    creator_bid=normalized_user_bid,
                    product_bid=product.product_bid,
                    status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
                    billing_provider=_MANUAL_PROVIDER_NAME,
                    provider_subscription_id="",
                    provider_customer_id="",
                    billing_anchor_at=granted_at,
                    current_period_start_at=granted_at,
                    current_period_end_at=cycle_end_at,
                    grace_period_end_at=None,
                    cancel_at_period_end=0,
                    next_product_bid="",
                    last_renewed_at=None,
                    last_failed_at=None,
                    metadata_json=subscription_metadata,
                )
            else:
                subscription = existing_subscription
                subscription.metadata_json = {
                    **(
                        subscription.metadata_json
                        if isinstance(subscription.metadata_json, dict)
                        else {}
                    ),
                    **subscription_metadata,
                }
                subscription.updated_at = granted_at

            db.session.add(subscription)
            db.session.flush()

            order_metadata = {
                "checkout_type": "admin_manual_plan_grant",
                "admin_manual_plan_grant": True,
                "grant_channel": grant_channel,
                "operator_user_bid": normalized_operator_user_bid,
                "request_id": normalized_request_id,
                "applied_cycle_start_at": granted_at.isoformat(),
                "applied_cycle_end_at": cycle_end_at.isoformat(),
            }
            if normalized_note:
                order_metadata["note"] = normalized_note

            order = BillingOrder(
                bill_order_bid=generate_id(app),
                creator_bid=normalized_user_bid,
                order_type=order_type,
                product_bid=product.product_bid,
                subscription_bid=subscription.subscription_bid,
                currency=product.currency,
                payable_amount=0,
                paid_amount=0,
                payment_provider=_MANUAL_PROVIDER_NAME,
                channel=_MANUAL_PROVIDER_NAME,
                provider_reference_id=_build_manual_grant_provider_reference(
                    normalized_request_id
                ),
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=granted_at,
                metadata_json=order_metadata,
            )
            notification_status = _ensure_notification_extension_metadata(
                order,
                requested_at=granted_at,
                operator_user_bid=normalized_operator_user_bid,
                grant_channel=grant_channel,
            )

            db.session.add(order)
            db.session.flush()

            grant_paid_order_credits(app, order)

            db.session.commit()
            return ManualPlanGrantResult(
                user_bid=normalized_user_bid,
                product_bid=product.product_bid,
                product_code=str(product.product_code or "").strip(),
                subscription_bid=str(subscription.subscription_bid or "").strip(),
                bill_order_bid=str(order.bill_order_bid or "").strip(),
                current_period_start_at=subscription.current_period_start_at,
                current_period_end_at=subscription.current_period_end_at,
                notification_status=notification_status,
                reused_existing_request=False,
            )
        finally:
            try:
                grant_lock.release()
            except LockError:
                pass
