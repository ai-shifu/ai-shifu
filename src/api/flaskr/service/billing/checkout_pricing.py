"""Stripe price mappings, campaign discounts, and payable amounts for checkout."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.common.models import raise_error

from .campaign_provider_discounts import (
    load_current_stripe_campaign_provider_discount,
)
from .consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
)
from .primitives import normalize_bid as _normalize_bid
from .provider_price_mappings import (
    ProviderPriceMappingError,
    ProviderPriceRuntimeScope,
    get_current_stripe_active_provider_price_mapping,
    serialize_provider_price_mapping,
)

if TYPE_CHECKING:
    from flask import Flask

    from .models import (
        BillingCampaignProviderDiscount,
        BillingOrder,
        BillingProduct,
        BillingProductProviderPrice,
    )


def _resolve_required_stripe_provider_price_mapping(
    app: Flask,
    *,
    product: BillingProduct,
    scope: ProviderPriceRuntimeScope | None = None,
) -> BillingProductProviderPrice:
    try:
        mapping = get_current_stripe_active_provider_price_mapping(
            app,
            product_bid=product.product_bid,
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


def _resolve_stripe_campaign_provider_discount(
    *,
    applied_campaign: object | None,
    product: BillingProduct,
    provider_price_mapping: BillingProductProviderPrice | None,
) -> BillingCampaignProviderDiscount | None:
    if (
        provider_price_mapping is None
        or applied_campaign is None
        or not _stripe_campaign_affects_charge_amount(applied_campaign)
    ):
        return None
    row = load_current_stripe_campaign_provider_discount(
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


def _stripe_campaign_affects_charge_amount(campaign: object) -> bool:
    return bool(
        getattr(campaign, "campaign_bid", "")
        and int(getattr(campaign, "benefit_type_code", 0) or 0)
        == BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT
    )
