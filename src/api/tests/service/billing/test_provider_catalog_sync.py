"""Validate provider catalog webhook inbox and reconcile behavior."""

from __future__ import annotations

from decimal import Decimal

import pytest
from flask import has_app_context
from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_INTERVAL_MONTH,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PROVIDER_CATALOG_EVENT_STATUS_FAILED,
    BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED,
    BILLING_PROVIDER_CATALOG_EVENT_STATUS_SKIPPED,
    BILLING_PROVIDER_CATALOG_HEALTH_INACTIVE,
    BILLING_PROVIDER_CATALOG_HEALTH_UNLINKED,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
)
from flaskr.service.billing.models import (
    BillingProduct,
    BillingProductProviderPrice,
    BillingProviderCatalogEvent,
    BillingProviderCatalogSnapshot,
)
from flaskr.service.billing.provider_catalog import (
    ProviderAccountSnapshot,
    ProviderCatalogReadError,
    ProviderPriceSnapshot,
    ProviderProductSnapshot,
)
from flaskr.service.billing.provider_catalog_admin import (
    build_admin_provider_catalog_inbox_page,
)
from flaskr.service.billing.provider_catalog_sync import (
    apply_stripe_catalog_notification,
    reconcile_stripe_catalog,
)
from flaskr.service.billing.provider_price_mappings import upsert_provider_price_mapping
from flaskr.service.order.payment_providers import PaymentNotificationResult
from sqlalchemy.exc import IntegrityError


def _product(
    product_bid: str = "bill-product-catalog-growth",
    *,
    product_code: str = "creator-global-growth-monthly",
) -> BillingProduct:
    return BillingProduct(
        product_bid=product_bid,
        product_code=product_code,
        product_type=BILLING_PRODUCT_TYPE_PLAN,
        billing_mode=BILLING_MODE_RECURRING,
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
        display_name_i18n_key="module.billing.catalog.growth.title",
        description_i18n_key="module.billing.catalog.growth.description",
        currency="USD",
        price_amount=5900,
        credit_amount=Decimal(1000),
        status=BILLING_PRODUCT_STATUS_ACTIVE,
        sort_order=20,
        metadata_json={"plan_tier": "growth"},
        deleted=0,
    )


def _catalog_notification(
    *,
    event_id: str,
    event_type: str,
    created: int,
    data_object: dict[str, object],
) -> PaymentNotificationResult:
    return PaymentNotificationResult(
        order_bid="",
        status=event_type,
        provider_payload={
            "id": event_id,
            "type": event_type,
            "created": created,
            "data": {"object": data_object},
        },
        charge_id=None,
    )


def _patch_account(monkeypatch: object, *, livemode: bool | None = False) -> None:
    import flaskr.service.billing.provider_catalog_sync as sync_module

    def _retrieve_account_snapshot(
        self: object, app: object
    ) -> ProviderAccountSnapshot:
        del self, app
        return ProviderAccountSnapshot(
            provider="stripe",
            account_id="acct_test",
            livemode=livemode,
        )

    monkeypatch.setattr(
        sync_module.StripeCatalogReadAdapter,
        "retrieve_account_snapshot",
        _retrieve_account_snapshot,
    )


def test_stripe_product_webhook_stores_unlinked_snapshot_with_metadata_suggestion(
    app: object,
    monkeypatch: object,
) -> None:
    _patch_account(monkeypatch)
    with app.app_context():
        db.session.add(_product())
        db.session.commit()

        result = apply_stripe_catalog_notification(
            app,
            _catalog_notification(
                event_id="evt_product_created",
                event_type="product.created",
                created=1_780_000_000,
                data_object={
                    "id": "prod_growth",
                    "object": "product",
                    "active": True,
                    "livemode": False,
                    "created": 1_780_000_000,
                    "metadata": {"product_code": "creator-global-growth-monthly"},
                },
            ),
        )

        snapshot = BillingProviderCatalogSnapshot.query.filter_by(
            object_type="product", object_id="prod_growth"
        ).one()
        event = BillingProviderCatalogEvent.query.filter_by(
            provider_event_id="evt_product_created"
        ).one()
        assert result.processed is True
        assert snapshot.health_status == BILLING_PROVIDER_CATALOG_HEALTH_UNLINKED
        assert snapshot.pending_issue_code == "provider_product_unlinked"
        assert snapshot.linked_product_bid == "bill-product-catalog-growth"
        assert (
            event.processing_status == BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED
        )


def test_stripe_catalog_webhook_is_idempotent(app: object, monkeypatch: object) -> None:
    _patch_account(monkeypatch)
    notification = _catalog_notification(
        event_id="evt_price_duplicate",
        event_type="price.created",
        created=1_780_000_001,
        data_object={
            "id": "price_growth",
            "object": "price",
            "product": "prod_growth",
            "active": True,
            "livemode": False,
            "currency": "usd",
            "unit_amount": 5900,
            "type": "recurring",
            "recurring": {"interval": "month", "interval_count": 1},
        },
    )
    with app.app_context():
        first = apply_stripe_catalog_notification(app, notification)
        second = apply_stripe_catalog_notification(app, notification)

        assert first.processed is True
        assert second.status == "duplicate"
        assert (
            BillingProviderCatalogEvent.query.filter_by(
                provider_event_id="evt_price_duplicate"
            ).count()
            == 1
        )
        assert (
            BillingProviderCatalogSnapshot.query.filter_by(
                object_type="price", object_id="price_growth"
            ).count()
            == 1
        )


def test_stale_stripe_catalog_event_does_not_overwrite_newer_snapshot(
    app: object,
    monkeypatch: object,
) -> None:
    _patch_account(monkeypatch)
    with app.app_context():
        newer = _catalog_notification(
            event_id="evt_product_newer",
            event_type="product.updated",
            created=1_780_000_100,
            data_object={
                "id": "prod_stale_guard",
                "object": "product",
                "active": True,
                "livemode": False,
                "created": 1_780_000_000,
                "metadata": {"version": "newer"},
            },
        )
        older = _catalog_notification(
            event_id="evt_product_older",
            event_type="product.updated",
            created=1_780_000_050,
            data_object={
                "id": "prod_stale_guard",
                "object": "product",
                "active": False,
                "livemode": False,
                "created": 1_780_000_000,
                "metadata": {"version": "older"},
            },
        )

        apply_stripe_catalog_notification(app, newer)
        stale_result = apply_stripe_catalog_notification(app, older)

        snapshot = BillingProviderCatalogSnapshot.query.filter_by(
            object_type="product", object_id="prod_stale_guard"
        ).one()
        stale_event = BillingProviderCatalogEvent.query.filter_by(
            provider_event_id="evt_product_older"
        ).one()
        assert stale_result.processed is False
        assert snapshot.active == 1
        assert snapshot.metadata_json == {"version": "newer"}
        assert (
            stale_event.processing_status
            == BILLING_PROVIDER_CATALOG_EVENT_STATUS_SKIPPED
        )


def test_inactive_price_marks_active_mapping_invalid(
    app: object,
    monkeypatch: object,
) -> None:
    _patch_account(monkeypatch)
    with app.app_context():
        db.session.add(
            _product(
                "bill-product-catalog-growth-inactive",
                product_code="creator-global-growth-inactive",
            )
        )
        db.session.commit()
        mapping, _created = upsert_provider_price_mapping(
            product_bid="bill-product-catalog-growth-inactive",
            provider_account_id="acct_test",
            provider_product_id="prod_growth",
            provider_price_id="price_growth_inactive",
            livemode=False,
        )
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        db.session.commit()

        result = apply_stripe_catalog_notification(
            app,
            _catalog_notification(
                event_id="evt_price_inactive",
                event_type="price.updated",
                created=1_780_000_200,
                data_object={
                    "id": "price_growth_inactive",
                    "object": "price",
                    "product": "prod_growth",
                    "active": False,
                    "livemode": False,
                    "currency": "usd",
                    "unit_amount": 5900,
                    "type": "recurring",
                    "recurring": {
                        "interval": "month",
                        "interval_count": 1,
                        "usage_type": "licensed",
                    },
                },
            ),
        )

        snapshot = BillingProviderCatalogSnapshot.query.filter_by(
            object_type="price", object_id="price_growth_inactive"
        ).one()
        refreshed_mapping = BillingProductProviderPrice.query.filter_by(
            provider_price_bid=mapping.provider_price_bid
        ).one()
        assert result.processed is True
        assert snapshot.health_status == BILLING_PROVIDER_CATALOG_HEALTH_INACTIVE
        assert snapshot.pending_issue_code == "provider_price_inactive"
        assert refreshed_mapping.status == BILLING_PROVIDER_PRICE_STATUS_INVALID
        assert "provider_price_inactive" in refreshed_mapping.validation_error


def test_catalog_webhook_uses_object_livemode_when_account_omits_mode(
    app: object,
    monkeypatch: object,
) -> None:
    _patch_account(monkeypatch, livemode=None)
    with app.app_context():
        result = apply_stripe_catalog_notification(
            app,
            _catalog_notification(
                event_id="evt_product_live_scope",
                event_type="product.updated",
                created=1_780_000_300,
                data_object={
                    "id": "prod_live_scope",
                    "object": "product",
                    "active": True,
                    "livemode": True,
                    "created": 1_780_000_300,
                    "metadata": {},
                },
            ),
        )

        snapshot = BillingProviderCatalogSnapshot.query.filter_by(
            object_type="product", object_id="prod_live_scope"
        ).one()
        event = BillingProviderCatalogEvent.query.filter_by(
            provider_event_id="evt_product_live_scope"
        ).one()
        assert result.processed is True
        assert snapshot.provider_account_id == "acct_test"
        assert snapshot.livemode == 1
        assert event.livemode == 1


def test_catalog_webhook_account_read_failure_does_not_persist_empty_scope(
    app: object,
    monkeypatch: object,
) -> None:
    import flaskr.service.billing.provider_catalog_sync as sync_module

    def _raise_account_error(self: object, app: object) -> ProviderAccountSnapshot:
        del self, app
        code = "stripe_catalog_retrieve_failed"
        message = "failed"
        raise ProviderCatalogReadError(code, message)

    monkeypatch.setattr(
        sync_module.StripeCatalogReadAdapter,
        "retrieve_account_snapshot",
        _raise_account_error,
    )
    with app.app_context():
        with pytest.raises(ProviderCatalogReadError):
            apply_stripe_catalog_notification(
                app,
                _catalog_notification(
                    event_id="evt_account_failure",
                    event_type="product.updated",
                    created=1_780_000_301,
                    data_object={
                        "id": "prod_account_failure",
                        "object": "product",
                        "active": True,
                        "livemode": False,
                    },
                ),
            )

        assert (
            BillingProviderCatalogEvent.query.filter_by(
                provider_event_id="evt_account_failure"
            ).count()
            == 0
        )
        assert (
            BillingProviderCatalogSnapshot.query.filter_by(
                object_id="prod_account_failure"
            ).count()
            == 0
        )


def test_same_second_catalog_event_does_not_overwrite_existing_snapshot(
    app: object,
    monkeypatch: object,
) -> None:
    _patch_account(monkeypatch)
    with app.app_context():
        first = _catalog_notification(
            event_id="evt_product_same_second_first",
            event_type="product.updated",
            created=1_780_000_302,
            data_object={
                "id": "prod_same_second",
                "object": "product",
                "active": True,
                "livemode": False,
                "created": 1_780_000_302,
                "metadata": {"version": "first"},
            },
        )
        second = _catalog_notification(
            event_id="evt_product_same_second_second",
            event_type="product.updated",
            created=1_780_000_302,
            data_object={
                "id": "prod_same_second",
                "object": "product",
                "active": False,
                "livemode": False,
                "created": 1_780_000_302,
                "metadata": {"version": "second"},
            },
        )

        apply_stripe_catalog_notification(app, first)
        skipped = apply_stripe_catalog_notification(app, second)

        snapshot = BillingProviderCatalogSnapshot.query.filter_by(
            object_type="product", object_id="prod_same_second"
        ).one()
        event = BillingProviderCatalogEvent.query.filter_by(
            provider_event_id="evt_product_same_second_second"
        ).one()
        assert skipped.processed is False
        assert snapshot.active == 1
        assert snapshot.metadata_json == {"version": "first"}
        assert event.processing_status == BILLING_PROVIDER_CATALOG_EVENT_STATUS_SKIPPED


def test_catalog_webhook_duplicate_insert_race_returns_duplicate(
    app: object,
    monkeypatch: object,
) -> None:
    _patch_account(monkeypatch)
    original_flush = db.session.flush
    calls = {"count": 0}

    def _raise_duplicate_once(*args: object, **kwargs: object) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            statement = "insert"
            message = "duplicate"
            raise IntegrityError(statement, {}, Exception(message))
        original_flush(*args, **kwargs)

    monkeypatch.setattr(db.session, "flush", _raise_duplicate_once)
    with app.app_context():
        result = apply_stripe_catalog_notification(
            app,
            _catalog_notification(
                event_id="evt_price_race_duplicate",
                event_type="price.updated",
                created=1_780_000_303,
                data_object={
                    "id": "price_race_duplicate",
                    "object": "price",
                    "product": "prod_race_duplicate",
                    "active": True,
                    "livemode": False,
                    "currency": "usd",
                    "unit_amount": 5900,
                    "type": "recurring",
                    "recurring": {"interval": "month", "interval_count": 1},
                },
            ),
        )

        assert result.status == "duplicate"
        assert result.processed is False


def test_catalog_webhook_persists_failed_event_and_allows_retry(
    app: object,
    monkeypatch: object,
) -> None:
    import flaskr.service.billing.provider_catalog_sync as sync_module

    _patch_account(monkeypatch)
    original_apply_product_health = sync_module.apply_product_health

    def _raise_health_error(row: object) -> None:
        del row
        message = "health failed"
        raise RuntimeError(message)

    monkeypatch.setattr(sync_module, "apply_product_health", _raise_health_error)
    notification = _catalog_notification(
        event_id="evt_product_failed_then_retry",
        event_type="product.updated",
        created=1_780_000_304,
        data_object={
            "id": "prod_failed_then_retry",
            "object": "product",
            "active": True,
            "livemode": False,
            "created": 1_780_000_304,
            "metadata": {},
        },
    )
    with app.app_context():
        with pytest.raises(RuntimeError):
            apply_stripe_catalog_notification(app, notification)

        failed_event = BillingProviderCatalogEvent.query.filter_by(
            provider_event_id="evt_product_failed_then_retry"
        ).one()
        assert (
            failed_event.processing_status
            == BILLING_PROVIDER_CATALOG_EVENT_STATUS_FAILED
        )
        assert "RuntimeError" in failed_event.processing_error

        monkeypatch.setattr(
            sync_module, "apply_product_health", original_apply_product_health
        )
        retry = apply_stripe_catalog_notification(app, notification)

        retried_event = BillingProviderCatalogEvent.query.filter_by(
            provider_event_id="evt_product_failed_then_retry"
        ).one()
        assert retry.processed is True
        assert (
            retried_event.processing_status
            == BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED
        )
        assert retried_event.processing_error is None


def test_reconcile_reads_stripe_catalog_inside_app_context(
    app: object,
    monkeypatch: object,
) -> None:
    import flaskr.service.billing.provider_catalog_sync as sync_module

    def _account(self: object, app: object) -> ProviderAccountSnapshot:
        del self, app
        assert has_app_context()
        return ProviderAccountSnapshot(provider="stripe", account_id="acct_test")

    def _products(self: object, app: object) -> list[ProviderProductSnapshot]:
        del self, app
        assert has_app_context()
        return [
            ProviderProductSnapshot(
                provider="stripe",
                product_id="prod_reconcile_context",
                active=True,
                livemode=True,
                raw={"id": "prod_reconcile_context", "livemode": True},
            )
        ]

    def _prices(self: object, app: object) -> list[ProviderPriceSnapshot]:
        del self, app
        assert has_app_context()
        return []

    monkeypatch.setattr(
        sync_module.StripeCatalogReadAdapter, "retrieve_account_snapshot", _account
    )
    monkeypatch.setattr(
        sync_module.StripeCatalogReadAdapter, "list_product_snapshots", _products
    )
    monkeypatch.setattr(
        sync_module.StripeCatalogReadAdapter, "list_price_snapshots", _prices
    )

    payload = reconcile_stripe_catalog(app)

    with app.app_context():
        snapshot = BillingProviderCatalogSnapshot.query.filter_by(
            object_type="product", object_id="prod_reconcile_context"
        ).one()
        assert payload["processed"] == 1
        assert snapshot.livemode == 1


def test_provider_catalog_inbox_applies_shared_filters(app: object) -> None:
    with app.app_context():
        db.session.add_all(
            [
                BillingProviderCatalogSnapshot(
                    catalog_snapshot_bid="snap-filter-price",
                    provider="stripe",
                    provider_account_id="acct_filter",
                    livemode=1,
                    object_type="price",
                    object_id="price_filter",
                    active=1,
                    deleted=0,
                ),
                BillingProviderCatalogSnapshot(
                    catalog_snapshot_bid="snap-filter-product",
                    provider="stripe",
                    provider_account_id="acct_other",
                    livemode=0,
                    object_type="product",
                    object_id="prod_filter_other",
                    active=1,
                    deleted=0,
                ),
                BillingProviderCatalogEvent(
                    catalog_event_bid="event-filter-price",
                    provider="stripe",
                    provider_event_id="evt_filter_price",
                    event_type="price.updated",
                    event_source="webhook",
                    provider_account_id="acct_filter",
                    livemode=1,
                    object_type="price",
                    object_id="price_filter",
                    processing_status=BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED,
                    deleted=0,
                ),
                BillingProviderCatalogEvent(
                    catalog_event_bid="event-filter-product",
                    provider="stripe",
                    provider_event_id="evt_filter_product",
                    event_type="product.updated",
                    event_source="webhook",
                    provider_account_id="acct_other",
                    livemode=0,
                    object_type="product",
                    object_id="prod_filter_other",
                    processing_status=BILLING_PROVIDER_CATALOG_EVENT_STATUS_PROCESSED,
                    deleted=0,
                ),
            ]
        )
        db.session.commit()

        payload = build_admin_provider_catalog_inbox_page(
            object_type="price",
            provider_account_id="acct_filter",
            livemode=True,
        )

        assert [row["object_id"] for row in payload["snapshots"]] == ["price_filter"]
        assert [row["object_id"] for row in payload["events"]] == ["price_filter"]
