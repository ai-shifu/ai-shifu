"""Runtime bucket-category normalization for creator billing credits."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from .consts import (
    BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
    BILLING_ORDER_TYPE_LABELS,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .models import BillingOrder, CreditWalletBucket
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object

OrderTypeLoader = Callable[[str], int | None]

_BUCKET_PRIORITY_BY_CATEGORY = {
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION: 20,
    CREDIT_BUCKET_CATEGORY_TOPUP: 30,
}
_ORDER_TYPE_BY_LABEL = {
    str(label): code for code, label in BILLING_ORDER_TYPE_LABELS.items()
}
_SUBSCRIPTION_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
}


def resolve_credit_bucket_priority(category: int | None) -> int:
    normalized_category = normalize_runtime_credit_bucket_category(category)
    return _BUCKET_PRIORITY_BY_CATEGORY.get(
        normalized_category,
        _BUCKET_PRIORITY_BY_CATEGORY[CREDIT_BUCKET_CATEGORY_SUBSCRIPTION],
    )


def normalize_runtime_credit_bucket_category(category: int | None) -> int:
    return (
        CREDIT_BUCKET_CATEGORY_TOPUP
        if int(category or 0) == CREDIT_BUCKET_CATEGORY_TOPUP
        else CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    )


def resolve_bucket_category_from_order_type(order_type: int | None) -> int:
    if int(order_type or 0) == BILLING_ORDER_TYPE_TOPUP:
        return CREDIT_BUCKET_CATEGORY_TOPUP
    if int(order_type or 0) in _SUBSCRIPTION_ORDER_TYPES:
        return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION


def resolve_runtime_credit_bucket_category(
    *,
    bucket_category: int | None = None,
    source_type: int | None = None,
    source_bid: str = "",
    metadata: Any | None = None,
    load_order_type: OrderTypeLoader | None = None,
) -> int:
    current_bucket_category = int(bucket_category or 0)
    current_source_type = int(source_type or 0)

    if current_bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP:
        return CREDIT_BUCKET_CATEGORY_TOPUP
    if current_bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION:
        return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    if current_source_type == CREDIT_SOURCE_TYPE_TOPUP:
        return CREDIT_BUCKET_CATEGORY_TOPUP
    if current_source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
        return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    if current_source_type == CREDIT_SOURCE_TYPE_REFUND:
        return _resolve_refund_bucket_category(
            metadata=metadata,
            load_order_type=load_order_type,
        )
    if current_source_type == CREDIT_SOURCE_TYPE_MANUAL:
        return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    if current_source_type == CREDIT_SOURCE_TYPE_GIFT:
        return _resolve_gift_bucket_category(
            source_bid=source_bid,
            metadata=metadata,
            load_order_type=load_order_type,
        )
    if current_bucket_category == CREDIT_BUCKET_CATEGORY_FREE:
        return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION


def resolve_wallet_bucket_runtime_category(
    bucket: CreditWalletBucket,
    *,
    load_order_type: OrderTypeLoader | None = None,
) -> int:
    return resolve_runtime_credit_bucket_category(
        bucket_category=int(bucket.bucket_category or 0),
        source_type=int(bucket.source_type or 0),
        source_bid=str(bucket.source_bid or ""),
        metadata=bucket.metadata_json,
        load_order_type=load_order_type,
    )


def wallet_bucket_requires_active_subscription(
    bucket: CreditWalletBucket,
    *,
    load_order_type: OrderTypeLoader | None = None,
) -> bool:
    runtime_category = resolve_wallet_bucket_runtime_category(
        bucket,
        load_order_type=load_order_type,
    )
    if runtime_category == CREDIT_BUCKET_CATEGORY_TOPUP:
        return True
    if int(bucket.bucket_category or 0) == CREDIT_BUCKET_CATEGORY_FREE:
        return False
    if int(bucket.source_type or 0) in {
        CREDIT_SOURCE_TYPE_GIFT,
        CREDIT_SOURCE_TYPE_MANUAL,
    }:
        return False
    return runtime_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION


def build_wallet_bucket_runtime_sort_key(
    bucket: CreditWalletBucket,
    *,
    load_order_type: OrderTypeLoader | None = None,
) -> tuple[int, bool, datetime, datetime, int]:
    normalized_category = resolve_wallet_bucket_runtime_category(
        bucket,
        load_order_type=load_order_type,
    )
    return (
        resolve_credit_bucket_priority(normalized_category),
        bucket.effective_to is None,
        bucket.effective_to or datetime.max,
        bucket.created_at or datetime.min,
        int(bucket.id or 0),
    )


def load_billing_order_type_by_bid(bill_order_bid: str) -> int | None:
    order = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.bill_order_bid == str(bill_order_bid or "").strip(),
        )
        .order_by(BillingOrder.id.desc())
        .first()
    )
    if order is None:
        return None
    return int(order.order_type or 0)


def _resolve_refund_bucket_category(
    *,
    metadata: Any | None = None,
    load_order_type: OrderTypeLoader | None = None,
) -> int:
    return resolve_bucket_category_from_order_type(
        _resolve_origin_order_type(
            metadata=metadata,
            load_order_type=load_order_type,
        )
    )


def _resolve_gift_bucket_category(
    *,
    source_bid: str,
    metadata: Any | None = None,
    load_order_type: OrderTypeLoader | None = None,
) -> int:
    normalized_source_bid = _normalize_bid(source_bid)
    metadata_map = _normalize_json_object(metadata)

    if normalized_source_bid == BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE:
        return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    if _normalize_bid(metadata_map.get("program_code")) == (
        BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE
    ):
        return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION

    category_from_metadata = _resolve_bucket_category_hint(metadata_map)
    if category_from_metadata is not None:
        return category_from_metadata

    return resolve_bucket_category_from_order_type(
        _resolve_origin_order_type(
            metadata=metadata_map,
            load_order_type=load_order_type,
        )
    )


def _resolve_origin_order_type(
    *,
    metadata: Any | None = None,
    load_order_type: OrderTypeLoader | None = None,
) -> int | None:
    metadata_map = _normalize_json_object(metadata)
    bill_order_bid = _normalize_bid(metadata_map.get("bill_order_bid"))
    if bill_order_bid and load_order_type is not None:
        resolved_order_type = load_order_type(bill_order_bid)
        if resolved_order_type is not None:
            return int(resolved_order_type)

    raw_order_type = metadata_map.get("billing_order_type")
    if raw_order_type in (None, ""):
        raw_order_type = metadata_map.get("order_type")
    parsed_order_type = _parse_order_type(raw_order_type)
    if parsed_order_type is not None:
        return parsed_order_type

    raw_product_type = str(metadata_map.get("product_type") or "").strip().lower()
    if raw_product_type == "topup":
        return BILLING_ORDER_TYPE_TOPUP
    if raw_product_type in {"plan", "subscription"}:
        return BILLING_ORDER_TYPE_SUBSCRIPTION_START

    return None


def _resolve_bucket_category_hint(metadata: dict[str, Any]) -> int | None:
    for key in (
        "bucket_category",
        "credit_bucket_category",
        "original_bucket_category",
    ):
        parsed_category = _parse_bucket_category(metadata.get(key))
        if parsed_category is not None:
            return parsed_category
    return None


def _parse_order_type(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)

    normalized_value = str(value).strip()
    if not normalized_value:
        return None
    if normalized_value.isdigit():
        return int(normalized_value)
    return _ORDER_TYPE_BY_LABEL.get(normalized_value)


def _parse_bucket_category(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return normalize_runtime_credit_bucket_category(int(value))

    normalized_value = str(value).strip().lower()
    if not normalized_value:
        return None
    if normalized_value.isdigit():
        return normalize_runtime_credit_bucket_category(int(normalized_value))
    if normalized_value == "topup":
        return CREDIT_BUCKET_CATEGORY_TOPUP
    if normalized_value in {"subscription", "free"}:
        return CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    return None
