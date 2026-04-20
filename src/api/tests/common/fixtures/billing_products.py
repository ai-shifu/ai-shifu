from __future__ import annotations

from typing import Any, Iterable, Mapping

from flaskr.service.billing.consts import list_billing_bootstrap_product_rows
from flaskr.service.billing.models import BillingProduct


def list_billing_product_rows(
    *,
    product_bids: Iterable[str] | None = None,
    overrides_by_bid: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return list_billing_bootstrap_product_rows(
        product_bids=product_bids,
        overrides_by_bid=overrides_by_bid,
    )


def build_bill_products(
    *,
    product_bids: Iterable[str] | None = None,
    overrides_by_bid: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[BillingProduct]:
    products: list[BillingProduct] = []
    for row in list_billing_product_rows(
        product_bids=product_bids,
        overrides_by_bid=overrides_by_bid,
    ):
        payload = dict(row)
        payload["metadata_json"] = payload.pop("metadata", None)
        products.append(BillingProduct(**payload))
    return products


build_billing_products = build_bill_products


def build_billing_product(
    product_bid: str,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> BillingProduct:
    overrides_by_bid = {product_bid: dict(overrides)} if overrides is not None else None
    return build_bill_products(
        product_bids=[product_bid],
        overrides_by_bid=overrides_by_bid,
    )[0]
