"""Serialization helpers for billing DTO payloads."""

from __future__ import annotations

from typing import Any

from flask import Flask

from flaskr.util.datetime import now_utc

from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)

from .consts import (
    BILLING_DOMAIN_BINDING_STATUS_FAILED,
    BILLING_DOMAIN_BINDING_STATUS_LABELS,
    BILLING_DOMAIN_BINDING_STATUS_PENDING,
    BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
    BILLING_DOMAIN_SSL_STATUS_LABELS,
    BILLING_DOMAIN_VERIFICATION_METHOD_LABELS,
    BILLING_INTERVAL_LABELS,
    BILLING_METRIC_LABELS,
    BILLING_CAMPAIGN_BENEFIT_TYPE_LABELS,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_LABELS,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_LABELS,
    BILLING_PRODUCT_TYPE_LABELS,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_LABELS,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_TYPE_LABELS,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    CREDIT_BUCKET_CATEGORY_LABELS,
    CREDIT_BUCKET_STATUS_LABELS,
    CREDIT_LEDGER_ENTRY_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_LABELS,
)
from .bucket_categories import (
    load_billing_order_type_by_bid,
    resolve_credit_bucket_priority,
    resolve_wallet_bucket_runtime_category,
)
from .models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    BillingDomainBinding,
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .dtos import (
    AdminBillingCampaignDTO,
    AdminBillingCampaignDetailDTO,
    AdminBillingCampaignProductOptionDTO,
    AdminBillingDailyLedgerSummaryDTO,
    AdminBillingDailyUsageMetricDTO,
    AdminBillingDomainBindingDTO,
    AdminBillingEntitlementDTO,
    AdminBillingOrderDTO,
    AdminBillingSubscriptionDTO,
    BillingAlertDTO,
    BillingCatalogCampaignDTO,
    BillingDailyLedgerSummaryDTO,
    BillingDailyUsageMetricDTO,
    BillingLedgerItemDTO,
    BillingOrderSummaryDTO,
    OperatorCreditOrderDTO,
    OperatorCreditOrderGrantDTO,
    BillingPlanDTO,
    BillingRenewalEventDTO,
    BillingSubscriptionDTO,
    BillingTopupProductDTO,
    BillingWalletBucketDTO,
    BillingWalletSnapshotDTO,
)
from .primitives import (
    credit_decimal_to_number,
    normalize_bid,
    normalize_json_object,
)
from .queries import load_product_code_map

_USAGE_SCENE_LABELS = {
    BILL_USAGE_SCENE_DEBUG: "debug",
    BILL_USAGE_SCENE_PREVIEW: "preview",
    BILL_USAGE_SCENE_PROD: "production",
}

_USAGE_TYPE_LABELS = {
    BILL_USAGE_TYPE_LLM: "llm",
    BILL_USAGE_TYPE_TTS: "tts",
}


def serialize_catalog_campaign(
    payload: dict[str, Any],
) -> BillingCatalogCampaignDTO | None:
    if not payload:
        return None
    return BillingCatalogCampaignDTO(
        campaign_bid=str(payload.get("campaign_bid") or ""),
        benefit_type=str(payload.get("benefit_type") or ""),
        discount_type=(str(payload.get("discount_type") or "") or None),
        discount_amount=int(payload.get("discount_amount") or 0),
        discount_percent=credit_decimal_to_number(payload.get("discount_percent") or 0),
        campaign_price_amount=int(payload.get("campaign_price_amount") or 0),
        bonus_credit_amount=credit_decimal_to_number(
            payload.get("bonus_credit_amount") or 0
        ),
    )


def serialize_admin_campaign_product_option(
    row: BillingProduct,
    *,
    binding: BillingCampaignProduct | None = None,
) -> AdminBillingCampaignProductOptionDTO:
    payload = serialize_product(row)
    return AdminBillingCampaignProductOptionDTO(
        product_bid=row.product_bid,
        product_code=row.product_code,
        product_type=BILLING_PRODUCT_TYPE_LABELS.get(row.product_type, ""),
        display_name=row.display_name_i18n_key,
        description=row.description_i18n_key,
        currency=row.currency,
        price_amount=int(row.price_amount or 0),
        credit_amount=credit_decimal_to_number(row.credit_amount),
        billing_interval=getattr(payload, "billing_interval", "none") or "none",
        billing_interval_count=int(getattr(payload, "billing_interval_count", 0) or 0),
        campaign_discount_type=(
            BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS.get(binding.discount_type, "") or None
        )
        if binding is not None
        else None,
        campaign_discount_amount=int(getattr(binding, "discount_amount", 0) or 0),
        campaign_discount_percent=credit_decimal_to_number(
            getattr(binding, "discount_percent", 0) or 0
        ),
        campaign_price_amount=int(getattr(binding, "campaign_price_amount", 0) or 0),
        campaign_bonus_credit_amount=credit_decimal_to_number(
            getattr(binding, "bonus_credit_amount", 0) or 0
        ),
    )


def serialize_admin_campaign(
    app: Flask,
    row: BillingCampaign,
    *,
    product_names: list[str],
    product_types: list[str],
    hit_order_count: int,
    has_custom_product_rules: bool = False,
    discount_type_code: int | None = None,
    discount_amount: int | None = None,
    discount_percent: Any | None = None,
    bonus_credit_amount: Any | None = None,
) -> AdminBillingCampaignDTO:
    now = now_utc()
    if not bool(row.enabled):
        computed_status = "inactive"
    elif row.start_at and row.start_at > now:
        computed_status = "upcoming"
    elif row.end_at and row.end_at <= now:
        computed_status = "ended"
    else:
        computed_status = "active"
    resolved_discount_type_code = (
        int(row.discount_type or 0)
        if discount_type_code is None
        else int(discount_type_code or 0)
    )
    resolved_discount_amount = (
        int(row.discount_amount or 0)
        if discount_amount is None
        else int(discount_amount or 0)
    )
    resolved_discount_percent = (
        row.discount_percent if discount_percent is None else discount_percent
    )
    resolved_bonus_credit_amount = (
        row.bonus_credit_amount if bonus_credit_amount is None else bonus_credit_amount
    )
    return AdminBillingCampaignDTO(
        campaign_bid=row.campaign_bid,
        name=str(row.name or ""),
        note=str(row.note or ""),
        benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_LABELS.get(row.benefit_type, ""),
        discount_type=(
            BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS.get(
                resolved_discount_type_code,
                "",
            )
            or None
        ),
        discount_amount=resolved_discount_amount,
        discount_percent=credit_decimal_to_number(resolved_discount_percent),
        bonus_credit_amount=credit_decimal_to_number(resolved_bonus_credit_amount),
        product_count=len(product_names),
        product_types=product_types,
        product_names=product_names,
        has_custom_product_rules=has_custom_product_rules,
        computed_status=computed_status,
        hit_order_count=hit_order_count,
        start_at=row.start_at,
        end_at=row.end_at,
        enabled=bool(row.enabled),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def serialize_admin_campaign_detail(
    campaign: AdminBillingCampaignDTO,
    *,
    products: list[AdminBillingCampaignProductOptionDTO],
    created_user_bid: str,
    updated_user_bid: str,
) -> AdminBillingCampaignDetailDTO:
    return AdminBillingCampaignDetailDTO(
        campaign=campaign,
        products=products,
        created_user_bid=created_user_bid,
        updated_user_bid=updated_user_bid,
    )


def serialize_product(
    row: BillingProduct,
    *,
    campaign_payload: dict[str, Any] | None = None,
) -> BillingPlanDTO | BillingTopupProductDTO:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    badge = metadata.get("badge")
    highlights = metadata.get("highlights")
    payload: dict[str, Any] = {
        "product_bid": row.product_bid,
        "product_code": row.product_code,
        "product_type": BILLING_PRODUCT_TYPE_LABELS.get(row.product_type, ""),
        "display_name": row.display_name_i18n_key,
        "description": row.description_i18n_key,
        "currency": row.currency,
        "price_amount": int(row.price_amount or 0),
        "credit_amount": credit_decimal_to_number(row.credit_amount),
    }
    if isinstance(highlights, list) and highlights:
        payload["highlights"] = [
            str(item) for item in highlights if str(item or "").strip()
        ]
    resolved_campaign_payload = serialize_catalog_campaign(
        campaign_payload
        if isinstance(campaign_payload, dict)
        else (
            metadata.get("campaign")
            if isinstance(metadata.get("campaign"), dict)
            else {}
        )
    )
    if resolved_campaign_payload is not None:
        payload["campaign"] = resolved_campaign_payload
    if badge:
        badge_key = str(badge).strip()
        if "_" in badge_key:
            parts = [part for part in badge_key.split("_") if part]
            if parts:
                badge_key = parts[0] + "".join(
                    part[:1].upper() + part[1:] for part in parts[1:]
                )
        payload["status_badge_key"] = f"module.billing.catalog.badges.{badge_key}"
    if row.product_type == BILLING_PRODUCT_TYPE_PLAN:
        payload["billing_interval"] = BILLING_INTERVAL_LABELS.get(
            row.billing_interval,
            "none",
        )
        payload["billing_interval_count"] = int(row.billing_interval_count or 0)
        payload["auto_renew_enabled"] = bool(row.auto_renew_enabled)
        try:
            payload["plan_tier"] = int(metadata.get("plan_tier"))
        except (TypeError, ValueError):
            payload["plan_tier"] = None
        return BillingPlanDTO(**payload)
    return BillingTopupProductDTO(**payload)


def serialize_wallet(wallet: CreditWallet | None) -> BillingWalletSnapshotDTO:
    if wallet is None:
        return BillingWalletSnapshotDTO(
            available_credits=0,
            reserved_credits=0,
            lifetime_granted_credits=0,
            lifetime_consumed_credits=0,
        )
    return BillingWalletSnapshotDTO(
        available_credits=credit_decimal_to_number(wallet.available_credits),
        reserved_credits=credit_decimal_to_number(wallet.reserved_credits),
        lifetime_granted_credits=credit_decimal_to_number(
            wallet.lifetime_granted_credits
        ),
        lifetime_consumed_credits=credit_decimal_to_number(
            wallet.lifetime_consumed_credits
        ),
    )


def serialize_subscription(
    app: Flask,
    row: BillingSubscription | None,
) -> BillingSubscriptionDTO | None:
    if row is None:
        return None
    product_codes = load_product_code_map([row.product_bid])
    next_product_bid = normalize_bid(row.next_product_bid)
    return BillingSubscriptionDTO(
        subscription_bid=row.subscription_bid,
        product_bid=row.product_bid,
        product_code=product_codes.get(row.product_bid, ""),
        status=BILLING_SUBSCRIPTION_STATUS_LABELS.get(row.status, "draft"),
        billing_provider=str(row.billing_provider or ""),
        current_period_start_at=row.current_period_start_at,
        current_period_end_at=row.current_period_end_at,
        grace_period_end_at=row.grace_period_end_at,
        cancel_at_period_end=bool(row.cancel_at_period_end),
        next_product_bid=next_product_bid or None,
        last_renewed_at=row.last_renewed_at,
        last_failed_at=row.last_failed_at,
    )


def serialize_admin_subscription(
    app: Flask,
    row: BillingSubscription,
    *,
    product_codes: dict[str, str],
    wallet: CreditWallet | None,
    renewal_event: BillingRenewalEvent | None,
) -> AdminBillingSubscriptionDTO:
    next_product_bid = normalize_bid(row.next_product_bid)
    return AdminBillingSubscriptionDTO(
        subscription_bid=row.subscription_bid,
        creator_bid=row.creator_bid,
        product_bid=row.product_bid,
        product_code=product_codes.get(row.product_bid, ""),
        status=BILLING_SUBSCRIPTION_STATUS_LABELS.get(row.status, "draft"),
        billing_provider=str(row.billing_provider or ""),
        current_period_start_at=row.current_period_start_at,
        current_period_end_at=row.current_period_end_at,
        grace_period_end_at=row.grace_period_end_at,
        cancel_at_period_end=bool(row.cancel_at_period_end),
        next_product_bid=next_product_bid or None,
        next_product_code=product_codes.get(next_product_bid, "")
        if next_product_bid
        else "",
        last_renewed_at=row.last_renewed_at,
        last_failed_at=row.last_failed_at,
        wallet=serialize_wallet(wallet),
        latest_renewal_event=serialize_renewal_event(
            app,
            renewal_event,
        ),
        has_attention=_subscription_has_attention(
            row,
            renewal_event=renewal_event,
        ),
    )


def serialize_renewal_event(
    app: Flask,
    row: BillingRenewalEvent | None,
) -> BillingRenewalEventDTO | None:
    if row is None:
        return None
    return BillingRenewalEventDTO(
        renewal_event_bid=row.renewal_event_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_LABELS.get(
            row.event_type,
            "renewal",
        ),
        status=BILLING_RENEWAL_EVENT_STATUS_LABELS.get(row.status, "pending"),
        scheduled_at=row.scheduled_at,
        processed_at=row.processed_at,
        attempt_count=int(row.attempt_count or 0),
        last_error=str(row.last_error or ""),
        payload=normalize_json_object(row.payload_json).to_metadata_json(),
    )


def build_billing_alerts(
    wallet_payload: BillingWalletSnapshotDTO,
    subscription: BillingSubscription | None,
) -> list[BillingAlertDTO]:
    alerts: list[BillingAlertDTO] = []
    available_credits = float(wallet_payload.available_credits or 0)

    if available_credits <= 0:
        alerts.append(
            BillingAlertDTO(
                code="low_balance",
                severity="warning",
                message_key="module.billing.alerts.lowBalance",
                message_params={
                    "available_credits": wallet_payload.available_credits,
                },
                action_type="checkout_topup",
                action_payload={},
            )
        )

    if subscription is None:
        return alerts

    if subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE:
        alerts.append(
            BillingAlertDTO(
                code="subscription_past_due",
                severity="error",
                message_key="module.billing.alerts.subscriptionPastDue",
                action_type="open_orders",
                action_payload={
                    "subscription_bid": subscription.subscription_bid,
                },
            )
        )

    if subscription.cancel_at_period_end:
        alerts.append(
            BillingAlertDTO(
                code="subscription_cancel_scheduled",
                severity="info",
                message_key="module.billing.alerts.cancelScheduled",
                action_type="resume_subscription",
                action_payload={
                    "subscription_bid": subscription.subscription_bid,
                },
            )
        )

    return alerts


def serialize_wallet_bucket(
    app: Flask,
    row: CreditWalletBucket,
) -> BillingWalletBucketDTO:
    runtime_status = CREDIT_BUCKET_STATUS_LABELS.get(row.status, "active")
    if (
        runtime_status == "active"
        and row.effective_to is not None
        and row.effective_to <= now_utc()
    ):
        runtime_status = "expired"

    category_code = resolve_wallet_bucket_runtime_category(
        row,
        load_order_type=load_billing_order_type_by_bid,
    )
    return BillingWalletBucketDTO(
        wallet_bucket_bid=row.wallet_bucket_bid,
        category=CREDIT_BUCKET_CATEGORY_LABELS.get(category_code, "subscription"),
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        source_bid=row.source_bid,
        available_credits=credit_decimal_to_number(row.available_credits),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        priority=resolve_credit_bucket_priority(category_code),
        status=runtime_status,
    )


def serialize_ledger_entry(
    app: Flask,
    row: CreditLedgerEntry,
    *,
    metadata: Any | None = None,
) -> BillingLedgerItemDTO:
    return BillingLedgerItemDTO(
        ledger_bid=row.ledger_bid,
        wallet_bucket_bid=row.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant"),
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        source_bid=row.source_bid,
        idempotency_key=row.idempotency_key,
        amount=credit_decimal_to_number(row.amount),
        balance_after=credit_decimal_to_number(row.balance_after),
        expires_at=row.expires_at,
        consumable_from=row.consumable_from,
        metadata=normalize_json_object(
            row.metadata_json if metadata is None else metadata
        ).to_metadata_json(),
        created_at=row.created_at,
    )


def serialize_daily_usage_metric(
    app: Flask,
    row: BillingDailyUsageMetric,
) -> BillingDailyUsageMetricDTO:
    return BillingDailyUsageMetricDTO(
        daily_usage_metric_bid=row.daily_usage_metric_bid,
        stat_date=row.stat_date,
        shifu_bid=row.shifu_bid,
        usage_scene=_USAGE_SCENE_LABELS.get(row.usage_scene, "production"),
        usage_type=_USAGE_TYPE_LABELS.get(row.usage_type, "llm"),
        provider=str(row.provider or ""),
        model=str(row.model or ""),
        billing_metric=BILLING_METRIC_LABELS.get(
            row.billing_metric,
            "llm_output_tokens",
        ),
        raw_amount=int(row.raw_amount or 0),
        record_count=int(row.record_count or 0),
        consumed_credits=credit_decimal_to_number(row.consumed_credits),
        window_started_at=row.window_started_at,
        window_ended_at=row.window_ended_at,
    )


def serialize_daily_ledger_summary(
    app: Flask,
    row: BillingDailyLedgerSummary,
) -> BillingDailyLedgerSummaryDTO:
    return BillingDailyLedgerSummaryDTO(
        daily_ledger_summary_bid=row.daily_ledger_summary_bid,
        stat_date=row.stat_date,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant"),
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        amount=credit_decimal_to_number(row.amount),
        entry_count=int(row.entry_count or 0),
        window_started_at=row.window_started_at,
        window_ended_at=row.window_ended_at,
    )


def serialize_admin_entitlement_state(
    app: Flask,
    state,
) -> AdminBillingEntitlementDTO:
    return AdminBillingEntitlementDTO(
        creator_bid=normalize_bid(state.creator_bid),
        source_kind=str(state.source_kind or "default"),
        source_type=str(state.source_type or ""),
        source_bid=normalize_bid(state.source_bid) or None,
        product_bid=normalize_bid(state.product_bid),
        branding_enabled=bool(state.branding_enabled),
        custom_domain_enabled=bool(state.custom_domain_enabled),
        priority_class=str(state.priority_class or "standard"),
        analytics_tier=str(state.analytics_tier or "basic"),
        support_tier=str(state.support_tier or "self_serve"),
        effective_from=state.effective_from,
        effective_to=state.effective_to,
        feature_payload=state.feature_payload.to_metadata_json(),
    )


def serialize_admin_domain_binding(
    app: Flask,
    row: BillingDomainBinding,
    *,
    custom_domain_enabled: bool = False,
) -> AdminBillingDomainBindingDTO:
    metadata = normalize_json_object(row.metadata_json)
    verification_record_name = str(
        metadata.get("verification_record_name") or f"_ai-shifu.{row.host}"
    )
    verification_record_value = str(
        metadata.get("verification_record_value") or row.verification_token or ""
    )
    is_effective = bool(
        custom_domain_enabled and row.status == BILLING_DOMAIN_BINDING_STATUS_VERIFIED
    )
    return AdminBillingDomainBindingDTO(
        domain_binding_bid=row.domain_binding_bid,
        creator_bid=row.creator_bid,
        host=row.host,
        status=BILLING_DOMAIN_BINDING_STATUS_LABELS.get(row.status, "pending"),
        verification_method=BILLING_DOMAIN_VERIFICATION_METHOD_LABELS.get(
            row.verification_method,
            "dns_txt",
        ),
        verification_token=row.verification_token,
        verification_record_name=verification_record_name,
        verification_record_value=verification_record_value,
        last_verified_at=row.last_verified_at,
        ssl_status=BILLING_DOMAIN_SSL_STATUS_LABELS.get(
            row.ssl_status,
            "not_requested",
        ),
        is_effective=is_effective,
        custom_domain_enabled=custom_domain_enabled,
        has_attention=bool(
            row.status
            in {
                BILLING_DOMAIN_BINDING_STATUS_PENDING,
                BILLING_DOMAIN_BINDING_STATUS_FAILED,
            }
            or (
                row.status == BILLING_DOMAIN_BINDING_STATUS_VERIFIED
                and not custom_domain_enabled
            )
        ),
        metadata=metadata.to_metadata_json(),
    )


def serialize_admin_daily_usage_metric(
    app: Flask,
    row: BillingDailyUsageMetric,
) -> AdminBillingDailyUsageMetricDTO:
    payload = serialize_daily_usage_metric(
        app,
        row,
    )
    return AdminBillingDailyUsageMetricDTO(
        **payload.__json__(), creator_bid=row.creator_bid
    )


def serialize_admin_daily_ledger_summary(
    app: Flask,
    row: BillingDailyLedgerSummary,
) -> AdminBillingDailyLedgerSummaryDTO:
    payload = serialize_daily_ledger_summary(
        app,
        row,
    )
    return AdminBillingDailyLedgerSummaryDTO(
        **payload.__json__(),
        creator_bid=row.creator_bid,
    )


def serialize_order_summary(
    app: Flask,
    row: BillingOrder,
) -> BillingOrderSummaryDTO:
    subscription_bid = normalize_bid(row.subscription_bid)
    payment_mode = _resolve_billing_order_payment_mode(row)

    return BillingOrderSummaryDTO(
        bill_order_bid=row.bill_order_bid,
        creator_bid=row.creator_bid,
        product_bid=row.product_bid,
        subscription_bid=subscription_bid or None,
        order_type=BILLING_ORDER_TYPE_LABELS.get(row.order_type, "manual"),
        status=BILLING_ORDER_STATUS_LABELS.get(row.status, "init"),
        payment_provider=str(row.payment_provider or ""),
        payment_mode=payment_mode,
        payable_amount=int(row.payable_amount or 0),
        paid_amount=int(row.paid_amount or 0),
        currency=row.currency,
        provider_reference_id=str(row.provider_reference_id or ""),
        failure_message=str(row.failure_message or ""),
        created_at=row.created_at,
        paid_at=row.paid_at,
    )


def serialize_admin_order_summary(
    app: Flask,
    row: BillingOrder,
) -> AdminBillingOrderDTO:
    payload = serialize_order_summary(app, row)
    return AdminBillingOrderDTO(
        **payload.__json__(),
        failure_code=str(row.failure_code or ""),
        failed_at=row.failed_at,
        refunded_at=row.refunded_at,
        has_attention=row.status
        in {
            BILLING_ORDER_STATUS_FAILED,
            BILLING_ORDER_STATUS_PENDING,
            BILLING_ORDER_STATUS_TIMEOUT,
        },
    )


def _resolve_operator_credit_order_kind(product: BillingProduct | None) -> str:
    if product is None:
        return "other"
    if product.product_type == BILLING_PRODUCT_TYPE_PLAN:
        return "plan"
    if product.product_type == BILLING_PRODUCT_TYPE_TOPUP:
        return "topup"
    return "other"


def serialize_operator_credit_order_grant(
    app: Flask,
    *,
    source_type: str,
    source_bid: str,
    granted_credits: int | float,
    valid_from,
    valid_to,
) -> OperatorCreditOrderGrantDTO:
    return OperatorCreditOrderGrantDTO(
        granted_credits=granted_credits,
        valid_from=valid_from,
        valid_to=valid_to,
        source_type=source_type,
        source_bid=source_bid,
    )


def serialize_operator_credit_order(
    app: Flask,
    row: BillingOrder,
    *,
    product: BillingProduct | None,
    creator: dict[str, str],
    grant: OperatorCreditOrderGrantDTO | None,
) -> OperatorCreditOrderDTO:
    order_summary = serialize_admin_order_summary(
        app,
        row,
    )
    return OperatorCreditOrderDTO(
        bill_order_bid=row.bill_order_bid,
        creator_bid=row.creator_bid,
        creator_identify=str(creator.get("identify") or ""),
        creator_mobile=str(creator.get("mobile") or ""),
        creator_email=str(creator.get("email") or ""),
        creator_nickname=str(creator.get("nickname") or ""),
        credit_order_kind=_resolve_operator_credit_order_kind(product),
        product_bid=row.product_bid,
        product_code=str(
            (product.product_code if product is not None else "")
            or row.product_bid
            or ""
        ),
        product_type=(
            BILLING_PRODUCT_TYPE_LABELS.get(product.product_type, "")
            if product is not None
            else ""
        ),
        product_name_key=(
            str(product.display_name_i18n_key or "") if product is not None else ""
        ),
        credit_amount=(
            grant.granted_credits
            if grant is not None
            else (
                credit_decimal_to_number(product.credit_amount)
                if product is not None
                else 0
            )
        ),
        valid_from=grant.valid_from if grant is not None else None,
        valid_to=grant.valid_to if grant is not None else None,
        order_type=order_summary.order_type,
        status=order_summary.status,
        payment_provider=order_summary.payment_provider,
        payment_channel=str(row.channel or ""),
        payable_amount=order_summary.payable_amount,
        paid_amount=order_summary.paid_amount,
        currency=order_summary.currency,
        provider_reference_id=order_summary.provider_reference_id,
        failure_code=str(row.failure_code or ""),
        failure_message=order_summary.failure_message,
        created_at=order_summary.created_at,
        paid_at=order_summary.paid_at,
        failed_at=row.failed_at,
        refunded_at=row.refunded_at,
        has_attention=order_summary.status
        in {
            "failed",
            "pending",
            "timeout",
        },
    )


def _resolve_billing_order_payment_mode(row: BillingOrder) -> str:
    order_label = BILLING_ORDER_TYPE_LABELS.get(int(row.order_type or 0), "manual")
    if order_label.startswith("subscription_"):
        return "subscription"
    return "one_time"


def _subscription_has_attention(
    row: BillingSubscription,
    *,
    renewal_event: BillingRenewalEvent | None,
) -> bool:
    if row.status in {
        BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
        BILLING_SUBSCRIPTION_STATUS_PAUSED,
        BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    }:
        return True
    if renewal_event is None:
        return False
    if renewal_event.status in {
        BILLING_RENEWAL_EVENT_STATUS_PENDING,
        BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
        BILLING_RENEWAL_EVENT_STATUS_FAILED,
    }:
        return True
    return bool(str(renewal_event.last_error or "").strip())
