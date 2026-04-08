"""Creator entitlement snapshot resolution helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .consts import (
    BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC,
    BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD,
    BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS,
    BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    CREDIT_SOURCE_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from .models import BillingEntitlement, BillingProduct, BillingSubscription

_ACTIVE_SUBSCRIPTION_STATUSES = (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)


def resolve_creator_entitlement_state(
    creator_bid: str,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Resolve the effective entitlement snapshot for a creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    resolved_at = as_of or datetime.now()

    snapshot = _load_active_entitlement_snapshot(
        normalized_creator_bid,
        as_of=resolved_at,
    )
    if snapshot is not None:
        return _serialize_entitlement_row_state(snapshot)

    product_state = _resolve_subscription_product_entitlement_state(
        normalized_creator_bid,
        as_of=resolved_at,
    )
    if product_state is not None:
        return product_state

    return _build_default_entitlement_state(normalized_creator_bid)


def serialize_creator_entitlements(state: dict[str, Any]) -> dict[str, Any]:
    """Return the public creator entitlement projection."""

    return {
        "branding_enabled": bool(state.get("branding_enabled")),
        "custom_domain_enabled": bool(state.get("custom_domain_enabled")),
        "priority_class": str(state.get("priority_class") or "standard"),
        "max_concurrency": max(int(state.get("max_concurrency") or 1), 1),
        "analytics_tier": str(state.get("analytics_tier") or "basic"),
        "support_tier": str(state.get("support_tier") or "self_serve"),
    }


def _load_active_entitlement_snapshot(
    creator_bid: str,
    *,
    as_of: datetime,
) -> BillingEntitlement | None:
    return (
        BillingEntitlement.query.filter(
            BillingEntitlement.deleted == 0,
            BillingEntitlement.creator_bid == creator_bid,
            BillingEntitlement.effective_from <= as_of,
            (
                (BillingEntitlement.effective_to.is_(None))
                | (BillingEntitlement.effective_to > as_of)
            ),
        )
        .order_by(
            BillingEntitlement.effective_from.desc(),
            BillingEntitlement.created_at.desc(),
            BillingEntitlement.id.desc(),
        )
        .first()
    )


def _resolve_subscription_product_entitlement_state(
    creator_bid: str,
    *,
    as_of: datetime,
) -> dict[str, Any] | None:
    subscription = (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
            BillingSubscription.status.in_(_ACTIVE_SUBSCRIPTION_STATUSES),
        )
        .order_by(
            BillingSubscription.current_period_end_at.desc(),
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        )
        .first()
    )
    if subscription is None:
        return None

    product = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == subscription.product_bid,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )
    payload = getattr(product, "entitlement_payload", None)
    if not isinstance(payload, dict) or not payload:
        return None

    default_state = _build_default_entitlement_state(creator_bid)
    default_state.update(
        {
            "source_kind": "product_payload",
            "source_type": CREDIT_SOURCE_TYPE_LABELS.get(
                CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                "subscription",
            ),
            "source_bid": _normalize_bid(subscription.subscription_bid) or None,
            "product_bid": _normalize_bid(subscription.product_bid) or None,
            "effective_from": _coalesce_datetime(
                subscription.current_period_start_at,
                as_of,
            ),
            "effective_to": subscription.current_period_end_at,
            "feature_payload": _normalize_feature_payload(
                payload.get("feature_payload"),
            ),
        }
    )
    return _apply_entitlement_payload(default_state, payload)


def _build_default_entitlement_state(creator_bid: str) -> dict[str, Any]:
    return {
        "creator_bid": creator_bid,
        "source_kind": "default",
        "source_type": None,
        "source_bid": None,
        "product_bid": None,
        "effective_from": None,
        "effective_to": None,
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "priority_class": BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS.get(
            BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD,
            "standard",
        ),
        "max_concurrency": 1,
        "analytics_tier": BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS.get(
            BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC,
            "basic",
        ),
        "support_tier": BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS.get(
            BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE,
            "self_serve",
        ),
        "feature_payload": {},
    }


def _serialize_entitlement_row_state(row: BillingEntitlement) -> dict[str, Any]:
    return {
        "creator_bid": _normalize_bid(row.creator_bid),
        "source_kind": "snapshot",
        "source_type": CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        "source_bid": _normalize_bid(row.source_bid) or None,
        "product_bid": None,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "branding_enabled": bool(row.branding_enabled),
        "custom_domain_enabled": bool(row.custom_domain_enabled),
        "priority_class": BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS.get(
            row.priority_class,
            "standard",
        ),
        "max_concurrency": max(int(row.max_concurrency or 1), 1),
        "analytics_tier": BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS.get(
            row.analytics_tier,
            "basic",
        ),
        "support_tier": BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS.get(
            row.support_tier,
            "self_serve",
        ),
        "feature_payload": _normalize_feature_payload(row.feature_payload),
    }


def _apply_entitlement_payload(
    base_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    state = dict(base_state)
    state["branding_enabled"] = _to_bool(
        payload.get("branding_enabled"),
        default=state["branding_enabled"],
    )
    state["custom_domain_enabled"] = _to_bool(
        payload.get("custom_domain_enabled"),
        default=state["custom_domain_enabled"],
    )
    state["priority_class"] = _resolve_labeled_value(
        payload.get("priority_class"),
        labels=BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS,
        default=state["priority_class"],
    )
    state["max_concurrency"] = _to_positive_int(
        payload.get("max_concurrency"),
        default=state["max_concurrency"],
    )
    state["analytics_tier"] = _resolve_labeled_value(
        payload.get("analytics_tier"),
        labels=BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS,
        default=state["analytics_tier"],
    )
    state["support_tier"] = _resolve_labeled_value(
        payload.get("support_tier"),
        labels=BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS,
        default=state["support_tier"],
    )
    if "feature_payload" in payload:
        state["feature_payload"] = _normalize_feature_payload(
            payload.get("feature_payload"),
        )
    return state


def _resolve_labeled_value(
    value: Any,
    *,
    labels: dict[int, str],
    default: str,
) -> str:
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return labels.get(value, default)
    normalized = str(value).strip()
    if not normalized:
        return default
    if normalized in labels.values():
        return normalized
    try:
        return labels.get(int(normalized), default)
    except (TypeError, ValueError):
        return default


def _normalize_feature_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _coalesce_datetime(
    value: datetime | None,
    fallback: datetime,
) -> datetime:
    return value or fallback


def _normalize_bid(value: Any) -> str:
    return str(value or "").strip()


def _to_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _to_positive_int(value: Any, *, default: int = 1) -> int:
    if value is None or value == "":
        return max(int(default or 1), 1)
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return max(int(default or 1), 1)
