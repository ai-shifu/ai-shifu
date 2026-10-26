"""Health evaluation helpers for provider catalog snapshots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .consts import (
    BILLING_INTERVAL_LABELS,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_PROVIDER_CATALOG_HEALTH_ACCOUNT_MISMATCH,
    BILLING_PROVIDER_CATALOG_HEALTH_DRIFT,
    BILLING_PROVIDER_CATALOG_HEALTH_INACTIVE,
    BILLING_PROVIDER_CATALOG_HEALTH_MODE_MISMATCH,
    BILLING_PROVIDER_CATALOG_HEALTH_OK,
    BILLING_PROVIDER_CATALOG_HEALTH_UNLINKED,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
)
from .models import (
    BillingProduct,
    BillingProductProviderPrice,
    BillingProviderCatalogSnapshot,
)
from .primitives import normalize_json_object
from .provider_price_mappings import PROVIDER_STRIPE

if TYPE_CHECKING:
    from .provider_catalog import ProviderPriceSnapshot

_OBJECT_TYPE_PRODUCT = "product"
_OBJECT_TYPE_PRICE = "price"


def apply_product_health(row: BillingProviderCatalogSnapshot) -> None:
    """Evaluate Product snapshot health and linked local mapping."""
    active_mappings = _active_mappings_for_product(row)
    suggested_product_bid = _suggest_product_bid(row.metadata_json or {})
    if active_mappings:
        row.linked_product_bid = active_mappings[0].product_bid
        if not row.active:
            row.health_status = BILLING_PROVIDER_CATALOG_HEALTH_INACTIVE
            row.pending_issue_code = "provider_product_inactive"
            _invalidate_mappings(active_mappings, "provider_product_inactive")
            return
        row.health_status = BILLING_PROVIDER_CATALOG_HEALTH_OK
        row.pending_issue_code = ""
        return
    scope_issue = _detect_cross_scope_issue(row, _OBJECT_TYPE_PRODUCT)
    if scope_issue is not None:
        row.health_status = scope_issue[0]
        row.pending_issue_code = scope_issue[1]
        row.linked_product_bid = scope_issue[2]
        return
    row.linked_product_bid = suggested_product_bid
    row.health_status = BILLING_PROVIDER_CATALOG_HEALTH_UNLINKED
    row.pending_issue_code = "provider_product_unlinked"


def apply_price_health(
    row: BillingProviderCatalogSnapshot,
    price: ProviderPriceSnapshot,
) -> None:
    """Evaluate Price snapshot health and linked local mapping."""
    active_mappings = _active_mappings_for_price(row)
    suggested_product_bid = _suggest_product_bid(row.metadata_json or {})
    if not active_mappings:
        scope_issue = _detect_cross_scope_issue(row, _OBJECT_TYPE_PRICE)
        if scope_issue is not None:
            row.health_status = scope_issue[0]
            row.pending_issue_code = scope_issue[1]
            row.linked_product_bid = scope_issue[2]
            return
        row.linked_product_bid = suggested_product_bid
        row.health_status = BILLING_PROVIDER_CATALOG_HEALTH_UNLINKED
        row.pending_issue_code = "provider_price_unlinked"
        return
    row.linked_product_bid = active_mappings[0].product_bid
    issue = _detect_price_mapping_issue(active_mappings[0], price)
    if issue:
        row.health_status = issue[0]
        row.pending_issue_code = issue[1]
        if issue[0] in {
            BILLING_PROVIDER_CATALOG_HEALTH_INACTIVE,
            BILLING_PROVIDER_CATALOG_HEALTH_DRIFT,
            BILLING_PROVIDER_CATALOG_HEALTH_ACCOUNT_MISMATCH,
        }:
            _invalidate_mappings(active_mappings, issue[1])
        return
    row.health_status = BILLING_PROVIDER_CATALOG_HEALTH_OK
    row.pending_issue_code = ""


def _detect_price_mapping_issue(
    mapping: BillingProductProviderPrice,
    price: ProviderPriceSnapshot,
) -> tuple[int, str] | None:
    if not price.active:
        return BILLING_PROVIDER_CATALOG_HEALTH_INACTIVE, "provider_price_inactive"
    if price.product_id != mapping.provider_product_id:
        return BILLING_PROVIDER_CATALOG_HEALTH_DRIFT, "price_product_mismatch"
    if int(price.unit_amount or 0) != int(mapping.unit_amount or 0):
        return BILLING_PROVIDER_CATALOG_HEALTH_DRIFT, "unit_amount_mismatch"
    if price.currency.upper() != str(mapping.currency or "").upper():
        return BILLING_PROVIDER_CATALOG_HEALTH_DRIFT, "currency_mismatch"
    expected_type = (
        "recurring"
        if int(mapping.billing_mode or 0) == BILLING_MODE_RECURRING
        else "one_time"
    )
    if price.price_type != expected_type:
        return BILLING_PROVIDER_CATALOG_HEALTH_DRIFT, "billing_mode_mismatch"
    if int(mapping.billing_mode or 0) == BILLING_MODE_RECURRING:
        expected_interval = BILLING_INTERVAL_LABELS.get(
            int(mapping.billing_interval or 0), ""
        )
        if price.recurring_interval != expected_interval:
            return BILLING_PROVIDER_CATALOG_HEALTH_DRIFT, "billing_interval_mismatch"
        if int(price.recurring_interval_count or 0) != int(
            mapping.billing_interval_count or 0
        ):
            return (
                BILLING_PROVIDER_CATALOG_HEALTH_DRIFT,
                "billing_interval_count_mismatch",
            )
    return None


def _active_mappings_for_product(
    row: BillingProviderCatalogSnapshot,
) -> list[BillingProductProviderPrice]:
    return BillingProductProviderPrice.query.filter(
        BillingProductProviderPrice.deleted == 0,
        BillingProductProviderPrice.provider == PROVIDER_STRIPE,
        BillingProductProviderPrice.provider_account_id == row.provider_account_id,
        BillingProductProviderPrice.livemode == int(row.livemode or 0),
        BillingProductProviderPrice.provider_product_id == row.object_id,
        BillingProductProviderPrice.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    ).all()


def _active_mappings_for_price(
    row: BillingProviderCatalogSnapshot,
) -> list[BillingProductProviderPrice]:
    return BillingProductProviderPrice.query.filter(
        BillingProductProviderPrice.deleted == 0,
        BillingProductProviderPrice.provider == PROVIDER_STRIPE,
        BillingProductProviderPrice.provider_account_id == row.provider_account_id,
        BillingProductProviderPrice.livemode == int(row.livemode or 0),
        BillingProductProviderPrice.provider_price_id == row.object_id,
        BillingProductProviderPrice.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    ).all()


def _detect_cross_scope_issue(
    row: BillingProviderCatalogSnapshot,
    object_type: str,
) -> tuple[int, str, str] | None:
    query = BillingProductProviderPrice.query.filter(
        BillingProductProviderPrice.deleted == 0,
        BillingProductProviderPrice.provider == PROVIDER_STRIPE,
        BillingProductProviderPrice.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    )
    if object_type == _OBJECT_TYPE_PRICE:
        query = query.filter(
            BillingProductProviderPrice.provider_price_id == row.object_id
        )
    else:
        query = query.filter(
            BillingProductProviderPrice.provider_product_id == row.object_id
        )
    mapping = query.order_by(BillingProductProviderPrice.id.asc()).first()
    if mapping is None:
        return None
    if mapping.provider_account_id != row.provider_account_id:
        return (
            BILLING_PROVIDER_CATALOG_HEALTH_ACCOUNT_MISMATCH,
            "provider_account_mismatch",
            mapping.product_bid,
        )
    if int(mapping.livemode or 0) != int(row.livemode or 0):
        return (
            BILLING_PROVIDER_CATALOG_HEALTH_MODE_MISMATCH,
            "provider_livemode_mismatch",
            mapping.product_bid,
        )
    return None


def _invalidate_mappings(
    mappings: list[BillingProductProviderPrice], issue_code: str
) -> None:
    for mapping in mappings:
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_INVALID
        mapping.validation_error = json.dumps(
            [{"code": issue_code}],
            separators=(",", ":"),
        )


def _suggest_product_bid(metadata: object) -> str:
    product_code = str(
        normalize_json_object(metadata).get("product_code") or ""
    ).strip()
    if not product_code:
        return ""
    product = BillingProduct.query.filter(
        BillingProduct.deleted == 0,
        BillingProduct.product_code == product_code,
        BillingProduct.product_type.in_(
            [BILLING_PRODUCT_TYPE_PLAN, BILLING_PRODUCT_TYPE_TOPUP]
        ),
    ).one_or_none()
    return product.product_bid if product is not None else ""
