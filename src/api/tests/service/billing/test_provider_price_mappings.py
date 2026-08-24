"""Validate provider price mapping persistence and lifecycle transitions."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.config import config_overrides

if TYPE_CHECKING:
    from flask import Flask
from flaskr.service.billing.consts import (
    BILLING_INTERVAL_MONTH,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_DRAFT,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
    BILLING_PROVIDER_PRICE_STATUS_RETIRED,
)
from flaskr.service.billing.models import BillingProduct, BillingProductProviderPrice
from flaskr.service.billing.provider_catalog import (
    ProviderAccountSnapshot,
    ProviderCatalogSnapshot,
    ProviderPriceSnapshot,
    ProviderProductSnapshot,
    StripeCatalogReadAdapter,
)
from flaskr.service.billing.provider_price_mappings import (
    ProviderPriceMappingError,
    _infer_stripe_livemode_from_secret_key,
    _select_single_active_mapping,
    activate_provider_price_mapping,
    get_active_provider_price_mapping,
    restore_retired_provider_price_mapping,
    upsert_provider_price_mapping,
    validate_provider_price_mapping_by_bid,
)
from flaskr.util.datetime import now_utc


class _FakeStripeCatalogAdapter(StripeCatalogReadAdapter):
    def __init__(self, snapshot: ProviderCatalogSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[dict[str, str]] = []

    def retrieve_mapping_snapshot(
        self,
        app: Flask,
        *,
        provider_product_id: str,
        provider_price_id: str,
    ) -> ProviderCatalogSnapshot:
        _ = app
        self.calls.append(
            {
                "provider_product_id": provider_product_id,
                "provider_price_id": provider_price_id,
            }
        )
        return self.snapshot


@pytest.mark.parametrize(
    ("secret_key", "expected_livemode"),
    [
        ("sk_live_123", True),
        ("sk_test_123", False),
        ("", False),
        ("not-a-stripe-key", False),
    ],
)
def test_infer_stripe_livemode_from_secret_key_prefix(
    secret_key: str,
    expected_livemode: bool,
) -> None:
    with config_overrides({"STRIPE_SECRET_KEY": secret_key}):
        assert _infer_stripe_livemode_from_secret_key() is expected_livemode


def _product(product_bid: str = "bill-product-mapping-growth") -> BillingProduct:
    product_code_suffix = product_bid.removeprefix("bill-product-mapping-")
    return BillingProduct(
        product_bid=product_bid,
        product_code=f"creator-global-growth-{product_code_suffix}",
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


def _snapshot(
    *,
    account_id: str = "acct_test",
    product_id: str = "prod_growth",
    price_id: str = "price_growth_month",
    price_product_id: str = "prod_growth",
    unit_amount: int = 5900,
    currency: str = "usd",
    product_code: str = "creator-global-growth-monthly",
) -> ProviderCatalogSnapshot:
    return ProviderCatalogSnapshot(
        account=ProviderAccountSnapshot(provider="stripe", account_id=account_id),
        product=ProviderProductSnapshot(
            provider="stripe",
            product_id=product_id,
            active=True,
            livemode=False,
            metadata={
                "market": "global",
                "plan_tier": "growth",
                "product_type": "plan",
            },
        ),
        price=ProviderPriceSnapshot(
            provider="stripe",
            price_id=price_id,
            product_id=price_product_id,
            active=True,
            livemode=False,
            currency=currency,
            unit_amount=unit_amount,
            price_type="recurring",
            recurring_interval="month",
            recurring_interval_count=1,
            recurring_usage_type="licensed",
            metadata={
                "product_code": product_code,
                "credit_amount": "1000",
                "billing_interval": "month",
            },
        ),
    )


def _bind_mapping(
    *,
    product_bid: str = "bill-product-mapping-growth",
    provider_price_id: str = "price_growth_month",
    provider_product_id: str = "prod_growth",
) -> BillingProductProviderPrice:
    mapping, _ = upsert_provider_price_mapping(
        product_bid=product_bid,
        provider_account_id="acct_test",
        provider_product_id=provider_product_id,
        provider_price_id=provider_price_id,
        livemode=False,
    )
    return mapping


def test_provider_price_mapping_upsert_is_idempotent(app: object) -> None:
    product_bid = "bill-product-mapping-idempotent"
    with app.app_context():
        db.session.add(_product(product_bid))
        db.session.commit()

        first, first_created = upsert_provider_price_mapping(
            product_bid=product_bid,
            provider_account_id="acct_test",
            provider_product_id="prod_growth",
            provider_price_id="price_mapping_idempotent",
            livemode=False,
            metadata={"source": "first"},
        )
        second, second_created = upsert_provider_price_mapping(
            product_bid=product_bid,
            provider_account_id="acct_test",
            provider_product_id="prod_growth",
            provider_price_id="price_mapping_idempotent",
            livemode=False,
            metadata={"source": "second"},
        )
        db.session.commit()

        assert first_created is True
        assert second_created is False
        assert second.provider_price_bid == first.provider_price_bid
        assert second.metadata_json == {"source": "second"}
        assert (
            BillingProductProviderPrice.query.filter_by(
                provider_price_id="price_mapping_idempotent"
            ).count()
            == 1
        )


def test_provider_price_mapping_rebind_resets_invalid_lifecycle_state(
    app: object,
) -> None:
    product_bid = "bill-product-mapping-rebind-invalid"
    with app.app_context():
        db.session.add(_product(product_bid))
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_rebind_invalid",
        )
        stale_time = now_utc()
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_INVALID
        mapping.validated_at = stale_time
        mapping.activated_at = stale_time
        mapping.retired_at = stale_time
        mapping.validation_error = "stale validation result"
        db.session.commit()

        rebound, created = upsert_provider_price_mapping(
            product_bid=product_bid,
            provider_account_id="acct_test",
            provider_product_id="prod_growth_updated",
            provider_price_id="price_rebind_invalid",
            livemode=False,
            metadata={"source": "rebound"},
        )
        db.session.commit()

        assert created is False
        assert rebound.provider_price_bid == mapping.provider_price_bid
        assert rebound.status == BILLING_PROVIDER_PRICE_STATUS_DRAFT
        assert rebound.validated_at is None
        assert rebound.activated_at is None
        assert rebound.retired_at is None
        assert rebound.validation_error == ""
        assert rebound.provider_product_id == "prod_growth_updated"
        assert rebound.metadata_json == {"source": "rebound"}


def test_provider_price_mapping_rejects_retired_rebind(app: object) -> None:
    product_bid = "bill-product-mapping-rebind-retired"
    with app.app_context():
        db.session.add(_product(product_bid))
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_rebind_retired",
        )
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_RETIRED
        mapping.retired_at = now_utc()
        db.session.commit()

        with pytest.raises(ProviderPriceMappingError) as exc_info:
            upsert_provider_price_mapping(
                product_bid=product_bid,
                provider_account_id="acct_test",
                provider_product_id="prod_growth_updated",
                provider_price_id="price_rebind_retired",
                livemode=False,
            )

        assert exc_info.value.code == "retired_mapping_cannot_be_rebound"
        assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_RETIRED
        assert mapping.product_bid == product_bid
        assert mapping.provider_product_id == "prod_growth"


def test_provider_price_mapping_restores_retired_mapping_to_draft(app: object) -> None:
    product_bid = "bill-product-mapping-restore-retired"
    with app.app_context():
        db.session.add(_product(product_bid))
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_restore_retired",
        )
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_RETIRED
        mapping.validated_at = now_utc()
        mapping.activated_at = now_utc()
        mapping.retired_at = now_utc()
        mapping.validation_error = "stale"
        db.session.commit()

        restored = restore_retired_provider_price_mapping(mapping.provider_price_bid)
        db.session.commit()

        assert restored.provider_price_bid == mapping.provider_price_bid
        assert restored.status == BILLING_PROVIDER_PRICE_STATUS_DRAFT
        assert restored.validated_at is None
        assert restored.activated_at is None
        assert restored.retired_at is None
        assert restored.validation_error == ""
        assert restored.provider_price_id == "price_restore_retired"


def test_provider_price_mapping_restore_is_idempotent_for_draft_mapping(
    app: object,
) -> None:
    product_bid = "bill-product-mapping-restore-draft"
    with app.app_context():
        db.session.add(_product(product_bid))
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_restore_draft",
        )
        mapping.validated_at = now_utc()
        mapping.activated_at = now_utc()
        mapping.retired_at = now_utc()
        mapping.validation_error = "stale"
        db.session.commit()

        restored = restore_retired_provider_price_mapping(mapping.provider_price_bid)

        assert restored.provider_price_bid == mapping.provider_price_bid
        assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_DRAFT
        assert mapping.validated_at is None
        assert mapping.activated_at is None
        assert mapping.retired_at is None
        assert mapping.validation_error == ""


def test_provider_price_mapping_restore_rejects_active_mapping(app: object) -> None:
    product_bid = "bill-product-mapping-restore-active"
    with app.app_context():
        db.session.add(_product(product_bid))
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_restore_active",
        )
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        db.session.commit()

        with pytest.raises(ProviderPriceMappingError) as exc_info:
            restore_retired_provider_price_mapping(mapping.provider_price_bid)

        assert exc_info.value.code == "provider_price_mapping_not_retired"
        assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE


def test_provider_price_validate_keeps_retired_mapping_terminal(app: Flask) -> None:
    product_bid = "bill-product-mapping-validate-retired"
    with app.app_context():
        product = _product(product_bid)
        db.session.add(product)
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_validate_retired",
        )
        retired_at = now_utc()
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_RETIRED
        mapping.retired_at = retired_at
        mapping.validation_error = ""
        db.session.commit()

        result = validate_provider_price_mapping_by_bid(
            mapping.provider_price_bid,
            adapter=_FakeStripeCatalogAdapter(
                _snapshot(
                    price_id="price_validate_retired",
                    unit_amount=6900,
                    product_code=product.product_code,
                )
            ),
        )
        db.session.commit()

        assert result.valid is False
        assert {issue["code"] for issue in result.errors} == {
            "retired_mapping_cannot_be_validated"
        }
        assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_RETIRED
        assert mapping.retired_at == retired_at
        assert mapping.validation_error == ""


def test_provider_price_activation_rejects_retired_mapping(app: Flask) -> None:
    product_bid = "bill-product-mapping-activate-retired"
    with app.app_context():
        product = _product(product_bid)
        db.session.add(product)
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_activate_retired",
        )
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_RETIRED
        mapping.retired_at = now_utc()
        db.session.commit()

        with pytest.raises(ProviderPriceMappingError) as exc_info:
            activate_provider_price_mapping(
                mapping.provider_price_bid,
                adapter=_FakeStripeCatalogAdapter(
                    _snapshot(
                        price_id="price_activate_retired",
                        product_code=product.product_code,
                    )
                ),
            )

        assert exc_info.value.code == "retired_mapping_cannot_be_activated"
        assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_RETIRED


def test_provider_price_mapping_rejects_rebinding_price_to_different_product(
    app: object,
) -> None:
    first_product_bid = "bill-product-mapping-price-original"
    second_product_bid = "bill-product-mapping-price-other"
    with app.app_context():
        db.session.add(_product(first_product_bid))
        db.session.add(_product(second_product_bid))
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=first_product_bid,
            provider_price_id="price_rebind_other_product",
        )
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_INVALID
        db.session.commit()

        with pytest.raises(ProviderPriceMappingError) as exc_info:
            upsert_provider_price_mapping(
                product_bid=second_product_bid,
                provider_account_id="acct_test",
                provider_product_id="prod_business",
                provider_price_id="price_rebind_other_product",
                livemode=False,
            )

        assert exc_info.value.code == "provider_price_product_mismatch"
        assert mapping.product_bid == first_product_bid
        assert mapping.provider_product_id == "prod_growth"


def test_provider_price_activation_retires_existing_active_mapping(app: object) -> None:
    product_bid = "bill-product-mapping-activate"
    with app.app_context():
        product = _product(product_bid)
        db.session.add(product)
        db.session.commit()

        first = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_growth_month_old",
        )
        first.status = BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        db.session.flush()
        second = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_mapping_activate_current",
        )
        db.session.commit()

        result = activate_provider_price_mapping(
            second.provider_price_bid,
            adapter=_FakeStripeCatalogAdapter(
                _snapshot(
                    price_id="price_mapping_activate_current",
                    product_code=product.product_code,
                )
            ),
        )
        db.session.commit()

        assert result.valid is True
        assert first.status == BILLING_PROVIDER_PRICE_STATUS_RETIRED
        assert second.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        assert second.validated_at is not None
        assert (
            get_active_provider_price_mapping(
                product_bid=product_bid,
                provider_account_id="acct_test",
                livemode=False,
            ).provider_price_bid
            == second.provider_price_bid
        )


def test_provider_price_activation_failure_preserves_existing_active_mapping(
    app: object,
) -> None:
    product_bid = "bill-product-mapping-activate-failure"
    with app.app_context():
        product = _product(product_bid)
        db.session.add(product)
        db.session.commit()

        active = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_growth_month_active",
        )
        active.status = BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        db.session.flush()
        candidate = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_growth_month_failure",
        )
        db.session.commit()

        result = activate_provider_price_mapping(
            candidate.provider_price_bid,
            adapter=_FakeStripeCatalogAdapter(
                _snapshot(
                    price_id="price_growth_month_failure",
                    unit_amount=6900,
                    product_code=product.product_code,
                )
            ),
        )
        db.session.commit()

        assert result.valid is False
        assert {issue["code"] for issue in result.errors} == {"unit_amount_mismatch"}
        assert active.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        assert candidate.status == BILLING_PROVIDER_PRICE_STATUS_INVALID
        assert (
            get_active_provider_price_mapping(
                product_bid=product_bid,
                provider_account_id="acct_test",
                livemode=False,
            ).provider_price_bid
            == active.provider_price_bid
        )


def test_provider_price_validate_keeps_valid_draft_as_draft(app: object) -> None:
    product_bid = "bill-product-mapping-validate"
    with app.app_context():
        product = _product(product_bid)
        db.session.add(product)
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_growth_month_validate",
        )
        db.session.commit()

        result = validate_provider_price_mapping_by_bid(
            mapping.provider_price_bid,
            adapter=_FakeStripeCatalogAdapter(
                _snapshot(
                    price_id="price_growth_month_validate",
                    product_code=product.product_code,
                )
            ),
        )
        db.session.commit()

        assert result.valid is True
        assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_DRAFT
        assert mapping.validated_at is not None
        assert mapping.validation_error == ""


def test_provider_price_validate_moves_recovered_invalid_mapping_to_draft(
    app: object,
) -> None:
    product_bid = "bill-product-mapping-recovered-invalid"
    with app.app_context():
        product = _product(product_bid)
        db.session.add(product)
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_growth_month_recovered_invalid",
        )
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_INVALID
        mapping.validation_error = '[{"code":"stripe_catalog_retrieve_failed"}]'
        db.session.commit()

        result = validate_provider_price_mapping_by_bid(
            mapping.provider_price_bid,
            adapter=_FakeStripeCatalogAdapter(
                _snapshot(
                    price_id="price_growth_month_recovered_invalid",
                    product_code=product.product_code,
                )
            ),
        )
        db.session.commit()

        assert result.valid is True
        assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_DRAFT
        assert mapping.validated_at is not None
        assert mapping.validation_error == ""


def test_active_provider_price_validate_failure_invalidates_mapping(
    app: object,
) -> None:
    product_bid = "bill-product-mapping-active-invalid"
    with app.app_context():
        product = _product(product_bid)
        db.session.add(product)
        db.session.commit()
        mapping = _bind_mapping(
            product_bid=product_bid,
            provider_price_id="price_active_invalid",
        )
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        db.session.commit()

        result = validate_provider_price_mapping_by_bid(
            mapping.provider_price_bid,
            adapter=_FakeStripeCatalogAdapter(
                _snapshot(
                    price_id="price_active_invalid",
                    unit_amount=6900,
                    product_code=product.product_code,
                )
            ),
        )
        db.session.commit()

        assert result.valid is False
        assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_INVALID
        assert "unit_amount_mismatch" in mapping.validation_error
        assert (
            get_active_provider_price_mapping(
                product_bid=product_bid,
                provider_account_id="acct_test",
                livemode=False,
            )
            is None
        )


def test_active_provider_price_selection_fails_closed_for_multiple_rows() -> None:
    rows = [
        BillingProductProviderPrice(provider_price_bid="provider-price-active-a"),
        BillingProductProviderPrice(provider_price_bid="provider-price-active-b"),
    ]

    with pytest.raises(ProviderPriceMappingError) as exc_info:
        _select_single_active_mapping(rows, product_bid="bill-product-corrupt")

    assert exc_info.value.code == "multiple_active_provider_prices"


def test_admin_provider_price_create_infers_account_and_mode_from_stripe(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import admin_provider_prices

    product_bid = "bill-product-mapping-admin-infer"

    def fake_read_snapshot(
        _app: Flask, *, provider_product_id: str, provider_price_id: str
    ) -> ProviderCatalogSnapshot:
        assert provider_product_id == "prod_admin_infer"
        assert provider_price_id == "price_admin_infer"
        return _snapshot(
            account_id="acct_admin_infer",
            product_id="prod_admin_infer",
            price_id="price_admin_infer",
        )

    monkeypatch.setattr(
        admin_provider_prices,
        "_read_provider_snapshot",
        fake_read_snapshot,
    )

    with app.app_context():
        db.session.add(_product(product_bid))
        db.session.commit()

        result = admin_provider_prices.create_admin_billing_provider_price_mapping(
            app,
            payload={
                "product_bid": product_bid,
                "provider_product_id": "prod_admin_infer",
                "provider_price_id": "price_admin_infer",
            },
        )
        db.session.commit()

        mapping = result["mapping"]
        assert result["created"] is True
        assert mapping["provider_account_id"] == "acct_admin_infer"
        assert mapping["livemode"] is False
        assert mapping["provider_product_id"] == "prod_admin_infer"
        assert mapping["provider_price_id"] == "price_admin_infer"
