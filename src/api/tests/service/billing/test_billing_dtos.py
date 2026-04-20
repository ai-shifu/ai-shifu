from __future__ import annotations

from decimal import Decimal

from flaskr.service.billing.dtos import (
    BillingAlertDTO,
    BillingBucketBreakdownDTO,
    BillingBucketMetricBreakdownDTO,
    BillingLedgerItemDTO,
    BillingLedgerMetadataDTO,
    BillingMetricBreakdownDTO,
    BillingOverviewDTO,
    BillingSubscriptionDTO,
    BillingTrialOfferDTO,
    BillingWalletBucketListDTO,
    BillingWalletBucketDTO,
    BillingWalletSnapshotDTO,
    RuntimeBillingBrandingDTO,
    RuntimeBillingContextDTO,
    RuntimeBillingDomainDTO,
    RuntimeBillingEntitlementsDTO,
    RuntimeConfigDTO,
    RuntimeLegalUrlsDTO,
    RuntimeLocalizedUrlDTO,
)


def test_billing_dto_json_serializes_nested_models_and_decimal_inputs() -> None:
    dto = BillingOverviewDTO(
        creator_bid="creator-1",
        wallet=BillingWalletSnapshotDTO(
            available_credits=Decimal("12.5000000000"),
            reserved_credits=Decimal("1.0000000000"),
            lifetime_granted_credits=Decimal("30.0000000000"),
            lifetime_consumed_credits=Decimal("17.5000000000"),
        ),
        subscription=BillingSubscriptionDTO(
            subscription_bid="sub-1",
            product_bid="bill-product-plan-monthly",
            product_code="plan-monthly",
            status="active",
            billing_provider="stripe",
            current_period_start_at="2026-04-01T00:00:00+00:00",
            current_period_end_at="2026-05-01T00:00:00+00:00",
            grace_period_end_at=None,
            cancel_at_period_end=False,
            next_product_bid=None,
            last_renewed_at="2026-04-01T00:00:00+00:00",
            last_failed_at=None,
        ),
        billing_alerts=[
            BillingAlertDTO(
                code="low_balance",
                severity="warning",
                message_key="module.billing.alert.lowBalance",
                message_params={"remaining": 12.5},
                action_type="checkout_topup",
                action_payload={"target": "topup"},
            )
        ],
        trial_offer=BillingTrialOfferDTO(
            enabled=True,
            status="granted",
            product_bid="bill-product-plan-trial",
            product_code="creator-plan-trial",
            display_name="module.billing.package.free.title",
            description="module.billing.package.free.description",
            currency="CNY",
            price_amount=0,
            credit_amount=100,
            highlights=["module.billing.package.features.free.publish"],
            valid_days=15,
            starts_on_first_grant=True,
            granted_at="2026-04-09T00:00:00+00:00",
            expires_at="2026-04-24T00:00:00+00:00",
            welcome_dialog_acknowledged_at="2026-04-10T00:00:00+00:00",
        ),
    )

    payload = dto.__json__()

    assert payload["wallet"]["available_credits"] == 12.5
    assert payload["subscription"]["status"] == "active"
    assert payload["billing_alerts"][0]["action_payload"] == {"target": "topup"}
    assert payload["trial_offer"]["status"] == "granted"
    assert payload["trial_offer"]["product_code"] == "creator-plan-trial"
    assert payload["trial_offer"]["welcome_dialog_acknowledged_at"] == (
        "2026-04-10T00:00:00+00:00"
    )


def test_billing_dto_json_serializes_metric_breakdowns_and_bucket_lists() -> None:
    ledger_item = BillingLedgerItemDTO(
        ledger_bid="ledger-1",
        wallet_bucket_bid="bucket-1",
        entry_type="consume",
        source_type="usage",
        source_bid="usage-1",
        idempotency_key="usage-1-bucket-1",
        amount=-2.5,
        balance_after=97.5,
        expires_at=None,
        consumable_from=None,
        metadata=BillingLedgerMetadataDTO(
            usage_bid="usage-1",
            usage_scene="production",
            provider="openai",
            model="gpt-5.4-mini",
            metric_breakdown=[
                BillingMetricBreakdownDTO(
                    billing_metric="llm_output_tokens",
                    billing_metric_code=7303,
                    raw_amount=1234,
                    unit_size=1000,
                    rounded_units=2,
                    credits_per_unit=1.25,
                    rounding_mode="ceil",
                    consumed_credits=2.5,
                )
            ],
            bucket_breakdown=[
                BillingBucketBreakdownDTO(
                    wallet_bucket_bid="bucket-free",
                    bucket_category="free",
                    source_type="subscription",
                    source_bid="sub-1",
                    consumed_credits=1,
                    effective_from="2026-04-01T00:00:00+00:00",
                    effective_to="2026-05-01T00:00:00+00:00",
                    metric_breakdown=[
                        BillingBucketMetricBreakdownDTO(
                            billing_metric="llm_output_tokens",
                            billing_metric_code=7303,
                            consumed_credits=1,
                        )
                    ],
                )
            ],
        ),
        created_at="2026-04-06T10:00:00+00:00",
    )
    bucket_list = BillingWalletBucketListDTO(
        items=[
            BillingWalletBucketDTO(
                wallet_bucket_bid="bucket-1",
                category="subscription",
                source_type="subscription",
                source_bid="sub-1",
                available_credits=97.5,
                effective_from="2026-04-01T00:00:00+00:00",
                effective_to="2026-05-01T00:00:00+00:00",
                priority=20,
                status="active",
            )
        ]
    )

    ledger_payload = ledger_item.__json__()
    bucket_payload = bucket_list.__json__()

    assert ledger_payload["metadata"]["metric_breakdown"][0]["billing_metric"] == (
        "llm_output_tokens"
    )
    assert (
        ledger_payload["metadata"]["bucket_breakdown"][0]["wallet_bucket_bid"]
        == "bucket-free"
    )
    assert bucket_payload == {
        "items": [
            {
                "wallet_bucket_bid": "bucket-1",
                "category": "subscription",
                "source_type": "subscription",
                "source_bid": "sub-1",
                "available_credits": 97.5,
                "effective_from": "2026-04-01T00:00:00+00:00",
                "effective_to": "2026-05-01T00:00:00+00:00",
                "priority": 20,
                "status": "active",
            }
        ]
    }


def test_runtime_config_dto_json_uses_public_aliases() -> None:
    dto = RuntimeConfigDTO(
        courseId="course-1",
        defaultLlmModel="gpt-5.4",
        wechatAppId="wechat-app-1",
        enableWechatCode=True,
        billingEnabled=True,
        billingCreditPrecision=2,
        stripePublishableKey="pk_test_123",
        stripeEnabled=True,
        paymentChannels=["stripe", "pingxx"],
        payOrderExpireSeconds=600,
        alwaysShowLessonTree=False,
        logoWideUrl="https://cdn.example.com/logo-wide.png",
        logoSquareUrl="https://cdn.example.com/logo-square.png",
        faviconUrl="https://cdn.example.com/favicon.ico",
        umamiScriptSrc="",
        umamiWebsiteId="",
        enableEruda=False,
        loginMethodsEnabled=["phone"],
        defaultLoginMethod="phone",
        googleOauthRedirect="https://example.com/login/google-callback",
        homeUrl="/",
        currencySymbol="¥",
        legalUrls=RuntimeLegalUrlsDTO(
            agreement=RuntimeLocalizedUrlDTO(
                **{
                    "zh-CN": "/legal/agreement/zh",
                    "en-US": "/legal/agreement/en",
                }
            ),
            privacy=RuntimeLocalizedUrlDTO(
                **{
                    "zh-CN": "/legal/privacy/zh",
                    "en-US": "/legal/privacy/en",
                }
            ),
        ),
        genMdfApiUrl="",
        entitlements=RuntimeBillingEntitlementsDTO(
            branding_enabled=True,
            custom_domain_enabled=True,
            priority_class="priority",
            analytics_tier="advanced",
            support_tier="business_hours",
        ),
        branding=RuntimeBillingBrandingDTO(
            logo_wide_url="https://cdn.example.com/logo-wide.png",
            logo_square_url="https://cdn.example.com/logo-square.png",
            favicon_url="https://cdn.example.com/favicon.ico",
            home_url="https://creator.example.com",
        ),
        domain=RuntimeBillingDomainDTO(
            request_host="creator.example.com",
            matched=True,
            is_custom_domain=True,
            creator_bid="creator-1",
            domain_binding_bid="binding-1",
            host="creator.example.com",
            binding_status="verified",
        ),
    )

    payload = dto.__json__()
    context = RuntimeBillingContextDTO(
        entitlements=dto.entitlements,
        branding=dto.branding,
        domain=dto.domain,
    )

    assert payload["legalUrls"]["agreement"] == {
        "zh-CN": "/legal/agreement/zh",
        "en-US": "/legal/agreement/en",
    }
    assert payload["billingEnabled"] is True
    assert payload["billingCreditPrecision"] == 2
    assert payload["branding"]["home_url"] == "https://creator.example.com"
    assert context.__json__()["domain"]["is_custom_domain"] is True
