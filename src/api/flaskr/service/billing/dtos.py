"""Public DTOs for billing and billing-related runtime config surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flaskr.common.swagger import register_schema_to_swagger
from pydantic import BaseModel, ConfigDict, Field


class BillingBaseDTO(BaseModel):
    """Base DTO with stable JSON serialization for common route responses."""

    __hash__ = None

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def __json__(self: object) -> dict[str, Any]:
        """Return aliased model fields as JSON-compatible data."""
        return self.model_dump(mode="python", by_alias=True)

    def __getitem__(self: object, key: str) -> Any:
        """Return a serialized DTO field by key."""
        return self.__json__()[key]

    def __eq__(self: object, other: object) -> bool:
        """Compare the DTO with a serialized mapping or model."""
        if isinstance(other, dict):
            return self.__json__() == other
        return super().__eq__(other)


@register_schema_to_swagger
class BillingRouteItemDTO(BillingBaseDTO):
    """Represent the billing route item API payload."""

    method: str
    path: str


@register_schema_to_swagger
class BillingCapabilityEntryPointDTO(BillingBaseDTO):
    """Represent the billing capability entry point API payload."""

    kind: str
    method: str | None = None
    path: str | None = None
    name: str | None = None


@register_schema_to_swagger
class BillingCapabilityDTO(BillingBaseDTO):
    """Represent the billing capability API payload."""

    key: str
    status: str
    audience: str
    user_visible: bool
    default_enabled: bool
    entry_points: list[BillingCapabilityEntryPointDTO] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


@register_schema_to_swagger
class BillingRouteBootstrapDTO(BillingBaseDTO):
    """Represent the billing route bootstrap API payload."""

    service: str
    status: str
    path_prefix: str
    creator_routes: list[BillingRouteItemDTO]
    admin_routes: list[BillingRouteItemDTO]
    capabilities: list[BillingCapabilityDTO] = Field(default_factory=list)
    notes: list[str]


@register_schema_to_swagger
class BillingCatalogCampaignDTO(BillingBaseDTO):
    """Represent the billing catalog campaign API payload."""

    campaign_bid: str
    benefit_type: str
    discount_type: str | None = None
    discount_amount: int = 0
    discount_percent: int | float = 0
    campaign_price_amount: int = 0
    bonus_credit_amount: int | float = 0


@register_schema_to_swagger
class BillingPlanDTO(BillingBaseDTO):
    """Represent the billing plan API payload."""

    product_bid: str
    product_code: str
    product_type: str
    display_name: str
    description: str
    currency: str
    price_amount: int
    credit_amount: int | float
    highlights: list[str] = Field(default_factory=list)
    status_badge_key: str | None = None
    billing_interval: str
    billing_interval_count: int
    auto_renew_enabled: bool
    plan_tier: int | None = None
    campaign: BillingCatalogCampaignDTO | None = None


@register_schema_to_swagger
class BillingTopupProductDTO(BillingBaseDTO):
    """Represent the billing topup product API payload."""

    product_bid: str
    product_code: str
    product_type: str
    display_name: str
    description: str
    currency: str
    price_amount: int
    credit_amount: int | float
    highlights: list[str] = Field(default_factory=list)
    status_badge_key: str | None = None
    campaign: BillingCatalogCampaignDTO | None = None


@register_schema_to_swagger
class BillingCatalogDTO(BillingBaseDTO):
    """Represent the billing catalog API payload."""

    plans: list[BillingPlanDTO]
    topups: list[BillingTopupProductDTO]


@register_schema_to_swagger
class BillingWalletSnapshotDTO(BillingBaseDTO):
    """Represent the billing wallet snapshot API payload."""

    available_credits: int | float
    reserved_credits: int | float
    lifetime_granted_credits: int | float
    lifetime_consumed_credits: int | float


@register_schema_to_swagger
class BillingSubscriptionDTO(BillingBaseDTO):
    """Represent the billing subscription API payload."""

    subscription_bid: str
    product_bid: str
    product_code: str
    status: str
    billing_provider: str
    current_period_start_at: datetime | None = None
    current_period_end_at: datetime | None = None
    grace_period_end_at: datetime | None = None
    cancel_at_period_end: bool
    next_product_bid: str | None = None
    last_renewed_at: datetime | None = None
    last_failed_at: datetime | None = None


@register_schema_to_swagger
class BillingAlertDTO(BillingBaseDTO):
    """Represent the billing alert API payload."""

    code: str
    severity: str
    message_key: str
    message_params: dict[str, Any] | None = None
    action_type: str | None = None
    action_payload: dict[str, Any] | None = None


@register_schema_to_swagger
class BillingTrialOfferDTO(BillingBaseDTO):
    """Represent the billing trial offer API payload."""

    enabled: bool
    status: str
    product_bid: str
    product_code: str
    display_name: str
    description: str
    currency: str
    price_amount: int
    credit_amount: int | float
    highlights: list[str] = Field(default_factory=list)
    valid_days: int
    starts_on_first_grant: bool
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    welcome_dialog_acknowledged_at: datetime | None = None


@register_schema_to_swagger
class BillingTrialWelcomeAckDTO(BillingBaseDTO):
    """Represent the billing trial welcome ack API payload."""

    acknowledged: bool
    acknowledged_at: datetime | None = None


@register_schema_to_swagger
class BillingOverviewDTO(BillingBaseDTO):
    """Represent the billing overview API payload."""

    creator_bid: str
    wallet: BillingWalletSnapshotDTO
    subscription: BillingSubscriptionDTO | None = None
    billing_alerts: list[BillingAlertDTO]
    trial_offer: BillingTrialOfferDTO
    credit_status: str = "normal"
    debug_allowed: bool = True
    softlimit_threshold: str | None = None


@register_schema_to_swagger
class BillingEntitlementsDTO(BillingBaseDTO):
    """Represent the billing entitlements API payload."""

    branding_enabled: bool
    custom_domain_enabled: bool
    custom_wechat_enabled: bool = False
    custom_payment_enabled: bool = False
    priority_class: str
    analytics_tier: str
    support_tier: str


@register_schema_to_swagger
class BillingWalletBucketDTO(BillingBaseDTO):
    """Represent the billing wallet bucket API payload."""

    wallet_bucket_bid: str
    category: str
    credit_asset_kind: str = "unknown"
    source_type: str
    source_bid: str
    available_credits: int | float
    effective_from: datetime | None
    effective_to: datetime | None = None
    priority: int
    status: str


@register_schema_to_swagger
class BillingWalletBucketListDTO(BillingBaseDTO):
    """Represent the billing wallet bucket list API payload."""

    items: list[BillingWalletBucketDTO]


@register_schema_to_swagger
class BillingMetricBreakdownDTO(BillingBaseDTO):
    """Represent the billing metric breakdown API payload."""

    billing_metric: str
    billing_metric_code: int | None = None
    raw_amount: int
    unit_size: int
    rounded_units: int | float | None = None
    credits_per_unit: int | float
    rounding_mode: str
    consumed_credits: int | float


@register_schema_to_swagger
class BillingBucketMetricBreakdownDTO(BillingBaseDTO):
    """Represent the billing bucket metric breakdown API payload."""

    billing_metric: str
    billing_metric_code: int | None = None
    consumed_credits: int | float


@register_schema_to_swagger
class BillingBucketBreakdownDTO(BillingBaseDTO):
    """Represent the billing bucket breakdown API payload."""

    wallet_bucket_bid: str
    bucket_category: str
    source_type: str
    source_bid: str
    consumed_credits: int | float
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    metric_breakdown: list[BillingBucketMetricBreakdownDTO] = Field(
        default_factory=list
    )


@register_schema_to_swagger
class BillingLedgerMetadataDTO(BillingBaseDTO):
    """Represent the billing ledger metadata API payload."""

    usage_bid: str | None = None
    usage_scene: str | None = None
    course_name: str | None = None
    user_identify: str | None = None
    provider: str | None = None
    model: str | None = None
    metric_breakdown: list[BillingMetricBreakdownDTO] = Field(default_factory=list)
    bucket_breakdown: list[BillingBucketBreakdownDTO] = Field(default_factory=list)


@register_schema_to_swagger
class BillingLedgerItemDTO(BillingBaseDTO):
    """Represent the billing ledger item API payload."""

    ledger_bid: str
    wallet_bucket_bid: str
    entry_type: str
    source_type: str
    source_bid: str
    credit_asset_kind: str = "unknown"
    idempotency_key: str
    amount: int | float
    balance_after: int | float
    expires_at: datetime | None = None
    consumable_from: datetime | None = None
    metadata: BillingLedgerMetadataDTO | dict[str, Any]
    created_at: datetime | None


@register_schema_to_swagger
class BillingLedgerPageDTO(BillingBaseDTO):
    """Represent the billing ledger page API payload."""

    items: list[BillingLedgerItemDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingDailyUsageMetricDTO(BillingBaseDTO):
    """Represent the billing daily usage metric API payload."""

    daily_usage_metric_bid: str
    stat_date: str
    shifu_bid: str
    usage_scene: str
    usage_type: str
    provider: str
    model: str
    billing_metric: str
    raw_amount: int
    record_count: int
    consumed_credits: int | float
    window_started_at: datetime | None
    window_ended_at: datetime | None


@register_schema_to_swagger
class BillingDailyUsageMetricsPageDTO(BillingBaseDTO):
    """Represent the billing daily usage metrics page API payload."""

    items: list[BillingDailyUsageMetricDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingDailyLedgerSummaryDTO(BillingBaseDTO):
    """Represent the billing daily ledger summary API payload."""

    daily_ledger_summary_bid: str
    stat_date: str
    entry_type: str
    source_type: str
    amount: int | float
    entry_count: int
    window_started_at: datetime | None
    window_ended_at: datetime | None


@register_schema_to_swagger
class BillingDailyLedgerSummaryPageDTO(BillingBaseDTO):
    """Represent the billing daily ledger summary page API payload."""

    items: list[BillingDailyLedgerSummaryDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingRenewalEventDTO(BillingBaseDTO):
    """Represent the billing renewal event API payload."""

    renewal_event_bid: str
    event_type: str
    status: str
    scheduled_at: datetime | None = None
    processed_at: datetime | None = None
    attempt_count: int
    last_error: str
    payload: dict[str, Any] | None = None


@register_schema_to_swagger
class BillingOrderSummaryDTO(BillingBaseDTO):
    """Represent the billing order summary API payload."""

    bill_order_bid: str
    creator_bid: str
    product_bid: str
    subscription_bid: str | None = None
    order_type: str
    status: str
    payment_provider: str
    payment_mode: str
    payable_amount: int
    paid_amount: int
    currency: str
    provider_reference_id: str
    failure_message: str
    created_at: datetime | None
    paid_at: datetime | None = None


@register_schema_to_swagger
class BillingOrderDetailDTO(BillingOrderSummaryDTO):
    """Represent the billing order detail API payload."""

    metadata: dict[str, Any] | None = None
    failure_code: str = ""
    refunded_at: datetime | None = None
    failed_at: datetime | None = None


@register_schema_to_swagger
class BillingOrdersPageDTO(BillingBaseDTO):
    """Represent the billing orders page API payload."""

    items: list[BillingOrderSummaryDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingCheckoutResultDTO(BillingBaseDTO):
    """Represent the billing checkout result API payload."""

    bill_order_bid: str
    provider: str
    payment_mode: str
    status: str
    reused_existing_order: bool = False
    checkout_type: str | None = None
    effective_mode: str | None = None
    current_product_bid: str | None = None
    target_product_bid: str | None = None
    preorder_order_bid: str | None = None
    prepaid_offset_amount: int = 0
    payable_amount: int | None = None
    currency: str = ""
    expires_at: datetime | None = None
    expires_in_seconds: int | None = None
    campaign: BillingCatalogCampaignDTO | None = None
    redirect_url: str | None = None
    checkout_session_id: str | None = None
    payment_payload: dict[str, Any] | None = None


@register_schema_to_swagger
class BillingOrderSyncResultDTO(BillingBaseDTO):
    """Represent the billing order sync result API payload."""

    bill_order_bid: str
    status: str
    expires_at: datetime | None = None
    expires_in_seconds: int | None = None


@register_schema_to_swagger
class BillingRefundResultDTO(BillingBaseDTO):
    """Represent the billing refund result API payload."""

    bill_order_bid: str
    provider: str
    status: str
    refund_reference_id: str | None = None


@register_schema_to_swagger
class AdminBillingSubscriptionDTO(BillingSubscriptionDTO):
    """Represent the admin billing subscription API payload."""

    creator_bid: str
    creator_identify: str = ""
    creator_mobile: str = ""
    creator_email: str = ""
    creator_nickname: str = ""
    product_name_key: str = ""
    next_product_code: str = ""
    next_product_name_key: str = ""
    wallet: BillingWalletSnapshotDTO
    latest_renewal_event: BillingRenewalEventDTO | None = None
    has_attention: bool


@register_schema_to_swagger
class BillingSubscriptionsPageDTO(BillingBaseDTO):
    """Represent the billing subscriptions page API payload."""

    items: list[AdminBillingSubscriptionDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class AdminBillingEntitlementDTO(BillingEntitlementsDTO):
    """Represent the admin billing entitlement API payload."""

    creator_bid: str
    creator_identify: str = ""
    creator_mobile: str = ""
    creator_email: str = ""
    creator_nickname: str = ""
    source_kind: str
    source_type: str = ""
    source_bid: str | None = None
    product_bid: str | None = None
    product_name_key: str = ""
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    feature_payload: dict[str, Any] = Field(default_factory=dict)


@register_schema_to_swagger
class BillingEntitlementsPageDTO(BillingBaseDTO):
    """Represent the billing entitlements page API payload."""

    items: list[AdminBillingEntitlementDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingDomainBindingDTO(BillingBaseDTO):
    """Represent the billing domain binding API payload."""

    domain_binding_bid: str
    creator_bid: str
    host: str
    status: str
    verification_method: str
    verification_token: str
    verification_record_name: str
    verification_record_value: str
    last_verified_at: datetime | None = None
    ssl_status: str
    is_effective: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


@register_schema_to_swagger
class BillingDomainBindingsDTO(BillingBaseDTO):
    """Represent the billing domain bindings API payload."""

    creator_bid: str
    custom_domain_enabled: bool
    items: list[BillingDomainBindingDTO]


@register_schema_to_swagger
class BillingDomainBindResultDTO(BillingBaseDTO):
    """Represent the billing domain bind result API payload."""

    action: str
    binding: BillingDomainBindingDTO


@register_schema_to_swagger
class AdminBillingOrderDTO(BillingOrderSummaryDTO):
    """Represent the admin billing order API payload."""

    creator_identify: str = ""
    creator_mobile: str = ""
    creator_email: str = ""
    creator_nickname: str = ""
    product_name_key: str = ""
    product_credit_amount: int | float = 0
    failure_code: str = ""
    failed_at: datetime | None = None
    refunded_at: datetime | None = None
    has_attention: bool


@register_schema_to_swagger
class AdminBillingCampaignProductOptionDTO(BillingBaseDTO):
    """Represent the admin billing campaign product option API payload."""

    product_bid: str
    product_code: str
    product_type: str
    display_name: str
    description: str
    currency: str
    price_amount: int
    credit_amount: int | float
    billing_interval: str = "none"
    billing_interval_count: int = 0
    campaign_discount_type: str | None = None
    campaign_discount_amount: int = 0
    campaign_discount_percent: int | float = 0
    campaign_price_amount: int = 0
    campaign_bonus_credit_amount: int | float = 0


@register_schema_to_swagger
class AdminBillingCampaignProductOptionsDTO(BillingBaseDTO):
    """Represent the admin billing campaign product options API payload."""

    plans: list[AdminBillingCampaignProductOptionDTO] = Field(default_factory=list)
    topups: list[AdminBillingCampaignProductOptionDTO] = Field(default_factory=list)


@register_schema_to_swagger
class AdminBillingCampaignDTO(BillingBaseDTO):
    """Represent the admin billing campaign API payload."""

    campaign_bid: str
    name: str
    note: str = ""
    benefit_type: str
    discount_type: str | None = None
    discount_amount: int = 0
    discount_percent: int | float = 0
    bonus_credit_amount: int | float = 0
    product_count: int = 0
    product_types: list[str] = Field(default_factory=list)
    product_names: list[str] = Field(default_factory=list)
    has_custom_product_rules: bool = False
    computed_status: str
    hit_order_count: int = 0
    start_at: datetime | None
    end_at: datetime | None
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None


@register_schema_to_swagger
class AdminBillingCampaignDetailDTO(BillingBaseDTO):
    """Represent the admin billing campaign detail API payload."""

    campaign: AdminBillingCampaignDTO
    products: list[AdminBillingCampaignProductOptionDTO] = Field(default_factory=list)
    created_user_bid: str = ""
    updated_user_bid: str = ""


@register_schema_to_swagger
class AdminBillingCampaignsPageDTO(BillingBaseDTO):
    """Represent the admin billing campaigns page API payload."""

    items: list[AdminBillingCampaignDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class OperatorCreditOrderGrantDTO(BillingBaseDTO):
    """Represent the operator credit order grant API payload."""

    granted_credits: int | float
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_type: str
    source_bid: str


@register_schema_to_swagger
class OperatorCreditOrderDTO(BillingBaseDTO):
    """Represent the operator credit order API payload."""

    bill_order_bid: str
    creator_bid: str
    creator_identify: str = ""
    creator_mobile: str = ""
    creator_email: str = ""
    creator_nickname: str = ""
    credit_order_kind: str
    product_bid: str
    product_code: str
    product_type: str
    product_name_key: str
    credit_amount: int | float
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    order_type: str
    status: str
    payment_provider: str
    payment_channel: str
    payable_amount: int
    paid_amount: int
    currency: str
    provider_reference_id: str
    failure_code: str = ""
    failure_message: str = ""
    created_at: datetime | None
    paid_at: datetime | None = None
    failed_at: datetime | None = None
    refunded_at: datetime | None = None
    has_attention: bool


@register_schema_to_swagger
class OperatorCreditOrderOverviewDTO(BillingBaseDTO):
    """Represent the operator credit order overview API payload."""

    total_order_count: int = 0
    paid_order_count: int = 0
    pending_order_count: int = 0
    refunded_order_count: int = 0
    closed_order_count: int = 0
    canceled_order_count: int = 0
    available_credit_total: int | float = 0
    paid_amount_total: int = 0
    currency: str = "CNY"
    paid_amount_totals_by_currency: dict[str, int] = Field(default_factory=dict)


@register_schema_to_swagger
class OperatorCreditOrdersPageDTO(BillingBaseDTO):
    """Represent the operator credit orders page API payload."""

    items: list[OperatorCreditOrderDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class OperatorCreditOrderDetailDTO(BillingBaseDTO):
    """Represent the operator credit order detail API payload."""

    order: OperatorCreditOrderDTO
    metadata: dict[str, Any] | None = None
    grant: OperatorCreditOrderGrantDTO | None = None


@register_schema_to_swagger
class AdminBillingDailyUsageMetricDTO(BillingDailyUsageMetricDTO):
    """Represent the admin billing daily usage metric API payload."""

    creator_bid: str
    creator_mobile: str = ""
    creator_email: str = ""
    creator_nickname: str = ""


@register_schema_to_swagger
class AdminBillingDailyUsageMetricsPageDTO(BillingBaseDTO):
    """Represent the admin billing daily usage metrics page API payload."""

    items: list[AdminBillingDailyUsageMetricDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class AdminBillingFocusTeacherDTO(BillingBaseDTO):
    """Represent the admin billing focus teacher API payload."""

    creator_bid: str
    creator_mobile: str = ""
    creator_email: str = ""
    creator_nickname: str = ""
    credits_7d: int | float = 0
    credits_30d: int | float = 0
    record_count_7d: int = 0
    active_days_7d: int = 0
    production_credits_30d: int | float = 0
    debug_preview_credits_30d: int | float = 0
    total_credits_30d: int | float = 0
    production_ratio_30d: int | float = 0
    latest_usage_at: datetime | None = None
    attention_reasons: list[str] = Field(default_factory=list)


@register_schema_to_swagger
class AdminBillingFocusTeachersPageDTO(BillingBaseDTO):
    """Represent the admin billing focus teachers page API payload."""

    items: list[AdminBillingFocusTeacherDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class AdminBillingDailyLedgerSummaryDTO(BillingDailyLedgerSummaryDTO):
    """Represent the admin billing daily ledger summary API payload."""

    creator_bid: str


@register_schema_to_swagger
class AdminBillingDailyLedgerSummaryPageDTO(BillingBaseDTO):
    """Represent the admin billing daily ledger summary page API payload."""

    items: list[AdminBillingDailyLedgerSummaryDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingWalletRefDTO(BillingBaseDTO):
    """Represent the billing wallet ref API payload."""

    wallet_bid: str
    available_credits: int | float
    reserved_credits: int | float


@register_schema_to_swagger
class BillingLedgerAdjustResultDTO(BillingBaseDTO):
    """Represent the billing ledger adjust result API payload."""

    status: str
    adjustment_bid: str | None = None
    creator_bid: str | None = None
    amount: int | float
    wallet: BillingWalletRefDTO | None = None
    wallet_bucket_bids: list[str] = Field(default_factory=list)
    ledger_bids: list[str] = Field(default_factory=list)


class RuntimeLocalizedUrlDTO(BillingBaseDTO):
    """Represent the runtime localized URL API payload."""

    zh_cn: str = Field(alias="zh-CN")
    en_us: str = Field(alias="en-US")
    fr_fr: str = Field(alias="fr-FR")


class RuntimeLegalUrlsDTO(BillingBaseDTO):
    """Represent the runtime legal urls API payload."""

    agreement: RuntimeLocalizedUrlDTO
    privacy: RuntimeLocalizedUrlDTO


class RuntimeBillingEntitlementsDTO(BillingEntitlementsDTO):
    """Represent the runtime billing entitlements API payload."""


class RuntimeBillingBrandingDTO(BillingBaseDTO):
    """Represent the runtime billing branding API payload."""

    logo_wide_url: str | None = None
    logo_square_url: str | None = None
    favicon_url: str | None = None
    home_url: str | None = None
    contact_us_url: str | None = None


class RuntimeBillingDomainDTO(BillingBaseDTO):
    """Represent the runtime billing domain API payload."""

    request_host: str | None = None
    matched: bool
    is_custom_domain: bool
    creator_bid: str | None = None
    domain_binding_bid: str | None = None
    host: str | None = None
    binding_status: str | None = None


class RuntimeBillingContextDTO(BillingBaseDTO):
    """Represent the runtime billing context API payload."""

    entitlements: RuntimeBillingEntitlementsDTO
    branding: RuntimeBillingBrandingDTO
    domain: RuntimeBillingDomainDTO


class RuntimeConfigDTO(BillingBaseDTO):
    """Represent the runtime config API payload."""

    default_llm_model: str = Field(alias="defaultLlmModel")
    wechat_app_id: str = Field(alias="wechatAppId")
    enable_wechat_code: bool = Field(alias="enableWechatCode")
    billing_enabled: bool = Field(alias="billingEnabled")
    billing_credit_precision: int = Field(alias="billingCreditPrecision")
    stripe_publishable_key: str = Field(alias="stripePublishableKey")
    stripe_enabled: bool = Field(alias="stripeEnabled")
    payment_channels: list[str] = Field(alias="paymentChannels")
    pay_order_expire_seconds: int = Field(alias="payOrderExpireSeconds")
    always_show_lesson_tree: bool = Field(alias="alwaysShowLessonTree")
    logo_wide_url: str = Field(alias="logoWideUrl")
    logo_square_url: str = Field(alias="logoSquareUrl")
    favicon_url: str = Field(alias="faviconUrl")
    umami_script_src: str = Field(alias="umamiScriptSrc")
    umami_website_id: str = Field(alias="umamiWebsiteId")
    enable_eruda: bool = Field(alias="enableEruda")
    login_methods_enabled: list[str] = Field(alias="loginMethodsEnabled")
    default_login_method: str = Field(alias="defaultLoginMethod")
    google_oauth_redirect: str = Field(alias="googleOauthRedirect")
    home_url: str = Field(alias="homeUrl")
    contact_us_url: str = Field(alias="contactUsUrl")
    official_site_url: str = Field(alias="officialSiteUrl")
    currency_symbol: str = Field(alias="currencySymbol")
    legal_urls: RuntimeLegalUrlsDTO = Field(alias="legalUrls")
    entitlements: RuntimeBillingEntitlementsDTO
    branding: RuntimeBillingBrandingDTO
    domain: RuntimeBillingDomainDTO
    customization_capabilities: dict[str, bool] = Field(
        default_factory=dict,
        alias="customizationCapabilities",
    )
    payment_configuration_ready: bool = Field(
        default=False,
        alias="paymentConfigurationReady",
    )
