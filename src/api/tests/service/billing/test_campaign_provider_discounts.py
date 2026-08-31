"""Verify billing campaign provider discount publishing."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal
from typing import ClassVar

import pytest
from flaskr.dao import db
from flaskr.service.billing import campaigns as billing_campaigns
from flaskr.service.billing.campaign_discount_providers import (
    ProviderDiscountCreateRequest,
    ProviderDiscountSnapshot,
    StripeCampaignDiscountProvider,
)
from flaskr.service.billing.campaign_provider_discounts import (
    CampaignProviderDiscountError,
    list_admin_campaign_provider_discounts,
    publish_admin_campaign_provider_discounts,
    retire_admin_campaign_provider_discounts,
    summarize_campaign_provider_discounts,
    validate_admin_campaign_provider_discount,
)
from flaskr.service.billing.campaigns import (
    create_admin_billing_campaign,
    update_admin_billing_campaign,
    update_admin_billing_campaign_status,
)
from flaskr.service.billing.consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CLEANUP_REQUIRED,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED,
    BILLING_INTERVAL_MONTH,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingCampaignProviderDiscount,
    BillingProduct,
    BillingProductProviderPrice,
)
from flaskr.service.billing.provider_price_mappings import (
    ProviderPriceRuntimeScope,
    retire_provider_price_mapping,
)
from flaskr.service.common.models import AppError
from flaskr.util.datetime import now_utc


class _FakeCampaignDiscountProvider:
    def __init__(self) -> None:
        self.created: list[ProviderDiscountCreateRequest] = []
        self.retired: list[str] = []
        self.snapshots: dict[str, ProviderDiscountSnapshot] = {}
        self.create_error: Exception | None = None
        self.retrieve_error: Exception | None = None
        self.retire_error: Exception | None = None

    def create_campaign_discount(
        self, *, request: ProviderDiscountCreateRequest, app: object
    ) -> ProviderDiscountSnapshot:
        _ = app
        if self.create_error is not None:
            raise self.create_error
        self.created.append(request)
        coupon_id = f"coupon_{request.campaign_provider_discount_bid}"
        snapshot = ProviderDiscountSnapshot(
            provider_coupon_id=coupon_id,
            provider_account_id="acct_test",
            livemode=False,
            valid=True,
            currency=request.currency,
            amount_off=request.amount_off,
            percent_off=request.percent_off,
            duration=request.duration,
            applies_to_product_ids=[request.provider_product_id],
            metadata=request.metadata,
        )
        self.snapshots[coupon_id] = snapshot
        return snapshot

    def retrieve_campaign_discount(
        self, *, provider_coupon_id: str, app: object
    ) -> ProviderDiscountSnapshot:
        _ = app
        if self.retrieve_error is not None:
            raise self.retrieve_error
        return self.snapshots[provider_coupon_id]

    def retire_campaign_discount(
        self, *, provider_coupon_id: str, app: object
    ) -> ProviderDiscountSnapshot:
        _ = app
        if self.retire_error is not None:
            raise self.retire_error
        self.retired.append(provider_coupon_id)
        return self.snapshots[provider_coupon_id]


class _StripeResourceMissingError(RuntimeError):
    code = "resource_missing"


def _product(product_bid: str = "product-growth-month") -> BillingProduct:
    return BillingProduct(
        product_bid=product_bid,
        product_code=f"creator-global-growth-{product_bid}",
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
        sort_order=10,
        metadata_json={"plan_tier": "growth"},
    )


def _mapping(
    product_bid: str = "product-growth-month",
    *,
    provider_price_bid: str | None = None,
    provider_account_id: str = "acct_test",
    livemode: bool = False,
) -> BillingProductProviderPrice:
    return BillingProductProviderPrice(
        provider_price_bid=provider_price_bid or f"provider-price-{product_bid}",
        product_bid=product_bid,
        provider="stripe",
        provider_account_id=provider_account_id,
        provider_product_id=f"prod_{product_bid}",
        provider_price_id=f"price_{product_bid}",
        livemode=int(bool(livemode)),
        currency="USD",
        unit_amount=5900,
        billing_mode=BILLING_MODE_RECURRING,
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
        status=BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
        activated_at=now_utc(),
    )


def _campaign(
    *,
    campaign_bid: str = "campaign-growth-fixed",
    benefit_type: int = BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    discount_type: int = BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    discount_percent: Decimal = Decimal(0),
    bonus_credit_amount: Decimal = Decimal(0),
) -> BillingCampaign:
    now = now_utc()
    return BillingCampaign(
        campaign_bid=campaign_bid,
        name="Growth launch",
        note="",
        benefit_type=benefit_type,
        discount_type=discount_type,
        discount_amount=1000
        if discount_type == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED
        else 0,
        discount_percent=discount_percent,
        bonus_credit_amount=bonus_credit_amount,
        enabled=1,
        start_at=now,
        end_at=now.replace(year=now.year + 1),
        created_user_bid="operator",
        updated_user_bid="operator",
    )


def _binding(
    *,
    campaign_bid: str = "campaign-growth-fixed",
    product_bid: str = "product-growth-month",
    benefit_type: int = BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    discount_type: int = BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    campaign_price_amount: int = 4900,
    discount_percent: Decimal = Decimal(0),
    bonus_credit_amount: Decimal = Decimal(0),
) -> BillingCampaignProduct:
    return BillingCampaignProduct(
        campaign_bid=campaign_bid,
        product_bid=product_bid,
        product_type=BILLING_PRODUCT_TYPE_PLAN,
        discount_type=discount_type
        if benefit_type == BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT
        else 0,
        discount_amount=1000
        if discount_type == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED
        else 0,
        discount_percent=discount_percent,
        campaign_price_amount=campaign_price_amount,
        bonus_credit_amount=bonus_credit_amount,
    )


def _seed_discount_campaign(
    *,
    campaign_bid: str = "campaign-growth-fixed",
    product_bid: str = "product-growth-month",
    discount_type: int = BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    campaign_price_amount: int = 4900,
    discount_percent: Decimal = Decimal(0),
) -> None:
    product = _product(product_bid)
    db.session.add(product)
    db.session.add(_mapping(product.product_bid))
    db.session.add(
        _campaign(
            campaign_bid=campaign_bid,
            discount_type=discount_type,
            discount_percent=discount_percent,
        )
    )
    db.session.add(
        _binding(
            campaign_bid=campaign_bid,
            product_bid=product.product_bid,
            discount_type=discount_type,
            campaign_price_amount=campaign_price_amount,
            discount_percent=discount_percent,
        )
    )
    db.session.commit()


def _patch_scope(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider_account_id: str = "acct_test",
    livemode: bool = False,
) -> None:
    import flaskr.service.billing.campaign_provider_discounts as module

    monkeypatch.setattr(
        module,
        "resolve_current_stripe_provider_price_scope",
        lambda _app: ProviderPriceRuntimeScope(
            provider_account_id=provider_account_id, livemode=livemode
        ),
    )


def _patch_payment_channels(monkeypatch: pytest.MonkeyPatch, channels: str) -> None:
    monkeypatch.setattr(
        billing_campaigns,
        "get_config",
        lambda key, default=None: (
            channels if key == "PAYMENT_CHANNELS_ENABLED" else default
        ),
    )


def _discount_campaign_payload(
    *, product_bid: str, enabled: bool | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Growth launch",
        "note": "",
        "benefit_type": "discount",
        "products": [
            {
                "product_bid": product_bid,
                "discount_type": "fixed",
                "campaign_price_amount": "4900",
            }
        ],
        "start_at": now_utc(),
        "end_at": now_utc().replace(year=now_utc().year + 1),
    }
    if enabled is not None:
        payload["enabled"] = enabled
    return payload


def test_stripe_campaign_discount_provider_scopes_coupon_to_product(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.service.billing.campaign_discount_providers as module

    class FakeCouponApi:
        last_params: ClassVar[dict[str, object]] = {}
        retrieve_params: ClassVar[dict[str, object]] = {}

        @classmethod
        def create(cls, **params: object) -> dict[str, object]:
            cls.last_params = params
            return {
                "id": "coupon_scoped",
                "account": "acct_test",
                "livemode": False,
                "valid": True,
                "currency": "usd",
                "amount_off": 1000,
                "duration": "once",
                "applies_to": {"products": ["prod_scoped"]},
                "metadata": {},
            }

        @classmethod
        def retrieve(
            cls, provider_coupon_id: str, **params: object
        ) -> dict[str, object]:
            cls.retrieve_params = {"provider_coupon_id": provider_coupon_id, **params}
            return {
                "id": provider_coupon_id,
                "account": "acct_test",
                "livemode": False,
                "valid": True,
                "currency": "usd",
                "amount_off": 1000,
                "duration": "once",
                "applies_to": {"products": ["prod_scoped"]},
                "metadata": {},
            }

    class FakeStripe:
        Coupon = FakeCouponApi

    monkeypatch.setattr(
        module,
        "get_stripe_client_options",
        lambda _app: (FakeStripe, {"api_key": "sk_test_fake"}),
    )

    snapshot = StripeCampaignDiscountProvider().create_campaign_discount(
        request=ProviderDiscountCreateRequest(
            campaign_bid="campaign",
            campaign_provider_discount_bid="provider-discount",
            product_bid="product",
            product_code="creator-global-growth-monthly",
            product_provider_price_bid="provider-price",
            provider_product_id="prod_scoped",
            provider_price_id="price_scoped",
            currency="USD",
            amount_off=1000,
            percent_off=None,
            duration="once",
            metadata={},
            idempotency_key="coupon-key",
        ),
        app=app,
    )

    assert FakeCouponApi.last_params["applies_to"] == {"products": ["prod_scoped"]}
    assert FakeCouponApi.last_params["expand"] == ["applies_to"]
    assert snapshot.applies_to_product_ids == ["prod_scoped"]

    retrieved = StripeCampaignDiscountProvider().retrieve_campaign_discount(
        provider_coupon_id="coupon_scoped",
        app=app,
    )

    assert FakeCouponApi.retrieve_params["expand"] == ["applies_to"]
    assert retrieved.applies_to_product_ids == ["prod_scoped"]


def test_create_global_discount_campaign_stays_disabled_until_stripe_sync(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_bid = "product-growth-create-sync-required"
    with app.app_context():
        product = _product(product_bid)
        db.session.add(product)
        db.session.add(_mapping(product.product_bid))
        db.session.commit()
    _patch_payment_channels(monkeypatch, "stripe")

    detail = create_admin_billing_campaign(
        app,
        operator_user_bid="operator",
        payload=_discount_campaign_payload(product_bid=product_bid),
    )

    assert detail.campaign.enabled is False


def test_update_campaign_preserves_disabled_status_when_enabled_omitted(
    app: object,
) -> None:
    product_bid = "product-growth-update-preserve-disabled"
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-update-preserve-disabled",
            product_bid=product_bid,
        )
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-growth-update-preserve-disabled"
        ).one()
        campaign.enabled = 0
        db.session.add(campaign)
        db.session.commit()

    detail = update_admin_billing_campaign(
        app,
        operator_user_bid="operator",
        campaign_bid="campaign-growth-update-preserve-disabled",
        payload=_discount_campaign_payload(product_bid=product_bid),
    )

    assert detail.campaign.enabled is False


def test_update_campaign_blocks_global_discount_enable_without_stripe_sync(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_bid = "product-growth-update-sync-required"
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-update-sync-required",
            product_bid=product_bid,
        )
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-growth-update-sync-required"
        ).one()
        campaign.enabled = 0
        db.session.add(campaign)
        db.session.commit()
    _patch_payment_channels(monkeypatch, "stripe")

    with pytest.raises(AppError) as exc_info:
        update_admin_billing_campaign(
            app,
            operator_user_bid="operator",
            campaign_bid="campaign-growth-update-sync-required",
            payload=_discount_campaign_payload(product_bid=product_bid, enabled=True),
        )

    assert "Stripe" in str(exc_info.value)


def test_publish_fixed_campaign_creates_amount_off_coupon(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(product_bid="product-growth-fixed-1")
    _patch_scope(monkeypatch)

    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-fixed",
        operator_user_bid="operator",
        provider=provider,
    )

    assert len(provider.created) == 1
    assert provider.created[0].amount_off == 1000
    assert provider.created[0].percent_off is None
    assert provider.created[0].provider_product_id == "prod_product-growth-fixed-1"
    assert provider.created[0].duration == "once"
    assert provider.created[0].idempotency_key.endswith(
        f":{BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED}:1000:0.00:USD"
    )
    assert payload["items"][0]["status"] == "active"
    assert payload["summary"]["active"] == 1
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-fixed"
        ).one()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE
        assert row.provider_coupon_id == f"coupon_{row.campaign_provider_discount_bid}"


def test_publish_redacts_full_stripe_secret_key_from_provider_failures(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    secret_key = "sk_live_SECRETbody_123"
    provider.create_error = RuntimeError(f"Stripe rejected key {secret_key}")
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-secret-redaction",
            product_bid="product-growth-secret-redaction-1",
        )
    _patch_scope(monkeypatch)

    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-secret-redaction",
        operator_user_bid="operator",
        provider=provider,
    )

    failure_message = payload["items"][0]["failure_message"]
    assert payload["items"][0]["status"] == "failed"
    assert "sk_****" in failure_message
    assert "sk_live" not in failure_message
    assert "SECRETbody" not in failure_message
    assert "123" not in failure_message


def test_publish_percent_campaign_creates_percent_off_coupon(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-percent",
            product_bid="product-growth-percent-1",
            discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
            campaign_price_amount=4720,
            discount_percent=Decimal("20.00"),
        )
    _patch_scope(monkeypatch)

    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-percent",
        operator_user_bid="operator",
        provider=provider,
    )

    assert len(provider.created) == 1
    assert provider.created[0].amount_off is None
    assert provider.created[0].percent_off == Decimal("20.00")


def test_publish_percent_campaign_rejects_fractional_minor_unit(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-fractional-percent",
            product_bid="product-growth-fractional-percent-1",
            discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
            campaign_price_amount=5162,
            discount_percent=Decimal("12.50"),
        )
    _patch_scope(monkeypatch)

    with pytest.raises(CampaignProviderDiscountError) as exc_info:
        publish_admin_campaign_provider_discounts(
            app,
            campaign_bid="campaign-growth-fractional-percent",
            operator_user_bid="operator",
            provider=provider,
        )

    assert exc_info.value.code == "fractional_minor_unit_discount"
    assert provider.created == []


def test_bonus_campaign_does_not_create_provider_coupon(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        product = _product("product-growth-bonus-1")
        db.session.add(product)
        db.session.add(_mapping(product.product_bid))
        db.session.add(
            _campaign(
                campaign_bid="campaign-growth-bonus",
                benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
                bonus_credit_amount=Decimal(500),
            )
        )
        db.session.add(
            _binding(
                campaign_bid="campaign-growth-bonus",
                product_bid=product.product_bid,
                benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
                campaign_price_amount=5900,
                bonus_credit_amount=Decimal(500),
            )
        )
        db.session.commit()
    _patch_scope(monkeypatch)

    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-bonus",
        operator_user_bid="operator",
        provider=provider,
    )

    assert provider.created == []
    assert payload["summary"]["total"] == 0
    assert payload["summary"]["active"] == 0
    assert payload["summary"]["failed"] == 0


def test_validate_and_retire_campaign_provider_discount(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-retire", product_bid="product-growth-retire-1"
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-retire",
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-retire"
        ).first()
        row_bid = row.campaign_provider_discount_bid

    validation = validate_admin_campaign_provider_discount(
        app,
        campaign_provider_discount_bid=row_bid,
        operator_user_bid="operator",
        provider=provider,
    )
    assert validation["status"] == "active"

    payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-retire",
        operator_user_bid="operator",
        provider=provider,
    )

    assert provider.retired == [payload["items"][0]["provider_coupon_id"]]
    assert payload["items"][0]["status"] == "retired"
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-retire"
        ).first()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED


def test_publish_preserves_active_coupon_on_transient_retrieve_failure(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-retrieve-failure",
            product_bid="product-growth-retrieve-failure-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-retrieve-failure",
        operator_user_bid="operator",
        provider=provider,
    )

    provider.retrieve_error = RuntimeError("stripe unavailable")
    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-retrieve-failure",
        operator_user_bid="operator",
        provider=provider,
    )

    assert payload["items"][0]["status"] == "active"
    assert payload["items"][0]["failure_code"] == ""
    assert payload["summary"]["active"] == 1
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-retrieve-failure"
        ).one()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE
        metadata = row.metadata_json or {}
        assert (
            metadata["last_provider_retrieve_error"]["message"] == "stripe unavailable"
        )


def test_validate_marks_coupon_invalid_when_product_scope_does_not_match(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-scope",
            product_bid="product-growth-scope-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-scope",
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-scope"
        ).one()
        row_bid = row.campaign_provider_discount_bid
        coupon_id = row.provider_coupon_id
    provider.snapshots[coupon_id] = ProviderDiscountSnapshot(
        provider_coupon_id=coupon_id,
        provider_account_id="acct_test",
        livemode=False,
        valid=True,
        currency="USD",
        amount_off=1000,
        percent_off=None,
        duration="once",
        applies_to_product_ids=["prod_other"],
        metadata={},
    )

    payload = validate_admin_campaign_provider_discount(
        app,
        campaign_provider_discount_bid=row_bid,
        operator_user_bid="operator",
        provider=provider,
    )

    assert payload["status"] == "provider_invalid"
    assert payload["failure_code"] == "product_scope_mismatch"
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-scope"
        ).one()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID


def test_retire_retries_cleanup_required_coupon(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-cleanup",
            product_bid="product-growth-cleanup-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-cleanup",
        operator_user_bid="operator",
        provider=provider,
    )

    provider.retire_error = RuntimeError("temporary stripe failure")
    first_payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-cleanup",
        operator_user_bid="operator",
        provider=provider,
    )
    assert first_payload["items"][0]["status"] == "cleanup_required"
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-cleanup"
        ).one()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CLEANUP_REQUIRED

    provider.retire_error = None
    retry_payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-cleanup",
        operator_user_bid="operator",
        provider=provider,
    )

    assert retry_payload["items"][0]["status"] == "retired"
    assert provider.retired == [retry_payload["items"][0]["provider_coupon_id"]]


def test_retire_includes_requires_republish_coupon(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-republish-retire",
            product_bid="product-growth-republish-retire-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish-retire",
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-republish-retire"
        ).one()
        row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH
        db.session.add(row)
        db.session.commit()

    payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish-retire",
        operator_user_bid="operator",
        provider=provider,
    )

    assert payload["items"][0]["status"] == "retired"
    assert provider.retired == [payload["items"][0]["provider_coupon_id"]]


def test_publish_after_retire_creates_replacement_coupon(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-republish",
            product_bid="product-growth-republish-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish",
        operator_user_bid="operator",
        provider=provider,
    )
    retire_payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish",
        operator_user_bid="operator",
        provider=provider,
    )
    retired_row_bid = retire_payload["items"][0]["campaign_provider_discount_bid"]

    publish_payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish",
        operator_user_bid="operator",
        provider=provider,
    )

    active_items = [
        item for item in publish_payload["items"] if item["status"] == "active"
    ]
    assert len(provider.created) == 2
    assert len(active_items) == 1
    assert active_items[0]["campaign_provider_discount_bid"] != retired_row_bid
    with app.app_context():
        replacement = BillingCampaignProviderDiscount.query.filter_by(
            campaign_provider_discount_bid=active_items[0][
                "campaign_provider_discount_bid"
            ]
        ).one()
        assert replacement.replaces_discount_bid == retired_row_bid


def test_list_campaign_provider_discounts_is_read_only(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-list", product_bid="product-growth-list-1"
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-list",
        operator_user_bid="operator",
        provider=provider,
    )

    payload = list_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-list",
    )

    assert payload["items"][0]["provider_coupon_id"].startswith("coupon_")
    assert payload["items"][0]["provider_price_id"] == "price_product-growth-list-1"


def test_campaign_provider_discount_summary_uses_stable_failure_order(
    app: object,
) -> None:
    with app.app_context():
        db.session.add(
            BillingCampaignProviderDiscount(
                campaign_provider_discount_bid="discount-z",
                campaign_bid="campaign-summary-order",
                product_bid="product-z",
                product_provider_price_bid="provider-price-z",
                provider="stripe",
                provider_account_id="acct_test",
                provider_coupon_id="coupon-z",
                status=BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
                failure_code="latest_failure",
                failure_message="latest failure by detail ordering",
            )
        )
        db.session.add(
            BillingCampaignProviderDiscount(
                campaign_provider_discount_bid="discount-a",
                campaign_bid="campaign-summary-order",
                product_bid="product-a",
                product_provider_price_bid="provider-price-a",
                provider="stripe",
                provider_account_id="acct_test",
                provider_coupon_id="coupon-a",
                status=BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
                failure_code="older_failure",
                failure_message="older failure by detail ordering",
            )
        )
        db.session.commit()

        summary = summarize_campaign_provider_discounts(["campaign-summary-order"])

    assert summary["campaign-summary-order"]["latest_failure_code"] == "latest_failure"
    assert (
        summary["campaign-summary-order"]["latest_failure_message"]
        == "latest failure by detail ordering"
    )


def test_retiring_provider_price_requires_campaign_coupon_republish(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-price-retired",
            product_bid="product-growth-price-retired-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-price-retired",
        operator_user_bid="operator",
        provider=provider,
    )

    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-price-retired"
        ).one()
        retire_provider_price_mapping(row.product_provider_price_bid)
        db.session.commit()

        refreshed = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-price-retired"
        ).one()
        assert (
            refreshed.status
            == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH
        )
        assert refreshed.failure_code == "provider_price_retired"


def test_publish_revalidates_republish_row_when_same_provider_price_restored(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-same-price-restored",
            product_bid="product-growth-same-price-restored-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-same-price-restored",
        operator_user_bid="operator",
        provider=provider,
    )

    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-same-price-restored"
        ).one()
        retire_provider_price_mapping(row.product_provider_price_bid)
        mapping = BillingProductProviderPrice.query.filter_by(
            provider_price_bid=row.product_provider_price_bid
        ).one()
        mapping.status = BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        mapping.retired_at = None
        db.session.add(mapping)
        db.session.commit()

    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-same-price-restored",
        operator_user_bid="operator",
        provider=provider,
    )

    assert len(provider.created) == 1
    assert payload["items"][0]["status"] == "active"
    assert payload["summary"]["active"] == 1
    with app.app_context():
        refreshed = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-same-price-restored"
        ).one()
        assert refreshed.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE
        assert refreshed.failure_code == ""


def test_publish_retires_old_provider_coupon_before_republish(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    product_bid = "product-growth-price-replace-1"
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-price-replace",
            product_bid=product_bid,
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-price-replace",
        operator_user_bid="operator",
        provider=provider,
    )

    with app.app_context():
        old_row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-price-replace"
        ).one()
        old_row_bid = old_row.campaign_provider_discount_bid
        old_coupon_id = old_row.provider_coupon_id
        retire_provider_price_mapping(old_row.product_provider_price_bid)
        db.session.add(
            BillingProductProviderPrice(
                provider_price_bid=f"provider-price-{product_bid}-replacement",
                product_bid=product_bid,
                provider="stripe",
                provider_account_id="acct_test",
                provider_product_id=f"prod_{product_bid}",
                provider_price_id=f"price_{product_bid}_replacement",
                livemode=0,
                currency="USD",
                unit_amount=5900,
                billing_mode=BILLING_MODE_RECURRING,
                billing_interval=BILLING_INTERVAL_MONTH,
                billing_interval_count=1,
                status=BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
                activated_at=now_utc(),
            )
        )
        db.session.commit()

    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-price-replace",
        operator_user_bid="operator",
        provider=provider,
    )

    active_items = [item for item in payload["items"] if item["status"] == "active"]
    assert provider.retired == [old_coupon_id]
    assert len(provider.created) == 2
    assert len(active_items) == 1
    assert active_items[0]["campaign_provider_discount_bid"] != old_row_bid
    with app.app_context():
        old_row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_provider_discount_bid=old_row_bid
        ).one()
        assert old_row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED


def test_publish_blocks_replacement_when_old_coupon_cleanup_fails(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    product_bid = "product-growth-price-cleanup-1"
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-price-cleanup-block",
            product_bid=product_bid,
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-price-cleanup-block",
        operator_user_bid="operator",
        provider=provider,
    )

    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-price-cleanup-block"
        ).one()
        retire_provider_price_mapping(row.product_provider_price_bid)
        db.session.add(
            BillingProductProviderPrice(
                provider_price_bid=f"provider-price-{product_bid}-replacement",
                product_bid=product_bid,
                provider="stripe",
                provider_account_id="acct_test",
                provider_product_id=f"prod_{product_bid}",
                provider_price_id=f"price_{product_bid}_replacement",
                livemode=0,
                currency="USD",
                unit_amount=5900,
                billing_mode=BILLING_MODE_RECURRING,
                billing_interval=BILLING_INTERVAL_MONTH,
                billing_interval_count=1,
                status=BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
                activated_at=now_utc(),
            )
        )
        db.session.commit()

    provider.retire_error = RuntimeError("stripe cleanup failed")
    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-price-cleanup-block",
        operator_user_bid="operator",
        provider=provider,
    )

    assert len(provider.created) == 1
    assert payload["items"][0]["status"] == "cleanup_required"
    assert payload["summary"]["cleanup_required"] == 1


def test_retire_treats_missing_provider_coupon_as_idempotent_success(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-retire-missing-coupon",
            product_bid="product-growth-retire-missing-coupon-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-retire-missing-coupon",
        operator_user_bid="operator",
        provider=provider,
    )

    provider.retire_error = _StripeResourceMissingError("No such coupon")
    payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-retire-missing-coupon",
        operator_user_bid="operator",
        provider=provider,
    )

    assert payload["items"][0]["status"] == "retired"
    assert payload["summary"]["retired"] == 1
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-retire-missing-coupon"
        ).one()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED
        assert row.failure_code == ""


def test_update_campaign_status_requires_current_scope_provider_coupon(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    product_bid = "product-growth-current-scope-required"
    campaign_bid = "campaign-growth-current-scope-required"
    with app.app_context():
        _seed_discount_campaign(campaign_bid=campaign_bid, product_bid=product_bid)
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid=campaign_bid,
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        campaign = BillingCampaign.query.filter_by(campaign_bid=campaign_bid).one()
        campaign.enabled = 0
        db.session.add(
            _mapping(
                product_bid,
                provider_price_bid=f"provider-price-{product_bid}-live",
                provider_account_id="acct_live",
                livemode=True,
            )
        )
        db.session.add(campaign)
        db.session.commit()
    _patch_scope(monkeypatch, provider_account_id="acct_live", livemode=True)
    _patch_payment_channels(monkeypatch, "stripe")

    with pytest.raises(AppError) as exc_info:
        update_admin_billing_campaign_status(
            app,
            operator_user_bid="operator",
            campaign_bid=campaign_bid,
            payload={"enabled": True},
        )

    assert "Stripe" in str(exc_info.value)


def test_retire_missing_coupon_keeps_cleanup_required_when_scope_changed(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    campaign_bid = "campaign-growth-retire-missing-scope-changed"
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid=campaign_bid,
            product_bid="product-growth-retire-missing-scope-changed-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid=campaign_bid,
        operator_user_bid="operator",
        provider=provider,
    )

    _patch_scope(monkeypatch, provider_account_id="acct_live", livemode=True)
    provider.retire_error = _StripeResourceMissingError("No such coupon")
    payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid=campaign_bid,
        operator_user_bid="operator",
        provider=provider,
    )

    assert payload["items"][0]["status"] == "cleanup_required"
    assert payload["items"][0]["failure_code"] == "provider_retire_scope_mismatch"
    assert payload["summary"]["cleanup_required"] == 1
    assert payload["summary"]["open_provider_coupon_count"] == 1
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid=campaign_bid
        ).one()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CLEANUP_REQUIRED


def test_update_campaign_blocks_rule_changes_after_coupon_publish(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-rule-lock",
            product_bid="product-growth-rule-lock-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-rule-lock",
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-growth-rule-lock"
        ).one()
        start_at = campaign.start_at
        end_at = campaign.end_at

    with pytest.raises(AppError) as exc_info:
        update_admin_billing_campaign(
            app,
            operator_user_bid="operator",
            campaign_bid="campaign-growth-rule-lock",
            payload={
                "name": "Growth launch updated",
                "note": "",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "product-growth-rule-lock-1",
                        "discount_type": "fixed",
                        "campaign_price_amount": "4800",
                    }
                ],
                "start_at": start_at,
                "end_at": end_at,
            },
        )

    assert "Stripe" in str(exc_info.value)


def test_update_campaign_blocks_rule_changes_for_republish_coupon(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-republish-rule-lock",
            product_bid="product-growth-republish-rule-lock-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish-rule-lock",
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-republish-rule-lock"
        ).one()
        row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-growth-republish-rule-lock"
        ).one()
        start_at = campaign.start_at
        end_at = campaign.end_at
        db.session.add(row)
        db.session.commit()

    with pytest.raises(AppError) as exc_info:
        update_admin_billing_campaign(
            app,
            operator_user_bid="operator",
            campaign_bid="campaign-growth-republish-rule-lock",
            payload={
                "name": "Growth launch updated",
                "note": "",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "product-growth-republish-rule-lock-1",
                        "discount_type": "fixed",
                        "campaign_price_amount": "4800",
                    }
                ],
                "start_at": start_at,
                "end_at": end_at,
            },
        )

    assert "Stripe" in str(exc_info.value)


def test_update_campaign_allows_same_coupon_rule_with_aware_datetime(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-aware-dates",
            product_bid="product-growth-aware-dates-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-aware-dates",
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-growth-aware-dates"
        ).one()
        start_at = campaign.start_at.replace(tzinfo=UTC)
        end_at = campaign.end_at.replace(tzinfo=UTC)

    update_admin_billing_campaign(
        app,
        operator_user_bid="operator",
        campaign_bid="campaign-growth-aware-dates",
        payload={
            "name": "Growth launch renamed",
            "note": "",
            "benefit_type": "discount",
            "products": [
                {
                    "product_bid": "product-growth-aware-dates-1",
                    "discount_type": "fixed",
                    "campaign_price_amount": "4900",
                }
            ],
            "start_at": start_at,
            "end_at": end_at,
        },
    )

    with app.app_context():
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-growth-aware-dates"
        ).one()
        assert campaign.start_at.tzinfo is None
        assert campaign.end_at.tzinfo is None


def test_update_campaign_status_blocks_disabling_open_provider_coupon(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-disable-lock",
            product_bid="product-growth-disable-lock-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-disable-lock",
        operator_user_bid="operator",
        provider=provider,
    )

    with pytest.raises(AppError) as exc_info:
        update_admin_billing_campaign_status(
            app,
            operator_user_bid="operator",
            campaign_bid="campaign-growth-disable-lock",
            payload={"enabled": False},
        )

    assert "Stripe" in str(exc_info.value)


def test_update_campaign_status_requires_stripe_sync_before_enabling_global_discount(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-enable-sync-required",
            product_bid="product-growth-enable-sync-required-1",
        )
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-growth-enable-sync-required"
        ).one()
        campaign.enabled = 0
        db.session.add(campaign)
        db.session.commit()

    monkeypatch.setattr(
        billing_campaigns,
        "get_config",
        lambda key, default=None: (
            "stripe" if key == "PAYMENT_CHANNELS_ENABLED" else default
        ),
    )

    with pytest.raises(AppError) as exc_info:
        update_admin_billing_campaign_status(
            app,
            operator_user_bid="operator",
            campaign_bid="campaign-growth-enable-sync-required",
            payload={"enabled": True},
        )

    assert "Stripe" in str(exc_info.value)


def test_update_campaign_status_allows_domestic_discount_without_stripe_sync(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-domestic-enable-no-sync",
            product_bid="product-domestic-enable-no-sync-1",
        )
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-domestic-enable-no-sync"
        ).one()
        campaign.enabled = 0
        db.session.add(campaign)
        db.session.commit()

    monkeypatch.setattr(
        billing_campaigns,
        "get_config",
        lambda key, default=None: (
            "pingxx" if key == "PAYMENT_CHANNELS_ENABLED" else default
        ),
    )

    result = update_admin_billing_campaign_status(
        app,
        operator_user_bid="operator",
        campaign_bid="campaign-domestic-enable-no-sync",
        payload={"enabled": True},
    )

    assert result.campaign.enabled is True
