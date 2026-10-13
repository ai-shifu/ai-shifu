"""Keep current discount readiness separate from historical provider records."""

from datetime import timedelta

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import campaign_provider_discounts as discounts
from flaskr.service.billing import campaigns
from flaskr.service.billing.consts import (
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CLEANUP_REQUIRED,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CREATING,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED,
    BILLING_PROVIDER_PRICE_STATUS_RETIRED,
)
from flaskr.service.billing.models import BillingCampaignProviderDiscount
from flaskr.service.billing.provider_price_mappings import ProviderPriceRuntimeScope
from flaskr.service.common.models import AppError
from flaskr.service.config import config_overrides
from flaskr.service.order import payment_providers
from flaskr.util.datetime import now_utc

from tests.service.billing.test_campaign_provider_discounts import (
    _binding,
    _campaign,
    _FakeCampaignDiscountProvider,
    _mapping,
    _product,
)
from tests.service.order.test_payment_catalog_extension import (
    CatalogHostedProvider,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.fixture
def current_scope(monkeypatch: pytest.MonkeyPatch, integration_app: Flask) -> Flask:
    payment_providers.register_payment_provider(CatalogHostedProvider)
    monkeypatch.setattr(
        discounts,
        "_DISCOUNT_SCOPE_RESOLVERS",
        {
            provider: lambda _app: ProviderPriceRuntimeScope(
                provider_account_id="acct_test", livemode=False
            )
            for provider in ("stripe", "fixture-catalog")
        },
    )
    return integration_app


def seed(providers: tuple[str, ...] = ("stripe",)) -> None:
    with unit_of_work():
        campaign = _campaign(campaign_bid="current-sync")
        campaign.enabled = 0
        campaign.start_at = now_utc() - timedelta(days=1)
        campaign.end_at = now_utc() + timedelta(days=1)
        db.session.add_all([campaign, _product("sync-product")])
        db.session.add(
            _binding(campaign_bid="current-sync", product_bid="sync-product")
        )
        for provider in providers:
            mapping = _mapping("sync-product", provider_price_bid=f"mapping-{provider}")
            mapping.provider = provider
            db.session.add(mapping)


def coupon(
    provider: str = "stripe", **overrides: object
) -> BillingCampaignProviderDiscount:
    fields = {
        "campaign_provider_discount_bid": f"discount-{provider}",
        "campaign_bid": "current-sync",
        "product_bid": "sync-product",
        "product_provider_price_bid": f"mapping-{provider}",
        "provider": provider,
        "provider_account_id": "acct_test",
        "provider_coupon_id": "coupon-current",
        "status": BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
        "livemode": 0,
    }
    return BillingCampaignProviderDiscount(**(fields | overrides))


@pytest.mark.parametrize("provider", ["stripe", "fixture-catalog"])
@pytest.mark.parametrize(
    "drift",
    [
        "account",
        "mode",
        "mapping",
        "mapping_retired",
        "mapping_deleted",
        "coupon_missing",
    ],
)
def test_stale_coupon_never_substitutes_for_current_readiness(
    current_scope: Flask, provider: str, drift: str
) -> None:
    seed((provider,))
    with unit_of_work():
        row = coupon(provider)
        if drift == "account":
            row.provider_account_id = "acct_old"
        elif drift == "mode":
            row.livemode = 1
        elif drift == "mapping":
            row.product_provider_price_bid = "mapping-old"
        elif drift.startswith("mapping_"):
            mapping = discounts.BillingProductProviderPrice.query.first()
            if drift == "mapping_retired":
                mapping.status = BILLING_PROVIDER_PRICE_STATUS_RETIRED
            else:
                mapping.deleted = 1
        else:
            row.provider_coupon_id = ""
        db.session.add(row)
    summary = discounts.summarize_campaign_provider_discounts(
        ["current-sync"], required_providers=[provider]
    )["current-sync"]
    assert summary["missing_provider_count"] == 1
    assert summary["current_sync"]["complete"] is False
    assert summary["active"] == 1  # History is preserved for cleanup/edit guards.
    with pytest.raises(AppError):
        discounts.assert_campaign_provider_discounts_ready(
            current_scope,
            campaign_bid="current-sync",
            product_bids=["sync-product"],
            provider=provider,
        )


@pytest.mark.parametrize("remaining", ["stripe", "fixture-catalog"])
def test_disabling_failed_provider_recovers_list_detail_enable_and_retry(
    current_scope: Flask, monkeypatch: pytest.MonkeyPatch, remaining: str
) -> None:
    removed = "stripe" if remaining == "fixture-catalog" else "fixture-catalog"
    seed((remaining, removed))
    healthy = _FakeCampaignDiscountProvider()
    broken = _FakeCampaignDiscountProvider()
    broken.create_error = RuntimeError("temporary provider failure")
    monkeypatch.setattr(
        discounts,
        "_DISCOUNT_FACTORIES",
        {remaining: lambda: healthy, removed: lambda: broken},
    )
    with config_overrides(
        {"PAYMENT_CHANNELS_ENABLED": f"{removed},{remaining}", "STRIPE_ENABLED": True}
    ):
        discounts.publish_admin_campaign_provider_discounts(
            current_scope,
            campaign_bid="current-sync",
            operator_user_bid="operator",
            provider_name=removed,
        )
        partial = discounts.publish_admin_campaign_provider_discounts(
            current_scope,
            campaign_bid="current-sync",
            operator_user_bid="operator",
            provider_name=remaining,
        )
        assert partial["summary"]["current_sync"]["complete"] is False
        with pytest.raises(AppError):
            campaigns.update_admin_billing_campaign_status(
                current_scope,
                campaign_bid="current-sync",
                operator_user_bid="operator",
                payload={"enabled": True},
            )
    with config_overrides(
        {"PAYMENT_CHANNELS_ENABLED": remaining, "STRIPE_ENABLED": True}
    ):
        for _ in range(2):
            result = discounts.publish_admin_campaign_provider_discounts(
                current_scope,
                campaign_bid="current-sync",
                operator_user_bid="operator",
                provider_name=remaining,
            )
            summary = result["summary"]
            assert summary["failed"] == 1
            assert summary["current_sync"]["complete"] is True
            assert summary["current_sync"]["failed"] == 0
            detail = campaigns.build_admin_billing_campaign_detail(
                current_scope, "current-sync"
            )
            page = campaigns.build_admin_billing_campaigns_page(current_scope)
            assert detail.campaign.provider_discount_summary == summary
            assert (
                next(
                    row for row in page.items if row.campaign_bid == "current-sync"
                ).provider_discount_summary
                == summary
            )
            enabled = campaigns.update_admin_billing_campaign_status(
                current_scope,
                campaign_bid="current-sync",
                operator_user_bid="operator",
                payload={"enabled": True},
            )
            assert enabled.campaign.enabled is True
        assert len(healthy.created) == 1  # Retrying reuses the current coupon.
        assert db.session.query(BillingCampaignProviderDiscount).count() == 2


@pytest.mark.parametrize(
    "status",
    [
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CREATING,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CLEANUP_REQUIRED,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED,
    ],
)
def test_sync_matches_readiness_for_current_row_states(
    current_scope: Flask, status: int
) -> None:
    seed()
    with unit_of_work():
        db.session.add(coupon(status=status))
    summary = discounts.summarize_campaign_provider_discounts(
        ["current-sync"], required_providers=["stripe"]
    )["current-sync"]
    ready = status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE
    assert summary["current_sync"]["complete"] is ready
    if ready:
        discounts.assert_campaign_provider_discounts_ready(
            current_scope, campaign_bid="current-sync", product_bids=["sync-product"]
        )
    else:
        with pytest.raises(AppError):
            discounts.assert_campaign_provider_discounts_ready(
                current_scope,
                campaign_bid="current-sync",
                product_bids=["sync-product"],
            )


def test_unknown_scope_stays_incomplete_and_scope_resolution_is_batched(
    current_scope: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert current_scope.testing
    seed()
    with unit_of_work():
        db.session.add(coupon())
    calls = []

    def unavailable(_app: Flask) -> ProviderPriceRuntimeScope:
        calls.append(True)
        message = "scope unavailable"
        raise RuntimeError(message)

    monkeypatch.setitem(discounts._DISCOUNT_SCOPE_RESOLVERS, "stripe", unavailable)
    summaries = discounts.summarize_campaign_provider_discounts(
        ["current-sync", "empty"], required_providers=["stripe"]
    )
    assert len(calls) == 1
    assert all(row["current_sync"]["complete"] is False for row in summaries.values())
    assert summaries["current-sync"]["active"] == 1


@pytest.mark.parametrize("provider", ["stripe", "fixture-catalog"])
def test_retry_creates_current_coupon_without_removing_other_account_history(
    current_scope: Flask, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    seed((provider,))
    with unit_of_work():
        db.session.add(
            coupon(
                provider,
                provider_account_id="acct_old",
                campaign_provider_discount_bid="old-discount",
            )
        )
    remote = _FakeCampaignDiscountProvider()
    monkeypatch.setitem(discounts._DISCOUNT_FACTORIES, provider, lambda: remote)
    with config_overrides(
        {"PAYMENT_CHANNELS_ENABLED": provider, "STRIPE_ENABLED": True}
    ):
        before = discounts.list_admin_campaign_provider_discounts(
            current_scope, campaign_bid="current-sync"
        )
        assert before["summary"]["current_sync"]["complete"] is False
        for _ in range(2):
            result = discounts.publish_admin_campaign_provider_discounts(
                current_scope,
                campaign_bid="current-sync",
                operator_user_bid="operator",
                provider_name=provider,
            )
            assert result["summary"]["current_sync"]["complete"] is True
            assert result["summary"]["active"] == 2
            mapping = discounts.BillingProductProviderPrice.query.filter_by(
                provider=provider
            ).one()
            selected = discounts.load_current_campaign_provider_discount(
                campaign_bid="current-sync",
                product_bid="sync-product",
                provider_price_mapping=mapping,
            )
            assert selected is not None
            assert selected.provider_account_id == "acct_test"
            assert selected.campaign_provider_discount_bid != "old-discount"
            discounts.assert_campaign_provider_discounts_ready(
                current_scope,
                campaign_bid="current-sync",
                product_bids=["sync-product"],
                provider=provider,
            )
        assert len(remote.created) == 1
        old = BillingCampaignProviderDiscount.query.filter_by(
            campaign_provider_discount_bid="old-discount"
        ).one()
        assert old.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE


def test_current_success_is_not_overridden_by_duplicate_failure_history(
    current_scope: Flask,
) -> None:
    assert current_scope.testing
    seed()
    with unit_of_work():
        db.session.add_all(
            [
                coupon(),
                coupon(
                    campaign_provider_discount_bid="duplicate-failure",
                    provider_coupon_id="coupon-failed",
                    status=BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
                ),
            ]
        )
    summary = discounts.summarize_campaign_provider_discounts(
        ["current-sync"], required_providers=["stripe"]
    )["current-sync"]
    assert summary["current_sync"]["complete"] is True
    assert summary["current_sync"]["active_pair_count"] == 1
    discounts.assert_campaign_provider_discounts_ready(
        current_scope, campaign_bid="current-sync", product_bids=["sync-product"]
    )
