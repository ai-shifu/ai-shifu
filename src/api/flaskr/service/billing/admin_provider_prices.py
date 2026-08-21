"""Admin helpers for billing provider price mapping management."""

from __future__ import annotations

from typing import Any

from flask import Flask
from flaskr.service.common.models import raise_param_error

from .consts import (
    BILLING_INTERVAL_LABELS,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_LABELS,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_PROVIDER_PRICE_STATUS_LABELS,
)
from .models import BillingProduct
from .primitives import credit_decimal_to_number, normalize_bid, normalize_json_object
from .provider_catalog import ProviderCatalogReadError, StripeCatalogReadAdapter
from .provider_price_mappings import (
    PROVIDER_STRIPE,
    ProviderPriceMappingError,
    ProviderPriceMappingValidationSummary,
    activate_provider_price_mapping,
    list_provider_price_mappings,
    retire_provider_price_mapping,
    serialize_provider_price_mapping,
    upsert_provider_price_mapping,
    validate_provider_price_mapping_by_bid,
)

_STATUS_LABEL_TO_CODE = {
    label: code for code, label in BILLING_PROVIDER_PRICE_STATUS_LABELS.items()
}


def build_admin_billing_provider_prices_page(
    app: Flask,
    *,
    product_bid: str = "",
    provider_account_id: str = "",
    livemode: bool | None = None,
    status: str = "",
) -> dict[str, Any]:
    """Return active billing products with their Stripe price mapping history."""
    with app.app_context():
        products = _load_admin_provider_price_products(product_bid=product_bid)
        mappings = list_provider_price_mappings(
            product_bid=product_bid,
            provider=PROVIDER_STRIPE,
            provider_account_id=provider_account_id,
            livemode=livemode,
            status=_resolve_status_filter(status),
        )
        product_bid_set = {row["product_bid"] for row in products}
        visible_mappings = [
            serialize_provider_price_mapping(row)
            for row in mappings
            if row.product_bid in product_bid_set or normalize_bid(product_bid)
        ]
        active_by_product: dict[str, dict[str, Any]] = {}
        history_by_product: dict[str, list[dict[str, Any]]] = {}
        for mapping in visible_mappings:
            if not mapping:
                continue
            product_key = str(mapping.get("product_bid") or "")
            history_by_product.setdefault(product_key, []).append(mapping)
            if mapping.get("status_label") == "active":
                active_by_product[product_key] = mapping

        return {
            "products": products,
            "mappings": visible_mappings,
            "active_by_product": active_by_product,
            "history_by_product": history_by_product,
            "status_options": [
                {"value": label, "code": code}
                for code, label in BILLING_PROVIDER_PRICE_STATUS_LABELS.items()
            ],
        }


def create_admin_billing_provider_price_mapping(
    app: Flask,
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        provider_product_id = str(payload.get("provider_product_id") or "")
        provider_price_id = str(payload.get("provider_price_id") or "")
        provider_account_id = str(payload.get("provider_account_id") or "")
        livemode = payload.get("livemode")
        if not provider_account_id or livemode is None:
            snapshot = _read_provider_snapshot(
                app,
                provider_product_id=provider_product_id,
                provider_price_id=provider_price_id,
            )
            provider_account_id = provider_account_id or snapshot.account.account_id
            if livemode is None:
                livemode = snapshot.price.livemode

        mapping, created = upsert_provider_price_mapping(
            product_bid=str(payload.get("product_bid") or ""),
            provider_account_id=provider_account_id,
            provider_product_id=provider_product_id,
            provider_price_id=provider_price_id,
            livemode=_coerce_livemode(livemode),
            provider=PROVIDER_STRIPE,
            metadata=_coerce_metadata(payload.get("metadata")),
        )
        return {
            "created": created,
            "mapping": serialize_provider_price_mapping(mapping),
        }


def validate_admin_billing_provider_price_mapping(
    app: Flask,
    *,
    provider_price_bid: str,
) -> dict[str, Any]:
    with app.app_context():
        return _serialize_validation_summary(
            validate_provider_price_mapping_by_bid(provider_price_bid)
        )


def activate_admin_billing_provider_price_mapping(
    app: Flask,
    *,
    provider_price_bid: str,
) -> dict[str, Any]:
    with app.app_context():
        return _serialize_validation_summary(
            activate_provider_price_mapping(provider_price_bid)
        )


def retire_admin_billing_provider_price_mapping(
    app: Flask,
    *,
    provider_price_bid: str,
) -> dict[str, Any]:
    with app.app_context():
        mapping = retire_provider_price_mapping(provider_price_bid)
        return {"mapping": serialize_provider_price_mapping(mapping)}


def _read_provider_snapshot(
    app: Flask,
    *,
    provider_product_id: str,
    provider_price_id: str,
):
    try:
        return StripeCatalogReadAdapter().retrieve_mapping_snapshot(
            app,
            provider_product_id=provider_product_id,
            provider_price_id=provider_price_id,
        )
    except ProviderCatalogReadError as exc:
        raise ProviderPriceMappingError(exc.code, str(exc)) from None


def _serialize_validation_summary(
    summary: ProviderPriceMappingValidationSummary,
) -> dict[str, Any]:
    return {
        "valid": bool(summary.valid),
        "errors": summary.errors,
        "warnings": summary.warnings,
        "mapping": summary.mapping,
    }


def _load_admin_provider_price_products(
    *, product_bid: str = ""
) -> list[dict[str, Any]]:
    query = BillingProduct.query.filter(
        BillingProduct.deleted == 0,
        BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
        BillingProduct.product_type.in_(
            [BILLING_PRODUCT_TYPE_PLAN, BILLING_PRODUCT_TYPE_TOPUP]
        ),
    )
    normalized_product_bid = normalize_bid(product_bid)
    if normalized_product_bid:
        query = query.filter(BillingProduct.product_bid == normalized_product_bid)
    rows = query.order_by(
        BillingProduct.sort_order.asc(), BillingProduct.id.asc()
    ).all()
    return [_serialize_admin_provider_price_product(row) for row in rows]


def _serialize_admin_provider_price_product(row: BillingProduct) -> dict[str, Any]:
    metadata = normalize_json_object(row.metadata_json or {})
    product_type = BILLING_PRODUCT_TYPE_LABELS.get(int(row.product_type or 0), "")
    billing_interval = BILLING_INTERVAL_LABELS.get(
        int(row.billing_interval or 0), "none"
    )
    return {
        "product_bid": row.product_bid,
        "product_code": row.product_code,
        "product_type": product_type,
        "display_name": row.display_name_i18n_key,
        "description": row.description_i18n_key,
        "currency": row.currency,
        "price_amount": int(row.price_amount or 0),
        "credit_amount": credit_decimal_to_number(row.credit_amount),
        "billing_interval": billing_interval,
        "billing_interval_count": int(row.billing_interval_count or 0),
        "plan_tier": metadata.to_metadata_json().get("plan_tier"),
        "sort_order": int(row.sort_order or 0),
    }


def _resolve_status_filter(status: str) -> int | None:
    normalized = str(status or "").strip().lower()
    if not normalized:
        return None
    if normalized not in _STATUS_LABEL_TO_CODE:
        raise_param_error("status")
    return _STATUS_LABEL_TO_CODE[normalized]


def _coerce_livemode(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on", "live"}:
        return True
    if normalized in {"0", "false", "no", "off", "test"}:
        return False
    raise_param_error("livemode")
    return False


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise_param_error("metadata")
    return normalize_json_object(value).to_metadata_json()


def provider_price_mapping_error_payload(
    error: ProviderPriceMappingError,
) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": str(error),
        "details": error.details,
    }
