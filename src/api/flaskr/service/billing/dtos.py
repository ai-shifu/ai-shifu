"""Public DTOs for billing and billing-related runtime config surfaces."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from flaskr.common.swagger import register_schema_to_swagger


class BillingBaseDTO(BaseModel):
    """Base DTO with stable JSON serialization for common route responses."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump(mode="python", by_alias=True)

    def __getitem__(self, key: str) -> Any:
        return self.__json__()[key]

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return self.__json__() == other
        return super().__eq__(other)


@register_schema_to_swagger
class BillingRouteItemDTO(BillingBaseDTO):
    method: str
    path: str


@register_schema_to_swagger
class BillingCapabilityEntryPointDTO(BillingBaseDTO):
    kind: str
    method: str | None = None
    path: str | None = None
    name: str | None = None


@register_schema_to_swagger
class BillingCapabilityDTO(BillingBaseDTO):
    key: str
    status: str
    audience: str
    user_visible: bool
    default_enabled: bool
    entry_points: list[BillingCapabilityEntryPointDTO] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


@register_schema_to_swagger
class BillingRouteBootstrapDTO(BillingBaseDTO):
    service: str
    status: str
    path_prefix: str
    creator_routes: list[BillingRouteItemDTO]
    admin_routes: list[BillingRouteItemDTO]
    capabilities: list[BillingCapabilityDTO] = Field(default_factory=list)
    notes: list[str]


@register_schema_to_swagger
class BillingPlanDTO(BillingBaseDTO):
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


@register_schema_to_swagger
class BillingTopupProductDTO(BillingBaseDTO):
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


@register_schema_to_swagger
class BillingCatalogDTO(BillingBaseDTO):
    plans: list[BillingPlanDTO]
    topups: list[BillingTopupProductDTO]


@register_schema_to_swagger
class BillingWalletSnapshotDTO(BillingBaseDTO):
    available_credits: int | float
    reserved_credits: int | float
    lifetime_granted_credits: int | float
    lifetime_consumed_credits: int | float


@register_schema_to_swagger
class BillingSubscriptionDTO(BillingBaseDTO):
    subscription_bid: str
    product_bid: str
    product_code: str
    status: str
    billing_provider: str
    current_period_start_at: str | None = None
    current_period_end_at: str | None = None
    grace_period_end_at: str | None = None
    cancel_at_period_end: bool
    next_product_bid: str | None = None
    last_renewed_at: str | None = None
    last_failed_at: str | None = None


@register_schema_to_swagger
class BillingAlertDTO(BillingBaseDTO):
    code: str
    severity: str
    message_key: str
    message_params: dict[str, Any] | None = None
    action_type: str | None = None
    action_payload: dict[str, Any] | None = None


@register_schema_to_swagger
class BillingTrialOfferDTO(BillingBaseDTO):
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
    granted_at: str | None = None
    expires_at: str | None = None
    welcome_dialog_acknowledged_at: str | None = None


@register_schema_to_swagger
class BillingTrialWelcomeAckDTO(BillingBaseDTO):
    acknowledged: bool
    acknowledged_at: str | None = None


@register_schema_to_swagger
class BillingOverviewDTO(BillingBaseDTO):
    creator_bid: str
    wallet: BillingWalletSnapshotDTO
    subscription: BillingSubscriptionDTO | None = None
    billing_alerts: list[BillingAlertDTO]
    trial_offer: BillingTrialOfferDTO


@register_schema_to_swagger
class BillingEntitlementsDTO(BillingBaseDTO):
    branding_enabled: bool
    custom_domain_enabled: bool
    priority_class: str
    analytics_tier: str
    support_tier: str


@register_schema_to_swagger
class BillingWalletBucketDTO(BillingBaseDTO):
    wallet_bucket_bid: str
    category: str
    source_type: str
    source_bid: str
    available_credits: int | float
    effective_from: str
    effective_to: str | None = None
    priority: int
    status: str


@register_schema_to_swagger
class BillingWalletBucketListDTO(BillingBaseDTO):
    items: list[BillingWalletBucketDTO]


@register_schema_to_swagger
class BillingMetricBreakdownDTO(BillingBaseDTO):
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
    billing_metric: str
    billing_metric_code: int | None = None
    consumed_credits: int | float


@register_schema_to_swagger
class BillingBucketBreakdownDTO(BillingBaseDTO):
    wallet_bucket_bid: str
    bucket_category: str
    source_type: str
    source_bid: str
    consumed_credits: int | float
    effective_from: str | None = None
    effective_to: str | None = None
    metric_breakdown: list[BillingBucketMetricBreakdownDTO] = Field(
        default_factory=list
    )


@register_schema_to_swagger
class BillingLedgerMetadataDTO(BillingBaseDTO):
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
    ledger_bid: str
    wallet_bucket_bid: str
    entry_type: str
    source_type: str
    source_bid: str
    idempotency_key: str
    amount: int | float
    balance_after: int | float
    expires_at: str | None = None
    consumable_from: str | None = None
    metadata: BillingLedgerMetadataDTO | dict[str, Any]
    created_at: str


@register_schema_to_swagger
class BillingLedgerPageDTO(BillingBaseDTO):
    items: list[BillingLedgerItemDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingDailyUsageMetricDTO(BillingBaseDTO):
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
    window_started_at: str
    window_ended_at: str


@register_schema_to_swagger
class BillingDailyUsageMetricsPageDTO(BillingBaseDTO):
    items: list[BillingDailyUsageMetricDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingDailyLedgerSummaryDTO(BillingBaseDTO):
    daily_ledger_summary_bid: str
    stat_date: str
    entry_type: str
    source_type: str
    amount: int | float
    entry_count: int
    window_started_at: str
    window_ended_at: str


@register_schema_to_swagger
class BillingDailyLedgerSummaryPageDTO(BillingBaseDTO):
    items: list[BillingDailyLedgerSummaryDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingRenewalEventDTO(BillingBaseDTO):
    renewal_event_bid: str
    event_type: str
    status: str
    scheduled_at: str | None = None
    processed_at: str | None = None
    attempt_count: int
    last_error: str
    payload: dict[str, Any] | None = None


@register_schema_to_swagger
class BillingOrderSummaryDTO(BillingBaseDTO):
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
    created_at: str
    paid_at: str | None = None


@register_schema_to_swagger
class BillingOrderDetailDTO(BillingOrderSummaryDTO):
    metadata: dict[str, Any] | None = None
    failure_code: str = ""
    refunded_at: str | None = None
    failed_at: str | None = None


@register_schema_to_swagger
class BillingOrdersPageDTO(BillingBaseDTO):
    items: list[BillingOrderSummaryDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingCheckoutResultDTO(BillingBaseDTO):
    bill_order_bid: str
    provider: str
    payment_mode: str
    status: str
    redirect_url: str | None = None
    checkout_session_id: str | None = None
    payment_payload: dict[str, Any] | None = None


@register_schema_to_swagger
class BillingOrderSyncResultDTO(BillingBaseDTO):
    bill_order_bid: str
    status: str


@register_schema_to_swagger
class BillingRefundResultDTO(BillingBaseDTO):
    bill_order_bid: str
    provider: str
    status: str
    refund_reference_id: str | None = None


@register_schema_to_swagger
class AdminBillingSubscriptionDTO(BillingSubscriptionDTO):
    creator_bid: str
    next_product_code: str = ""
    wallet: BillingWalletSnapshotDTO
    latest_renewal_event: BillingRenewalEventDTO | None = None
    has_attention: bool


@register_schema_to_swagger
class BillingSubscriptionsPageDTO(BillingBaseDTO):
    items: list[AdminBillingSubscriptionDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class AdminBillingEntitlementDTO(BillingEntitlementsDTO):
    creator_bid: str
    source_kind: str
    source_type: str = ""
    source_bid: str | None = None
    product_bid: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    feature_payload: dict[str, Any] = Field(default_factory=dict)


@register_schema_to_swagger
class BillingEntitlementsPageDTO(BillingBaseDTO):
    items: list[AdminBillingEntitlementDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingDomainBindingDTO(BillingBaseDTO):
    domain_binding_bid: str
    creator_bid: str
    host: str
    status: str
    verification_method: str
    verification_token: str
    verification_record_name: str
    verification_record_value: str
    last_verified_at: str | None = None
    ssl_status: str
    is_effective: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


@register_schema_to_swagger
class BillingDomainBindingsDTO(BillingBaseDTO):
    creator_bid: str
    custom_domain_enabled: bool
    items: list[BillingDomainBindingDTO]


@register_schema_to_swagger
class BillingDomainBindResultDTO(BillingBaseDTO):
    action: str
    binding: BillingDomainBindingDTO


@register_schema_to_swagger
class AdminBillingDomainBindingDTO(BillingDomainBindingDTO):
    custom_domain_enabled: bool
    has_attention: bool


@register_schema_to_swagger
class BillingDomainAuditsPageDTO(BillingBaseDTO):
    items: list[AdminBillingDomainBindingDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class AdminBillingOrderDTO(BillingOrderSummaryDTO):
    failure_code: str = ""
    failed_at: str | None = None
    refunded_at: str | None = None
    has_attention: bool


@register_schema_to_swagger
class AdminBillingOrdersPageDTO(BillingBaseDTO):
    items: list[AdminBillingOrderDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class AdminBillingDailyUsageMetricDTO(BillingDailyUsageMetricDTO):
    creator_bid: str


@register_schema_to_swagger
class AdminBillingDailyUsageMetricsPageDTO(BillingBaseDTO):
    items: list[AdminBillingDailyUsageMetricDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class AdminBillingDailyLedgerSummaryDTO(BillingDailyLedgerSummaryDTO):
    creator_bid: str


@register_schema_to_swagger
class AdminBillingDailyLedgerSummaryPageDTO(BillingBaseDTO):
    items: list[AdminBillingDailyLedgerSummaryDTO]
    page: int
    page_count: int
    page_size: int
    total: int


@register_schema_to_swagger
class BillingWalletRefDTO(BillingBaseDTO):
    wallet_bid: str
    available_credits: int | float
    reserved_credits: int | float


@register_schema_to_swagger
class BillingLedgerAdjustResultDTO(BillingBaseDTO):
    status: str
    adjustment_bid: str | None = None
    creator_bid: str | None = None
    amount: int | float
    wallet: BillingWalletRefDTO | None = None
    wallet_bucket_bids: list[str] = Field(default_factory=list)
    ledger_bids: list[str] = Field(default_factory=list)


class RuntimeLocalizedUrlDTO(BillingBaseDTO):
    zh_cn: str = Field(alias="zh-CN")
    en_us: str = Field(alias="en-US")


class RuntimeLegalUrlsDTO(BillingBaseDTO):
    agreement: RuntimeLocalizedUrlDTO
    privacy: RuntimeLocalizedUrlDTO


class RuntimeBillingEntitlementsDTO(BillingEntitlementsDTO):
    pass


class RuntimeBillingBrandingDTO(BillingBaseDTO):
    logo_wide_url: str | None = None
    logo_square_url: str | None = None
    favicon_url: str | None = None
    home_url: str | None = None


class RuntimeBillingDomainDTO(BillingBaseDTO):
    request_host: str | None = None
    matched: bool
    is_custom_domain: bool
    creator_bid: str | None = None
    domain_binding_bid: str | None = None
    host: str | None = None
    binding_status: str | None = None


class RuntimeBillingContextDTO(BillingBaseDTO):
    entitlements: RuntimeBillingEntitlementsDTO
    branding: RuntimeBillingBrandingDTO
    domain: RuntimeBillingDomainDTO


class RuntimeConfigDTO(BillingBaseDTO):
    courseId: str
    defaultLlmModel: str
    wechatAppId: str
    enableWechatCode: bool
    billingEnabled: bool
    billingCreditPrecision: int
    stripePublishableKey: str
    stripeEnabled: bool
    paymentChannels: list[str]
    payOrderExpireSeconds: int
    alwaysShowLessonTree: bool
    logoWideUrl: str
    logoSquareUrl: str
    faviconUrl: str
    umamiScriptSrc: str
    umamiWebsiteId: str
    enableEruda: bool
    loginMethodsEnabled: list[str]
    defaultLoginMethod: str
    googleOauthRedirect: str
    homeUrl: str
    currencySymbol: str
    legalUrls: RuntimeLegalUrlsDTO
    genMdfApiUrl: str
    entitlements: RuntimeBillingEntitlementsDTO
    branding: RuntimeBillingBrandingDTO
    domain: RuntimeBillingDomainDTO
