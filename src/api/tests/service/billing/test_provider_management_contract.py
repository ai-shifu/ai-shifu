"""Verify provider-neutral administration and legacy discount admission."""

from dataclasses import replace
from datetime import timedelta

import pytest
from flask import Flask, request
from flaskr import dao
from flaskr.service.billing import (
    campaign_discount_providers,
    campaigns,
    provider_catalog,
    provider_management,
)
from flaskr.service.billing.consts import BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT
from flaskr.service.common.models import AppError
from flaskr.service.config import config_overrides
from flaskr.service.order import payment_providers, raw_snapshots
from flaskr.util.datetime import now_utc

from tests.service.billing.test_admin_billing_routes import admin_billing_client
from tests.service.billing.test_campaign_provider_discounts import (
    _FakeCampaignDiscountProvider,
)
from tests.service.order.test_payment_catalog_extension import (
    CatalogHostedProvider,
    CatalogReader,
    CatalogSnapshot,
    integration_app,
)

__all__ = ["admin_billing_client", "integration_app"]


class OtherDiscountProvider(CatalogHostedProvider):
    channel = "fixture-discounts"
    definition = replace(
        CatalogHostedProvider.definition, label_key="fixture.discounts"
    )


@pytest.mark.parametrize(
    ("channels", "required", "providers"),
    [
        ("stripe", True, ["stripe"]),
        ("stripe,pingxx", False, ["stripe"]),
        ("pingxx", False, []),
        ("alipay,wechatpay", False, []),
        ("fixture-catalog", True, ["fixture-catalog"]),
        ("fixture-catalog,pingxx", True, ["fixture-catalog"]),
        ("stripe,fixture-catalog,pingxx", True, ["fixture-catalog", "stripe"]),
        (
            "fixture-catalog,fixture-discounts,pingxx",
            True,
            ["fixture-catalog", "fixture-discounts"],
        ),
    ],
)
def test_discount_admission_legacy_and_new_mixed_channels(
    integration_app: Flask, channels: str, required: bool, providers: list[str]
) -> None:
    assert integration_app.testing
    payment_providers.register_payment_provider(CatalogHostedProvider)
    payment_providers.register_payment_provider(OtherDiscountProvider)
    with config_overrides(
        {"PAYMENT_CHANNELS_ENABLED": channels, "STRIPE_ENABLED": True}
    ):
        assert (
            campaigns._should_require_provider_discount_sync_for_benefit(
                BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT
            )
            is required
        )
        assert campaigns._enabled_discount_providers() == providers
        assert not campaigns._should_require_provider_discount_sync_for_benefit(0)


def test_new_configuration_skips_disabled_stripe(integration_app: Flask) -> None:
    assert integration_app.testing
    payment_providers.register_payment_provider(CatalogHostedProvider)
    with config_overrides(
        {
            "PAYMENT_CHANNELS_ENABLED": "stripe,fixture-catalog,pingxx",
            "STRIPE_ENABLED": False,
        }
    ):
        assert provider_management.configured_discount_providers() == [
            "fixture-catalog"
        ]
        assert provider_management.requires_provider_discount_sync()


def test_operator_discovery_exposes_safe_configured_capabilities(
    admin_billing_client: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        payment_providers,
        "_PROVIDER_REGISTRY",
        dict(payment_providers._PROVIDER_REGISTRY),
    )
    payment_providers.register_payment_provider(CatalogHostedProvider)
    with config_overrides(
        {
            "PAYMENT_CHANNELS_ENABLED": "fixture-catalog,pingxx,stripe,unknown",
            "STRIPE_ENABLED": False,
        }
    ):
        result = (
            admin_billing_client["client"]
            .get("/api/admin/billing/payment-providers")
            .get_json(force=True)
        )
    assert result["code"] == 0, result
    assert result["data"]["discount_sync_required"] is True
    items = {item["provider"]: item for item in result["data"]["items"]}
    assert set(items) == {"fixture-catalog", "pingxx"}
    assert items["fixture-catalog"]["catalog"] is True
    assert items["fixture-catalog"]["discounts"] is True
    assert items["pingxx"]["discounts"] is False
    assert all(
        set(item) == {"provider", "label_key", "catalog", "discounts"}
        for item in items.values()
    )


def test_provider_discovery_rejects_non_operator(
    admin_billing_client: dict[str, object],
) -> None:
    result = (
        admin_billing_client["client"]
        .get("/api/admin/billing/payment-providers", headers={"X-Operator": "0"})
        .get_json(force=True)
    )
    assert result["code"] != 0


def offer_payload() -> dict[str, object]:
    now = now_utc()
    return {
        "name": "Provider-neutral offer",
        "note": "",
        "benefit_type": "discount",
        "enabled": True,
        "products": [
            {
                "product_bid": "bill-product-plan-monthly",
                "discount_type": "fixed",
                "campaign_price_amount": "490",
            }
        ],
        "start_at": now - timedelta(days=1),
        "end_at": now + timedelta(days=1),
    }


@pytest.mark.parametrize("channels", ["fixture-catalog", "fixture-catalog,pingxx"])
def test_admin_price_discount_and_checkout_lifecycle(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, channels: str
) -> None:
    app = integration_app
    monkeypatch.setattr(
        provider_catalog, "_CATALOG_READERS", dict(provider_catalog._CATALOG_READERS)
    )
    monkeypatch.setattr(
        campaign_discount_providers,
        "_DISCOUNT_PROVIDERS",
        dict(campaign_discount_providers._DISCOUNT_PROVIDERS),
    )
    payment_providers.register_payment_provider(CatalogHostedProvider)
    raw_snapshots.register_native_snapshot_model(
        "fixture-catalog", CatalogSnapshot, "alipay_order_bid"
    )
    provider_catalog.register_catalog_reader("fixture-catalog", CatalogReader)
    discounts = _FakeCampaignDiscountProvider()
    campaign_discount_providers.register_discount_provider(
        "fixture-catalog", lambda: discounts
    )

    @app.before_request
    def operator_context() -> None:
        request.user.is_operator = True

    CatalogSnapshot.__table__.create(dao.db.engine)
    try:
        with config_overrides(
            {
                "PAYMENT_CHANNELS_ENABLED": channels,
                "HOST_URL": "https://app.example.test",
            }
        ):
            client = app.test_client()
            created = client.post(
                "/api/admin/billing/provider-prices",
                json={
                    "provider": "fixture-catalog",
                    "product_bid": "bill-product-plan-monthly",
                    "provider_product_id": "catalog-product",
                    "provider_price_id": "catalog-offer",
                },
            ).get_json(force=True)
            assert created["code"] == 0, created
            mapping_bid = created["data"]["mapping"]["provider_price_bid"]
            for action in ("validate", "activate"):
                result = client.post(
                    f"/api/admin/billing/provider-prices/{mapping_bid}/{action}"
                ).get_json(force=True)
                assert result["code"] == 0, result
                assert result["data"]["valid"], result
            listed = client.get(
                "/api/admin/billing/provider-prices?provider=fixture-catalog"
            ).get_json(force=True)
            assert listed["code"] == 0, listed
            assert listed["data"]["provider"] == "fixture-catalog", listed
            detail = campaigns.create_admin_billing_campaign(
                app, operator_user_bid="operator", payload=offer_payload()
            )
            assert detail.campaign.enabled is False
            bid = detail.campaign.campaign_bid
            assert (
                detail.campaign.provider_discount_summary["missing_provider_count"] == 1
            )
            for update, payload in (
                (campaigns.update_admin_billing_campaign_status, {"enabled": True}),
                (campaigns.update_admin_billing_campaign, offer_payload()),
            ):
                with pytest.raises(AppError):
                    update(
                        app,
                        operator_user_bid="operator",
                        campaign_bid=bid,
                        payload=payload,
                    )
            for endpoint in ("publish", "publish/retry"):
                result = client.post(
                    f"/api/admin/billing/campaigns/{bid}/{endpoint}",
                    json={"provider": "fixture-catalog"},
                ).get_json(force=True)
                assert result["code"] == 0, result
                assert result["data"]["items"][0]["provider"] == "fixture-catalog", (
                    result
                )
            assert len(discounts.created) == 1
            campaigns.update_admin_billing_campaign_status(
                app,
                operator_user_bid="operator",
                campaign_bid=bid,
                payload={"enabled": True},
            )
            assert (
                campaigns.build_admin_billing_campaign_detail(
                    app, bid
                ).campaign.provider_discount_summary["missing_provider_count"]
                == 0
            )
            result = client.post(
                "/api/billing/subscriptions/checkout",
                json={
                    "product_bid": "bill-product-plan-monthly",
                    "payment_option": "fixture-catalog:fixture_checkout",
                },
            ).get_json(force=True)
            assert result["code"] == 0, result
            assert CatalogHostedProvider.checkout_terms[-1].amount == 490
            assert CatalogHostedProvider.checkout_terms[-1].discount_reference
    finally:
        dao.db.session.remove()
        CatalogSnapshot.__table__.drop(dao.db.engine)


def test_enable_checks_all_capable_providers_and_skips_local_only(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert integration_app.testing
    payment_providers.register_payment_provider(CatalogHostedProvider)
    payment_providers.register_payment_provider(OtherDiscountProvider)
    checked = []

    def check(
        app: Flask, *, campaign_bid: str, product_bids: list[str], provider: str
    ) -> None:
        del app, campaign_bid, product_bids
        checked.append(provider)
        if provider == "fixture-discounts":
            code = "server.billing.campaignProviderDiscountSyncRequired"
            raise AppError(code)

    monkeypatch.setattr(campaigns, "assert_campaign_provider_discounts_ready", check)
    with config_overrides(
        {"PAYMENT_CHANNELS_ENABLED": "fixture-catalog,fixture-discounts,pingxx"}
    ):
        detail = campaigns.create_admin_billing_campaign(
            integration_app, operator_user_bid="operator", payload=offer_payload()
        )
        with pytest.raises(AppError):
            campaigns.update_admin_billing_campaign_status(
                integration_app,
                operator_user_bid="operator",
                campaign_bid=detail.campaign.campaign_bid,
                payload={"enabled": True},
            )
        assert checked == ["fixture-catalog", "fixture-discounts"]
        assert not campaigns.build_admin_billing_campaign_detail(
            integration_app, detail.campaign.campaign_bid
        ).campaign.enabled


def test_partial_publication_reports_a_missing_provider(integration_app: Flask) -> None:
    assert integration_app.testing
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.billing.campaign_provider_discounts import (
        summarize_campaign_provider_discounts,
    )
    from flaskr.service.billing.consts import (
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
        BILLING_PRODUCT_TYPE_PLAN,
    )
    from flaskr.service.billing.models import (
        BillingCampaignProduct,
        BillingCampaignProviderDiscount,
    )

    with unit_of_work():
        dao.db.session.add(
            BillingCampaignProduct(
                campaign_bid="partial-campaign",
                product_bid="bill-product-plan-monthly",
                product_type=BILLING_PRODUCT_TYPE_PLAN,
            )
        )
        dao.db.session.add(
            BillingCampaignProviderDiscount(
                campaign_provider_discount_bid="partial-discount",
                campaign_bid="partial-campaign",
                product_bid="bill-product-plan-monthly",
                product_provider_price_bid="partial-price",
                provider="fixture-catalog",
                provider_account_id="acct_test",
                provider_coupon_id="coupon-partial",
                status=BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
            )
        )
    summary = summarize_campaign_provider_discounts(
        ["partial-campaign", "empty-campaign"],
        required_providers=["fixture-catalog", "stripe"],
    )
    assert summary["partial-campaign"]["active"] == 1
    assert summary["partial-campaign"]["missing_provider_count"] == 1
    assert summary["empty-campaign"]["missing_provider_count"] == 2
