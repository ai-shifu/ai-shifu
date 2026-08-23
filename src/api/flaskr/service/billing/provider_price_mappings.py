"""Lifecycle helpers for billing product provider price mappings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from flask import current_app
from flaskr.dao import db
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_DRAFT,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
    BILLING_PROVIDER_PRICE_STATUS_LABELS,
    BILLING_PROVIDER_PRICE_STATUS_RETIRED,
)
from .models import BillingProduct, BillingProductProviderPrice
from .primitives import normalize_bid, normalize_json_object
from .provider_catalog import (
    ProviderCatalogReadError,
    ProviderCatalogSnapshot,
    StripeCatalogReadAdapter,
    validate_provider_price_mapping,
)

PROVIDER_STRIPE = "stripe"


@dataclass(slots=True)
class ProviderPriceMappingError(RuntimeError):
    """Represent a provider-price mapping error with structured details."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """Return the validation error message."""
        return self.message


@dataclass(slots=True)
class ProviderPriceMappingValidationSummary:
    """Summarize validation results and serialized data for a provider-price mapping."""

    valid: bool
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    mapping: dict[str, Any] | None = None


def serialize_provider_price_mapping(
    mapping: BillingProductProviderPrice | None,
) -> dict[str, Any] | None:
    """Serialize an optional provider-price mapping for an API or CLI payload."""
    if mapping is None:
        return None
    metadata = normalize_json_object(mapping.metadata_json or {})
    return {
        "provider_price_bid": mapping.provider_price_bid,
        "product_bid": mapping.product_bid,
        "provider": mapping.provider,
        "provider_account_id": mapping.provider_account_id,
        "provider_product_id": mapping.provider_product_id,
        "provider_price_id": mapping.provider_price_id,
        "livemode": bool(mapping.livemode),
        "currency": mapping.currency,
        "unit_amount": int(mapping.unit_amount or 0),
        "billing_mode": int(mapping.billing_mode or 0),
        "billing_interval": int(mapping.billing_interval or 0),
        "billing_interval_count": int(mapping.billing_interval_count or 0),
        "status": int(mapping.status or 0),
        "status_label": BILLING_PROVIDER_PRICE_STATUS_LABELS.get(
            int(mapping.status or 0), "unknown"
        ),
        "validated_at": to_utc_iso(mapping.validated_at),
        "activated_at": to_utc_iso(mapping.activated_at),
        "retired_at": to_utc_iso(mapping.retired_at),
        "validation_error": mapping.validation_error or "",
        "metadata": metadata.to_metadata_json(),
    }


def list_provider_price_mappings(
    *,
    product_bid: str = "",
    provider: str = PROVIDER_STRIPE,
    provider_account_id: str = "",
    livemode: bool | None = None,
    status: int | None = None,
) -> list[BillingProductProviderPrice]:
    """Return non-deleted provider-price mappings matching the supplied filters."""
    query = BillingProductProviderPrice.query.filter(
        BillingProductProviderPrice.deleted == 0,
        BillingProductProviderPrice.provider == _normalize_provider(provider),
    )
    normalized_product_bid = normalize_bid(product_bid)
    if normalized_product_bid:
        query = query.filter(
            BillingProductProviderPrice.product_bid == normalized_product_bid
        )
    normalized_account_id = normalize_bid(provider_account_id)
    if normalized_account_id:
        query = query.filter(
            BillingProductProviderPrice.provider_account_id == normalized_account_id
        )
    if livemode is not None:
        query = query.filter(
            BillingProductProviderPrice.livemode == int(bool(livemode))
        )
    if status is not None:
        query = query.filter(BillingProductProviderPrice.status == int(status))
    return query.order_by(
        BillingProductProviderPrice.product_bid.asc(),
        BillingProductProviderPrice.status.asc(),
        BillingProductProviderPrice.updated_at.desc(),
        BillingProductProviderPrice.id.desc(),
    ).all()


def get_provider_price_mapping(
    provider_price_bid: str,
) -> BillingProductProviderPrice:
    """Return the non-deleted provider-price mapping for a business identifier."""
    return _load_mapping(provider_price_bid)


def get_active_provider_price_mapping(
    *,
    product_bid: str,
    provider: str = PROVIDER_STRIPE,
    provider_account_id: str,
    livemode: bool,
) -> BillingProductProviderPrice | None:
    """Return the sole active mapping for a product and provider scope."""
    rows = (
        BillingProductProviderPrice.query.filter(
            BillingProductProviderPrice.deleted == 0,
            BillingProductProviderPrice.product_bid == normalize_bid(product_bid),
            BillingProductProviderPrice.provider == _normalize_provider(provider),
            BillingProductProviderPrice.provider_account_id
            == normalize_bid(provider_account_id),
            BillingProductProviderPrice.livemode == int(bool(livemode)),
            BillingProductProviderPrice.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
        )
        .order_by(BillingProductProviderPrice.id.asc())
        .limit(2)
        .all()
    )
    return _select_single_active_mapping(rows, product_bid=normalize_bid(product_bid))


def _select_single_active_mapping(
    rows: list[BillingProductProviderPrice],
    *,
    product_bid: str,
) -> BillingProductProviderPrice | None:
    if len(rows) > 1:
        error_code = "multiple_active_provider_prices"
        raise ProviderPriceMappingError(
            error_code,
            "Multiple active provider price mappings found for the same product scope",
            {"product_bid": product_bid},
        )
    return rows[0] if rows else None


def upsert_provider_price_mapping(
    *,
    product_bid: str,
    provider_account_id: str,
    provider_product_id: str,
    provider_price_id: str,
    livemode: bool,
    provider: str = PROVIDER_STRIPE,
    metadata: dict[str, Any] | None = None,
) -> tuple[BillingProductProviderPrice, bool]:
    """Create or update a draft provider-price mapping for a billing product."""
    product = _load_product(product_bid)
    normalized_provider = _normalize_provider(provider)
    normalized_account_id = _require_value(provider_account_id, "provider_account_id")
    normalized_product_id = _require_value(provider_product_id, "provider_product_id")
    normalized_price_id = _require_value(provider_price_id, "provider_price_id")
    normalized_livemode = int(bool(livemode))

    row = _load_mapping_by_provider_price(
        provider=normalized_provider,
        provider_account_id=normalized_account_id,
        livemode=normalized_livemode,
        provider_price_id=normalized_price_id,
    )
    created = row is None
    if row is None:
        row = BillingProductProviderPrice(
            provider_price_bid=generate_id(current_app),
            status=BILLING_PROVIDER_PRICE_STATUS_DRAFT,
            deleted=0,
        )
        db.session.add(row)
    elif row.product_bid and row.product_bid != product.product_bid:
        error_code = "provider_price_product_mismatch"
        raise ProviderPriceMappingError(
            error_code,
            "Provider price mappings cannot be rebound to a different product",
            {
                "provider_price_bid": row.provider_price_bid,
                "existing_product_bid": row.product_bid,
                "requested_product_bid": product.product_bid,
            },
        )
    elif int(row.status or 0) == BILLING_PROVIDER_PRICE_STATUS_ACTIVE:
        error_code = "active_mapping_cannot_be_rebound"
        raise ProviderPriceMappingError(
            error_code,
            "Active provider price mappings cannot be rebound; retire them first",
            {"provider_price_bid": row.provider_price_bid},
        )
    elif int(row.status or 0) == BILLING_PROVIDER_PRICE_STATUS_RETIRED:
        error_code = "retired_mapping_cannot_be_rebound"
        raise ProviderPriceMappingError(
            error_code,
            "Retired provider price mappings cannot be rebound; create a new provider price instead",
            {"provider_price_bid": row.provider_price_bid},
        )
    elif int(row.status or 0) == BILLING_PROVIDER_PRICE_STATUS_INVALID:
        row.status = BILLING_PROVIDER_PRICE_STATUS_DRAFT
        row.validated_at = None
        row.activated_at = None
        row.retired_at = None
        row.validation_error = ""

    row.product_bid = product.product_bid
    row.provider = normalized_provider
    row.provider_account_id = normalized_account_id
    row.provider_product_id = normalized_product_id
    row.provider_price_id = normalized_price_id
    row.livemode = normalized_livemode
    row.currency = str(product.currency or "").strip().upper()
    row.unit_amount = int(product.price_amount or 0)
    row.billing_mode = int(product.billing_mode or 0)
    row.billing_interval = int(product.billing_interval or 0)
    row.billing_interval_count = int(product.billing_interval_count or 0)
    row.metadata_json = dict(metadata or {})
    row.deleted = 0
    db.session.flush()
    return row, created


def validate_provider_price_mapping_row(
    mapping: BillingProductProviderPrice,
    *,
    adapter: StripeCatalogReadAdapter | None = None,
) -> tuple[ProviderPriceMappingValidationSummary, ProviderCatalogSnapshot | None]:
    """Validate one mapping against the provider catalog and return its snapshot."""
    product = _load_product(mapping.product_bid)
    reader = adapter or StripeCatalogReadAdapter()
    try:
        snapshot = reader.retrieve_mapping_snapshot(
            current_app,
            provider_product_id=mapping.provider_product_id,
            provider_price_id=mapping.provider_price_id,
        )
    except ProviderCatalogReadError as exc:
        summary = ProviderPriceMappingValidationSummary(
            valid=False,
            errors=[{"code": exc.code, "message": str(exc)}],
            warnings=[],
            mapping=serialize_provider_price_mapping(mapping),
        )
        return summary, None

    result = validate_provider_price_mapping(
        product,
        snapshot,
        expected_provider_account_id=mapping.provider_account_id,
        expected_livemode=bool(mapping.livemode),
        expected_provider_product_id=mapping.provider_product_id,
        expected_provider_price_id=mapping.provider_price_id,
    )
    summary = ProviderPriceMappingValidationSummary(
        valid=result.valid,
        errors=_serialize_validation_issues(result.errors),
        warnings=_serialize_validation_issues(result.warnings),
        mapping=serialize_provider_price_mapping(mapping),
    )
    return summary, snapshot


def validate_provider_price_mapping_by_bid(
    provider_price_bid: str,
    *,
    adapter: StripeCatalogReadAdapter | None = None,
) -> ProviderPriceMappingValidationSummary:
    """Validate and persist the status of a provider-price mapping by identifier."""
    mapping = _load_mapping(provider_price_bid)
    summary, snapshot = validate_provider_price_mapping_row(mapping, adapter=adapter)
    _apply_validation_result(mapping, summary, snapshot)
    db.session.flush()
    summary.mapping = serialize_provider_price_mapping(mapping)
    return summary


def activate_provider_price_mapping(
    provider_price_bid: str,
    *,
    adapter: StripeCatalogReadAdapter | None = None,
) -> ProviderPriceMappingValidationSummary:
    """Validate, activate, and serialize a provider-price mapping by identifier."""
    mapping = _load_mapping(provider_price_bid)
    summary, snapshot = validate_provider_price_mapping_row(mapping, adapter=adapter)
    if not summary.valid:
        mapping.validated_at = now_utc()
        if snapshot is not None:
            _apply_provider_snapshot(mapping, snapshot)
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_INVALID
        mapping.validation_error = _validation_summary_error_text(summary)
        db.session.flush()
        summary.mapping = serialize_provider_price_mapping(mapping)
        return summary

    now = now_utc()
    active_rows = _load_active_rows_for_mapping_scope(mapping)
    for row in active_rows:
        if row.provider_price_bid == mapping.provider_price_bid:
            continue
        row.status = BILLING_PROVIDER_PRICE_STATUS_RETIRED
        row.retired_at = now
        row.validation_error = ""
    if active_rows:
        db.session.flush()

    mapping.status = BILLING_PROVIDER_PRICE_STATUS_ACTIVE
    mapping.validated_at = now
    mapping.activated_at = mapping.activated_at or now
    mapping.retired_at = None
    mapping.validation_error = _validation_summary_warning_text(summary)
    if snapshot is not None:
        _apply_provider_snapshot(mapping, snapshot)
    db.session.flush()
    summary.mapping = serialize_provider_price_mapping(mapping)
    return summary


def retire_provider_price_mapping(
    provider_price_bid: str,
) -> BillingProductProviderPrice:
    """Retire a provider-price mapping and return its persisted record."""
    mapping = _load_mapping(provider_price_bid)
    if int(mapping.status or 0) != BILLING_PROVIDER_PRICE_STATUS_RETIRED:
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_RETIRED
        mapping.retired_at = now_utc()
        mapping.validation_error = ""
    db.session.flush()
    return mapping


def _load_product(product_bid: str) -> BillingProduct:
    normalized_product_bid = _require_value(product_bid, "product_bid")
    product = BillingProduct.query.filter(
        BillingProduct.deleted == 0,
        BillingProduct.product_bid == normalized_product_bid,
    ).one_or_none()
    if product is None:
        error_code = "billing_product_not_found"
        raise ProviderPriceMappingError(
            error_code,
            "Billing product not found",
            {"product_bid": normalized_product_bid},
        )
    return product


def _load_mapping(provider_price_bid: str) -> BillingProductProviderPrice:
    normalized_bid = _require_value(provider_price_bid, "provider_price_bid")
    mapping = BillingProductProviderPrice.query.filter(
        BillingProductProviderPrice.deleted == 0,
        BillingProductProviderPrice.provider_price_bid == normalized_bid,
    ).one_or_none()
    if mapping is None:
        error_code = "provider_price_mapping_not_found"
        raise ProviderPriceMappingError(
            error_code,
            "Provider price mapping not found",
            {"provider_price_bid": normalized_bid},
        )
    return mapping


def _load_mapping_by_provider_price(
    *,
    provider: str,
    provider_account_id: str,
    livemode: int,
    provider_price_id: str,
) -> BillingProductProviderPrice | None:
    return BillingProductProviderPrice.query.filter(
        BillingProductProviderPrice.deleted == 0,
        BillingProductProviderPrice.provider == provider,
        BillingProductProviderPrice.provider_account_id == provider_account_id,
        BillingProductProviderPrice.livemode == int(livemode),
        BillingProductProviderPrice.provider_price_id == provider_price_id,
    ).one_or_none()


def _load_active_rows_for_mapping_scope(
    mapping: BillingProductProviderPrice,
) -> list[BillingProductProviderPrice]:
    return BillingProductProviderPrice.query.filter(
        BillingProductProviderPrice.deleted == 0,
        BillingProductProviderPrice.product_bid == mapping.product_bid,
        BillingProductProviderPrice.provider == mapping.provider,
        BillingProductProviderPrice.provider_account_id == mapping.provider_account_id,
        BillingProductProviderPrice.livemode == int(mapping.livemode or 0),
        BillingProductProviderPrice.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    ).all()


def _apply_provider_snapshot(
    mapping: BillingProductProviderPrice,
    snapshot: ProviderCatalogSnapshot,
) -> None:
    mapping.currency = snapshot.price.currency.upper()
    mapping.unit_amount = int(snapshot.price.unit_amount or 0)


def _apply_validation_result(
    mapping: BillingProductProviderPrice,
    summary: ProviderPriceMappingValidationSummary,
    snapshot: ProviderCatalogSnapshot | None,
) -> None:
    mapping.validated_at = now_utc()
    if snapshot is not None:
        _apply_provider_snapshot(mapping, snapshot)
    mapping.validation_error = (
        _validation_summary_warning_text(summary)
        if summary.valid
        else _validation_summary_error_text(summary)
    )
    if not summary.valid:
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_INVALID


def _validation_summary_error_text(
    summary: ProviderPriceMappingValidationSummary,
) -> str:
    return _safe_issue_summary(summary.errors)


def _validation_summary_warning_text(
    summary: ProviderPriceMappingValidationSummary,
) -> str:
    return _safe_issue_summary(summary.warnings)


def _safe_issue_summary(issues: list[dict[str, str]]) -> str:
    if not issues:
        return ""
    return json.dumps(
        [{"code": issue.get("code", "")} for issue in issues],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _serialize_validation_issues(issues: object) -> list[dict[str, str]]:
    return [
        {
            "code": issue.code,
            "message": issue.message,
            "expected": issue.expected,
            "actual": issue.actual,
        }
        for issue in issues
    ]


def _normalize_provider(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized != PROVIDER_STRIPE:
        error_code = "unsupported_provider"
        raise ProviderPriceMappingError(
            error_code,
            "Only Stripe provider price mappings are supported",
            {"provider": normalized},
        )
    return normalized


def _require_value(value: str, name: str) -> str:
    normalized = normalize_bid(value)
    if not normalized:
        code = f"{name}_required"
        message = f"{name} is required"
        raise ProviderPriceMappingError(code, message)
    return normalized
