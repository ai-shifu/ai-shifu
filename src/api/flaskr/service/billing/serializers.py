"""Serialization helpers for billing DTO payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask
from flaskr.util.timezone import get_app_timezone

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
    AdminBillingDailyLedgerSummaryDTO,
    AdminBillingDailyUsageMetricDTO,
    AdminBillingDomainBindingDTO,
    AdminBillingEntitlementDTO,
    AdminBillingOrderDTO,
    AdminBillingSubscriptionDTO,
    BillingAlertDTO,
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
    serialize_dt,
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

_LEDGER_SOURCE_TIMEZONE = "Asia/Shanghai"


def _serialize_ledger_dt(
    app: Flask,
    value,
    *,
    timezone_name: str | None = None,
) -> str | None:
    if value is None:
        return None

    if getattr(value, "tzinfo", None) is not None:
        return serialize_dt(app, value, timezone_name=timezone_name)

    source_tz = get_app_timezone(app, _LEDGER_SOURCE_TIMEZONE)
    target_tz = get_app_timezone(app, timezone_name)
    return value.replace(tzinfo=source_tz).astimezone(target_tz).isoformat()


def serialize_product(row: BillingProduct) -> BillingPlanDTO | BillingTopupProductDTO:
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
    *,
    timezone_name: str | None = None,
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
        current_period_start_at=serialize_dt(
            app,
            row.current_period_start_at,
            timezone_name=timezone_name,
        ),
        current_period_end_at=serialize_dt(
            app,
            row.current_period_end_at,
            timezone_name=timezone_name,
        ),
        grace_period_end_at=serialize_dt(
            app,
            row.grace_period_end_at,
            timezone_name=timezone_name,
        ),
        cancel_at_period_end=bool(row.cancel_at_period_end),
        next_product_bid=next_product_bid or None,
        last_renewed_at=serialize_dt(
            app,
            row.last_renewed_at,
            timezone_name=timezone_name,
        ),
        last_failed_at=serialize_dt(
            app,
            row.last_failed_at,
            timezone_name=timezone_name,
        ),
    )


def serialize_admin_subscription(
    app: Flask,
    row: BillingSubscription,
    *,
    product_codes: dict[str, str],
    wallet: CreditWallet | None,
    renewal_event: BillingRenewalEvent | None,
    timezone_name: str | None = None,
) -> AdminBillingSubscriptionDTO:
    next_product_bid = normalize_bid(row.next_product_bid)
    return AdminBillingSubscriptionDTO(
        subscription_bid=row.subscription_bid,
        creator_bid=row.creator_bid,
        product_bid=row.product_bid,
        product_code=product_codes.get(row.product_bid, ""),
        status=BILLING_SUBSCRIPTION_STATUS_LABELS.get(row.status, "draft"),
        billing_provider=str(row.billing_provider or ""),
        current_period_start_at=serialize_dt(
            app,
            row.current_period_start_at,
            timezone_name=timezone_name,
        ),
        current_period_end_at=serialize_dt(
            app,
            row.current_period_end_at,
            timezone_name=timezone_name,
        ),
        grace_period_end_at=serialize_dt(
            app,
            row.grace_period_end_at,
            timezone_name=timezone_name,
        ),
        cancel_at_period_end=bool(row.cancel_at_period_end),
        next_product_bid=next_product_bid or None,
        next_product_code=product_codes.get(next_product_bid, "")
        if next_product_bid
        else "",
        last_renewed_at=serialize_dt(
            app,
            row.last_renewed_at,
            timezone_name=timezone_name,
        ),
        last_failed_at=serialize_dt(
            app,
            row.last_failed_at,
            timezone_name=timezone_name,
        ),
        wallet=serialize_wallet(wallet),
        latest_renewal_event=serialize_renewal_event(
            app,
            renewal_event,
            timezone_name=timezone_name,
        ),
        has_attention=_subscription_has_attention(
            row,
            renewal_event=renewal_event,
        ),
    )


def serialize_renewal_event(
    app: Flask,
    row: BillingRenewalEvent | None,
    *,
    timezone_name: str | None = None,
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
        scheduled_at=serialize_dt(
            app,
            row.scheduled_at,
            timezone_name=timezone_name,
        ),
        processed_at=serialize_dt(
            app,
            row.processed_at,
            timezone_name=timezone_name,
        ),
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
    *,
    timezone_name: str | None = None,
) -> BillingWalletBucketDTO:
    runtime_status = CREDIT_BUCKET_STATUS_LABELS.get(row.status, "active")
    if (
        runtime_status == "active"
        and row.effective_to is not None
        and row.effective_to <= datetime.now()
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
        effective_from=serialize_dt(
            app,
            row.effective_from,
            timezone_name=timezone_name,
        )
        or "",
        effective_to=serialize_dt(
            app,
            row.effective_to,
            timezone_name=timezone_name,
        ),
        priority=resolve_credit_bucket_priority(category_code),
        status=runtime_status,
    )


def serialize_ledger_entry(
    app: Flask,
    row: CreditLedgerEntry,
    *,
    metadata: Any | None = None,
    timezone_name: str | None = None,
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
        expires_at=_serialize_ledger_dt(
            app,
            row.expires_at,
            timezone_name=timezone_name,
        ),
        consumable_from=_serialize_ledger_dt(
            app,
            row.consumable_from,
            timezone_name=timezone_name,
        ),
        metadata=normalize_json_object(
            row.metadata_json if metadata is None else metadata
        ).to_metadata_json(),
        created_at=_serialize_ledger_dt(
            app,
            row.created_at,
            timezone_name=timezone_name,
        )
        or "",
    )


def serialize_daily_usage_metric(
    app: Flask,
    row: BillingDailyUsageMetric,
    *,
    timezone_name: str | None = None,
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
        window_started_at=serialize_dt(
            app,
            row.window_started_at,
            timezone_name=timezone_name,
        )
        or "",
        window_ended_at=serialize_dt(
            app,
            row.window_ended_at,
            timezone_name=timezone_name,
        )
        or "",
    )


def serialize_daily_ledger_summary(
    app: Flask,
    row: BillingDailyLedgerSummary,
    *,
    timezone_name: str | None = None,
) -> BillingDailyLedgerSummaryDTO:
    return BillingDailyLedgerSummaryDTO(
        daily_ledger_summary_bid=row.daily_ledger_summary_bid,
        stat_date=row.stat_date,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant"),
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        amount=credit_decimal_to_number(row.amount),
        entry_count=int(row.entry_count or 0),
        window_started_at=serialize_dt(
            app,
            row.window_started_at,
            timezone_name=timezone_name,
        )
        or "",
        window_ended_at=serialize_dt(
            app,
            row.window_ended_at,
            timezone_name=timezone_name,
        )
        or "",
    )


def serialize_admin_entitlement_state(
    app: Flask,
    state,
    *,
    timezone_name: str | None = None,
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
        effective_from=serialize_dt(
            app,
            state.effective_from,
            timezone_name=timezone_name,
        ),
        effective_to=serialize_dt(
            app,
            state.effective_to,
            timezone_name=timezone_name,
        ),
        feature_payload=state.feature_payload.to_metadata_json(),
    )


def serialize_admin_domain_binding(
    app: Flask,
    row: BillingDomainBinding,
    *,
    custom_domain_enabled: bool = False,
    timezone_name: str | None = None,
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
        last_verified_at=serialize_dt(
            app,
            row.last_verified_at,
            timezone_name=timezone_name,
        ),
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
    *,
    timezone_name: str | None = None,
) -> AdminBillingDailyUsageMetricDTO:
    payload = serialize_daily_usage_metric(
        app,
        row,
        timezone_name=timezone_name,
    )
    return AdminBillingDailyUsageMetricDTO(
        **payload.__json__(), creator_bid=row.creator_bid
    )


def serialize_admin_daily_ledger_summary(
    app: Flask,
    row: BillingDailyLedgerSummary,
    *,
    timezone_name: str | None = None,
) -> AdminBillingDailyLedgerSummaryDTO:
    payload = serialize_daily_ledger_summary(
        app,
        row,
        timezone_name=timezone_name,
    )
    return AdminBillingDailyLedgerSummaryDTO(
        **payload.__json__(),
        creator_bid=row.creator_bid,
    )


def serialize_order_summary(
    app: Flask,
    row: BillingOrder,
    *,
    timezone_name: str | None = None,
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
        created_at=serialize_dt(app, row.created_at, timezone_name=timezone_name) or "",
        paid_at=serialize_dt(app, row.paid_at, timezone_name=timezone_name),
    )


def serialize_admin_order_summary(
    app: Flask,
    row: BillingOrder,
    *,
    timezone_name: str | None = None,
) -> AdminBillingOrderDTO:
    payload = serialize_order_summary(app, row, timezone_name=timezone_name)
    return AdminBillingOrderDTO(
        **payload.__json__(),
        failure_code=str(row.failure_code or ""),
        failed_at=serialize_dt(
            app,
            row.failed_at,
            timezone_name=timezone_name,
        ),
        refunded_at=serialize_dt(
            app,
            row.refunded_at,
            timezone_name=timezone_name,
        ),
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
    timezone_name: str | None = None,
) -> OperatorCreditOrderGrantDTO:
    return OperatorCreditOrderGrantDTO(
        granted_credits=granted_credits,
        valid_from=_serialize_ledger_dt(
            app,
            valid_from,
            timezone_name=timezone_name,
        ),
        valid_to=_serialize_ledger_dt(
            app,
            valid_to,
            timezone_name=timezone_name,
        ),
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
    timezone_name: str | None = None,
) -> OperatorCreditOrderDTO:
    order_summary = serialize_admin_order_summary(
        app,
        row,
        timezone_name=timezone_name,
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
            credit_decimal_to_number(product.credit_amount)
            if product is not None
            else (grant.granted_credits if grant is not None else 0)
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
        failed_at=serialize_dt(
            app,
            row.failed_at,
            timezone_name=timezone_name,
        ),
        refunded_at=serialize_dt(
            app,
            row.refunded_at,
            timezone_name=timezone_name,
        ),
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
