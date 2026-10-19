"""Billing product catalog and provider price mapping helpers for the CLI."""

from __future__ import annotations

import json
from decimal import Decimal

import click
from flaskr.dao.uow import unit_of_work

from .cli_support import (
    _ALLOCATION_INTERVAL_LABELS,
    _BILLING_INTERVAL_LABELS,
    _BILLING_MODE_LABELS,
    _PRODUCT_STATUS_LABELS,
    _PRODUCT_TYPE_LABELS,
    _PROVIDER_PRICE_STATUS_LABELS,
    _parse_optional_json_object,
    _upsert_bootstrap_row,
)
from .models import BillingProduct
from .provider_price_mappings import (
    ProviderPriceMappingError,
    activate_provider_price_mapping,
    get_active_provider_price_mapping,
    get_provider_price_mapping,
    list_provider_price_mappings,
    retire_provider_price_mapping,
    serialize_provider_price_mapping,
    upsert_provider_price_mapping,
    validate_provider_price_mapping_by_bid,
)


def upsert_billing_product(
    *,
    product_bid: str,
    product_code: str,
    product_type_label: str,
    billing_mode_label: str,
    billing_interval_label: str,
    billing_interval_count: int,
    display_name_i18n_key: str,
    description_i18n_key: str,
    currency: str,
    price_amount: int,
    credit_amount: str,
    allocation_interval_label: str,
    auto_renew_enabled: int,
    status_label: str,
    sort_order: int,
    entitlement_json: str,
    metadata_json: str,
) -> dict[str, object]:
    """Create or update billing product."""
    payload = {
        "product_bid": str(product_bid or "").strip(),
        "product_code": str(product_code or "").strip(),
        "product_type": _PRODUCT_TYPE_LABELS[str(product_type_label or "").lower()],
        "billing_mode": _BILLING_MODE_LABELS[str(billing_mode_label or "").lower()],
        "billing_interval": _BILLING_INTERVAL_LABELS[
            str(billing_interval_label or "").lower()
        ],
        "billing_interval_count": int(billing_interval_count or 0),
        "display_name_i18n_key": str(display_name_i18n_key or "").strip(),
        "description_i18n_key": str(description_i18n_key or "").strip(),
        "currency": str(currency or "").strip().upper() or "CNY",
        "price_amount": int(price_amount),
        "credit_amount": Decimal(str(credit_amount or "0").strip()),
        "allocation_interval": _ALLOCATION_INTERVAL_LABELS[
            str(allocation_interval_label or "").lower()
        ],
        "auto_renew_enabled": int(auto_renew_enabled),
        "entitlement_payload": _parse_optional_json_object(
            entitlement_json,
            option_name="entitlement-json",
        ),
        "metadata_json": _parse_optional_json_object(
            metadata_json,
            option_name="metadata-json",
        ),
        "status": _PRODUCT_STATUS_LABELS[str(status_label or "").lower()],
        "sort_order": int(sort_order),
        "deleted": 0,
    }

    if not payload["product_bid"]:
        message = "--product-bid is required."
        raise click.ClickException(message)
    if not payload["product_code"]:
        message = "--product-code is required."
        raise click.ClickException(message)
    if not payload["display_name_i18n_key"]:
        message = "--display-name-i18n-key is required."
        raise click.ClickException(message)
    if not payload["description_i18n_key"]:
        message = "--description-i18n-key is required."
        raise click.ClickException(message)

    with unit_of_work():
        created = _upsert_bootstrap_row(
            model=BillingProduct,
            key_field="product_bid",
            payload=payload,
        )
    return {
        "status": "upserted",
        "created": created,
        "product_bid": payload["product_bid"],
        "product_code": payload["product_code"],
    }


def bind_provider_price_mapping(
    *,
    product_bid: str,
    provider_account_id: str,
    provider_product_id: str,
    provider_price_id: str,
    livemode: bool,
    metadata_json: str,
) -> dict[str, object]:
    """Bind a provider price to a billing product and return its payload."""
    try:
        with unit_of_work():
            mapping, created = upsert_provider_price_mapping(
                product_bid=product_bid,
                provider_account_id=provider_account_id,
                provider_product_id=provider_product_id,
                provider_price_id=provider_price_id,
                livemode=livemode,
                metadata=_parse_optional_json_object(
                    metadata_json,
                    option_name="metadata-json",
                ),
            )
            payload = {
                "status": "bound",
                "created": created,
                "mapping": serialize_provider_price_mapping(mapping),
            }
    except ProviderPriceMappingError as exc:
        raise click.ClickException(_format_provider_price_mapping_error(exc)) from exc
    return payload


def activate_cli_provider_price_mapping(provider_price_bid: str) -> dict[str, object]:
    """Activate a provider-price mapping and return its validation result."""
    try:
        with unit_of_work():
            summary = activate_provider_price_mapping(provider_price_bid)
            payload = {
                "status": "activated" if summary.valid else "invalid",
                "validation": _provider_price_validation_payload(summary),
            }
    except ProviderPriceMappingError as exc:
        raise click.ClickException(_format_provider_price_mapping_error(exc)) from exc
    return payload


def retire_cli_provider_price_mapping(provider_price_bid: str) -> dict[str, object]:
    """Retire a provider-price mapping and return its serialized payload."""
    try:
        with unit_of_work():
            mapping = retire_provider_price_mapping(provider_price_bid)
            payload = {
                "status": "retired",
                "mapping": serialize_provider_price_mapping(mapping),
            }
    except ProviderPriceMappingError as exc:
        raise click.ClickException(_format_provider_price_mapping_error(exc)) from exc
    return payload


def validate_cli_provider_price_mapping(provider_price_bid: str) -> dict[str, object]:
    """Validate a provider-price mapping and return its validation result."""
    try:
        with unit_of_work():
            summary = validate_provider_price_mapping_by_bid(provider_price_bid)
            payload = {
                "status": "valid" if summary.valid else "invalid",
                "validation": _provider_price_validation_payload(summary),
            }
    except ProviderPriceMappingError as exc:
        raise click.ClickException(_format_provider_price_mapping_error(exc)) from exc
    return payload


def list_cli_provider_price_mappings(
    *,
    product_bid: str,
    provider_account_id: str,
    status_label: str,
    livemode: bool | None,
) -> dict[str, object]:
    """List provider-price mappings matching the requested CLI filters."""
    normalized_status = str(status_label or "").strip().lower()
    rows = list_provider_price_mappings(
        product_bid=product_bid,
        provider_account_id=provider_account_id,
        livemode=livemode,
        status=(
            _PROVIDER_PRICE_STATUS_LABELS[normalized_status]
            if normalized_status
            else None
        ),
    )
    return {
        "status": "listed",
        "count": len(rows),
        "items": [serialize_provider_price_mapping(row) for row in rows],
    }


def inspect_cli_provider_price_mapping(provider_price_bid: str) -> dict[str, object]:
    """Return a provider-price mapping and its active mapping in the same scope."""
    try:
        mapping = get_provider_price_mapping(provider_price_bid)
        active_mapping = get_active_provider_price_mapping(
            product_bid=mapping.product_bid,
            provider=mapping.provider,
            provider_account_id=mapping.provider_account_id,
            livemode=bool(mapping.livemode),
        )
    except ProviderPriceMappingError as exc:
        raise click.ClickException(_format_provider_price_mapping_error(exc)) from exc
    return {
        "status": "inspected",
        "mapping": serialize_provider_price_mapping(mapping),
        "active_mapping": serialize_provider_price_mapping(active_mapping),
    }


def _provider_price_validation_payload(summary: object) -> dict[str, object]:
    return {
        "valid": summary.valid,
        "errors": summary.errors,
        "warnings": summary.warnings,
        "mapping": summary.mapping,
    }


def _format_provider_price_mapping_error(exc: ProviderPriceMappingError) -> str:
    return json.dumps(
        {"code": exc.code, "message": exc.message},
        ensure_ascii=False,
        separators=(",", ":"),
    )
