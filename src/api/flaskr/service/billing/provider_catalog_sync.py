"""Synchronize provider catalog snapshots and inbox events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_PROVIDER_CATALOG_EVENT_STATUS_FAILED,
    BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED,
    BILLING_PROVIDER_CATALOG_EVENT_STATUS_RECEIVED,
    BILLING_PROVIDER_CATALOG_EVENT_STATUS_SKIPPED,
)
from .models import (
    BillingProviderCatalogEvent,
    BillingProviderCatalogSnapshot,
)
from .primitives import normalize_bid
from .provider_catalog import (
    ProviderAccountSnapshot,
    ProviderPriceSnapshot,
    ProviderProductSnapshot,
    StripeCatalogReadAdapter,
    normalize_stripe_price_snapshot,
    normalize_stripe_product_snapshot,
)
from .provider_catalog_health import apply_price_health, apply_product_health
from .provider_price_mappings import PROVIDER_STRIPE

if TYPE_CHECKING:
    from flask import Flask


class _CatalogNotification(Protocol):
    """Minimal Stripe notification shape needed by catalog sync."""

    status: str
    provider_payload: dict[str, Any]


CATALOG_EVENT_TYPES = {
    "product.created",
    "product.updated",
    "product.deleted",
    "price.created",
    "price.updated",
    "price.deleted",
}
_OBJECT_TYPE_PRODUCT = "product"
_OBJECT_TYPE_PRICE = "price"
_SOURCE_WEBHOOK = "webhook"
_SOURCE_RECONCILE = "reconcile"
_SOURCE_MANUAL = "manual"


@dataclass(slots=True, frozen=True)
class ProviderCatalogSyncResult:
    """Capture the provider catalog sync response."""

    status: str
    status_code: int = 202
    event_type: str = ""
    object_type: str = ""
    object_id: str = ""
    processed: bool = False
    message: str = ""

    def to_response_dict(self) -> dict[str, object]:
        """Serialize the sync response."""
        payload: dict[str, object] = {
            "status": self.status,
            "event_type": self.event_type,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "processed": self.processed,
        }
        if self.message:
            payload["message"] = self.message
        return payload


def is_stripe_catalog_event(event_type: object) -> bool:
    """Return whether a Stripe event type belongs to catalog sync."""
    return str(event_type or "").strip() in CATALOG_EVENT_TYPES


def apply_stripe_catalog_notification(
    app: Flask,
    notification: _CatalogNotification,
) -> ProviderCatalogSyncResult:
    """Persist a Stripe catalog webhook event and update local snapshots."""
    event = notification.provider_payload or {}
    event_type = str(notification.status or event.get("type") or "").strip()
    if not is_stripe_catalog_event(event_type):
        return ProviderCatalogSyncResult(status="ignored", event_type=event_type)

    account = _safe_read_account(app)
    with app.app_context(), unit_of_work():
        return _process_event_payload(
            app,
            event,
            event_type=event_type,
            source=_SOURCE_WEBHOOK,
            account=account,
        )


def reconcile_stripe_catalog(
    app: Flask,
    *,
    source: str = _SOURCE_RECONCILE,
) -> dict[str, object]:
    """Fetch Stripe catalog objects and reconcile them into local snapshots."""
    reader = StripeCatalogReadAdapter()
    account = reader.retrieve_account_snapshot(app)
    products = reader.list_product_snapshots(app)
    prices = reader.list_price_snapshots(app)
    processed = 0
    with app.app_context(), unit_of_work():
        for product in products:
            event_id = _reconcile_event_id(product.product_id)
            event_created_at = now_utc()
            _record_reconcile_event(
                app,
                account=account,
                event_id=event_id,
                event_type="product.reconciled",
                object_type=_OBJECT_TYPE_PRODUCT,
                object_id=product.product_id,
                parent_object_id="",
                event_created_at=event_created_at,
                source=source,
                raw_payload=product.raw,
            )
            _upsert_product_snapshot(
                app,
                account=account,
                product=product,
                event_type="product.reconciled",
                event_id=event_id,
                event_created_at=event_created_at,
                source=source,
                raw_event={"type": "product.reconciled", "object": product.raw},
            )
            processed += 1
        for price in prices:
            event_id = _reconcile_event_id(price.price_id)
            event_created_at = now_utc()
            _record_reconcile_event(
                app,
                account=account,
                event_id=event_id,
                event_type="price.reconciled",
                object_type=_OBJECT_TYPE_PRICE,
                object_id=price.price_id,
                parent_object_id=price.product_id,
                event_created_at=event_created_at,
                source=source,
                raw_payload=price.raw,
            )
            _upsert_price_snapshot(
                app,
                account=account,
                price=price,
                event_type="price.reconciled",
                event_id=event_id,
                event_created_at=event_created_at,
                source=source,
                raw_event={"type": "price.reconciled", "object": price.raw},
            )
            processed += 1
    return {
        "provider": PROVIDER_STRIPE,
        "provider_account_id": account.account_id,
        "livemode": bool(account.livemode),
        "products": len(products),
        "prices": len(prices),
        "processed": processed,
    }


def run_admin_provider_catalog_reconcile(app: Flask) -> dict[str, object]:
    """Run a manual Stripe catalog reconcile for admins."""
    return reconcile_stripe_catalog(app, source=_SOURCE_MANUAL)


def _process_event_payload(
    app: Flask,
    event: dict[str, Any],
    *,
    event_type: str,
    source: str,
    account: ProviderAccountSnapshot,
) -> ProviderCatalogSyncResult:
    data_object = event.get("data", {}).get("object", {}) or {}
    if not isinstance(data_object, dict):
        return ProviderCatalogSyncResult(status="ignored", event_type=event_type)
    object_type = _event_object_type(event_type, data_object)
    object_id = normalize_bid(data_object.get("id"))
    event_id = normalize_bid(event.get("id")) or f"{source}:{event_type}:{object_id}"
    event_created_at = _coerce_epoch_datetime(event.get("created"))
    existing_event = _load_event(event_id)
    if existing_event is not None:
        return ProviderCatalogSyncResult(
            status="duplicate",
            event_type=event_type,
            object_type=existing_event.object_type,
            object_id=existing_event.object_id,
            processed=False,
        )

    row = BillingProviderCatalogEvent(
        catalog_event_bid=generate_id(app),
        provider=PROVIDER_STRIPE,
        provider_event_id=event_id,
        event_type=event_type,
        event_source=source,
        provider_account_id=account.account_id,
        livemode=int(bool(account.livemode)),
        object_type=object_type,
        object_id=object_id,
        parent_object_id=_parent_object_id(data_object, object_type),
        event_created_at=event_created_at,
        processing_status=BILLING_PROVIDER_CATALOG_EVENT_STATUS_RECEIVED,
        raw_payload=event,
        deleted=0,
    )
    db.session.add(row)
    try:
        if object_type == _OBJECT_TYPE_PRODUCT:
            snapshot = normalize_stripe_product_snapshot(data_object)
            applied = _upsert_product_snapshot(
                app,
                account=account,
                product=snapshot,
                event_type=event_type,
                event_id=event_id,
                event_created_at=event_created_at,
                source=source,
                raw_event=event,
            )
        elif object_type == _OBJECT_TYPE_PRICE:
            snapshot = normalize_stripe_price_snapshot(data_object)
            applied = _upsert_price_snapshot(
                app,
                account=account,
                price=snapshot,
                event_type=event_type,
                event_id=event_id,
                event_created_at=event_created_at,
                source=source,
                raw_event=event,
            )
        else:
            applied = False
        row.processing_status = (
            BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED
            if applied
            else BILLING_PROVIDER_CATALOG_EVENT_STATUS_SKIPPED
        )
        row.processed_at = now_utc()
    except Exception as exc:
        row.processing_status = BILLING_PROVIDER_CATALOG_EVENT_STATUS_FAILED
        row.processed_at = now_utc()
        row.processing_error = _safe_error(exc)
        raise
    return ProviderCatalogSyncResult(
        status="acknowledged"
        if row.processing_status == BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED
        else "skipped",
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        processed=row.processing_status
        == BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED,
    )


def _upsert_product_snapshot(
    app: Flask,
    *,
    account: ProviderAccountSnapshot,
    product: ProviderProductSnapshot,
    event_type: str,
    event_id: str,
    event_created_at: datetime | None,
    source: str,
    raw_event: dict[str, Any],
) -> bool:
    del source, raw_event
    existing = _load_snapshot(
        account=account,
        object_type=_OBJECT_TYPE_PRODUCT,
        object_id=product.product_id,
    )
    if _is_stale_snapshot(existing, event_created_at):
        return False
    row = existing or BillingProviderCatalogSnapshot(
        catalog_snapshot_bid=generate_id(app),
        provider=PROVIDER_STRIPE,
        provider_account_id=account.account_id,
        livemode=int(bool(account.livemode)),
        object_type=_OBJECT_TYPE_PRODUCT,
        object_id=product.product_id,
        deleted=0,
    )
    if existing is None:
        db.session.add(row)
    row.parent_object_id = ""
    row.active = int(bool(product.active))
    row.provider_created_at = _coerce_epoch_datetime(product.raw.get("created"))
    row.last_event_id = event_id
    row.last_event_type = event_type
    row.last_event_created_at = event_created_at
    row.last_seen_at = now_utc()
    row.metadata_json = dict(product.metadata or {})
    row.raw_payload = product.raw
    apply_product_health(row)
    return True


def _upsert_price_snapshot(
    app: Flask,
    *,
    account: ProviderAccountSnapshot,
    price: ProviderPriceSnapshot,
    event_type: str,
    event_id: str,
    event_created_at: datetime | None,
    source: str,
    raw_event: dict[str, Any],
) -> bool:
    del source, raw_event
    existing = _load_snapshot(
        account=account,
        object_type=_OBJECT_TYPE_PRICE,
        object_id=price.price_id,
    )
    if _is_stale_snapshot(existing, event_created_at):
        return False
    row = existing or BillingProviderCatalogSnapshot(
        catalog_snapshot_bid=generate_id(app),
        provider=PROVIDER_STRIPE,
        provider_account_id=account.account_id,
        livemode=int(bool(account.livemode)),
        object_type=_OBJECT_TYPE_PRICE,
        object_id=price.price_id,
        deleted=0,
    )
    if existing is None:
        db.session.add(row)
    row.parent_object_id = price.product_id
    row.active = int(bool(price.active))
    row.provider_created_at = _coerce_epoch_datetime(price.raw.get("created"))
    row.last_event_id = event_id
    row.last_event_type = event_type
    row.last_event_created_at = event_created_at
    row.last_seen_at = now_utc()
    row.metadata_json = dict(price.metadata or {})
    row.raw_payload = price.raw
    apply_price_health(row, price)
    return True


def _load_snapshot(
    *, account: ProviderAccountSnapshot, object_type: str, object_id: str
) -> BillingProviderCatalogSnapshot | None:
    return BillingProviderCatalogSnapshot.query.filter(
        BillingProviderCatalogSnapshot.deleted == 0,
        BillingProviderCatalogSnapshot.provider == PROVIDER_STRIPE,
        BillingProviderCatalogSnapshot.provider_account_id == account.account_id,
        BillingProviderCatalogSnapshot.livemode == int(bool(account.livemode)),
        BillingProviderCatalogSnapshot.object_type == object_type,
        BillingProviderCatalogSnapshot.object_id == object_id,
    ).one_or_none()


def _load_event(provider_event_id: str) -> BillingProviderCatalogEvent | None:
    return BillingProviderCatalogEvent.query.filter(
        BillingProviderCatalogEvent.deleted == 0,
        BillingProviderCatalogEvent.provider == PROVIDER_STRIPE,
        BillingProviderCatalogEvent.provider_event_id == provider_event_id,
    ).one_or_none()


def _record_reconcile_event(
    app: Flask,
    *,
    account: ProviderAccountSnapshot,
    event_id: str,
    event_type: str,
    object_type: str,
    object_id: str,
    parent_object_id: str,
    event_created_at: datetime,
    source: str,
    raw_payload: dict[str, Any],
) -> None:
    event = BillingProviderCatalogEvent(
        catalog_event_bid=generate_id(app),
        provider=PROVIDER_STRIPE,
        provider_event_id=event_id,
        event_type=event_type,
        event_source=source,
        provider_account_id=account.account_id,
        livemode=int(bool(account.livemode)),
        object_type=object_type,
        object_id=object_id,
        parent_object_id=parent_object_id,
        event_created_at=event_created_at,
        processed_at=now_utc(),
        processing_status=BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED,
        raw_payload=raw_payload,
        deleted=0,
    )
    db.session.add(event)


def _is_stale_snapshot(
    row: BillingProviderCatalogSnapshot | None,
    event_created_at: datetime | None,
) -> bool:
    if row is None or event_created_at is None or row.last_event_created_at is None:
        return False
    return event_created_at < row.last_event_created_at


def _safe_read_account(app: Flask) -> ProviderAccountSnapshot:
    try:
        return StripeCatalogReadAdapter().retrieve_account_snapshot(app)
    except Exception:
        return ProviderAccountSnapshot(
            provider=PROVIDER_STRIPE,
            account_id="",
            livemode=False,
            raw={},
        )


def _event_object_type(event_type: str, data_object: dict[str, Any]) -> str:
    object_name = str(data_object.get("object") or "").strip()
    if object_name in {_OBJECT_TYPE_PRODUCT, _OBJECT_TYPE_PRICE}:
        return object_name
    if event_type.startswith("product."):
        return _OBJECT_TYPE_PRODUCT
    if event_type.startswith("price."):
        return _OBJECT_TYPE_PRICE
    return ""


def _parent_object_id(data_object: dict[str, Any], object_type: str) -> str:
    if object_type != _OBJECT_TYPE_PRICE:
        return ""
    product = data_object.get("product")
    if isinstance(product, dict):
        return normalize_bid(product.get("id"))
    return normalize_bid(product)


def _coerce_epoch_datetime(value: object) -> datetime | None:
    try:
        epoch = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(epoch, UTC).replace(tzinfo=None)


def _reconcile_event_id(object_id: str) -> str:
    return f"reconcile:{object_id}:{now_utc().strftime('%Y%m%d%H%M%S%f')}"


def _safe_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: provider catalog sync failed"
