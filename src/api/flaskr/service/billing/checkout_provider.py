"""Provider checkout request building, provider calls, and write-back."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flaskr.common.public_urls import build_stripe_billing_result_url
from flaskr.dao import db
from flaskr.dao.uow import (
    unit_of_work,
)
from flaskr.i18n import _ as translate
from flaskr.service.common.models import raise_error
from flaskr.service.order.payment_providers import (
    PaymentCreationResult,
    PaymentRequest,
)
from flaskr.util.datetime import now_utc

from .checkout_orders import (
    _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS,
    _build_checkout_response_payload,
    _build_manual_payment_payload,
    _load_billing_order_by_bid,
)
from .checkout_pricing import (
    _build_provider_price_order_metadata,
    _resolve_required_stripe_provider_price_mapping,
    _stored_provider_price_snapshot_matches_mapping,
)
from .checkout_snapshots import (
    _persist_billing_raw_snapshot_from_checkout,
)
from .consts import (
    BILLING_INTERVAL_LABELS,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_PRODUCT_TYPE_PLAN,
)
from .dtos import (
    BillingCheckoutResultDTO,
)
from .paid_side_effects import (
    BillingPaidOrderSideEffects,
)
from .paid_side_effects import (
    stage_billing_paid_order_side_effects as _stage_billing_paid_order_side_effects,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import to_decimal as _to_decimal

if TYPE_CHECKING:
    from types import ModuleType

    from flask import Flask

    from .models import (
        BillingOrder,
        BillingProduct,
        BillingProductProviderPrice,
    )


def _checkout_facade() -> ModuleType:
    """Resolve collaborators through ``checkout`` so its patch points stay live."""
    from . import checkout

    return checkout


_CHECKOUT_PLAN_SUBJECT_PREFIX_KEYS = {
    "day": "module.billing.checkout.subject.plan.day",
    "month": "module.billing.checkout.subject.plan.month",
    "year": "module.billing.checkout.subject.plan.year",
}


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
    provider_options: dict[str, Any] = {"metadata": metadata}

    if payment_provider == "stripe":
        if provider_price_mapping is None:
            provider_price_mapping = _resolve_required_stripe_provider_price_mapping(
                app,
                product=product,
            )
        if not _stored_provider_price_snapshot_matches_mapping(
            order,
            provider_price_mapping,
            metadata=order_metadata,
        ):
            raise_error("server.order.orderStatusError")
        provider_options["mode"] = "checkout_session"
        provider_options["success_url"] = _inject_billing_query(
            build_stripe_billing_result_url(),
            order.bill_order_bid,
        )
        provider_options["cancel_url"] = _inject_billing_query(
            build_stripe_billing_result_url(canceled=True),
            order.bill_order_bid,
        )
        provider_options["session_params"] = {
            "mode": "subscription" if payment_mode == "subscription" else "payment",
        }
        if provider_coupon_id:
            provider_options["discounts"] = [{"coupon": provider_coupon_id}]
        if payment_mode == "subscription":
            provider_options["session_params"]["payment_method_collection"] = "always"
            provider_options["session_params"]["subscription_data"] = {
                "metadata": metadata
            }
            product_amount = int(provider_price_mapping.unit_amount or 0)
            first_invoice_discount_amount = max(
                product_amount - int(order.payable_amount or 0),
                0,
            )
            if first_invoice_discount_amount > 0 and not provider_coupon_id:
                provider_options["subscription_one_time_discount_amount"] = (
                    first_invoice_discount_amount
                )
        provider_options["line_items"] = [
            {
                "price": provider_price_mapping.provider_price_id,
                "quantity": 1,
            }
        ]
    elif payment_provider == "pingxx":
        provider_options.update(
            _build_pingxx_provider_options(
                creator_bid=creator_bid,
                product=product,
                channel=channel,
            )
        )
    else:
        provider_options.update(
            _build_native_provider_options(
                creator_bid=creator_bid,
                product=product,
                provider=payment_provider,
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
    return _ProviderCheckoutRequest(
        bill_order_bid=order.bill_order_bid,
        payment_request=payment_request,
        subject=subject,
        payment_provider=payment_provider,
        payment_mode=payment_mode,
        reused_existing_order=reused_existing_order,
        provider_price_metadata=(
            _build_provider_price_order_metadata(provider_price_mapping)
            if payment_provider == "stripe" and provider_price_mapping is not None
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
    provider = _checkout_facade().get_payment_provider(request.payment_provider)
    if request.payment_mode == "subscription" and request.payment_provider == "stripe":
        return provider.create_subscription(
            request=request.payment_request,
            app=app,
        )
    return provider.create_payment(
        request=request.payment_request,
        app=app,
    )


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
    if payment_provider == "stripe":
        redirect_url = str(result.extra.get("url") or "")
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
        order = _load_billing_order_by_bid(request.bill_order_bid)
        if order is None:
            raise_error("server.order.orderNotFound")
        if int(order.status or 0) == BILLING_ORDER_STATUS_PENDING:
            return _persist_provider_checkout(order, result, request)

        # A callback settled the order while the charge was being created.
        # Keep the raw snapshot so the new charge stays reconcilable, but
        # never point a settled order at it. The snapshot is written here and
        # committed by this block; the error is raised only afterwards, so it
        # cannot take the snapshot down with it.
        _persist_billing_raw_snapshot_from_checkout(
            order,
            result,
            subject=request.subject,
            body=request.subject,
            # The charge itself is pending, whatever became of the order.
            raw_snapshot_status=_RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS[
                BILLING_ORDER_STATUS_PENDING
            ],
        )
        settled_status = int(order.status or 0)

    app.logger.warning(
        "Billing order %s left status %s while its %s charge %s was being "
        "created; snapshot kept for reconciliation",
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


def _build_pingxx_provider_options(
    *,
    creator_bid: str,
    product: BillingProduct,
    channel: str,
) -> dict[str, object]:
    normalized_channel = _normalize_bid(channel)
    charge_extra: dict[str, Any]

    if normalized_channel == "wx_pub_qr":
        charge_extra = {"product_id": product.product_bid}
    elif normalized_channel == "alipay_qr":
        charge_extra = {}
    elif normalized_channel == "wx_pub":
        user = _checkout_facade().load_user_aggregate(creator_bid)
        open_id = str(user.wechat_open_id or "").strip() if user else ""
        if not open_id:
            raise_error("server.pay.wechatOpenIdRequired")
        charge_extra = {"open_id": open_id}
    elif normalized_channel == "wx_wap":
        charge_extra = {}
    else:
        raise_error("server.pay.payChannelNotSupport")

    return {
        "app_id": str(_checkout_facade().get_config("PINGXX_APP_ID", "") or "").strip(),
        "charge_extra": charge_extra,
    }


def _build_native_provider_options(
    *,
    creator_bid: str,
    product: BillingProduct,
    provider: str,
    channel: str,
) -> dict[str, object]:
    normalized_channel = _normalize_bid(channel)
    del product
    if provider == "alipay":
        if normalized_channel != "alipay_qr":
            raise_error("server.pay.payChannelNotSupport")
        return {}
    if provider == "wechatpay":
        if normalized_channel == "wx_pub_qr":
            return {}
        if normalized_channel == "wx_pub":
            user = _checkout_facade().load_user_aggregate(creator_bid)
            open_id = str(user.wechat_open_id or "").strip() if user else ""
            if not open_id:
                raise_error("server.pay.wechatOpenIdRequired")
            return {"open_id": open_id}
        raise_error("server.pay.payChannelNotSupport")
    raise_error("server.pay.payChannelNotSupport")
    return None


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
