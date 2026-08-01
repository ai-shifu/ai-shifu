"""Read-only credit grant and allocation interpretation views."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from flask import has_app_context

from flaskr.dao import db

from .bucket_categories import (
    OrderTypeLoader,
    resolve_runtime_credit_bucket_category,
)
from .consts import (
    BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_LABELS,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .models import CreditLedgerEntry, CreditWalletBucket
from .primitives import normalize_json_object, to_decimal

CreditAssetKind = Literal[
    "plan_credits",
    "pack_credits",
    "internal_legacy",
    "unknown",
]
CreditGrantState = Literal[
    "available",
    "reserved",
    "absorbed",
    "not_grant",
    "unknown",
]

_PRODUCT_ASSET_KINDS = {"plan_credits", "pack_credits"}
_INTERNAL_LEGACY_SOURCE_TYPES = {
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_MANUAL,
}
_SUBSCRIPTION_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
}
_MISSING_TEXT_VALUES = {"", "null", "none"}
_PLAN_CHECKOUT_TYPES = {
    "subscription",
    "subscription_preorder",
    "subscription_renewal",
    "referral_invitation_reward",
    "trial_bootstrap",
    "admin_manual_plan_grant",
}
_PACK_CHECKOUT_TYPES = {"topup"}
_REFERRAL_REWARD_PROGRAM = "referral_reward"
_REFERRAL_REWARD_SCENE = "referral"


@dataclass(frozen=True)
class CreditAllocationView:
    """Read-only interpretation of a wallet bucket as a credit allocation.

    Balance fields reflect persisted allocation state. They do not by themselves
    prove the credits are currently consumable at a specific request time.
    """

    wallet_bucket_bid: str
    wallet_bid: str
    creator_bid: str
    bucket_category: int
    bucket_category_label: str
    runtime_bucket_category: int
    runtime_bucket_category_label: str
    source_type: int
    source_type_label: str
    source_bid: str
    asset_kind: CreditAssetKind
    original_credits: Decimal
    available_credits: Decimal
    reserved_credits: Decimal
    consumed_credits: Decimal
    expired_credits: Decimal
    effective_from: datetime | None
    effective_to: datetime | None
    status: int


@dataclass(frozen=True)
class CreditGrantView:
    """Read-only interpretation of a ledger row as a credit grant."""

    ledger_bid: str
    wallet_bucket_bid: str
    wallet_bid: str
    creator_bid: str
    entry_type: int
    entry_type_label: str
    source_type: int
    source_type_label: str
    source_bid: str
    asset_kind: CreditAssetKind
    grant_state: CreditGrantState
    amount: Decimal
    balance_after: Decimal
    consumable_from: datetime | None
    expires_at: datetime | None
    allocation: CreditAllocationView | None = None


def build_credit_allocation_view(
    bucket: CreditWalletBucket,
    *,
    load_order_type: OrderTypeLoader | None = None,
) -> CreditAllocationView:
    """Interpret an existing bucket without mutating it."""

    bucket_category = int(bucket.bucket_category or 0)
    source_type = int(bucket.source_type or 0)
    source_bid = str(bucket.source_bid or "")
    safe_load_order_type = _wrap_order_type_loader(load_order_type)
    runtime_category = resolve_runtime_credit_bucket_category(
        bucket_category=bucket_category,
        source_type=source_type,
        source_bid=source_bid,
        metadata=bucket.metadata_json,
        load_order_type=safe_load_order_type,
    )
    return CreditAllocationView(
        wallet_bucket_bid=str(bucket.wallet_bucket_bid or ""),
        wallet_bid=str(bucket.wallet_bid or ""),
        creator_bid=str(bucket.creator_bid or ""),
        bucket_category=bucket_category,
        bucket_category_label=CREDIT_BUCKET_CATEGORY_LABELS.get(bucket_category, ""),
        runtime_bucket_category=runtime_category,
        runtime_bucket_category_label=CREDIT_BUCKET_CATEGORY_LABELS.get(
            runtime_category, ""
        ),
        source_type=source_type,
        source_type_label=CREDIT_SOURCE_TYPE_LABELS.get(source_type, ""),
        source_bid=source_bid,
        asset_kind=resolve_credit_asset_kind(
            bucket_category=bucket_category,
            source_type=source_type,
            source_bid=source_bid,
            metadata=bucket.metadata_json,
            load_order_type=safe_load_order_type,
        ),
        original_credits=to_decimal(bucket.original_credits),
        available_credits=to_decimal(bucket.available_credits),
        reserved_credits=to_decimal(bucket.reserved_credits),
        consumed_credits=to_decimal(bucket.consumed_credits),
        expired_credits=to_decimal(bucket.expired_credits),
        effective_from=bucket.effective_from,
        effective_to=bucket.effective_to,
        status=int(bucket.status or 0),
    )


def build_credit_grant_view(
    ledger: CreditLedgerEntry,
    *,
    bucket: CreditWalletBucket | None = None,
    load_order_type: OrderTypeLoader | None = None,
) -> CreditGrantView:
    """Interpret an existing ledger grant without mutating it."""

    safe_load_order_type = _wrap_order_type_loader(load_order_type)
    ledger_deleted = int(ledger.deleted or 0) != 0
    ledger_asset_kind = (
        "unknown"
        if ledger_deleted
        else resolve_credit_asset_kind(
            source_type=int(ledger.source_type or 0),
            source_bid=str(ledger.source_bid or ""),
            metadata=ledger.metadata_json,
            load_order_type=safe_load_order_type,
        )
    )
    allocation = (
        None
        if ledger_deleted
        else _build_matching_allocation_view(
            ledger,
            bucket,
            load_order_type=safe_load_order_type,
        )
    )
    asset_kind = _resolve_grant_asset_kind(
        ledger_asset_kind=ledger_asset_kind,
        allocation_asset_kind=allocation.asset_kind if allocation is not None else None,
    )
    return CreditGrantView(
        ledger_bid=str(ledger.ledger_bid or ""),
        wallet_bucket_bid=str(ledger.wallet_bucket_bid or ""),
        wallet_bid=str(ledger.wallet_bid or ""),
        creator_bid=str(ledger.creator_bid or ""),
        entry_type=int(ledger.entry_type or 0),
        entry_type_label=CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(
            int(ledger.entry_type or 0), ""
        ),
        source_type=int(ledger.source_type or 0),
        source_type_label=CREDIT_SOURCE_TYPE_LABELS.get(
            int(ledger.source_type or 0), ""
        ),
        source_bid=str(ledger.source_bid or ""),
        asset_kind=asset_kind,
        grant_state=resolve_credit_grant_state(ledger),
        amount=to_decimal(ledger.amount),
        balance_after=to_decimal(ledger.balance_after),
        consumable_from=ledger.consumable_from,
        expires_at=ledger.expires_at,
        allocation=allocation,
    )


def resolve_credit_asset_kind(
    *,
    bucket_category: int | None = None,
    source_type: int | None = None,
    source_bid: str = "",
    metadata: object | None = None,
    load_order_type: OrderTypeLoader | None = None,
) -> CreditAssetKind:
    """Map current storage records to canonical credit product semantics."""

    safe_load_order_type = _wrap_order_type_loader(load_order_type)
    evidence: list[CreditAssetKind] = []
    invalid_evidence = False
    current_source_type = int(source_type or 0)

    source_kind = _asset_kind_from_source_type(current_source_type)
    if source_kind is not None:
        evidence.append(source_kind)

    bucket_kind = _asset_kind_from_bucket_category_for_source(
        bucket_category,
        current_source_type,
    )
    if bucket_kind is not None:
        evidence.append(bucket_kind)

    metadata_kind, metadata_invalid = _asset_kind_from_metadata(
        metadata,
        source_type=current_source_type,
    )
    invalid_evidence = invalid_evidence or metadata_invalid
    if metadata_kind is not None:
        evidence.append(metadata_kind)

    order_kind, order_invalid = _asset_kind_from_order_metadata(
        metadata,
        load_order_type=safe_load_order_type,
    )
    invalid_evidence = invalid_evidence or order_invalid
    if order_kind is not None:
        evidence.append(order_kind)

    if current_source_type == CREDIT_SOURCE_TYPE_GIFT:
        legacy_free_kind = _asset_kind_from_legacy_free_gift(source_bid, metadata)
        if legacy_free_kind is not None:
            evidence.append(legacy_free_kind)
    if current_source_type == CREDIT_SOURCE_TYPE_MANUAL:
        referral_reward_kind = _asset_kind_from_manual_referral_reward(
            source_bid,
            metadata,
        )
        if referral_reward_kind is not None:
            evidence.append(referral_reward_kind)

    product_evidence = {kind for kind in evidence if kind in _PRODUCT_ASSET_KINDS}
    if len(product_evidence) > 1:
        return "unknown"
    if product_evidence:
        return next(iter(product_evidence))
    if invalid_evidence:
        return "unknown"
    if current_source_type in _INTERNAL_LEGACY_SOURCE_TYPES:
        return "internal_legacy"
    return "unknown"


def resolve_credit_grant_state(ledger: CreditLedgerEntry) -> CreditGrantState:
    if int(ledger.entry_type or 0) != CREDIT_LEDGER_ENTRY_TYPE_GRANT:
        return "not_grant"

    metadata = normalize_json_object(ledger.metadata_json)
    state = str(metadata.get("bucket_credit_state") or "").strip().lower()
    if state in {"available", "reserved", "absorbed"}:
        return state  # type: ignore[return-value]
    return "unknown"


def _build_matching_allocation_view(
    ledger: CreditLedgerEntry,
    bucket: CreditWalletBucket | None,
    *,
    load_order_type: OrderTypeLoader | None = None,
) -> CreditAllocationView | None:
    if bucket is None or int(bucket.deleted or 0) != 0:
        return None
    if str(ledger.wallet_bucket_bid or "") != str(bucket.wallet_bucket_bid or ""):
        return None
    if str(ledger.wallet_bid or "") != str(bucket.wallet_bid or ""):
        return None
    if str(ledger.creator_bid or "") != str(bucket.creator_bid or ""):
        return None
    return build_credit_allocation_view(bucket, load_order_type=load_order_type)


def _resolve_grant_asset_kind(
    *,
    ledger_asset_kind: CreditAssetKind,
    allocation_asset_kind: CreditAssetKind | None,
) -> CreditAssetKind:
    if allocation_asset_kind is None:
        return ledger_asset_kind
    if (
        ledger_asset_kind in _PRODUCT_ASSET_KINDS
        and allocation_asset_kind in _PRODUCT_ASSET_KINDS
        and ledger_asset_kind != allocation_asset_kind
    ):
        return "unknown"
    if ledger_asset_kind in _PRODUCT_ASSET_KINDS:
        return ledger_asset_kind
    if allocation_asset_kind in _PRODUCT_ASSET_KINDS:
        return allocation_asset_kind
    if (
        ledger_asset_kind == "internal_legacy"
        or allocation_asset_kind == "internal_legacy"
    ):
        return "internal_legacy"
    return "unknown"


def _asset_kind_from_source_type(source_type: int) -> CreditAssetKind | None:
    if source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION:
        return "plan_credits"
    if source_type == CREDIT_SOURCE_TYPE_TOPUP:
        return "pack_credits"
    return None


def _asset_kind_from_bucket_category_for_source(
    bucket_category: int | None,
    source_type: int,
) -> CreditAssetKind | None:
    try:
        category = int(bucket_category or 0)
    except (OverflowError, ValueError):
        return None
    if category == CREDIT_BUCKET_CATEGORY_TOPUP:
        return "pack_credits"
    if category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION:
        if source_type in _INTERNAL_LEGACY_SOURCE_TYPES:
            return None
        return "plan_credits"
    if category == CREDIT_BUCKET_CATEGORY_FREE:
        return "plan_credits" if source_type == CREDIT_SOURCE_TYPE_GIFT else None
    return None


def _asset_kind_from_metadata(
    metadata: object | None,
    *,
    source_type: int,
) -> tuple[CreditAssetKind | None, bool]:
    metadata_map = normalize_json_object(metadata)
    evidence: list[CreditAssetKind] = []
    invalid_evidence = False

    for key in (
        "bucket_category",
        "credit_bucket_category",
        "original_bucket_category",
    ):
        if key not in metadata_map:
            continue
        asset_kind, is_invalid = _asset_kind_from_metadata_value(metadata_map.get(key))
        invalid_evidence = invalid_evidence or is_invalid
        if asset_kind is not None:
            evidence.append(asset_kind)

    checkout_kind, checkout_invalid = _asset_kind_from_checkout_type(
        metadata_map.get("checkout_type")
    )
    invalid_evidence = invalid_evidence or checkout_invalid
    if checkout_kind is not None:
        evidence.append(checkout_kind)

    if source_type != CREDIT_SOURCE_TYPE_MANUAL:
        product_kind, product_invalid = _asset_kind_from_product_type(
            metadata_map.get("product_type")
        )
        invalid_evidence = invalid_evidence or product_invalid
        if product_kind is not None:
            evidence.append(product_kind)

    if metadata_map.get("referral_invitation_reward") is True:
        evidence.append("plan_credits")
    if _is_present_text(metadata_map.get("preorder_state")) or _is_present_text(
        metadata_map.get("preorder_effective_at")
    ):
        evidence.append("plan_credits")
    if _normalize_text(metadata_map.get("grant_reason")) in {
        "referral_invitation_reward",
        "subscription",
    }:
        evidence.append("plan_credits")
    if _normalize_text(metadata_map.get("grant_reason")) == "topup":
        evidence.append("pack_credits")

    product_evidence = {kind for kind in evidence if kind in _PRODUCT_ASSET_KINDS}
    if len(product_evidence) > 1:
        return None, True
    if product_evidence:
        return next(iter(product_evidence)), invalid_evidence
    return None, invalid_evidence


def _asset_kind_from_order_metadata(
    metadata: object | None,
    *,
    load_order_type: OrderTypeLoader | None = None,
) -> tuple[CreditAssetKind | None, bool]:
    metadata_map = normalize_json_object(metadata)
    bill_order_bid = _normalize_text(metadata_map.get("bill_order_bid"))
    if not bill_order_bid:
        return None, "bill_order_bid" in metadata_map
    if load_order_type is None:
        return None, True

    order_type = load_order_type(bill_order_bid)
    if order_type is None:
        return None, True
    return _asset_kind_from_order_type(order_type)


def _asset_kind_from_order_type(
    order_type: object,
) -> tuple[CreditAssetKind | None, bool]:
    if isinstance(order_type, bool) or order_type in (None, ""):
        return None, True
    try:
        normalized_order_type = int(order_type)
    except (TypeError, ValueError):
        return None, True
    if normalized_order_type == BILLING_ORDER_TYPE_TOPUP:
        return "pack_credits", False
    if normalized_order_type in _SUBSCRIPTION_ORDER_TYPES:
        return "plan_credits", False
    return None, True


def _asset_kind_from_legacy_free_gift(
    source_bid: str,
    metadata: object | None,
) -> CreditAssetKind | None:
    metadata_map = normalize_json_object(metadata)
    if _normalize_text(source_bid) == BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE:
        return "plan_credits"
    if (
        _normalize_text(metadata_map.get("program_code"))
        == BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE
    ):
        return "plan_credits"
    return None


def _asset_kind_from_manual_referral_reward(
    source_bid: str,
    metadata: object | None,
) -> CreditAssetKind | None:
    metadata_map = normalize_json_object(metadata)
    if _normalize_text(source_bid) != _REFERRAL_REWARD_PROGRAM:
        return None
    if _normalize_text(metadata_map.get("grant_type")) != _REFERRAL_REWARD_PROGRAM:
        return None
    if _normalize_text(metadata_map.get("reward_scene")) != _REFERRAL_REWARD_SCENE:
        return None
    if _normalize_text(metadata_map.get("reward_program")) != _REFERRAL_REWARD_PROGRAM:
        return None
    return "plan_credits"


def _asset_kind_from_metadata_value(
    value: object,
) -> tuple[CreditAssetKind | None, bool]:
    if not _is_present_text(value):
        return None, True
    if isinstance(value, bool):
        return None, True
    if isinstance(value, (int, float)):
        return _asset_kind_from_bucket_category(value)

    normalized = _normalize_text(value)
    if normalized.isdigit():
        return _asset_kind_from_bucket_category(int(normalized))
    if normalized in {"topup", "pack", "pack_credits", "credit_pack"}:
        return "pack_credits", False
    if normalized in {"subscription", "plan", "plan_credits", "free"}:
        return "plan_credits", False
    return None, True


def _asset_kind_from_bucket_category(
    bucket_category: int | float | None,
) -> tuple[CreditAssetKind | None, bool]:
    try:
        category = int(bucket_category or 0)
    except (OverflowError, ValueError):
        return None, True
    if category == CREDIT_BUCKET_CATEGORY_TOPUP:
        return "pack_credits", False
    if category in {CREDIT_BUCKET_CATEGORY_FREE, CREDIT_BUCKET_CATEGORY_SUBSCRIPTION}:
        return "plan_credits", False
    return None, True


def _asset_kind_from_checkout_type(
    value: object,
) -> tuple[CreditAssetKind | None, bool]:
    normalized = _normalize_text(value)
    if not normalized:
        return None, False
    if normalized in _PLAN_CHECKOUT_TYPES:
        return "plan_credits", False
    if normalized in _PACK_CHECKOUT_TYPES:
        return "pack_credits", False
    if normalized == "manual_grant":
        return None, False
    return None, True


def _asset_kind_from_product_type(value: object) -> tuple[CreditAssetKind | None, bool]:
    normalized = _normalize_text(value)
    if not normalized:
        return None, False
    if normalized in {"topup", "pack", "credit_pack"}:
        return "pack_credits", False
    if normalized in {"plan", "subscription"}:
        return "plan_credits", False
    return None, True


def _wrap_order_type_loader(
    load_order_type: OrderTypeLoader | None,
) -> OrderTypeLoader | None:
    if load_order_type is None:
        return None
    order_type_cache: dict[str, int | None] = {}

    def _load_without_autoflush(order_bid: str) -> int | None:
        if order_bid in order_type_cache:
            return order_type_cache[order_bid]
        if not has_app_context():
            order_type_cache[order_bid] = load_order_type(order_bid)
            return order_type_cache[order_bid]
        with db.session.no_autoflush:
            order_type_cache[order_bid] = load_order_type(order_bid)
            return order_type_cache[order_bid]

    return _load_without_autoflush


def _normalize_text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    normalized = str(value).strip().lower()
    return "" if normalized in _MISSING_TEXT_VALUES else normalized


def _is_present_text(value: object) -> bool:
    return bool(_normalize_text(value))


__all__ = [
    "CreditAllocationView",
    "CreditAssetKind",
    "CreditGrantState",
    "CreditGrantView",
    "build_credit_allocation_view",
    "build_credit_grant_view",
    "resolve_credit_asset_kind",
    "resolve_credit_grant_state",
]
