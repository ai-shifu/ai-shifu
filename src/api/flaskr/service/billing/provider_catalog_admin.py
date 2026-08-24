"""Admin read helpers for provider catalog inbox."""

from __future__ import annotations

from flaskr.service.common.models import raise_param_error
from flaskr.util.datetime import to_utc_iso

from .consts import (
    BILLING_PROVIDER_CATALOG_EVENT_STATUS_LABELS,
    BILLING_PROVIDER_CATALOG_HEALTH_LABELS,
)
from .models import BillingProviderCatalogEvent, BillingProviderCatalogSnapshot
from .primitives import normalize_bid, normalize_json_object
from .provider_price_mappings import PROVIDER_STRIPE


def build_admin_provider_catalog_inbox_page(
    *,
    object_type: str = "",
    provider_account_id: str = "",
    livemode: bool | None = None,
    health_status: str = "",
    limit: int = 100,
) -> dict[str, object]:
    """Return provider catalog snapshots and recent inbox events for admins."""
    resolved_limit = max(1, min(int(limit or 100), 200))
    snapshot_query = BillingProviderCatalogSnapshot.query.filter(
        BillingProviderCatalogSnapshot.deleted == 0,
        BillingProviderCatalogSnapshot.provider == PROVIDER_STRIPE,
    )
    normalized_object_type = _normalize_object_type_filter(object_type)
    if normalized_object_type:
        snapshot_query = snapshot_query.filter(
            BillingProviderCatalogSnapshot.object_type == normalized_object_type
        )
    normalized_account_id = normalize_bid(provider_account_id)
    if normalized_account_id:
        snapshot_query = snapshot_query.filter(
            BillingProviderCatalogSnapshot.provider_account_id == normalized_account_id
        )
    if livemode is not None:
        snapshot_query = snapshot_query.filter(
            BillingProviderCatalogSnapshot.livemode == int(bool(livemode))
        )
    resolved_health = _resolve_health_filter(health_status)
    if resolved_health is not None:
        snapshot_query = snapshot_query.filter(
            BillingProviderCatalogSnapshot.health_status == resolved_health
        )
    snapshots = (
        snapshot_query.order_by(
            BillingProviderCatalogSnapshot.updated_at.desc(),
            BillingProviderCatalogSnapshot.id.desc(),
        )
        .limit(resolved_limit)
        .all()
    )
    event_query = BillingProviderCatalogEvent.query.filter(
        BillingProviderCatalogEvent.deleted == 0,
        BillingProviderCatalogEvent.provider == PROVIDER_STRIPE,
    )
    if normalized_object_type:
        event_query = event_query.filter(
            BillingProviderCatalogEvent.object_type == normalized_object_type
        )
    if normalized_account_id:
        event_query = event_query.filter(
            BillingProviderCatalogEvent.provider_account_id == normalized_account_id
        )
    if livemode is not None:
        event_query = event_query.filter(
            BillingProviderCatalogEvent.livemode == int(bool(livemode))
        )
    events = (
        event_query.order_by(
            BillingProviderCatalogEvent.created_at.desc(),
            BillingProviderCatalogEvent.id.desc(),
        )
        .limit(resolved_limit)
        .all()
    )
    return {
        "snapshots": [serialize_provider_catalog_snapshot(row) for row in snapshots],
        "events": [serialize_provider_catalog_event(row) for row in events],
        "health_options": [
            {"value": label, "code": code}
            for code, label in BILLING_PROVIDER_CATALOG_HEALTH_LABELS.items()
        ],
    }


def serialize_provider_catalog_snapshot(
    row: BillingProviderCatalogSnapshot,
) -> dict[str, object]:
    """Serialize a provider catalog snapshot."""
    return {
        "catalog_snapshot_bid": row.catalog_snapshot_bid,
        "provider": row.provider,
        "provider_account_id": row.provider_account_id,
        "livemode": bool(row.livemode),
        "object_type": row.object_type,
        "object_id": row.object_id,
        "parent_object_id": row.parent_object_id,
        "active": bool(row.active),
        "provider_created_at": to_utc_iso(row.provider_created_at),
        "last_event_id": row.last_event_id,
        "last_event_type": row.last_event_type,
        "last_event_created_at": to_utc_iso(row.last_event_created_at),
        "last_seen_at": to_utc_iso(row.last_seen_at),
        "health_status": int(row.health_status or 0),
        "health_status_label": BILLING_PROVIDER_CATALOG_HEALTH_LABELS.get(
            int(row.health_status or 0), "unknown"
        ),
        "pending_issue_code": row.pending_issue_code,
        "linked_product_bid": row.linked_product_bid,
        "metadata": normalize_json_object(row.metadata_json or {}).to_metadata_json(),
    }


def serialize_provider_catalog_event(
    row: BillingProviderCatalogEvent,
) -> dict[str, object]:
    """Serialize a provider catalog inbox event."""
    return {
        "catalog_event_bid": row.catalog_event_bid,
        "provider": row.provider,
        "provider_event_id": row.provider_event_id,
        "event_type": row.event_type,
        "event_source": row.event_source,
        "provider_account_id": row.provider_account_id,
        "livemode": bool(row.livemode),
        "object_type": row.object_type,
        "object_id": row.object_id,
        "parent_object_id": row.parent_object_id,
        "event_created_at": to_utc_iso(row.event_created_at),
        "processed_at": to_utc_iso(row.processed_at),
        "processing_status": int(row.processing_status or 0),
        "processing_status_label": BILLING_PROVIDER_CATALOG_EVENT_STATUS_LABELS.get(
            int(row.processing_status or 0), "unknown"
        ),
        "processing_error": row.processing_error or "",
    }


def _normalize_object_type_filter(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if normalized not in {"product", "price"}:
        raise_param_error("object_type")
    return normalized


def _resolve_health_filter(value: str) -> int | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    for code, label in BILLING_PROVIDER_CATALOG_HEALTH_LABELS.items():
        if label == normalized:
            return code
    raise_param_error("health_status")
    return None
