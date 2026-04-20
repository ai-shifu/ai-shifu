"""Creator entitlement snapshot resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .consts import (
    BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC,
    BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD,
    BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS,
    BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE,
    CREDIT_SOURCE_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from .dtos import BillingEntitlementsDTO
from .models import BillingEntitlement, BillingProduct
from .queries import (
    load_primary_active_subscription as _load_primary_active_subscription,
)
from .primitives import normalize_bid as _normalize_bid
from .value_objects import JsonObjectMap


@dataclass(slots=True, frozen=True)
class CreatorEntitlementState:
    creator_bid: str
    source_kind: str
    source_type: str | None
    source_bid: str | None
    product_bid: str | None
    effective_from: datetime | None
    effective_to: datetime | None
    branding_enabled: bool
    custom_domain_enabled: bool
    priority_class: str
    analytics_tier: str
    support_tier: str
    feature_payload: JsonObjectMap = field(default_factory=JsonObjectMap)

    def to_public_payload(self) -> dict[str, Any]:
        return {
            "branding_enabled": self.branding_enabled,
            "custom_domain_enabled": self.custom_domain_enabled,
            "priority_class": self.priority_class,
            "analytics_tier": self.analytics_tier,
            "support_tier": self.support_tier,
        }

    def __getitem__(self, key: str) -> Any:
        if key == "feature_payload":
            return self.feature_payload.to_metadata_json()
        return getattr(self, key)


def resolve_creator_entitlement_state(
    creator_bid: str,
    *,
    as_of: datetime | None = None,
) -> CreatorEntitlementState:
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


def serialize_creator_entitlements(
    state: CreatorEntitlementState,
) -> BillingEntitlementsDTO:
    """Return the public creator entitlement projection."""

    return BillingEntitlementsDTO(**state.to_public_payload())


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
) -> CreatorEntitlementState | None:
    subscription = _load_primary_active_subscription(creator_bid, as_of=as_of)
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
    seed_state = CreatorEntitlementState(
        creator_bid=default_state.creator_bid,
        source_kind="product_payload",
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(
            CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            "subscription",
        ),
        source_bid=_normalize_bid(subscription.subscription_bid) or None,
        product_bid=_normalize_bid(subscription.product_bid) or None,
        effective_from=_coalesce_datetime(
            subscription.current_period_start_at,
            as_of,
        ),
        effective_to=subscription.current_period_end_at,
        branding_enabled=default_state.branding_enabled,
        custom_domain_enabled=default_state.custom_domain_enabled,
        priority_class=default_state.priority_class,
        analytics_tier=default_state.analytics_tier,
        support_tier=default_state.support_tier,
        feature_payload=_normalize_feature_payload(
            payload.get("feature_payload"),
        ),
    )
    return _apply_entitlement_payload(seed_state, payload)


def _build_default_entitlement_state(creator_bid: str) -> CreatorEntitlementState:
    return CreatorEntitlementState(
        creator_bid=creator_bid,
        source_kind="default",
        source_type=None,
        source_bid=None,
        product_bid=None,
        effective_from=None,
        effective_to=None,
        branding_enabled=False,
        custom_domain_enabled=False,
        priority_class=BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS.get(
            BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD,
            "standard",
        ),
        analytics_tier=BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS.get(
            BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC,
            "basic",
        ),
        support_tier=BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS.get(
            BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE,
            "self_serve",
        ),
        feature_payload=JsonObjectMap(),
    )


def _serialize_entitlement_row_state(
    row: BillingEntitlement,
) -> CreatorEntitlementState:
    return CreatorEntitlementState(
        creator_bid=_normalize_bid(row.creator_bid),
        source_kind="snapshot",
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        source_bid=_normalize_bid(row.source_bid) or None,
        product_bid=None,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        branding_enabled=bool(row.branding_enabled),
        custom_domain_enabled=bool(row.custom_domain_enabled),
        priority_class=BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS.get(
            row.priority_class,
            "standard",
        ),
        analytics_tier=BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS.get(
            row.analytics_tier,
            "basic",
        ),
        support_tier=BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS.get(
            row.support_tier,
            "self_serve",
        ),
        feature_payload=_normalize_feature_payload(row.feature_payload),
    )


def _apply_entitlement_payload(
    base_state: CreatorEntitlementState,
    payload: dict[str, Any],
) -> CreatorEntitlementState:
    branding_enabled = _to_bool(
        payload.get("branding_enabled"),
        default=base_state.branding_enabled,
    )
    custom_domain_enabled = _to_bool(
        payload.get("custom_domain_enabled"),
        default=base_state.custom_domain_enabled,
    )
    priority_class = _resolve_labeled_value(
        payload.get("priority_class"),
        labels=BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS,
        default=base_state.priority_class,
    )
    analytics_tier = _resolve_labeled_value(
        payload.get("analytics_tier"),
        labels=BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS,
        default=base_state.analytics_tier,
    )
    support_tier = _resolve_labeled_value(
        payload.get("support_tier"),
        labels=BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS,
        default=base_state.support_tier,
    )
    feature_payload = base_state.feature_payload
    if "feature_payload" in payload:
        feature_payload = _normalize_feature_payload(
            payload.get("feature_payload"),
        )
    return CreatorEntitlementState(
        creator_bid=base_state.creator_bid,
        source_kind=base_state.source_kind,
        source_type=base_state.source_type,
        source_bid=base_state.source_bid,
        product_bid=base_state.product_bid,
        effective_from=base_state.effective_from,
        effective_to=base_state.effective_to,
        branding_enabled=branding_enabled,
        custom_domain_enabled=custom_domain_enabled,
        priority_class=priority_class,
        analytics_tier=analytics_tier,
        support_tier=support_tier,
        feature_payload=feature_payload,
    )


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


def _normalize_feature_payload(value: Any) -> JsonObjectMap:
    if not isinstance(value, dict):
        return JsonObjectMap()
    return JsonObjectMap(values={str(key): item for key, item in value.items()})


def _coalesce_datetime(
    value: datetime | None,
    fallback: datetime,
) -> datetime:
    return value or fallback


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
